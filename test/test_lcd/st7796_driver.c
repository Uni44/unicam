#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h> // for usleep
#include "spi_gpio.h" // You must implement or use a library for SPI/GPIO
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

#define SPI_FREQ 80000000
#define BL_FREQ 1000
#define RST_PIN 25
#define DC_PIN 24
#define BL_PIN 18

#define LCD_WIDTH  320
#define LCD_HEIGHT 480

typedef struct {
    int width;
    int height;
    // GPIO pins
    int rst_pin;
    int dc_pin;
    int bl_pin;
    // SPI handle
    int spi_fd;
} st7796_t;

void st7796_bl_duty_cycle(st7796_t* lcd, int duty) {
    gpio_pwm_set(lcd->bl_pin, duty); // Implement this for your platform
}

void st7796_digital_write(int pin, int value) {
    gpio_write(pin, value); // Implement this for your platform
}

void st7796_spi_writebyte(st7796_t* lcd, const uint8_t* data, size_t len) {
    spi_write(lcd->spi_fd, data, len); // Implement this for your platform
}

void st7796_command(st7796_t* lcd, uint8_t cmd) {
    st7796_digital_write(lcd->dc_pin, 0);
    st7796_spi_writebyte(lcd, &cmd, 1);
}

void st7796_data(st7796_t* lcd, uint8_t val) {
    st7796_digital_write(lcd->dc_pin, 1);
    st7796_spi_writebyte(lcd, &val, 1);
}

void st7796_reset(st7796_t* lcd) {
    st7796_digital_write(lcd->rst_pin, 1);
    usleep(10000);
    st7796_digital_write(lcd->rst_pin, 0);
    usleep(10000);
    st7796_digital_write(lcd->rst_pin, 1);
    usleep(10000);
}

// Ensure GPIO pins (RST, DC, BL) are exported and set to known states
void st7796_gpio_init(st7796_t* lcd) {
    // Try to initialize pins; ignore minor failures but continue
    gpio_init_pin(lcd->rst_pin, 1); // default high (not in reset)
    gpio_init_pin(lcd->dc_pin, 1);  // data/command default high
    gpio_init_pin(lcd->bl_pin, 0);  // backlight off initially
}

// Faster set_windows: batch command + params to avoid per-byte DC toggles
void st7796_set_windows(st7796_t* lcd, int Xstart, int Ystart, int Xend, int Yend, int horizontal) {
    // Asegurarse que los límites sean inclusivos y correctos
    if (Xstart > Xend) { int t = Xstart; Xstart = Xend; Xend = t; }
    if (Ystart > Yend) { int t = Ystart; Ystart = Yend; Yend = t; }
    
    // Mantener X,Y en orden correcto para landscape
    uint8_t buf2A[4] = { (uint8_t)(Xstart >> 8), (uint8_t)(Xstart & 0xFF), 
                         (uint8_t)(Xend >> 8), (uint8_t)(Xend & 0xFF) };
    st7796_command(lcd, 0x2A);
    st7796_digital_write(lcd->dc_pin, 1);
    st7796_spi_writebyte(lcd, buf2A, sizeof(buf2A));

    uint8_t buf2B[4] = { (uint8_t)(Ystart >> 8), (uint8_t)(Ystart & 0xFF),
                         (uint8_t)(Yend >> 8), (uint8_t)(Yend & 0xFF) };
    st7796_command(lcd, 0x2B);
    st7796_digital_write(lcd->dc_pin, 1);
    st7796_spi_writebyte(lcd, buf2B, sizeof(buf2B));

    st7796_command(lcd, 0x2C);
    // leave DC for data writes to st7796_write_data_bytes / show_image_fast
}

// New helper: write data buffer with DC=1 in large chunks (no usleep)
void st7796_write_data_bytes(st7796_t* lcd, const uint8_t* buf, size_t len) {
    const size_t CHUNK = 4096; // tamaño seguro para evitar "Message too long"
    size_t sent = 0;
    st7796_digital_write(lcd->dc_pin, 1);
    while (sent < len) {
        size_t to_send = (len - sent > CHUNK) ? CHUNK : (len - sent);
        st7796_spi_writebyte(lcd, buf + sent, to_send);
        sent += to_send;
    }
}

