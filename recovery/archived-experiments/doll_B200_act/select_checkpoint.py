"""Compare checkpoints on fixed held-out episodes without connecting hardware.

All 50 checkpoints: two fixed times per validation episode.
Best five candidates: ten fixed times per episode. Selection is an offline
normalized action MAE estimate, not a measured robot success rate.
"""
import os
from pathlib import Path
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
os.environ.setdefault('HF_HOME', str(ROOT / 'hf_pickplace_reference'))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'

import argparse
import copy
import csv
import json
import time
import numpy as np
import torch
from safetensors.torch import load_file
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTConfig, ACTPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--shortlist', type=int, default=5)
    parser.add_argument('--full-comparison', action='store_true', help='Compare every checkpoint on all 500 fixed samples')
    args = parser.parse_args()
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required for this checkpoint comparison.')
    result_root = BASE / 'act_doll_basic'
    out = BASE / 'selection'
    out.mkdir(exist_ok=True)
    split = json.loads((result_root / 'split.json').read_text())
    episodes = split['validation']
    assert len(episodes) == 50 and not set(episodes) & set(split['train'])
    folders = sorted(p for p in (result_root / 'checkpoints').iterdir() if p.is_dir() and p.name.isdigit())
    config = ACTConfig.from_pretrained(folders[-1] / 'pretrained_model')
    config.device = 'cuda'
    config.pretrained_backbone_weights = None
    dataset = LeRobotDataset('local/doll', root=ROOT / 'robot_datasets/tasks/pick_doll/dataset', episodes=episodes,
                             video_backend='pyav', return_uint8=True,
                             delta_timestamps={'action': [i / 30 for i in range(config.chunk_size)]})
    # Remove only the in-memory depth feature so no depth frames are decoded.
    for key in list(dataset.meta.depth_keys):
        dataset.meta.features.pop(key)
    policy = ACTPolicy(config).to('cuda').eval()
    preprocess, _ = make_pre_post_processors(config, pretrained_path=str(folders[-1] / 'pretrained_model'))
    camera_keys = ['observation.images.top', 'observation.images.side']
    samples, broad, screen = [], [], []
    started = time.perf_counter()
    for n, ep in enumerate(episodes):
        row = dataset.meta.episodes[ep]
        start, end = int(row['dataset_from_index']), int(row['dataset_to_index'])
        offsets = sorted(set(np.linspace(0, end-start-1, 10).astype(int).tolist()))
        for j, offset in enumerate(offsets):
            raw = dataset[dataset.absolute_to_relative_idx[start+offset]]
            sample = {key: raw[key].clone() for key in camera_keys + ['observation.state', 'action', 'action_is_pad']}
            samples.append(sample)
            broad.append((ep, start+offset, len(samples)-1))
            if j in (0, len(offsets)-1):
                screen.append((ep, start+offset, len(samples)-1))
        if (n+1) % 5 == 0:
            print(f'Cached validation episodes {n+1}/50 ({time.perf_counter()-started:.1f}s)', flush=True)
    anchors = {'screen': [[ep, idx] for ep, idx, _ in screen], 'final': [[ep, idx] for ep, idx, _ in broad]}
    (out / 'anchors.json').write_text(json.dumps(anchors, indent=2))

    def score(folder, anchors):
        state = load_file(str(folder / 'pretrained_model/model.safetensors'), device='cpu')
        policy.load_state_dict(state, strict=True)
        del state
        policy.eval()
        totals = {ep: [0., 0] for ep in episodes}
        with torch.inference_mode():
            for first in range(0, len(anchors), args.batch_size):
                part = anchors[first:first+args.batch_size]
                batch = {key: torch.stack([samples[i][key] for _, _, i in part]) for key in samples[0]}
                for key in camera_keys:
                    batch[key] = batch[key].float() / 255.
                batch = preprocess(batch)
                target, mask = batch['action'], ~batch['action_is_pad'].bool()
                inputs = {key: batch[key] for key in config.input_features}
                pred = policy.predict_action_chunk(inputs)
                if not torch.isfinite(pred).all():
                    return float('inf')
                errors = (pred-target).abs().mean(-1)
                sums = (errors*mask).sum(-1).cpu().tolist()
                counts = mask.sum(-1).cpu().tolist()
                for (ep, _, _), error, count in zip(part, sums, counts):
                    totals[ep][0] += error
                    totals[ep][1] += count
        return float(np.mean([total/count for total, count in totals.values()]))

    records = []
    for folder in folders:
        value = score(folder, broad if args.full_comparison else screen)
        records.append({'checkpoint': folder.name, 'screen_mae': value,
                        'final_mae': value if args.full_comparison else None})
        print(f'Screen {folder.name}: normalized MAE={value:.6f}', flush=True)
        (out / 'progress.json').write_text(json.dumps(records, indent=2))
    candidates = records if args.full_comparison else sorted(records, key=lambda r: r['screen_mae'])[:args.shortlist]
    for record in ([] if args.full_comparison else candidates):
        value = score(result_root / 'checkpoints' / record['checkpoint'], broad)
        record['final_mae'] = value
        print(f'Final {record["checkpoint"]}: normalized MAE={value:.6f}', flush=True)
    winner = min(candidates, key=lambda r: r['final_mae'])
    if not np.isfinite(winner['final_mae']):
        raise RuntimeError('No finite candidate.')
    with (out / 'scores.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['checkpoint', 'screen_mae', 'final_mae'])
        writer.writeheader(); writer.writerows(records)
    selection = {'checkpoint': winner['checkpoint'],
                 'model_dir': str(result_root / 'checkpoints' / winner['checkpoint'] / 'pretrained_model'),
                 'normalized_action_mae': winner['final_mae'],
                 'criterion': 'equal-episode normalized L1 over valid 100-action chunks, z=0',
                 'screen_samples': len(broad) if args.full_comparison else len(screen), 'final_samples': len(broad),
                 'checkpoints_screened': len(folders), 'finalists': len(candidates),
                 'robot_success_rate_measured': False}
    (out / 'selected_checkpoint.json').write_text(json.dumps(selection, indent=2))
    print('SELECTED:', json.dumps(selection), flush=True)


if __name__ == '__main__':
    main()
