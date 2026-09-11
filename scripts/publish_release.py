"""Publish the verified assets once; never overwrite an existing release."""
import json
import os
from pathlib import Path
import subprocess
from build_hop_distribution import digest

metadata=json.loads(Path('dist/release-metadata.json').read_text())
tag=metadata['release_tag']
# Read the list to distinguish a missing tag from an authentication/network failure.
response=subprocess.run(['gh','api','--paginate',f'repos/{os.environ["GH_REPO"]}/releases','--jq','.[].tag_name'],check=True,capture_output=True,text=True)
if tag in response.stdout.splitlines():
    print(f'Release {tag} already exists; leaving all published assets unchanged.')
    raise SystemExit(0)
assets=[]
for artifact in metadata['artifacts']:
    path=Path('dist')/artifact['file']
    if digest(path)!=artifact['sha256']:raise SystemExit('Release artifact checksum mismatch')
    assets.extend([str(path),str(path)+'.sha256'])
assets.append('dist/release-metadata.json')
body=[f'Apache Hop {metadata["hop_version"]}; distribution {metadata["distribution_version"]}.',
      f'Commit: `{metadata["commit_sha"]}`', '', 'Verified with Java 21 and 25 on Linux, macOS and Windows.', '', 'Included Maven snapshots:']
body.extend(f'- `{p["artifact"]}`: `{p["resolved_version"]}`' for p in metadata['plugins'])
Path('dist/release-body.md').write_text('\n'.join(body)+'\n')
subprocess.run(['gh','release','create',tag,'--target',metadata['commit_sha'],'--title',metadata['release_name'],'--notes-file','dist/release-body.md',*assets],check=True)
