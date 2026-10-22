# SO-101 ACT Pick & Place — 실물 실행 영상 페이지

이 브랜치(`gh-pages`)는 GitHub Pages로 배포되는 실물 실행 영상 페이지입니다. 코드와 연구 기록은 [`dev` 브랜치](https://github.com/hazyala/LeRobot-S101-ACT-2026/tree/dev)에 있습니다.

<table>
  <tr>
    <td width="150" align="center">
      <a href="https://hazyala.github.io/LeRobot-S101-ACT-2026/"><img src="img/qr_demo.png" width="130" alt="실물 실행 영상 페이지 QR"></a>
    </td>
    <td>
      <a href="https://hazyala.github.io/LeRobot-S101-ACT-2026/"><img src="https://img.shields.io/badge/Demo-%EC%8B%A4%EB%AC%BC%20%EC%8B%A4%ED%96%89%20%EC%98%81%EC%83%81%20%EB%B3%B4%EA%B8%B0-2563EB?style=for-the-badge" alt="실물 실행 영상 보기"></a>
      <br><br>
      <a href="https://hazyala.github.io/LeRobot-S101-ACT-2026/">hazyala.github.io/LeRobot-S101-ACT-2026</a>
    </td>
  </tr>
</table>

## 수록 영상

| 구분 | 파일 | 내용 |
|---|---|---|
| 01 인형 | [`videos/robot_view_b.mp4`](videos/robot_view_b.mp4) | 서 있는 인형 — 파지 · 운반 · 상자 안착 후 HOME 복귀 |
| 01 인형 | [`videos/robot_view_a.mp4`](videos/robot_view_a.mp4) | 누워 있는 인형 — 파지 · 운반 · 상자 안착 |
| 01 인형 | [`videos/runner_top_side.mp4`](videos/runner_top_side.mp4) | 로봇 실행기 화면 — 정책 입력인 TOP(D405) · SIDE(웹캠) 카메라 |
| 02 종이컵 | [`videos/cup_robot_view.mp4`](videos/cup_robot_view.mp4) | 종이컵 — 찌그러지지 않게 파지해 빨간 목표 패드 위에 세워 안착 |
| 02 종이컵 | [`videos/cup_runner_top_side.mp4`](videos/cup_runner_top_side.mp4) | 로봇 실행기 화면 — 종이컵 실행 중 TOP · SIDE 카메라 |

인형 영상은 NVIDIA B200에서 50,000단계 학습한 ACT 모델 중 검증 오차가 가장 낮은 checkpoint 047000으로 실행했습니다.

## 구성

```text
index.html   영상 페이지
videos/      웹용으로 다시 인코딩한 실행 영상 (H.264, faststart)
img/         영상 포스터 · 장면 이미지 · QR
```
