#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

NATIVE_ACCESS_OPTION = "--enable-native-access=ALL-UNNAMED"
ADD_OPENS_MARKER = " --add-opens "
REQUIRED_LAUNCHERS = (
    "hop/hop-run.bat",
    "hop/hop-run.sh",
    "hop/hop-gui.bat",
    "hop/hop-gui.sh",
)


class PatchError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable Java FFM native access in Apache Hop launcher scripts inside distribution ZIPs."
    )
    parser.add_argument("archives", nargs="+", help="Hop distribution ZIPs to patch in place.")
    return parser.parse_args(argv)


def is_hop_launcher(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    if len(path.parts) != 2 or path.parts[0] != "hop":
        return False
    filename = path.name
    return filename == "hop" or (
        filename.startswith("hop-") and (filename.endswith(".bat") or filename.endswith(".sh"))
    ) or filename in {"hop.bat", "hop.sh"}


def patch_launcher_bytes(name: str, data: bytes) -> tuple[bytes, bool]:
    if not is_hop_launcher(name):
        return data, False

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"Hop launcher '{name}' is not valid UTF-8.") from exc

    if "HOP_OPTIONS" not in text:
        return data, False
    if NATIVE_ACCESS_OPTION in text:
        return data, False
    if ADD_OPENS_MARKER not in text:
        raise PatchError(
            f"Hop launcher '{name}' uses HOP_OPTIONS but has no expected --add-opens option block."
        )

    patched = text.replace(
        ADD_OPENS_MARKER,
        f" {NATIVE_ACCESS_OPTION}{ADD_OPENS_MARKER}",
        1,
    )
    return patched.encode("utf-8"), True


def patch_archive(path: Path) -> list[str]:
    if not path.is_file():
        raise PatchError(f"Distribution ZIP not found: {path}")

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(temp_fd)
    temp_path = Path(temp_name)
    patched_launchers: list[str] = []

    try:
        with zipfile.ZipFile(path, "r") as source_zip, zipfile.ZipFile(
            temp_path, "w", allowZip64=True
        ) as target_zip:
            target_zip.comment = source_zip.comment
            for info in source_zip.infolist():
                data = b"" if info.is_dir() else source_zip.read(info.filename)
                if not info.is_dir():
                    data, changed = patch_launcher_bytes(info.filename, data)
                    if changed:
                        patched_launchers.append(info.filename.replace("\\", "/"))
                target_zip.writestr(info, data)

        validate_archive(temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)

    return patched_launchers


def validate_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
        for launcher in REQUIRED_LAUNCHERS:
            if launcher not in names:
                raise PatchError(f"Distribution '{path.name}' is missing required launcher '{launcher}'.")
            text = archive.read(launcher).decode("utf-8")
            if NATIVE_ACCESS_OPTION not in text:
                raise PatchError(
                    f"Distribution '{path.name}' launcher '{launcher}' does not enable native access."
                )
            if text.count(NATIVE_ACCESS_OPTION) != 1:
                raise PatchError(
                    f"Distribution '{path.name}' launcher '{launcher}' contains native access option more than once."
                )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        for archive_name in args.archives:
            archive = Path(archive_name).resolve()
            patched = patch_archive(archive)
            print(
                f"Patched {archive.name}: "
                + (", ".join(patched) if patched else "launchers already configured")
            )
    except (PatchError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
