"""Compare standalone ONNX CPU inference with the original LeRobot policy.

Requires LeRobot/PyTorch ONLY for the reference side of this offline test.
Synthetic observations are not robot success-rate tests.
"""
import argparse
import contextlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTConfig, ACTPolicy
from standalone_act import OnnxBackend, load_stats, prepare, postprocess

MODEL_DIRS = {
    'doll': '/NHNHOME/workspace/lerobot/so101-demo/models/doll',
    'cup': '/NHNHOME/workspace/lerobot/outputs/act_paper_cup_basic_20261021_224407_822254/checkpoints/044000/pretrained_model',
}
ROOT = '/NHNHOME/workspace/lerobot/so101-demo/onnx_candidate'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('model', choices=('doll','cup'))
    ap.add_argument('--real-data', action='store_true')
    ap.add_argument('--fixture-output', help='optional offline comparison fixture (.npz)')
    ap.add_argument('--onnx-file', help='override ONNX file for graph-equivalence verification')
    ap.add_argument('--cases', type=int, default=2)
    ap.add_argument('--fixtures-dir', help='optional directory for offline input/reference files')
    args = ap.parse_args()
    if not 1 <= args.cases <= 20: raise ValueError('cases must be 1..20')
    name = args.model
    path = MODEL_DIRS[name]
    stats = load_stats('{}/{}/stats.json'.format(ROOT, name))
    config = ACTConfig.from_pretrained(path)
    config.device = 'cuda'
    config.pretrained_backbone_weights = None
    policy = ACTPolicy.from_pretrained(path, config=config, strict=True).cuda().eval()
    torch.set_num_threads(4)
    pre, post = make_pre_post_processors(config, pretrained_path=path)
    ort = OnnxBackend(args.onnx_file or '{}/{}.onnx'.format(ROOT, name))
    rng = np.random.default_rng(2026)
    reports = []
    dataset = None
    if args.real_data:
        from lerobot.datasets import LeRobotDataset
        dataset = LeRobotDataset('local/' + name,
            root='/NHNHOME/workspace/lerobot/datasets/{}/dataset'.format('paper_cup' if name == 'cup' else 'doll'),
            episodes=[0], video_backend='pyav', return_uint8=True)
    if args.fixtures_dir: Path(args.fixtures_dir).mkdir(parents=True, exist_ok=True)
    for idx in range(args.cases):
        if dataset is None:
            state = (np.array([-5, -85, 90, 60, -2, 10], dtype=np.float32) + idx)
            top = rng.integers(0, 256, size=(480,640,3), dtype=np.uint8)
            side = rng.integers(0, 256, size=(480,640,3), dtype=np.uint8)
        else:
            sample = dataset[min(idx * 50, len(dataset)-1)]
            state = sample['observation.state'].numpy().astype(np.float32)
            top = np.ascontiguousarray(sample['observation.images.top'].numpy().transpose(1,2,0)[:,:,::-1])
            side = np.ascontiguousarray(sample['observation.images.side'].numpy().transpose(1,2,0)[:,:,::-1])
        independent = prepare(state, top, side, stats)
        def image(x):
            return torch.from_numpy(x[:,:,::-1].copy()).permute(2,0,1).float()/255.0
        frame = {'observation.state':torch.from_numpy(state),
                 'observation.images.top':image(top), 'observation.images.side':image(side)}
        batch = pre(frame)
        for short, key in [('state','observation.state'),('top','observation.images.top'),('side','observation.images.side')]:
            diff = np.max(np.abs(independent[short] - batch[key].cpu().numpy()))
            if diff > 1e-5: raise AssertionError('input preprocessing mismatch {}: {}'.format(short,diff))
        with torch.inference_mode():
            original_raw = policy.predict_action_chunk(batch)
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                original_fp16 = policy.predict_action_chunk(batch)
        original = post(original_raw)[0].cpu().numpy()
        original_amp = post(original_fp16)[0].cpu().numpy()
        cpu_batch = {key: torch.from_numpy(independent[short]) for short,key in
                     [('state','observation.state'),('top','observation.images.top'),('side','observation.images.side')]}
        policy.cpu()
        with torch.inference_mode():
            torch_cpu_raw = policy.predict_action_chunk(cpu_batch).numpy()
        cpu_original = postprocess(torch_cpu_raw, stats)
        policy.cuda()
        started = time.perf_counter()
        independent_raw = ort.run(independent)
        onnx_s = time.perf_counter()-started
        result = postprocess(independent_raw, stats)
        if args.fixture_output and idx == 0:
            np.savez_compressed(args.fixture_output, state=state, top_bgr=top, side_bgr=side,
                                reference_cpu=cpu_original, reference_gpu_fp32=original,
                                reference_gpu_fp16=original_amp)
        if args.fixtures_dir:
            np.savez_compressed(str(Path(args.fixtures_dir)/('case-{:03d}.npz'.format(idx))),
                                state=state, top_bgr=top, side_bgr=side,
                                reference_cpu=cpu_original, reference_gpu_fp32=original,
                                reference_gpu_fp16=original_amp)
        delta = np.abs(cpu_original-result)
        reports.append({'case':idx,'cpu_reference_max_abs':float(delta.max()),
                        'cpu_reference_mean_abs':float(delta.mean()),
                        'gpu_fp32_reference_max_abs':float(np.abs(original-result).max()),
                        'gpu_fp16_reference_max_abs':float(np.abs(original_amp-result).max()),
                        'onnx_cpu_s':round(onnx_s,3)})
        print(json.dumps({'model':name, 'case_result':reports[-1]}), flush=True)
        if not np.isfinite(delta).all() or delta.max() > 0.02:
            raise AssertionError('ONNX output differs from original model')
    print(json.dumps({'model':name, 'source':'dataset' if dataset is not None else 'synthetic',
                      'cases':reports, 'comparison':'passed'}, allow_nan=False), flush=True)
    ort.close()

if __name__ == '__main__': main()
