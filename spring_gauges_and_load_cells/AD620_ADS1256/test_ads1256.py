#!/usr/bin/env python3
"""
Simple ADS1256 Test Script
Tests basic communication with the ADS1256 ADC
"""

import time
import spidev
import RPi.GPIO as GPIO

# Pin Configuration
CS_PIN = 22
DRDY_PIN = 17

# ADS1256 Commands
CMD_RESET = 0xFE
CMD_RREG = 0x10
CMD_WREG = 0x50

# Registers
REG_STATUS = 0x00
REG_MUX = 0x01
REG_ADCON = 0x02
REG_DRATE = 0x03

def main():
    print("=== ADS1256 Basic Communication Test ===\n")
    
    # Setup GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(CS_PIN, GPIO.OUT)
    GPIO.setup(DRDY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.output(CS_PIN, GPIO.HIGH)
    
    # Setup SPI
    spi = spidev.SpiDev()
    try:
        spi.open(0, 0)
        spi.max_speed_hz = 1000000
        spi.mode = 0b01
        print("✓ SPI opened successfully")
    except Exception as e:
        print(f"✗ Failed to open SPI: {e}")
        print("  Make sure SPI is enabled: sudo raspi-config")
        return
    
    # Test 1: Reset
    print("\nTest 1: Sending RESET command...")
    try:
        GPIO.output(CS_PIN, GPIO.LOW)
        spi.writebytes([CMD_RESET])
        GPIO.output(CS_PIN, GPIO.HIGH)
        time.sleep(0.1)
        print("✓ RESET command sent")
    except Exception as e:
        print(f"✗ RESET failed: {e}")
        spi.close()
        GPIO.cleanup()
        return
    
    # Test 2: Read STATUS register
    print("\nTest 2: Reading STATUS register...")
    try:
        GPIO.output(CS_PIN, GPIO.LOW)
        spi.writebytes([CMD_RREG | (REG_STATUS & 0x0F), 0x00])
        result = spi.readbytes(1)
        GPIO.output(CS_PIN, GPIO.HIGH)
        print(f"✓ STATUS register: 0x{result[0]:02X}")
        
        # Decode status
        if result[0] & 0x01:
            print("  - Buffer enabled")
        else:
            print("  - Buffer disabled")
    except Exception as e:
        print(f"✗ Read STATUS failed: {e}")
    
    # Test 3: Read ADCON register  
    print("\nTest 3: Reading ADCON register...")
    try:
        GPIO.output(CS_PIN, GPIO.LOW)
        spi.writebytes([CMD_RREG | (REG_ADCON & 0x0F), 0x00])
        result = spi.readbytes(1)
        GPIO.output(CS_PIN, GPIO.HIGH)
        print(f"✓ ADCON register: 0x{result[0]:02X}")
        
        # Decode ADCON
        gain = result[0] & 0x07
        gain_values = [1, 2, 4, 8, 16, 32, 64, 64]
        print(f"  - PGA Gain: {gain_values[gain]}x")
    except Exception as e:
        print(f"✗ Read ADCON failed: {e}")
    
    # Test 4: Check DRDY pin
    print("\nTest 4: Checking DRDY pin...")
    drdy_state = GPIO.input(DRDY_PIN)
    print(f"  DRDY pin state: {'HIGH' if drdy_state else 'LOW'}")
    if drdy_state == 0:
        print("✓ DRDY is LOW (data ready - good!)")
    else:
        print("  DRDY is HIGH (waiting or issue)")
    
    # Test 5: Write and read back a register
    print("\nTest 5: Write/read test (DRATE register)...")
    try:
        # Write value 0x82 (100 SPS)
        GPIO.output(CS_PIN, GPIO.LOW)
        spi.writebytes([CMD_WREG | (REG_DRATE & 0x0F), 0x00, 0x82])
        GPIO.output(CS_PIN, GPIO.HIGH)
        time.sleep(0.01)
        
        # Read back
        GPIO.output(CS_PIN, GPIO.LOW)
        spi.writebytes([CMD_RREG | (REG_DRATE & 0x0F), 0x00])
        result = spi.readbytes(1)
        GPIO.output(CS_PIN, GPIO.HIGH)
        
        if result[0] == 0x82:
            print(f"✓ Write/read successful: 0x{result[0]:02X}")
        else:
            print(f"⚠ Write/read mismatch: wrote 0x82, read 0x{result[0]:02X}")
    except Exception as e:
        print(f"✗ Write/read test failed: {e}")
    
    # Cleanup
    spi.close()
    GPIO.cleanup()
    
    print("\n=== Test Complete ===")
    print("\nIf all tests passed, your ADS1256 is communicating correctly!")
    print("You can now run: python3 ads1256_load_cells.py")
    print("\nIf tests failed, check:")
    print("  1. SPI is enabled (sudo raspi-config)")
    print("  2. Wiring connections (especially CS and DRDY pins)")
    print("  3. Power to ADS1256 board")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        try:
            GPIO.cleanup()
        except:
            pass
