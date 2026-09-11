import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import publish_release as publisher


class PublisherTests(unittest.TestCase):
    def metadata(self, root, version, prerelease):
        archive = root / "distribution.zip"
        archive.write_bytes(b"distribution")
        checksum = publisher.digest(archive)
        (root / "distribution.zip.sha256").write_text(f"{checksum}  distribution.zip\n")
        metadata = {
            "schema_version": 2,
            "distribution_version": version,
            "publication_version": version,
            "prerelease": prerelease,
            "hop_version": "2.19.0",
            "commit_sha": "abc123",
            "release_tag": f"v{version}",
            "release_name": f"Hop Geo Distribution {version}",
            "plugins": [{"artifact": "geometry", "resolved_version": "0.2.1-20260911.100000-1"}],
            "artifacts": [{"file": archive.name, "sha256": checksum}],
        }
        metadata_path = root / "release-metadata.json"
        metadata_path.write_text(json.dumps(metadata))
        return metadata_path, metadata

    def fake_gh(self, calls, existing_tags=""):
        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:2] == ["api"]:
                return subprocess.CompletedProcess(command, 0, stdout=existing_tags, stderr="")
            return subprocess.CompletedProcess(command, 0)

        return run

    def test_creates_snapshot_as_prerelease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path, metadata = self.metadata(
                root, "0.2.1-SNAPSHOT.build.123.1", prerelease=True
            )
            calls = []
            with patch.object(publisher.subprocess, "run", side_effect=self.fake_gh(calls)):
                self.assertTrue(publisher.publish_release(metadata_path, "owner/repo"))

            create = calls[1][0]
            self.assertEqual(create[:3], ["gh", "release", "create"])
            self.assertEqual(create[3], metadata["release_tag"])
            self.assertIn("--prerelease", create)
            self.assertIn(metadata["publication_version"], (root / "release-body.md").read_text())

    def test_existing_tag_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path, metadata = self.metadata(root, "0.2.1-SNAPSHOT.build.123.1", prerelease=True)
            calls = []
            with patch.object(
                publisher.subprocess,
                "run",
                side_effect=self.fake_gh(calls, metadata["release_tag"] + "\n"),
            ):
                self.assertFalse(publisher.publish_release(metadata_path, "owner/repo"))
            self.assertEqual(len(calls), 1)

    def test_stable_release_is_not_prerelease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path, metadata = self.metadata(root, "0.2.1", prerelease=False)
            calls = []
            with patch.object(publisher.subprocess, "run", side_effect=self.fake_gh(calls)):
                self.assertTrue(publisher.publish_release(metadata_path, "owner/repo"))
            create = calls[1][0]
            self.assertEqual(create[3], metadata["release_tag"])
            self.assertNotIn("--prerelease", create)


if __name__ == "__main__":
    unittest.main()
