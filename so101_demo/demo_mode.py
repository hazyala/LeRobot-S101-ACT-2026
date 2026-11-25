"""Dispatch one supervised mode from the demonstration menu."""
import sys

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('0','1','2','3','4'):
        raise ValueError('invalid mode')
    if sys.argv[1] == '0':
        from home_return import run
        run()
    elif sys.argv[1] == '1':
        from teleoperation import run
        run()
    elif sys.argv[1] == '4':
        from camera_aim import run
        run()
    else:
        from local_act_demo import run
        run('doll' if sys.argv[1] == '2' else 'cup')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n중단 요청을 받았습니다.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print('중지됨: {}'.format(exc), file=sys.stderr, flush=True)
        sys.exit(1)
