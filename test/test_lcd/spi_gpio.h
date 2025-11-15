#ifndef SPI_GPIO_H
#define SPI_GPIO_H

#include <stdint.h>
#include <stddef.h>

#define SPI_MODE_0 0

// SPI
int spi_init(uint32_t speed_hz, uint8_t mode); // returns fd or -1
void spi_close(int fd);
void spi_write(int spi_fd, const uint8_t* data, size_t len);

// GPIO (sysfs simple)
void gpio_write(int pin, int value);     // set output 0/1 (exports and sets direction "out" automáticamente)
void gpio_pwm_set(int pin, int duty);    // simple: duty==0 -> off, duty>0 -> on (for real PWM use pigpio/etc)
int gpio_init_pin(int pin, int initial_value); // returns 0 on success, -1 on error

#endif // SPI_GPIO_H
