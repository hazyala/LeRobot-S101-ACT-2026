"""Shared collection engine: settings, validation, recovery, and recording."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import queue
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Configuration and dataset locks


BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
STORE = ROOT / "robot_datasets"
LEGACY = ROOT / "episode_sample_dataset/auto_home_collection/auto_home_record.py"
_DLL_HANDLES = []


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def registry():
    tasks = read_json(BASE / "settings.json")["tasks"]
    if [t["id"] for t in tasks] != list(range(6)):
        raise ValueError("Task IDs must be exactly 0..5 in order")
    if len({t["key"] for t in tasks}) != 6 or len({t["instruction"] for t in tasks}) != 6:
        raise ValueError("Task keys and instructions must be unique")
    for t in tasks:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", t["key"]) or not t["instruction"].strip():
            raise ValueError("Invalid task key/instruction")
    return tasks


def task_for(value):
    for task in registry():
        if str(task["id"]) == str(value) or task["key"] == value:
            return task
    raise ValueError(f"Unknown task: {value}")


def task_dir(task):
    return STORE / "tasks" / task["key"]


def rig_config():
    rig = read_json(BASE / "settings.json")["rig"]
    # Changing these requires updating camera features and policy preprocessing together.
    if (rig["fps"], rig["width"], rig["height"], rig["depth_max_m"]) != (30, 640, 480, 2.0):
        raise ValueError("This schema requires 30 FPS, 640x480 and depth_max_m=2.0")
    if set(rig["home_pose"]) != set(rig["home_tolerance"]):
        raise ValueError("HOME pose and tolerance joints must match")
    for field in ("min_free_gb", "max_frame_gap_s", "min_effective_fps", "queue_frames", "home_stable_seconds", "min_episode_seconds"):
        if rig[field] <= 0:
            raise ValueError(f"{field} must be positive")
    if rig["leader_port"] == rig["follower_port"]:
        raise ValueError("Leader and follower must use distinct ports")
    return rig


def data_root(task):
    return task_dir(task) / "dataset"


def repo_id(task):
    return "local/so101_" + task["key"]


def setup_environment():
    # Match the established collector; explicitly fix the Arrow cache too.
    os.environ["HF_HOME"] = str(ROOT / "hf_pickplace_reference")
    os.environ["HF_LEROBOT_HOME"] = str(ROOT / "hf_pickplace_reference/lerobot")
    os.environ["HF_DATASETS_CACHE"] = str(ROOT / ".cache/hf_datasets")
    os.environ["HF_LEROBOT_CALIBRATION"] = str(ROOT / "robot_calibration")
    candidates = list((Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages").glob(
        "BtbN.FFmpeg.GPL.Shared.7.1_*/ffmpeg*/bin"))
    if candidates:
        ffmpeg = candidates[0]
        os.environ["PATH"] = str(ffmpeg) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            _DLL_HANDLES.append(os.add_dll_directory(str(ffmpeg)))


def load_engine(task=None, root=None):
    setup_environment()
    spec = importlib.util.spec_from_file_location("legacy_collection_helpers", LEGACY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rig = rig_config()
    module.FPS = rig["fps"]
    module.HOME_POSE = rig["home_pose"]
    module.HOME_TOLERANCE = rig["home_tolerance"]
    module.TOP_DEPTH_RAW_TO_MM = rig["depth_raw_to_mm"]
    module.TOP_DEPTH_MAX_M = rig["depth_max_m"]
    if root is not None:
        module.DATASET_ROOT = Path(root)
    elif task:
        module.DATASET_ROOT = data_root(task)
    if task:
        module.TASK = task["instruction"]
        module.REPO_ID = repo_id(task)
    return module


def fingerprint(task):
    calibration = {}
    for name, rel in {"leader": "teleoperators/so_leader/leader.json", "follower": "robots/so_follower/follower.json"}.items():
        calibration[name] = hashlib.sha256((ROOT / "robot_calibration" / rel).read_bytes()).hexdigest()
    return {"schema_version": 1, "task": task, "rig": rig_config(),
            "calibration_sha256": calibration,
            "legacy_collector_sha256": hashlib.sha256(LEGACY.read_bytes()).hexdigest(),
            "action_semantics": "absolute_leader_targets_degrees_gripper_0_100",
            "cameras": ["observation.images.top", "observation.images.side", "observation.images.top_depth"]}


def ensure_manifest(task):
    expected = fingerprint(task)
    path = task_dir(task) / "collection_manifest.json"
    if path.exists():
        if read_json(path) != expected:
            raise RuntimeError("Task/rig/calibration changed. Use a new dataset version; do not mix configurations.")
    elif data_root(task).exists():
        raise RuntimeError("Existing dataset has no collection manifest; refusing to adopt it implicitly")
    else:
        atomic_json(path, expected)
    return expected


def check_space(path=ROOT):
    required = read_json(BASE / "settings.json")["rig"]["min_free_gb"]
    free = shutil.disk_usage(path).free / 1e9
    if free < required:
        raise RuntimeError(f"Free disk {free:.1f} GB is below reserve {required} GB")
    return free


@contextlib.contextmanager
def exclusive(path):
    """OS lock is released even after a killed process; the lock file can remain."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        f.seek(0, 2)
        if not f.tell():
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(f"Another process is using this resource: {path}") from exc
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def pending_guard(task):
    path = task_dir(task) / "pending_episode.json"
    if path.exists():
        raise RuntimeError(f"Unfinished episode detected: {path}. Run inspect/recover before collecting.")






