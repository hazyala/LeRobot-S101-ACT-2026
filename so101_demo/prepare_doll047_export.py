"""Create isolated export scripts for the recorded 047000 doll checkpoint."""
from pathlib import Path

base = Path('/NHNHOME/workspace/lerobot/so101-demo')
dest = base / 'doll047'
dest.mkdir(exist_ok=True)
model = '/NHNHOME/workspace/lerobot/outputs/act_doll_basic/checkpoints/047000/pretrained_model'
old_model = '/NHNHOME/workspace/lerobot/so101-demo/models/doll'
for name in ('export_tensorrt_candidate.py', 'export_standalone_stats.py', 'compare_standalone.py'):
    source = (base / name).read_text()
    source = source.replace(old_model, model)
    if name == 'export_standalone_stats.py':
        source = source.replace("ROOT / 'models/doll'", "Path('{}')".format(model))
        source = source.replace("ROOT = Path('/NHNHOME/workspace/lerobot/so101-demo')", "ROOT = Path('{}')".format(dest))
        source = '\n'.join(line for line in source.split('\n') if not line.strip().startswith("'cup':"))
    if name == 'compare_standalone.py':
        source = source.replace("ROOT = '/NHNHOME/workspace/lerobot/so101-demo/onnx_candidate'", "ROOT = '{}/onnx_candidate'".format(dest))
    (dest / name).write_text(source)
print('isolated scripts:', dest)
