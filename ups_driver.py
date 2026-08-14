import smbus
import time


def classify_current_state(current_a):
    """Devuelve el estado eléctrico de la UPS según el signo de la corriente.

    current_a > 0  -> cargando
    current_a < 0  -> descargándose
    current_a == 0 -> inactivo
    """
    try:
        current = float(current_a)
    except (TypeError, ValueError):
        return "unknown"
    if current > 0:
        return "charging"
    if current < 0:
        return "discharging"
    return "idle"


class INA219:
    def __init__(self, i2c_bus=1, addr=0x40):
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr
        self._current_lsb = 0.1524 
        self._cal_value = 26868
        self._power_lsb = 0.003048
        self.config_sensor()

    def write(self, address, data):
        temp = [(data & 0xFF00) >> 8, data & 0xFF]
        self.bus.write_i2c_block_data(self.addr, address, temp)

    def read(self, address):
        data = self.bus.read_i2c_block_data(self.addr, address, 2)
        return ((data[0] << 8) | data[1])

    def config_sensor(self):
        self.write(0x05, self._cal_value) # Registro de calibración
        # Configuración: 16V, Gain /2, 12-bit, 32 samples, Continuous
        config = (0x00 << 13 | 0x01 << 11 | 0x0D << 7 | 0x0D << 3 | 0x07)
        self.write(0x00, config)

    def get_stats(self):
        """Retorna un diccionario con los datos listos para JSON/Frontend"""
        try:
            # Lecturas directas
            bus_voltage = (self.read(0x02) >> 3) * 0.004

            raw_current = self.read(0x04)
            if raw_current > 32767: raw_current -= 65535
            current_ma = raw_current * self._current_lsb
            current_a = current_ma / 1000

            raw_power = self.read(0x03)
            power_w = raw_power * self._power_lsb

            # Cálculo de porcentaje de batería (basado en tu lógica de 9V a 12.6V aprox)
            percent = (bus_voltage - 9) / 3.6 * 100
            percent = max(0, min(100, percent))
            power_state = classify_current_state(current_a)

            return {
                "status": "online",
                "power_state": power_state,
                "voltage_v": round(bus_voltage, 3),
                "current_a": round(current_a, 6),
                "power_w": round(power_w, 3),
                "battery_percent": round(percent, 1)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}