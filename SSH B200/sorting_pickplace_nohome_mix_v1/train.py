"""ACT mixed training: sorting 4 / no-HOME doll 2 / no-HOME cup 2 per batch."""
import copy
import importlib
import json
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import ConcatDataset
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.compute_stats import aggregate_stats
from lerobot.configs.default import DatasetConfig, WandBConfig
from lerobot.configs.train import TrainPipelineConfig
from lerobot.configs import FeatureType, PolicyFeature
from lerobot.policies.act import ACTConfig
from baseline_reference import training_stats
from best_checkpoint import train_with_best

BASE = Path('/NHNHOME/workspace/lerobot')
HERE = Path(__file__).resolve().parent
DATA = BASE / 'datasets/pickplace_nohome_v1'
KEYS = ['action', 'action_is_pad', 'observation.state', 'observation.images.top', 'observation.images.side']
TRAINING_SETTINGS = dict(steps=50000, batch_size=8, num_workers=4, save_freq=2000, eval_steps=2000, log_freq=100)
ACTIVE_LENGTHS = None

class MixedDataset(ConcatDataset):
    def __init__(self, datasets, stats):
        super().__init__(datasets)
        self.meta = copy.deepcopy(datasets[0].meta)
        self.meta.stats = {k: {s: torch.as_tensor(v.copy()) for s,v in values.items()} for k,values in stats.items()}
        self.num_frames = len(self)
        self.num_episodes = sum(d.num_episodes for d in datasets)
        self.episodes = None
        self.absolute_to_relative_idx = None
    def __getitem__(self, index):
        sample = super().__getitem__(index)
        return {key: sample[key] for key in KEYS}

