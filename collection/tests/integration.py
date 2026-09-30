"""Hardware-free integration: create, discard, save, resume, decode, merge all six tasks."""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core as common

from core import BASE, ROOT, atomic_json, load_engine, registry, repo_id
from core import require_valid


def run():
    m = load_engine()
    # Reuse the exact feature schema of the established dataset, including depth metadata.
    import json
    template = json.loads((ROOT / "episode_sample_dataset/auto_home_collection/auto_home_dataset/meta/info.json").read_text())
    from lerobot.datasets.aggregate import aggregate_datasets
    tasks = registry()
    with tempfile.TemporaryDirectory(prefix="collection_smoke_", dir=ROOT / "collection") as temp:
        roots = []
        for task in tasks:
            root = Path(temp) / "tasks" / task["key"] / "dataset"
            roots.append(root)
            kwargs = dict(root=root, rgb_encoder=m.RGB_ENCODER, depth_encoder=m.DEPTH_ENCODER,
                          streaming_encoding=True, encoder_queue_maxsize=300)
            ds = m.LeRobotDataset.create(repo_id(task), 30, robot_type="so101_follower",
                                        features=copy.deepcopy(template["features"]), use_videos=True, **kwargs)
            # A clean quit before the first recording must still be resumable.
            ds.finalize()
            ds = m.LeRobotDataset.resume(repo_id(task), **kwargs)
            def frame():
                return {"action": m.np.zeros(6, dtype=m.np.float32),
                        "observation.state": m.np.zeros(6, dtype=m.np.float32),
                        "observation.images.top": m.np.zeros((480, 640, 3), dtype=m.np.uint8),
                        "observation.images.side": m.np.zeros((480, 640, 3), dtype=m.np.uint8),
                        "observation.images.top_depth": m.np.full((480, 640, 1), 300, dtype=m.np.uint16),
                        "task": task["instruction"]}
            try:
                ds.add_frame(frame())
                ds.clear_episode_buffer()
                for _ in range(8):
                    ds.add_frame(frame())
                ds.save_episode()
            finally:
                ds.finalize()
            ds = m.LeRobotDataset.resume(repo_id(task), **kwargs)
            try:
                for _ in range(8):
                    ds.add_frame(frame())
                ds.save_episode()
            finally:
                ds.finalize()
            require_valid(task=task, root=root, deep=True)
            if task["id"] == 0:
                from core import snapshot, recover
                with patch.object(common, "STORE", Path(temp)):
                    snapshot(task)
                    atomic_json(root.parent / "pending_episode.json", {"episode": 2, "status": "saving"})
                    damaged_info = common.read_json(root / "meta/info.json")
                    damaged_info["total_frames"] += 1
                    atomic_json(root / "meta/info.json", damaged_info)
                    recover(task)
                    require_valid(task=task, root=root, deep=True)
                    assert common.read_json(root / "meta/info.json")["total_frames"] == 16
                    assert list(root.parent.glob("interrupted_*"))
            reader = m.LeRobotDataset(repo_id(task), root=root, video_backend="pyav")
            for index in [0, 15]:
                assert reader[index]["task"] == task["instruction"]
                assert reader[index]["observation.images.top"].shape == (3, 480, 640)
        merged = Path(temp) / "merged"
        aggregate_datasets([repo_id(t) for t in tasks], "local/smoke_merged", roots=roots,
                           aggr_root=merged, concatenate_videos=False, concatenate_data=False)
        require_valid(root=merged, deep=True, expected_tasks=[t["instruction"] for t in tasks])
        print("PASS: empty resume, discard, save, resume, recovery, RGB/depth decode, six-task merge and task_index mapping")
    from datetime import datetime, timezone
    atomic_json(BASE / "reports/smoke_test.json", {"passed": True, "checked_utc": datetime.now(timezone.utc).isoformat(),
                "tasks": 6, "episodes_per_task": 2, "frames_per_episode": 8,
                "checks": ["empty resume", "discard", "save", "resume", "recovery", "RGB/depth decode", "merge", "task_index 0..5"]})


if __name__ == '__main__':
    run()
