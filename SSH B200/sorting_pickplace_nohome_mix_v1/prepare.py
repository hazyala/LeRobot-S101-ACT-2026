"""Verify uploaded numeric prefixes against server originals and reuse RGB videos."""
import hashlib
import json
import os
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

BASE=Path('/NHNHOME/workspace/lerobot')
DATA=BASE/'datasets/pickplace_nohome_v1'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    manifest=read(DATA/'payload_manifest.json')
    for row in manifest:
        assert sha(DATA/row['path'])==row['sha256'],row['path']
    assert read(DATA/'validation_report.json')['passed']
    for name,original_name in [('doll','doll'),('cup','paper_cup')]:
        original=BASE/'datasets'/original_name/'dataset'
        out=DATA/name/'dataset'
        mapping=read(DATA/name/'derivation.json')
        assert sha(original/'meta/info.json')==mapping['source_info_sha256']
        for rec in mapping['episodes']:
            ep,n=rec['source_episode'],rec['retained_frames']
            source_rel=rec['source_data_file'].replace('\\','/').split('/dataset/',1)[1]
            tab=pq.read_table(original/source_rel,columns=['episode_index','action','observation.state'])
            tab=tab.filter(pa.compute.equal(tab['episode_index'],ep)).slice(0,n)
            h=hashlib.sha256(tab['action'].combine_chunks().values.to_numpy().tobytes()+tab['observation.state'].combine_chunks().values.to_numpy().tobytes()).hexdigest()
            assert h==rec['retained_action_state_sha256'],(name,ep)
            assert sha(out/f'data/chunk-000/file-{ep:03d}.parquet')==rec['data_sha256']
            assert n < rec['last_home_start_frame'] < rec['length']
            for video in rec['videos']:
                relative=video['source'].replace('\\','/').split('/dataset/',1)[1]
                src=original/relative
                assert src.stat().st_size==video['size'],src
                dst=out/f"videos/{video['key']}/chunk-000/file-{ep:03d}.mp4"
                dst.parent.mkdir(parents=True,exist_ok=True)
                if not dst.exists(): os.link(src,dst)
                assert os.path.samefile(src,dst)
        print(name,'verified',len(mapping['episodes']),flush=True)
    (DATA/'READY.json').write_text(json.dumps({'verified':True,'episodes':749,'numeric_prefixes_match_server_original':True,
        'uploaded_payload_sha256_verified':True,'video_source_sizes_verified':True},indent=2))

if __name__=='__main__': main()
