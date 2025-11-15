CC = gcc
CFLAGS = -Wall -O2
SRC = st7796_driver.c spi_gpio.c
OUT = st7796_test
LDFLAGS = -lm
RUNCMD = sudo ./$(OUT)

all: stb_image.h $(OUT)

stb_image.h:
	@if [ -f stb_image.h ]; then \
		echo "stb_image.h already present"; \
	else \
		echo "Downloading stb_image.h..."; \
		( command -v curl >/dev/null 2>&1 && curl -fsSL -o stb_image.h https://raw.githubusercontent.com/nothings/stb/master/stb_image.h ) || \
		( command -v wget >/dev/null 2>&1 && wget -q -O stb_image.h https://raw.githubusercontent.com/nothings/stb/master/stb_image.h ); \
		if [ ! -f stb_image.h ]; then \
			echo "Failed to download stb_image.h. Please install curl or wget or place stb_image.h in the project folder."; \
			exit 1; \
		fi \
	fi

$(OUT): $(SRC) stb_image.h
	$(CC) $(CFLAGS) -o $(OUT) $(SRC) $(LDFLAGS)

install-deps:
	sudo apt update && sudo apt install -y build-essential wget curl

# Ejecuta el binario con sudo (necesario para /dev/spidev y sysfs GPIO)
run: $(OUT)
	@echo "Running $(OUT) with sudo (required for SPI/GPIO access)"
	$(RUNCMD)

clean:
	rm -f $(OUT)
