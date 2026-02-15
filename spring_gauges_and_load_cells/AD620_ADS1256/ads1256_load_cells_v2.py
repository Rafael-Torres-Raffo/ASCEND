#!/usr/bin/env python3
"""
Dual Load Cell Reader using AD620 Amplifiers + ADS1256 ADC
Setup: Load Cell -> AD620 (amplifier) -> ADS1256 (ADC) -> Raspberry Pi
Version 2: Uses lgpio (compatible with ALL Pi models including Pi 5)
"""

import time
import spidev
import lgpio

# --- ADS1256 Register Definitions ---
REG_STATUS = 0x00
REG_MUX = 0x01
REG_ADCON = 0x02
REG_DRATE = 0x03
REG_IO = 0x04

# --- ADS1256 Commands ---
CMD_WAKEUP = 0x00
CMD_RDATA = 0x01
CMD_RDATAC = 0x03
CMD_SDATAC = 0x0F
CMD_RREG = 0x10
CMD_WREG = 0x50
CMD_SELFCAL = 0xF0
CMD_SYNC = 0xFC
CMD_STANDBY = 0xFD
CMD_RESET = 0xFE

# --- Data Rate Settings (samples/sec) ---
DRATE_30000 = 0xF0
DRATE_15000 = 0xE0
DRATE_7500 = 0xD0
DRATE_3750 = 0xC0
DRATE_2000 = 0xB0
DRATE_1000 = 0xA1
DRATE_500 = 0x92
DRATE_100 = 0x82
DRATE_60 = 0x72
DRATE_50 = 0x63
DRATE_30 = 0x53
DRATE_25 = 0x43
DRATE_15 = 0x33
DRATE_10 = 0x23
DRATE_5 = 0x13
DRATE_2_5 = 0x03

# --- Gain Settings ---
GAIN_1 = 0x00
GAIN_2 = 0x01
GAIN_4 = 0x02
GAIN_8 = 0x03
GAIN_16 = 0x04
GAIN_32 = 0x05
GAIN_64 = 0x06


class ADS1256:
    """Driver for ADS1256 ADC using lgpio"""
    
    def __init__(self, cs_pin=22, drdy_pin=17, spi_bus=0, spi_device=0):
        """
        Initialize ADS1256
        cs_pin: Chip Select (BCM GPIO number)
        drdy_pin: Data Ready (BCM GPIO number)
        """
        self.cs_pin = cs_pin
        self.drdy_pin = drdy_pin
        
        # Setup GPIO using lgpio
        self.h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self.h, self.cs_pin)
        lgpio.gpio_claim_input(self.h, self.drdy_pin)
        lgpio.gpio_write(self.h, self.cs_pin, 1)  # CS high
        
        # Setup SPI
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = 1000000  # 1MHz
        self.spi.mode = 0b01  # CPOL=0, CPHA=1
        
        # Initialize ADC
        self.reset()
        time.sleep(0.5)
        
    def reset(self):
        """Reset the ADC"""
        self._cs_low()
        self.spi.writebytes([CMD_RESET])
        time.sleep(0.1)
        self._cs_high()
        
    def _cs_low(self):
        lgpio.gpio_write(self.h, self.cs_pin, 0)
        
    def _cs_high(self):
        lgpio.gpio_write(self.h, self.cs_pin, 1)
        
    def _wait_drdy(self, timeout=1.0):
        """Wait for DRDY to go low (data ready)"""
        start = time.time()
        while lgpio.gpio_read(self.h, self.drdy_pin):
            if time.time() - start > timeout:
                return False
            time.sleep(0.0001)
        return True
        
    def write_reg(self, reg, value):
        """Write to a register"""
        self._cs_low()
        self.spi.writebytes([CMD_WREG | (reg & 0x0F), 0x00, value])
        self._cs_high()
        
    def read_reg(self, reg):
        """Read from a register"""
        self._cs_low()
        self.spi.writebytes([CMD_RREG | (reg & 0x0F), 0x00])
        result = self.spi.readbytes(1)
        self._cs_high()
        return result[0]
        
    def set_channel(self, pos_ch, neg_ch=8):
        """
        Set input channel
        pos_ch: Positive input (0-7 for AIN0-AIN7)
        neg_ch: Negative input (0-7 for AIN0-AIN7, 8 for AINCOM)
        """
        mux_value = (pos_ch << 4) | (neg_ch & 0x0F)
        self.write_reg(REG_MUX, mux_value)
        
    def set_data_rate(self, drate):
        """Set data rate"""
        self.write_reg(REG_DRATE, drate)
        
    def set_gain(self, gain):
        """Set PGA gain"""
        adcon = self.read_reg(REG_ADCON)
        adcon = (adcon & 0xF8) | (gain & 0x07)
        self.write_reg(REG_ADCON, adcon)
        
    def calibrate(self):
        """Perform self-calibration"""
        self._cs_low()
        self.spi.writebytes([CMD_SELFCAL])
        self._cs_high()
        time.sleep(0.5)
        
    def read_raw(self):
        """Read raw 24-bit value from current channel"""
        self._cs_low()
        
        # Send SYNC and WAKEUP
        self.spi.writebytes([CMD_SYNC])
        time.sleep(0.00001)
        self.spi.writebytes([CMD_WAKEUP])
        time.sleep(0.00001)
        
        # Wait for DRDY
        if not self._wait_drdy():
            self._cs_high()
            return None
            
        # Read data
        self.spi.writebytes([CMD_RDATA])
        time.sleep(0.00001)
        data = self.spi.readbytes(3)
        self._cs_high()
        
        # Convert to signed 24-bit value
        value = (data[0] << 16) | (data[1] << 8) | data[2]
        if value & 0x800000:  # Check sign bit
            value -= 0x1000000
        
        return value
    
    def read_channel(self, pos_ch, neg_ch=8):
        """Read from a specific channel"""
        self.set_channel(pos_ch, neg_ch)
        time.sleep(0.01)  # Allow settling
        return self.read_raw()
    
    def cleanup(self):
        """Cleanup resources"""
        self.spi.close()
        lgpio.gpiochip_close(self.h)


