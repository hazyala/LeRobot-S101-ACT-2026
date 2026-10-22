import json
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core as common
import core as recovery


class CollectionTests(unittest.TestCase):
    def test_d405_model_name_accepts_sdk_labels_but_rejects_other_models(self):
        for name in ('Intel RealSense D405', 'Intel RealSense D405I', 'Intel RealSense D455',
                     'Intel RealSense D4050', 'Intel RealSense D435', ''):
            with self.subTest(name=name):
                if name == 'Intel RealSense D405':
                    common.validate_top_camera_name(name)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'detected'):
                        common.validate_top_camera_name(name)
        for name in ('Intel RealSense (TM) D405', 'RealSense D405', 'Intel RealSense D405 Camera'):
            with self.subTest(name=name):
                common.validate_top_camera_name(name)

    def test_recovery_cancel_preserves_original_and_pending_journal(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, 'STORE', Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / 'meta/info.json', {'total_episodes': 1})
            common.atomic_json(root.parent / 'pending_episode.json', {'episode': 1})
            with self.assertRaises(common.RecoveryCancelled):
                common.recover(task, cancelled=lambda: True)
            self.assertTrue((root / 'meta/info.json').exists())
            self.assertTrue((root.parent / 'pending_episode.json').exists())

    def test_exact_task_sentences_and_order(self):
        self.assertEqual([t["instruction"] for t in common.registry()], [
            "Pick up the doll and place it in the container.",
            "Pick up the paper cup and place it in the container.",
            "Sort the doll and the paper cup into their containers.",
            "Stack two boxes.", "Stack three boxes.", "Stack four boxes."])
        self.assertEqual(common.task_for("5"), common.task_for("stack_four"))
        with self.assertRaises(ValueError):
            common.task_for("../../outside")

    def test_atomic_json_replaces_complete_content(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "journal.json"
            common.atomic_json(path, {"stage": "recording"})
            common.atomic_json(path, {"stage": "saving", "한국어": True})
            self.assertEqual(common.read_json(path)["stage"], "saving")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_same_resource_cannot_be_opened_twice(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rig.lock"
            with common.exclusive(path):
                with self.assertRaises((RuntimeError, BlockingIOError)):
                    with common.exclusive(path):
                        pass
            with common.exclusive(path):
                pass

    def test_pending_episode_blocks_resume(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            common.atomic_json(common.task_dir(task) / "pending_episode.json", {"status": "saving"})
            with self.assertRaisesRegex(RuntimeError, "Unfinished"):
                common.pending_guard(task)

    def test_changed_calibration_cannot_mix_into_dataset(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            with patch.object(common, "fingerprint", return_value={"calibration": "A"}):
                common.ensure_manifest(task)
            with patch.object(common, "fingerprint", return_value={"calibration": "B"}):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    common.ensure_manifest(task)

    def test_clean_empty_dataset_can_upgrade_manifest_without_deleting_records(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 0, "total_frames": 0})
            manifest = root.parent / "collection_manifest.json"
            common.atomic_json(manifest, {"schema_version": 3})
            common.atomic_json(root.parent / "sessions/rejected.json", {"status": "discarded"})
            with patch.object(common, "fingerprint", return_value={"schema_version": 4}):
                common.ensure_manifest(task)
            self.assertEqual(common.read_json(manifest), {"schema_version": 4})
            self.assertTrue((root.parent / "sessions/rejected.json").exists())
            self.assertEqual(len(list((root.parent / "sessions").glob("previous_manifest_*.json"))), 1)

    def test_quality_limit_change_keeps_saved_dataset_resumable(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 4, "total_frames": 1200})
            previous = {"schema_version": 4, "rig": {"fps": 30, "max_camera_skew_s": 0.05}}
            expected = {"schema_version": 4, "rig": {"fps": 30, "max_camera_skew_s": 0.1}}
            common.atomic_json(root.parent / "collection_manifest.json", previous)
            with patch.object(common, "fingerprint", return_value=expected):
                common.ensure_manifest(task)
            self.assertEqual(common.read_json(root / "meta/info.json")["total_episodes"], 4)
            self.assertEqual(common.read_json(root.parent / "collection_manifest.json"), expected)

    def test_recovery_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                recovery.safe_child(Path(d), "../../outside")

    def test_d405_replacement_preserves_history_and_rejects_incompatible_changes(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, 'STORE', Path(d)):
            task = common.task_for(0)
            old = common.fingerprint(task, depth_scale=0.0001)
            old['rig']['top_serial'] = 'old-device'
            old['legacy_collector_sha256'] = 'daa496e3306276cb091eccb0029074b5ea0f3803c6c1c1be42e5fb71457f5753'
            new = common.fingerprint(task, depth_scale=0.0001)
            manifest = common.task_dir(task) / 'collection_manifest.json'
            common.atomic_json(manifest, old)
            with patch.object(common, 'fingerprint', return_value=new):
                common.ensure_manifest(task)
            backups = list((manifest.parent / 'sessions').glob('previous_manifest_*.json'))
            self.assertEqual(common.read_json(backups[0]), old)
            self.assertEqual(common.read_json(manifest), new)
            for field in ('fps', 'width', 'top_exposure'):
                changed = copy.deepcopy(new)
                changed['rig']['top_serial'] = 'another-device'
                changed['rig'][field] += 1
                with self.subTest(field=field), patch.object(common, 'fingerprint', return_value=changed):
                    with self.assertRaisesRegex(RuntimeError, 'changed'):
                        common.ensure_manifest(task)
            for field, value in [('calibration_sha256', {}), ('legacy_collector_sha256', 'unknown'),
                                 ('depth', {**new['depth'], 'depth_scale_m_per_unit': 0.001})]:
                changed = copy.deepcopy(new)
                changed['rig']['top_serial'] = 'another-device'
                changed[field] = value
                with self.subTest(field=field), patch.object(common, 'fingerprint', return_value=changed):
                    with self.assertRaisesRegex(RuntimeError, 'changed'):
                        common.ensure_manifest(task)

    def test_completed_save_with_pending_quality_is_rolled_back(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 1})
            (root / "data").mkdir()
            (root / "data/file.parquet").write_bytes(b"accepted")
            recovery.snapshot(task)
            common.atomic_json(root.parent / "pending_episode.json",
                               {"episode": 1, "quality_pending": True})
            common.atomic_json(root / "meta/info.json", {"total_episodes": 2})
            (root / "data/file.parquet").write_bytes(b"unverified")
            with patch("core.require_valid"), patch("core.shutil.disk_usage") as disk:
                disk.return_value.free = 10**12
                recovery.recover(task)
            self.assertEqual(common.read_json(root / "meta/info.json")["total_episodes"], 1)
            self.assertEqual((root / "data/file.parquet").read_bytes(), b"accepted")
            self.assertFalse((root.parent / "pending_episode.json").exists())

    def test_snapshot_preserves_previous_video_and_numerical_metadata(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 1})
            (root / "data").mkdir()
            (root / "data/file.parquet").write_bytes(b"committed")
            for index in range(2):
                p = root / f"videos/top/chunk-000/file-{index:03d}.mp4"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"video" + bytes([index]))
            recovery.snapshot(task)
            backup = common.task_dir(task) / "recovery_snapshot"
            (root / "videos/top/chunk-000/file-001.mp4").write_bytes(b"damaged")
            self.assertEqual((backup / "videos/top/chunk-000/file-001.mp4").read_bytes(), b"video\x01")
            self.assertEqual((backup / "data/file.parquet").read_bytes(), b"committed")
            self.assertEqual(len(common.read_json(backup / "snapshot.json")["videos"]), 2)

    def test_recovery_retains_interrupted_original(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 1})
            (root / "data").mkdir()
            (root / "data/file.parquet").write_bytes(b"saved")
            recovery.snapshot(task)
            common.atomic_json(common.task_dir(task) / "pending_episode.json", {"episode": 1})
            common.atomic_json(root / "meta/info.json", {"total_episodes": 2})
            (root / "data/file.parquet").write_bytes(b"interrupted")
            def verify(**kwargs):
                if "root" not in kwargs:
                    raise RuntimeError("Simulated partial save")
            with patch("core.require_valid", side_effect=verify), patch("core.shutil.disk_usage") as disk:
                disk.return_value.free = 10**12
                recovery.recover(task)
            self.assertEqual((root / "data/file.parquet").read_bytes(), b"saved")
            quarantined = list(common.task_dir(task).glob("interrupted_*"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual((quarantined[0] / "data/file.parquet").read_bytes(), b"interrupted")
            self.assertFalse((common.task_dir(task) / "pending_episode.json").exists())

    def test_failed_recovery_validation_does_not_replace_original(self):
        with tempfile.TemporaryDirectory() as d, patch.object(common, "STORE", Path(d)):
            task = common.task_for(0)
            root = common.data_root(task)
            common.atomic_json(root / "meta/info.json", {"total_episodes": 1})
            (root / "data").mkdir()
            recovery.snapshot(task)
            common.atomic_json(common.task_dir(task) / "pending_episode.json", {"episode": 1})
            with patch("core.require_valid", side_effect=RuntimeError("invalid")), patch("core.shutil.disk_usage") as disk:
                disk.return_value.free = 10**12
                with self.assertRaisesRegex(RuntimeError, "invalid"):
                    recovery.recover(task)
            self.assertTrue(root.exists())
            self.assertTrue((common.task_dir(task) / "pending_episode.json").exists())

    def test_invalid_rig_fails_before_connection(self):
        rig = common.rig_config()
        rig["fps"] = 60
        with patch.object(common, "read_json", return_value={"rig": rig}):
            with self.assertRaises(ValueError):
                common.rig_config()


if __name__ == "__main__":
    unittest.main()
