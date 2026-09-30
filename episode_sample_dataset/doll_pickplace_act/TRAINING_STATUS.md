# ACT Training Status

- 시작: 2026-09-22 20:56 KST
- dataset: 100 episodes / 56,768 frames
- policy: ACT, ResNet18 ImageNet initialization, 52M parameters
- inputs: joint state + top RGB + side RGB
- output: 6-DoF action chunk (100 steps)
- device: RTX 3080 CUDA, AMP enabled
- batch size: 4
- target: 20,000 steps
- checkpoint interval: 2,000 steps
- output: `outputs/act_100ep_20k`
- stdout: `train_stdout.log`
- progress/loss log: `train_stderr.log`

초기 확인: 약 6.8 steps/s, GPU memory 2.13 GB, loss 4.10(step 200) → 2.88(step 560).

2026-09-22 21:02 KST에 2,000-step checkpoint 저장 후 Windows의 관리자 권한 없는 symlink 생성 오류로 프로세스가 중단됐다. 모델·optimizer·RNG·training step은 모두 정상 저장됐다. Windows에서는 선택 사항인 `checkpoints/last` 별칭 생성을 건너뛰도록 LeRobot 저장 함수를 보완했고, 22:15 KST에 `002000` checkpoint에서 데이터 순서와 optimizer 상태를 포함해 재개했다. 현재 목표는 남은 18,000 steps이다.
