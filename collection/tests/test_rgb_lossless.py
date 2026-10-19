import sys
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from migrate_rgb_lossless import convert, signature, rollback, core


class LosslessRGBTests(unittest.TestCase):
    def test_lossless_backend_change_keeps_same_dataset_but_rejects_lossy_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STORE', Path(directory)):
            task = core.task_for(0)
            old = {'rig': {}, 'rgb_encoder': {'vcodec': 'libx264rgb', 'pix_fmt': 'rgb24', 'crf': 0}}
            new = {'rig': {}, 'rgb_encoder': {'vcodec': 'h264_nvenc', 'pix_fmt': 'gbrp',
                                            'crf': None, 'extra_options': {'tune': 'lossless'}}}
            manifest = core.task_dir(task) / 'collection_manifest.json'
            core.atomic_json(manifest, old)
            core.atomic_json(core.data_root(task) / 'meta/info.json', {
                'total_episodes': 1, 'total_frames': 1,
                'features': {key: {'info': {'video.codec': 'h264', 'video.pix_fmt': 'gbrp'}}
                             for key in ['observation.images.top', 'observation.images.side']}})
            with patch.object(core, 'fingerprint', return_value=new):
                core.ensure_manifest(task)
            self.assertEqual(core.read_json(manifest), new)
            lossy = {**new, 'rgb_encoder': {**new['rgb_encoder'], 'crf': 20}}
            with patch.object(core, 'fingerprint', return_value=lossy):
                with self.assertRaisesRegex(RuntimeError, 'changed'):
                    core.ensure_manifest(task)

    def test_nvenc_lossless_options_survive_metadata_reload(self):
        from lerobot.configs import RGBEncoderConfig
        restored = RGBEncoderConfig.from_video_info({
            'video.codec': 'h264', 'video.pix_fmt': 'gbrp', 'video.preset': 'p1',
            'video.extra_options': {'tune': 'lossless'}})
        self.assertEqual(restored.vcodec, 'h264_nvenc')
        self.assertIsNone(restored.crf)
        self.assertEqual(restored.get_codec_options()['tune'], 'lossless')

    def test_interrupted_commit_blocks_collection_and_restores_originals(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'STORE', Path(directory)):
            task = core.task_for(0)
            folder = core.task_dir(task)
            relative = Path('videos/observation.images.top/chunk-000/file-000.mp4')
            original = folder / 'backup/originals' / relative
            original.parent.mkdir(parents=True)
            original.write_bytes(b'original')
            current = core.data_root(task) / relative
            current.parent.mkdir(parents=True)
            current.write_bytes(b'converted')
            for name in ('dataset/meta/info.json', 'collection_manifest.json'):
                core.atomic_json(folder / name, {'version': 'new'})
                core.atomic_json(folder / 'backup' / name, {'version': 'old'})
            core.atomic_json(folder / 'rgb_migration_pending.json', {'backup': 'backup'})
            with self.assertRaisesRegex(RuntimeError, 'migration'):
                core.pending_guard(task)
            rollback(task)
            self.assertEqual(current.read_bytes(), b'original')
            self.assertEqual(core.read_json(folder / 'dataset/meta/info.json'), {'version': 'old'})
            core.pending_guard(task)

    def test_camera_rgb_pixels_survive_encoder_and_metadata_reload(self):
        import av
        import numpy as np
        from lerobot.configs import RGBEncoderConfig
        config = RGBEncoderConfig(vcodec='libx264rgb', pix_fmt='rgb24', crf=0, preset='ultrafast')
        frames = np.random.default_rng(9).integers(0, 256, (4, 48, 64, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'camera.mp4'
            with av.open(str(source), 'w') as output:
                stream = output.add_stream(config.vcodec, rate=30, options=config.get_codec_options(2, True))
                stream.width, stream.height, stream.pix_fmt = 64, 48, config.pix_fmt
                for index, array in enumerate(frames):
                    frame = av.VideoFrame.from_ndarray(array, format='rgb24')
                    frame.pts, frame.time_base = index, Fraction(1, 30)
                    for packet in stream.encode(frame):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            with av.open(str(source)) as incoming:
                decoded = list(incoming.decode(video=0))
                for expected, frame in zip(frames, decoded, strict=True):
                    np.testing.assert_array_equal(expected, frame.to_ndarray(format='rgb24'))
                restored = RGBEncoderConfig.from_video_info({
                    'video.codec': incoming.streams.video[0].codec_context.name,
                    'video.pix_fmt': incoming.streams.video[0].pix_fmt,
                    'video.crf': 0, 'video.preset': 'ultrafast'})
                self.assertEqual(restored.vcodec, 'libx264rgb')
                self.assertEqual(restored.pix_fmt, 'rgb24')
            converted = Path(directory) / 'converted.mp4'
            report = convert(source, converted)
            self.assertEqual(report['frames'], 4)
            self.assertEqual(signature(source), signature(converted))


if __name__ == '__main__':
    unittest.main()
