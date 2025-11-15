import time
import smbus
from gpiozero import *
import RPi.GPIO   


FT6336U_ADDRESS = 0x38

FT6336U_LCD_TOUCH_MAX_POINTS = 2

TP_INT   = 4
TP_RST   = 17

    


class ft6336u():
    def __init__(self):
        self.GPIO = RPi.GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        # #Initialize I2C
        self.I2C = smbus.SMBus(1)
        # self.GPIO.setup(TP_INT, self.GPIO.IN,self.GPIO.PUD_UP)
        self.GPIO.setup(TP_RST, self.GPIO.OUT)
        # self.GPIO.add_event_detect(TP_INT,self.GPIO.FALLING,self.Int_Callback,5) 
        # pass
        self.GPIO_TP_INT = Button(TP_INT)                                                  # 使用GPIO Zero库中的Button类
        # self.GPIO_TP_RST = DigitalOutputDevice(TP_RST,active_high = True,initial_value =True)   # 使用GPIO Zero库中的DigitalOutputDevice类
        # self.GPIO_TP_INT.when_pressed = self.Int_Callback  # 中断函数
        
        self.coordinates = [{"x": 0, "y": 0} for _ in range(FT6336U_LCD_TOUCH_MAX_POINTS)]
        self.point_count = 0
        self.touch_rst()
    
    def Int_Callback(self):
        self.read_touch_data()
    
    #Reset  复位    
    def touch_rst(self):
        self.GPIO.output(TP_RST, 0)  
        time.sleep(1 / 1000.0)
        self.GPIO.output(TP_RST, 1)  
        time.sleep(50 / 1000.0)
        
        
    def write_cmd(self, cmd):
        self.I2C.write_byte(FT6336U_ADDRESS, data)

    def read_bytes(self, reg_addr, length):
        # 发送寄存器地址并读取多个字节
        data = self.I2C.read_i2c_block_data(FT6336U_ADDRESS, reg_addr, length)
        return data
    
    def read_touch_data(self):
        TOUCH_NUM_REG = 0x02
        TOUCH_XY_REG = 0x03
        
        buf = self.read_bytes(TOUCH_NUM_REG, 1)
        
        if buf and buf[0] != 0:
            self.point_count = buf[0]
            buf = self.read_bytes(TOUCH_XY_REG, 6 * self.point_count)
            for i in range(2):
                self.coordinates[i]["x"] = 0
                self.coordinates[i]["y"] = 0
            
            if buf:
                for i in range(self.point_count):
                    self.coordinates[i]["x"] = 319 - (((buf[(i * 6) + 0] & 0x0f) << 8) + buf[(i * 6) + 1])
                    self.coordinates[i]["y"] = ((buf[(i * 6) + 2] & 0x0f) << 8) + buf[(i * 6) + 3]
    
    def get_touch_xy(self):
        point = self.point_count
        # 将触摸点数重置为 0
        self.point_count = 0

        if point != 0:
            # 返回触摸状态和坐标
            return point, self.coordinates
        else:
            # 返回 0 和空坐标列表
            return 0 , []
    
    
        