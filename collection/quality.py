"""Capture provenance and episode checks; hardware timestamps use the host monotonic clock."""
from __future__ import annotations

import hashlib
import time
import json
from concurrent.futures import ThreadPoolExecutor

TIMING_NAMES = ["state_read_start", "state_read_end", "top_capture", "side_capture",
                "feedback_read_start", "feedback_read_end", "command_send_start",
                "command_send_end", "frame_complete"]


def research_features(motors):
    return {
        "research.leader_action_raw": {"dtype": "float32", "shape": (len(motors),),
                                       "names": [name + ".pos" for name in motors]},
        "research.capture_timing_s": {"dtype": "float32", "shape": (len(TIMING_NAMES),),
                                     "names": TIMING_NAMES},
        "research.camera_frame_numbers": {"dtype": "int64", "shape": (3,),
                                          "names": ["top_rgb_device", "top_depth_device", "side_host_sequence"]},
    }


def camera_bundle(camera, previous=None, timeout_s=0.2, max_age_s=None):
    """Snapshot frames and their host receipt time under one lock; await fresh buffers."""
    deadline = time.perf_counter() + timeout_s
    age_limit = timeout_s if max_age_s is None else max_age_s
    stale_age = None
    while True:
        if camera.thread is None or not camera.thread.is_alive():
            raise RuntimeError("Camera capture thread is not running")
        with camera.frame_lock:
            stamp = camera.latest_timestamp
            if hasattr(camera, "latest_color_frame"):
                rgb, depth = camera.latest_color_frame, camera.latest_depth_frame
                numbers = camera.latest_frame_numbers
            else:
                rgb, depth = camera.latest_frame, None
                numbers = (camera.latest_frame_number,)
        if stamp is not None and rgb is not None and (previous is None or stamp > previous):
            if getattr(camera, "use_depth", False) and depth is None:
                raise RuntimeError("Depth frame is missing")
            stale_age = time.perf_counter() - stamp
            if stale_age <= age_limit:
                # Background capture replaces buffers rather than mutating them.
                # RGB-only RealSense capture intentionally has no depth number.
                # Collection with depth enabled still requires both numbers.
                required_numbers = numbers if getattr(camera, "use_depth", False) else numbers[:1]
                if any(number is None for number in required_numbers):
                    raise RuntimeError("Camera frame numbers are unavailable")
                return rgb, depth, stamp, numbers
            # Save/verification can briefly delay capture threads. Wait for a new
            # buffer within the existing deadline; never return stale pixels.
        if time.perf_counter() >= deadline:
            if stale_age is not None and stale_age > age_limit:
                raise TimeoutError(f"Camera buffer is stale (age {stale_age:.3f}s)")
            raise TimeoutError("Camera did not produce a fresh frame")
        time.sleep(0.001)


def capture_observation(robot, previous, recording, feedback_registers=None, max_camera_age_s=None):
    obs, stamps, frame_numbers = {}, {}, {}
    deadline = time.perf_counter() + 0.2
    while True:
        for name, camera in robot.cameras.items():
            # Resample independent cameras; only wait if a buffer is too old.
            try:
                rgb, depth, stamp, numbers = camera_bundle(
                    camera, timeout_s=max(0, deadline - time.perf_counter()), max_age_s=max_camera_age_s)
            except TimeoutError as error:
                raise TimeoutError(f"{name}: {error}") from error
            obs[name] = rgb
            if depth is not None:
                obs[name + "_depth"] = depth
            stamps[name + "_capture"] = stamp
            frame_numbers[name] = numbers
        # Waiting for SIDE may have aged TOP; check the pair before motor reads.
        now = time.perf_counter()
        if max_camera_age_s is None or now - min(stamps.values()) <= max_camera_age_s:
            break
        if now >= deadline:
            raise TimeoutError("Camera pair did not refresh within 0.2s")
        time.sleep(0.001)
    if recording:
        previous.update({name: stamps[name + '_capture'] for name in robot.cameras})
    stamps["state_read_start"] = time.perf_counter()
    if recording and feedback_registers:
        snapshot = robot.bus.sync_read_registers(["Present_Position", *feedback_registers],
                                                num_retry=robot.config.num_read_retries)
        positions = snapshot["Present_Position"]
    else:
        snapshot = None
        positions = robot.bus.sync_read("Present_Position", num_retry=robot.config.num_read_retries)
    stamps["state_read_end"] = time.perf_counter()
    stamps["feedback_read_start"] = stamps["state_read_start"]
    stamps["feedback_read_end"] = stamps["state_read_end"]
    obs.update({name + ".pos": value for name, value in positions.items()})
    return obs, stamps, [*frame_numbers["top"], frame_numbers["side"][0]], snapshot


