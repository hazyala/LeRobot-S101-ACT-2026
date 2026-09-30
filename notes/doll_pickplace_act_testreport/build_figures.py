"""Rebuild report figures from saved metadata/logs; never connects to a robot."""

from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
from safetensors import safe_open


ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
IMG = REPORT / "img"
DATASET = ROOT / "episode_sample_dataset/auto_home_collection/auto_home_dataset"
WORK = ROOT / "episode_sample_dataset/doll_pickplace_act"
CHECKPOINTS = WORK / "outputs/act_100ep_20k/checkpoints"
IMG.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def save(name: str) -> None:
    plt.savefig(IMG / name, dpi=180, bbox_inches="tight")
    plt.close()


with (DATASET / "meta/info.json").open(encoding="utf-8") as file:
    info = json.load(file)
episode_files = sorted((DATASET / "meta/episodes").rglob("*.parquet"))
episodes = pq.read_table(episode_files, columns=["episode_index", "length"]).to_pandas()
episodes = episodes.sort_values("episode_index")
lengths = episodes["length"].to_numpy()
assert len(lengths) == info["total_episodes"] == 100
assert int(lengths.sum()) == info["total_frames"] == 56768

storage = {}
for folder in ("data", "meta", "videos"):
    storage[folder] = sum(path.stat().st_size for path in (DATASET / folder).rglob("*") if path.is_file())
streams = {}
for key in ("top", "side", "top_depth"):
    files = list((DATASET / "videos" / f"observation.images.{key}").rglob("*.mp4"))
    streams[key] = {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}

fig, ax = plt.subplots(figsize=(11, 3.7))
ax.bar(episodes["episode_index"] + 1, lengths / 30, color="#3678aa", width=0.8)
ax.axhline(lengths.mean() / 30, color="#c65338", ls="--", label=f"mean {lengths.mean()/30:.2f} s")
ax.set(xlabel="Episode number (1-based)", ylabel="Duration (s)", title="Recorded duration by episode")
ax.legend(frameon=False)
save("dataset_episode_durations.png")

fig, ax = plt.subplots(figsize=(7.2, 3.4))
labels = ["Top depth", "Side RGB", "Top RGB", "Parquet + metadata"]
values = [streams["top_depth"]["bytes"], streams["side"]["bytes"], streams["top"]["bytes"], storage["data"] + storage["meta"]]
bars = ax.barh(labels[::-1], np.asarray(values[::-1]) / 1e9, color=["#b7bec8", "#5795c4", "#7bc3c7", "#7459a6"])
for bar in bars:
    ax.text(bar.get_width() + 0.04, bar.get_y() + bar.get_height()/2, f"{bar.get_width():.3f} GB", va="center")
ax.set(xlim=(0, 12.9), xlabel="Disk storage (decimal GB)", title="Dataset storage by component")
save("dataset_storage.png")

pattern = re.compile(r"step:(\d+)(K?) smpl:.*?loss:([0-9.]+).*?l1_loss:([0-9.]+) kld_loss:([0-9.]+)")
loss_rows = []
for name in ("train_stderr.log", "train_resume_stderr.log"):
    content = (WORK / name).read_text(encoding="utf-8", errors="replace")
    for match in pattern.finditer(content):
        loss_rows.append(tuple(float(match.group(i)) for i in range(3, 6)))
assert len(loss_rows) == 1000, f"Expected 1000 loss logs, got {len(loss_rows)}"
records = {20 * (index + 1): row for index, row in enumerate(loss_rows)}
checkpoint_steps = sorted(int(path.name) for path in CHECKPOINTS.iterdir() if path.is_dir() and path.name.isdigit())
assert checkpoint_steps == list(range(2000, 20001, 2000))
logged_steps = sorted(records)
assert logged_steps[-1] == 20000
fig, (ax, ax_late) = plt.subplots(1, 2, figsize=(12.3, 4.0), gridspec_kw={"width_ratios": [1.2, 1]})
for index, (label, color) in enumerate((("total loss", "#174c78"), ("L1", "#e47b38"), ("KL", "#7d69a8"))):
    values = [records[s][index] for s in logged_steps]
    ax.plot(logged_steps, values, label=label, color=color, linewidth=1.2)
    if index < 2:
        ax_late.plot(logged_steps, values, label=label, color=color, linewidth=1.2)
for step in checkpoint_steps:
    ax.axvline(step, color="#cdd1d4", linewidth=0.6, zorder=0)
    ax_late.axvline(step, color="#cdd1d4", linewidth=0.6, zorder=0)
ax.set_yscale("log")
ax.set(xlabel="Training step", ylabel="Loss (log scale)", title="All 1,000 logs (every 20 steps)")
ax_late.set(xlabel="Training step", ylabel="Loss (linear scale)", xlim=(2000, 20000), ylim=(0, 1.85), title="After 2k (checkpoint lines)")
ax.legend(frameon=False)
fig.suptitle("Training loss only; no held-out validation curve", fontsize=12)
save("training_loss_checkpoints.png")