def validate(task=None, root=None, deep=False, expected_tasks=None):
    root = Path(root) if root else data_root(task)
    m = load_engine(task, root)
    info = m.load_info()
    # A clean zero-episode dataset may remain after quitting before the first save.
    if info["total_episodes"] == 0:
        if info["total_frames"] or list(root.glob("data/**/*.parquet")) or list(root.glob("videos/**/*.mp4")):
            return ["Zero-episode dataset contains uncommitted data; recover before resuming"]
        return []
    errors = m.validate_existing_dataset()
    if info["fps"] != m.FPS or info["robot_type"] != "so101_follower":
        errors.append("FPS or robot type differs from the collection rig")
    expected_names = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
    for key in ["action", "observation.state"]:
        feature = info["features"].get(key, {})
        if feature.get("shape") != [6] or feature.get("names") != expected_names:
            errors.append(f"{key}: incompatible joint order/shape")
    for key, channels in [("top", 3), ("side", 3), ("top_depth", 1)]:
        feature = info["features"].get("observation.images." + key, {})
        if feature.get("shape") != [480, 640, channels]:
            errors.append(f"{key}: incompatible camera shape")
    expected = expected_tasks or [task["instruction"]]
    tasks_path = root / "meta/tasks.parquet"
    if not tasks_path.exists():
        return errors + ["Missing tasks.parquet"]
    tasks = m.pq.read_table(tasks_path).to_pandas()
    mapping = dict(zip(tasks.index, tasks["task_index"]))
    if mapping != {text: index for index, text in enumerate(expected)}:
        errors.append(f"Task mapping differs from registry: {mapping}")
    rows = m.read_parquet_rows("meta/episodes/chunk-*/file-*.parquet")
    if sum(int(ep["length"]) for ep in rows) != info["total_frames"]:
        errors.append("Episode lengths do not sum to total_frames")
    frames = m.pq.read_table(sorted(root.glob("data/chunk-*/file-*.parquet")))
    for key in ["action", "observation.state"]:
        arr = m.np.asarray(frames[key].to_pylist())
        if arr.shape != (info["total_frames"], 6) or not m.np.isfinite(arr).all():
            errors.append(f"{key}: non-finite or malformed numeric data")
    episode_ids = frames["episode_index"].to_numpy()
    task_ids = frames["task_index"].to_numpy()
    timestamps = frames["timestamp"].to_numpy()
    for ep in rows:
        selected = episode_ids == ep["episode_index"]
        names = list(ep["tasks"])
        if len(names) != 1 or names[0] not in mapping:
            errors.append(f"Episode {ep['episode_index']}: unexpected task sentence")
        elif not m.np.all(task_ids[selected] == mapping[names[0]]):
            errors.append(f"Episode {ep['episode_index']}: task_index mismatch")
        ts = timestamps[selected]
        if not m.np.allclose(ts, m.np.arange(len(ts)) / info["fps"], atol=1e-4):
            errors.append(f"Episode {ep['episode_index']}: timestamp mismatch")
    # Read-only; never silently truncate or repair during validation.
    if deep:
        for path in root.glob("videos/*/chunk-*/*.mp4"):
            try:
                with m.av.open(str(path)) as container:
                    declared = container.streams.video[0].frames
                    decoded = sum(1 for _ in container.decode(video=0))
                    if declared and decoded != declared:
                        errors.append(f"{path}: declared {declared}, decoded {decoded}")
            except Exception as exc:
                errors.append(f"{path}: decode failed: {exc}")
    return errors