void st7796_dre_rectangle(st7796_t* lcd, int Xstart, int Ystart, int Xend, int Yend, uint16_t color) {
    if (Xstart > Xend) { int t = Xstart; Xstart = Xend; Xend = t; }
    if (Ystart > Yend) { int t = Ystart; Ystart = Yend; Yend = t; }

    int width = Xend - Xstart + 1;
    int height = Yend - Ystart + 1;
    if (width <= 0 || height <= 0) return;

    uint8_t ch = (color >> 8) & 0xFF;
    uint8_t cl = color & 0xFF;

    // CORRECCIÓN: pasar Xstart,Ystart,Xend,Yend (no intercambiar)
    st7796_set_windows(lcd, Xstart, Ystart, Xend, Yend, 0);

    size_t total_bytes = (size_t)width * (size_t)height * 2;
    const size_t FULLBUF_LIMIT = 4 * 1024 * 1024;

    if (total_bytes <= FULLBUF_LIMIT) {
        uint8_t *full = malloc(total_bytes);
        if (!full) {
            size_t row_bytes = (size_t)width * 2;
            uint8_t *row = malloc(row_bytes);
            if (!row) return;
            for (int x = 0; x < width; x++) { row[x*2]=ch; row[x*2+1]=cl; }
            for (int y = 0; y < height; y++) st7796_write_data_bytes(lcd, row, row_bytes);
            free(row);
            return;
        }
        for (size_t i = 0; i < (size_t)width*(size_t)height; i++) {
            full[i*2] = ch;
            full[i*2+1] = cl;
        }
        st7796_write_data_bytes(lcd, full, total_bytes);
        free(full);
    } else {
        size_t row_bytes = (size_t)width * 2;
        uint8_t *row = malloc(row_bytes);
        if (!row) return;
        for (int x = 0; x < width; x++) { row[x*2]=ch; row[x*2+1]=cl; }
        for (int y = 0; y < height; y++) st7796_write_data_bytes(lcd, row, row_bytes);
        free(row);
    }
    // done
}

void st7796_lcd_init(st7796_t* lcd) {
    st7796_reset(lcd);
    st7796_command(lcd, 0x11);
    usleep(120000);

    // Inicialmente en modo portrait (como en tu Python driver)
    st7796_command(lcd, 0x36);
    st7796_data(lcd, 0x08);

    st7796_command(lcd, 0x3A);
    st7796_data(lcd, 0x05);

    st7796_command(lcd, 0xF0);
    st7796_data(lcd, 0xC3);

    st7796_command(lcd, 0xF0);
    st7796_data(lcd, 0x96);

    st7796_command(lcd, 0xB4);
    st7796_data(lcd, 0x01);

    st7796_command(lcd, 0xB7);
    st7796_data(lcd, 0xC6);

    st7796_command(lcd, 0xC0);
    st7796_data(lcd, 0x80);
    st7796_data(lcd, 0x45);

    st7796_command(lcd, 0xC1);
    st7796_data(lcd, 0x13);

    st7796_command(lcd, 0xC2);
    st7796_data(lcd, 0xA7);

    st7796_command(lcd, 0xC5);
    st7796_data(lcd, 0x0A);

    st7796_command(lcd, 0xE8);
    st7796_data(lcd, 0x40);
    st7796_data(lcd, 0x8A);
    st7796_data(lcd, 0x00);
    st7796_data(lcd, 0x00);
    st7796_data(lcd, 0x29);
    st7796_data(lcd, 0x19);
    st7796_data(lcd, 0xA5);
    st7796_data(lcd, 0x33);

    st7796_command(lcd, 0xE0);
    st7796_data(lcd, 0xD0);
    st7796_data(lcd, 0x08);
    st7796_data(lcd, 0x0F);
    st7796_data(lcd, 0x06);
    st7796_data(lcd, 0x06);
    st7796_data(lcd, 0x33);
    st7796_data(lcd, 0x30);
    st7796_data(lcd, 0x33);
    st7796_data(lcd, 0x47);
    st7796_data(lcd, 0x17);
    st7796_data(lcd, 0x13);
    st7796_data(lcd, 0x13);
    st7796_data(lcd, 0x2B);
    st7796_data(lcd, 0x31);

    st7796_command(lcd, 0xE1);
    st7796_data(lcd, 0xD0);
    st7796_data(lcd, 0x0A);
    st7796_data(lcd, 0x11);
    st7796_data(lcd, 0x0B);
    st7796_data(lcd, 0x09);
    st7796_data(lcd, 0x07);
    st7796_data(lcd, 0x2F);
    st7796_data(lcd, 0x33);
    st7796_data(lcd, 0x47);
    st7796_data(lcd, 0x38);
    st7796_data(lcd, 0x15);
    st7796_data(lcd, 0x16);
    st7796_data(lcd, 0x2C);
    st7796_data(lcd, 0x32);

    st7796_command(lcd, 0xF0);
    st7796_data(lcd, 0x3C);

    st7796_command(lcd, 0xF0);
    st7796_data(lcd, 0x69);

    st7796_command(lcd, 0x21);
    st7796_command(lcd, 0x11);
    usleep(100000);
    st7796_command(lcd, 0x29);
}

