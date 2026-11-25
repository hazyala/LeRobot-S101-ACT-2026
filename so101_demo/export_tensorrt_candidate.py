"""Export the existing ACT network for TensorRT feasibility testing only.

Inputs are already normalized tensors; output is the normalized action chunk.
This is not a complete or verified robot policy runtime.
"""
import argparse
import contextlib
import json
from pathlib import Path
import torch
from lerobot.policies.act import ACTConfig, ACTPolicy

MODELS = {
    'doll': '/NHNHOME/workspace/lerobot/so101-demo/models/doll',
    'cup': '/NHNHOME/workspace/lerobot/outputs/act_paper_cup_basic_20261021_224407_822254/checkpoints/044000/pretrained_model',
}

class ACTWrapper(torch.nn.Module):
    def __init__(self, policy):
        super().__init__()
        self.policy = policy
    def forward(self, state, top, side):
        return self.policy.predict_action_chunk({'observation.state': state,
            'observation.images.top': top, 'observation.images.side': side})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('model', choices=tuple(MODELS))
    ap.add_argument('output')
    args = ap.parse_args()
    path = MODELS[args.model]
    config = ACTConfig.from_pretrained(path)
    config.device = 'cpu'
    config.pretrained_backbone_weights = None
    model = ACTPolicy.from_pretrained(path, config=config, strict=True).cpu().eval()
    wrapper = ACTWrapper(model).eval()
    inputs = (torch.zeros(1, 6), torch.zeros(1, 3, 480, 640), torch.zeros(1, 3, 480, 640))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        expected = wrapper(*inputs)
        if expected.shape != (1, 100, 6) or not torch.isfinite(expected).all():
            raise RuntimeError('unexpected output')
        torch.onnx.export(wrapper, inputs, str(out), input_names=['state','top','side'],
                          output_names=['action'], opset_version=13, dynamo=False)
    import onnx
    graph = onnx.load(str(out))
    onnx.checker.check_model(graph)
    print(json.dumps({'model': args.model, 'output': str(out), 'bytes': out.stat().st_size,
                      'onnx_check': 'passed', 'shape': list(expected.shape)}))

if __name__ == '__main__': main()
