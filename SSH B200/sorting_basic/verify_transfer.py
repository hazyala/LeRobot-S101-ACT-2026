"""Verify every transferred dataset file before allowing training."""
import hashlib
import json
import os
from pathlib import Path

BASE = Path('/NHNHOME/workspace/lerobot/datasets/sorting')
root = BASE / 'dataset'
manifest_path = BASE / 'transfer_manifest.json'
manifest = json.loads(manifest_path.read_text())
ready = BASE / 'TRANSFER_VERIFIED.json'
ready.unlink(missing_ok=True)
assert manifest['total_episodes'] == 150
expected = {row['path'] for row in manifest['files']}
actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual == expected, {'missing': sorted(expected-actual), 'extra': sorted(actual-expected)}
for index, row in enumerate(manifest['files'], 1):
    path = (root / row['path']).resolve()
    assert path.is_relative_to(root.resolve())
    assert path.stat().st_size == row['size'], str(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    assert digest.hexdigest() == row['sha256'], str(path)
    if index % 25 == 0:
        print(f'Verified {index}/{len(expected)} files', flush=True)
info = json.loads((root / 'meta/info.json').read_text())
assert info['total_episodes'] == 150
assert info['total_frames'] == manifest['total_frames']
record = dict(verified=True, dataset=str(root), total_episodes=150,
              total_frames=info['total_frames'], files=len(expected),
              bytes=sum(row['size'] for row in manifest['files']),
              manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
temporary = ready.with_suffix('.json.tmp')
temporary.write_text(json.dumps(record, indent=2) + '\n')
os.replace(temporary, ready)
print(json.dumps(record), flush=True)