// For image functions, you must convert your image to a uint8_t array in RGB888 format.
// Then convert to RGB565 and send in chunks as in Python.
// Example for show_image_fast:
void st7796_show_image_fast(st7796_t* lcd, uint8_t* img, int im_width, int im_height) {
    // im_width, im_height corresponden a la imagen (height,width en Python si está rotada)
    // Detectar si la imagen está en landscape comparando con las dimensiones internas
    // (igual que en Python: if imwidth == self.height and imheight == self.width)
    int is_landscape = (im_width == lcd->height && im_height == lcd->width);

    int send_w = im_width;
    int send_h = im_height;

    if (is_landscape) {
        // configurar MADCTL a landscape
        st7796_command(lcd, 0x36);
        st7796_data(lcd, 0x78);
        // Python usa set_windows(0,0,height,width,1) -> swap
        st7796_set_windows(lcd, 0, 0, lcd->height - 1, lcd->width - 1, 1);
        send_w = im_width;  // note: pix array will be built from img as given
        send_h = im_height;
    } else {
        // portrait
        st7796_command(lcd, 0x36);
        st7796_data(lcd, 0x08);
        st7796_set_windows(lcd, 0, 0, lcd->width - 1, lcd->height - 1, 0);
    }

    // Convertir RGB888 a RGB565 en buffer único y enviar en chunks de 4096 (como Python)
    size_t total = (size_t)im_width * (size_t)im_height * 2;
    uint8_t* pix = malloc(total);
    if (!pix) return;

    for (int y = 0; y < im_height; y++) {
        for (int x = 0; x < im_width; x++) {
            int in_idx = (y * im_width + x) * 3;
            uint8_t r = img[in_idx];
            uint8_t g = img[in_idx + 1];
            uint8_t b = img[in_idx + 2];
            uint16_t rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
            size_t out_idx = (size_t)(y * im_width + x) * 2;
            pix[out_idx]     = (uint8_t)(rgb565 >> 8);
            pix[out_idx + 1] = (uint8_t)(rgb565 & 0xFF);
        }
    }

    // Dejar DC en datos y enviar en trozos de 4096 bytes (igual que Python)
    st7796_digital_write(lcd->dc_pin, 1);
    const size_t CHUNK = 4096;
    for (size_t i = 0; i < total; i += CHUNK) {
        size_t chunk = (total - i > CHUNK) ? CHUNK : (total - i);
        st7796_spi_writebyte(lcd, pix + i, chunk);
    }

    free(pix);
}

// Helper: vertical flip
void vertical_flip(uint8_t* img, int width, int height) {
    int row_size = width * 3;
    uint8_t* tmp = malloc(row_size);
    for (int y = 0; y < height / 2; y++) {
        memcpy(tmp, img + y * row_size, row_size);
        memcpy(img + y * row_size, img + (height - 1 - y) * row_size, row_size);
        memcpy(img + (height - 1 - y) * row_size, tmp, row_size);
    }
    free(tmp);
}

// Invertir colores de una imagen RGB888 en memoria (in-place)
void invert_colors(uint8_t *img, int width, int height) {
    if (!img || width <= 0 || height <= 0) return;
    size_t total = (size_t)width * (size_t)height * 3;
    for (size_t i = 0; i < total; ++i) {
        img[i] = (uint8_t)(255 - img[i]);
    }
}

