"""Camera alignment using the red table marker; no motor connection."""
import os
from functools import lru_cache
from pathlib import Path
import cv2
from preview_window import open_fullscreen, show_fullscreen
import numpy as np

TARGETS = ((364, 180, 103, 72), (140, 0, 202, 137))
PATTERNS = ('/dev/v4l/by-id/*RealSense*405*video-index2',
            '/dev/v4l/by-id/*ABKO*video-index0')

def red_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 110, 65), (8, 255, 255)) | cv2.inRange(hsv, (175, 110, 65), (179, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask

def marker(image):
    mask = red_mask(image)
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    candidates = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > 600]
    candidates = [r for r in candidates if 55 <= r[2] <= 280 and 30 <= r[3] <= 220]
    return max(candidates, key=lambda r: r[2]*r[3], default=None)

@lru_cache(maxsize=2)
def reference(top):
    path = Path(__file__).with_name('aim_ref_' + ('top' if top else 'side') + '.png')
    ref = cv2.imread(str(path))
    if ref is None: raise FileNotFoundError(str(path))
    roi = (slice(84,154),slice(132,236)) if top else (slice(278,477),slice(0,196))
    edges = cv2.Canny(ref[roi],45,110) > 0
    area = (slice(165,270),slice(345,485)) if top else (slice(0,156),slice(126,365))
    return roi, edges, area, red_mask(ref)[area] > 0

def compare(image, top):
    roi, edges, area, tape = reference(top)
    observed = red_mask(image)[area] > 0
    overlap = np.count_nonzero(tape & observed) / np.count_nonzero(tape | observed)
    distance = cv2.distanceTransform(255-cv2.Canny(image[roi],45,110), cv2.DIST_L2, 3)
    coverage = np.mean(distance[edges] <= 6)
    return overlap, coverage

def tape_anchors(mask):
    contours = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    if not contours: return []
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 600: return []
    points = contour[:,0,:]
    return [points[np.argmax(points @ direction)] for direction in ((-.3,1.),(1.,.45))]

def panel(image, target, name):
    view = image.copy()
    x, y, w, h = target
    found = marker(image)
    top = target == TARGETS[0]
    overlap, coverage = compare(image, top)
    good = found is not None and overlap >= .65 and coverage >= .70
    roi, edges, area, tape = reference(top)
    view[roi][edges] = (255,255,0)
    outline = cv2.morphologyEx(tape.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3,3), np.uint8))
    view[area][outline > 0] = (255,255,0)
    color = (0, 210, 0) if good else (0, 0, 255)
    for gx in range(0, 640, 80): cv2.line(view, (gx,0), (gx,479), (100,100,100), 1)
    for gy in range(0, 480, 80): cv2.line(view, (0,gy), (639,gy), (100,100,100), 1)
    cv2.drawMarker(view, (320,240), (255,255,255), cv2.MARKER_CROSS, 18, 2)
    cv2.rectangle(view, (x,y), (x+w,y+h), color, 3)
    if found:
        fx,fy,fw,fh = found
        cv2.rectangle(view, (fx,fy), (fx+fw,fy+fh), (120,120,120), 1)
        cv2.arrowedLine(view, (fx+fw//2,fy+fh//2), (x+w//2,y+h//2), color, 3, tipLength=.25)
    label = 'ALIGNED' if good else ('MATCH BOX' if overlap >= .65 else 'MATCH RED TAPE')
    if not top and found:
        origin = np.array([area[1].start, area[0].start])
        actual = tape_anchors(red_mask(image)[fy:fy+fh,fx:fx+fw])
        for ref, live in zip(tape_anchors(tape), actual):
            goal = tuple(map(int,ref + origin))
            pos = tuple(map(int,live + (fx,fy)))
            cv2.circle(view, goal, 8, (255,255,0), 2)
            cv2.circle(view, pos, 3, (0,255,255), -1)
            cv2.arrowedLine(view,pos,goal,(0,255,255),2)
    cv2.rectangle(view, (220, 446), (640, 479), (0,0,0), -1)
    cv2.putText(view, name + '  ' + label, (230,470), cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2)
    return view

def run():
    from teleoperation import Camera, TerminalStop
    if not os.environ.get('DISPLAY'): raise RuntimeError('Jetson 화면에서 실행하세요.')
    cameras = []
    terminal = None
    try:
        for pattern in PATTERNS: cameras.append(Camera(pattern))
        terminal = TerminalStop()
        open_fullscreen('Camera aim - Q to exit')
        print('옆 화면에서는 노란 점 두 개를 각각 하늘색 고리에 맞추세요. 한쪽만 맞으면 카메라 각도도 조정하세요.', flush=True)
        print('하늘색 기준 윤곽에 빨간 테이프와 빈 투명 상자 모서리가 모두 겹치도록 조정하세요.', flush=True)
        print('빨간 표식을 가리지 말고 기준 사각형에 맞춰 주세요. 초록색이면 허용 범위입니다. Q를 누르면 메뉴로 돌아갑니다.', flush=True)
        print('격자 중심 십자와 빨간 표식 기준은 별개입니다. 표식과 상자의 실제 위치도 학습 때와 맞춰 주세요.', flush=True)
        print('인형·종이컵 공통 구도입니다. 두 화면이 모두 초록색이면 카메라를 고정하세요.', flush=True)
        while True:
            panels = []
            for camera, target, name in zip(cameras, TARGETS, ('TOP D405', 'SIDE')):
                try: panels.append(panel(camera.latest(), target, name))
                except RuntimeError:
                    blank = np.zeros((480,640,3), np.uint8)
                    cv2.putText(blank, name+' CAMERA NOT READY', (20,240), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,0,255), 2)
                    panels.append(blank)
            show_fullscreen('Camera aim - Q to exit', np.hstack(panels))
            key = cv2.waitKey(20) & 255
            keys = (key, terminal.poll())
            if any(k in (ord('q'), ord('Q'), 27) for k in keys): break
            if cv2.getWindowProperty('Camera aim - Q to exit', cv2.WND_PROP_VISIBLE) < 1: break
    finally:
        if terminal: terminal.close()
        for camera in cameras: camera.close()
        cv2.destroyAllWindows()
