"""Exhaustive index/prefix checks and one real ACT-boundary loader query per episode."""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collection"))
from core import setup_environment


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    setup_environment()
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.datasets.dataset_reader import DatasetReader

    base = ROOT / "robot_datasets/derived/pickplace_nohome_v1"
    status = read(base / "BUILD_STATUS.json")
    assert status["stage"] == "built_pending_validation"
    result = {}
    for name, expected in [("doll", 499), ("cup", 250)]:
        root = base / name / "dataset"
        derivation = read(root.parent / "derivation.json")
        info = read(root / "meta/info.json")
        split = read(root.parent / "split.json")
        assert sorted(split["train"] + split["validation"]) == list(range(expected))
        assert not set(split["train"]) & set(split["validation"])
        dataset = LeRobotDataset("local/" + name + "_nohome", root=root,
                    delta_timestamps={"action": [i / 30 for i in range(100)]},
                    video_backend="pyav", return_uint8=True)
        assert dataset.num_episodes == expected
        assert dataset.num_frames == info["total_frames"]
        cursor = 0
        for mapping in derivation["episodes"]:
            ep, n = mapping["derived_episode"], mapping["retained_frames"]
            meta = dataset.meta.episodes[ep]
            table = pq.read_table(root / dataset.meta.get_data_file_path(ep))
            assert len(table) == n
            assert set(table["episode_index"].to_pylist()) == {ep}
            assert np.array_equal(table["frame_index"].to_numpy(), np.arange(n))
            assert np.array_equal(table["index"].to_numpy(), np.arange(cursor, cursor + n))
            assert np.allclose(table["timestamp"].to_numpy(), np.arange(n) / 30, atol=1e-4)
            assert (meta["dataset_from_index"], meta["dataset_to_index"]) == (cursor, cursor + n)
            h = hashlib.sha256(table["action"].combine_chunks().values.to_numpy().tobytes()
                               + table["observation.state"].combine_chunks().values.to_numpy().tobytes()).hexdigest()
            assert h == mapping["retained_action_state_sha256"]
            # Re-read source values to ensure no approach/grasp/place targets were altered.
            original = pq.read_table(mapping["source_data_file"], columns=["episode_index", "action", "observation.state"])
            original = original.filter(pa.compute.equal(original["episode_index"], ep)).slice(0, n)
            for feature in ("action", "observation.state"):
                assert original[feature].to_pylist() == table[feature].to_pylist()
                assert np.isfinite(np.asarray(table[feature].to_pylist())).all()
            for video in mapping["videos"]:
                path = root / dataset.meta.get_video_file_path(ep, video["key"])
                source = Path(video["source"])
                assert os.path.samefile(path, source)
                assert source.stat().st_size == video["size"]
                assert source.stat().st_mtime_ns == video["source_mtime_ns"]
                assert abs(meta[f"videos/{video['key']}/to_timestamp"]
                           - meta[f"videos/{video['key']}/from_timestamp"] - n / 30) < 1e-6
            for offset in [0, max(0, n - 100), n - 20, n - 1]:
                query, padding = dataset.reader._get_query_indices(cursor + offset, ep)
                assert min(query["action"]) >= cursor
                assert max(query["action"]) < cursor + n
                assert int(padding["action_is_pad"].sum()) == max(0, offset + 100 - n)
            # Actual image decode + numeric lookup at the action boundary, every episode.
            sample = dataset[cursor + n - 20]
            assert tuple(sample["action"].shape) == (100, 6)
            assert int(sample["action_is_pad"].sum()) == 80
            assert torch.equal(sample["action"][20:], sample["action"][19:20].repeat(80, 1))
            assert torch.isfinite(sample["action"]).all()
            for camera in ("observation.images.top", "observation.images.side"):
                assert tuple(sample[camera].shape) == (3, 480, 640)
            cursor += n
            if (ep + 1) % 25 == 0:
                print(f"{name}: validated {ep + 1}/{expected}", flush=True)
        assert cursor == info["total_frames"]
        result[name] = {"episodes": expected, "frames": cursor,
                        "train_episodes": len(split["train"]), "validation_episodes": len(split["validation"]),
                        "prefix_values_match_source": True, "indices_and_timestamps_valid": True,
                        "all_episode_chunk_boundaries_valid": True,
                        "real_RGB_and_chunk_queries": expected, "source_videos_unmodified": True}
        del dataset
    report = {"passed": True, "datasets": result, "episodes": 749,
              "visual_review": "all episode boundary-before/end/after snapshots; not all full-rollout frames",
              "full_video_decode_performed": False, "training_started": False,
              "hardware_connected": False,
              "limitations": "No mathematical guarantee of every visual action being correct; no whole-video corruption sweep."}
    write(base / "validation_report.json", report)
    status.update(stage="validated", ready_for_training=True,
                  readiness_scope="reviewed prefix boundaries + complete structural and ACT-loader boundary checks",
                  validation_report="validation_report.json")
    write(base / "BUILD_STATUS.json", status)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
