"""Convert collected RGB videos in place, keeping originals and verifying every pixel.

Run with the project Python. --rollback TASK restores an interrupted migration.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'collection'))
import core


def signature(path):
    import av
    digest = hashlib.sha256()
    times = []
    with av.open(str(path)) as container:
        container.streams.video[0].thread_count = 2
        for frame in container.decode(video=0):
            digest.update(frame.to_ndarray(format='rgb24').tobytes())
            times.append(str(frame.pts * frame.time_base))
    return digest.hexdigest(), times


def convert(source, target):
    import av
    target.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(source)) as incoming, av.open(str(target), 'w') as outgoing:
        stream = incoming.streams.video[0]
        stream.thread_count = 2
        encoder = outgoing.add_stream('libx264rgb', rate=stream.average_rate,
                                      options={'crf': '0', 'preset': 'ultrafast', 'g': '2', 'threads': '4'})
        encoder.width, encoder.height = stream.width, stream.height
        encoder.pix_fmt = 'rgb24'
        encoder.time_base = stream.time_base
        for frame in incoming.decode(video=0):
            rgb = frame.reformat(format='rgb24')
            rgb.pts, rgb.time_base = frame.pts, frame.time_base
            for packet in encoder.encode(rgb):
                outgoing.mux(packet)
        for packet in encoder.encode():
            outgoing.mux(packet)
    before, after = signature(source), signature(target)
    if before != after or not before[1]:
        raise RuntimeError(f'RGB pixels or timestamps changed: {source}')
    return {'rgb_sha256': before[0], 'frames': len(before[1]),
            'old_bytes': source.stat().st_size, 'new_bytes': target.stat().st_size}


def rollback(task):
    folder = core.task_dir(task)
    marker = folder / 'rgb_migration_pending.json'
    state = core.read_json(marker)
    backup = core.safe_child(folder, state['backup'])
    root = core.data_root(task)
    for old in (backup / 'originals/videos').glob('*/chunk-*/*.mp4'):
        target = root / old.relative_to(backup / 'originals')
        shutil.copy2(old, target)
    for relative in ('dataset/meta/info.json', 'collection_manifest.json'):
        old = backup / relative
        if old.exists():
            shutil.copy2(old, folder / relative)
    old_snapshot = backup / 'recovery_snapshot'
    if old_snapshot.exists():
        current = folder / 'recovery_snapshot'
        if current.exists():
            current.rename(backup / ('aborted_snapshot_' + datetime.now().strftime('%H%M%S%f')))
        old_snapshot.rename(current)
    marker.unlink()
    print(f'{task["key"]}: restored original videos and metadata', flush=True)


def migrate(task):
    import av
    folder, root = core.task_dir(task), core.data_root(task)
    marker = folder / 'rgb_migration_pending.json'
    if marker.exists():
        raise RuntimeError(f'Interrupted migration: run --rollback {task["key"]} first')
    core.pending_guard(task)
    info_path = root / 'meta/info.json'
    if not info_path.exists():
        return
    info = core.read_json(info_path)
    keys = ['observation.images.top', 'observation.images.side']
    if all(info['features'][key]['info'].get('video.pix_fmt') == 'gbrp'
           and (info['features'][key]['info'].get('video.crf') == 0
                or info['features'][key]['info'].get('video.extra_options', {}).get('tune') == 'lossless')
           for key in keys):
        print(f'{task["key"]}: already migrated', flush=True)
        return
    files = sorted(path for key in keys for path in (root / 'videos' / key).glob('chunk-*/*.mp4'))
    if not files:
        return
    backup = folder / ('rgb_lossless_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir()
    for relative in ('dataset/meta/info.json', 'collection_manifest.json'):
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / relative, destination)
    core.atomic_json(marker, {'backup': backup.name, 'stage': 'converting'})
    report = {'task': task['key'], 'source': 'previously lossy RGB decoded to rgb24',
              'restores_original_camera_quality': False, 'files': {}}
    try:
        required = sum(source.stat().st_size for source in files) * 100 + 20_000_000_000
        if shutil.disk_usage(root).free < required:
            raise RuntimeError('Insufficient staging space plus 20 GB reserve')
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(convert, source, backup / 'staged' / source.relative_to(root)): source
                       for source in files}
            for index, future in enumerate(as_completed(futures), 1):
                relative = futures[future].relative_to(root)
                report['files'][relative.as_posix()] = future.result()
                if index == 1 or index % 10 == 0 or index == len(files):
                    print(f'{task["key"]}: pixel/time verified {index}/{len(files)}', flush=True)
        core.atomic_json(backup / 'report.json', report)
        core.atomic_json(marker, {'backup': backup.name, 'stage': 'committing'})
        for source in files:
            relative = source.relative_to(root)
            original = backup / 'originals' / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            source.rename(original)
            (backup / 'staged' / relative).rename(source)
        for key in keys:
            sample = next((root / 'videos' / key).glob('chunk-*/*.mp4'))
            with av.open(str(sample)) as container:
                stream = container.streams.video[0]
                info['features'][key]['info'].update({
                    'video.codec': stream.codec_context.name, 'video.pix_fmt': stream.pix_fmt,
                    'video.crf': 0, 'video.preset': 'ultrafast', 'video.g': 2,
                    'video.fast_decode': 0, 'video.extra_options': {}, 'video.video_backend': 'pyav'})
        core.atomic_json(info_path, info)
        manifest_path = folder / 'collection_manifest.json'
        manifest = core.read_json(manifest_path)
        manifest['rgb_encoder'] = core.read_json(core.BASE / 'settings.json')['rgb_encoder']
        core.atomic_json(manifest_path, manifest)
        if (folder / 'recovery_snapshot').exists():
            (folder / 'recovery_snapshot').rename(backup / 'recovery_snapshot')
        core.snapshot(task)
        core.atomic_json(folder / 'sessions' / ('rgb_migration_' + backup.name + '.json'), report)
        marker.unlink()
        print(f'{task["key"]}: complete; originals retained at {backup}', flush=True)
    except BaseException:
        rollback(task)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', help='Task key to restore after interrupted conversion')
    args = parser.parse_args()
    with core.exclusive(core.STORE / 'rig.lock'):
        tasks = [core.task_for(args.rollback)] if args.rollback else core.registry()
        for task in tasks:
            with core.exclusive(core.task_dir(task) / 'access.lock'):
                if args.rollback:
                    rollback(task)
                else:
                    migrate(task)


if __name__ == '__main__':
    main()
