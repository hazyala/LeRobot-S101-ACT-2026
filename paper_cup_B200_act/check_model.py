"""Hardware-free reload and held-out observation test for the downloaded cup model."""
import json
from pathlib import Path
import time
import run


def main():
    run.main(preflight_only=True)
    import numpy as np
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.act import ACTConfig, ACTPolicy

    base = Path(__file__).resolve().parent
    split = json.loads((base / 'split.json').read_text())
    assert len(split['train']) == 200 and len(split['validation']) == 50
    assert not set(split['train']) & set(split['validation'])
    held_out = split['validation']
    episodes = [held_out[i] for i in np.linspace(0, len(held_out)-1, 10).astype(int)]
    best = json.loads((base / 'best.json').read_text())
    model = base / 'checkpoints' / f"{best['step']:06d}" / 'pretrained_model'
    config = ACTConfig.from_pretrained(model)
    config.device = 'cuda'
    config.pretrained_backbone_weights = None
    policy = ACTPolicy.from_pretrained(model, config=config, strict=True).to('cuda').eval()
    assert all(torch.isfinite(p).all().item() for p in policy.parameters())
    preprocess, postprocess = make_pre_post_processors(config, pretrained_path=str(model))
    dataset = LeRobotDataset('local/paper_cup', root=run.ROOT/'robot_datasets/tasks/pick_paper_cup/dataset',
                            episodes=episodes, video_backend='pyav', return_uint8=True,
                            delta_timestamps={'action': [i/30 for i in range(config.chunk_size)]})
    for key in list(dataset.meta.depth_keys):
        dataset.meta.features.pop(key)
    cameras = list(config.image_features)
    scores, timings, anchors = [], [], []
    stats = json.loads((base/'train_stats.json').read_text())
    std = torch.tensor(stats['action']['std'],device='cuda')
    total_errors = torch.zeros(6,device='cuda')
    total_count = 0
    with torch.inference_mode():
        for ep in episodes:
            row = dataset.meta.episodes[ep]
            start, end = int(row['dataset_from_index']), int(row['dataset_to_index'])
            episode_error, episode_count = 0.0, 0
            for offset in np.linspace(0, end-start-1, 3).astype(int):
                absolute = start + int(offset)
                raw = dataset[dataset.absolute_to_relative_idx[absolute]]
                batch = {key: raw[key].unsqueeze(0) for key in cameras + ['observation.state', 'action', 'action_is_pad']}
                for key in cameras:
                    batch[key] = batch[key].float()/255.0
                batch = preprocess(batch)
                target = batch['action']
                mask = ~batch['action_is_pad'].bool()
                torch.cuda.synchronize()
                t = time.perf_counter()
                pred = policy.predict_action_chunk({key: batch[key] for key in config.input_features})
                torch.cuda.synchronize()
                timings.append((time.perf_counter()-t)*1000)
                assert pred.shape == (1,100,6) and torch.isfinite(pred).all()
                actions = postprocess(pred.clone())
                assert torch.isfinite(actions).all()
                error = (pred-target).abs()
                count = int(mask.sum().item())
                episode_error += float((error.mean(-1)*mask).sum().item())
                episode_count += count
                total_errors += (error*std*mask.unsqueeze(-1)).sum((0,1))
                total_count += count
                anchors.append({'episode':ep,'absolute_frame':absolute,'valid_actions':count})
            scores.append(episode_error/episode_count)
            print('Held-out episode checked:', ep, flush=True)
    report = {'checkpoint':best['step'],'source_validation_loss':best['eval_loss'],
              'weights_finite':True,'reload_strict':True,'hardware_connected':False,
              'held_out_episodes':episodes,'observations':len(anchors),
              'normalized_mae_equal_episode':float(np.mean(scores)),
              'joint_mae_original_units':(total_errors/total_count).cpu().tolist(),
              'joint_order':dataset.meta.features['action']['names'],
              'median_inference_ms_excluding_first':float(np.median(timings[1:])),
              'anchors':anchors,'robot_success_rate_measured':False,
              'note':'30 fixed held-out observations; not the full validation score or a grasp-success test.'}
    (base/'model_check_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='anchors'},indent=2),flush=True)


if __name__ == '__main__':
    main()
