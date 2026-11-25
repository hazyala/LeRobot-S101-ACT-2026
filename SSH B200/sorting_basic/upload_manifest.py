"""Upload the full local SHA-256 manifest once local hashing completes."""
import json
import subprocess
import time
from pathlib import Path
here = Path(__file__).resolve().parent
manifest = here / 'transfer_manifest.json'
deadline = time.monotonic() + 6 * 3600
while True:
    try:
        record = json.loads(manifest.read_text())
        if record['total_episodes'] == 150 and len(record['files']) == 753:
            break
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if time.monotonic() > deadline:
        raise TimeoutError('Local dataset SHA-256 hashing did not finish')
    time.sleep(5)
subprocess.run(['scp', '-o', 'BatchMode=yes', str(manifest),
                '59.150.33.1:/NHNHOME/workspace/lerobot/datasets/sorting/transfer_manifest.json'], check=True)
print('MANIFEST_UPLOADED', flush=True)
