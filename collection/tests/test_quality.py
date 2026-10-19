import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import load_engine, rig_config
from quality import (TIMING_NAMES, EpisodeQuality, camera_bundle, convert_depth,
                     research_features, send_control_action, verify_encoded_episode)


class QualityTests(unittest.TestCase):
    def test_capture_clock_does_not_accumulate_sleep_overshoot(self):
        from core import wait_capture_tick
        with patch('core.time.perf_counter', side_effect=[0.01, 0.045]), patch('core.time.sleep') as sleep:
            deadline = wait_capture_tick(0, 1 / 30)
            deadline = wait_capture_tick(deadline, 1 / 30)
        self.assertAlmostEqual(deadline, 2 / 30)
        self.assertAlmostEqual(sleep.call_args_list[1].args[0], 2 / 30 - 0.045)

    def test_capture_clock_does_not_catch_up_after_long_stall(self):
        from core import wait_capture_tick
        with patch('core.time.perf_counter', return_value=0.3), patch('core.time.sleep') as sleep:
            self.assertEqual(wait_capture_tick(0, 1 / 30), 0.3)
        sleep.assert_not_called()

    def test_camera_refreshes_before_quality_age_limit_not_timeout(self):
        camera = SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(),
                                 latest_timestamp=9.89, latest_frame=np.zeros((2, 2, 3)),
                                 latest_frame_number=1)
        def refresh(_):
            camera.latest_timestamp = 10.01
            camera.latest_frame_number = 2
        with patch('quality.time.perf_counter', side_effect=[10, 10, 10, 10.02]), \
                patch('quality.time.sleep', side_effect=refresh) as wait:
            _, _, stamp, numbers = camera_bundle(camera, max_age_s=0.08)
        wait.assert_called_once()
        self.assertEqual((stamp, numbers), (10.01, (2,)))

    def test_fifty_samples_cover_whole_episode_without_duplicates(self):
        from quality import sample_indices
        chosen = sample_indices(659, 50)
        self.assertEqual(len(chosen), 50)
        self.assertEqual((chosen[0], chosen[-1]), (0, 658))
        self.assertEqual(len(set(chosen)), 50)
        self.assertLessEqual(max(b - a for a, b in zip(chosen, chosen[1:])), 14)
        self.assertEqual(sample_indices(20, 50), list(range(20)))
    def test_stale_buffer_waits_for_capture_thread_to_refresh(self):
        camera = SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(),
                                 latest_timestamp=9.0, latest_frame=np.zeros((2, 2, 3)),
                                 latest_frame_number=1)
        def refresh(_):
            with camera.frame_lock:
                camera.latest_timestamp = 10.01
                camera.latest_frame_number = 2
        with patch('quality.time.perf_counter', side_effect=[10, 10, 10, 10.02]), \
                patch('quality.time.sleep', side_effect=refresh) as wait:
            _, _, stamp, numbers = camera_bundle(camera)
        wait.assert_called_once()
        self.assertEqual(stamp, 10.01)
        self.assertEqual(numbers, (2,))

    def test_permanently_stale_buffer_still_times_out(self):
        camera = SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(),
                                 latest_timestamp=9.0, latest_frame=np.zeros((2, 2, 3)),
                                 latest_frame_number=1)
        with patch('quality.time.perf_counter', side_effect=[10, 10.01, 10.21]):
            with self.assertRaisesRegex(TimeoutError, 'buffer is stale'):
                camera_bundle(camera)

    def test_final_command_and_original_leader_are_distinct(self):
        leader = Mock()
        leader.get_action.return_value = {"gripper.pos": 80.0}
        robot = Mock()
        robot.send_action.side_effect = lambda action: {"gripper.pos": min(action["gripper.pos"], 15.0)}
        def mutate_processor(pair):
            pair[0]["gripper.pos"] = 90.0
            return pair[0]
        timings = {}
        raw, sent = send_control_action(robot, leader, mutate_processor, lambda pair: pair[0], {}, timings)
        self.assertEqual(raw, {"gripper.pos": 80.0})
        self.assertEqual(sent, {"gripper.pos": 15.0})
        self.assertLessEqual(timings["command_send_start"], timings["command_send_end"])

    def test_atomic_rgb_depth_bundle_and_freshness(self):
        camera = SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(),
                                 latest_timestamp=time.perf_counter(), latest_color_frame=np.full((2, 2, 3), 7),
                                 latest_depth_frame=np.full((2, 2, 1), 77), latest_frame_numbers=(7, 7), use_depth=True)
        rgb, depth, stamp, numbers = camera_bundle(camera)
        self.assertEqual(rgb[0, 0, 0], 7)
        self.assertEqual(depth[0, 0, 0], 77)
        self.assertEqual(numbers, (7, 7))
        with self.assertRaises(TimeoutError):
            camera_bundle(camera, stamp, timeout_s=0.005)

    def test_device_scale_conversion_and_range(self):
        mm, clipped = convert_depth(np.array([0, 10, 8001], dtype=np.uint16), 0.00025, np)
        np.testing.assert_array_equal(mm, [0, 2, 2000])
        self.assertEqual(clipped, 0)  # 2000.25 mm rounds into the valid mm range.
        _, clipped = convert_depth(np.array([9000], dtype=np.uint16), 0.00025, np)
        self.assertEqual(clipped, 1)
        with self.assertRaises(ValueError):
            convert_depth(np.array([1]), 0, np)

    def test_time_quality_detects_repeats_skew_and_low_fps(self):
        from lerobot.configs import DepthEncoderConfig
        quality = EpisodeQuality(rig_config())
        encoder = DepthEncoderConfig(depth_min=0, depth_max=2, use_log=False)
        for t in [10, 11]:
            timings = dict.fromkeys(TIMING_NAMES, t)
            timings["top_capture"] = 9
            quality.add(timings, np.zeros((2, 2, 1), dtype=np.uint16), encoder, np, 0, [int(t)] * 3)
        errors = quality.errors(final=True)
        self.assertNotIn("Dropped or repeated frames", errors)
        self.assertIn("Actual FPS below threshold", errors)
        self.assertIn("Camera skew exceeds threshold", errors)

    def test_camera_resampling_does_not_reject_matching_saved_counts(self):
        from lerobot.configs import DepthEncoderConfig
        quality = EpisodeQuality(rig_config())
        encoder = DepthEncoderConfig(depth_min=0, depth_max=2, use_log=False)
        for index, number in enumerate([100, 102]):
            quality.add(dict.fromkeys(TIMING_NAMES, index / 30), np.zeros((2, 2, 1), dtype=np.uint16),
                        encoder, np, 0, [number, number, index])
        self.assertEqual(quality.summary()["skipped_source_frames"]["top_depth"], 1)
        self.assertEqual(quality.errors(final=True), [])

    def test_slow_side_camera_does_not_gate_control_clock(self):
        from quality import capture_observation
        stamp = time.perf_counter()
        cameras = {
            "top": SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(), latest_timestamp=stamp,
                                   latest_color_frame=np.zeros((2, 2, 3)), latest_depth_frame=np.zeros((2, 2, 1)),
                                   latest_frame_numbers=(1, 1), use_depth=True),
            "side": SimpleNamespace(thread=Mock(), frame_lock=threading.Lock(), latest_timestamp=stamp,
                                    latest_frame=np.zeros((2, 2, 3)), latest_frame_number=1),
        }
        bus = Mock()
        bus.sync_read_registers.return_value = {"Present_Position": {"gripper": 10}, "Present_Load": {"gripper": -3}}
        robot = SimpleNamespace(cameras=cameras, bus=bus, config=SimpleNamespace(num_read_retries=2))
        previous = {"top": stamp, "side": stamp}
        obs, timings, numbers, snapshot = capture_observation(robot, previous, True, ["Present_Load"])
        self.assertEqual(numbers, [1, 1, 1])
        self.assertEqual(obs["gripper.pos"], 10)
        self.assertEqual(snapshot["Present_Load"]["gripper"], -3)
        self.assertEqual(timings["feedback_read_end"], timings["state_read_end"])
        bus.sync_read.assert_not_called()
        bus.sync_read_registers.assert_called_once_with(["Present_Position", "Present_Load"], num_retry=2)

    def test_waiting_for_side_rechecks_top_age(self):
        from quality import capture_observation
        rgb = np.zeros((2, 2, 3))
        bus = Mock()
        bus.sync_read.return_value = {"gripper": 10}
        robot = SimpleNamespace(cameras={"top": Mock(), "side": Mock()}, bus=bus,
                                config=SimpleNamespace(num_read_retries=2))
        bundles = [(rgb, None, 10.0, (1, 1)), (rgb, None, 10.09, (2,)),
                   (rgb, None, 10.10, (3, 3)), (rgb, None, 10.10, (4,))]
        clock = [10, 10, 10, 10.09, 10.09, 10.09, 10.09, 10.10, 10.10, 10.10]
        with patch('quality.camera_bundle', side_effect=bundles) as bundle, \
                patch('quality.time.perf_counter', side_effect=clock), patch('quality.time.sleep'):
            _, timings, numbers, _ = capture_observation(robot, {}, False, max_camera_age_s=0.08)
        self.assertEqual(bundle.call_count, 4)
        self.assertEqual(numbers, [3, 3, 4])
        self.assertEqual(timings['top_capture'], 10.10)

    def test_real_hevc_depth_roundtrip_and_episode_segment_counts(self):
        m = load_engine()
        # This 64x48 depth fixture is smaller than NVENC's supported size.
        m.RGB_ENCODER = m.RGBEncoderConfig(vcodec="libx264rgb", pix_fmt="rgb24", crf=0, preset="ultrafast")
        m.DEPTH_ENCODER.use_log = False
        features = {
            "action": {"dtype": "float32", "shape": (1,), "names": ["gripper.pos"]},
            "observation.state": {"dtype": "float32", "shape": (1,), "names": ["gripper.pos"]},
            **research_features(["gripper"]),
        }
        for key, channels in [("top", 3), ("side", 3), ("top_depth", 1)]:
            features["observation.images." + key] = {
                "dtype": "video", "shape": (48, 64, channels), "names": ["height", "width", "channels"],
                "info": {"is_depth_map": channels == 1}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "dataset"
            m.DATASET_ROOT = root
            dataset = m.LeRobotDataset.create("local/quality_test", 30, root=root, features=features,
                                             use_videos=True, video_files_size_in_mb=10,
                                             streaming_encoding=True, rgb_encoder=m.RGB_ENCODER,
                                             depth_encoder=m.DEPTH_ENCODER)
            qualities = []
            try:
                for episode in range(2):
                    streaming = dataset.writer._streaming_encoder
                    streaming.start_episode(
                        video_keys=list(dataset.meta.video_keys), depth_video_keys=list(dataset.meta.depth_keys),
                        temp_dir=root, frame_shapes={key: features[key]['shape'] for key in dataset.meta.video_keys})
                    prepared_threads = dict(streaming._threads)
                    quality = EpisodeQuality(rig_config())
                    qualities.append(quality)
                    for index in range(4):
                        # Cover every integer mm value in the stored range, including invalid zero.
                        depth = np.roll(np.resize(np.arange(2001, dtype=np.uint16), (48, 64, 1)),
                                        index + episode * 7, axis=1)
                        timings = dict.fromkeys(TIMING_NAMES, episode + index / 30)
                        quality.add(timings, depth, m.DEPTH_ENCODER, np, 0, [index] * 3)
                        frame = {"action": np.array([15], dtype=np.float32),
                                 "observation.state": np.array([10], dtype=np.float32),
                                 "research.leader_action_raw": np.array([80], dtype=np.float32),
                                 "research.capture_timing_s": np.zeros(len(TIMING_NAMES), dtype=np.float32),
                                 "research.camera_frame_numbers": np.array([index] * 3, dtype=np.int64),
                                 "observation.images.top": np.zeros((48, 64, 3), dtype=np.uint8),
                                 "observation.images.side": np.zeros((48, 64, 3), dtype=np.uint8),
                                 "observation.images.top_depth": depth, "task": "test"}
                        dataset.add_frame(frame)
                        self.assertEqual(prepared_threads, streaming._threads)
                    dataset.save_episode()
                    dataset.checkpoint_recording()
                    # Committed footers must be readable before the next episode.
                    saved_rows = m.pq.read_table(sorted(root.glob('data/chunk-*/file-*.parquet')))
                    self.assertEqual(len(saved_rows), (episode + 1) * 4)
            finally:
                dataset.finalize()
            for episode, quality in enumerate(qualities):
                report, errors = verify_encoded_episode(m, root, episode, quality, m.DEPTH_ENCODER)
                self.assertEqual(errors, [])
                self.assertEqual([report[key] for key in ("numeric_frames", "top_rgb_frames", "top_depth_frames", "side_rgb_frames")], [4] * 4)
                self.assertTrue(report["depth_codes_lossless"])
                self.assertTrue(report["depth_mm_exact"])
                sampled, sampled_errors = verify_encoded_episode(
                    m, root, episode, quality, m.DEPTH_ENCODER, video_samples=2)
                self.assertEqual(sampled_errors, [])
                self.assertEqual(sampled['video_sample_indices'], [0, 3])
                self.assertIsNone(sampled['depth_codes_lossless'])
                self.assertFalse(sampled['full_depth_verified'])
                self.assertTrue(sampled['depth_samples_mm_match'])
            import core
            for episode, quality in enumerate(qualities):
                core.atomic_json(root.parent / 'verification_pending' / f'episode_{episode:06d}.json', {
                    'episode': episode, 'frames': len(quality.times), 'rig': quality.rig,
                    'code_hashes': quality.code_hashes, 'mm_hashes': quality.mm_hashes})
                core.atomic_json(root.parent / 'sessions' / f'episode_{episode:06d}.json', {
                    'status': 'saved', 'quality': quality.summary(), 'full_verification_pending': True})
            audit_task = core.task_for(0)
            with patch.object(core, 'task_dir', return_value=root.parent), \
                    patch.object(core, 'data_root', return_value=root), \
                    patch.object(core, 'load_engine', return_value=m), \
                    patch.object(core, 'read_json', side_effect=lambda path: (
                        {'verification': {'exit_check_fraction': 1}} if Path(path) == core.BASE / 'settings.json'
                        else __import__('json').loads(Path(path).read_text(encoding='utf-8')))):
                core.verify_pending_episodes(audit_task)
            self.assertFalse(core.read_json(root.parent / 'sessions/episode_000001.json')['full_verification_pending'])
            self.assertTrue(core.read_json(root.parent / 'sessions/episode_000001.json')['quality']['full_depth_verified'])
            from lerobot.utils.feature_utils import dataset_to_policy_features
            self.assertFalse(any(key.startswith("research.") for key in dataset_to_policy_features(features)))
            rows = m.pq.read_table(sorted(root.glob("data/chunk-*/file-*.parquet"))).to_pydict()
            self.assertEqual(np.atleast_1d(rows["action"][0]).tolist(), [15.0])
            self.assertEqual(np.atleast_1d(rows["research.leader_action_raw"][0]).tolist(), [80.0])
            _, errors = verify_encoded_episode(m, root, 0, qualities[0], m.DEPTH_ENCODER, dropped=1)
            self.assertIn("Dropped or repeated frames", errors)
            qualities[1].code_hashes[0] = "corrupt"
            _, errors = verify_encoded_episode(m, root, 1, qualities[1], m.DEPTH_ENCODER)
            self.assertIn("Depth code mismatch at frame 0", errors)
            # Corruption of new numerical rows must still fail without rescanning history.
            import pyarrow as pa
            episode_row = next(row for row in m.pq.read_table(sorted(root.glob("meta/episodes/chunk-*/file-*.parquet"))).to_pylist()
                               if row['episode_index'] == 1)
            path = root / 'data' / f"chunk-{episode_row['data/chunk_index']:03d}" / f"file-{episode_row['data/file_index']:03d}.parquet"
            table = m.pq.read_table(path)
            values = table["action"].to_pylist()
            values[-1] = float("nan")
            field = table.schema.field("action")
            table = table.set_column(table.schema.get_field_index("action"), field, pa.array(values, type=field.type))
            m.pq.write_table(table, path)
            _, errors = verify_encoded_episode(m, root, 1, qualities[1], m.DEPTH_ENCODER)
            self.assertIn("action: non-finite or malformed numeric data", errors)


if __name__ == "__main__":
    unittest.main()
