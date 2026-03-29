from pyorcasdk import Actuator, MotorMode
import time
import sys

# --- SETTINGS ---
PORT = 0           
BAUD_RATE = 19200
MODBUS_ID = 1      

print("--- ORCA HARDWARE CALIBRATION MODE ---")
print("⚠️ WARNING: Keep fingers clear of the shaft.\n")

motor = Actuator("Orca_Calib", modbus_server_address=MODBUS_ID)

if motor.open_serial_port(PORT, baud_rate=BAUD_RATE):
    print("❌ Failed to open port.")
    exit()

def trigger_motion(motor_obj):
    for _ in range(3):
        if not motor_obj.trigger_kinematic_motion(1):
            return True
        time.sleep(0.1)
    return False

# 1. WAKE UP & TUNE
motor.clear_errors()
time.sleep(0.1)
motor.set_mode(MotorMode.SleepMode)
time.sleep(0.1)
motor.set_mode(MotorMode.KinematicMode)
time.sleep(0.1)
motor.tune_position_controller(2000, 10, 5000, 15000, 0)
motor.enable_stream()

# 2. PROMPT FOR ZERO
print("\n👇 PREPARATION 👇")
print("1. Push the bare metal shaft ALL THE WAY IN.")
print("2. You should feel it hit the internal mechanical hard stop.")
input("Press ENTER when ready to set this physical position as 0 um > ")

motor.zero_position()
time.sleep(0.1)
print("✅ Home Set.\n")

# 3. JOG LOOP
current_target = 0
xxlarge_step = 100000 # 10 cm
xlarge_step = 10000   # 1 cm
large_step = 1000     # 1 mm
small_step = 100      # 0.1 mm

print("--- CONTROLS ---")
print(" [t] +100000 um (+10 cm - ⚠️ HUGE STEP)")
print(" [g] -100000 um (-10 cm - ⚠️ HUGE STEP)")
print(" [r] +10000 um  (+1 cm)")
print(" [f] -10000 um  (-1 cm)")
print(" [w] +1000 um   (+1 mm)")
print(" [s] -1000 um   (-1 mm)")
print(" [e] +100 um    (+0.1 mm)")
print(" [d] -100 um    (-0.1 mm)")
print(" [q] Quit and Output Final Max Limit")
print("----------------\n")

try:
    while True:
        pos_res = motor.get_position_um()
        actual_pos = pos_res.value if not pos_res.error else "ERR"
        
        print(f"📍 Target: {current_target} um | 📊 Sensor: {actual_pos} um")
        cmd = input("Command > ").strip().lower()
        
        if cmd == 'q':
            break
        elif cmd == 't':
            current_target += xxlarge_step
        elif cmd == 'g':
            current_target -= xxlarge_step
        elif cmd == 'r':
            current_target += xlarge_step
        elif cmd == 'f':
            current_target -= xlarge_step
        elif cmd == 'w':
            current_target += large_step
        elif cmd == 's':
            current_target -= large_step
        elif cmd == 'e':
            current_target += small_step
        elif cmd == 'd':
            current_target -= small_step
        else:
            print("⚠️ Invalid command.")
            continue

        if current_target < 0:
            print("⚠️ Cannot go below 0 um. Holding at 0.")
            current_target = 0

        motor.set_kinematic_motion(1, current_target, 1500, 0, 1, 0)
        time.sleep(0.05)
        
        if trigger_motion(motor):
            start_t = time.time()
            # Give it time to travel the full 10cm if triggered
            while time.time() - start_t < 2.5:
                motor.run()
                time.sleep(0.05)
        else:
            print("❌ Failed to trigger motion.")

except KeyboardInterrupt:
    pass

finally:
    final_pos_res = motor.get_position_um()
    final_max = final_pos_res.value if not final_pos_res.error else current_target

    print("\n\n--- 🛑 CALIBRATION COMPLETE ---")
    print(f"Maximum stable extension reached: {final_max} um")
    
    safe_buffer = 1500 # 1.5mm buffer
    recommended_max = max(0, final_max - safe_buffer)
    
    print(f"🛡️  Recommended MAX_POS_UM for your main script: {recommended_max} um")
    print("-------------------------------\n")

    print("Returning to 0 before shutdown...")
    motor.set_kinematic_motion(1, 0, 1500, 0, 1, 0)
    trigger_motion(motor)
    park_start = time.time()
    
    # Increased park time for massive shafts
    while time.time() - park_start < 10.0:
        motor.run()
        time.sleep(0.05)
        
    motor.set_mode(MotorMode.SleepMode)
    motor.close_serial_port()
    print("Disconnected and Safe.")