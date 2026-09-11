"""Publish verified assets once; never overwrite an existing release."""
import json
import os
from pathlib import Path
import subprocess

from build_hop_distribution import digest


def publish_release(metadata_path=Path("dist/release-metadata.json"), gh_repo=None):
    metadata_path = Path(metadata_path)
    dist_dir = metadata_path.parent
    metadata = json.loads(metadata_path.read_text())
    tag = metadata["release_tag"]
    repo = gh_repo or os.environ["GH_REPO"]

    # Read the list to distinguish a missing tag from an authentication/network failure.
    response = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/releases", "--jq", ".[].tag_name"],
        check=True,
        capture_output=True,
        text=True,
    )
    if tag in response.stdout.splitlines():
        print(f"Release {tag} already exists; leaving all published assets unchanged.")
        return False

    assets = []
    for artifact in metadata["artifacts"]:
        path = dist_dir / artifact["file"]
        if digest(path) != artifact["sha256"]:
            raise SystemExit("Release artifact checksum mismatch")
        assets.extend([str(path), str(path) + ".sha256"])
    assets.append(str(metadata_path))

    version = metadata.get("publication_version", metadata["distribution_version"])
    body = [
        f"Apache Hop {metadata['hop_version']}; distribution {version}.",
        f"Commit: `{metadata['commit_sha']}`",
        "",
        "Verified with Java 21 and 25 on Linux, macOS and Windows.",
        "",
        "Included Maven snapshots:",
    ]
    body.extend(f"- `{p['artifact']}`: `{p['resolved_version']}`" for p in metadata["plugins"])
    notes_path = dist_dir / "release-body.md"
    notes_path.write_text("\n".join(body) + "\n")

    command = [
        "gh",
        "release",
        "create",
        tag,
        "--target",
        metadata["commit_sha"],
        "--title",
        metadata["release_name"],
        "--notes-file",
        str(notes_path),
    ]
    if metadata.get("prerelease", False):
        command.append("--prerelease")
    command.extend(assets)
    subprocess.run(command, check=True)
    return True


if __name__ == "__main__":
    publish_release()
