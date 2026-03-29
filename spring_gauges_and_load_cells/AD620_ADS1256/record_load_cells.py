#!/usr/bin/env python3
"""
Record Load Cell Data to CSV File
Saves timestamped data for later analysis
"""

import time
import csv
from datetime import datetime
from ads1256_load_cells_v2 import ADS1256, read_avg_raw, DRATE_100, GAIN_1

# Configuration
CS_PIN = 22
DRDY_PIN = 17
CHANNEL_1 = 0
CHANNEL_2 = 1
SAMPLE_RATE_HZ = 10  # How many readings per second
DURATION_SECONDS = 60  # How long to record (0 = infinite)

def main():
    print("=== Load Cell Data Recorder ===\n")
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"load_cell_data_{timestamp}.csv"
    
    print(f"Recording to: {filename}")
    if DURATION_SECONDS > 0:
        print(f"Duration: {DURATION_SECONDS} seconds")
    else:
        print("Duration: Until stopped (Ctrl+C)")
    print(f"Sample rate: {SAMPLE_RATE_HZ} Hz")
    print()
    
    # Initialize ADC
    print("Initializing ADS1256...")
    ads = ADS1256(cs_pin=CS_PIN, drdy_pin=DRDY_PIN)
    ads.set_data_rate(DRATE_100)
    ads.set_gain(GAIN_1)
    ads.calibrate()
    print("✓ Ready")
    
    # Tare
    print("\nTaring load cells...")
    tare1 = read_avg_raw(ads, CHANNEL_1, samples=20)
    tare2 = read_avg_raw(ads, CHANNEL_2, samples=20)
    print(f"Tare1: {tare1:.0f}")
    print(f"Tare2: {tare2:.0f}")
    
    # Open CSV file
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Time_Seconds', 'LoadCell1_Raw', 'LoadCell1_Delta', 
                        'LoadCell2_Raw', 'LoadCell2_Delta'])
        
        print(f"\nRecording started... (Ctrl+C to stop)")
        print()
        
        start_time = time.time()
        sample_count = 0
        period = 1.0 / SAMPLE_RATE_HZ
        
        try:
            while True:
                # Check duration
                elapsed = time.time() - start_time
                if DURATION_SECONDS > 0 and elapsed >= DURATION_SECONDS:
                    break
                
                # Read values
                r1 = read_avg_raw(ads, CHANNEL_1, samples=3)
                r2 = read_avg_raw(ads, CHANNEL_2, samples=3)
                
                if r1 is not None and r2 is not None:
                    delta1 = r1 - tare1
                    delta2 = r2 - tare2
                    
                    # Write to CSV
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    writer.writerow([timestamp_str, f"{elapsed:.3f}", 
                                   f"{r1:.0f}", f"{delta1:.0f}", 
                                   f"{r2:.0f}", f"{delta2:.0f}"])
                    
                    # Print to screen
                    sample_count += 1
                    print(f"[{sample_count:4d}] LC1: {delta1:+7.0f}  |  LC2: {delta2:+7.0f}  |  {elapsed:.1f}s")
                    
                time.sleep(period)
                
        except KeyboardInterrupt:
            print("\n\nRecording stopped by user.")
        
        elapsed = time.time() - start_time
        print(f"\nRecorded {sample_count} samples in {elapsed:.1f} seconds")
        print(f"Average rate: {sample_count/elapsed:.1f} Hz")
        print(f"Saved to: {filename}")
    
    ads.cleanup()
    print("\nDone!")

if __name__ == "__main__":
    main()