def require_valid(**kwargs):
    errors = validate(**kwargs)
    if errors:
        raise RuntimeError("Dataset validation failed:\n" + "\n".join(errors))


# Interrupted-save recovery




def snapshot(task):
    root = data_root(task)
    backup = task_dir(task) / "recovery_snapshot"
    if backup.exists():
        if backup.resolve().parent != task_dir(task).resolve():
            raise RuntimeError("Invalid recovery path")
        shutil.rmtree(backup)
    for name in ("meta", "data"):
        if (root / name).exists():
            shutil.copytree(root / name, backup / name)
    videos = sorted(root.glob("videos/*/chunk-*/*.mp4"))
    latest = {}
    for path in videos:
        latest[path.relative_to(root).parts[1]] = path
    for path in latest.values():
        dest = backup / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    atomic_json(backup / "snapshot.json", {
        "videos": {p.relative_to(root).as_posix(): p.stat().st_size for p in videos},
        "episodes": read_json(root / "meta/info.json")["total_episodes"]})


def safe_child(root, relative):
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise RuntimeError("Snapshot path escapes dataset root")
    return path


def recover(task):
    folder, root = task_dir(task), data_root(task)
    with exclusive(folder / "access.lock"):
        journal = folder / "pending_episode.json"
        if not journal.exists():
            raise RuntimeError("No unfinished episode to recover")
        backup = folder / "recovery_snapshot"
        snapshot_info = read_json(backup / "snapshot.json")
        # If the last save actually completed, preserve it rather than rolling it back.
        try:
            info = read_json(root / "meta/info.json")
            require_valid(task=task, deep=True)
            if info["total_episodes"] == snapshot_info["episodes"] + 1:
                atomic_json(folder / "sessions" / f"episode_{snapshot_info['episodes']:06d}.json",
                            read_json(journal) | {"status": "recovered_completed_save"})
                journal.rename(folder / f"recovered_journal_{datetime.now():%Y%m%d_%H%M%S_%f}.json")
                print("Completed episode validated; preserved the save and cleared the pending marker.")
                return
        except Exception:
            pass
        required = sum(snapshot_info["videos"].values()) + sum(p.stat().st_size for p in backup.rglob("*") if p.is_file())
        if shutil.disk_usage(ROOT).free < required + 20_000_000_000:
            raise RuntimeError("Recovery requires space for a complete copy plus 20 GB reserve")
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        candidate = folder / ("recovered_" + suffix)
        if snapshot_info["episodes"]:
            for name in ("meta", "data"):
                shutil.copytree(backup / name, candidate / name)
            for relative, size in snapshot_info["videos"].items():
                saved = safe_child(backup, relative)
                source = saved if saved.exists() else safe_child(root, relative)
                if source.stat().st_size != size:
                    raise RuntimeError(f"Baseline video changed: {source}. Original data retained")
                target = safe_child(candidate, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            require_valid(task=task, root=candidate, deep=True)
        # Keep the entire failed state, including any newly written videos, for inspection.
        quarantine = folder / ("interrupted_" + suffix)
        if root.resolve().parent != folder.resolve() or quarantine.parent.resolve() != folder.resolve():
            raise RuntimeError("Recovery path outside task folder")
        root.rename(quarantine)
        if candidate.exists():
            try:
                candidate.rename(root)
            except BaseException:
                quarantine.rename(root)
                raise
        journal.rename(folder / ("recovered_journal_" + suffix + ".json"))
        print(f"Restored {snapshot_info['episodes']} saved episodes. Interrupted data retained at {quarantine}")


# Auto-home collection




def configs(m, rig):
    leader, follower = m.make_configs()
    leader.port = rig["leader_port"]
    follower.port = rig["follower_port"]
    follower.cameras["top"].serial_number_or_name = rig["top_serial"]
    follower.cameras["top"].exposure = rig["top_exposure"]
    follower.cameras["top"].gain = rig["top_gain"]
    follower.cameras["side"].index_or_path = rig["side_index"]
    return leader, follower


class AutoHomeCycle:
    """The legacy reset/start/record cycle, independent of cameras and disk I/O."""
    def __init__(self, now, episodes=0, prepare=5, start=1, discard=10,
                 minimum=8, stable=2, maximum=90):
        self.prepare, self.start_delay, self.discard_delay = prepare, start, discard
        self.minimum, self.stable, self.maximum = minimum, stable, maximum
        self.episode = episodes
        self.state, self.changed, self.delay = "PREP", now, prepare
        self.started = self.home_since = None
        self.left_home = self.failed = False

    def remaining(self, now):
        delay = self.start_delay if self.state == "START" else self.delay
        return max(delay - (now - self.changed), 0.0)

    def step(self, now, at_home, command=None, save_busy=False, failed=False):
        # Exit/discard must win over a HOME finish on the same frame.
        if command == "q":
            return "quit"
        if self.state == "RECORDING" and command == "f":
            self.reset(now, discarded=True)
            return "discard"
        if self.state == "PREP":
            if self.remaining(now) == 0 and not save_busy:
                self.state, self.changed = "START", now
        elif self.state == "START":
            if self.remaining(now) == 0:
                self.state, self.started = "RECORDING", now
                self.episode += 1
                self.home_since = now if at_home else None
                self.left_home = self.failed = False
                return "begin"
        else:
            self.failed = self.failed or failed
            if not at_home:
                self.left_home, self.home_since = True, None
            elif self.home_since is None:
                self.home_since = now
            elapsed = now - self.started
            stable = 0 if self.home_since is None else now - self.home_since
            timed_out = elapsed >= self.maximum
            if timed_out or (self.left_home and elapsed >= self.minimum and stable >= self.stable):
                discarded = self.failed or timed_out
                self.reset(now, discarded=discarded)
                return "discard" if discarded else "save"
        return None

    def reset(self, now, discarded):
        if discarded:
            self.episode -= 1
        self.state, self.changed = "PREP", now
        self.delay = self.discard_delay if discarded else self.prepare
        self.started = self.home_since = None
        self.left_home = self.failed = False


def finish_collection(dataset, future, saving, journal):
    """Join a committed save before cleanup; leave failed saves recoverable."""
    save_error = None
    if future is not None:
        try:
            dataset = future.result()
            saving = False
        except BaseException as exc:
            save_error = exc
    if dataset is not None:
        if not saving:
            dataset.clear_episode_buffer()
        dataset.finalize()
        if not saving:
            journal.unlink(missing_ok=True)
    if save_error is not None:
        raise save_error


def run(task, session_label, commands=None, notify=None):
    with exclusive(STORE / "rig.lock"), exclusive(task_dir(task) / "access.lock"):
        pending_guard(task)
        if notify:
            notify("LOADING")
        m = load_engine(task)
        if notify:
            notify("VALIDATING")
        m.validate_calibration_files()
        ensure_manifest(task)
        check_space()
        root = data_root(task)
        if root.exists():
            require_valid(task=task)
        rig = rig_config()
        leader_cfg, follower_cfg = configs(m, rig)
        leader = m.make_teleoperator_from_config(leader_cfg)
        robot = m.make_robot_from_config(follower_cfg)
        ap, rp, op = m.make_default_processors()
        features = m.combine_feature_dicts(
            m.aggregate_pipeline_dataset_features(pipeline=ap, initial_features=m.create_initial_features(action=robot.action_features), use_videos=True),
            m.aggregate_pipeline_dataset_features(pipeline=op, initial_features=m.create_initial_features(observation=robot.observation_features), use_videos=True))
        journal = task_dir(task) / "pending_episode.json"
        dataset = None
        future = None
        saving = False
        executor = ThreadPoolExecutor(max_workers=1)
        previous_frame = None
        frame_count, max_gap = 0, 0.0
        reported_state = None
        pending_key = None

        def incoming():
            if commands is None:
                return None
            result = None
            while True:
                try:
                    value = commands.get_nowait()
                    if value == "q":
                        result = "q"
                    elif result != "q" and value == "f":
                        result = "f"
                except queue.Empty:
                    return result

        def open_dataset():
            kwargs = dict(root=root, image_writer_processes=0, image_writer_threads=12,
                          rgb_encoder=m.RGB_ENCODER, depth_encoder=m.DEPTH_ENCODER,
                          streaming_encoding=True, encoder_queue_maxsize=rig["queue_frames"])
            if root.exists():
                return m.LeRobotDataset.resume(repo_id(task), **kwargs)
            return m.LeRobotDataset.create(repo_id(task), rig["fps"], robot_type="so101_follower",
                                          features=features, use_videos=True, video_files_size_in_mb=1, **kwargs)

        def save_and_reopen(writer, details):
            # Only this thread touches the writer until the main loop collects its result.
            try:
                writer.save_episode(parallel_encoding=True)
            finally:
                writer.finalize()
            require_valid(task=task)
            atomic_json(task_dir(task) / "sessions" / f"episode_{details['episode']:06d}.json", details | {"status": "saved"})
            journal.unlink()
            print(f"Episode {details['episode'] + 1}: saved and validated.", flush=True)
            return open_dataset()

        def render(obs, now):
            nonlocal reported_state
            visible = "SAVING" if saving else cycle.state
            if visible != reported_state:
                if notify:
                    notify(visible)
                reported_state = visible
            at_home = m.is_home(obs, rig["home_pose"])
            worst, diff, tol = m.largest_home_error(obs, rig["home_pose"])
            elapsed = now - cycle.started if cycle.state == "RECORDING" else 0.0
            stable = 0 if cycle.home_since is None else now - cycle.home_since
            episode = cycle.episode if cycle.state == "RECORDING" else cycle.episode + 1
            remaining = cycle.remaining(now) if cycle.state in ("PREP", "START") else None
            m.draw_status(obs, visible, episode, elapsed, m.max_home_error(obs, rig["home_pose"]),
                          stable, at_home, worst, diff, tol, cycle.failed, prep_remaining_s=remaining)
            m.cv2.setWindowTitle("SO-101 Auto Home Recording", f"{task['key']} | AUTO SAVE | f=discard q=quit")

        def key_command(key):
            if key in (ord("q"), ord("Q")):
                return "q"
            if key in (ord("f"), ord("F")):
                return "f"
            return None

        try:
            if incoming() == "q":
                return
            print(f"TASK {task['id']}: {task['instruction']}\nDestination: {root}", flush=True)
            print("Prepare 5s -> START 1s -> record -> HOME 2s -> auto-save. f=discard, q=quit.", flush=True)
            if notify:
                notify("LEADER")
            m.connect_with_saved_calibration(leader, "leader")
            if incoming() == "q":
                return
            if notify:
                notify("FOLLOWER")
            m.connect_with_saved_calibration(robot, "follower")
            if incoming() == "q":
                return
            scale = robot.cameras["top"].rs_profile.get_device().first_depth_sensor().get_depth_scale()
            if abs(scale * 1000 - rig["depth_raw_to_mm"]) > 1e-6:
                raise RuntimeError(f"D405 depth scale changed: {scale} m/unit")
            dataset = open_dataset()
            cycle = AutoHomeCycle(time.perf_counter(), dataset.num_episodes,
                                  prepare=rig["prepare_seconds"], start=m.START_TIME_S,
                                  discard=m.DISCARD_RESET_TIME_S, minimum=rig["min_episode_seconds"],
                                  stable=rig["home_stable_seconds"], maximum=task["max_seconds"])
            while True:
                command = incoming()
                if command == "q" or pending_key == "q":
                    break
                command = command or pending_key
                pending_key = None
                if future is not None and future.done():
                    dataset = future.result()  # Raises before any next episode if save/validation failed.
                    future = None
                    saving = False
                tick = time.perf_counter()
                obs = robot.get_observation()
                m.convert_top_depth_to_mm(obs)
                action = ap((leader.get_action(), obs))
                robot.send_action(rp((action, obs)))
                now = time.perf_counter()
                at_home = m.is_home(obs, rig["home_pose"])
                render(obs, now)
                key = key_command(m.cv2.waitKeyEx(1))
                requested = incoming()
                if "q" in (command, key, requested) or m.cv2.getWindowProperty("SO-101 Auto Home Recording", m.cv2.WND_PROP_VISIBLE) < 1:
                    break
                command = command or key or requested
                failed = False
                elapsed = 0.0
                if cycle.state == "RECORDING" and command != "f":
                    elapsed = now - cycle.started
                    gap = 0 if previous_frame is None else now - previous_frame
                    max_gap = max(max_gap, gap)
                    previous_frame = now
                    observation = m.build_dataset_frame(dataset.features, op(obs), prefix=m.OBS_STR)
                    action_frame = m.build_dataset_frame(dataset.features, action, prefix=m.ACTION)
                    dataset.add_frame({**observation, **action_frame, "task": task["instruction"]})
                    frame_count += 1
                    effective_fps = (frame_count - 1) / elapsed if elapsed > 0 else 0
                    failed = (gap > rig["max_frame_gap_s"] or any(dataset.writer._streaming_encoder._dropped_frames.values())
                              or (elapsed >= rig["min_episode_seconds"] and effective_fps < rig["min_effective_fps"]))
                    if failed and not cycle.failed:
                        print("Frame loss/slow capture detected: this episode will be discarded at HOME or timeout.", flush=True)
                old_state = cycle.state
                outcome = cycle.step(now, at_home, command, save_busy=saving, failed=failed)
                if old_state == "PREP" and cycle.state == "START":
                    check_space()
                    snapshot(task)
                    cycle.changed = time.perf_counter()  # Show the full START second after disk preparation.
                if outcome == "begin":
                    atomic_json(journal, {"episode": cycle.episode - 1, "status": "recording",
                                         "task": task["key"], "session": session_label,
                                         "started_utc": datetime.now(timezone.utc).isoformat()})
                    cycle.started = time.perf_counter()
                    cycle.home_since = cycle.started if at_home else None
                    previous_frame, frame_count, max_gap = None, 0, 0.0
                    print(f"Episode {cycle.episode}: recording.", flush=True)
                elif outcome == "discard":
                    # Show the same 10-second PREP screen immediately, before encoder cleanup.
                    render(obs, time.perf_counter())
                    pending_key = key_command(m.cv2.waitKeyEx(1))
                    dataset.clear_episode_buffer()
                    journal.unlink(missing_ok=True)
                    print(f"Episode {cycle.episode + 1}: discarded; retry after 10s.", flush=True)
                    previous_frame, frame_count, max_gap = None, 0, 0.0
                elif outcome == "save":
                    details = read_json(journal)
                    details.update(status="saving", frames=frame_count, max_gap_s=max_gap, effective_fps=effective_fps)
                    atomic_json(journal, details)
                    saving = True
                    render(obs, time.perf_counter())
                    future = executor.submit(save_and_reopen, dataset, details)
                m.precise_sleep(max(1 / rig["fps"] - (time.perf_counter() - tick), 0))
        except KeyboardInterrupt:
            print("Stopping collection...", flush=True)
        finally:
            try:
                finish_collection(dataset, future, saving, journal)
            finally:
                executor.shutdown(wait=True)
                m.cv2.destroyAllWindows()
                for device in (robot, leader):
                    with contextlib.suppress(Exception):
                        device.disconnect()
                    for camera in getattr(device, "cameras", {}).values():
                        with contextlib.suppress(Exception):
                            camera.disconnect()
                    with contextlib.suppress(Exception):
                        if device.bus.is_connected:
                            device.bus.disconnect()
