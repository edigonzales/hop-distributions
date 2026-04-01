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
    def test_select_gdal_suite_assets_returns_all_targets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": f"hop-gdal-suite-1.2.3-{target}.zip",
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

        assets = builder.select_gdal_suite_assets(release_payload)

        self.assertEqual(set(builder.SUPPORTED_TARGETS), set(assets.keys()))
        self.assertEqual("linux-x86_64", assets["linux-x86_64"].target)

    def test_select_gdal_suite_assets_requires_all_targets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": f"hop-gdal-suite-1.2.3-{target}.zip",
                    "browser_download_url": f"https://example.test/{target}.zip",
                }
                for target in builder.SUPPORTED_TARGETS
                if target != "windows-x86_64"
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_gdal_suite_assets(release_payload)

    def test_compact_tag_component_keeps_short_tag(self) -> None:
        self.assertEqual("v1.2.3", builder.compact_tag_component("v1.2.3"))

    def test_compact_tag_component_uses_trailing_hash_for_long_auto_release_tag(self) -> None:
        self.assertEqual(
            "97ff5c8",
            builder.compact_tag_component("auto-v0.1.0-SNAPSHOT-20260317-1648-97ff5c8"),
        )

    def test_compact_tag_component_truncates_non_hash_long_tag(self) -> None:
        compact = builder.compact_tag_component("release-name-without-commit-hash-but-still-very-long")
        self.assertLessEqual(len(compact), builder.MAX_TAG_ID_LENGTH)
        self.assertRegex(compact, r"^[0-9A-Za-z._-]+$")

    def test_build_distribution_archive_merges_plugin_and_preserves_permissions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-dist-test-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            hop_zip = temp_dir / "hop.zip"
            suite_zip = temp_dir / "suite.zip"
            geometry_zip = temp_dir / "geometry.zip"
            geoprocessing_zip = temp_dir / "geoprocessing.zip"
            ili2db_action_zip = temp_dir / "ili2db-action.zip"
            ili2db_transform_zip = temp_dir / "ili2db-transform.zip"
            ilivalidator_action_zip = temp_dir / "ilivalidator-action.zip"
            ilivalidator_transform_zip = temp_dir / "ilivalidator-transform.zip"
            output_zip = temp_dir / "output.zip"

            self.create_hop_zip(hop_zip)
            self.create_suite_zip(suite_zip)
            self.create_geometry_zip(geometry_zip)
            self.create_geoprocessing_zip(geoprocessing_zip)
            self.create_ili2db_action_zip(ili2db_action_zip)
            self.create_ili2db_transform_zip(ili2db_transform_zip)
            self.create_ilivalidator_action_zip(ilivalidator_action_zip)
            self.create_ilivalidator_transform_zip(ilivalidator_transform_zip)

            builder.build_distribution_archive(
                hop_zip_path=hop_zip,
                plugin_archives=[
                    builder.PluginArchive(
                        path=suite_zip,
                        required_prefix=builder.GDAL_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=geometry_zip,
                        required_prefix=builder.GEOMETRY_INSPECTOR_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=geoprocessing_zip,
                        required_prefix=builder.GEOPROCESSING_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=ili2db_action_zip,
                        required_prefix=builder.ILI2DB_ACTION_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=ili2db_transform_zip,
                        required_prefix=builder.ILI2DB_TRANSFORM_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=ilivalidator_action_zip,
                        required_prefix=builder.ILIVALIDATOR_ACTION_PLUGIN_PREFIX,
                    ),
                    builder.PluginArchive(
                        path=ilivalidator_transform_zip,
                        required_prefix=builder.ILIVALIDATOR_TRANSFORM_PLUGIN_PREFIX,
                    ),
                ],
                output_path=output_zip,
            )

            with zipfile.ZipFile(output_zip) as archive:
                names = archive.namelist()
                self.assertIn("hop/lib/core.jar", names)
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-ogr-reader.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-gdal-raster-info.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/misc/hop-geometry-inspector/geometry-inspector.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/hop-geoprocessing/geoprocessing.jar",
                    names,
                )
                self.assertIn("hop/plugins/actions/ili2db/hop-action-ili2db.jar", names)
                self.assertIn("hop/plugins/transforms/ili2db/hop-transform-ili2db.jar", names)
                self.assertIn(
                    "hop/plugins/actions/ilivalidator/hop-action-ilivalidator.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/ilivalidator/hop-transform-ilivalidator.jar",
                    names,
                )
                mode = (archive.getinfo("hop/hop-gui.sh").external_attr >> 16) & 0o777
                self.assertEqual(0o755, mode)

    def test_build_distribution_archive_merges_gdal_suite_vector_and_raster_transforms(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-dist-test-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            hop_zip = temp_dir / "hop.zip"
            suite_zip = temp_dir / "suite.zip"
            output_zip = temp_dir / "output.zip"

            self.create_hop_zip(hop_zip)
            self.create_suite_zip(suite_zip)

            builder.build_distribution_archive(
                hop_zip_path=hop_zip,
                plugin_archives=[
                    builder.PluginArchive(
                        path=suite_zip,
                        required_prefix=builder.GDAL_PLUGIN_PREFIX,
                    )
                ],
                output_path=output_zip,
            )

            with zipfile.ZipFile(output_zip) as archive:
                names = archive.namelist()
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-ogr-reader.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-ogr-exporter.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-gdal-raster-info.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/gdal-suite/hop-transform-gdal-raster-clip.jar",
                    names,
                )

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

    def test_select_single_zip_asset_returns_ili2db_action_archive(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-action-ili2db-1.2.3.zip",
                    "browser_download_url": "https://example.test/ili2db-action.zip",
                },
                {
                    "name": "hop-transform-ili2db-1.2.3.zip",
                    "browser_download_url": "https://example.test/ili2db-transform.zip",
                },
            ],
        }

        asset = builder.select_single_zip_asset(
            release_payload,
            asset_prefix=builder.ILI2DB_ACTION_ASSET_PREFIX,
            repo_name=builder.ILI2DB_PLUGIN_REPO,
        )

        self.assertEqual("hop-action-ili2db-1.2.3.zip", asset.name)
        self.assertEqual("generic", asset.target)

    def test_select_single_zip_asset_returns_geoprocessing_archive(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-geoprocessing-plugin-1.2.3.zip",
                    "browser_download_url": "https://example.test/geoprocessing.zip",
                }
            ],
        }

        asset = builder.select_single_zip_asset(
            release_payload,
            asset_prefix=builder.GEOPROCESSING_ASSET_PREFIX,
            repo_name=builder.GEOPROCESSING_PLUGIN_REPO,
        )

        self.assertEqual("hop-geoprocessing-plugin-1.2.3.zip", asset.name)
        self.assertEqual("generic", asset.target)

    def test_select_single_zip_asset_requires_exactly_one_match(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-action-ili2db-1.2.3.zip",
                    "browser_download_url": "https://example.test/ili2db-action-1.zip",
                },
                {
                    "name": "hop-action-ili2db-1.2.4.zip",
                    "browser_download_url": "https://example.test/ili2db-action-2.zip",
                },
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.ILI2DB_ACTION_ASSET_PREFIX,
                repo_name=builder.ILI2DB_PLUGIN_REPO,
            )

    def test_select_single_zip_asset_fails_when_missing(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-transform-ili2db-1.2.3.zip",
                    "browser_download_url": "https://example.test/ili2db-transform.zip",
                }
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.ILI2DB_ACTION_ASSET_PREFIX,
                repo_name=builder.ILI2DB_PLUGIN_REPO,
            )

    def test_select_single_zip_asset_returns_ilivalidator_action_archive(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-action-ilivalidator-1.2.3.zip",
                    "browser_download_url": "https://example.test/ilivalidator-action.zip",
                },
                {
                    "name": "hop-transform-ilivalidator-1.2.3.zip",
                    "browser_download_url": "https://example.test/ilivalidator-transform.zip",
                },
            ],
        }

        asset = builder.select_single_zip_asset(
            release_payload,
            asset_prefix=builder.ILIVALIDATOR_ACTION_ASSET_PREFIX,
            repo_name=builder.ILIVALIDATOR_PLUGIN_REPO,
        )

        self.assertEqual("hop-action-ilivalidator-1.2.3.zip", asset.name)
        self.assertEqual("generic", asset.target)

    def test_select_single_zip_asset_rejects_duplicate_ilivalidator_action_assets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-action-ilivalidator-1.2.3.zip",
                    "browser_download_url": "https://example.test/ilivalidator-action-1.zip",
                },
                {
                    "name": "hop-action-ilivalidator-1.2.4.zip",
                    "browser_download_url": "https://example.test/ilivalidator-action-2.zip",
                },
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.ILIVALIDATOR_ACTION_ASSET_PREFIX,
                repo_name=builder.ILIVALIDATOR_PLUGIN_REPO,
            )

    def test_select_single_zip_asset_rejects_missing_ilivalidator_transform_asset(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-action-ilivalidator-1.2.3.zip",
                    "browser_download_url": "https://example.test/ilivalidator-action.zip",
                }
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.ILIVALIDATOR_TRANSFORM_ASSET_PREFIX,
                repo_name=builder.ILIVALIDATOR_PLUGIN_REPO,
            )

    def test_select_single_zip_asset_rejects_duplicate_geoprocessing_assets(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "hop-geoprocessing-plugin-1.2.3.zip",
                    "browser_download_url": "https://example.test/geoprocessing-1.zip",
                },
                {
                    "name": "hop-geoprocessing-plugin-1.2.4.zip",
                    "browser_download_url": "https://example.test/geoprocessing-2.zip",
                },
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.GEOPROCESSING_ASSET_PREFIX,
                repo_name=builder.GEOPROCESSING_PLUGIN_REPO,
            )

    def test_select_single_zip_asset_rejects_missing_geoprocessing_asset(self) -> None:
        release_payload = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "notes.txt",
                    "browser_download_url": "https://example.test/notes.txt",
                }
            ],
        }

        with self.assertRaises(builder.BuildError):
            builder.select_single_zip_asset(
                release_payload,
                asset_prefix=builder.GEOPROCESSING_ASSET_PREFIX,
                repo_name=builder.GEOPROCESSING_PLUGIN_REPO,
            )

    def create_hop_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("hop/"), b"")
            archive.writestr(self.dir_info("hop/lib/"), b"")
            archive.writestr(self.dir_info("hop/plugins/"), b"")
            archive.writestr(self.file_info("hop/lib/core.jar", 0o644), b"core")
            archive.writestr(self.file_info("hop/hop-gui.sh", 0o755), b"#!/bin/sh\nexit 0\n")

    def create_suite_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/transforms/gdal-suite/"), b"")
            archive.writestr(self.dir_info("plugins/transforms/gdal-suite/lib/"), b"")
            archive.writestr(
                self.file_info("plugins/transforms/gdal-suite/hop-transform-ogr-reader.jar", 0o644),
                b"ogr-reader",
            )
            archive.writestr(
                self.file_info("plugins/transforms/gdal-suite/hop-transform-ogr-exporter.jar", 0o644),
                b"ogr-exporter",
            )
            archive.writestr(
                self.file_info(
                    "plugins/transforms/gdal-suite/hop-transform-gdal-raster-info.jar",
                    0o644,
                ),
                b"raster-info",
            )
            archive.writestr(
                self.file_info(
                    "plugins/transforms/gdal-suite/hop-transform-gdal-raster-clip.jar",
                    0o644,
                ),
                b"raster-clip",
            )
            archive.writestr(
                self.file_info("plugins/transforms/gdal-suite/lib/hop-ogr-core.jar", 0o644),
                b"core-lib",
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

    def create_ili2db_action_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/actions/ili2db/"), b"")
            archive.writestr(
                self.file_info("plugins/actions/ili2db/hop-action-ili2db.jar", 0o644),
                b"ili2db-action",
            )

    def create_geoprocessing_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/transforms/hop-geoprocessing/"), b"")
            archive.writestr(
                self.file_info(
                    "plugins/transforms/hop-geoprocessing/geoprocessing.jar",
                    0o644,
                ),
                b"geoprocessing",
            )

    def create_ili2db_transform_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/transforms/ili2db/"), b"")
            archive.writestr(
                self.file_info("plugins/transforms/ili2db/hop-transform-ili2db.jar", 0o644),
                b"ili2db-transform",
            )

    def create_ilivalidator_action_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/actions/ilivalidator/"), b"")
            archive.writestr(
                self.file_info(
                    "plugins/actions/ilivalidator/hop-action-ilivalidator.jar",
                    0o644,
                ),
                b"ilivalidator-action",
            )

    def create_ilivalidator_transform_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(self.dir_info("plugins/transforms/ilivalidator/"), b"")
            archive.writestr(
                self.file_info(
                    "plugins/transforms/ilivalidator/hop-transform-ilivalidator.jar",
                    0o644,
                ),
                b"ilivalidator-transform",
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
