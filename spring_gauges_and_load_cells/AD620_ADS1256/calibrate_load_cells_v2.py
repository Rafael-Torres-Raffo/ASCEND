#!/usr/bin/env python3
"""
Load Cell Calibration Helper v2
Easier, step-by-step calibration with live preview
"""

import time
import sys
from ads1256_load_cells_v2 import ADS1256, read_avg_raw, DRATE_100, GAIN_1

# Configuration
CS_PIN = 22
DRDY_PIN = 17
CHANNEL_1 = 0
CHANNEL_2 = 1

def print_header(text):
    """Print a nice header"""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def get_stable_reading(ads, channel, channel_name, duration=3):
    """Get a stable reading with live preview"""
    print(f"\n  Reading {channel_name} for {duration} seconds...")
    print(f"  Watch the values stabilize:\n")
    
    readings = []
    start_time = time.time()
    
    while time.time() - start_time < duration:
        val = ads.read_channel(channel)
        if val is not None:
            readings.append(val)
            # Show last 5 readings
            if len(readings) % 5 == 0:
                recent = readings[-5:]
                avg = sum(recent) / len(recent)
                std = (sum((x - avg) ** 2 for x in recent) / len(recent)) ** 0.5
                print(f"    Current: {val:8.0f}  |  Avg (last 5): {avg:8.0f}  |  StdDev: {std:6.1f}")
        time.sleep(0.1)
    
    if len(readings) < 10:
        print("\n  ⚠ Warning: Not enough readings collected")
        return None
    
    # Calculate statistics
    avg = sum(readings) / len(readings)
    std_dev = (sum((x - avg) ** 2 for x in readings) / len(readings)) ** 0.5
    
    print(f"\n  ✓ Collected {len(readings)} readings")
    print(f"  Final Average: {avg:.2f}")
    print(f"  Std Deviation: {std_dev:.2f}")
    
    if std_dev > 100:
        print(f"  ⚠ High noise detected! Consider:")
        print(f"    - Stabilizing the load cell (no vibration)")
        print(f"    - Checking wiring connections")
        print(f"    - Adjusting AD620 gain")
    
    return avg

def calibrate_single_channel(ads, channel, channel_name):
    """Calibrate one load cell"""
    print_header(f"Calibrating {channel_name} (AIN{channel})")
    
    # Step 1: Zero/Tare
    print("\n📌 STEP 1: ZERO READING")
    print(f"  Remove ALL weight from {channel_name}")
    input("  Press Enter when ready...")
    
    zero_value = get_stable_reading(ads, channel, channel_name)
    if zero_value is None:
        print("  ❌ Failed to get zero reading")
        return None
    
    # Step 2: Check if user wants to calibrate with known weight
    print("\n📌 STEP 2: CALIBRATION WEIGHT")
    print("  Do you have a known weight to calibrate with?")
    print("  (This lets you convert raw values to kg/lbs)")
    
    choice = input("  Calibrate with known weight? (y/n): ").lower()
    
    if choice != 'y':
        print(f"\n  Skipping weight calibration for {channel_name}")
        print(f"  You can still use raw values (delta from zero)")
        return {'zero': zero_value, 'scale': None}
    
    # Get weight value
    while True:
        weight_str = input("\n  Enter weight in kg (or lbs, specify unit): ")
        try:
            # Parse weight and unit
            weight_str = weight_str.strip().lower()
            if 'lb' in weight_str or 'pound' in weight_str:
                weight = float(''.join(c for c in weight_str if c.isdigit() or c == '.'))
                unit = 'lbs'
            else:
                weight = float(''.join(c for c in weight_str if c.isdigit() or c == '.'))
                unit = 'kg'
            
            if weight <= 0:
                print("  ⚠ Weight must be positive. Try again.")
                continue
            
            print(f"  Using: {weight} {unit}")
            break
        except:
            print("  ⚠ Invalid input. Examples: '10', '10kg', '5.5', '20lbs'")
    
    # Get loaded reading
    print(f"\n  Place {weight} {unit} on {channel_name}")
    print(f"  Make sure it's stable and centered")
    input("  Press Enter when weight is in place...")
    
    loaded_value = get_stable_reading(ads, channel, channel_name)
    if loaded_value is None:
        print("  ❌ Failed to get loaded reading")
        return {'zero': zero_value, 'scale': None}
    
    # Calculate scale factor
    delta = loaded_value - zero_value
    
    print(f"\n📊 CALIBRATION RESULTS:")
    print(f"  Zero Value:   {zero_value:.2f}")
    print(f"  Loaded Value: {loaded_value:.2f}")
    print(f"  Delta:        {delta:.2f}")
    
    if abs(delta) < 50:
        print(f"\n  ⚠ WARNING: Very small change detected!")
        print(f"  The signal is too weak. Try:")
        print(f"    1. Adjusting AD620 gain potentiometer (turn clockwise)")
        print(f"    2. Using a heavier weight")
        print(f"    3. Checking load cell connections")
        return {'zero': zero_value, 'scale': None}
    
    scale_factor = weight / delta
    
    print(f"  Scale Factor: {scale_factor:.10f} {unit}/unit")
    
    # Test the calibration
    print(f"\n  ✓ Calibration complete!")
    print(f"  Formula: weight_{unit} = (raw_value - {zero_value:.2f}) × {scale_factor:.10f}")
    
    return {'zero': zero_value, 'scale': scale_factor, 'unit': unit}

