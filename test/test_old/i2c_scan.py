import smbus

def scan_i2c():
    # 创建 SMBus 对象，表示 I2C-1 总线
    bus = smbus.SMBus(1)  # 树莓派的 I2C-1 总线编号为 1
    devices = []

    # 扫描 I2C 地址 0x03 到 0x77
    for address in range(0x03, 0x78):
        try:
            # 尝试读取每个地址的一个字节，检查设备是否响应
            bus.read_byte(address)
            devices.append(hex(address))
        except OSError:
            # 地址未被设备响应，继续扫描
            pass
    
    if devices:
        print("I2C devices found at the following addresses:")
        for device in devices:
            print(f" - {device}")
    else:
        print("No I2C devices found.")
    
    # 关闭 I2C 总线
    bus.close()

if __name__ == '__main__':
    scan_i2c()
