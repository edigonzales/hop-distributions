import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from check_geotools_versions import geotools_artifacts, verify_archive


def _jar(group_id: str, artifact_id: str, version: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as jar:
        jar.writestr(
            f"META-INF/maven/{group_id}/{artifact_id}/pom.properties",
            f"groupId={group_id}\nartifactId={artifact_id}\nversion={version}\n",
        )
    return buffer.getvalue()


def _distribution(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in entries:
            archive.writestr(member, content)


class GeoToolsVersionGuardTest(unittest.TestCase):
    def test_accepts_same_geotools_version_from_multiple_plugins(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "hop.zip"
            _distribution(
                archive,
                [
                    (
                        "hop/plugins/misc/hop-geometry-inspector/lib/gt-main.jar",
                        _jar("org.geotools", "gt-main", "35.0"),
                    ),
                    (
                        "hop/plugins/transforms/geotools-vector/lib/gt-main-35.0.jar",
                        _jar("org.geotools", "gt-main", "35.0"),
                    ),
                    (
                        "hop/plugins/transforms/geotools-vector/lib/gt-referencing-35.0.jar",
                        _jar("org.geotools", "gt-referencing", "35.0"),
                    ),
                ],
            )

            self.assertEqual("35.0", verify_archive(archive, "35.0"))
            self.assertEqual(3, len(geotools_artifacts(archive)))

    def test_rejects_mixed_inspector_and_vector_geotools_versions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "hop.zip"
            _distribution(
                archive,
                [
                    (
                        "hop/plugins/misc/hop-geometry-inspector/lib/gt-main.jar",
                        _jar("org.geotools", "gt-main", "31.3"),
                    ),
                    (
                        "hop/plugins/transforms/geotools-vector/lib/gt-main-35.0.jar",
                        _jar("org.geotools", "gt-main", "35.0"),
                    ),
                ],
            )

            with self.assertRaisesRegex(RuntimeError, r"Mixed GeoTools versions.*31\.3, 35\.0"):
                verify_archive(archive)

    def test_rejects_unexpected_single_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "hop.zip"
            _distribution(
                archive,
                [
                    (
                        "hop/plugins/misc/hop-geometry-inspector/lib/gt-main.jar",
                        _jar("org.geotools", "gt-main", "34.0"),
                    )
                ],
            )

            with self.assertRaisesRegex(RuntimeError, r"Unexpected GeoTools version.*34\.0.*35\.0"):
                verify_archive(archive, "35.0")

    def test_ignores_non_geotools_maven_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "hop.zip"
            _distribution(
                archive,
                [
                    (
                        "hop/plugins/misc/hop-geometry-inspector/lib/gt-main.jar",
                        _jar("org.geotools", "gt-main", "35.0"),
                    ),
                    (
                        "hop/plugins/misc/hop-geometry-inspector/lib/something.jar",
                        _jar("example", "something", "99"),
                    ),
                ],
            )

            artifacts = geotools_artifacts(archive)
            self.assertEqual(["35.0"], [artifact.version for artifact in artifacts])


if __name__ == "__main__":
    unittest.main()
