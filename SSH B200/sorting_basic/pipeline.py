"""Wait for the transfer, verify, smoke-test, then train the sorting-only ACT."""
import fcntl
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path('/NHNHOME/workspace/lerobot')
DATA = BASE / 'datasets/sorting'
STATUS = HERE / 'pipeline_status.json'

def status(stage, **details):
    record = {'stage': stage, 'updated_utc': datetime.now(timezone.utc).isoformat(), **details}
    temporary = STATUS.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    os.replace(temporary, STATUS)
    print(json.dumps(record), flush=True)

def run(script, log):
    with (HERE / log).open('w') as output:
        subprocess.run([sys.executable, '-u', str(HERE / script)], cwd=HERE,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=900)



def main():
    lock = (HERE / 'pipeline.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        manifest_deadline = time.monotonic() + 6 * 3600
        while not (DATA / 'transfer_manifest.json').is_file():
            status('waiting_for_manifest')
            if time.monotonic() > manifest_deadline:
                raise TimeoutError('Local hash manifest was not uploaded within six hours')
            time.sleep(30)
        manifest = json.loads((DATA / 'transfer_manifest.json').read_text())
        assert manifest['total_episodes'] == 150
        started = time.monotonic()
        while True:
            matched = 0
            transferred = 0
            for row in manifest['files']:
                path = DATA / 'dataset' / row['path']
                if path.is_file():
                    size = path.stat().st_size
                    transferred += min(size, row['size'])
                    matched += size == row['size']
            status('waiting_for_transfer', files_ready=matched, total_files=len(manifest['files']),
                   bytes_present=transferred, total_bytes=sum(row['size'] for row in manifest['files']))
            if matched == len(manifest['files']):
                break
            if time.monotonic() - started > 6 * 3600:
                raise TimeoutError('Dataset transfer did not complete within six hours; training was not started')
            time.sleep(30)
        status('verifying_transfer')
        run('verify_transfer.py', 'verify_transfer.log')
        status('smoke_test')
        run('smoke_test.py', 'smoke_test.log')
        result = json.loads((HERE / 'smoke_result.json').read_text())
        assert result['passed']
        import train
        out = BASE / 'outputs' / ('act_sorting_basic_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        settings = dict(train.TRAINING_SETTINGS, output_dir=out)
        status('training', output=str(out), steps=settings['steps'], train_episodes=120, validation_episodes=30)
        # Save the exact output directory before entering the full training loop.
        with (HERE / 'training.log').open('w', buffering=1) as output:
            os.dup2(output.fileno(), 1)
            os.dup2(output.fileno(), 2)
            train.main(settings=settings)
        best = json.loads((out / 'best.json').read_text())
        assert (out / 'checkpoints/best/pretrained_model/model.safetensors').is_file()
        status('completed', output=str(out), best=best)
    except Exception as exc:
        status('failed', error=str(exc), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