// Invertir colores en una región (x,y) de tamaño w x h dentro de una imagen RGB888 (in-place)
void invert_colors_region(uint8_t *img, int img_width, int img_height,
                          int x, int y, int w, int h) {
    if (!img || img_width <= 0 || img_height <= 0) return;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (w <= 0 || h <= 0) return;
    if (x + w > img_width) w = img_width - x;
    if (y + h > img_height) h = img_height - y;

    for (int row = 0; row < h; ++row) {
        size_t base = (size_t)( (y + row) * img_width + x ) * 3;
        for (int col = 0; col < w; ++col) {
            img[base + col*3 + 0] = (uint8_t)(255 - img[base + col*3 + 0]); // R
            img[base + col*3 + 1] = (uint8_t)(255 - img[base + col*3 + 1]); // G
            img[base + col*3 + 2] = (uint8_t)(255 - img[base + col*3 + 2]); // B
        }
    }
}

// Nueva función para encontrar origen
void draw_test_pattern(st7796_t* lcd) {
    st7796_dre_rectangle(lcd, 0, 0, LCD_WIDTH, LCD_HEIGHT, 0xFFFF);

    st7796_dre_rectangle(lcd, 0, 0, 4, 4, 0x0000);
}

int main() {
    st7796_t lcd = {
        .width = LCD_WIDTH,
        .height = LCD_HEIGHT,
        .rst_pin = RST_PIN,
        .dc_pin = DC_PIN,
        .bl_pin = BL_PIN,
        .spi_fd = spi_init(SPI_FREQ, SPI_MODE_0) // You must implement spi_init
    };

    printf("st7796 LCD: %d x %d\n", lcd.width, lcd.height);
    fflush(stdout);

    // Check SPI init
    if (lcd.spi_fd < 0) {
        fprintf(stderr, "ERROR: spi_init failed (fd=%d). Check /dev/spidev0.0 and SPI enabled via raspi-config.\n", lcd.spi_fd);
        fflush(stderr);
        return 1;
    }
    printf("SPI initialized, fd=%d\n", lcd.spi_fd); fflush(stdout);

    // Initialize GPIOs before using them
    st7796_gpio_init(&lcd);

    // Turn backlight on (100%)
    st7796_bl_duty_cycle(&lcd, 100);
    printf("Backlight set (duty=100)\n"); fflush(stdout);

    // Reset sequence (mirror Python: True -> False -> True with 10ms delays)
    st7796_reset(&lcd);
    printf("Reset sequence completed\n"); fflush(stdout);

    st7796_lcd_init(&lcd);
    printf("LCD init done\n"); fflush(stdout);

    // Test pattern para encontrar origen
    draw_test_pattern(&lcd);
    printf("Test pattern drawn\n"); fflush(stdout);

    // Pausa para ver el patrón
    sleep(5);

    // Check image file exists before loading
    const char* image_path = "test.png";
    if (access(image_path, R_OK) != 0) {
        fprintf(stderr, "ERROR: image file '%s' not found or not readable\n", image_path);
        fflush(stderr);
        return 1;
    }

    int img_w, img_h, channels;
    uint8_t* img = stbi_load(image_path, &img_w, &img_h, &channels, 3);
    if (!img) {
        fprintf(stderr, "stbi_load failed: %s\n", stbi_failure_reason());
        fflush(stderr);
        return 1;
    }
    printf("Open image: %s\n", image_path);
    printf("image: %d x %d (channels=%d)\n", img_w, img_h, channels);
    fflush(stdout);

    // Resize to screen dimensions (simple nearest-neighbor)
    int resized_w = LCD_WIDTH, resized_h = LCD_HEIGHT;
    uint8_t* img_disp = malloc(resized_w * resized_h * 3);
    for (int y = 0; y < resized_h; y++) {
        for (int x = 0; x < resized_w; x++) {
            int src_x = x * img_w / resized_w;
            int src_y = y * img_h / resized_h;
            memcpy(&img_disp[(y * resized_w + x) * 3],
                   &img[(src_y * img_w + src_x) * 3], 3);
        }
    }
    printf("img_resized: %d x %d\n", resized_w, resized_h);

    // Optional: invert colors
    invert_colors(img_disp, resized_w, resized_h);

    printf("of type: uint8_t* (RGB888)\n");
    st7796_show_image_fast(&lcd, img_disp, LCD_WIDTH, LCD_HEIGHT);
    printf("Image transferred to LCD (attempted)\n");
    fflush(stdout);

    // Clean up
    stbi_image_free(img);
    free(img_disp);
    spi_close(lcd.spi_fd);

    return 0;
}
