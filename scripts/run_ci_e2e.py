from pathlib import Path
import json
import subprocess
import sys
from build_hop_distribution import digest
metadata=json.loads(Path('dist/release-metadata.json').read_text())
assert len(metadata['artifacts'])==1
artifact=metadata['artifacts'][0]
archive=Path('dist')/artifact['file']
assert digest(archive)==artifact['sha256'], 'Downloaded archive checksum mismatch'
subprocess.run([sys.executable,'scripts/run_e2e.py','--archive',str(archive),'--work-dir','.ci/e2e'],check=True)
