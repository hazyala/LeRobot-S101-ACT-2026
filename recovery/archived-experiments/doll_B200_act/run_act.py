"""Deploy doll_basic ACT through the official LeRobot v0.6.1 rollout CLI."""

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOINTS = [f"{name}.pos" for name in (
    "shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"
)]
INPUTS = {
    "observation.state": [6],
    "observation.images.top": [3, 480, 640],
    "observation.images.side": [3, 480, 640],
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_files(model, dataset, calibration):
    for name in ("config.json", "model.safetensors",
                 "policy_preprocessor.json", "policy_postprocessor.json"):
        if not (model / name).is_file():
            raise ValueError(f"Missing checkpoint file: {model / name}")
    cfg = read_json(model / "config.json")
    if cfg.get("type") != "act":
        raise ValueError("Expected an ACT checkpoint.")
    inputs = {key: value["shape"] for key, value in cfg["input_features"].items()}
    outputs = {key: value["shape"] for key, value in cfg["output_features"].items()}
    if inputs != INPUTS or outputs != {"action": [6]}:
        raise ValueError(f"Not a doll_basic checkpoint: inputs={inputs}, outputs={outputs}")
    info = read_json(dataset / "meta" / "info.json")
    # The official base rollout builds state in hardware order. Refuse a mismatch
    # rather than silently sending predictions to a different joint.
    for key in ("observation.state", "action"):
        if info["features"][key].get("names") != JOINTS:
            raise ValueError(f"Training joint order differs from SO-101 hardware: {key}")
    action_names = cfg.get("action_feature_names")
    if action_names and action_names != JOINTS:
        raise ValueError("Checkpoint action_feature_names differs from training metadata.")
    fps = info["fps"]
    if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("Invalid dataset FPS.")
    saved = read_json(calibration)
    if set(saved) != {name.removesuffix(".pos") for name in JOINTS}:
        raise ValueError("Follower calibration must contain all six joints.")
    for name, values in saved.items():
        if values["range_min"] >= values["range_max"]:
            raise ValueError(f"Invalid calibration range: {name}")
    return fps, cfg


def check_model(model, device):
    """Load weights and saved normalization without connecting any hardware."""
    from importlib.metadata import version

    if version("lerobot") != "0.6.1":
        raise ValueError("This launcher requires LeRobot 0.6.1, matching training.")
    import torch
    from lerobot.configs import PreTrainedConfig
    from lerobot.policies import get_policy_class, make_pre_post_processors

    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable; choose --device cpu or repair the GPU environment.")
    config = PreTrainedConfig.from_pretrained(str(model))
    config.device = device
    policy = get_policy_class(config.type).from_pretrained(str(model), config=config)
    policy.to(device).eval()
    make_pre_post_processors(
        policy_cfg=config, pretrained_path=str(model),
        preprocessor_overrides={
            "device_processor": {"device": device},
            "rename_observations_processor": {"rename_map": {}},
        },
    )
    del policy
    if device == "cuda":
        torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True,
                        help="Checkpoint's pretrained_model directory")
    parser.add_argument("--dataset", type=Path, required=True,
                        help="Training dataset directory containing meta/info.json")
    parser.add_argument("--settings", type=Path, default=ROOT / "collection/settings.json")
    parser.add_argument("--calibration-dir", type=Path,
                        default=ROOT / "robot_calibration/robots/so_follower")
    parser.add_argument("--robot-id", default="follower")
    parser.add_argument("--port", help="Override follower port, e.g. COM3 or /dev/ttyACM0")
    parser.add_argument("--task", default="Pick up the doll and place it in the container.")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--max-relative-target", type=float, default=5)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--execute", action="store_true",
                        help="Connect hardware and immediately begin motor control")
    args = parser.parse_args()
    if any(not math.isfinite(x) or x <= 0
           for x in (args.duration, args.max_relative_target)):
        parser.error("duration and max-relative-target must be finite and positive")
    if not args.robot_id or Path(args.robot_id).name != args.robot_id:
        parser.error("robot-id must be a plain filename stem")
    model = args.model.resolve()
    calibration_dir = args.calibration_dir.resolve()
    try:
        fps, cfg = check_files(model, args.dataset, calibration_dir / f"{args.robot_id}.json")
        rig = read_json(args.settings)["rig"]
        if (rig["width"], rig["height"], rig["fps"]) != (640, 480, fps):
            raise ValueError("Camera dimensions/FPS must match the training dataset.")
        check_model(model, args.device)
    except (ValueError, KeyError, OSError, ImportError) as exc:
        parser.error(str(exc))
    cameras = {
        "top": dict(type="intelrealsense", serial_number_or_name=rig["top_serial"],
                    width=640, height=480, fps=fps, color_mode="rgb", use_depth=False,
                    exposure=rig["top_exposure"], gain=rig["top_gain"]),
        "side": dict(type="opencv", index_or_path=rig["side_index"],
                     width=640, height=480, fps=fps, color_mode="rgb"),
    }
    command = [
        sys.executable, "-m", "lerobot.scripts.lerobot_rollout",
        "--strategy.type=base", "--inference.type=sync",
        f"--policy.path={model}", f"--device={args.device}",
        "--robot.type=so101_follower", f"--robot.port={args.port or rig['follower_port']}",
        f"--robot.id={args.robot_id}", f"--robot.calibration_dir={calibration_dir}",
        "--robot.use_degrees=true", f"--robot.max_relative_target={args.max_relative_target}",
        f"--robot.cameras={json.dumps(cameras)}", f"--fps={fps}",
        f"--duration={args.duration}", f"--task={args.task}",
        "--play_sounds=false", "--return_to_initial_position=true",
    ]
    print(f"Preflight passed: {model}\nFPS={fps}, chunk_size={cfg['chunk_size']}, "
          f"n_action_steps={cfg['n_action_steps']}", flush=True)
    if args.preflight_only or not args.execute:
        print("No hardware connected. Use --execute to start rollout.")
        return
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    print("Starting motor control. Ctrl+C requests shutdown and return to initial pose.", flush=True)
    raise SystemExit(subprocess.call(command, env=env))


if __name__ == "__main__":
    main()