def send_control_action(robot, leader, action_processor, robot_processor, obs, timings):
    # Preserve the unprocessed leader reading even if a processor mutates its input.
    raw = dict(leader.get_action())
    processed = action_processor((dict(raw), obs))
    timings["command_send_start"] = time.perf_counter()
    sent = robot.send_action(robot_processor((processed, obs)))
    timings["command_send_end"] = time.perf_counter()
    return raw, sent


def convert_depth(raw, scale_m, np, maximum_mm=2000):
    if not np.isfinite(scale_m) or scale_m <= 0:
        raise ValueError("Invalid device depth scale")
    mm = np.rint(raw.astype(np.float64) * scale_m * 1000)
    clipped = int(np.count_nonzero(mm > maximum_mm))
    return mm.clip(0, maximum_mm).astype(np.uint16), clipped


def depth_codes(depth_mm, encoder):
    from lerobot.datasets.depth_utils import quantize_depth
    return quantize_depth(depth_mm, depth_min=encoder.depth_min, depth_max=encoder.depth_max,
                          shift=encoder.shift, use_log=encoder.use_log, input_unit="mm",
                          pix_fmt=encoder.pix_fmt, video_backend=None)


def array_hash(array):
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


class EpisodeQuality:
    def __init__(self, rig):
        self.rig = rig
        self.times = []
        self.stamps = {}
        self.repeated_camera = {"top": 0, "side": 0}
        self.skipped_source = {"top_rgb": 0, "top_depth": 0, "side": 0}
        self.repeated_source = 0
        self.code_hashes, self.mm_hashes = [], []
        self.clipped_pixels = 0
        self.max_skew_s = self.max_span_s = self.max_age_s = 0.0
        self.max_gap_s = 0.0
        self.max_camera_age_by_source = {"top": 0.0, "side": 0.0}
        self.previous_source = None
        self.stage_seconds = {"motor_snapshot": 0.0, "command_send": 0.0}

    def add(self, timings, depth_mm, encoder, np, clipped, frame_numbers):
        now = timings["frame_complete"]
        if self.times:
            self.max_gap_s = max(self.max_gap_s, now - self.times[-1])
        self.times.append(now)
        self.stage_seconds["motor_snapshot"] += timings["state_read_end"] - timings["state_read_start"]
        self.stage_seconds["command_send"] += timings["command_send_end"] - timings["command_send_start"]
        if self.previous_source is not None:
            for index, name in enumerate(self.skipped_source):
                self.skipped_source[name] += max(0, frame_numbers[index] - self.previous_source[index] - 1)
            self.repeated_source += int(any(b <= a for a, b in zip(self.previous_source, frame_numbers)))
        self.previous_source = list(frame_numbers)
        for name in self.repeated_camera:
            stamp = timings[name + "_capture"]
            if name in self.stamps:
                self.repeated_camera[name] += int(stamp <= self.stamps[name])
            self.stamps[name] = stamp
        self.max_skew_s = max(self.max_skew_s, abs(timings["top_capture"] - timings["side_capture"]))
        self.max_span_s = max(self.max_span_s, max(timings.values()) - min(timings.values()))
        self.max_age_s = max(self.max_age_s, now - min(timings["top_capture"], timings["side_capture"]))
        for name in self.max_camera_age_by_source:
            self.max_camera_age_by_source[name] = max(self.max_camera_age_by_source[name], now - timings[name + '_capture'])
        self.code_hashes.append(array_hash(depth_codes(depth_mm, encoder)))
        self.mm_hashes.append(array_hash(np.squeeze(depth_mm)))
        self.clipped_pixels += clipped

    def summary(self, dropped=0):
        count = len(self.times)
        duration = self.times[-1] - self.times[0] if count > 1 else 0
        actual_fps = (count - 1) / duration if duration > 0 else 0
        return {"target_fps": self.rig["fps"], "actual_fps": actual_fps,
                "numeric_frames": count, "dropped_frames": dropped,
                "repeated_camera_frames": dict(self.repeated_camera), "max_camera_skew_s": self.max_skew_s,
                "skipped_source_frames": dict(self.skipped_source), "repeated_source_frames": self.repeated_source,
                "max_sample_span_s": self.max_span_s, "max_camera_age_s": self.max_age_s,
                "max_camera_age_by_source_s": dict(self.max_camera_age_by_source),
                "max_frame_gap_s": self.max_gap_s, "depth_clipped_pixels": self.clipped_pixels,
                "mean_stage_ms": {name: seconds * 1000 / count if count else 0
                                  for name, seconds in self.stage_seconds.items()},
                "camera_resampling": "latest_available_on_control_clock"}

    def errors(self, dropped=0, final=False):
        report = self.summary(dropped)
        errors = []
        if dropped:
            errors.append("Dropped or repeated frames")
        # Repeated/skipped camera source frames are expected when resampling independent rates.
        # Stale images, frame-count mismatches, encoder drops and timing limits remain fatal.
        if self.max_gap_s > self.rig["max_frame_gap_s"]:
            errors.append("Capture frame gap exceeds threshold")
        duration = self.times[-1] - self.times[0] if len(self.times) > 1 else 0
        if (final or duration >= self.rig["min_episode_seconds"]) and report["actual_fps"] < self.rig["min_effective_fps"]:
            errors.append("Actual FPS below threshold")
        for value, limit, label in (
            (self.max_skew_s, "max_camera_skew_s", "Camera skew"),
            (self.max_span_s, "max_sample_span_s", "Sample time span"),
            (self.max_age_s, "max_camera_age_s", "Camera age"),
        ):
            if value > self.rig[limit]:
                errors.append(label + " exceeds threshold")
        return errors


