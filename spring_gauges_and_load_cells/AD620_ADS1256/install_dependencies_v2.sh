#!/bin/bash
# Updated installer with lgpio support for all Raspberry Pi models

echo "=== ADS1256 Load Cell Dependencies Installer (v2) ==="
echo ""

# Check Pi model
echo "Detecting Raspberry Pi model..."
if grep -q "Raspberry Pi 5" /proc/cpuinfo 2>/dev/null; then
    PI_MODEL="Pi 5"
    USE_LGPIO=1
elif grep -q "Raspberry Pi 4" /proc/cpuinfo 2>/dev/null; then
    PI_MODEL="Pi 4"
    USE_LGPIO=1  # Pi 4 can use either, lgpio is more modern
elif grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    PI_MODEL="Pi 3 or older"
    USE_LGPIO=1  # lgpio works on all models
else
    echo "WARNING: Cannot detect Raspberry Pi model"
    PI_MODEL="Unknown"
    USE_LGPIO=1
fi

echo "  Detected: $PI_MODEL"
echo ""

echo "Step 1: Updating package list..."
sudo apt-get update

echo ""
echo "Step 2: Installing Python SPI library..."
sudo apt-get install -y python3-spidev

echo ""
echo "Step 3: Installing GPIO library..."
if [ $USE_LGPIO -eq 1 ]; then
    echo "  Installing lgpio (modern, works on all Pi models including Pi 5)..."
    sudo apt-get install -y python3-lgpio
    echo "  ✓ lgpio installed"
else
    echo "  Installing RPi.GPIO (classic library)..."
    sudo apt-get install -y python3-rpi.gpio
    echo "  ✓ RPi.GPIO installed"
fi

echo ""
echo "Step 4: Checking SPI status..."
if lsmod | grep -q spi; then
    echo "✓ SPI module is loaded"
else
    echo "✗ SPI module is NOT loaded"
    echo "  Please enable SPI:"
    echo "    sudo raspi-config"
    echo "    → Interface Options → SPI → Enable"
    echo "    → Reboot"
fi

echo ""
echo "Step 5: Checking for SPI devices..."
if ls /dev/spi* 2>/dev/null; then
    echo "✓ SPI devices found"
else
    echo "✗ No SPI devices found"
    echo "  Please enable SPI in raspi-config and reboot"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Installed GPIO library: lgpio (compatible with all Pi models)"
echo ""
echo "Next steps:"
echo "1. If SPI is not enabled, run: sudo raspi-config"
echo "2. Connect your hardware according to SETUP_INSTRUCTIONS.md"
echo "3. Test with: python3 test_ads1256_v2.py"
echo "4. Run full script: python3 ads1256_load_cells_v2.py"