class BalancedSampler:
    """Deterministic with-replacement draws, exactly 4/2/2 in each batch of eight."""
    def __init__(self, *args, seed=0, **kwargs):
        self.lengths = list(ACTIVE_LENGTHS)
        assert len(self.lengths) == 3 and min(self.lengths) > 0
        self.seed, self.epoch, self.start = seed, 0, 0
        self.count = ((sum(self.lengths) + 7) // 8) * 8
    def __len__(self): return self.count
    def set_epoch(self, epoch): self.epoch = epoch
    def state_dict(self): return {'epoch':self.epoch, 'start_index':self.start}
    def load_state_dict(self, state): self.epoch, self.start = state['epoch'], state['start_index']
    def __iter__(self):
        generator = torch.Generator().manual_seed(int(np.random.SeedSequence([self.seed,self.epoch]).generate_state(1)[0]))
        self.epoch += 1
        start, self.start = self.start, 0
        blocks = self.count // 8
        values = torch.empty((blocks,8), dtype=torch.int64)
        offset = 0
        for group, columns in enumerate([(0,4),(4,6),(6,8)]):
            a,b = columns
            values[:,a:b] = torch.randint(self.lengths[group], (blocks,b-a), generator=generator) + offset
            offset += self.lengths[group]
        return iter(values.reshape(-1)[start:].tolist())

def make_datasets(cfg, validation_limit=None):
    global ACTIVE_LENGTHS
    roots = [BASE/'datasets/sorting/dataset', DATA/'doll/dataset', DATA/'cup/dataset']
    splits = [json.loads((HERE/'sorting_split.json').read_text()),
              json.loads((DATA/'doll/split.json').read_text()), json.loads((DATA/'cup/split.json').read_text())]
    stats = aggregate_stats([training_stats(root,split['train']) for root,split in zip(roots,splits)])
    stats = {k:v for k,v in stats.items() if k in KEYS}
    datasets = []
    for root,split in zip(roots,splits):
        assert not set(split['train']) & set(split['validation'])
        d = LeRobotDataset('local/'+root.parent.name, root=root, episodes=split['train'],
               delta_timestamps={'action':[i/30 for i in range(100)]}, video_backend='torchcodec')
        for key in list(d.meta.depth_keys):
            d.meta.features.pop(key,None)
            if d.reader.delta_indices is not None: d.reader.delta_indices.pop(key,None)
            if d.delta_timestamps is not None: d.delta_timestamps.pop(key,None)
        datasets.append(d)
    ACTIVE_LENGTHS = [len(d) for d in datasets]
    training = MixedDataset(datasets,stats)
    ids = splits[0]['validation']
    if validation_limit: ids = ids[:validation_limit]
    val = LeRobotDataset('local/sorting', root=roots[0], episodes=ids,
              delta_timestamps={'action':[i/30 for i in range(100)]}, video_backend='torchcodec')
    for key in list(val.meta.depth_keys):
        val.meta.features.pop(key,None)
        if val.reader.delta_indices is not None: val.reader.delta_indices.pop(key,None)
        if val.delta_timestamps is not None: val.delta_timestamps.pop(key,None)
    validation = MixedDataset([val],stats)
    cfg.output_dir.mkdir(parents=True,exist_ok=False)
    (cfg.output_dir/'train_stats.json').write_text(json.dumps({k:{s:v.tolist() for s,v in x.items()} for k,x in stats.items()},indent=2))
    (cfg.output_dir/'data_recipe.json').write_text(json.dumps(dict(
        source_roots=list(map(str,roots)), splits=splits, source_lengths=ACTIVE_LENGTHS,
        batch_sources={'sorting':4,'doll_nohome':2,'cup_nohome':2},
        validation='sorting heldout only', initialization='fresh ACT, seed 1000; ImageNet ResNet18',
        nohome_validation_report=json.loads((DATA/'validation_report.json').read_text())),indent=2))
    # Check actual sampler draws and checkpoint-independent source proportions before optimization.
    sampler = BalancedSampler(seed=cfg.seed)
    draws = np.array(list(iter(sampler))[:800]).reshape(-1,8)
    first,second = ACTIVE_LENGTHS[0],sum(ACTIVE_LENGTHS[:2])
    assert np.all((draws < first).sum(1)==4)
    assert np.all(((draws >= first)&(draws < second)).sum(1)==2)
    assert np.all((draws >= second).sum(1)==2)
    print('MIX source frames:',ACTIVE_LENGTHS,'episodes:',[d.num_episodes for d in datasets], 'sorting validation:',len(ids),flush=True)
    return training,validation

def main(output, smoke=False):
    assert json.loads((DATA/'READY.json').read_text())['verified']
    settings = dict(TRAINING_SETTINGS)
    if smoke: settings.update(steps=10,save_freq=10,eval_steps=10,log_freq=5)
    policy = ACTConfig(input_features={
        'observation.state':PolicyFeature(FeatureType.STATE,(6,)),
        'observation.images.top':PolicyFeature(FeatureType.VISUAL,(3,480,640)),
        'observation.images.side':PolicyFeature(FeatureType.VISUAL,(3,480,640))},
        output_features={'action':PolicyFeature(FeatureType.ACTION,(6,))},
        device='cuda',use_amp=False,push_to_hub=False,chunk_size=100,n_action_steps=100,
        pretrained_backbone_weights='ResNet18_Weights.IMAGENET1K_V1')
    cfg = TrainPipelineConfig(dataset=DatasetConfig(repo_id='local/sorting_pickplace_nohome_mix_v1',
        root=str(BASE/'datasets/sorting/dataset'),video_backend='torchcodec',use_imagenet_stats=False,eval_split=0.1),
        policy=policy,output_dir=Path(output),job_name='act_sorting_pickplace_nohome_mix_v1',
        seed=1000,prefetch_factor=2,save_checkpoint=True,wandb=WandBConfig(enable=False),**settings)
    trainer=importlib.import_module('lerobot.scripts.lerobot_train')
    old_make,old_sampler=trainer.make_train_eval_datasets,trainer.EpisodeAwareSampler
    trainer.make_train_eval_datasets=lambda cfg: make_datasets(cfg,1 if smoke else None)
    trainer.EpisodeAwareSampler=BalancedSampler
    try: train_with_best(trainer,cfg)
    finally: trainer.make_train_eval_datasets,trainer.EpisodeAwareSampler=old_make,old_sampler

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    main(args.output,args.smoke)
