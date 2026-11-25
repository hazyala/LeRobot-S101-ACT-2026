"""Observe Wi-Fi and TCP locally while the D405 stream is running."""
import cv2
import socket
import subprocess
import time

def netcheck(label):
    wifi = subprocess.run(['iwconfig', 'wlan0'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    lines = ' '.join(line.strip() for line in wifi.splitlines() if any(x in line for x in ('Access Point', 'Link Quality', 'Bit Rate')))
    try:
        start = time.monotonic()
        s = socket.create_connection(('59.150.33.1', 54307), timeout=3)
        s.close()
        connection = 'TCP {:.0f}ms'.format(1000*(time.monotonic()-start))
    except OSError as ex:
        connection = str(ex)
    print(label, lines, connection, flush=True)

netcheck('before')
cam = cv2.VideoCapture(3, cv2.CAP_V4L2)
try:
    ok, frame = cam.read()
    print('D405 frame:', ok, None if frame is None else frame.shape, flush=True)
    for i in range(4):
        netcheck('camera {}'.format(i))
finally:
    cam.release()
time.sleep(2)
netcheck('after')
