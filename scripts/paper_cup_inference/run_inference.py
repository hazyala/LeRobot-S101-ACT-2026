"""SO-101 종이컵 ACT 모델 추론 실행."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 다른 학습 결과 사용 시 paper_cup_training을 해당 학습 결과 폴더명으로 변경
TRAINING_DIR = PROJECT_ROOT / "models" / "paper_cup_training"
# 선택한 학습 결과에서 최고 모델 자동 사용
MODEL_DIR = TRAINING_DIR / "best_model"
CALIBRATION_DIR = PROJECT_ROOT / "datasets" / "calibration"
os.environ["HF_DATASETS_CACHE"] = str(PROJECT_ROOT / ".cache" / "huggingface" / "datasets")
os.environ["HF_HUB_OFFLINE"] = "1"

import cv2
import numpy as np
import torch
from safetensors.torch import load_file
from lerobot.cameras import Cv2Backends
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.cameras.realsense import RealSenseCameraConfig
from lerobot.datasets import LeRobotDatasetMetadata
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTConfig, ACTPolicy
from lerobot.robots import make_robot_from_config
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

import inference_control as control
from robot_shutdown import shutdown


# 포트와 카메라 정보는 scripts/settings.py에서 수정
def load_settings():
    path = PROJECT_ROOT / "scripts" / "settings.py"
    spec = importlib.util.spec_from_file_location("practice_settings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 모델 파일, 데이터셋 형식, GPU 확인 후 ACT와 정규화 정보 불러오기
def load_runtime():
    required = ["config.json", "train_config.json", "model.safetensors", "policy_preprocessor.json",
                "policy_postprocessor.json", "policy_postprocessor_step_0_unnormalizer_processor.safetensors",
                "policy_preprocessor_step_3_normalizer_processor.safetensors"]
    missing = [str(MODEL_DIR / name) for name in required if not (MODEL_DIR / name).is_file()]
    calibration = CALIBRATION_DIR / "follower.json"
    if not calibration.is_file():
        missing.append(str(calibration))
    if missing:
        raise FileNotFoundError("필수 파일 누락:\n" + "\n".join(missing))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU를 찾을 수 없습니다.")

    # 학습 설정에 저장된 데이터셋 이름으로 현재 실습 폴더에서 데이터셋 찾기
    training = json.loads((MODEL_DIR / "train_config.json").read_text(encoding="utf-8"))
    repo_id = training["dataset"]["repo_id"]
    dataset_name = repo_id.rsplit("/", 1)[-1]
    if dataset_name in ("", ".", "..") or "\\" in dataset_name:
        raise ValueError("학습 설정의 데이터셋 이름이 올바르지 않습니다.")
    dataset_dir = PROJECT_ROOT / "datasets" / dataset_name
    if not (dataset_dir / "meta" / "info.json").is_file():
        raise FileNotFoundError(f"학습 데이터셋을 찾을 수 없습니다: {dataset_dir}")
    metadata = LeRobotDatasetMetadata(repo_id, root=dataset_dir)
    if len(metadata.tasks) != 1:
        raise ValueError("본 실습은 작업 설명이 하나인 데이터셋만 지원합니다.")
    task = str(metadata.tasks.index[0])
    names = list(metadata.features["action"]["names"])
    if names != list(control.MAX_DELTA_PER_STEP) or metadata.features["observation.state"]["names"] != names:
        raise ValueError("데이터셋 관절 순서가 실습 로봇과 다릅니다.")
    expected = {"observation.state", "observation.images.top", "observation.images.side"}
    config = ACTConfig.from_pretrained(MODEL_DIR)
    if set(config.input_features) != expected or config.action_feature.shape != (6,):
        raise ValueError("모델의 입력 또는 출력 구성이 다릅니다.")
    if config.input_features["observation.state"].shape != (6,) or any(
        config.input_features[key].shape != (3, 480, 640)
        for key in ("observation.images.top", "observation.images.side")
    ) or metadata.fps != 30 or config.chunk_size != 100:
        raise ValueError("모델 또는 데이터셋의 관절 수·화면 크기·FPS·행동 묶음이 실습 설정과 다릅니다.")
    config.device = "cuda"
    config.pretrained_backbone_weights = None
    policy = ACTPolicy.from_pretrained(MODEL_DIR, config=config, strict=True).to("cuda").eval()
    preprocess, postprocess = make_pre_post_processors(config, pretrained_path=str(MODEL_DIR))
    # 해당 모델의 학습 데이터에서 계산한 행동 범위 사용
    stats = load_file(str(MODEL_DIR / "policy_postprocessor_step_0_unnormalizer_processor.safetensors"))
    low = stats["action.min"].numpy().astype(np.float32)
    high = stats["action.max"].numpy().astype(np.float32)
    if low.shape != (6,) or not np.isfinite(low).all() or not np.isfinite(high).all() or np.any(low >= high):
        raise ValueError("학습된 행동 범위가 올바르지 않습니다.")
    features = {key: metadata.features[key] for key in expected}
    return task, policy, preprocess, postprocess, features, names, low, high


def main():
    parser = argparse.ArgumentParser(description="종이컵 ACT 추론")
    # --preflight-only: 로봇 연결 없이 모델과 설정만 확인
    parser.add_argument("--preflight-only", action="store_true", help="장비 연결 없이 모델과 설정 확인")
    args = parser.parse_args()
    settings = load_settings()
    if settings.FPS != 30:
        raise ValueError("본 모델은 30 FPS 설정이 필요합니다.")
    runtime = load_runtime()
    task, policy, _, _, _, names, low, high = runtime
    print(f"작업: {task}")
    print(f"모델: {MODEL_DIR}")
    record = PROJECT_ROOT / "outputs" / TRAINING_DIR.name / "best.json"
    if record.is_file():
        best = json.loads(record.read_text(encoding="utf-8"))
        print(f"최고 모델: {best['step']} 단계 · 검증 손실 {best['eval_loss']:.6f}")
    print(f"GPU: {torch.cuda.get_device_name(0)} · 행동 묶음: {policy.config.chunk_size}")
    if args.preflight_only:
        print("사전 점검 완료 · 로봇과 카메라를 연결하지 않았습니다.")
        return

    # 실습 환경에 맞는 Follower와 TOP·SIDE 카메라 설정
    config = SOFollowerRobotConfig(
        id="follower", port=settings.FOLLOWER_PORT, calibration_dir=CALIBRATION_DIR,
        max_relative_target=12.0,
        cameras={
            "top": RealSenseCameraConfig(serial_number_or_name=settings.TOP_SERIAL,
                width=640, height=480, fps=30, use_depth=False),
            "side": OpenCVCameraConfig(index_or_path=settings.SIDE_CAMERA_INDEX,
                width=640, height=480, fps=30, backend=Cv2Backends.DSHOW,
                fourcc=settings.SIDE_FOURCC, warmup_s=3),
        },
    )
    robot = make_robot_from_config(config)
    # 30 FPS, 최대 40초, 60스텝마다 행동 재예측
    options = SimpleNamespace(fps=30, max_duration_s=40.0, replan_every=60,
                              max_inference_ms=750.0)  # 추론 시간 제한
    emergency = False
    started = False
    failed = False
    try:
        # 기존 캘리브레이션 사용 · 새로 캘리브레이션하지 않음
        if not robot.calibration:
            raise RuntimeError("Follower 캘리브레이션을 불러오지 못했습니다.")
        robot.connect(calibrate=False)
        if not robot.is_calibrated:
            robot.bus.write_calibration(robot.calibration)
        if not robot.is_calibrated:
            raise RuntimeError("Follower 캘리브레이션 적용 실패")
        cv2.namedWindow(control.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(control.WINDOW_NAME, 1280, 480)
        print("화면 선택 후 SPACE 시작 · P 일시정지 · Q 홈 복귀 · E 긴급 토크 OFF")
        # 시작 전 종료 시 홈 이동 없이 연결 해제
        def mark_started():
            nonlocal started
            started = True
        emergency = control.run_episode(robot, options, runtime, mark_started) == "emergency"
    except control.EmergencyStop:
        emergency = True
        print("긴급 정지 · 토크 OFF")
    except KeyboardInterrupt:
        print("사용자 종료")
    except Exception:
        failed = True
        raise
    finally:
        # 오류 발생 시 자동 홈 복귀 없이 토크 해제
        if failed and robot.bus.is_connected and not emergency:
            print("오류로 홈 복귀를 중단하고 토크를 해제합니다. 팔이 내려갈 수 있습니다.", flush=True)
            started = False
        shutdown(robot, names, low, high, options.fps, emergency, started)


if __name__ == "__main__":
    main()
