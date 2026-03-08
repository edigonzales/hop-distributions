from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


def load_module():
    module_path = Path(__file__).with_name("build_hop_distribution.py")
    spec = importlib.util.spec_from_file_location("build_hop_distribution", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_module()


class BuildHopDistributionTests(unittest.TestCase):
    def test_select_vector_suite_assets_returns_all_targets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": f"hop-vector-suite-1.2.3-{target}.zip",
                    "browser_download_url": f"https://example.test/{target}.zip",
                }
                for target in builder.SUPPORTED_TARGETS
            ]
            + [
                {
                    "name": "notes.txt",
                    "browser_download_url": "https://example.test/notes.txt",
                }
            ],
        }

        assets = builder.select_vector_suite_assets(release_payload)

        self.assertEqual(set(builder.SUPPORTED_TARGETS), set(assets.keys()))
        self.assertEqual("linux-x86_64", assets["linux-x86_64"].target)

    def test_select_vector_suite_assets_requires_all_targets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": f"hop-vector-suite-1.2.3-{target}.zip",
                    "browser_download_url": f"https://example.test/{target}.zip",
                }
                for target in builder.SUPPORTED_TARGETS
                if target != "windows-x86_64"
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_vector_suite_assets(release_payload)

    def test_build_distribution_archive_merges_plugin_and_preserves_permissions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-dist-test-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            hop_zip = temp_dir / "hop.zip"
            suite_zip = temp_dir / "suite.zip"
            geometry_zip = temp_dir / "geometry.zip"
            output_zip = temp_dir / "output.zip"

            self.create_hop_zip(hop_zip)
            self.create_suite_zip(suite_zip)
            self.create_geometry_zip(geometry_zip)

            builder.build_distribution_archive(
                hop_zip_path=hop_zip,
                plugin_archives=[
                    builder.PluginArchive(
                        path=suite_zip,
                        required_prefix=builder.VECTOR_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=geometry_zip,
                        required_prefix=builder.GEOMETRY_INSPECTOR_PLUGIN_PREFIX,
                    ),
                ],
                output_path=output_zip,
            )

            with zipfile.ZipFile(output_zip) as archive:
                names = archive.namelist()
                self.assertIn("hop/lib/core.jar", names)
                self.assertIn("hop/plugins/transforms/ogr-vector/plugin.jar", names)
                self.assertIn(
                    "hop/plugins/misc/hop-geometry-inspector/geometry-inspector.jar",
                    names,
                )
                mode = (archive.getinfo("hop/hop-gui.sh").external_attr >> 16) & 0o777
                self.assertEqual(0o755, mode)

    def test_build_distribution_archive_rejects_missing_plugin_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-dist-test-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            hop_zip = temp_dir / "hop.zip"
            geometry_zip = temp_dir / "geometry.zip"
            output_zip = temp_dir / "output.zip"

            self.create_hop_zip(hop_zip)
            with zipfile.ZipFile(geometry_zip, "w") as archive:
                archive.writestr("plugins/transforms/other-plugin/plugin.jar", b"plugin")

            with self.assertRaises(builder.BuildError):
                builder.build_distribution_archive(
                    hop_zip_path=hop_zip,
                    plugin_archives=[
                        builder.PluginArchive(
                            path=geometry_zip,
                            required_prefix=builder.GEOMETRY_INSPECTOR_PLUGIN_PREFIX,
                        )
                    ],
                    output_path=output_zip,
                )

    def test_select_single_zip_asset_returns_geometry_archive(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-geometry-inspector-plugin-1.2.3.zip",
                    "browser_download_url": "https://example.test/geometry.zip",
                }
            ],
        }

        asset = builder.select_single_zip_asset(
            release_payload,
            asset_prefix=builder.GEOMETRY_INSPECTOR_ASSET_PREFIX,
            repo_name=builder.GEOMETRY_INSPECTOR_REPO,
        )

        self.assertEqual("hop-geometry-inspector-plugin-1.2.3.zip", asset.name)
        self.assertEqual("generic", asset.target)

    def create_hop_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("hop/"), b"")
            archive.writestr(self.dir_info("hop/lib/"), b"")
            archive.writestr(self.dir_info("hop/plugins/"), b"")
            archive.writestr(self.file_info("hop/lib/core.jar", 0o644), b"core")
            archive.writestr(self.file_info("hop/hop-gui.sh", 0o755), b"#!/bin/sh\nexit 0\n")

    def create_suite_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/transforms/ogr-vector/"), b"")
            archive.writestr(
                self.file_info("plugins/transforms/ogr-vector/plugin.jar", 0o644),
                b"plugin",
            )

    def create_geometry_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/misc/hop-geometry-inspector/"), b"")
            archive.writestr(
                self.file_info(
                    "plugins/misc/hop-geometry-inspector/geometry-inspector.jar",
                    0o644,
                ),
                b"geometry",
            )

    def dir_info(self, name: str) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = 0o755 << 16
        return info

    def file_info(self, name: str, mode: int) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        return info


if __name__ == "__main__":
    unittest.main()
