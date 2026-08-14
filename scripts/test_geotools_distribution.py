from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


def load_module():
    module_path = Path(__file__).with_name("build_hop_distribution.py")
    spec = importlib.util.spec_from_file_location("build_hop_distribution_geotools_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_module()


class GeoToolsDistributionTests(unittest.TestCase):
    def test_cli_defaults_to_latest_geotools_release(self) -> None:
        args = builder.parse_args(["--hop-version", "2.18.1", "--output-dir", "dist"])
        self.assertEqual("latest", args.geotools_release)

    def test_selects_single_geotools_release_zip(self) -> None:
        release_payload = {
            "tag_name": "auto-v0.1.0-SNAPSHOT-20260814-1200-abcdef0",
            "assets": [
                {
                    "name": "hop-geotools-plugin-0.1.0-SNAPSHOT.zip",
                    "browser_download_url": "https://example.test/hop-geotools-plugin.zip",
                },
                {
                    "name": "notes.txt",
                    "browser_download_url": "https://example.test/notes.txt",
                },
            ],
        }

        asset = builder.select_single_zip_asset(
            release_payload,
            asset_prefix=builder.GEOTOOLS_ASSET_PREFIX,
            repo_name=builder.GEOTOOLS_PLUGIN_REPO,
        )

        self.assertEqual("hop-geotools-plugin-0.1.0-SNAPSHOT.zip", asset.name)
        self.assertEqual("generic", asset.target)

    def test_merge_places_geotools_vector_plugin_in_hop_distribution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-geotools-dist-test-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            hop_zip = temp_dir / "hop.zip"
            geotools_zip = temp_dir / "geotools.zip"
            output_zip = temp_dir / "output.zip"

            with zipfile.ZipFile(hop_zip, "w") as archive:
                archive.writestr("hop/", b"")
                archive.writestr("hop/lib/", b"")
                archive.writestr("hop/lib/core.jar", b"core")

            with zipfile.ZipFile(geotools_zip, "w") as archive:
                archive.writestr("plugins/transforms/geotools-vector/", b"")
                archive.writestr(
                    "plugins/transforms/geotools-vector/hop-geotools-vector-0.1.0-SNAPSHOT.jar",
                    b"plugin",
                )
                archive.writestr(
                    "plugins/transforms/geotools-vector/lib/gt-main-35.0.jar",
                    b"geotools",
                )

            builder.build_distribution_archive(
                hop_zip_path=hop_zip,
                plugin_archives=[
                    builder.PluginArchive(
                        path=geotools_zip,
                        required_prefix=builder.GEOTOOLS_PLUGIN_PREFIX,
                    )
                ],
                output_path=output_zip,
            )

            with zipfile.ZipFile(output_zip) as archive:
                names = archive.namelist()
                self.assertIn(
                    "hop/plugins/transforms/geotools-vector/hop-geotools-vector-0.1.0-SNAPSHOT.jar",
                    names,
                )
                self.assertIn(
                    "hop/plugins/transforms/geotools-vector/lib/gt-main-35.0.jar",
                    names,
                )
                self.assertFalse(
                    any(
                        name.startswith("hop/plugins/transforms/geotools-vector/")
                        and "jts-core-" in name
                        for name in names
                    )
                )


if __name__ == "__main__":
    unittest.main()
