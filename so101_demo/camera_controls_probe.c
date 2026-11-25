#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/videodev2.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int fd = open(argv[1], O_RDWR);
    if (fd < 0) { perror("open"); return 1; }
    struct v4l2_queryctrl q;
    memset(&q, 0, sizeof(q));
    q.id = V4L2_CTRL_FLAG_NEXT_CTRL;
    while (ioctl(fd, VIDIOC_QUERYCTRL, &q) == 0) {
        struct v4l2_control v = {.id = q.id};
        int ok = ioctl(fd, VIDIOC_G_CTRL, &v) == 0;
        printf("id=%#x name=%s min=%d max=%d step=%d default=%d value=%d readable=%d flags=%#x\n",
               q.id, q.name, q.minimum, q.maximum, q.step, q.default_value, v.value, ok, q.flags);
        q.id |= V4L2_CTRL_FLAG_NEXT_CTRL;
    }
    close(fd);
    return 0;
}
