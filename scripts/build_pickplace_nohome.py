"""Build separate LeRobot RGB datasets from visually reviewed pick/place prefixes.

Source files are never edited. Video files are hard-linked and their referenced
time ranges are shortened; no video re-encoding or pixel change is performed.
The build refuses unreviewed boundaries and existing output directories.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import shutil
import sys

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
NUMERIC = ["action", "observation.state", "timestamp", "frame_index",
           "episode_index", "index", "task_index"]
CAMERAS = ["observation.images.top", "observation.images.side"]
SOURCES = {"doll": ("pick_doll", 499, "SSH B200/split.json"),
           "cup": ("pick_paper_cup", 250, "SSH B200/paper_cup_basic/split.json")}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stats(array, image=False):
    array = np.asarray(array)
    if array.ndim == 1:
        array = array[:, None]
    shape = (3, 1, 1) if image else (array.shape[1],)
    result = {"min": array.min(0), "max": array.max(0),
              "mean": array.mean(0), "std": array.std(0)}
    for name, q in [("q01", .01), ("q10", .1), ("q50", .5), ("q90", .9), ("q99", .99)]:
        result[name] = np.quantile(array, q, axis=0)
    result = {k: np.asarray(v).reshape(shape) for k, v in result.items()}
    result["count"] = np.array([12 if image else len(array)], dtype=np.int64)
    return result


def sampled_rgb_stats(path, shift, count):
    pixels = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_count = 1
        for index in np.linspace(0, count - 1, 12).astype(int):
            timestamp = shift + index / 30
            container.seek(int(timestamp / stream.time_base), stream=stream)
            decoded = None
            for frame in container.decode(stream):
                if float(frame.pts * stream.time_base) >= timestamp - 1 / 60:
                    decoded = frame
                    break
            if decoded is None or abs(float(decoded.pts * stream.time_base) - timestamp) > 1 / 30:
                raise RuntimeError(f"Cannot decode requested RGB frame {path}: {index}")
            rgb = decoded.to_ndarray(format="rgb24")
            if rgb.shape != (480, 640, 3):
                raise RuntimeError(f"RGB shape mismatch: {path}: {rgb.shape}")
            pixels.append(rgb[::8, ::8].reshape(-1, 3).astype(np.float32) / 255)
    return stats(np.concatenate(pixels), image=True)


def build_source(name, records, destination):
    from lerobot.datasets.compute_stats import aggregate_stats
    from lerobot.datasets.utils import serialize_dict

    key, expected, split_file = SOURCES[name]
    source = ROOT / "robot_datasets/tasks" / key / "dataset"
    info = read(source / "meta/info.json")
    assert info["total_episodes"] == expected
    assert sorted(x["episode"] for x in records) == list(range(expected))
    output = destination / name / "dataset"
    output.mkdir(parents=True)
    features = {k: copy.deepcopy(info["features"][k]) for k in NUMERIC + CAMERAS}
    metadata = {int(row["episode_index"]): row for path in (source / "meta/episodes").rglob("*.parquet")
                for row in pq.read_table(path).to_pylist()}
    all_stats, mappings, frame_cursor = [], [], 0
    for record in sorted(records, key=lambda x: x["episode"]):
        ep = record["episode"]
        assert record["visual_boundary_reviewed"] is True
        n = record["end_exclusive"]
        assert 0 < n < record["last_home_start_frame"] < record["length"]
        original = metadata[ep]
        source_path = source / info["data_path"].format(
            chunk_index=original["data/chunk_index"], file_index=original["data/file_index"])
        table = pq.read_table(source_path)
        table = table.filter(pa.compute.equal(table["episode_index"], ep))
        assert len(table) == record["length"]
        table = table.slice(0, n).select(NUMERIC).replace_schema_metadata(None)
        prefix_hash = hashlib.sha256(table["action"].combine_chunks().values.to_numpy().tobytes()
                                     + table["observation.state"].combine_chunks().values.to_numpy().tobytes()).hexdigest()
        table = table.set_column(table.schema.get_field_index("index"), "index",
                                 pa.array(np.arange(frame_cursor, frame_cursor + n), type=pa.int64()))
        ep_stats = {}
        for column in NUMERIC:
            values = np.asarray(table[column].to_pylist())
            assert np.isfinite(values).all()
            ep_stats[column] = stats(values)
        data_path = output / f"data/chunk-000/file-{ep:03d}.parquet"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, data_path, compression="zstd")
        row = {"episode_index": ep, "tasks": original["tasks"], "length": n,
               "data/chunk_index": 0, "data/file_index": ep,
               "dataset_from_index": frame_cursor, "dataset_to_index": frame_cursor + n,
               "meta/episodes/chunk_index": 0, "meta/episodes/file_index": ep}
        videos = []
        for key in CAMERAS:
            src = source / info["video_path"].format(video_key=key,
                  chunk_index=original[f"videos/{key}/chunk_index"],
                  file_index=original[f"videos/{key}/file_index"])
            dst = output / f"videos/{key}/chunk-000/file-{ep:03d}.mp4"
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.link(src, dst)
            assert os.path.samefile(src, dst)
            shift = float(original[f"videos/{key}/from_timestamp"])
            row.update({f"videos/{key}/chunk_index": 0, f"videos/{key}/file_index": ep,
                        f"videos/{key}/from_timestamp": shift,
                        f"videos/{key}/to_timestamp": shift + n / 30})
            ep_stats[key] = sampled_rgb_stats(dst, shift, n)
            videos.append({"key": key, "source": str(src), "size": src.stat().st_size,
                           "source_mtime_ns": src.stat().st_mtime_ns,
                           "storage": "hardlink; only referenced prefix is part of this dataset"})
        all_stats.append(ep_stats)
        for feature, values in serialize_dict(ep_stats).items():
            for stat, value in values.items():
                row[f"stats/{feature}/{stat}"] = value
        meta_path = output / f"meta/episodes/chunk-000/file-{ep:03d}.parquet"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist([row]), meta_path, compression="zstd")
        mappings.append({**record, "retained_frames": n, "removed_frames": record["length"] - n,
                         "source_dataset": str(source), "source_data_file": str(source_path),
                         "source_episode": ep, "derived_episode": ep,
                         "retained_action_state_sha256": prefix_hash,
                         "data_sha256": digest(data_path), "videos": videos})
        frame_cursor += n
        if (ep + 1) % 25 == 0:
            print(f"{name}: built {ep + 1}/{expected}", flush=True)
    new_info = copy.deepcopy(info)
    new_info.update(features=features, total_frames=frame_cursor, total_episodes=expected,
                    splits={"train": f"0:{expected}"})
    write(output / "meta/info.json", new_info)
    write(output / "meta/stats.json", serialize_dict(aggregate_stats(all_stats)))
    shutil.copy2(source / "meta/tasks.parquet", output / "meta/tasks.parquet")
    split = read(ROOT / split_file)
    assert sorted(split["train"] + split["validation"]) == list(range(expected))
    write(output.parent / "split.json", split)
    write(output.parent / "derivation.json", {
        "source_info_sha256": digest(source / "meta/info.json"),
        "original_files_modified": False,
        "policy_features": list(features),
        "rgb_statistics": "12 evenly spaced retained frames per episode, every eighth pixel; RGB values /255",
        "numeric_statistics": "all retained numeric frames, exact min/max/mean/std/quantiles",
        "metadata_stats_include_heldout": True,
        "training_must_aggregate_only_train_episode_stats": True,
        "video_storage": "unmodified source hardlinks, referenced time range restricted to retained prefix",
        "episodes": mappings,
    })
    return {"episodes": expected, "frames": frame_cursor,
            "removed_frames": info["total_frames"] - frame_cursor,
            "path": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundaries", type=Path, default=ROOT / "collection/reports/pickplace_nohome_749/approved_boundaries.json")
    parser.add_argument("--output", type=Path, default=ROOT / "robot_datasets/derived/pickplace_nohome_v1")
    args = parser.parse_args()
    assert args.output.resolve().is_relative_to((ROOT / "robot_datasets/derived").resolve())
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite: {args.output}")
    records = read(args.boundaries)
    assert len(records) == 749 and all(x["visual_boundary_reviewed"] for x in records)
    args.output.mkdir(parents=True)
    write(args.output / "approved_boundaries.json", records)
    write(args.output / "BUILD_STATUS.json", {"stage": "building", "ready_for_training": False})
    result = {name: build_source(name, [x for x in records if x["source"] == name], args.output)
              for name in SOURCES}
    write(args.output / "BUILD_STATUS.json", {"stage": "built_pending_validation", "ready_for_training": False,
          "boundaries_sha256": digest(args.boundaries), "datasets": result})
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