def read_avg_raw(ads, channel, samples=5):
    """Read average of multiple samples from a channel"""
    vals = []
    for _ in range(samples):
        v = ads.read_channel(channel)
        if v is None:
            return None
        vals.append(v)
        time.sleep(0.005)
    return sum(vals) / len(vals)


def main():
    print("=== TWO LOAD CELLS with AD620 + ADS1256 (v2 - lgpio) ===")
    print("\nWiring Guide:")
    print("  ADS1256 -> Raspberry Pi:")
    print("    VCC -> 5V")
    print("    GND -> GND")
    print("    SCLK -> GPIO 11 (SPI0 SCLK)")
    print("    DIN -> GPIO 10 (SPI0 MOSI)")
    print("    DOUT -> GPIO 9 (SPI0 MISO)")
    print("    CS -> GPIO 22 (configurable)")
    print("    DRDY -> GPIO 17 (configurable)")
    print("    PDWN -> VCC (keep powered on)")
    print("\n  AD620 Outputs -> ADS1256:")
    print("    AD620 #1 Output -> AIN0")
    print("    AD620 #2 Output -> AIN1")
    print("    AD620 GND -> AGND")
    print()
    
    # Configuration
    CS_PIN = 22       # Chip Select
    DRDY_PIN = 17     # Data Ready
    CHANNEL_1 = 0     # AIN0 for first load cell
    CHANNEL_2 = 1     # AIN1 for second load cell
    DATA_RATE = DRATE_100  # 100 samples/second
    GAIN = GAIN_1     # Gain=1 (AD620 already amplifies)
    SAMPLES_PER_PRINT = 5
    PRINT_HZ = 10
    
    print(f"Configuration:")
    print(f"  CS Pin: GPIO {CS_PIN}")
    print(f"  DRDY Pin: GPIO {DRDY_PIN}")
    print(f"  Channel 1 (Load Cell 1): AIN{CHANNEL_1}")
    print(f"  Channel 2 (Load Cell 2): AIN{CHANNEL_2}")
    print(f"  Data Rate: 100 SPS")
    print(f"  ADC Gain: 1x (AD620 provides amplification)")
    print()
    
    # Initialize ADC
    ads = ADS1256(cs_pin=CS_PIN, drdy_pin=DRDY_PIN)
    ads.set_data_rate(DATA_RATE)
    ads.set_gain(GAIN)
    
    print("Calibrating ADC...")
    ads.calibrate()
    print("Calibration complete.")
    
    # Tare both channels
    print("\nTaring both load cells... keep unloaded for ~1 second.")
    tare1 = read_avg_raw(ads, CHANNEL_1, samples=20)
    tare2 = read_avg_raw(ads, CHANNEL_2, samples=20)
    
    if tare1 is None or tare2 is None:
        print("Failed to read during tare. Check wiring/connections.")
        ads.cleanup()
        return
    
    print(f"Tare1 (AIN{CHANNEL_1}): {tare1:.0f}")
    print(f"Tare2 (AIN{CHANNEL_2}): {tare2:.0f}")
    print("\nReading load cells... (Ctrl+C to stop)")
    print()
    
    period = 1.0 / PRINT_HZ
    
    try:
        while True:
            r1 = read_avg_raw(ads, CHANNEL_1, samples=SAMPLES_PER_PRINT)
            r2 = read_avg_raw(ads, CHANNEL_2, samples=SAMPLES_PER_PRINT)
            
            s1 = "invalid" if r1 is None else f"{r1:.0f} (Δ {r1 - tare1:+.0f})"
            s2 = "invalid" if r2 is None else f"{r2:.0f} (Δ {r2 - tare2:+.0f})"
            
            print(f"LC1 (AIN{CHANNEL_1}): {s1}   |   LC2 (AIN{CHANNEL_2}): {s2}")
            time.sleep(period)
            
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        ads.cleanup()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
