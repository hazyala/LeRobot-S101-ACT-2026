"""선택한 B200 ACT 모델 실행. 기본은 장비 미연결 검사, --run으로 실물 실행.

기존 안전 실행기의 속도·범위 제한, HOME 복귀, SPACE 시작, E 정지를 재사용한다.
모델과 정규화는 선택한 체크포인트에서 함께 읽는다.
"""
from pathlib import Path
import argparse
import json
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='실제 로봇 연결 허용; 동작은 SPACE로 시작')
    parser.add_argument('--max-episodes', type=int, default=1)
    parser.add_argument('--max-duration-s', type=float, default=60)
    args = parser.parse_args()
    selection = json.loads((BASE / 'selection/selected_checkpoint.json').read_text())
    # 절대 경로가 아닌 체크포인트 번호로 현재 프로젝트 안에서 다시 찾는다.
    checkpoint = selection['checkpoint']
    if not checkpoint.isdigit():
        raise ValueError('선택한 체크포인트 번호가 잘못됐습니다.')
    model_dir = BASE / 'act_doll_basic/checkpoints' / checkpoint / 'pretrained_model'

    from episode_sample_dataset.doll_pickplace_act import run_act_pickplace_safe as safe
    import numpy as np
    import torch
    from lerobot.datasets import LeRobotDatasetMetadata
    from lerobot.policies.act import ACTConfig, ACTPolicy
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.utils import build_inference_frame

    safe.DATASET_ROOT = ROOT / 'robot_datasets/tasks/pick_doll/dataset'
    safe.MODEL_DIR = model_dir
    safe.CHECKPOINT_DIR = model_dir.parent
    safe.REPO_ID = 'local/doll'
    safe.TASK = 'Pick up the doll and place it in the container.'
    rig = json.loads((ROOT / 'collection/settings.json').read_text(encoding='utf-8'))['rig']
    if (rig['fps'], rig['width'], rig['height']) != (30, 640, 480):
        raise RuntimeError('학습과 같은 30 FPS, 640x480 카메라 설정이 필요합니다.')
    safe.HOME_POSE = rig['home_pose']
    safe.HOME_TOLERANCE = rig['home_tolerance']
    safe.HOME_STABLE_TIME_S = rig['home_stable_seconds']

    def load_runtime():
        if not torch.cuda.is_available():
            raise RuntimeError('로컬 CUDA GPU가 필요합니다.')
        metadata = LeRobotDatasetMetadata(safe.REPO_ID, root=safe.DATASET_ROOT)
        if metadata.total_episodes != 499 or metadata.total_frames != 291869:
            raise RuntimeError('선택 평가에 사용한 데이터셋과 현재 데이터가 다릅니다.')
        config = ACTConfig.from_pretrained(model_dir)
        config.device = 'cuda'
        config.pretrained_backbone_weights = None
        policy = ACTPolicy.from_pretrained(model_dir, config=config, strict=True).to('cuda').eval()
        expected = {'observation.state', 'observation.images.top', 'observation.images.side'}
        if set(config.input_features) != expected or config.action_feature.shape != (6,):
            raise RuntimeError('관절+RGB 기본 모델의 입력/출력과 다릅니다.')
        preprocess, postprocess = make_pre_post_processors(config, pretrained_path=str(model_dir))
        names = list(metadata.features['action']['names'])
        if names != list(safe.MAX_DELTA_PER_STEP):
            raise RuntimeError('모터 축 순서가 기존 실행기와 다릅니다.')
        stats = json.loads((BASE / 'act_doll_basic/train_stats.json').read_text())
        low = np.asarray(stats['action']['min'], dtype=np.float32)
        high = np.asarray(stats['action']['max'], dtype=np.float32)
        if not np.isfinite(low).all() or not np.isfinite(high).all() or np.any(low >= high):
            raise RuntimeError('학습 데이터의 행동 범위가 잘못됐습니다.')
        features = {key: value for key, value in metadata.features.items() if key in expected}
        return metadata, policy, preprocess, postprocess, features, names, low, high

    def predict(observation, policy, preprocess, postprocess, inference_features):
        frame = build_inference_frame(observation=observation, ds_features=inference_features,
                                      device=torch.device('cuda'), task=safe.TASK,
                                      robot_type='so101_follower')
        batch = preprocess(frame)
        torch.cuda.synchronize()
        start = time.perf_counter()
        # 평가와 같은 FP32로 추론하고, 이전 실행기의 FP16 강제는 사용하지 않는다.
        with torch.inference_mode():
            chunk = policy.predict_action_chunk(batch)
        torch.cuda.synchronize()
        elapsed = (time.perf_counter()-start)*1000
        actions = postprocess(chunk)[0].cpu().numpy()
        if actions.shape != (100, 6) or not np.isfinite(actions).all():
            raise RuntimeError('추론 결과가 잘못됐습니다.')
        return actions, elapsed

    original_configs = safe.make_configs
    def current_configs():
        from dataclasses import replace
        leader, follower = original_configs()
        follower.port = rig['follower_port']
        leader.port = rig['leader_port']
        follower.cameras['top'] = replace(follower.cameras['top'],
            serial_number_or_name=rig['top_serial'], width=rig['width'], height=rig['height'],
            fps=rig['fps'], exposure=rig['top_exposure'], gain=rig['top_gain'])
        follower.cameras['side'] = replace(follower.cameras['side'],
            index_or_path=rig['side_index'], width=rig['width'], height=rig['height'], fps=rig['fps'])
        return leader, follower

    safe.load_policy_runtime = load_runtime
    safe.predict_chunk = predict
    safe.make_configs = current_configs
    safe.DEFAULT_GRIPPER_CLOSE_LEAD_FRAMES = 0
    print('선택 모델:', model_dir, flush=True)
    print('선택 기준: 검증 행동 MAE; 실제 파지 성공률은 미측정', flush=True)
    # 기본은 기존 실행기의 하드웨어 미연결 preflight 모드다.
    sys.argv = [str(__file__), '--max-episodes', str(args.max_episodes),
                '--max-duration-s', str(args.max_duration_s), '--gripper-close-lead-frames', '0']
    if not args.run:
        sys.argv.append('--preflight-only')
    safe.main()


if __name__ == '__main__':
    main()
