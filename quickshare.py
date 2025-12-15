#!/usr/bin/env python3
"""
Odysafe QuickShare - Simple network file sharing solution
A lightweight Python script for sharing files, folders, and text over local network.
"""

import os
import json
import time
import socket
import threading
import argparse
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration defaults
DEFAULT_PORT = 8000
DEFAULT_HOST = '0.0.0.0'
DEFAULT_CLEANUP_HOURS = 24
DEFAULT_MAX_SIZE_MB = 100
DEFAULT_STORAGE_DIR = './shared_files'

# Storage paths
UPLOADS_DIR = 'uploads'
TEXT_SHARES_DIR = 'text_shares'
METADATA_DIR = '.metadata'


class FileSharingServer:
    """Main server class managing storage and cleanup"""
    
    def __init__(self, storage_dir, cleanup_hours, max_size_mb):
        self.storage_dir = Path(storage_dir)
        self.cleanup_hours = cleanup_hours
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        # Create storage directories
        self.uploads_dir = self.storage_dir / UPLOADS_DIR
        self.text_shares_dir = self.storage_dir / METADATA_DIR / TEXT_SHARES_DIR
        self.metadata_dir = self.storage_dir / METADATA_DIR
        
        self._create_directories()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
    
    def _create_directories(self):
        """Create necessary directories"""
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.text_shares_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def _cleanup_loop(self):
        """Background thread for automatic cleanup"""
        while True:
            try:
                self.cleanup_old_files()
                time.sleep(3600)  # Check every hour
            except Exception as e:
                print(f"Cleanup error: {e}")
    
    def cleanup_old_files(self):
        """Remove files older than cleanup_hours"""
        cutoff_time = datetime.now() - timedelta(hours=self.cleanup_hours)
        removed_count = 0
        
        # Clean uploads
        for file_path in self.uploads_dir.iterdir():
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        removed_count += 1
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
        
        # Clean text shares
        for file_path in self.text_shares_dir.iterdir():
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        removed_count += 1
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
        
        # Clean metadata
        metadata_file = self.metadata_dir / 'files.json'
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                updated_metadata = {}
                for filename, info in metadata.items():
                    file_time = datetime.fromisoformat(info['uploaded_at'])
                    if file_time >= cutoff_time:
                        updated_metadata[filename] = info
                
                with open(metadata_file, 'w') as f:
                    json.dump(updated_metadata, f, indent=2)
            except Exception as e:
                print(f"Error cleaning metadata: {e}")
        
        if removed_count > 0:
            print(f"Cleaned up {removed_count} old file(s)")
    
    def get_storage_stats(self):
        """Get storage statistics"""
        total_files = 0
        total_size = 0
        
        for file_path in self.uploads_dir.iterdir():
            if file_path.is_file():
                total_files += 1
                total_size += file_path.stat().st_size
        
        for file_path in self.text_shares_dir.iterdir():
            if file_path.is_file():
                total_files += 1
                total_size += file_path.stat().st_size
        
        return {
            'total_files': total_files,
            'total_size': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2)
        }
    
    def get_files_list(self):
        """Get list of all shared files"""
        files = []
        
        # Get uploaded files
        for file_path in self.uploads_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                uploaded_time = datetime.fromtimestamp(stat.st_mtime)
                expires_at = uploaded_time + timedelta(hours=self.cleanup_hours)
                files.append({
                    'name': file_path.name,
                    'size': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'uploaded_at': uploaded_time.isoformat(),
                    'expires_at': expires_at.isoformat(),
                    'type': 'file'
                })
        
        # Get text shares
        for file_path in self.text_shares_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                uploaded_time = datetime.fromtimestamp(stat.st_mtime)
                expires_at = uploaded_time + timedelta(hours=self.cleanup_hours)
                files.append({
                    'name': file_path.name,
                    'size': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'uploaded_at': uploaded_time.isoformat(),
                    'expires_at': expires_at.isoformat(),
                    'type': 'text'
                })
        
        # Sort by upload time (newest first)
        files.sort(key=lambda x: x['uploaded_at'], reverse=True)
        return files
    
    def save_file(self, filename, content, file_type='file'):
        """Save uploaded file"""
        if file_type == 'file':
            sanitized = self._sanitize_filename(filename)
            # Add timestamp to avoid collisions
            name_parts = os.path.splitext(sanitized)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if name_parts[1]:  # Has extension
                new_filename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
            else:
                new_filename = f"{sanitized}_{timestamp}"
            file_path = self.uploads_dir / new_filename
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = self.text_shares_dir / f"text_{timestamp}.txt"
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return file_path
    
    def delete_file(self, filename):
        """Delete a file"""
        # Try uploads first
        file_path = self.uploads_dir / self._sanitize_filename(filename)
        if file_path.exists():
            file_path.unlink()
            return True
        
        # Try text shares
        file_path = self.text_shares_dir / self._sanitize_filename(filename)
        if file_path.exists():
            file_path.unlink()
            return True
        
        return False
    
    def get_file(self, filename):
        """Get file path and content"""
        # Try uploads first
        file_path = self.uploads_dir / self._sanitize_filename(filename)
        if file_path.exists():
            return file_path
        
        # Try text shares
        file_path = self.text_shares_dir / self._sanitize_filename(filename)
        if file_path.exists():
            return file_path
        
        return None
    
    def _sanitize_filename(self, filename):
        """Sanitize filename to prevent directory traversal"""
        # Remove path components
        filename = os.path.basename(filename)
        # Remove dangerous characters
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        return filename


class FileSharingHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for file sharing server"""
    
    server_instance = None
    
    def do_GET(self):
        """Handle GET requests"""
        path = self.path.split('?')[0]
        
        if path == '/' or path == '/index.html':
            self._serve_index()
        elif path.startswith('/api/files'):
            self._serve_files_list()
        elif path.startswith('/api/stats'):
            self._serve_stats()
        elif path.startswith('/api/text/'):
            self._serve_text_content(path)
        elif path.startswith('/download/'):
            self._serve_download(path)
        else:
            self._send_response(404, {'error': 'Not found'}, content_type='application/json')
    
    def do_POST(self):
        """Handle POST requests"""
        path = self.path.split('?')[0]
        
        if path == '/upload':
            self._handle_upload()
        elif path == '/upload-text':
            self._handle_text_upload()
        elif path.startswith('/api/delete/'):
            self._handle_delete(path)
        elif path == '/api/cleanup':
            self._handle_cleanup()
        else:
            self._send_response(404, {'error': 'Not found'}, content_type='application/json')
    
    def _serve_index(self):
        """Serve the main web interface"""
        html = self._get_html_interface()
        self._send_response(200, html, content_type='text/html')
    
    def _serve_files_list(self):
        """Serve files list as JSON"""
        files = self.server_instance.get_files_list()
        self._send_response(200, files, content_type='application/json')
    
    def _serve_stats(self):
        """Serve storage statistics"""
        stats = self.server_instance.get_storage_stats()
        stats['cleanup_hours'] = self.server_instance.cleanup_hours
        self._send_response(200, stats, content_type='application/json')
    
    def _serve_text_content(self, path):
        """Serve text file content as JSON"""
        filename = unquote(path.replace('/api/text/', ''))
        file_path = self.server_instance.get_file(filename)
        
        if not file_path or not file_path.exists():
            self._send_response(404, {'error': 'File not found'}, content_type='application/json')
            return
        
        try:
            # Check if it's a text file
            if file_path.parent.name != TEXT_SHARES_DIR:
                self._send_response(400, {'error': 'Not a text file'}, content_type='application/json')
                return
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            self._send_response(200, {
                'success': True,
                'content': content,
                'filename': filename
            }, content_type='application/json')
        except Exception as e:
            self._send_response(500, {'error': str(e)}, content_type='application/json')
    
    def _serve_download(self, path):
        """Serve file download"""
        filename = unquote(path.replace('/download/', ''))
        file_path = self.server_instance.get_file(filename)
        
        if not file_path or not file_path.exists():
            self._send_response(404, {'error': 'File not found'}, content_type='application/json')
            return
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # Determine content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            if not content_type:
                content_type = 'application/octet-stream'
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_response(500, {'error': str(e)}, content_type='application/json')
    
    def _handle_upload(self):
        """Handle file upload"""
        try:
            content_type = self.headers.get('Content-Type', '')
            
            if not content_type.startswith('multipart/form-data'):
                self._send_response(400, {'error': 'Invalid content type'}, content_type='application/json')
                return
            
            # Parse multipart form data
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > self.server_instance.max_size_bytes * 10:  # Allow multiple files
                self._send_response(400, {'error': 'Total upload size too large'}, content_type='application/json')
                return
            
            data = self.rfile.read(content_length)
            
            # Extract boundary
            boundary_str = content_type.split('boundary=')[1].strip()
            # Remove quotes if present
            if boundary_str.startswith('"') and boundary_str.endswith('"'):
                boundary_str = boundary_str[1:-1]
            boundary = boundary_str.encode() if isinstance(boundary_str, str) else boundary_str
            boundary_marker = b'--' + boundary
            
            # Split by boundary
            parts = data.split(boundary_marker)
            
            uploaded_files = []
            
            for part in parts:
                if not part.strip() or part.strip() == b'--':
                    continue
                
                # Find headers section
                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue
                
                headers_section = part[:header_end]
                file_content = part[header_end + 4:]
                
                # Remove trailing boundary markers
                if file_content.endswith(b'\r\n'):
                    file_content = file_content[:-2]
                
                # Extract filename from headers
                filename = None
                if b'Content-Disposition' in headers_section:
                    # Look for filename="..." or filename=...
                    filename_match = None
                    for line in headers_section.split(b'\r\n'):
                        if b'filename' in line.lower():
                            # Try filename="..."
                            if b'filename="' in line:
                                start = line.find(b'filename="') + 11
                                end = line.find(b'"', start)
                                if end != -1:
                                    filename_match = line[start:end]
                            # Try filename=...
                            elif b'filename=' in line:
                                start = line.find(b'filename=') + 9
                                # Find end (space, semicolon, or end of line)
                                end = len(line)
                                for char in [b' ', b';', b'\r', b'\n']:
                                    idx = line.find(char, start)
                                    if idx != -1 and idx < end:
                                        end = idx
                                filename_match = line[start:end]
                            
                            if filename_match:
                                try:
                                    filename = filename_match.decode('utf-8', errors='ignore').strip('"')
                                except:
                                    filename = filename_match.decode('latin-1', errors='ignore').strip('"')
                                break
                
                if filename and file_content:
                    # Check individual file size
                    if len(file_content) > self.server_instance.max_size_bytes:
                        continue
                    
                    # Save file
                    file_path = self.server_instance.save_file(filename, file_content)
                    uploaded_files.append({
                        'filename': file_path.name,
                        'size': len(file_content),
                        'original_name': filename
                    })
            
            if uploaded_files:
                self._send_response(200, {
                    'success': True,
                    'uploaded': len(uploaded_files),
                    'files': uploaded_files
                }, content_type='application/json')
            else:
                self._send_response(400, {'error': 'No files uploaded'}, content_type='application/json')
            
        except Exception as e:
            self._send_response(500, {'error': str(e)}, content_type='application/json')
    
    def _handle_text_upload(self):
        """Handle text sharing"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > self.server_instance.max_size_bytes:
                self._send_response(400, {'error': 'Text too large'}, content_type='application/json')
                return
            
            data = self.rfile.read(content_length)
            text_content = data.decode('utf-8', errors='ignore')
            
            # Save as text file
            file_path = self.server_instance.save_file('text_share.txt', text_content.encode('utf-8'), file_type='text')
            
            self._send_response(200, {
                'success': True,
                'filename': file_path.name
            }, content_type='application/json')
            
        except Exception as e:
            self._send_response(500, {'error': str(e)}, content_type='application/json')
    
    def _handle_delete(self, path):
        """Handle file deletion"""
        filename = unquote(path.replace('/api/delete/', ''))
        
        if self.server_instance.delete_file(filename):
            self._send_response(200, {'success': True}, content_type='application/json')
        else:
            self._send_response(404, {'error': 'File not found'}, content_type='application/json')
    
    def _handle_cleanup(self):
        """Handle manual cleanup"""
        self.server_instance.cleanup_old_files()
        self._send_response(200, {'success': True}, content_type='application/json')
    
    def _send_response(self, status_code, data, content_type='application/json'):
        """Send HTTP response"""
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        
        if isinstance(data, (dict, list)):
            response = json.dumps(data).encode('utf-8')
        else:
            response = data.encode('utf-8') if isinstance(data, str) else data
        
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    
    def log_message(self, format, *args):
        """Custom logging"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")
    
    def _get_html_interface(self):
        """Generate HTML interface"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odysafe QuickShare</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    {self._get_html_body()}
    <script>
        {self._get_javascript()}
    </script>
