#!/usr/bin/env python3
"""Fail when a finished Hop distribution contains incompatible GeoTools versions."""

from __future__ import annotations

import argparse
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeoToolsArtifact:
    distribution_path: str
    artifact_id: str
    version: str


def _read_properties(raw: bytes) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw_line in raw.decode("iso-8859-1").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key, value = line.split(separator, 1)
        properties[key.strip()] = value.strip()
    return properties


def geotools_artifacts(archive: Path) -> list[GeoToolsArtifact]:
    findings: list[GeoToolsArtifact] = []
    with zipfile.ZipFile(archive) as distribution:
        for member in distribution.namelist():
            if not member.endswith(".jar") or "/plugins/" not in member:
                continue

            try:
                jar_bytes = distribution.read(member)
                with zipfile.ZipFile(io.BytesIO(jar_bytes)) as jar:
                    for entry in jar.namelist():
                        if not entry.startswith("META-INF/maven/org.geotools/"):
                            continue
                        if not entry.endswith("/pom.properties"):
                            continue

                        properties = _read_properties(jar.read(entry))
                        version = properties.get("version", "").strip()
                        artifact_id = properties.get("artifactId", "").strip()
                        group_id = properties.get("groupId", "").strip()
                        if group_id == "org.geotools" and version:
                            findings.append(
                                GeoToolsArtifact(
                                    distribution_path=member,
                                    artifact_id=artifact_id or Path(member).stem,
                                    version=version,
                                )
                            )
            except zipfile.BadZipFile:
                # Not every file ending in .jar in a third-party plugin necessarily has to be a
                # conventional ZIP/JAR. Ignore such files; they cannot expose Maven GeoTools
                # metadata anyway.
                continue

    return findings


def verify_archive(archive: Path, expected_version: str | None = None) -> str:
    artifacts = geotools_artifacts(archive)
    if not artifacts:
        raise RuntimeError(f"No org.geotools Maven artifacts found in {archive}")

    versions = sorted({artifact.version for artifact in artifacts})
    if len(versions) != 1:
        details = "\n".join(
            f"  {artifact.version}: {artifact.distribution_path} ({artifact.artifact_id})"
            for artifact in sorted(
                artifacts,
                key=lambda artifact: (
                    artifact.version,
                    artifact.distribution_path,
                    artifact.artifact_id,
                ),
            )
        )
        raise RuntimeError(
            f"Mixed GeoTools versions in {archive}: {', '.join(versions)}\n{details}"
        )

    version = versions[0]
    if expected_version is not None and version != expected_version:
        raise RuntimeError(
            f"Unexpected GeoTools version in {archive}: {version}; expected {expected_version}"
        )

    return version


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that finished Hop ZIPs contain exactly one GeoTools runtime version."
    )
    parser.add_argument(
        "--expected-version",
        help="Also require this exact GeoTools version (for example 35.0).",
    )
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()

    for archive in args.archives:
        version = verify_archive(archive, args.expected_version)
        print(f"GeoTools version OK: {archive} -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
