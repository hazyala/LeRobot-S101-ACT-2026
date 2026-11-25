"""Package numeric/meta derivatives only; server reuses original RGB videos."""
from pathlib import Path
import hashlib
import json
import tarfile
ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'robot_datasets/derived/pickplace_nohome_v1'
assert json.loads((base/'validation_report.json').read_text())['passed']
files=[p for p in base.rglob('*') if p.is_file() and 'videos' not in p.relative_to(base).parts and p.name!='payload_manifest.json']
rows=[dict(path=p.relative_to(base).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
(base/'payload_manifest.json').write_text(json.dumps(rows,indent=2))
archive=ROOT/'robot_datasets/derived/pickplace_nohome_v1_payload.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for p in files+[base/'payload_manifest.json']: tar.add(p,arcname=p.relative_to(base).as_posix())
print(archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())
