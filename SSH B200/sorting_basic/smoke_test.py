"""Short end-to-end check; never used as the final sorting model."""
import json
from datetime import datetime
from pathlib import Path
import train


def main():
    out = train.ROOT / 'outputs' / ('sorting_smoke_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    settings = dict(train.TRAINING_SETTINGS, steps=10, save_freq=10, eval_steps=10, log_freq=5, output_dir=out)
    train.main(settings=settings, validation_limit=2)
    best = json.loads((out / 'best.json').read_text())
    assert best['step'] == 10
    assert (out / 'checkpoints/best/pretrained_model/model.safetensors').is_file()
    record = {'passed': True, 'output': str(out), 'best': best}
    Path(__file__).with_name('smoke_result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
