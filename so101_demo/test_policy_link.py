"""Exercise the SSH pipe protocol locally without camera or robot access."""
import sys
import time
import unittest
import numpy as np
from policy_link import PolicyLink

FAKE = r'''
import json, sys, time
for line in sys.stdin:
    data = json.loads(line)
    if 'model' in data:
        print(json.dumps({'ready':True,'model':data['model']}),flush=True)
    else:
        if sys.argv[1] == 'slow': time.sleep(2)
        print(json.dumps({'id':data['id'],'actions':[[0]*6 for _ in range(100)]}),flush=True)
'''

class LinkTests(unittest.TestCase):
    def test_large_request_and_clean_close(self):
        link = PolicyLink([sys.executable, '-u', '-c', FAKE, 'normal'])
        try:
            link.start('doll', timeout=5)
            rng = np.random.default_rng(2026)
            frame = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
            actions, elapsed = link.infer([0]*6, frame, frame, timeout=8)
            self.assertEqual(actions.shape, (100, 6))
            self.assertLess(elapsed, 8)
        finally:
            link.close()
        self.assertIsNone(link.process)

    def test_timeout_closes_connection(self):
        link = PolicyLink([sys.executable, '-u', '-c', FAKE, 'slow'])
        link.start('cup', timeout=5)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with self.assertRaises(TimeoutError):
            link.infer([0]*6, frame, frame, timeout=0.2)
        self.assertIsNone(link.process)

if __name__ == '__main__': unittest.main()
