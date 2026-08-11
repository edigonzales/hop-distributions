from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


def load_module():
    module_path = Path(__file__).with_name("patch_hop_launchers.py")
    spec = importlib.util.spec_from_file_location("patch_hop_launchers", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


patcher = load_module()


class PatchHopLaunchersTests(unittest.TestCase):
    def test_patch_archive_enables_native_access_and_preserves_permissions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-launcher-test-") as temp_dir_name:
            archive_path = Path(temp_dir_name) / "distribution.zip"
            self.create_distribution_zip(archive_path)

            patched = patcher.patch_archive(archive_path)

            self.assertIn("hop/hop-run.bat", patched)
            self.assertIn("hop/hop-gui.bat", patched)
            self.assertIn("hop/hop-run.sh", patched)
            self.assertIn("hop/hop-gui.sh", patched)

            with zipfile.ZipFile(archive_path) as archive:
                for launcher in patcher.REQUIRED_LAUNCHERS:
                    text = archive.read(launcher).decode("utf-8")
                    self.assertEqual(1, text.count(patcher.NATIVE_ACCESS_OPTION))
                    self.assertIn(
                        f"{patcher.NATIVE_ACCESS_OPTION} --add-opens",
                        text,
                    )

                mode = (archive.getinfo("hop/hop-run.sh").external_attr >> 16) & 0o777
                self.assertEqual(0o755, mode)
                self.assertEqual(b"core", archive.read("hop/lib/core.jar"))

    def test_patch_archive_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-launcher-test-") as temp_dir_name:
            archive_path = Path(temp_dir_name) / "distribution.zip"
            self.create_distribution_zip(archive_path)

            patcher.patch_archive(archive_path)
            patched_again = patcher.patch_archive(archive_path)

            self.assertEqual([], patched_again)
            with zipfile.ZipFile(archive_path) as archive:
                for launcher in patcher.REQUIRED_LAUNCHERS:
                    text = archive.read(launcher).decode("utf-8")
                    self.assertEqual(1, text.count(patcher.NATIVE_ACCESS_OPTION))

    def create_distribution_zip(self, path: Path) -> None:
        bat = (
            '@echo off\r\n'
            'if "%HOP_OPTIONS%"=="" set HOP_OPTIONS="-Xmx2048m"\r\n'
            'set HOP_OPTIONS=%HOP_OPTIONS% --add-opens java.base/java.lang=ALL-UNNAMED\r\n'
            '%_HOP_JAVA% %HOP_OPTIONS% org.example.Main\r\n'
        ).encode("utf-8")
        sh = (
            '#!/usr/bin/env bash\n'
            'HOP_OPTIONS="${HOP_OPTIONS:--Xmx2048m}"\n'
            'HOP_OPTIONS="${HOP_OPTIONS} --add-opens java.base/java.lang=ALL-UNNAMED"\n'
            '"${_HOP_JAVA}" ${HOP_OPTIONS} org.example.Main\n'
        ).encode("utf-8")

        with zipfile.ZipFile(path, "w") as archive:
            for name in ("hop/hop-run.bat", "hop/hop-gui.bat"):
                archive.writestr(self.file_info(name, 0o644), bat)
            for name in ("hop/hop-run.sh", "hop/hop-gui.sh"):
                archive.writestr(self.file_info(name, 0o755), sh)
            archive.writestr(self.file_info("hop/lib/core.jar", 0o644), b"core")

    def file_info(self, name: str, mode: int) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        return info


if __name__ == "__main__":
    unittest.main()