</body>
</html>"""
    
    def _get_css(self):
        """Get CSS styles (inspired by ODYSAFE-CTI design)"""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg-primary: #0a0a0a;
            --violet-medium: #6D28D9;
            --violet-light: #8B5CF6;
            --violet-aurora: #a78bfa;
            --text-primary: #F5F3FF;
            --text-secondary: #DDD6FE;
            --text-muted: #A78BFA;
            --white: #FFFFFF;
            --green-positive: #22C55E;
            --red-alert: #DC2626;
            --transition-fast: 0.2s ease;
            --transition-medium: 0.3s ease;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            color: var(--text-primary);
            background: #0a0a0a;
            line-height: 1.6;
            min-height: 100vh;
            font-size: 17px;
            -webkit-font-smoothing: antialiased;
            position: relative;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: -40%;
            left: -30%;
            width: 160%;
            height: 160%;
            background: 
                radial-gradient(ellipse 1200px 1800px at -15% -15%, rgba(139, 92, 246, 0.6) 0%, rgba(139, 92, 246, 0.3) 20%, transparent 50%),
                radial-gradient(ellipse 900px 1400px at -5% -10%, rgba(167, 139, 250, 0.5) 0%, rgba(167, 139, 250, 0.25) 25%, transparent 55%);
            animation: haloPulse 12s ease-in-out infinite;
            pointer-events: none;
            z-index: 0;
            filter: blur(60px);
        }
        
        @keyframes haloPulse {
            0%, 100% { opacity: 0.85; transform: scale(1) translateX(0) translateY(0); }
            50% { opacity: 1; transform: scale(1.08) translateX(-15px) translateY(-15px); }
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px 20px;
            position: relative;
            z-index: 1;
        }
        
        .header {
            text-align: center;
            margin-bottom: 60px;
        }
        
        .header h1 {
            font-size: clamp(32px, 5vw, 56px);
            font-weight: 700;
            margin-bottom: 16px;
            background: linear-gradient(135deg, var(--violet-light), var(--violet-aurora));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .stats {
            display: flex;
            justify-content: center;
            gap: 32px;
            margin-bottom: 40px;
            flex-wrap: wrap;
        }
        
        .stat-card {
            background: rgba(22, 27, 34, 0.6);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(167, 139, 250, 0.1);
            min-width: 150px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: var(--violet-light);
            margin-bottom: 8px;
        }
        
        .stat-label {
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .card {
            background: rgba(22, 27, 34, 0.6);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            padding: 32px;
            border: 1px solid rgba(167, 139, 250, 0.1);
            margin-bottom: 32px;
            transition: all var(--transition-medium);
        }
        
        .card:hover {
            border-color: rgba(167, 139, 250, 0.2);
            transform: translateY(-4px);
            box-shadow: 0 12px 48px rgba(139, 92, 246, 0.2);
        }
        
        .card-title {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 24px;
            color: var(--white);
        }
        
        .drop-zone {
            border: 2px dashed rgba(167, 139, 250, 0.3);
            border-radius: 20px;
            padding: 64px 32px;
            text-align: center;
            transition: all var(--transition-medium);
            background: rgba(22, 27, 34, 0.3);
        }
        
        .drop-zone.dragover {
            border-color: var(--violet-light);
            background: rgba(139, 92, 246, 0.05);
            transform: scale(1.02);
        }
        
        .drop-zone-icon {
            font-size: 64px;
            margin-bottom: 16px;
        }
        
        .btn {
            display: inline-block;
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: 500;
            text-decoration: none;
            border: none;
            transition: all var(--transition-medium);
            font-size: 16px;
            font-family: inherit;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--violet-medium), var(--violet-light));
            color: var(--white);
            box-shadow: 0 4px 16px rgba(139, 92, 246, 0.3);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(139, 92, 246, 0.4);
        }
        
        .btn-secondary {
            background: rgba(139, 92, 246, 0.1);
            color: var(--violet-light);
            border: 1px solid rgba(167, 139, 250, 0.2);
        }
        
        .btn-danger {
            background: rgba(220, 38, 38, 0.1);
            color: var(--red-alert);
            border: 1px solid rgba(220, 38, 38, 0.2);
        }
        
        .btn-danger:hover {
            background: rgba(220, 38, 38, 0.2);
        }
        
        .form-control {
            width: 100%;
            padding: 12px 16px;
            background: rgba(22, 27, 34, 0.6);
            border: 1px solid rgba(167, 139, 250, 0.1);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 16px;
            font-family: inherit;
            transition: all var(--transition-medium);
        }
        
        .form-control:focus {
            outline: none;
            border-color: var(--violet-light);
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
        }
        
        textarea.form-control {
            min-height: 120px;
            resize: vertical;
        }
        
        .file-list {
            margin-top: 24px;
        }
        
        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            background: rgba(139, 92, 246, 0.05);
            border-radius: 12px;
            margin-bottom: 12px;
            border: 1px solid rgba(167, 139, 250, 0.1);
        }
        
        .file-info {
            flex: 1;
        }
        
        .file-name {
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 4px;
        }
        
        .file-meta {
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        .file-actions {
            display: flex;
            gap: 8px;
        }
        
        .alert {
            padding: 16px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid;
        }
        
        .alert-success {
            background: rgba(34, 197, 94, 0.1);
            border-color: rgba(34, 197, 94, 0.3);
            color: var(--green-positive);
        }
        
        .alert-error {
            background: rgba(220, 38, 38, 0.1);
            border-color: rgba(220, 38, 38, 0.3);
            color: var(--red-alert);
        }
        
        .hidden {
            display: none;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(167, 139, 250, 0.3);
            border-top-color: var(--violet-light);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px 12px;
            }
            
            .stats {
                gap: 16px;
            }
            
            .card {
                padding: 24px;
            }
            
            .file-item {
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
            }
        }
        """
    
    def _get_html_body(self):
        """Get HTML body content"""
        return """
    <div class="container">
        <div class="header">
            <h1>📁 Odysafe QuickShare</h1>
            <p style="color: var(--text-secondary); font-size: 18px;">
                Share files, folders, and text across your local network
            </p>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-value" id="stat-files">0</div>
                <div class="stat-label">Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="stat-size">0 MB</div>
                <div class="stat-label">Storage Used</div>
            </div>
        </div>
        
        <div id="alert-container"></div>
        
        <div class="card">
            <h2 class="card-title">📤 Upload Files</h2>
            <div class="drop-zone" id="drop-zone">
                <div class="drop-zone-icon">📁</div>
                <p style="margin-bottom: 24px; color: var(--text-secondary);">
                    Drag and drop files here or click to select
                </p>
                <input type="file" id="file-input" multiple style="display: none;">
                <button class="btn btn-primary" onclick="document.getElementById('file-input').click()">
                    Select Files
                </button>
            </div>
            <div id="upload-progress" class="hidden" style="margin-top: 16px;">
                <div class="loading"></div>
                <span style="margin-left: 12px; color: var(--text-secondary);">Uploading...</span>
            </div>
        </div>
        
        <div class="card">
            <h2 class="card-title">📝 Share Text</h2>
            <textarea class="form-control" id="text-input" placeholder="Paste or type text here..."></textarea>
            <button class="btn btn-primary" onclick="shareText()" style="margin-top: 16px; width: 100%;">
                Share Text
            </button>
        </div>
        
        <div class="card">
            <h2 class="card-title">📋 Shared Files</h2>
            <div class="file-list" id="file-list">
                <p style="color: var(--text-secondary); text-align: center; padding: 40px;">
                    No files shared yet
                </p>
            </div>
        </div>
    </div>
        """
    
    def _get_javascript(self):
        """Get JavaScript code"""
        return """
        let files = [];
        
        // Load stats and files on page load
        window.addEventListener('DOMContentLoaded', () => {
            loadStats();
            loadFiles();
            setInterval(loadFiles, 5000); // Refresh every 5 seconds
        });
        
        // Drag and drop
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');
        
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            uploadFiles(files);
        });
        
        fileInput.addEventListener('change', (e) => {
            uploadFiles(e.target.files);
        });
        
        async function uploadFiles(fileList) {
            if (fileList.length === 0) return;
            
            // Check file sizes
            let totalSize = 0;
            for (let file of fileList) {
                totalSize += file.size;
            }
            
            if (totalSize > 100 * 1024 * 1024) { // 100MB limit
                showAlert('Total file size exceeds 100MB limit', 'error');
                return;
            }
            
            const formData = new FormData();
            for (let file of fileList) {
                formData.append('files', file, file.name);
            }
            
            showProgress(true);
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    const count = result.uploaded || fileList.length;
                    showAlert(count + ' file(s) uploaded successfully!', 'success');
                    loadFiles();
                    loadStats();
                } else {
                    showAlert('Upload failed: ' + (result.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                showAlert('Upload error: ' + error.message, 'error');
            } finally {
                showProgress(false);
                fileInput.value = '';
            }
        }
        
        async function shareText() {
            const text = document.getElementById('text-input').value.trim();
            if (!text) {
                showAlert('Please enter some text', 'error');
                return;
            }
            
            try {
                const response = await fetch('/upload-text', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'text/plain'
                    },
                    body: text
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    showAlert('Text shared successfully!', 'success');
                    document.getElementById('text-input').value = '';
                    loadFiles();
                    loadStats();
                } else {
                    showAlert('Share failed: ' + (result.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                showAlert('Share error: ' + error.message, 'error');
            }
        }
        
        async function loadFiles() {
            try {
                const response = await fetch('/api/files');
                files = await response.json();
                renderFiles();
            } catch (error) {
                console.error('Error loading files:', error);
            }
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                document.getElementById('stat-files').textContent = stats.total_files || 0;
                document.getElementById('stat-size').textContent = (stats.total_size_mb || 0) + ' MB';
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
        
        function renderFiles() {
            const fileList = document.getElementById('file-list');
            
            if (files.length === 0) {
                fileList.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 40px;">No files shared yet</p>';
                return;
            }
            
            fileList.innerHTML = files.map(file => `
                <div class="file-item">
                    <div class="file-info">
                        <div class="file-name">${escapeHtml(file.name)}</div>
                        <div class="file-meta">
                            ${formatSize(file.size_mb)} MB • ${formatDate(file.uploaded_at)} • ${file.type === 'text' ? '📝 Text' : '📁 File'}
                        </div>
                        <div class="file-expiry" style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                            Auto-delete: ${formatDate(file.expires_at)}
                        </div>
                    </div>
                    <div class="file-actions">
                        ${file.type === 'text' ? `
                            <button class="btn btn-secondary copy-btn" id="copy-btn-${escapeHtml(file.name).replace(/[^a-zA-Z0-9]/g, '_')}" onclick="copyText('${escapeHtml(file.name)}', this)">
                                📋 Copy
                            </button>
                        ` : ''}
                        <a href="/download/${encodeURIComponent(file.name)}" class="btn btn-secondary" download>
                            Download
                        </a>
                        <button class="btn btn-danger" onclick="deleteFile('${escapeHtml(file.name)}')">
                            Delete
                        </button>
                    </div>
                </div>
            `).join('');
        }
        
        async function copyText(filename, buttonElement) {
            const originalText = buttonElement.textContent;
            
            try {
                const response = await fetch('/api/text/' + encodeURIComponent(filename));
                const result = await response.json();
                
                if (!response.ok || !result.content) {
                    buttonElement.textContent = '❌ Error';
                    setTimeout(() => {
                        buttonElement.textContent = originalText;
                    }, 2000);
                    return;
                }
                
                // Try modern clipboard API first
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    try {
                        await navigator.clipboard.writeText(result.content);
                        buttonElement.textContent = '✓ Copied';
                        setTimeout(() => {
                            buttonElement.textContent = originalText;
                        }, 2000);
                        return;
                    } catch (clipboardError) {
                        // Fall through to fallback method
                    }
                }
                
                // Fallback for older browsers or when clipboard API fails
                const textArea = document.createElement('textarea');
                textArea.value = result.content;
                textArea.style.position = 'fixed';
                textArea.style.left = '-9999px';
                textArea.style.top = '0';
                textArea.style.opacity = '0';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                
                try {
                    const successful = document.execCommand('copy');
                    document.body.removeChild(textArea);
                    if (successful) {
                        buttonElement.textContent = '✓ Copied';
                        setTimeout(() => {
                            buttonElement.textContent = originalText;
                        }, 2000);
                    } else {
                        buttonElement.textContent = '❌ Failed';
                        setTimeout(() => {
                            buttonElement.textContent = originalText;
                        }, 2000);
                    }
                } catch (execError) {
                    document.body.removeChild(textArea);
                    buttonElement.textContent = '❌ Failed';
                    setTimeout(() => {
                        buttonElement.textContent = originalText;
                    }, 2000);
                }
            } catch (error) {
                buttonElement.textContent = '❌ Error';
                setTimeout(() => {
                    buttonElement.textContent = originalText;
                }, 2000);
            }
        }
        
        async function deleteFile(filename) {
            if (!confirm('Are you sure you want to delete this file?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/delete/' + encodeURIComponent(filename), {
                    method: 'POST'
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    showAlert('File deleted successfully', 'success');
                    loadFiles();
                    loadStats();
                } else {
                    showAlert('Delete failed: ' + (result.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                showAlert('Delete error: ' + error.message, 'error');
            }
        }
        
        function showAlert(message, type) {
            const container = document.getElementById('alert-container');
            const alert = document.createElement('div');
            alert.className = 'alert alert-' + type;
            alert.textContent = message;
            container.appendChild(alert);
            
            setTimeout(() => {
                alert.remove();
            }, 5000);
        }
        
        function showProgress(show) {
            document.getElementById('upload-progress').classList.toggle('hidden', !show);
        }
        
        function formatSize(mb) {
            return mb.toFixed(2);
        }
        
        function formatDate(isoString) {
            const date = new Date(isoString);
            return date.toLocaleString();
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        """