def sample_indices(count, limit):
    """Evenly spaced samples, including the first and last frame."""
    if limit < 2:
        raise ValueError("Video samples must be at least 2")
    if count <= limit:
        return list(range(count))
    return sorted({round(index * (count - 1) / (limit - 1)) for index in range(limit)})


def video_sample_check(av, path, start, end, fps, limit, inspect, checkpoint=None):
    """Count all timestamped video packets, decode only selected frames.

    Collected H.264/HEVC MP4 stores one frame per packet. This checks packet
    presence and sampled decodability, not the integrity of every frame payload.
    """
    indices = sample_indices(end - start, limit)
    # Dense sampling is cheaper with one sequential decode than hundreds of seeks.
    if len(indices) >= (end - start) / 4:
        chosen = set(indices)
        count = 0
        with av.open(str(path)) as container:
            container.streams.video[0].thread_count = 4
            for absolute, frame in enumerate(container.decode(video=0)):
                if checkpoint:
                    checkpoint()
                if absolute < start:
                    continue
                if absolute >= end:
                    break
                if count in chosen:
                    inspect(count, frame)
                count += 1
        if count != end - start:
            raise RuntimeError('Video decoded frame count mismatch')
        return count, indices
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        frame_numbers = [round(float(packet.pts * stream.time_base) * fps)
                         for packet in container.demux(stream) if packet.pts is not None and packet.size]
    actual = sorted(index for index in frame_numbers if start <= index < end)
    if actual != list(range(start, end)):
        raise RuntimeError("Video packet frame sequence mismatch")
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_count = 2
        for index in indices:
            if checkpoint:
                checkpoint()
            target = start + index
            # HEVC's reordered B frames can precede the selected keyframe's
            # presentation time. Seek earlier so the desired frame is retained.
            seek_frame = max(0, target - 8)
            container.seek(round(seek_frame / fps / stream.time_base), stream=stream, backward=True)
            found = False
            for frame in container.decode(stream):
                number = round(float(frame.pts * frame.time_base) * fps)
                if number < target:
                    continue
                if number != target:
                    break
                inspect(index, frame)
                found = True
                break
            if not found:
                # A valid reordered GOP may still seek past the target. Confirm
                # from the beginning before declaring corruption and rolling back.
                container.seek(0, stream=stream, backward=True)
                for frame in container.decode(stream):
                    if checkpoint:
                        checkpoint()
                    number = round(float(frame.pts * frame.time_base) * fps)
                    if number == target:
                        inspect(index, frame)
                        found = True
                        break
                    if number > target:
                        break
                if not found:
                    raise RuntimeError(f"Video sample could not decode at frame {index}")
    return len(actual), indices


