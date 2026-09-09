# RealSense D405 탑뷰 카메라 테스트

이 문서는 Intel RealSense D405를 SO-101 Pick & Place 작업대의 탑뷰 카메라로 쓰기 위해 확인한 내용입니다.

## 지금 보면 되는 것

- 테스트 스크립트: `D:\lerobot-2026\scripts\realsense_D405_test.py`
- 컬러 이미지: `D:\lerobot-2026\notes\realsense_D405_test\d405_top_color.png`
- Depth 원본 이미지: `D:\lerobot-2026\notes\realsense_D405_test\d405_top_depth_raw.png`
- Depth 확인용 컬러맵: `D:\lerobot-2026\notes\realsense_D405_test\d405_top_depth_colormap.png`

## 설치된 것

- Python SDK 패키지: `pyrealsense2==2.58.4`
- 역할: Python에서 RealSense 카메라의 color/depth 프레임을 읽게 해주는 SDK 바인딩입니다.

## 확인된 카메라

- 장치 이름: `RealSense D405`
- Serial number: 로컬 테스트 출력에서 확인
- Firmware: 로컬 테스트 출력에서 확인
- USB 연결: 로컬 테스트 출력에서 확인

## 테스트 결과

- Color stream: 성공
- Depth stream: 성공
- Color frame: `(480, 640, 3)`, `uint8`
- Depth frame: `(480, 640)`, `uint16`
- Depth scale: `9.999999747378752e-05 meter/unit`
- Depth range: `0.0916m ~ 6.5535m`

## 실행 방법

PowerShell에서:

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\python.exe .\scripts\realsense_D405_test.py
```

실시간 미리보기까지 보고 싶으면:

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\python.exe .\scripts\realsense_D405_test.py --preview
```

## 주의

현재 저장된 테스트 이미지는 카메라가 천장/모니터 쪽을 보고 있는 상태에서 찍힌 것입니다. 실제 Pick & Place 데이터 수집 전에는 D405를 작업대 위에서 아래로 향하게 고정해야 합니다.
