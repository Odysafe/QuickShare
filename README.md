# 🗂️ ODYSAFE QuickShare - Local Network File Sharing Tool

**📁 Python File Server • 🖥️ Cross-Platform LAN Sharing • 🌐 Local Network Transfer**
**💾 Temporary File Storage • 🧹 Auto-Cleanup • 🔒 Secure Local Network**

Fast, secure local network file sharing and text sharing tool. Share files and text snippets across your LAN with zero configuration. Perfect for team collaboration, development workflows, and home networks. Built with Python for maximum compatibility.

![Odysafe QuickShare Interface](docs/images/quickshare.png)

---

## 📑 Table of Contents

- [Why ODYSAFE QuickShare?](#-why-odysafe-quickshare)
- [Quick Start](#-quick-start)
- [Features Overview](#-features-overview)
- [Usage Guide](#-usage-guide)
- [Network File Sharing](#-network-file-sharing)
- [Security & Privacy](#-security--privacy)
- [Configuration](#-configuration)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 🚀 Why ODYSAFE QuickShare?

### 🔥 Key Advantages

- 🗂️ **Simple File Sharing** : Share files and text snippets across your local network
- 📝 **Text Sharing** : Copy-paste text snippets with instant clipboard integration
- 💾 **Temporary Storage** : Automatic cleanup prevents storage accumulation
- 🖥️ **Multi-OS Support** : Works on Windows, Linux, and macOS
- ⚡ **Single Script** : No installation required, just run the Python script
- 🔒 **Network Security** : Local network only, no internet required
- 🆓 **100% Free & Open Source** : MIT licensed

### 🎯 Perfect For

- **Team Collaboration** : Instant file sharing between team members on local network
- **Development Teams** : Share code snippets, test files, and project assets
- **Office Environments** : Quick document and presentation sharing
- **Home Networks** : Family file sharing and media transfer
- **LAN File Transfer** : Fast, secure file exchange without cloud services
- **Network File Server** : Create temporary file server for multiple users

---

## ⚡ Quick Start

### Prerequisites

- Python 3.7 or higher installed on your system
- Local network access

### Running the Server

```bash
# Clone the repository
git clone https://github.com/Odysafe/QuickShare.git
cd QuickShare

# Run the server (default settings)
python quickshare.py
# On Windows, you may need to use: py quickshare.py
# On Linux/macOS, you can also use: python3 quickshare.py

# Or with custom options
python quickshare.py --port 8080 --cleanup-hours 12
```

> **Note:** The script creates a `shared_files/` directory automatically for temporary storage.

**Access the application:**
- Local: `http://localhost:8000`
- Network: `http://<YOUR_IP>:8000`

---

## ✅ Features Overview

| Feature | Description | Status |
|---------|-------------|--------|
| **File Upload** | Drag & drop multiple files | ✅ Available |
| **Text Sharing** | Copy-paste text with clipboard integration | ✅ Available |
| **File Download** | Download individual files | ✅ Available |
| **Text Copy** | One-click text copying to clipboard | ✅ Available |
| **Auto-Cleanup** | Automatic deletion after specified hours | ✅ Available |
| **Multi-OS Support** | Windows, Linux, macOS compatibility | ✅ Available |
| **Network Detection** | Auto-detection of local IP address | ✅ Available |
| **Web Interface** | Modern responsive web UI | ✅ Available |
| **Size Limits** | Configurable file size limits | ✅ Available |

---

## 📖 Usage Guide

### Basic Usage

```bash
# Start LAN file server (default settings: port 8000, 24h cleanup)
python quickshare.py

# Custom port and cleanup time
python quickshare.py --port 8080 --cleanup-hours 12

# Limited file sizes for development
python quickshare.py --max-size 50
```

### Web Interface Features

#### File Upload & Sharing
- **Drag & Drop**: Drag files directly onto the drop zone for instant upload
- **Click to Select**: Click the drop zone to open file browser
- **Multiple Files**: Upload multiple files at once to LAN
- **Progress Feedback**: Visual upload progress indicator
- **File Size Limits**: Configurable maximum file sizes

#### Text Sharing & Clipboard
- **Paste Text**: Enter or paste text in the text area
- **One-Click Copy**: Copy shared text to clipboard instantly
- **Share Button**: Share text snippets with one click
- **Clipboard Integration**: Direct clipboard access for text sharing

#### File Management
- **Download Files**: Click Download button for any shared file
- **Copy Text**: Click Copy button for text files
- **Delete Files**: Remove files manually if needed
- **Auto-Expiry**: Files show automatic deletion time
- **Storage Stats**: Real-time storage usage display

### Command Line Options

```
--port PORT          Server port (default: 8000)
--host HOST          Host interface (default: 0.0.0.0)
--cleanup-hours HRS  Hours before auto-cleanup (default: 24)
--max-size SIZE      Max file size in MB (default: 100)
--storage-dir DIR    Storage directory (default: ./shared_files)
```

**Popular Configurations:**

```bash
# Development mode (short cleanup, small files)
python quickshare.py --port 3000 --cleanup-hours 1 --max-size 10

# Office collaboration (extended retention)
python quickshare.py --port 8080 --cleanup-hours 168 --max-size 500

# Custom storage location
python quickshare.py --storage-dir /tmp/quickshare_data
```

---

## 🏗️ Architecture

**Key Components:**
- **HTTP Server**: Built-in Python `http.server` with custom handlers
- **File Storage**: Temporary storage with automatic cleanup
- **Web Interface**: Embedded HTML/CSS/JS interface
- **Network Detection**: Automatic local IP detection for cross-platform compatibility

**Technology Stack:**
- **Python 3.7+**: Cross-platform compatibility (Windows, Linux, macOS)
- **HTTP Server**: Built-in Python `http.server` module
- **File System**: Native OS file operations with pathlib
- **Web Interface**: Responsive HTML/CSS/JavaScript interface

**Directory Structure:**
```
├── quickshare.py              # Main Python file server script
├── shared_files/              # Auto-created storage directory
│   ├── uploads/               # Uploaded files storage
│   └── .metadata/
│       └── text_shares/       # Shared text files
└── README.md                  # This documentation
```

---

## 🔒 Security & Privacy

### Network Security

- **Local Network Only**: Server binds to local interfaces only, no internet exposure
- **No External Access**: Cannot be accessed from outside your network
- **File Sanitization**: All filenames are sanitized
- **Size Limits**: Configurable file size limits prevent abuse
- **Temporary Storage**: Files are automatically deleted

### Privacy Features

- **No Data Collection**: No telemetry or analytics
- **Local Processing**: All processing happens on your machine
- **No Accounts**: No user registration or authentication required
- **Clean Storage**: Automatic cleanup prevents data accumulation

### Safe Usage Guidelines

- Only run on trusted local networks
- Be aware of file size limits for large uploads
- Files are automatically cleaned up (default: 24 hours)
- Manual deletion available for immediate cleanup

---

## ⚙️ Configuration

### Default Settings

```python
DEFAULT_PORT = 8000
DEFAULT_HOST = '0.0.0.0'
DEFAULT_CLEANUP_HOURS = 24
DEFAULT_MAX_SIZE_MB = 100
DEFAULT_STORAGE_DIR = './shared_files'
```

### Use Cases & Configurations

**Development Teams:**
```bash
python quickshare.py --cleanup-hours 4 --max-size 50
```

**Office File Sharing:**
```bash
python quickshare.py --port 8080 --cleanup-hours 72 --max-size 200
```

**Home Network Media Sharing:**
```bash
python quickshare.py --port 9000 --cleanup-hours 168 --max-size 1024
```

**Temporary Project Sharing:**
```bash
python quickshare.py --cleanup-hours 24 --storage-dir ./project_files
```

---

## 🔧 Troubleshooting & Network File Sharing Tips

### Common Issues

**Server won't start:**
- Check if port is already in use:
  - Linux/macOS: `netstat -an | grep :8000` or `lsof -i :8000`
  - Windows: `netstat -an | findstr :8000`
- Try a different port: `python quickshare.py --port 8081`

**Cannot access from other devices on LAN:**
- **Firewall Settings**: Ensure port 8000 is open on your firewall
- **Network Configuration**: Verify all devices are on the same local network (same subnet)
- **IP Address**: Use the IP address shown in server output, not localhost
- **Antivirus Software**: Some antivirus may block local network access

**Files not uploading:**
- Check file size limits (default: 100MB)
- Verify disk space availability
- Check file permissions on storage directory
- Ensure files are not corrupted or in use by another program

**Text not copying to clipboard:**
- Try using a different browser
- Some browsers require user interaction before allowing clipboard access
- Use the text area to manually copy-paste if automatic copy fails

### Logs & Debugging

View server logs for troubleshooting:
```bash
# Linux/macOS
python quickshare.py 2>&1 | tee quickshare.log

# Windows (PowerShell)
python quickshare.py *> quickshare.log

# Windows (Command Prompt)
python quickshare.py > quickshare.log 2>&1
```

### Network File Sharing Tips

- **Large Files**: For files >100MB, increase `--max-size` parameter
- **Multiple Users**: Each user can download simultaneously without issues
- **Network Speed**: Transfer speed depends on your local network bandwidth
- **File Types**: All file types are supported, including binaries and archives
- **Security**: Only share with trusted devices on your local network

---

## 📝 License

**MIT License**

Copyright (c) 2025 Odysafe

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

**Built with ❤️ by Odysafe | Python LAN File Sharing | Local Network Server | Cross-Platform File Transfer**
