"""종류별 수집 데이터 용량 확인: python scripts/dataset_sizes.py

원본 dataset의 data/videos/meta만 집계합니다. 임시 파일, 공개 참조 데이터,
학습용 복사본 및 체크포인트는 제외합니다. GB는 1,000,000,000 bytes입니다.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def directory_size(path: Path, errors: list[str]) -> int:
    if not path.exists():
        return 0
    total = 0

    def onerror(error: OSError) -> None:
        errors.append(str(error))

    for folder, directories, files in os.walk(path, onerror=onerror, followlinks=False):
        directories[:] = [name for name in directories
                          if not (Path(folder) / name).is_symlink()]
        for name in files:
            file = Path(folder) / name
            if file.is_symlink():
                continue
            try:
                total += file.stat().st_size
            except OSError as error:
                errors.append(str(error))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'robot_datasets',
                        help='수집 저장소 경로 (tasks 폴더의 상위 경로)')
    parser.add_argument('--settings', type=Path, default=ROOT / 'collection/settings.json',
                        help='작업 종류를 정의한 설정 파일')
    args = parser.parse_args()
    tasks_root = args.root.resolve() / 'tasks'
    if not tasks_root.is_dir():
        parser.error(f'수집 작업 폴더가 없습니다: {tasks_root}')
    try:
        tasks = json.loads(args.settings.read_text(encoding='utf-8-sig'))['tasks']
        groups = {task['key']: task['group'] for task in tasks}
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f'설정 파일을 읽을 수 없습니다: {error}')

    errors: list[str] = []
    totals = dict.fromkeys(groups.values(), 0)
    rows = []
    keys = set(groups) | {path.name for path in tasks_root.iterdir() if path.is_dir()}
    for key in sorted(keys):
        dataset = tasks_root / key / 'dataset'
        group = groups.get(key, 'unclassified')
        size = sum(directory_size(dataset / part, errors)
                   for part in ('data', 'videos', 'meta'))
        totals[group] = totals.get(group, 0) + size
        rows.append((group, key, size))

    print(f'수집 데이터: {tasks_root}')
    print('집계 범위: dataset/data + videos + meta (GB = 10^9 bytes)')
    print('\n종류별 용량')
    for group, size in sorted(totals.items()):
        print(f'  {group:<20} {size / 1e9:12.3f} GB')
    total = sum(totals.values())
    print(f'  {"TOTAL":<20} {total / 1e9:12.3f} GB ({total / 2**30:.3f} GiB)')
    print('\n작업별 용량')
    for group, key, size in rows:
        print(f'  {key:<24} {size / 1e9:12.3f} GB  [{group}]')
    if errors:
        print('\n주의: 일부 파일을 읽지 못해 위 용량은 부분 합계입니다.')
        for error in errors:
            print(f'  {error}')
        return 1
    print('\n수집 중 실행하면 파일 변경으로 용량이 달라질 수 있습니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
