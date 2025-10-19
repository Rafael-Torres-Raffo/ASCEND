import time
from pymodbus.client import ModbusSerialClient

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

def build_request():
    # This builds a 'get position' query for Orca's custom protocol (function 0x64, command 0x11 maybe?)
    return bytes([0x01, 0x64, 0x11]) + modbus_crc([0x01, 0x64, 0x11])

client = ModbusSerialClient(
    port='/dev/ttyUSB0',
    baudrate=19200,
    parity='E',
    stopbits=1,
    bytesize=8,
    timeout=1
)

if client.connect():
    try:
        request = build_request()
        print("Sending:", request.hex())
        client.socket.write(request)
        time.sleep(0.1)
        resp = client.socket.read(19)
        print("Received:", resp.hex())
    finally:
        client.close()
else:
    print("Failed to connect")
