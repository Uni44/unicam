#include "spi_gpio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>
#include <sys/stat.h>
#include <sys/types.h>

// SPI device path (ajusta si usas otro CS)
static const char *SPI_DEVICE = "/dev/spidev0.0";

static int write_file(const char *path, const char *val) {
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    ssize_t r = write(fd, val, strlen(val));
    (void)r;
    close(fd);
    return 0;
}

int spi_init(uint32_t speed_hz, uint8_t mode) {
    int fd = open(SPI_DEVICE, O_RDWR);
    if (fd < 0) {
        perror("spi_init: open");
        return -1;
    }
    uint8_t spi_mode = mode;
    uint8_t bits = 8;
    if (ioctl(fd, SPI_IOC_WR_MODE, &spi_mode) < 0) {
        perror("SPI_IOC_WR_MODE");
        close(fd);
        return -1;
    }
    if (ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0) {
        perror("SPI_IOC_WR_BITS_PER_WORD");
        close(fd);
        return -1;
    }
    if (ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed_hz) < 0) {
        perror("SPI_IOC_WR_MAX_SPEED_HZ");
        close(fd);
        return -1;
    }
    return fd;
}

void spi_close(int fd) {
    if (fd >= 0) close(fd);
}

void spi_write(int spi_fd, const uint8_t* data, size_t len) {
    if (spi_fd < 0 || data == NULL || len == 0) return;
    const size_t MAX_WRITE = 4096; // límite seguro para /dev/spidev
    size_t offset = 0;
    while (offset < len) {
        size_t chunk = (len - offset > MAX_WRITE) ? MAX_WRITE : (len - offset);
        ssize_t w = write(spi_fd, data + offset, chunk);
        if (w < 0) {
            if (errno == EINTR) continue;
            if (errno == EAGAIN) { usleep(1000); continue; }
            perror("spi_write: write");
            return;
        }
        offset += (size_t)w;
    }
}

// --- GPIO via sysfs (simple) ---
static int gpio_export_force(int pin) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%d", pin);
    return write_file("/sys/class/gpio/export", buf);
}

static int gpio_set_dir(int pin, const char *dir) {
    char path[128];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/direction", pin);
    return write_file(path, dir);
}

// New: export pin, set direction out and set initial value
int gpio_init_pin(int pin, int initial_value) {
    if (gpio_export_force(pin) < 0) {
        // It may already be exported; continue
    }
    // small delay to allow sysfs to create files
    usleep(10000);
    if (gpio_set_dir(pin, "out") < 0) {
        // continue anyway
    }
    char path[128], val[2];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", pin);
    snprintf(val, sizeof(val), "%d", initial_value ? 1 : 0);
    if (write_file(path, val) < 0) return -1;
    return 0;
}

void gpio_write(int pin, int value) {
    // export & set dir if needed
    gpio_init_pin(pin, value); // ensures exported and direction set; sets initial value
    char path[128], val[2];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", pin);
    snprintf(val, sizeof(val), "%d", value ? 1 : 0);
    write_file(path, val);
}

// Simple backlight control: on/off only. For true PWM, use pigpio or hardware PWM.
void gpio_pwm_set(int pin, int duty) {
    // ensure pin exported and direction configured
    gpio_init_pin(pin, duty > 0 ? 1 : 0);
    if (duty <= 0) gpio_write(pin, 0);
    else gpio_write(pin, 1);
}
