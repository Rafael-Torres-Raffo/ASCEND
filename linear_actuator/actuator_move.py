from pyorcasdk import Actuator, MotorMode
import time
import sys

# --- SETTINGS ---
PORT = 0
BAUD_RATE = 19200
MODBUS_ID = 1

history_time = []
history_pos = []
history_force = []

print("--- ORCA POSITION CONTROL (DEEP READ) ---")

motor = Actuator("MyOrca", modbus_server_address=MODBUS_ID)
if motor.open_serial_port(PORT, baud_rate=BAUD_RATE):
    print("❌ Failed to open port.")
    exit()

def trigger_with_retry(motor_obj, max_retries=3):
    for i in range(max_retries):
        err = motor_obj.trigger_kinematic_motion(1)
        if not err:
            return True
        print(f"   ⚠️ Trigger timeout (Attempt {i+1}). Retrying...")
        time.sleep(0.3)
    return False

# 1. RESET & WAKE UP
motor.clear_errors()
time.sleep(0.1)
motor.set_mode(MotorMode.SleepMode)
time.sleep(0.1)
motor.set_mode(MotorMode.KinematicMode)
time.sleep(0.1)

# 2. APPLY TUNING
motor.tune_position_controller(2000, 10, 5000, 15000, 0)

# 3. MANUAL HOMING
print("\n👇 MANUAL HOMING 👇")
print("Push the shaft all the way IN by hand.")
input("Press ENTER when ready to set this as ZERO >")
motor.zero_position()
print("✅ Home Set.")

motor.enable_stream()

try:
    while True:
        user_input = input("\nEnter Target (um) or 'q' to Plot: ")
        if user_input.lower() == 'q': break
        
        try:
            target = int(user_input)
            history_time.clear()
            history_pos.clear()
            history_force.clear()

            print(f"Planning motion to {target}...")
            motor.set_kinematic_motion(1, target, 1500, 0, 1, 0)
            time.sleep(0.1) 
            
            if not trigger_with_retry(motor):
                print("❌ Failed to start motor.")
                continue
                
            print("   Moving...")
            start_t = time.time()
            
            # Monitor loop for 2.5 seconds
            while time.time() - start_t < 2.5:
                # We call the motor.run() to keep the heartbeat alive
                motor.run() 
                
                # --- FORCED READINGS ---
                # We pull these directly from the hardware registers instead of the stream cache
                pos_res = motor.get_position_um()
                force_res = motor.get_force_mN()
                
                # Only record if the reading was successful
                if not pos_res.error and not force_res.error:
                    cur_pos = pos_res.value
                    cur_force = force_res.value
                    
                    history_time.append(time.time() - start_t)
                    history_pos.append(cur_pos)
                    history_force.append(cur_force)
                    
                    sys.stdout.write(f"\r   Live Pos: {cur_pos} um | Force: {cur_force} mN   ")
                    sys.stdout.flush()
                
                # Wait slightly so we don't overwhelm the 19200 baud line
                time.sleep(0.05)
                
            print("\n✅ Done.")

        except ValueError:
            print("Invalid Number")

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    motor.set_mode(MotorMode.SleepMode)
    motor.close_serial_port()
    print("Disconnected.")

    if history_time:
        print("\n📊 Saving Plot...")
        import matplotlib.pyplot as plt
        fig, ax1 = plt.subplots()
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Position (um)', color='tab:blue')
        ax1.plot(history_time, history_pos, color='tab:blue')
        ax2 = ax1.twinx()
        ax2.set_ylabel('Force (mN)', color='tab:red')
        ax2.plot(history_time, history_force, color='tab:red', linestyle='--')
        plt.title('Motor Performance (Deep Read)')
        plt.savefig("motor_plot.png")
        print("✅ Saved as 'motor_plot.png'.")
