from pyorcasdk import Actuator, MotorMode
import time
import sys

# --- SETTINGS ---
PORT_1 = 0 
PORT_2 = 1 
BAUD_RATE = 19200
MODBUS_ID_1 = 1
MODBUS_ID_2 = 1 

# --- HARDWARE LIMITS (Adjust these based on your specific actuators) ---
MIN_POS_UM = 0        # 0 mm
MAX_POS_UM = 50000    # 50 mm (Example: change this to your actuator's max stroke)

print("--- DUAL ORCA POSITION CONTROL ---")

# 1. INITIALIZE BOTH MOTORS
motor1 = Actuator("Orca_Left", modbus_server_address=MODBUS_ID_1)
motor2 = Actuator("Orca_Right", modbus_server_address=MODBUS_ID_2)

if motor1.open_serial_port(PORT_1, baud_rate=BAUD_RATE):
    print("❌ Failed to open port for Motor 1.")
    exit()
if motor2.open_serial_port(PORT_2, baud_rate=BAUD_RATE):
    print("❌ Failed to open port for Motor 2.")
    exit()

def trigger_with_retry(motor_obj, max_retries=3):
    for i in range(max_retries):
        err = motor_obj.trigger_kinematic_motion(1)
        if not err:
            return True
        print(f"   ⚠️ Trigger timeout for {motor_obj.name} (Attempt {i+1}). Retrying...")
        time.sleep(0.3)
    return False

def setup_motor(m):
    m.clear_errors()
    time.sleep(0.1)
    m.set_mode(MotorMode.SleepMode)
    time.sleep(0.1)
    m.set_mode(MotorMode.KinematicMode)
    time.sleep(0.1)
    m.tune_position_controller(2000, 10, 5000, 15000, 0)
    m.enable_stream()

# 2. WAKE UP & TUNE BOTH
setup_motor(motor1)
setup_motor(motor2)

# 3. MANUAL HOMING
print("\n👇 MANUAL HOMING 👇")
print("Push BOTH shafts all the way IN by hand.")
input("Press ENTER when ready to set these as ZERO >")
motor1.zero_position()
motor2.zero_position()
print("✅ Homes Set.")

try:
    while True:
        user_input = input("\nEnter Target (um) or 'q' to Quit: ")
        if user_input.lower() == 'q': 
            break
        
        try:
            target = int(user_input)

            # --- SOFTWARE LIMIT CHECK ---
            if target < MIN_POS_UM or target > MAX_POS_UM:
                print(f"⚠️ OUT OF BOUNDS: Please enter a value between {MIN_POS_UM} and {MAX_POS_UM} um.")
                continue # Skips the rest of the loop and asks for input again

            print(f"Planning motion to {target} for both motors...")
            
            motor1.set_kinematic_motion(1, target, 1500, 0, 1, 0)
            motor2.set_kinematic_motion(1, target, 1500, 0, 1, 0)
            time.sleep(0.1) 
            
            if not trigger_with_retry(motor1) or not trigger_with_retry(motor2):
                print("❌ Failed to start one or both motors.")
                continue
                
            print("   Moving...")
            start_t = time.time()
            
            while time.time() - start_t < 2.5:
                motor1.run() 
                motor2.run() 
                
                pos1 = motor1.get_position_um()
                pos2 = motor2.get_position_um()
                
                val1 = pos1.value if not pos1.error else "ERR"
                val2 = pos2.value if not pos2.error else "ERR"
                
                sys.stdout.write(f"\r   Live Pos -> M1: {val1} um | M2: {val2} um   ")
                sys.stdout.flush()
                
                time.sleep(0.05)
                
            print("\n✅ Done.")

        except ValueError:
            print("Invalid Number")

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    # --- AUTO-RETURN TO ZERO SEQUENCE ---
    print("\nReturning motors to home (0 um) before shutdown...")
    motor1.set_kinematic_motion(1, 0, 1500, 0, 1, 0)
    motor2.set_kinematic_motion(1, 0, 1500, 0, 1, 0)
    time.sleep(0.1)
    
    if trigger_with_retry(motor1) and trigger_with_retry(motor2):
        print("   Parking...")
        park_start_t = time.time()
        # Give them 3 seconds to safely travel back to 0
        while time.time() - park_start_t < 3.0:
            motor1.run()
            motor2.run()
            time.sleep(0.05)
    else:
        print("⚠️ Could not trigger return-to-home sequence.")

    # Safely power down and disconnect
    motor1.set_mode(MotorMode.SleepMode)
    motor2.set_mode(MotorMode.SleepMode)
    motor1.close_serial_port()
    motor2.close_serial_port()
    print("✅ Disconnected and Safe.")