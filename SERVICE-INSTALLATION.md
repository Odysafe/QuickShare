# Service Installation Guide

This guide explains how to install Odysafe QuickShare as a systemd service that runs in the background with HTTPS support.

## Prerequisites

- Linux system with systemd
- Python 3.7 or higher
- OpenSSL (for SSL certificate generation)
- Root/sudo access

## Installation

1. **Run the installation script as root:**

```bash
sudo ./install-service.sh
```

The script will:
- Install `quickshare.py` to `/usr/local/bin/`
- Create necessary directories in `/usr/local/quickshare/`
- Generate a self-signed SSL certificate (if not already present)
- Create and enable the systemd service
- Start the service automatically

2. **The service will run on HTTPS port 8443**

Access the service at:
- `https://localhost:8443`
- `https://<YOUR_IP>:8443`

**Note:** Your browser will show a security warning for the self-signed certificate. This is normal and you can safely accept it for local network use.

## Service Management

### Start the service
```bash
sudo systemctl start quickshare
```

### Stop the service
```bash
sudo systemctl stop quickshare
```

### Restart the service
```bash
sudo systemctl restart quickshare
```

### Check service status
```bash
sudo systemctl status quickshare
```

### View service logs
```bash
# View recent logs
sudo journalctl -u quickshare -n 50

# Follow logs in real-time
sudo journalctl -u quickshare -f
```

### Enable/Disable service at boot
```bash
# Enable service to start at boot
sudo systemctl enable quickshare

# Disable service from starting at boot
sudo systemctl disable quickshare
```

## Configuration

The service is configured in `/etc/systemd/system/quickshare.service`. Default settings:

- **Port:** 8443 (HTTPS)
- **Storage Directory:** `/usr/local/quickshare/shared_files`
- **SSL Certificate:** `/usr/local/quickshare/ssl/cert.pem`
- **SSL Key:** `/usr/local/quickshare/ssl/key.pem`
- **User:** root
- **Auto-restart:** Enabled

To modify the configuration:

1. Edit the service file:
```bash
sudo nano /etc/systemd/system/quickshare.service
```

2. Modify the `ExecStart` line with your desired parameters:
```ini
ExecStart=/usr/bin/python3 /usr/local/bin/quickshare.py \
    --port 8443 \
    --ssl-cert /usr/local/quickshare/ssl/cert.pem \
    --ssl-key /usr/local/quickshare/ssl/key.pem \
    --storage-dir /usr/local/quickshare/shared_files \
    --cleanup-hours 24 \
    --max-size 1024
```

3. Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart quickshare
```

## Using Your Own SSL Certificate

If you have your own SSL certificate:

1. Copy your certificate and key to the SSL directory:
```bash
sudo cp your-cert.pem /usr/local/quickshare/ssl/cert.pem
sudo cp your-key.pem /usr/local/quickshare/ssl/key.pem
sudo chmod 644 /usr/local/quickshare/ssl/cert.pem
sudo chmod 600 /usr/local/quickshare/ssl/key.pem
```

2. Restart the service:
```bash
sudo systemctl restart quickshare
```

## Uninstallation

To remove the service:

```bash
sudo ./uninstall-service.sh
```

This will:
- Stop and disable the service
- Remove the service file
- Remove the installed script
- Optionally remove the data directory (you'll be prompted)

## Troubleshooting

### Service won't start

1. Check the logs:
```bash
sudo journalctl -u quickshare -n 50
```

2. Verify Python is installed:
```bash
which python3
```

3. Check file permissions:
```bash
ls -l /usr/local/bin/quickshare.py
ls -l /usr/local/quickshare/ssl/
```

### SSL certificate issues

If you get SSL errors:

1. Regenerate the certificate:
```bash
sudo rm /usr/local/quickshare/ssl/cert.pem /usr/local/quickshare/ssl/key.pem
sudo ./install-service.sh
```

2. Or check certificate validity:
```bash
openssl x509 -in /usr/local/quickshare/ssl/cert.pem -text -noout
```

### Port already in use

If port 8443 is already in use:

1. Edit the service file to use a different port
2. Or find what's using the port:
```bash
sudo lsof -i :8443
```

## Security Notes

- The service runs as **root** to allow binding to privileged ports
- The self-signed certificate is for local network use only
- For production use, consider using a proper SSL certificate from a CA
- The service automatically restarts on failure
- All data is stored in `/usr/local/quickshare/shared_files`

