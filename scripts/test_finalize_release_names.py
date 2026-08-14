from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import finalize_release_names as naming


class FinalizeReleaseNamesTests(unittest.TestCase):
    def test_distribution_id_uses_short_commit_sha(self) -> None:
        self.assertEqual("5957288", naming.distribution_id("595728817ee158f06f54d52675a5600c4ac680e1"))

    def test_distribution_id_uses_manual_without_commit(self) -> None:
        self.assertEqual("manual", naming.distribution_id(None))

    def test_finalize_metadata_renames_assets_and_keeps_plugin_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hop-release-name-test-") as temp_dir_name:
            root = Path(temp_dir_name)
            old_windows = (
                "apache-hop-client-2.18.1-hop-plugins-cb6cef8-5fa3748-0d69c2e-"
                "a49fece-865a676-1dc072a-36c670d-windows-x86_64.zip"
            )
            old_macos = (
                "apache-hop-client-2.18.1-hop-plugins-cb6cef8-5fa3748-0d69c2e-"
                "a49fece-865a676-1dc072a-36c670d-osx-aarch64.zip"
            )
            (root / old_windows).write_bytes(b"windows")
            (root / old_macos).write_bytes(b"macos")

            metadata_path = root / "release-metadata.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "hop_version": "2.18.1",
                        "commit_sha": "595728817ee158f06f54d52675a5600c4ac680e1",
                        "plugin_release_tag": "auto-vsnapshot-20260814-1543-cb6cef8",
                        "geometry_inspector_release_tag": "auto-v0.1.0-SNAPSHOT-20260814-1244-0d69c2e",
                        "artifacts": [
                            {"target": "windows-x86_64", "file": old_windows},
                            {"target": "osx-aarch64", "file": old_macos},
                        ],
                        "release_tag": "old-long-tag",
                        "release_name": "Old very long release name",
                    }
                ),
                encoding="utf-8",
            )

            result = naming.finalize_metadata(
                metadata_path,
                geometry_type_tag="auto-v0.1.0-SNAPSHOT-20260814-1527-60dca6e",
                geometry_type_name="Auto Release 0.1.0-SNAPSHOT",
            )

            self.assertEqual("5957288", result["distribution_id"])
            self.assertEqual("hop-2.18.1-geo-5957288", result["release_tag"])
            self.assertEqual(
                "Apache Hop 2.18.1 + Geo Plugins (5957288)",
                result["release_name"],
            )
            self.assertEqual(
                "auto-vsnapshot-20260814-1543-cb6cef8",
                result["plugin_release_tag"],
            )
            self.assertEqual(
                "auto-v0.1.0-SNAPSHOT-20260814-1527-60dca6e",
                result["geometry_type_release_tag"],
            )

            expected_windows = "apache-hop-client-2.18.1-geo-5957288-windows-x86_64.zip"
            expected_macos = "apache-hop-client-2.18.1-geo-5957288-osx-aarch64.zip"
            self.assertTrue((root / expected_windows).is_file())
            self.assertTrue((root / expected_macos).is_file())
            self.assertFalse((root / old_windows).exists())
            self.assertFalse((root / old_macos).exists())
            self.assertEqual(expected_windows, result["artifacts"][0]["file"])
            self.assertEqual(expected_macos, result["artifacts"][1]["file"])
            self.assertLess(len(expected_windows), 80)


if __name__ == "__main__":
    unittest.main()
