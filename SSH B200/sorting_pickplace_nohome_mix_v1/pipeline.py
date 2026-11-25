"""Prepare -> smoke including validation/best -> fresh 50k mixed ACT training."""
import fcntl
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path('/NHNHOME/workspace/lerobot')
def status(stage,**kw):
    record=dict(stage=stage,updated_utc=datetime.now(timezone.utc).isoformat(),**kw)
    p=HERE/'pipeline_status.json'
    p.with_suffix('.tmp').write_text(json.dumps(record,indent=2))
    os.replace(p.with_suffix('.tmp'),p)
    print(json.dumps(record),flush=True)
def run(args,log,timeout=None):
    with (HERE/log).open('w') as f:
        subprocess.run([sys.executable,'-u',*args],cwd=HERE,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def main():
    lock=(HERE/'pipeline.lock').open('a+')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        status('verifying_and_linking')
        run(['prepare.py'],'prepare.log',1800)
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        smoke=BASE/'outputs'/('smoke_sorting_pickplace_nohome_mix_v1_'+stamp)
        status('smoke_test',output=str(smoke))
        run(['train.py','--output',str(smoke),'--smoke'],'smoke.log',1800)
        assert json.loads((smoke/'best.json').read_text())['step']==10
        assert (smoke/'checkpoints/best/pretrained_model/model.safetensors').is_file()
        (HERE/'smoke_result.json').write_text(json.dumps({'passed':True,'output':str(smoke)},indent=2))
        out=BASE/'outputs'/('act_sorting_pickplace_nohome_mix_v1_'+stamp)
        status('training',output=str(out),steps=50000,batch_size=8,batch_sources={'sorting':4,'doll_nohome':2,'cup_nohome':2},train_episodes=769,sorting_validation_episodes=30)
        run(['train.py','--output',str(out)],'training.log')
        best=json.loads((out/'best.json').read_text())
        assert (out/'checkpoints/best/pretrained_model/model.safetensors').is_file()
        status('completed',output=str(out),best=best)
    except Exception as exc:
        status('failed',error=str(exc),traceback=traceback.format_exc())
        raise
if __name__=='__main__': main()
