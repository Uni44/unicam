import time
import spidev
import logging
import numpy as np
from gpiozero import *

#SPI_Freq = 40000000     # SPI 时钟频率
SPI_Freq = 80000000  # 62.5 MHz
SPI_Mode = 0            # 模式0
BL_Freq  = 1000         # PWM 频率（背光）
#RST_PIN  = 27
#DC_PIN   = 25
#BL_PIN   = 18
RST_PIN = 25   # porque conectaste RESET a GPIO 25
DC_PIN  = 24   # porque conectaste DC a GPIO 24
BL_PIN  = 18   # si usás el GPIO 18 para el backlight

class st7796():
    def __init__(self):
        self.np=np
        self.width  = 320
        self.height = 480 
        
        self.GPIO_RST_PIN = DigitalOutputDevice(RST_PIN,active_high = True,initial_value =True)    # RST 设置为输出 参数：引脚，高电平有效，默认高          # 使用GPIO Zero库中的DigitalOutputDevice类
        self.GPIO_DC_PIN  = DigitalOutputDevice(DC_PIN,active_high = True,initial_value =True)     # DC 设置为输出 参数：引脚，高电平有效，默认高           # 使用GPIO Zero库中的DigitalOutputDevice类
        self.GPIO_BL_PIN  = PWMOutputDevice(BL_PIN,frequency = BL_Freq)                            # BL 设置为PWM  参数：引脚，PWM 频率                    # 使用GPIO Zero库中的PWMOutputDevice类
        self.bl_DutyCycle(100)    
        #Initialize SPI
        self.SPI = spidev.SpiDev(0,0)
        self.SPI.max_speed_hz = SPI_Freq  
        self.SPI.mode = 0b00   
        
        self.lcd_init()
    
    def bl_DutyCycle(self, duty):                   # 设置 PWM 占空比
        self.GPIO_BL_PIN.value = duty / 100

    
    
    def digital_write(self, Pin, value):
        if value:
            Pin.on()
        else:
            Pin.off()
            
    def spi_writebyte(self, data):
        if self.SPI!=None :
            self.SPI.writebytes(data)
    
    def command(self, cmd):
        self.digital_write(self.GPIO_DC_PIN, False)
        self.spi_writebyte([cmd])   
        
    def data(self, val):
        self.digital_write(self.GPIO_DC_PIN, True)
        self.spi_writebyte([val])  
        
    def reset(self):
        """Reset the display"""
        self.digital_write(self.GPIO_RST_PIN,True)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN,False)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN,True)
        time.sleep(0.01)
    
    def dre_rectangle(self, Xstart, Ystart, Xend, Yend, color):
        color_high = (color >> 8) & 0xFF
        color_low = color & 0xFF
            
        self.set_windows( Xstart, Ystart, Xend, Yend) 
        for a in range (Xstart, Xend+1):
            for b in range (Ystart , Yend + 1):
                self.data(color_high)
                self.data(color_low)
    
    def lcd_init(self):
        self.reset()
        self.command(0x11)      
        time.sleep(0.12)

        self.command(0x36)      # Memory Data Access Control MY,MX~~
        self.data(0x08)    

        self.command(0x3A)      
        self.data(0x05)    # self.data(0x66) 

        self.command(0xF0)      # Command Set Control
        self.data(0xC3)    

        self.command(0xF0)      
        self.data(0x96)    

        self.command(0xB4)      
        self.data(0x01)    

        self.command(0xB7)      
        self.data(0xC6)    

        self.command(0xC0)      
        self.data(0x80)    
        self.data(0x45)    

        self.command(0xC1)      
        self.data(0x13)    # 18  #00

        self.command(0xC2)      
        self.data(0xA7)    

        self.command(0xC5)      
        self.data(0x0A)    

        self.command(0xE8)      
        self.data(0x40) 
        self.data(0x8A) 
        self.data(0x00) 
        self.data(0x00) 
        self.data(0x29) 
        self.data(0x19) 
        self.data(0xA5) 
        self.data(0x33) 

        self.command(0xE0) 
        self.data(0xD0) 
        self.data(0x08) 
        self.data(0x0F) 
        self.data(0x06) 
        self.data(0x06) 
        self.data(0x33) 
        self.data(0x30) 
        self.data(0x33) 
        self.data(0x47) 
        self.data(0x17) 
        self.data(0x13) 
        self.data(0x13) 
        self.data(0x2B) 
        self.data(0x31) 

        self.command(0xE1) 
        self.data(0xD0) 
        self.data(0x0A) 
        self.data(0x11) 
        self.data(0x0B) 
        self.data(0x09) 
        self.data(0x07) 
        self.data(0x2F) 
        self.data(0x33) 
        self.data(0x47) 
        self.data(0x38) 
        self.data(0x15) 
        self.data(0x16) 
        self.data(0x2C) 
        self.data(0x32) 
    
        self.command(0xF0)      
        self.data(0x3C)    

        self.command(0xF0)      
        self.data(0x69)    
        
        
        self.command(0x21)

        self.command(0x11)

        time.sleep(0.1)

        self.command(0x29)
        
    def set_windows(self, Xstart, Ystart, Xend, Yend, horizontal = 0):
        if horizontal:  
            #set the X coordinates
            self.command(0x2A)
            self.data(Xstart>>8)         #Set the horizontal starting point to the high octet
            self.data(Xstart & 0xff)     #Set the horizontal starting point to the low octet
            self.data(Xend>>8)         #Set the horizontal end to the high octet
            self.data((Xend) & 0xff)   #Set the horizontal end to the low octet 
            #set the Y coordinates
            self.command(0x2B)
            self.data(Ystart>>8)
            self.data((Ystart & 0xff))
            self.data(Yend>>8)
            self.data((Yend) & 0xff)
            self.command(0x2C)
        else:
            #set the X coordinates
            self.command(0x2A)
            self.data(Xstart>>8)        #Set the horizontal starting point to the high octet
            self.data(Xstart & 0xff)    #Set the horizontal starting point to the low octet
            self.data(Xend>>8)        #Set the horizontal end to the high octet
            self.data((Xend) & 0xff)  #Set the horizontal end to the low octet 
            #set the Y coordinates
            self.command(0x2B)
            self.data(Ystart>>8)
            self.data((Ystart & 0xff))
            self.data(Yend>>8)
            self.data((Yend) & 0xff)
            self.command(0x2C)     
    
    
    def show_image_windows(self, Xstart, Ystart, Xend, Yend, Image):
        # """Set buffer to value of Python Imaging Library image."""
        # """Write display buffer to physical display"""
        imwidth, imheight = Image.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError('Image must be same dimensions as display \
                ({0}x{1}).' .format(self.width, self.height))
        img = self.np.asarray(Image)
        pix = self.np.zeros((imheight,imwidth , 2), dtype = self.np.uint8)
        #RGB888 >> RGB565
        pix[...,[0]] = self.np.add(self.np.bitwise_and(img[...,[0]],0xF8),self.np.right_shift(img[...,[1]],5))
        pix[...,[1]] = self.np.add(self.np.bitwise_and(self.np.left_shift(img[...,[1]],3),0xE0), self.np.right_shift(img[...,[2]],3))
        pix = pix.flatten().tolist()
            
        if Xstart > Xend:
            data = Xstart
            Xstart = Xend
            Xend = data
            
        if Ystart > Yend:        
            data = Ystart
            Ystart = Yend
            Yend = data
        
        if Xend < self.width - 1:
            Xend = Xend + 1
        if Yend < self.width - 1:
            Yend = Yend + 1
            
        self.set_windows( Xstart, Ystart, Xend, Yend)
        self.digital_write(self.GPIO_DC_PIN,True)
        
        for i in range (Ystart,Yend):             
            Addr = ((Xstart) + (i * 240)) * 2        
            self.spi_writebyte(pix[Addr : Addr+((Xend-Xstart+1)*2)])

    def show_image(self, Image):
        """Set buffer to value of Python Imaging Library image."""
        """Write display buffer to physical display"""
        imwidth, imheight = Image.size
        if imwidth == self.height and imheight ==  self.width:
            # print("Landscape screen")
            img = self.np.asarray(Image)
            pix = self.np.zeros((self.width, self.height,2), dtype = self.np.uint8)
            #RGB888 >> RGB565
            pix[...,[0]] = self.np.add(self.np.bitwise_and(img[...,[0]],0xF8),self.np.right_shift(img[...,[1]],5))
            pix[...,[1]] = self.np.add(self.np.bitwise_and(self.np.left_shift(img[...,[1]],3),0xE0), self.np.right_shift(img[...,[2]],3))
            pix = pix.flatten().tolist()
            
            self.command(0x36)
            self.data(0x78)
            self.set_windows(0, 0, self.height,self.width, 1)
            self.digital_write(self.GPIO_DC_PIN,True)
            for i in range(0,len(pix),4096):
                self.spi_writebyte(pix[i:i+4096])
        else :
            # print("Portrait screen")
            img = self.np.asarray(Image)
            pix = self.np.zeros((imheight,imwidth , 2), dtype = self.np.uint8)
            
            pix[...,[0]] = self.np.add(self.np.bitwise_and(img[...,[0]],0xF8),self.np.right_shift(img[...,[1]],5))
            pix[...,[1]] = self.np.add(self.np.bitwise_and(self.np.left_shift(img[...,[1]],3),0xE0), self.np.right_shift(img[...,[2]],3))
            pix = pix.flatten().tolist()
            
            self.command(0x36)
            self.data(0x08)
            self.set_windows(0, 0, self.width, self.height, 0)
            self.digital_write(self.GPIO_DC_PIN,True)
        for i in range(0, len(pix), 4096):
            self.spi_writebyte(pix[i: i+4096])

    
    def clear(self):
        """Clear contents of image buffer"""
        _buffer = [0xff] * (self.width*self.height*2)
        self.set_windows(0, 0, self.width, self.height)
        self.digital_write(self.GPIO_DC_PIN,True)
        for i in range(0, len(_buffer), 4096):
            self.spi_writebyte(_buffer[i: i+4096])
    
    def show_image_fast(self, Image):
        import numpy as np

        img = np.asarray(Image)
        height, width = img.shape[:2]

        # Convertir RGB888 a RGB565
        pix = np.zeros((height, width, 2), dtype=np.uint8)
        pix[..., 0] = (img[..., 0] & 0xF8) | (img[..., 1] >> 5)
        pix[..., 1] = ((img[..., 1] << 3) & 0xE0) | (img[..., 2] >> 3)

        pix_bytes = pix.flatten().tolist()  # spidev necesita lista
        self.set_windows(0, 0, width-1, height-1)
        self.digital_write(self.GPIO_DC_PIN, True)

        max_chunk = 4096  # SPI límite
        for i in range(0, len(pix_bytes), max_chunk):
            self.spi_writebyte(pix_bytes[i:i+max_chunk])