#!/bin/bash
# Uninstallation script for Odysafe QuickShare systemd service
# This script must be run as root

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root${NC}"
    echo "Please run: sudo $0"
    exit 1
fi

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Odysafe QuickShare Service Uninstaller${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Stop and disable the service
if systemctl is-active --quiet quickshare.service 2>/dev/null; then
    echo -e "${YELLOW}Stopping service...${NC}"
    systemctl stop quickshare.service
fi

if systemctl is-enabled --quiet quickshare.service 2>/dev/null; then
    echo -e "${YELLOW}Disabling service...${NC}"
    systemctl disable quickshare.service
fi

# Remove service file
if [ -f /etc/systemd/system/quickshare.service ]; then
    echo -e "${YELLOW}Removing service file...${NC}"
    rm -f /etc/systemd/system/quickshare.service
    systemctl daemon-reload
fi

# Remove installed files
echo -e "${YELLOW}Removing installed files...${NC}"

if [ -f /usr/local/bin/quickshare.py ]; then
    rm -f /usr/local/bin/quickshare.py
    echo "  Removed /usr/local/bin/quickshare.py"
fi

# Ask if user wants to remove data directory
if [ -d /usr/local/quickshare ]; then
    echo ""
    read -p "Do you want to remove the data directory (/usr/local/quickshare)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf /usr/local/quickshare
        echo -e "${GREEN}Data directory removed${NC}"
    else
        echo -e "${YELLOW}Data directory kept at /usr/local/quickshare${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Uninstallation completed!${NC}"

