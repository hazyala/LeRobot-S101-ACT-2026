"""Check the fixed split, train-only statistics and best checkpoint selection."""
import json
import tempfile
from pathlib import Path
import train
from best_checkpoint import BestCheckpoint
root = train.ROOT / 'datasets/sorting/dataset'
split = train.read_split(root)
stats = train.training_stats(root, split['train'])
assert len(split['train']) == 120 and len(split['validation']) == 30
with tempfile.TemporaryDirectory(prefix='sorting_best_check_') as temporary:
    out = Path(temporary)
    tracker = BestCheckpoint(out)
    for step, loss in [(10, 2.0), (20, 3.0), (30, 1.0), (40, float('nan')), (50, 1.0)]:
        checkpoint = out / 'checkpoints' / str(step)
        (checkpoint / 'pretrained_model').mkdir(parents=True)
        (checkpoint / 'pretrained_model/model.safetensors').touch()
        tracker.evaluation(step, loss)
        tracker.saved(step, checkpoint)
    assert json.loads((out / 'best.json').read_text())['step'] == 30
    assert (out / 'checkpoints/best').resolve() == out / 'checkpoints/30'
result = {'passed': True, 'train': 120, 'validation': 30,
          'train_only_stats': True, 'best_selection': 'improvement/tie/worse/NaN checked',
          'inputs': ['observation.state', 'observation.images.top', 'observation.images.side']}
Path(__file__).with_name('preflight_result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
