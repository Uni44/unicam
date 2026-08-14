import time

try:
    import smbus
except Exception:  # pragma: no cover - entorno sin SMBus
    smbus = None


class Focuser:
    bus = None
    CHIP_I2C_ADDR = 0x0C
    BUSY_REG_ADDR = 0x04

    OPT_BASE = 0x1000
    OPT_FOCUS = OPT_BASE | 0x01
    OPT_ZOOM = OPT_BASE | 0x02
    OPT_MOTOR_X = OPT_BASE | 0x03   # pan (si tu lente lo soporta)
    OPT_MOTOR_Y = OPT_BASE | 0x04   # tilt
    OPT_IRCUT = OPT_BASE | 0x05

    opts = {
        OPT_FOCUS: {"REG_ADDR": 0x01, "MIN_VALUE": 0, "MAX_VALUE": 20000, "RESET_ADDR": 0x0B},
        OPT_ZOOM: {"REG_ADDR": 0x00, "MIN_VALUE": 3000, "MAX_VALUE": 20000, "RESET_ADDR": 0x0A},
        OPT_IRCUT: {"REG_ADDR": 0x0C, "MIN_VALUE": 0x00, "MAX_VALUE": 0x01, "RESET_ADDR": None},
    }

    def __init__(self, bus):
        if smbus is None:
            raise RuntimeError("smbus no está disponible")
        self.bus = None
        try:
            self.bus = smbus.SMBus(bus)  # en RPi normalmente bus=0 ó 1
        except Exception as exc:
            self.bus = None
            raise RuntimeError(f"No se pudo abrir el bus I2C {bus}: {exc}")

    def read(self, chip_addr, reg_addr):
        if self.bus is None:
            return 0
        value = self.bus.read_word_data(chip_addr, reg_addr)
        return ((value & 0x00FF) << 8) | ((value & 0xFF00) >> 8)

    def write(self, chip_addr, reg_addr, value):
        if self.bus is None:
            return False
        if value < 0:
            value = 0
        value = ((value & 0x00FF) << 8) | ((value & 0xFF00) >> 8)
        return self.bus.write_word_data(chip_addr, reg_addr, value)

    def isBusy(self):
        return self.read(self.CHIP_I2C_ADDR, self.BUSY_REG_ADDR) != 0

    def waitingForFree(self):
        if self.bus is None:
            return
        count = 0
        while self.isBusy() and count < 500:  # timeout ~5s
            count += 1
            time.sleep(0.01)

    def get(self, opt):
        self.waitingForFree()
        info = self.opts[opt]
        return self.read(self.CHIP_I2C_ADDR, info["REG_ADDR"])

    def set(self, opt, value, flag=1):
        if self.bus is None:
            return False
        self.waitingForFree()
        info = self.opts[opt]
        value = max(info["MIN_VALUE"], min(info["MAX_VALUE"], value))
        self.write(self.CHIP_I2C_ADDR, info["REG_ADDR"], value)
        if flag & 0x01:
            self.waitingForFree()
        return True