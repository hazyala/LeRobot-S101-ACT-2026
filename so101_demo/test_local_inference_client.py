"""Test local worker framing and cleanup with a fake inference worker."""
import json
import os
import tempfile
import unittest
import numpy as np
from local_inference_client import LocalInference

FAKE = '''import json,sys,time,numpy as np
for line in sys.stdin:
 r=json.loads(line)
 if r.get("hello"): print(json.dumps({"ready":True,"model":"cup"}),flush=True); continue
 with np.load(r["path"], allow_pickle=False) as o:
  assert o["state"].shape == (6,) and o["top_bgr"].shape == (480,640,3)
 if "slow" in sys.argv[0]: time.sleep(2)
 print(json.dumps({"id":r["id"],"actions":[[2]*6 for _ in range(100)]}),flush=True)
'''

class ClientTest(unittest.TestCase):
    def run_case(self, slow):
        with tempfile.TemporaryDirectory() as directory:
            script = os.path.join(directory, 'slow.py' if slow else 'normal.py')
            with open(script, 'w') as f: f.write(FAKE)
            client = LocalInference('/tmp/dummy-engine','/tmp/dummy-stats',worker_path=script)
            client.start('cup', timeout=8)
            ipc_dir = client.ipc_dir
            image = np.zeros((480,640,3), dtype=np.uint8)
            try:
                if slow:
                    with self.assertRaises(TimeoutError): client.infer([0]*6, image, image, timeout=0.2)
                else:
                    result, elapsed = client.infer([0]*6, image, image, timeout=5)
                    self.assertEqual(result.shape, (100,6))
                    self.assertEqual(result[0,0], 2)
            finally:
                client.close()
            self.assertFalse(os.path.exists(ipc_dir))
    def test_inference_and_cleanup(self): self.run_case(False)
    def test_timeout_and_cleanup(self): self.run_case(True)

if __name__ == '__main__': unittest.main()
