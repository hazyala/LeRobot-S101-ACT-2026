"""Worker import must not start training or acquire pipeline locks."""
import runpy
from pathlib import Path
here = Path(__file__).resolve().parent
for name in ('smoke_test.py', 'pipeline.py'):
    runpy.run_path(str(here / name), run_name='__mp_main__')
    print(name + ': child-process import passed', flush=True)
