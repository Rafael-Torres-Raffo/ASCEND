import time
from pymodbus.client import ModbusSerialClient
import struct

def modbus_crc(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1):
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder='little')

def build_position_command(position_um):
    position_bytes = position_um.to_bytes(4, byteorder='big', signed=True)
    request = bytes([0x01, 0x64, 0x1E]) + position_bytes
    crc = modbus_crc(request)
    return request + crc

def parse_motor_response_line(response):
    if response is None or len(response) != 19:
        print("Invalid response length or no response received.")
        return None

    if response[1] != 0x64:
        print(f"Unexpected function code: 0x{response[1]:02X}")
        return None

    pos = int.from_bytes(response[2:6], byteorder='big', signed=True)
    force = int.from_bytes(response[6:10], byteorder='big', signed=True)
    power = int.from_bytes(response[10:12], byteorder='big')
    temp = response[12]
    voltage = int.from_bytes(response[13:15], byteorder='big')
    errors = int.from_bytes(response[15:17], byteorder='big')

    print(f"pos: {pos:>7} µm | force: {force:>6} mN | power: {power:>2} W | temp: {temp}°C | voltage: {voltage} mV | errors: 0x{errors:04X}")

    return pos


def float_to_registers(value):
    b = struct.pack('<f', value)  # little-endian float
    return struct.unpack('>HH', b)  # Modbus wants big-endian 16-bit regs

# Added this function
def enable_motion(client):
    # Command: [0x01, 0x64, 0x10, 0x00, 0x00, 0x00, 0x01]
    raw = bytes([0x01, 0x64, 0x10, 0x00, 0x00, 0x00, 0x01])
    full_cmd = raw + modbus_crc(raw)
    client.socket.write(full_cmd)
    time.sleep(0.1)
    response = client.socket.read(8)
    print("Enable motion response:", response.hex())
    
kp = 500.0 # 0.5
ki = 0.0 # 0.01 
kd = 0.0 # 0.001

kp_regs = float_to_registers(kp)  # Writes to 688
ki_regs = float_to_registers(ki)  # Writes to 690
kd_regs = float_to_registers(kd)  # Writes to 692

# --- Connect to motor ---
client = ModbusSerialClient(
    port='/dev/ttyUSB1',
    baudrate=19200,
    parity='E',
    stopbits=1,
    bytesize=8,
    timeout=1
)

zero_offset_um = 0

if client.connect():
    enable_motion(client)
    client.write_registers(address=688, values=kp_regs)
    client.write_registers(address=690, values=ki_regs)
    client.write_registers(address=692, values=kd_regs)

    
    try:
        while True:
            user_input = input("Enter target position in µm, 'z' to zero, or 'q' to quit: ").strip().lower()

            if user_input == 'q':
                break

            elif user_input == 'z':
                print("Zeroing at current position...")
                # Send a no-op command just to trigger a fresh response
                client.socket.write(build_position_command(0))
                time.sleep(0.1)
                response = client.socket.read(19)
                if len(response) == 19:
                    zero_offset_um = parse_motor_response_line(response)
                    print(f"Zero set at {zero_offset_um} µm")
                else:
                    print("Failed to read position to set zero.")
                continue

            try:
                position_um = int(float(user_input))  # Allow float input, convert to int µm
            except ValueError:
                print("Invalid input. Enter a number, 'z' to zero, or 'q' to quit.")
                continue

            target_um = zero_offset_um + position_um
            full_request = build_position_command(target_um)
            print(f"Moving to {position_um} µm from zero (absolute target: {target_um} µm). Streaming... (Ctrl+C to stop)")

            while True:
                client.socket.write(full_request)
                response = client.socket.read(19)
                parse_motor_response_line(response)
                time.sleep(0.3)  # 50 Hz

                if client.socket.in_waiting > 0:
                    break

    except KeyboardInterrupt:
        print("\nStreaming stopped.")
    finally:
        client.close()
else:
    print("Could not connect to motor.")