def main():
    print_header("LOAD CELL CALIBRATION WIZARD")
    
    print("\nThis wizard will help you:")
    print("  1. Zero (tare) your load cells")
    print("  2. Calibrate them with known weights (optional)")
    print("  3. Generate code for your projects")
    print("\nYou'll need:")
    print("  - Load cells connected and powered")
    print("  - Known weights (optional, for calibration)")
    print("  - A stable surface")
    
    input("\nPress Enter to begin...")
    
    # Initialize ADC
    print("\n🔧 Initializing ADS1256...")
    try:
        ads = ADS1256(cs_pin=CS_PIN, drdy_pin=DRDY_PIN)
        ads.set_data_rate(DRATE_100)
        ads.set_gain(GAIN_1)
        print("  Calibrating ADC (self-test)...")
        ads.calibrate()
        print("  ✓ ADS1256 ready")
    except Exception as e:
        print(f"  ❌ Failed to initialize: {e}")
        print("\n  Troubleshooting:")
        print("    - Check SPI is enabled (sudo raspi-config)")
        print("    - Verify wiring connections")
        print("    - Run: python3 test_ads1256_v2.py")
        return
    
    # Calibrate both channels
    cal1 = calibrate_single_channel(ads, CHANNEL_1, "Load Cell 1")
    cal2 = calibrate_single_channel(ads, CHANNEL_2, "Load Cell 2")
    
    # Generate code
    print_header("CALIBRATION COMPLETE!")
    
    if cal1 or cal2:
        print("\n📄 Add this code to your script:\n")
        print("# Calibration values")
        
        if cal1:
            print(f"TARE_1 = {cal1['zero']:.2f}")
            if cal1['scale']:
                print(f"SCALE_1 = {cal1['scale']:.10f}  # {cal1.get('unit', 'kg')}/unit")
        
        if cal2:
            print(f"TARE_2 = {cal2['zero']:.2f}")
            if cal2['scale']:
                print(f"SCALE_2 = {cal2['scale']:.10f}  # {cal2.get('unit', 'kg')}/unit")
        
        print("\n# Convert to weight:")
        if cal1 and cal1['scale']:
            print(f"weight_1 = (raw_1 - TARE_1) * SCALE_1  # {cal1.get('unit', 'kg')}")
        if cal2 and cal2['scale']:
            print(f"weight_2 = (raw_2 - TARE_2) * SCALE_2  # {cal2.get('unit', 'kg')}")
    
    # Offer live test
    print("\n" + "="*70)
    test = input("\n🧪 Test calibration with live readings? (y/n): ")
    
    if test.lower() == 'y':
        print("\n📊 LIVE CALIBRATED READINGS")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                r1 = ads.read_channel(CHANNEL_1)
                r2 = ads.read_channel(CHANNEL_2)
                
                output = []
                
                if r1 is not None and cal1:
                    delta1 = r1 - cal1['zero']
                    if cal1['scale']:
                        weight1 = delta1 * cal1['scale']
                        output.append(f"LC1: {weight1:7.3f} {cal1.get('unit', 'kg')}")
                    else:
                        output.append(f"LC1: {delta1:7.0f} (raw)")
                
                if r2 is not None and cal2:
                    delta2 = r2 - cal2['zero']
                    if cal2['scale']:
                        weight2 = delta2 * cal2['scale']
                        output.append(f"LC2: {weight2:7.3f} {cal2.get('unit', 'kg')}")
                    else:
                        output.append(f"LC2: {delta2:7.0f} (raw)")
                
                print("  |  ".join(output))
                time.sleep(0.2)
                
        except KeyboardInterrupt:
            print("\n\n✓ Test stopped")
    
    # Cleanup
    ads.cleanup()
    print("\n✅ Calibration session complete!")
    print("Save the calibration values above for your project.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Calibration cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
