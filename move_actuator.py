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

def move_actuator_inches(client, inches):
    microns = int(inches * 25400)  # Convert inches to micrometers
    command = build_position_command(microns)
    
    print(f"Sending move command to {microns} µm ({inches} inches)...")
    client.socket.write(command)
    time.sleep(0.1)
    response = client.socket.read(19)
    print("Response:", response.hex())
    if len(response) == 19:
        parse_motor_response_line(response)
    else:
        print("Incomplete response received.")

def parse_motor_response_line(response):
    if len(response) != 19 or response[1] != 0x64:
        return
    pos = int.from_bytes(response[2:6], byteorder='big', signed=True)
    force = int.from_bytes(response[6:10], byteorder='big', signed=True)
    power = int.from_bytes(response[10:12], byteorder='big')
    temp = response[12]
    voltage = int.from_bytes(response[13:15], byteorder='big')
    errors = int.from_bytes(response[15:17], byteorder='big')
    print(f"pos: {pos:>7} µm | force: {force:>6} mN | power: {power:>2} W | temp: {temp}°C | voltage: {voltage} mV | errors: 0x{errors:04X}")

# Main usage
if __name__ == "__main__":
    client = ModbusSerialClient(
        port='/dev/ttyUSB1',
        baudrate=19200,
        parity='E',
        stopbits=1,
        bytesize=8,
        timeout=1
    )

    if client.connect():
        try:
            while True:
                val = input("Enter distance to move in inches (or 'q' to quit): ").strip()
                if val.lower() == 'q':
                    break
                try:
                    inches = float(val)
                    move_actuator_inches(client, inches)
                except ValueError:
                    print("Please enter a valid number.")
        finally:
            client.close()
    else:
        print("Failed to connect to actuator.")
