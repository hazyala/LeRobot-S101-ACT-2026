#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/uvcvideo.h>
#include <linux/usb/video.h>

static int control(int fd, int selector, int request, uint32_t *value) {
    struct uvc_xu_control_query q = { .unit = 3, .selector = selector,
        .query = request, .size = selector == 3 ? 4 : 1, .data = (uint8_t *)value };
    return ioctl(fd, UVCIOC_CTRL_QUERY, &q);
}

int main(int argc, char **argv) {
    if (argc != 2 && argc != 4) return 2;
    int fd = open(argv[1], O_RDWR);
    if (fd < 0) { perror("open"); return 1; }
    if (argc == 4) {
        uint32_t automatic = (uint32_t)strtoul(argv[2], NULL, 10);
        uint32_t exposure = (uint32_t)strtoul(argv[3], NULL, 10);
        if (automatic > 1 || exposure < 1 || exposure > 33000) return 2;
        uint32_t off = 0;
        if (control(fd, 11, UVC_SET_CUR, &off) || control(fd, 3, UVC_SET_CUR, &exposure)
            || control(fd, 11, UVC_SET_CUR, &automatic)) { perror("set"); return 1; }
    }
    for (int selector = 3; selector <= 11; selector += 8) {
        uint32_t value = 0;
        int rc = -1;
        for (int retry = 0; retry < 12; ++retry) {
            rc = control(fd, selector, UVC_GET_CUR, &value);
            if (rc == 0) break;
            usleep(100000);
        }
        if (rc < 0) { perror("query"); return 1; }
        else {
            printf("selector=%d value=%u\n", selector, value);
            if (argc == 4 && ((selector == 3 && value != strtoul(argv[3], NULL, 10)) ||
                              (selector == 11 && value != strtoul(argv[2], NULL, 10)))) {
                fprintf(stderr, "camera control readback mismatch\n");
                return 1;
            }
        }
    }
    close(fd);
    return 0;
}
