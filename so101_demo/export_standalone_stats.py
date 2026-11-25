"""Offline export of checkpoint normalization for the standalone runtime.

Requires safetensors during export only; standalone inference does not use
LeRobot, PyTorch, or safetensors.
"""
import hashlib
import argparse
import json
from pathlib import Path
from safetensors.torch import load_file

ROOT = Path('/NHNHOME/workspace/lerobot/so101-demo')
MODELS = {
    'doll': ROOT / 'models/doll',
    'cup': Path('/NHNHOME/workspace/lerobot/outputs/act_paper_cup_basic_20261021_224407_822254/checkpoints/044000/pretrained_model'),
}
FEATURES = ('observation.state', 'observation.images.top', 'observation.images.side')
NAMES = ['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos',
         'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos']

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument('--rewritten', action='store_true')
args = parser.parse_args()

for name, path in MODELS.items():
    pre_path = path / 'policy_preprocessor_step_3_normalizer_processor.safetensors'
    post_path = path / 'policy_postprocessor_step_0_unnormalizer_processor.safetensors'
    pre = load_file(str(pre_path))
    post = load_file(str(post_path))
    data = {'model': name, 'joint_names': NAMES, 'eps': 1e-8,
            'weight_sha256': digest(path/'model.safetensors'),
            'onnx_sha256': digest(ROOT/'onnx_candidate'/(name+('_rewritten' if args.rewritten else '')+'.onnx')),
            'preprocessor_sha256': digest(pre_path), 'postprocessor_sha256': digest(post_path),
            'input': {key: {s: pre[key+'.'+s].flatten().tolist() for s in ('mean','std')} for key in FEATURES},
            'action': {s: post['action.'+s].flatten().tolist() for s in ('mean','std')},
            'action_min': pre['action.min'].flatten().tolist(),
            'action_max': pre['action.max'].flatten().tolist()}
    destination = ROOT/'onnx_candidate'/name/('rewritten_stats.json' if args.rewritten else 'stats.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    print('wrote', destination)
