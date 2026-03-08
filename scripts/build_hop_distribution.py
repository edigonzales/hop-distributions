#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_TARGETS = (
    "linux-x86_64",
    "linux-aarch64",
    "osx-x86_64",
    "osx-aarch64",
    "windows-x86_64",
)

GITHUB_API_BASE = "https://api.github.com"
GDAL_PLUGIN_REPO = "edigonzales/hop-gdal-plugin"
GEOMETRY_INSPECTOR_REPO = "edigonzales/hop-geometry-inspector-plugin"
APACHE_HOP_DOWNLOAD_BASE = "https://downloads.apache.org/hop"
USER_AGENT = "hop-distributions-builder/1.0"
VECTOR_SUITE_PREFIX = "hop-vector-suite-"
VECTOR_PLUGIN_PREFIX = "plugins/transforms/ogr-vector/"
GEOMETRY_INSPECTOR_ASSET_PREFIX = "hop-geometry-inspector-plugin-"
GEOMETRY_INSPECTOR_PLUGIN_PREFIX = "plugins/misc/hop-geometry-inspector/"


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    target: str


@dataclass(frozen=True)
class PluginArchive:
    path: Path
    required_prefix: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an Apache Hop client distribution with the hop-gdal-plugin suite "
            "and hop-geometry-inspector-plugin merged in."
        )
    )
    parser.add_argument("--hop-version", required=True, help="Apache Hop version, for example 2.17.0.")
    parser.add_argument(
        "--plugin-release",
        default="latest",
        help="hop-gdal-plugin release tag to use, or 'latest' (default).",
    )
    parser.add_argument(
        "--geometry-inspector-release",
        default="latest",
        help="hop-geometry-inspector-plugin release tag to use, or 'latest' (default).",
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=SUPPORTED_TARGETS,
        help="Target classifier to build. May be specified multiple times. Defaults to all supported targets.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for generated ZIP files.")
    parser.add_argument(
        "--metadata-file",
        help="Optional path for generated build metadata JSON. Defaults to <output-dir>/release-metadata.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = deduplicate_targets(args.target or list(SUPPORTED_TARGETS))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = Path(args.metadata_file).resolve() if args.metadata_file else output_dir / "release-metadata.json"
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        metadata = build_distributions(
            hop_version=args.hop_version,
            plugin_release=args.plugin_release,
            geometry_inspector_release=args.geometry_inspector_release,
            targets=targets,
            output_dir=output_dir,
        )
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    metadata_file.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


def deduplicate_targets(targets: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered_targets: list[str] = []
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        ordered_targets.append(target)
    return ordered_targets


def build_distributions(
    *,
    hop_version: str,
    plugin_release: str,
    geometry_inspector_release: str,
    targets: list[str],
    output_dir: Path,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="hop-dist-build-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        hop_zip_path = download_hop_archive(temp_dir=temp_dir, hop_version=hop_version)
        gdal_release_payload = fetch_github_release(GDAL_PLUGIN_REPO, plugin_release)
        assets_by_target = select_vector_suite_assets(gdal_release_payload)
        geometry_release_payload = fetch_github_release(
            GEOMETRY_INSPECTOR_REPO,
            geometry_inspector_release,
        )
        geometry_asset = select_single_zip_asset(
            geometry_release_payload,
            asset_prefix=GEOMETRY_INSPECTOR_ASSET_PREFIX,
            repo_name=GEOMETRY_INSPECTOR_REPO,
        )

        plugin_tag = gdal_release_payload["tag_name"]
        plugin_tag_safe = sanitize_tag_component(plugin_tag)
        geometry_plugin_tag = geometry_release_payload["tag_name"]
        geometry_plugin_tag_safe = sanitize_tag_component(geometry_plugin_tag)
        geometry_plugin_zip_path = download_release_asset(
            temp_dir=temp_dir,
            asset=geometry_asset,
            required_prefix=GEOMETRY_INSPECTOR_PLUGIN_PREFIX,
        )
        artifacts: list[dict[str, str]] = []

        for target in targets:
            suite_asset = assets_by_target[target]
            suite_zip_path = download_release_asset(
                temp_dir=temp_dir,
                asset=suite_asset,
                required_prefix=VECTOR_PLUGIN_PREFIX,
            )
            output_name = (
                f"apache-hop-client-{hop_version}-hop-gdal-plugin-{plugin_tag_safe}-{target}.zip"
            )
            output_path = output_dir / output_name
            build_distribution_archive(
                hop_zip_path=hop_zip_path,
                plugin_archives=[
                    PluginArchive(path=suite_zip_path, required_prefix=VECTOR_PLUGIN_PREFIX),
                    PluginArchive(
                        path=geometry_plugin_zip_path,
                        required_prefix=GEOMETRY_INSPECTOR_PLUGIN_PREFIX,
                    ),
                ],
                output_path=output_path,
            )
            artifacts.append({"target": target, "file": output_name})

        short_sha = sanitize_tag_component((get_commit_sha() or "manual")[:7])
        return {
            "hop_version": hop_version,
            "plugin_release_tag": plugin_tag,
            "plugin_release_name": gdal_release_payload.get("name") or plugin_tag,
            "plugin_tag_safe": plugin_tag_safe,
            "geometry_inspector_release_tag": geometry_plugin_tag,
            "geometry_inspector_release_name": (
                geometry_release_payload.get("name") or geometry_plugin_tag
            ),
            "geometry_inspector_tag_safe": geometry_plugin_tag_safe,
            "targets": targets,
            "artifacts": artifacts,
            "release_tag": f"hop-{hop_version}-{plugin_tag_safe}-{geometry_plugin_tag_safe}-{short_sha}",
            "release_name": (
                f"Apache Hop {hop_version} + hop-gdal-plugin {plugin_tag} "
                f"+ hop-geometry-inspector-plugin {geometry_plugin_tag} ({short_sha})"
            ),
            "commit_sha": get_commit_sha(),
        }


def get_commit_sha() -> str | None:
    for key in ("GITHUB_SHA", "CI_COMMIT_SHA"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def sanitize_tag_component(value: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    if not sanitized:
        raise BuildError(f"Could not derive a safe identifier from '{value}'.")
    return sanitized


def fetch_github_release(repo_name: str, release_name: str) -> dict:
    if release_name == "latest":
        url = f"{GITHUB_API_BASE}/repos/{repo_name}/releases/latest"
    else:
        url = f"{GITHUB_API_BASE}/repos/{repo_name}/releases/tags/{release_name}"

    try:
        payload = fetch_json(url)
    except BuildError as exc:
        if release_name == "latest":
            raise BuildError(
                f"Could not resolve the latest public release for {repo_name}: {exc}"
            ) from exc
        raise

    if payload.get("draft"):
        raise BuildError(f"Release '{payload.get('tag_name', release_name)}' is still a draft.")
    if payload.get("prerelease"):
        raise BuildError(f"Release '{payload.get('tag_name', release_name)}' is marked as a prerelease.")
    if not payload.get("assets"):
        raise BuildError(f"Release '{payload.get('tag_name', release_name)}' does not contain any assets.")
    return payload


def select_vector_suite_assets(release_payload: dict) -> dict[str, ReleaseAsset]:
    assets_by_target: dict[str, ReleaseAsset] = {}
    for raw_asset in release_payload.get("assets", []):
        name = raw_asset.get("name")
        download_url = raw_asset.get("browser_download_url")
        if not name or not download_url:
            continue

        matched_target = None
        for target in SUPPORTED_TARGETS:
            if name.startswith(VECTOR_SUITE_PREFIX) and name.endswith(f"-{target}.zip"):
                matched_target = target
                break

        if not matched_target:
            continue
        if matched_target in assets_by_target:
            raise BuildError(
                f"Release '{release_payload.get('tag_name')}' contains multiple suite assets for {matched_target}."
            )

        assets_by_target[matched_target] = ReleaseAsset(
            name=name,
            download_url=download_url,
            target=matched_target,
        )

    missing_targets = [target for target in SUPPORTED_TARGETS if target not in assets_by_target]
    if missing_targets:
        missing = ", ".join(missing_targets)
        raise BuildError(
            f"Release '{release_payload.get('tag_name')}' is missing required suite assets for: {missing}."
        )
    return assets_by_target


def download_hop_archive(*, temp_dir: Path, hop_version: str) -> Path:
    archive_name = f"apache-hop-client-{hop_version}.zip"
    archive_url = f"{APACHE_HOP_DOWNLOAD_BASE}/{hop_version}/{archive_name}"
    checksum_url = f"{archive_url}.sha512"
    archive_path = temp_dir / archive_name

    download_file(archive_url, archive_path)
    expected_sha512 = parse_sha512_file(fetch_text(checksum_url), archive_name)
    actual_sha512 = calculate_sha512(archive_path)
    if actual_sha512 != expected_sha512:
        raise BuildError(
            f"SHA-512 mismatch for {archive_name}: expected {expected_sha512}, got {actual_sha512}."
        )
    return archive_path


def select_single_zip_asset(release_payload: dict, *, asset_prefix: str, repo_name: str) -> ReleaseAsset:
    matching_assets = [
        asset
        for asset in release_payload.get("assets", [])
        if asset.get("name", "").startswith(asset_prefix) and asset.get("name", "").endswith(".zip")
    ]
    if len(matching_assets) != 1:
        raise BuildError(
            f"Release '{release_payload.get('tag_name')}' in {repo_name} must contain exactly one '{asset_prefix}*.zip' asset."
        )
    asset = matching_assets[0]
    return ReleaseAsset(name=asset["name"], download_url=asset["browser_download_url"], target="generic")


def download_release_asset(*, temp_dir: Path, asset: ReleaseAsset, required_prefix: str) -> Path:
    asset_path = temp_dir / asset.name
    if asset_path.exists():
        return asset_path
    download_file(asset.download_url, asset_path)
    validate_plugin_archive(asset_path, required_prefix)
    return asset_path


def fetch_json(url: str) -> dict:
    data = fetch_bytes(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"Response from {url} is not valid JSON.") from exc


def fetch_text(url: str) -> str:
    return fetch_bytes(url, headers={"User-Agent": USER_AGENT}).decode("utf-8")


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise BuildError(f"HTTP {exc.code} while requesting {url}.") from exc
    except urllib.error.URLError as exc:
        raise BuildError(f"Could not reach {url}: {exc.reason}.") from exc


def fetch_bytes(url: str, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise BuildError(f"HTTP {exc.code} while requesting {url}.") from exc
    except urllib.error.URLError as exc:
        raise BuildError(f"Could not reach {url}: {exc.reason}.") from exc


def parse_sha512_file(contents: str, archive_name: str) -> str:
    line = contents.strip().splitlines()[0].strip()
    parts = line.split()
    if len(parts) < 2:
        raise BuildError(f"Unexpected SHA-512 file format for {archive_name}.")
    checksum = parts[0]
    referenced_file = parts[-1].lstrip("*")
    if referenced_file != archive_name:
        raise BuildError(
            f"SHA-512 file references '{referenced_file}' instead of '{archive_name}'."
        )
    if not re.fullmatch(r"[0-9a-fA-F]{128}", checksum):
        raise BuildError(f"Invalid SHA-512 checksum for {archive_name}.")
    return checksum.lower()


def calculate_sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_plugin_archive(plugin_zip_path: Path, required_prefix: str) -> None:
    with zipfile.ZipFile(plugin_zip_path) as suite_zip:
        has_plugin = any(
            normalize_zip_entry_name(info.filename).startswith(required_prefix)
            for info in suite_zip.infolist()
            if info.filename
        )
        if not has_plugin:
            raise BuildError(
                f"Plugin archive '{plugin_zip_path.name}' does not contain {required_prefix}."
            )


def build_distribution_archive(
    *,
    hop_zip_path: Path,
    plugin_archives: list[PluginArchive],
    output_path: Path,
) -> None:
    for plugin_archive in plugin_archives:
        validate_plugin_archive(plugin_archive.path, plugin_archive.required_prefix)

    with tempfile.TemporaryDirectory(prefix="hop-merge-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with zipfile.ZipFile(hop_zip_path) as hop_zip:
            safe_extract_all(hop_zip, temp_dir)

        hop_root = temp_dir / "hop"
        if not hop_root.is_dir():
            raise BuildError(f"Hop archive '{hop_zip_path.name}' does not contain a top-level 'hop/' directory.")

        for plugin_archive in plugin_archives:
            with zipfile.ZipFile(plugin_archive.path) as plugin_zip:
                safe_extract_all(plugin_zip, hop_root)

        for plugin_archive in plugin_archives:
            required_path = hop_root / Path(plugin_archive.required_prefix.rstrip("/"))
            if not required_path.exists():
                raise BuildError(
                    f"Plugin archive '{plugin_archive.path.name}' was not merged into hop/{plugin_archive.required_prefix}."
                )

    merge_zip_archives(hop_zip_path=hop_zip_path, plugin_archives=plugin_archives, output_path=output_path)
    validate_output_archive(output_path, [archive.required_prefix for archive in plugin_archives])


def safe_extract_all(zip_file: zipfile.ZipFile, destination: Path) -> None:
    for info in zip_file.infolist():
        normalized = normalize_zip_entry_name(info.filename)
        target_path = destination / normalized.rstrip("/")
        if info.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(info) as source_handle, target_path.open("wb") as target_handle:
            target_handle.write(source_handle.read())


def normalize_zip_entry_name(name: str) -> str:
    normalized = name.replace("\\", "/").lstrip("/")
    is_directory = normalized.endswith("/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise BuildError(f"Unsafe ZIP entry name: '{name}'.")
    normalized = "/".join(parts)
    if is_directory:
        normalized += "/"
    return normalized


def merge_zip_archives(*, hop_zip_path: Path, plugin_archives: list[PluginArchive], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        hop_zip = stack.enter_context(zipfile.ZipFile(hop_zip_path))
        opened_plugin_zips = [
            (plugin_archive, stack.enter_context(zipfile.ZipFile(plugin_archive.path)))
            for plugin_archive in plugin_archives
        ]
        output_zip = stack.enter_context(zipfile.ZipFile(output_path, mode="w", allowZip64=True))
        output_zip.comment = hop_zip.comment
        prefixed_plugin_names, prefixed_plugin_entries = collect_prefixed_plugin_entries(opened_plugin_zips)

        for info in hop_zip.infolist():
            normalized_name = normalize_zip_entry_name(info.filename)
            if normalized_name in prefixed_plugin_names:
                continue
            copy_zip_entry(
                source_zip=hop_zip,
                source_info=info,
                destination_zip=output_zip,
                destination_name=normalized_name,
            )

        for source_zip, source_info, destination_name in prefixed_plugin_entries:
            copy_zip_entry(
                source_zip=source_zip,
                source_info=source_info,
                destination_zip=output_zip,
                destination_name=destination_name,
            )


def collect_prefixed_plugin_entries(
    opened_plugin_zips: list[tuple[PluginArchive, zipfile.ZipFile]],
) -> tuple[set[str], list[tuple[zipfile.ZipFile, zipfile.ZipInfo, str]]]:
    prefixed_names: set[str] = set()
    prefixed_entries: list[tuple[zipfile.ZipFile, zipfile.ZipInfo, str]] = []
    for plugin_archive, plugin_zip in opened_plugin_zips:
        seen_in_archive: set[str] = set()
        for info in plugin_zip.infolist():
            normalized_name = normalize_zip_entry_name(info.filename)
            if normalized_name.startswith("hop/"):
                raise BuildError(
                    f"Plugin archive '{plugin_archive.path.name}' must not include a top-level 'hop/' directory."
                )
            destination_name = f"hop/{normalized_name}"
            if destination_name in seen_in_archive:
                raise BuildError(
                    f"Plugin archive '{plugin_archive.path.name}' contains duplicate entry '{destination_name}'."
                )
            seen_in_archive.add(destination_name)

            if destination_name in prefixed_names:
                if info.is_dir():
                    continue
                raise BuildError(
                    f"Plugin archives overlap on file '{destination_name}'."
                )

            prefixed_names.add(destination_name)
            prefixed_entries.append((plugin_zip, info, destination_name))
    return prefixed_names, prefixed_entries


def copy_zip_entry(
    *,
    source_zip: zipfile.ZipFile,
    source_info: zipfile.ZipInfo,
    destination_zip: zipfile.ZipFile,
    destination_name: str,
) -> None:
    if source_info.is_dir() and not destination_name.endswith("/"):
        destination_name += "/"

    destination_info = clone_zip_info(source_info, destination_name)
    data = b"" if source_info.is_dir() else source_zip.read(source_info.filename)
    destination_zip.writestr(destination_info, data)


def clone_zip_info(source_info: zipfile.ZipInfo, destination_name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=destination_name, date_time=source_info.date_time)
    info.comment = source_info.comment
    info.compress_type = source_info.compress_type
    info.create_system = source_info.create_system
    info.create_version = source_info.create_version
    info.extract_version = source_info.extract_version
    info.extra = source_info.extra
    info.external_attr = source_info.external_attr
    info.flag_bits = source_info.flag_bits
    info.internal_attr = source_info.internal_attr
    info.volume = source_info.volume
    return info


def validate_output_archive(output_path: Path, required_prefixes: list[str]) -> None:
    with zipfile.ZipFile(output_path) as output_zip:
        names = [normalize_zip_entry_name(name) for name in output_zip.namelist() if name]
    if "hop/" not in names and not any(name.startswith("hop/") for name in names):
        raise BuildError(f"Output archive '{output_path.name}' does not contain a top-level 'hop/' directory.")
    for required_prefix in required_prefixes:
        if not any(name.startswith(f"hop/{required_prefix}") for name in names):
            raise BuildError(
                f"Output archive '{output_path.name}' does not contain hop/{required_prefix}."
            )
    if not any(name.startswith("hop/lib/") for name in names):
        raise BuildError(f"Output archive '{output_path.name}' is missing hop/lib/.")


if __name__ == "__main__":
    sys.exit(main())
