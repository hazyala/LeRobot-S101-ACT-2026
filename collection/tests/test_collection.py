import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core as common
import core as recovery


class CollectionTests(unittest.TestCase):
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

    def test_recovery_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                recovery.safe_child(Path(d), "../../outside")

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
