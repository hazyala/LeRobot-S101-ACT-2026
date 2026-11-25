# SO-101 Jetson/B200 integration — work in progress

This directory is not a runnable robot demonstration. Do not use the inference
output to command a robot until the Jetson controller, safety interlocks, and
on-device tests have been completed.

## Prepared components

- `inference_server.py`: one-client, newline-JSON ACT inference over an SSH
  stdin/stdout stream. It loads the original doll checkpoint or the existing
  B200 paper-cup 044000 checkpoint, checks model weights, decodes two lossless
  camera frames, and returns a 100-by-6 action chunk. It has no motor access.
- `test_inference.py`: GPU inference test with synthetic images and zero joint
  state. It is not a robot or policy-success test.
- `camera_probe.py`, `servo_probe.py`: camera capture and read-only servo checks.
- `roundtrip_probe.py`: camera-to-server timing probe; uses a synthetic joint
  state and never commands motors. It requires working Jetson SSH credentials.
- `synthetic_roundtrip.py`: small synthetic-image test over Jetson-to-B200 SSH.
- `devices.py` and `safety.py`: unfinished controller building blocks. The
  latter's range, rate, and stale-response checks have unit tests, but are not
  connected to robot control; they are not a functional safety system.
- `policy_link.py`: nonblocking, deadline-bounded SSH transport, verified with
  synthetic data and simulated timeouts on Jetson and B200. No camera or motor
  control. `teleoperation.py` is an uncommissioned draft; never run it on real
  hardware before supervised verification, including stop and torque behavior.
- `ssh_bandwidth_probe.py`, `wifi_camera_probe.py`, `camera_benchmark.py`:
  diagnostics only, without motor commands.

## Deployment notes (2026-11-16)

Jetson environment is `/home/aisw/lerobot/.venv` (Python 3.12); its uv binary
is `/home/aisw/jetson-tools/uv-aarch64-unknown-linux-musl/uv`. Leader USB serial
is `5AE6058375`; follower USB serial is `5AE6055249`. Use `/dev/serial/by-id/`
paths, never rely on ACM device numbering. Both arms matched the existing
calibration files by read-only register checks. Two cameras were detected: the
RealSense D405 is serial `262723072576` and the side camera is ABKO APC480.
The D405 color stream was readable on `video3` on this boot; video numbers can
change, so production code must resolve the correct stream by device identity
and verify its format. The training setup used a different D405 serial and its
visual equivalence remains unverified.

B200 files live in `/NHNHOME/workspace/lerobot/so101-demo/`; its existing
environment is `/NHNHOME/workspace/lerobot/lerobot-act`. The copied doll
checkpoint and normalization files match the existing local execution model.
The server-side synthetic inference test passed for both models.

The Jetson-specific restricted public key was added to B200's authorized_keys,
but the public SSH gateway rejected it. With the user's explicit approval, the
existing accepted B200 credential was copied to Jetson at
`~/.ssh/so101_gateway_key` (mode 600). Jetson successfully connected to B200
using it. A live-camera inference probe subsequently timed out, and the Jetson
itself became unreachable over SSH; do not infer that the network is the sole
cause of the probe timeout. The probe also had a partial-write bug; its fix
still requires an on-device retest. A later small synthetic-image request succeeded
(9.5 s including SSH and model startup; GPU execution 296 ms). This credential
grants general B200 account access.

On a subsequent Wi-Fi-only test, a 140 kB SSH transfer succeeded in 386 ms
without camera capture. It also succeeded with the side camera open, but an
attempt with D405 color capture open timed out. D405 capture at the lower
negotiated 424x240/5fps also timed out. The evidence suggests a correlation,
not a confirmed cause; changing the camera image would also require policy
validation. D405-open tests can interrupt the Jetson SSH connection.

The locally recorded diagnostic after reconnecting the D405 observed a TCP
timeout before opening its video stream, then reported Wi-Fi disassociation
while the video stream was open. Another unattended test read both 640x480
camera frames and measured the follower state but lost SSH before receiving an
inference result. Wi-Fi was using the RTL8188CUS adapter on 2.4 GHz; its signal
was approximately -68 to -72 dBm in these tests. This is correlation rather
than proof of radio interference or a definitive root cause.

A subsequent diagnostic captured both live camera frames and actual follower
state, closed both cameras, then transmitted a lossless snapshot to the B200
cup model and received an output of shape (100, 6). The inference transaction
took 4.36 seconds, excluding SSH/model startup. This proves input/output
compatibility for one stale snapshot, not live operation or action safety.
A side-camera-only benchmark, with a copy of the same frame used for both
images, measured PNG transactions at 5.45 and 9.90 seconds and JPEG quality 90
transactions at 0.86 and 1.41 seconds. JPEG was only tested for transport;
its effect on the trained policy and on real manipulation is unknown.

## Remaining work

Restore Jetson connectivity; diagnose the camera inference probe timeout and measure real end-to-end frame/state-to-action
latency and dropout; implement and test a bounded, stale-action-rejecting Jetson
controller with robust local stop, disconnect, and torque handling; create the
requested `lerobot` menu; verify camera orientation and image preprocessing;
and perform supervised teleoperation and both pick-and-place trials. Avoid
assuming that TCP connect time or synthetic GPU inference is an end-to-end test.
