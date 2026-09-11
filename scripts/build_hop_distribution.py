#!/usr/bin/env python3
"""Assemble one Hop distribution from current installable Maven snapshots."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

class BuildError(RuntimeError):
    pass

@dataclass(frozen=True)
class PluginArchive:
    path: Path
    required_prefix: str


VERSION_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")


def publication_version(base_version):
    if not isinstance(base_version, str) or not VERSION_PATTERN.fullmatch(base_version):
        raise BuildError(f"Invalid distribution version: {base_version}")

    suffix = os.environ.get("DISTRIBUTION_BUILD_SUFFIX", "").strip()
    prerelease = base_version.endswith("-SNAPSHOT")
    if suffix:
        if not prerelease:
            raise BuildError("DISTRIBUTION_BUILD_SUFFIX is only valid for SNAPSHOT distributions")
        if not VERSION_PATTERN.fullmatch(suffix):
            raise BuildError(f"Invalid distribution build suffix: {suffix}")
        return f"{base_version}.{suffix}", True
    return base_version, prerelease

def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def download(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": "hop-distributions/0.2"})
    with urllib.request.urlopen(request, timeout=120) as source, Path(path).open("wb") as out:
        while chunk := source.read(1024 * 1024):
            out.write(chunk)

def resolve_snapshot(metadata, artifact):
    root = ET.fromstring(metadata)
    versions = [node for node in root.findall("./versioning/snapshotVersions/snapshotVersion")
                if node.findtext("extension") == "zip" and not node.findtext("classifier")]
    if not versions:
        raise BuildError(f"No installable ZIP snapshot for {artifact}")
    version = max(versions, key=lambda node: node.findtext("updated", "")).findtext("value")
    if not version or not re.fullmatch(r"[A-Za-z0-9_.-]+", version):
        raise BuildError(f"Invalid resolved snapshot for {artifact}")
    return version

def validate_runtime(archive, prefix="hop/"):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        central = prefix + "plugins/misc/hop-geometry-type/"
        vector = prefix + "plugins/transforms/vector-raster/"
        for stem, folder in [("hop-geometry-type-", central), ("jts-core-", central + "lib/")]:
            matches = [n for n in names if n.startswith(central) and Path(n).name.startswith(stem) and n.endswith(".jar")]
            if len(matches) != 1 or not matches[0].startswith(folder):
                raise BuildError(f"Expected one central {stem} runtime under {folder}: {matches}")
        for name in names:
            if name.startswith(vector) and Path(name).name.startswith(("hop-geometry-type-", "jts-core-")) and name.endswith(".jar"):
                raise BuildError(f"Obsolete Vector Raster snapshot bundles runtime: {name}")
            if name.startswith(central) and Path(name).name.startswith(("postgresql-", "postgis-jdbc-")):
                raise BuildError(f"Database driver in shared Geometry runtime: {name}")
        try:
            deps = ET.fromstring(z.read(vector + "dependencies.xml"))
        except (KeyError, ET.ParseError) as error:
            raise BuildError("Vector Raster requires its corrected dependencies.xml") from error
        folders = {n.text for n in deps.findall("folder")}
        if not {"../../misc/hop-geometry-type", "../../misc/hop-geometry-type/lib"} <= folders:
            raise BuildError("Vector Raster must reference both central Geometry folders")

def build(config, output):
    output.mkdir(parents=True, exist_ok=True)
    base_version = config["distribution_version"]
    version, prerelease = publication_version(base_version)
    hop = config["hop_version"]
    with tempfile.TemporaryDirectory(prefix="hop-inputs-") as directory:
        work = Path(directory)
        hop_name = f"apache-hop-client-{hop}.zip"
        hop_url = f"https://downloads.apache.org/hop/{hop}/{hop_name}"
        hop_zip = work / hop_name
        try:
            download(hop_url, hop_zip)
        except Exception:
            hop_url = f"https://archive.apache.org/dist/hop/{hop}/{hop_name}"
            download(hop_url, hop_zip)
        actual = digest(hop_zip, "sha512")
        if actual != config["hop_sha512"]:
            raise BuildError("Apache Hop SHA-512 mismatch")
        plugins = []
        resolved = []
        for spec in config["plugins"]:
            artifact = spec["artifact"]
            base = f'{config["snapshot_repository"]}/ch/so/agi/{artifact}/{spec["version"]}/'
            metadata_file = work / (artifact + ".xml")
            download(base + "maven-metadata.xml", metadata_file)
            snapshot = resolve_snapshot(metadata_file.read_bytes(), artifact)
            url = base + f"{artifact}-{snapshot}.zip"
            target = work / (artifact + ".zip")
            download(url, target)
            with zipfile.ZipFile(target) as z:
                for name in z.namelist():
                    normalized = normalize_zip_entry_name(name)
                    if not normalized.endswith("/") and not normalized.startswith(spec["root"] + "/"):
                        raise BuildError(f"Unexpected plugin file {artifact}: {name}")
            plugins.append(PluginArchive(target, spec["root"] + "/"))
            resolved.append(dict(spec, resolved_version=snapshot, url=url, sha256=digest(target)))
        name = f"apache-hop-client-{hop}-geo-{version}.zip"
        archive = output / name
        build_distribution_archive(hop_zip_path=hop_zip, plugin_archives=plugins, output_path=archive)
        validate_runtime(archive)
        metadata = {"schema_version": 2, "distribution_version": base_version,
                    "publication_version": version, "prerelease": prerelease, "hop_version": hop,
                    "commit_sha": os.environ.get("GITHUB_SHA", ""), "release_tag": "v" + version,
                    "release_name": f"Hop Geo Distribution {version} (Apache Hop {hop})",
                    "hop": {"url": hop_url, "sha512": actual}, "plugins": resolved,
                    "artifacts": [{"file": name, "sha256": digest(archive)}]}
        (output / "release-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        (output / (name + ".sha256")).write_text(f'{digest(archive)}  {name}\n')
        return metadata

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "distribution.json")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    print(json.dumps(build(json.loads(args.config.read_text()), args.output_dir), indent=2))

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
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        raise BuildError(f"Unsafe absolute ZIP entry: {name}")
    normalized = name.replace("\\", "/")
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
    main()