def verify_encoded_episode(m, root, episode_index, quality, encoder, dropped=0, video_samples=None, checkpoint=None):
    """Validate numerics plus full decoding or packet counts and sampled video/depth."""
    from lerobot.datasets.depth_utils import dequantize_depth
    metadata_columns = ['episode_index', 'length', 'tasks', 'data/chunk_index', 'data/file_index']
    metadata_columns += [f'videos/observation.images.{camera}/{field}'
                         for camera in ('top', 'side', 'top_depth')
                         for field in ('chunk_index', 'file_index', 'from_timestamp', 'to_timestamp')]
    rows = m.pq.read_table(sorted(root.glob('meta/episodes/chunk-*/file-*.parquet')),
                          columns=metadata_columns).to_pylist()
    episode = next(row for row in rows if row["episode_index"] == episode_index)
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
    columns = ["episode_index", "frame_index", "index", "timestamp", "task_index"]
    numerical = [key for key, feature in info["features"].items()
                 if key in ("action", "observation.state") or key.startswith("research.")]
    data_path = root / 'data' / f"chunk-{int(episode['data/chunk_index']):03d}" / f"file-{int(episode['data/file_index']):03d}.parquet"
    frames = m.pq.read_table(data_path,
                             columns=columns + numerical,
                             filters=[("episode_index", "=", episode_index)])
    numeric_count = len(frames)
    report = quality.summary(dropped)
    report["numeric_frames"] = int(numeric_count)
    errors = quality.errors(dropped, final=True)
    expected = len(quality.times)
    if numeric_count != expected or episode["length"] != expected:
        errors.append("Numeric frame count mismatch")
    if info["total_episodes"] != len(rows) or [int(row["episode_index"]) for row in rows] != list(range(len(rows))):
        errors.append("Episode metadata sequence mismatch")
    if sum(int(row["length"]) for row in rows) != info["total_frames"]:
        errors.append("Dataset total frame count mismatch")
    offset = sum(int(row["length"]) for row in rows if row["episode_index"] < episode_index)
    if not m.np.array_equal(frames["frame_index"].to_numpy(), m.np.arange(expected)):
        errors.append("Frame index mismatch")
    if not m.np.array_equal(frames["index"].to_numpy(), m.np.arange(offset, offset + expected)):
        errors.append("Global frame index mismatch")
    if numeric_count != expected or not m.np.allclose(frames["timestamp"].to_numpy(), m.np.arange(expected) / info["fps"], atol=1e-4):
        errors.append("Timestamp mismatch")
    tasks = m.pq.read_table(root / "meta/tasks.parquet").to_pandas()
    mapping = dict(zip(tasks.index, tasks["task_index"]))
    names = list(episode["tasks"])
    if len(names) != 1 or names[0] not in mapping or not m.np.all(frames["task_index"].to_numpy() == mapping[names[0]]):
        errors.append("Task index mismatch")
    for key in numerical:
        values = m.np.asarray(frames[key].to_pylist())
        shape = info["features"][key]["shape"]
        valid_shapes = [(expected, *shape)]
        if shape == [1]:  # LeRobot serializes single-element numerical features as scalars.
            valid_shapes.append((expected,))
        if values.shape not in valid_shapes or not m.np.isfinite(values).all():
            errors.append(key + ": non-finite or malformed numeric data")
    # Reuse the exact decoder conversion for all 12-bit codes rather than allocate float images per frame.
    depth_lut = m.np.squeeze(dequantize_depth(m.np.arange(4096, dtype=m.np.uint16).reshape(1, -1),
                            depth_min=encoder.depth_min, depth_max=encoder.depth_max,
                            shift=encoder.shift, use_log=encoder.use_log,
                            output_tensor=False, output_unit="mm"))

    def verify_video(key, label):
        video_errors = []
        max_error_mm = 0
        video_key = "observation.images." + key
        prefix = "videos/" + video_key + "/"
        path = root / "videos" / video_key / f"chunk-{int(episode[prefix + 'chunk_index']):03d}" / f"file-{int(episode[prefix + 'file_index']):03d}.mp4"
        start = int(round(episode[prefix + "from_timestamp"] * quality.rig["fps"]))
        end = int(round(episode[prefix + "to_timestamp"] * quality.rig["fps"]))
        count = 0
        def inspect(index, frame):
            nonlocal max_error_mm
            if key == "top_depth":
                codes = frame.to_ndarray(format=encoder.pix_fmt)
                if index >= expected or array_hash(codes) != quality.code_hashes[index]:
                    video_errors.append(f"Depth code mismatch at frame {index}")
                mm = depth_lut[codes]
                if index >= expected or array_hash(m.np.squeeze(mm)) != quality.mm_hashes[index]:
                    video_errors.append(f"Depth mm roundtrip mismatch at frame {index}")
                    max_error_mm = None
        if video_samples is not None:
            count, _ = video_sample_check(m.av, path, start, end, quality.rig['fps'], video_samples, inspect, checkpoint)
            if count != expected or end - start != expected:
                video_errors.append(label + " count mismatch")
            return label, count, video_errors, max_error_mm
        with m.av.open(str(path)) as container:
            # Bound per-stream decoding so the three checks can share the CPU.
            container.streams.video[0].thread_type = "AUTO"
            container.streams.video[0].thread_count = 4
            for index, frame in enumerate(container.decode(video=0)):
                if checkpoint:
                    checkpoint()
                if index < start:
                    continue
                if index >= end:
                    break
                inspect(count, frame)
                count += 1
        if count != expected or end - start != expected:
            video_errors.append(label + " count mismatch")
        return label, count, video_errors, max_error_mm

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda pair: verify_video(*pair),
                               [("top", "top_rgb_frames"), ("top_depth", "top_depth_frames"), ("side", "side_rgb_frames")]))
    max_error_mm = 0
    for label, count, video_errors, depth_error in results:
        report[label] = count
        errors.extend(video_errors)
        if depth_error is None:
            max_error_mm = None
    report.update(depth_codes_lossless=not any("Depth code" in error for error in errors),
                  depth_mm_exact=not any("Depth mm" in error for error in errors),
                  depth_max_error_mm=max_error_mm)
    report['video_verification_mode'] = 'full' if video_samples is None else 'sampled'
    if video_samples is not None:
        checked = sample_indices(expected, video_samples)
        report.update(video_sample_indices=checked, depth_frames_checked=len(checked),
                      full_depth_verified=len(checked) == expected,
                      video_frame_count_method='packet_timestamps',
                      depth_samples_codes_match=report['depth_codes_lossless'],
                      depth_samples_mm_match=report['depth_mm_exact'])
        if len(checked) < expected:
            report.update(depth_codes_lossless=None, depth_mm_exact=None, depth_max_error_mm=None)
    return report, errors
