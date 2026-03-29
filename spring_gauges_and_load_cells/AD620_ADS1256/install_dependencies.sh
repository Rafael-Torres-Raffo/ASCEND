#!/bin/bash
# Install script for ADS1256 Load Cell Reader

echo "=== ADS1256 Load Cell Dependencies Installer ==="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNING: This script is designed for Raspberry Pi"
    echo "Continuing anyway..."
fi

echo "Step 1: Updating package list..."
sudo apt-get update

echo ""
echo "Step 2: Installing Python SPI and GPIO libraries..."
sudo apt-get install -y python3-spidev python3-rpi.gpio

echo ""
echo "Step 3: Checking SPI status..."
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
echo "Step 4: Checking for SPI devices..."
if ls /dev/spi* 2>/dev/null; then
    echo "✓ SPI devices found"
else
    echo "✗ No SPI devices found"
    echo "  Please enable SPI in raspi-config and reboot"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. If SPI is not enabled, run: sudo raspi-config"
echo "2. Connect your hardware according to SETUP_INSTRUCTIONS.md"
echo "3. Test with: python3 test_ads1256.py"
echo "4. Run full script: python3 ads1256_load_cells.py"
