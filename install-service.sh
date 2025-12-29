#!/bin/bash
# Installation script for Odysafe QuickShare as a systemd service
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

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Odysafe QuickShare Service Installer${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
QUICKSHARE_SCRIPT="$SCRIPT_DIR/quickshare.py"

# Check if quickshare.py exists
if [ ! -f "$QUICKSHARE_SCRIPT" ]; then
    echo -e "${RED}Error: quickshare.py not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Create directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p /usr/local/quickshare/shared_files
mkdir -p /usr/local/quickshare/ssl
mkdir -p /usr/local/bin

# Copy quickshare.py to /usr/local/bin
echo -e "${YELLOW}Installing quickshare.py...${NC}"
cp "$QUICKSHARE_SCRIPT" /usr/local/bin/quickshare.py
chmod +x /usr/local/bin/quickshare.py

# Generate SSL certificate if it doesn't exist
SSL_CERT="/usr/local/quickshare/ssl/cert.pem"
SSL_KEY="/usr/local/quickshare/ssl/key.pem"

if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
    echo -e "${YELLOW}Generating self-signed SSL certificate...${NC}"
    
    # Get local IP for certificate
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    HOSTNAME=$(hostname)
    
    openssl req -x509 -newkey rsa:4096 -keyout "$SSL_KEY" -out "$SSL_CERT" \
        -days 365 -nodes -subj "/C=US/ST=State/L=City/O=Odysafe/CN=$HOSTNAME" \
        -addext "subjectAltName=IP:$LOCAL_IP,DNS:$HOSTNAME,DNS:localhost"
    
    chmod 600 "$SSL_KEY"
    chmod 644 "$SSL_CERT"
    
    echo -e "${GREEN}SSL certificate generated successfully${NC}"
else
    echo -e "${GREEN}Using existing SSL certificate${NC}"
fi

# Copy service file
echo -e "${YELLOW}Installing systemd service...${NC}"
SERVICE_FILE="$SCRIPT_DIR/quickshare.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: quickshare.service not found${NC}"
    exit 1
fi

cp "$SERVICE_FILE" /etc/systemd/system/quickshare.service
chmod 644 /etc/systemd/system/quickshare.service

# Set proper permissions
chown -R root:root /usr/local/quickshare
chmod 755 /usr/local/quickshare
chmod 755 /usr/local/quickshare/shared_files

# Reload systemd
echo -e "${YELLOW}Reloading systemd...${NC}"
systemctl daemon-reload

# Enable and start the service
echo -e "${YELLOW}Enabling and starting service...${NC}"
systemctl enable quickshare.service
systemctl start quickshare.service

# Wait a moment for the service to start
sleep 2

# Check service status
if systemctl is-active --quiet quickshare.service; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Installation completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${GREEN}Service Status:${NC}"
    systemctl status quickshare.service --no-pager -l
    echo ""
    echo -e "${GREEN}Useful commands:${NC}"
    echo "  Start service:   sudo systemctl start quickshare"
    echo "  Stop service:    sudo systemctl stop quickshare"
    echo "  Restart service: sudo systemctl restart quickshare"
    echo "  View logs:       sudo journalctl -u quickshare -f"
    echo "  Service status:  sudo systemctl status quickshare"
    echo ""
    
    # Get local IP
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}Access the service at:${NC}"
    echo "  https://$LOCAL_IP:8443"
    echo "  https://localhost:8443"
    echo ""
    echo -e "${YELLOW}Note: You may need to accept the self-signed certificate warning in your browser${NC}"
else
    echo -e "${RED}Error: Service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u quickshare -n 50"
    exit 1
fi