def get_local_ip():
    """Get local network IP address without external connections"""
    try:
        # Get local IP by checking network interfaces
        hostname = socket.gethostname()
        ip_list = socket.gethostbyname_ex(hostname)[2]
        
        # Filter out localhost and link-local addresses
        for ip in ip_list:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
        
        # Fallback to first non-localhost IP or localhost
        return ip_list[0] if ip_list else "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Odysafe QuickShare - Simple network file sharing')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Server port (default: {DEFAULT_PORT})')
    parser.add_argument('--host', type=str, default=DEFAULT_HOST, help=f'Host interface (default: {DEFAULT_HOST})')
    parser.add_argument('--cleanup-hours', type=int, default=DEFAULT_CLEANUP_HOURS, 
                       help=f'Hours before auto-cleanup (default: {DEFAULT_CLEANUP_HOURS})')
    parser.add_argument('--max-size', type=int, default=DEFAULT_MAX_SIZE_MB,
                       help=f'Max file size in MB (default: {DEFAULT_MAX_SIZE_MB})')
    parser.add_argument('--storage-dir', type=str, default=DEFAULT_STORAGE_DIR,
                       help=f'Storage directory (default: {DEFAULT_STORAGE_DIR})')
    
    args = parser.parse_args()
    
    # Create server instance
    server_instance = FileSharingServer(
        storage_dir=args.storage_dir,
        cleanup_hours=args.cleanup_hours,
        max_size_mb=args.max_size
    )
    
    # Set server instance for handler
    FileSharingHTTPRequestHandler.server_instance = server_instance
    
    # Create HTTP server
    httpd = HTTPServer((args.host, args.port), FileSharingHTTPRequestHandler)
    
    # Get network info
    local_ip = get_local_ip()
    
    print("=" * 60)
    print("Odysafe QuickShare")
    print("=" * 60)
    print(f"Storage directory: {server_instance.storage_dir.absolute()}")
    print(f"Cleanup interval: {args.cleanup_hours} hours")
    print(f"Max file size: {args.max_size} MB")
    print("=" * 60)
    print(f"Server running on:")
    print(f"  Local:   http://127.0.0.1:{args.port}")
    print(f"  Network: http://{local_ip}:{args.port}")
    print("=" * 60)
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()


if __name__ == '__main__':
    main()