checkpoint_sizes = []
for step in checkpoint_steps:
    checkpoint_sizes.append(sum(p.stat().st_size for p in (CHECKPOINTS / f"{step:06d}").rglob("*") if p.is_file()))
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.bar([str(s//1000) + "k" for s in checkpoint_steps], np.asarray(checkpoint_sizes)/1e6, color="#4b81a9")
ax.set(xlabel="Checkpoint step", ylabel="Size (MB)", ylim=(0, max(checkpoint_sizes)/1e6*1.2), title="Saved model + optimizer state per checkpoint")
save("checkpoint_sizes.png")

with (WORK / "validation_outputs/offline_metrics.csv").open(newline="", encoding="utf-8-sig") as file:
    metrics = list(csv.DictReader(file))
shutil.copy2(WORK / "validation_outputs/action_chunk_comparison.png", IMG / "offline_action_chunk_example.png")
names = [row["joint"].replace("shoulder_", "sh_").replace("wrist_", "wr_") for row in metrics]
mae = np.array([float(row["MAE"]) for row in metrics])
rmse = np.array([float(row["RMSE"]) for row in metrics])
outside = np.array([float(row["outside_train_range_pct"]) for row in metrics])
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.7, 4.1), gridspec_kw={"width_ratios": [1.4, 1]})
x = np.arange(6)
ax1.bar(x-0.18, mae, 0.36, label="MAE", color="#4e8bb7")
ax1.bar(x+0.18, rmse, 0.36, label="RMSE", color="#cf784f")
ax1.set(ylabel="Position error (arm: degrees; gripper: dataset units)", title="In-sample action reconstruction")
ax1.set_xticks(x, names, rotation=30, ha="right")
ax1.legend(frameon=False)
ax2.barh(names[::-1], outside[::-1], color="#9a6aa8")
ax2.axvline(1, color="#c64c42", ls="--", label="review threshold 1%")
ax2.set(xlabel="Predictions outside train range (%)", title="Range review")
ax2.legend(frameon=False, fontsize=8)
save("offline_joint_metrics.png")

action_files = sorted((DATASET / "data").rglob("*.parquet"))
table = pq.read_table(action_files, columns=["episode_index", "frame_index", "action"])
ep_col = table["episode_index"].to_numpy()
frame_col = table["frame_index"].to_numpy()
actions = np.asarray(table["action"].to_pylist(), dtype=np.float32)
windows = []
onsets = []
movement_10 = []
for ep in np.unique(ep_col):
    group = actions[ep_col == ep]
    frames = frame_col[ep_col == ep]
    order = np.argsort(frames)
    group = group[order]
    candidates = np.flatnonzero((group[1:, 5] >= 15) & (group[:-1, 5] < 15)) + 1
    candidates = [i for i in candidates if i >= 15 and i+15 < len(group) and np.min(group[max(0, i-15):i, 5]) < 5]
    if not candidates:
        continue
    i = candidates[0]
    windows.append(group[i-15:i+16])
    onsets.append(int(ep))
    movement_10.append(float(np.linalg.norm(group[i+10, :5] - group[i, :5])))
windows = np.asarray(windows)
if len(windows):
    t = np.arange(-15, 16) / 30
    grip = np.median(windows[:, :, 5], axis=0)
    arm = np.median(np.linalg.norm(windows[:, :, :5] - windows[:, 15:16, :5], axis=2), axis=0)
    fig, ax1 = plt.subplots(figsize=(9.3, 3.8))
    ax2 = ax1.twinx()
    ax1.plot(t, grip, color="#a2538f", linewidth=2, label="gripper target")
    ax2.plot(t, arm, color="#24779b", linewidth=2, label="arm joint-vector displacement")
    ax1.axvline(0, color="#333333", ls="--")
    ax1.set(xlabel="Seconds relative to first close target >=15 units", ylabel="Gripper target (dataset units)", title=f"Demonstration command sequence (first closing event; n={len(windows)} episodes)")
    ax2.set_ylabel("Arm joint-vector displacement from t=0 (degrees)")
    ax1.text(0.02, 0.95, "Joint-space motion is not end-effector height", transform=ax1.transAxes, va="top", fontsize=8)
    save("demonstration_grasp_timing.png")

weights = CHECKPOINTS / "020000/pretrained_model/model.safetensors"
with safe_open(weights, framework="np") as file:
    parameter_count = sum(int(np.prod(file.get_slice(name).get_shape())) for name in file.keys())

video_specs = [
    (Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_성공 1.mp4"), [(6.5,"approach"),(7.4,"object tips"),(17.3,"regrasp/lift"),(23.2,"placed")]),
    (Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_20260923_성공2.mp4"), [(17.7,"near upright"),(18.3,"object tips"),(32.3,"regrasp/lift"),(37.0,"placed")]),
]
if all(path.is_file() for path, _ in video_specs):
    fig, axes = plt.subplots(2, 4, figsize=(12.5, 7.5))
    for row, (path, times) in enumerate(video_specs):
        cap = cv2.VideoCapture(str(path))
        for col, (sec, label) in enumerate(times):
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ok, frame = cap.read()
            ax = axes[row, col]
            if ok:
                ax.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            ax.set_title(f"Video {row+1}: {sec:.1f}s | {label}", fontsize=9)
            ax.axis("off")
        cap.release()
    fig.tight_layout()
    save("practice_video_keyframes.png")

summary = {
    "episodes": int(len(lengths)),
    "frames": int(lengths.sum()),
    "fps": int(info["fps"]),
    "duration_s_total": round(float(lengths.sum()/30), 3),
    "episode_length_frames": {"min": int(lengths.min()), "median": float(np.median(lengths)), "mean": float(lengths.mean()), "max": int(lengths.max())},
    "dataset_bytes": int(sum(storage.values())),
    "storage_bytes": storage,
    "stream_bytes": streams,
    "checkpoint_steps": checkpoint_steps,
    "checkpoint_size_bytes": checkpoint_sizes,
    "checkpoint_loss": {str(step): {"total": records[step][0], "l1": records[step][1], "kl": records[step][2]} for step in checkpoint_steps},
    "parameter_count": parameter_count,
    "demonstration_first_close_events": len(onsets),
    "demonstration_arm_joint_change_10f_deg": {"median": float(np.median(movement_10)) if movement_10 else None, "pct_over_5deg": float(np.mean(np.asarray(movement_10)>5)*100) if movement_10 else None},
}
(REPORT / "measurements.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
