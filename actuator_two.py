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
    inches = pos/25400

    print(f"pos: {pos:>7} µm | Inches: {inches:.2f} in| force: {force:>6} mN | power: {power:>2} W | temp: {temp}°C | voltage: {voltage} mV | errors: 0x{errors:04X}")

    return pos

def float_to_registers(value):
    b = struct.pack('<f', value)
    return struct.unpack('>HH', b)

def enable_motion(client):
    raw = bytes([0x01, 0x64, 0x10, 0x00, 0x00, 0x00, 0x01])
    full_cmd = raw + modbus_crc(raw)
    client.socket.write(full_cmd)
    time.sleep(0.1)
    response = client.socket.read(8)
    print("Enable motion response:", response.hex())

def set_position_control_mode(client):
    raw = bytes([0x01, 0x64, 0x12, 0x00, 0x00, 0x00, 0x01])  # Set to position mode
    full_cmd = raw + modbus_crc(raw)
    client.socket.write(full_cmd)
    time.sleep(0.1)
    response = client.socket.read(8)
    print("Set control mode response:", response.hex())

# PID gains
kp = 50.0
ki = 0.2
kd = 0.0

kp_regs = float_to_registers(kp)
ki_regs = float_to_registers(ki)
kd_regs = float_to_registers(kd)

# Connect
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
    set_position_control_mode(client)  # ✅ Must come first
    client.write_registers(address=688, values=kp_regs)
    client.write_registers(address=690, values=ki_regs)
    client.write_registers(address=692, values=kd_regs)
    enable_motion(client)  # ✅ Must come after setting mode and PID

    try:
        while True:
            user_input = input("Enter target position in µm, 'z' to zero, or 'q' to quit: ").strip().lower()

            if user_input == 'q':
                break

            elif user_input == 'z':
                print("Zeroing at current position...")
                status_cmd = bytes([0x01, 0x64, 0x11])
                full_cmd = status_cmd + modbus_crc(status_cmd)
                client.socket.write(full_cmd)
                time.sleep(0.1)
                response = client.socket.read(19)

                if response:
                    pos = parse_motor_response_line(response)
                    if pos is not None:
                        zero_offset_um = pos
                        print(f"Zero set at {zero_offset_um} µm")
                    else:
                        print("Response received, but couldn't parse position.")
                else:
                    print("No valid response received for zeroing.")
                continue

            try:
                position_um = int(float(user_input))

            except ValueError:
                print("Invalid input. Enter a number, 'z', or 'q'.")
                continue

            target_um = zero_offset_um + position_um
            full_request = build_position_command(target_um)
            print(f"Moving to {position_um} µm from zero (absolute: {target_um} µm).")

            for _ in range(100):  # stream for 30 seconds-ish
                client.socket.write(full_request)
                response = client.socket.read(19)
                parse_motor_response_line(response)
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStreaming stopped.")
    finally:
        client.close()
else:
    print("Could not connect to motor.")
