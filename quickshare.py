#!/usr/bin/env python3
"""
Odysafe QuickShare - Simple network file sharing solution
A lightweight Python script for sharing files, folders, and text over local network.
"""

import os
import json
import time
import socket
import ssl
import threading
import argparse
import mimetypes
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration defaults
DEFAULT_PORT = 8000
DEFAULT_HOST = '0.0.0.0'
DEFAULT_CLEANUP_HOURS = 24
DEFAULT_MAX_SIZE_MB = 1024
DEFAULT_STORAGE_DIR = './shared_files'
DEFAULT_SSL_CERT = None
DEFAULT_SSL_KEY = None

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
        
        # Load metadata for original filenames
        metadata_file = self.metadata_dir / 'files.json'
        metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            except:
                metadata = {}
        
        # Get uploaded files
        for file_path in self.uploads_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                uploaded_time = datetime.fromtimestamp(stat.st_mtime)
                expires_at = uploaded_time + timedelta(hours=self.cleanup_hours)
                # Get original name from metadata if available
                file_metadata = metadata.get(file_path.name, {})
                display_name = file_metadata.get('original_name', file_path.name)
                files.append({
                    'name': file_path.name,  # Actual filename on disk
                    'display_name': display_name,  # Original filename for display
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
                # Get original name from metadata if available
                file_metadata = metadata.get(file_path.name, {})
                display_name = file_metadata.get('original_name', file_path.name)
                files.append({
                    'name': file_path.name,  # Actual filename on disk
                    'display_name': display_name,  # Original filename for display
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
        original_filename = filename  # Store original name
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
            original_filename = f"text_{timestamp}.txt"
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Store original filename in metadata
        metadata_file = self.metadata_dir / 'files.json'
        metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            except:
                metadata = {}
        
        metadata[file_path.name] = {
            'original_name': original_filename,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return file_path
    
    def save_file_streaming(self, filename, source_stream, file_type='file', expected_size=None):
        """Save uploaded file using streaming to avoid loading entire file in RAM"""
        original_filename = filename
        if file_type == 'file':
            sanitized = self._sanitize_filename(filename)
            name_parts = os.path.splitext(sanitized)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if name_parts[1]:
                new_filename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
            else:
                new_filename = f"{sanitized}_{timestamp}"
            file_path = self.uploads_dir / new_filename
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = self.text_shares_dir / f"text_{timestamp}.txt"
            original_filename = f"text_{timestamp}.txt"
        
        # Stream directly to disk in chunks
        chunk_size = 8192  # 8KB chunks
        total_written = 0
        remaining = expected_size if expected_size else None
        
        try:
            with open(file_path, 'wb') as f:
                while True:
                    # If we have an expected size, read only what's remaining
                    if remaining is not None:
                        if remaining <= 0:
                            break
                        read_size = min(chunk_size, remaining)
                    else:
                        read_size = chunk_size
                    
                    chunk = source_stream.read(read_size)
                    if not chunk:
                        # If we expected more data but got EOF, that's an error
                        if remaining is not None and remaining > 0:
                            raise ValueError(f'Unexpected end of stream: expected {expected_size} bytes but got {total_written}')
                        break
                    
                    f.write(chunk)
                    total_written += len(chunk)
                    
                    if remaining is not None:
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise ValueError(f'File size exceeds limit: got {total_written} bytes but expected {expected_size}')
                    
                    # Check size limit during streaming
                    if expected_size and total_written > expected_size:
                        f.close()
                        if file_path.exists():
                            file_path.unlink()
                        raise ValueError(f'File size exceeds limit')
                    if not expected_size and total_written > self.max_size_bytes:
                        f.close()
                        if file_path.exists():
                            file_path.unlink()
                        raise ValueError(f'File size exceeds {self.max_size_bytes / (1024*1024):.0f} MB limit')
            
            # Store metadata
            metadata_file = self.metadata_dir / 'files.json'
            metadata = {}
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                except:
                    metadata = {}
            
            metadata[file_path.name] = {
                'original_name': original_filename,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return file_path, total_written
        except Exception as e:
            # Clean up partial file on error
            if file_path.exists():
                try:
                    file_path.unlink()
                except:
                    pass
            raise
    
    def delete_file(self, filename):
        """Delete a file and its metadata"""
        # Sanitize filename to prevent directory traversal
        sanitized = self._sanitize_filename(filename)
        
        # Also try the original filename (in case sanitize changed it)
        original_name = os.path.basename(filename)
        original_name = original_name.replace('..', '').replace('/', '').replace('\\', '')
        
        # List of filenames to try
        filenames_to_try = [sanitized, original_name, filename]
        # Remove duplicates while preserving order
        seen = set()
        filenames_to_try = [f for f in filenames_to_try if f and f not in seen and not seen.add(f)]
        
        # Try uploads first
        for name_to_try in filenames_to_try:
            file_path = self.uploads_dir / name_to_try
            if file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                    # Remove from metadata (try both names)
                    self._remove_from_metadata(name_to_try)
                    self._remove_from_metadata(sanitized)
                    print(f"[DELETE] Successfully deleted upload: {file_path}")
                    return True
                except Exception as e:
                    print(f"[DELETE] Error deleting file {file_path}: {e}")
                    continue
        
        # Try text shares
        for name_to_try in filenames_to_try:
            file_path = self.text_shares_dir / name_to_try
            if file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                    # Remove from metadata (try both names)
                    self._remove_from_metadata(name_to_try)
                    self._remove_from_metadata(sanitized)
                    print(f"[DELETE] Successfully deleted text share: {file_path}")
                    return True
                except Exception as e:
                    print(f"[DELETE] Error deleting file {file_path}: {e}")
                    continue
        
        # If not found by name, try to find by iterating (last resort)
        print(f"[DELETE] File not found by name, searching in directories...")
        for file_path in self.uploads_dir.iterdir():
            if file_path.is_file() and file_path.name == filename:
                try:
                    file_path.unlink()
                    self._remove_from_metadata(file_path.name)
                    print(f"[DELETE] Successfully deleted (found by iteration): {file_path}")
                    return True
                except Exception as e:
                    print(f"[DELETE] Error deleting file {file_path}: {e}")
        
        for file_path in self.text_shares_dir.iterdir():
            if file_path.is_file() and file_path.name == filename:
                try:
                    file_path.unlink()
                    self._remove_from_metadata(file_path.name)
                    print(f"[DELETE] Successfully deleted (found by iteration): {file_path}")
                    return True
                except Exception as e:
                    print(f"[DELETE] Error deleting file {file_path}: {e}")
        
        print(f"[DELETE] File not found: {filename} (tried: {filenames_to_try})")
        return False
    
    def _remove_from_metadata(self, filename):
        """Remove file entry from metadata"""
        metadata_file = self.metadata_dir / 'files.json'
        if not metadata_file.exists():
            return
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Remove the file from metadata if it exists
            if filename in metadata:
                del metadata[filename]
                
                # Save updated metadata
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"Error removing metadata for {filename}: {e}")
    
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
        stats['max_size_mb'] = self.server_instance.max_size_bytes / (1024 * 1024)
        self._send_response(200, stats, content_type='application/json')
    
    def _serve_text_content(self, path):
        """Serve text file content as JSON"""
        try:
            filename = unquote(path.replace('/api/text/', ''))
            if not filename or not filename.strip():
                self._send_response(400, {'error': 'Invalid filename'}, content_type='application/json')
                return
                
            file_path = self.server_instance.get_file(filename)
            
            if not file_path or not file_path.exists():
                self._send_response(404, {'error': 'File not found'}, content_type='application/json')
                return
            
            # Check if it's a text file
            if file_path.parent.name != TEXT_SHARES_DIR:
                self._send_response(400, {'error': 'Not a text file'}, content_type='application/json')
                return
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if not content:
                self._send_response(400, {'error': 'File is empty'}, content_type='application/json')
                return
            
            self._send_response(200, {
                'success': True,
                'content': content,
                'filename': filename
            }, content_type='application/json')
        except PermissionError:
            self._send_response(403, {'error': 'Permission denied'}, content_type='application/json')
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Text content error: {error_details}")
            self._send_response(500, {'error': f'Server error: {str(e)}'}, content_type='application/json')
    
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
            # Allow up to 10 files, each up to max_size_bytes
            if content_length > self.server_instance.max_size_bytes * 10:
                self._send_response(400, {'error': 'Total upload size too large'}, content_type='application/json')
                return
            
            # Extract boundary
            boundary_str = content_type.split('boundary=')[1].strip()
            # Remove quotes if present
            if boundary_str.startswith('"') and boundary_str.endswith('"'):
                boundary_str = boundary_str[1:-1]
            boundary = boundary_str.encode() if isinstance(boundary_str, str) else boundary_str
            boundary_marker = b'--' + boundary
            
            # For multipart, we need to parse boundaries to extract filenames
            # We'll read in chunks to minimize memory usage, but still need to parse boundaries
            # This is a compromise: we parse boundaries in memory (small overhead) but stream file content
            data = self.rfile.read(content_length)
            
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
                        line_lower = line.lower()
                        if b'filename' in line_lower:
                            # Try filename="..." (quoted filename) - most common
                            filename_quoted_start = line.find(b'filename="')
                            if filename_quoted_start != -1:
                                start = filename_quoted_start + 10  # len(b'filename="') = 10
                                # Find the closing quote
                                end = line.find(b'"', start)
                                if end != -1:
                                    filename_match = line[start:end]
                                    # Ensure we got the full filename
                                    if len(filename_match) > 0:
                                        pass  # Good, we have a match
                            # Try filename=... (unquoted filename)
                            elif b'filename=' in line_lower:
                                filename_eq_pos = line_lower.find(b'filename=')
                                start = filename_eq_pos + 9  # len(b'filename=')
                                # Find end (space, semicolon, or end of line)
                                end = len(line)
                                for char in [b' ', b';', b'\r', b'\n']:
                                    idx = line.find(char, start)
                                    if idx != -1 and idx < end:
                                        end = idx
                                if end > start:
                                    filename_match = line[start:end]
                            
                            if filename_match:
                                try:
                                    # Decode the filename - preserve all characters
                                    # Try UTF-8 first
                                    decoded = filename_match.decode('utf-8', errors='replace')
                                    # Remove only surrounding quotes, not internal ones
                                    if decoded.startswith('"') and decoded.endswith('"'):
                                        decoded = decoded[1:-1]
                                    if decoded.startswith("'") and decoded.endswith("'"):
                                        decoded = decoded[1:-1]
                                    # Use unquote to handle URL-encoded filenames (like %20 for space)
                                    filename = unquote(decoded)
                                except Exception as decode_error:
                                    try:
                                        # Fallback to latin-1
                                        decoded = filename_match.decode('latin-1', errors='replace')
                                        if decoded.startswith('"') and decoded.endswith('"'):
                                            decoded = decoded[1:-1]
                                        if decoded.startswith("'") and decoded.endswith("'"):
                                            decoded = decoded[1:-1]
                                        filename = unquote(decoded)
                                    except Exception:
                                        # Last resort: use raw bytes as string
                                        try:
                                            decoded = filename_match.decode('utf-8', errors='replace')
                                            filename = decoded.strip('"').strip("'")
                                        except:
                                            filename = str(filename_match)
                                if filename:
                                    break
                
                if filename and file_content:
                    # Validate filename is not empty after processing
                    if not filename or not filename.strip():
                        continue
                    
                    # Check individual file size
                    file_size = len(file_content)
                    if file_size > self.server_instance.max_size_bytes:
                        uploaded_files.append({
                            'filename': None,
                            'size': file_size,
                            'original_name': filename,
                            'error': f'File size exceeds {self.server_instance.max_size_bytes / (1024*1024):.0f} MB limit'
                        })
                        continue
                    
                    try:
                        # Use BytesIO to stream the content instead of passing raw bytes
                        # This allows save_file_streaming to work with the content
                        content_stream = BytesIO(file_content)
                        file_path, written_size = self.server_instance.save_file_streaming(
                            filename,
                            content_stream,
                            file_type='file',
                            expected_size=file_size
                        )
                        uploaded_files.append({
                            'filename': file_path.name,
                            'size': written_size,
                            'original_name': filename
                        })
                    except Exception as save_error:
                        uploaded_files.append({
                            'filename': None,
                            'size': file_size,
                            'original_name': filename,
                            'error': f'Failed to save file: {str(save_error)}'
                        })
            
            # Filter successful uploads
            successful_uploads = [f for f in uploaded_files if f.get('filename')]
            failed_uploads = [f for f in uploaded_files if not f.get('filename')]
            
            if successful_uploads:
                response_data = {
                    'success': True,
                    'uploaded': len(successful_uploads),
                    'files': successful_uploads
                }
                if failed_uploads:
                    response_data['failed'] = failed_uploads
                self._send_response(200, response_data, content_type='application/json')
            elif failed_uploads:
                # All uploads failed
                error_messages = [f.get('error', 'Unknown error') for f in failed_uploads]
                self._send_response(400, {
                    'error': 'All uploads failed',
                    'details': error_messages,
                    'files': failed_uploads
                }, content_type='application/json')
            else:
                self._send_response(400, {'error': 'No files uploaded'}, content_type='application/json')
            
        except ValueError as ve:
            self._send_response(400, {'error': f'Invalid request: {str(ve)}'}, content_type='application/json')
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Upload error: {error_details}")
            self._send_response(500, {'error': f'Server error: {str(e)}'}, content_type='application/json')
    
    def _handle_text_upload(self):
        """Handle text sharing with streaming to disk"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0:
                self._send_response(400, {'error': 'Empty content'}, content_type='application/json')
                return
                
            if content_length > self.server_instance.max_size_bytes:
                self._send_response(400, {'error': f'Text too large (max {self.server_instance.max_size_bytes / (1024*1024):.0f} MB)'}, content_type='application/json')
                return
            
            # Stream directly to disk without loading in RAM
            # Create a wrapper that limits reading to content_length bytes
            class LimitedStream:
                def __init__(self, stream, max_bytes):
                    self.stream = stream
                    self.max_bytes = max_bytes
                    self.bytes_read = 0
                
                def read(self, size=-1):
                    if self.bytes_read >= self.max_bytes:
                        return b''
                    remaining = self.max_bytes - self.bytes_read
                    if size == -1 or size > remaining:
                        size = remaining
                    chunk = self.stream.read(size)
                    self.bytes_read += len(chunk)
                    return chunk
            
            try:
                limited_stream = LimitedStream(self.rfile, content_length)
                file_path, written_size = self.server_instance.save_file_streaming(
                    'text_share.txt',
                    limited_stream,
                    file_type='text',
                    expected_size=content_length
                )
                
                # Verify the file is not empty (basic check)
                if written_size == 0:
                    if file_path.exists():
                        file_path.unlink()
                    self._send_response(400, {'error': 'Empty text content'}, content_type='application/json')
                    return
                
                self._send_response(200, {
                    'success': True,
                    'filename': file_path.name
                }, content_type='application/json')
            except ValueError as ve:
                # Size limit exceeded during streaming
                self._send_response(400, {'error': str(ve)}, content_type='application/json')
            except Exception as save_error:
                import traceback
                error_details = traceback.format_exc()
                print(f"Text upload save error: {error_details}")
                self._send_response(500, {'error': f'Failed to save text: {str(save_error)}'}, content_type='application/json')
            
        except ValueError as ve:
            self._send_response(400, {'error': f'Invalid request: {str(ve)}'}, content_type='application/json')
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Text upload error: {error_details}")
            self._send_response(500, {'error': f'Server error: {str(e)}'}, content_type='application/json')
    
    def _handle_delete(self, path):
        """Handle file deletion"""
        try:
            # Extract filename from path
            filename = path.replace('/api/delete/', '')
            # Decode URL-encoded filename
            filename = unquote(filename)
            
            # Log for debugging
            print(f"[DELETE] Attempting to delete file: {filename}")
            
            if self.server_instance.delete_file(filename):
                print(f"[DELETE] Successfully deleted: {filename}")
                self._send_response(200, {'success': True, 'message': 'File deleted successfully'}, content_type='application/json')
            else:
                print(f"[DELETE] File not found: {filename}")
                self._send_response(404, {'error': 'File not found', 'filename': filename}, content_type='application/json')
        except Exception as e:
            print(f"[DELETE] Error deleting file: {e}")
            self._send_response(500, {'error': f'Server error: {str(e)}'}, content_type='application/json')
    
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
        # Get current URL for QR code generation
        host = self.headers.get('Host', 'localhost:8000')
        # Detect HTTPS: check if connection is secure or if port is 8443
        port = host.split(':')[-1] if ':' in host else '8000'
        is_https = (
            hasattr(self.request, 'is_secure') and self.request.is_secure() or
            self.headers.get('X-Forwarded-Proto') == 'https' or
            port in ['8443', '443']
        )
        protocol = 'https' if is_https else 'http'
        base_url = f"{protocol}://{host}"
        
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
        // QR Code library (minimal implementation)
        {self._get_qrcode_library()}
        // Base URL for API calls
        const BASE_URL = '{base_url}';
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
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(10px);
        }
        
        .modal-content {
            background: rgba(22, 27, 34, 0.95);
            margin: 10% auto;
            padding: 32px;
            border: 1px solid rgba(167, 139, 250, 0.2);
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
            text-align: center;
            box-shadow: 0 12px 48px rgba(139, 92, 246, 0.3);
        }
        
        .modal-content h3 {
            color: var(--white);
            margin-bottom: 24px;
            font-size: 24px;
        }
        
        .qrcode-container {
            background: white;
            padding: 20px;
            border-radius: 12px;
            display: inline-block;
            margin: 20px 0;
        }
        
        .qrcode-container canvas {
            display: block;
        }
        
        .modal-close {
            color: var(--text-secondary);
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            margin-top: -10px;
        }
        
        .modal-close:hover {
            color: var(--white);
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
            
            .modal-content {
                margin: 20% auto;
                padding: 24px;
            }
        }
        """
    
    def _get_qrcode_library(self):
        """Get QR Code library - integrated qrcode.js library"""
        # Using the standard qrcode.js library embedded inline
        # Source: https://github.com/davidshimjs/qrcodejs
        return """
        // QRCode.js library - embedded inline (no external dependencies)
        // Source: https://github.com/davidshimjs/qrcodejs
        (function() {
            var QRCode = function(el, opt) {
                this._el = el;
                this._htOption = {
                    width: 256,
                    height: 256,
                    typeNumber: 4,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.M
                };
                if (typeof opt === 'string') {
                    opt = { text: opt };
                }
                if (opt) {
                    for (var i in opt) {
                        this._htOption[i] = opt[i];
                    }
                }
                if (this._el) {
                    this.makeCode(this._htOption.text || '');
                }
            };
            QRCode.prototype.makeCode = function(sText) {
                this._oQRCode = new QRCodeLib._QRCode(this._htOption.typeNumber, this._htOption.correctLevel);
                this._oQRCode.addData(sText);
                this._oQRCode.make();
                this._el.innerHTML = '';
                this._draw();
            };
            QRCode.prototype._draw = function() {
                var _htOption = this._htOption;
                var _oQRCode = this._oQRCode;
                var _el = this._el;
                var nCount = _oQRCode.getModuleCount();
                var nWidth = Math.floor(_htOption.width / nCount);
                var nHeight = Math.floor(_htOption.height / nCount);
                var nRoundedWidth = nWidth * nCount;
                var nRoundedHeight = nHeight * nCount;
                _el.style.width = nRoundedWidth + "px";
                _el.style.height = nRoundedHeight + "px";
                _el.innerHTML = "";
                var oCanvas = document.createElement("canvas");
                oCanvas.width = nRoundedWidth;
                oCanvas.height = nRoundedHeight;
                var ctx = oCanvas.getContext("2d");
                for (var row = 0; row < nCount; row++) {
                    for (var col = 0; col < nCount; col++) {
                        var bIsDark = _oQRCode.isDark(row, col);
                        ctx.fillStyle = bIsDark ? _htOption.colorDark : _htOption.colorLight;
                        ctx.fillRect(col * nWidth, row * nHeight, nWidth, nHeight);
                    }
                }
                _el.appendChild(oCanvas);
            };
            QRCode.CorrectLevel = { L: 1, M: 0, Q: 3, H: 2 };
            window.QRCode = QRCode;
        })();
        
        // QRCodeLib - Core QR Code implementation
        (function() {
            var QRCodeLib = {};
            QRCodeLib._QRCode = function(typeNumber, errorCorrectLevel) {
                this.typeNumber = typeNumber;
                this.errorCorrectLevel = errorCorrectLevel;
                this.modules = null;
                this.moduleCount = 0;
                this.dataCache = null;
                this.dataList = [];
            };
            QRCodeLib._QRCode.prototype = {
                addData: function(data) {
                    var newData = new QRCodeLib._QR8bitByte(data);
                    this.dataList.push(newData);
                    this.dataCache = null;
                },
                isDark: function(row, col) {
                    if (row < 0 || this.moduleCount <= row || col < 0 || this.moduleCount <= col) {
                        throw new Error(row + "," + col);
                    }
                    return this.modules[row][col];
                },
                getModuleCount: function() {
                    return this.moduleCount;
                },
                make: function() {
                    this.makeImpl(false, this.getBestMaskPattern());
                },
                makeImpl: function(test, maskPattern) {
                    this.moduleCount = this.typeNumber * 4 + 17;
                    this.modules = new Array(this.moduleCount);
                    for (var row = 0; row < this.moduleCount; row++) {
                        this.modules[row] = new Array(this.moduleCount);
                        for (var col = 0; col < this.moduleCount; col++) {
                            this.modules[row][col] = null;
                        }
                    }
                    this.setupPositionProbePattern(0, 0);
                    this.setupPositionProbePattern(this.moduleCount - 7, 0);
                    this.setupPositionProbePattern(0, this.moduleCount - 7);
                    this.setupPositionAdjustPattern();
                    this.setupTimingPattern();
                    this.setupTypeInfo(test, maskPattern);
                    if (this.typeNumber >= 7) {
                        this.setupTypeNumber(test);
                    }
                    if (this.dataCache == null) {
                        this.dataCache = QRCodeLib._QRCode.createData(this.typeNumber, this.errorCorrectLevel, this.dataList);
                    }
                    this.mapData(this.dataCache, maskPattern);
                },
                setupPositionProbePattern: function(row, col) {
                    for (var r = -1; r <= 7; r++) {
                        if (row + r <= -1 || this.moduleCount <= row + r) continue;
                        for (var c = -1; c <= 7; c++) {
                            if (col + c <= -1 || this.moduleCount <= col + c) continue;
                            if ((0 <= r && r <= 6 && (c == 0 || c == 6)) || (0 <= c && c <= 6 && (r == 0 || r == 6)) || (2 <= r && r <= 4 && 2 <= c && c <= 4)) {
                                this.modules[row + r][col + c] = true;
                            } else {
                                this.modules[row + r][col + c] = false;
                            }
                        }
                    }
                },
                getBestMaskPattern: function() {
                    var minLostPoint = 0;
                    var pattern = 0;
                    for (var i = 0; i < 8; i++) {
                        this.makeImpl(true, i);
                        var lostPoint = QRCodeLib.Util.getLostPoint(this);
                        if (i == 0 || minLostPoint > lostPoint) {
                            minLostPoint = lostPoint;
                            pattern = i;
                        }
                    }
                    return pattern;
                },
                setupTimingPattern: function() {
                    for (var r = 8; r < this.moduleCount - 8; r++) {
                        if (this.modules[r][6] != null) {
                            continue;
                        }
                        this.modules[r][6] = (r % 2 == 0);
                    }
                    for (var c = 8; c < this.moduleCount - 8; c++) {
                        if (this.modules[6][c] != null) {
                            continue;
                        }
                        this.modules[6][c] = (c % 2 == 0);
                    }
                },
                setupPositionAdjustPattern: function() {
                    var pos = QRCodeLib.Util.getPatternPosition(this.typeNumber);
                    for (var i = 0; i < pos.length; i++) {
                        for (var j = 0; j < pos.length; j++) {
                            var row = pos[i];
                            var col = pos[j];
                            if (this.modules[row][col] != null) {
                                continue;
                            }
                            for (var r = -2; r <= 2; r++) {
                                for (var c = -2; c <= 2; c++) {
                                    if (r == -2 || r == 2 || c == -2 || c == 2 || (r == 0 && c == 0)) {
                                        this.modules[row + r][col + c] = true;
                                    } else {
                                        this.modules[row + r][col + c] = false;
                                    }
                                }
                            }
                        }
                    }
                },
                setupTypeNumber: function(test) {
                    var bits = QRCodeLib.Util.getBCHTypeNumber(this.typeNumber);
                    for (var i = 0; i < 18; i++) {
                        var mod = (!test && ((bits >> i) & 1) == 1);
                        this.modules[Math.floor(i / 3)][i % 3 + this.moduleCount - 8 - 3] = mod;
                    }
                    for (var i = 0; i < 18; i++) {
                        var mod = (!test && ((bits >> i) & 1) == 1);
                        this.modules[i % 3 + this.moduleCount - 8 - 3][Math.floor(i / 3)] = mod;
                    }
                },
                setupTypeInfo: function(test, maskPattern) {
                    var data = (this.errorCorrectLevel << 3) | maskPattern;
                    var bits = QRCodeLib.Util.getBCHTypeInfo(data);
                    for (var i = 0; i < 15; i++) {
                        var mod = (!test && ((bits >> i) & 1) == 1);
                        if (i < 6) {
                            this.modules[i][8] = mod;
                        } else if (i < 8) {
                            this.modules[i + 1][8] = mod;
                        } else {
                            this.modules[this.moduleCount - 15 + i][8] = mod;
                        }
                    }
                    for (var i = 0; i < 15; i++) {
                        var mod = (!test && ((bits >> i) & 1) == 1);
                        if (i < 8) {
                            this.modules[8][this.moduleCount - i - 1] = mod;
                        } else if (i < 9) {
                            this.modules[8][15 - i - 1 + 1] = mod;
                        } else {
                            this.modules[8][15 - i - 1] = mod;
                        }
                    }
                    this.modules[this.moduleCount - 8][8] = (!test);
                },
                mapData: function(data, maskPattern) {
                    var inc = -1;
                    var row = this.moduleCount - 1;
                    var bitIndex = 7;
                    var byteIndex = 0;
                    for (var col = this.moduleCount - 1; col > 0; col -= 2) {
                        if (col == 6) col--;
                        while (true) {
                            for (var c = 0; c < 2; c++) {
                                if (this.modules[row][col - c] == null) {
                                    var dark = false;
                                    if (byteIndex < data.length) {
                                        dark = (((data[byteIndex] >>> bitIndex) & 1) == 1);
                                    }
                                    var mask = QRCodeLib.Util.getMask(maskPattern, row, col - c);
                                    if (mask) {
                                        dark = !dark;
                                    }
                                    this.modules[row][col - c] = dark;
                                    bitIndex--;
                                    if (bitIndex == -1) {
                                        byteIndex++;
                                        bitIndex = 7;
                                    }
                                }
                            }
                            row += inc;
                            if (row < 0 || this.moduleCount <= row) {
                                row -= inc;
                                inc = -inc;
                                break;
                            }
                        }
                    }
                }
            };
            QRCodeLib._QRCode.createData = function(typeNumber, errorCorrectLevel, dataList) {
                var rsBlocks = QRCodeLib._QRRSBlock.getRSBlocks(typeNumber, errorCorrectLevel);
                var buffer = new QRCodeLib._QRBitBuffer();
                for (var i = 0; i < dataList.length; i++) {
                    var data = dataList[i];
                    buffer.put(data.mode, 4);
                    buffer.put(data.getLength(), QRCodeLib.Util.getLengthInBits(data.mode, typeNumber));
                    data.write(buffer);
                }
                var totalDataCount = 0;
                for (var i = 0; i < rsBlocks.length; i++) {
                    totalDataCount += rsBlocks[i].dataCount;
                }
                if (buffer.getLengthInBits() + 4 <= totalDataCount * 8) {
                    buffer.put(0, 4);
                }
                while (buffer.getLengthInBits() % 8 != 0) {
                    buffer.putBit(false);
                }
                while (true) {
                    if (buffer.getLengthInBits() >= totalDataCount * 8) {
                        break;
                    }
                    buffer.put(0xEC, 8);
                    if (buffer.getLengthInBits() >= totalDataCount * 8) {
                        break;
                    }
                    buffer.put(0x11, 8);
                }
                return QRCodeLib._QRCode.createBytes(buffer, rsBlocks);
            };
            QRCodeLib._QRCode.createBytes = function(buffer, rsBlocks) {
                var offset = 0;
                var maxDcCount = 0;
                var maxEcCount = 0;
                var dcdata = new Array(rsBlocks.length);
                var ecdata = new Array(rsBlocks.length);
                for (var r = 0; r < rsBlocks.length; r++) {
                    var dcCount = rsBlocks[r].dataCount;
                    var ecCount = rsBlocks[r].totalCount - dcCount;
                    maxDcCount = Math.max(maxDcCount, dcCount);
                    maxEcCount = Math.max(maxEcCount, ecCount);
                    dcdata[r] = new Array(dcCount);
                    for (var i = 0; i < dcdata[r].length; i++) {
                        dcdata[r][i] = 0xff & buffer.buffer[i + offset];
                    }
                    offset += dcCount;
                    var rsPoly = QRCodeLib._QRPolynomial.getErrorCorrectPolynomial(ecCount);
                    var rawPoly = new QRCodeLib._QRPolynomial(dcdata[r], rsPoly.getLength() - 1);
                    var modPoly = rawPoly.mod(rsPoly);
                    ecdata[r] = new Array(rsPoly.getLength() - 1);
                    for (var i = 0; i < ecdata[r].length; i++) {
                        var modIndex = i + modPoly.getLength() - ecdata[r].length;
                        ecdata[r][i] = (modIndex >= 0) ? modPoly.get(modIndex) : 0;
                    }
                }
                var totalCodeCount = 0;
                for (var i = 0; i < rsBlocks.length; i++) {
                    totalCodeCount += rsBlocks[i].totalCount;
                }
                var data = new Array(totalCodeCount);
                var index = 0;
                for (var i = 0; i < maxDcCount; i++) {
                    for (var r = 0; r < rsBlocks.length; r++) {
                        if (i < dcdata[r].length) {
                            data[index++] = dcdata[r][i];
                        }
                    }
                }
                for (var i = 0; i < maxEcCount; i++) {
                    for (var r = 0; r < rsBlocks.length; r++) {
                        if (i < ecdata[r].length) {
                            data[index++] = ecdata[r][i];
                        }
                    }
                }
                return data;
            };
            QRCodeLib._QR8bitByte = function(data) {
                this.mode = QRCodeLib.Mode.MODE_8BIT_BYTE;
                this.data = data;
            };
            QRCodeLib._QR8bitByte.prototype = {
                getLength: function() {
                    return this.data.length;
                },
                write: function(buffer) {
                    for (var i = 0; i < this.data.length; i++) {
                        buffer.put(this.data.charCodeAt(i), 8);
                    }
                }
            };
            QRCodeLib.Mode = { MODE_NUMBER: 1 << 0, MODE_ALPHA_NUM: 1 << 1, MODE_8BIT_BYTE: 1 << 2, MODE_KANJI: 1 << 3 };
            QRCodeLib._QRRSBlock = function(totalCount, dataCount) {
                this.totalCount = totalCount;
                this.dataCount = dataCount;
            };
            QRCodeLib._QRRSBlock.RS_BLOCK_TABLE = [
                [1, 26, 19], [1, 26, 16], [1, 26, 13], [1, 26, 9], [1, 44, 34], [1, 44, 28], [1, 44, 22], [1, 44, 16],
                [1, 70, 55], [1, 70, 44], [2, 35, 17], [2, 35, 13], [1, 100, 80], [2, 50, 32], [2, 50, 24], [4, 25, 9],
                [1, 134, 108], [2, 67, 43], [2, 33, 15, 2, 34, 16], [2, 33, 11, 2, 34, 12], [2, 86, 68], [4, 43, 27],
                [4, 43, 19], [4, 43, 15], [2, 98, 78], [4, 49, 31], [2, 32, 14, 4, 33, 15], [4, 39, 13, 1, 40, 14],
                [2, 121, 97], [2, 60, 38, 2, 61, 39], [4, 40, 18, 2, 41, 19], [4, 40, 14, 2, 41, 15], [2, 146, 116],
                [3, 58, 36, 2, 59, 37], [4, 36, 16, 4, 37, 17], [4, 36, 12, 4, 37, 13], [2, 86, 68, 2, 87, 69],
                [4, 69, 43, 1, 70, 44], [6, 43, 19, 2, 44, 20], [6, 43, 15, 2, 44, 16], [4, 101, 81], [1, 80, 50, 4, 81, 51],
                [4, 50, 22, 4, 51, 23], [3, 36, 12, 8, 37, 13], [2, 116, 92, 2, 117, 93], [6, 58, 36, 2, 59, 37],
                [4, 46, 20, 6, 47, 21], [7, 42, 14, 4, 43, 15], [4, 133, 107], [8, 59, 37, 1, 60, 38], [8, 44, 20, 4, 45, 21],
                [12, 33, 11, 4, 34, 12], [3, 145, 115, 1, 146, 116], [4, 64, 40, 5, 65, 41], [11, 36, 16, 5, 37, 17],
                [11, 36, 12, 5, 37, 13], [5, 109, 87, 1, 110, 88], [5, 65, 41, 5, 66, 42], [5, 54, 24, 7, 55, 25],
                [11, 36, 12, 7, 37, 13], [5, 122, 98, 1, 123, 99], [7, 73, 45, 3, 74, 46], [15, 43, 19, 2, 44, 20],
                [3, 45, 15, 13, 46, 16], [1, 135, 107, 5, 136, 108], [10, 74, 46, 1, 75, 47], [1, 50, 22, 15, 51, 23],
                [2, 42, 14, 17, 43, 15], [5, 150, 120, 1, 151, 121], [9, 69, 43, 4, 70, 44], [17, 50, 22, 1, 51, 23],
                [2, 42, 14, 19, 43, 15], [3, 141, 113, 4, 142, 114], [3, 70, 44, 11, 71, 45], [17, 47, 21, 4, 48, 22],
                [9, 39, 13, 16, 40, 14], [3, 135, 107, 5, 136, 108], [3, 67, 41, 13, 68, 42], [15, 54, 24, 5, 55, 25],
                [15, 43, 15, 10, 44, 16], [4, 144, 116, 4, 145, 117], [17, 68, 42], [17, 50, 22, 6, 51, 23],
                [19, 46, 16, 6, 47, 17], [2, 139, 111, 7, 140, 112], [17, 74, 46], [7, 54, 24, 16, 55, 25],
                [34, 37, 13], [4, 151, 121, 5, 152, 122], [4, 75, 47, 14, 76, 48], [11, 54, 24, 14, 55, 25],
                [16, 45, 15, 14, 46, 16], [6, 147, 117, 4, 148, 118], [6, 73, 45, 14, 74, 46], [11, 54, 24, 16, 55, 25],
                [30, 46, 16, 2, 47, 17], [8, 132, 106, 4, 133, 107], [8, 75, 47, 13, 76, 48], [7, 54, 24, 22, 55, 25],
                [22, 45, 15, 13, 46, 16], [10, 142, 114, 2, 143, 115], [19, 73, 45, 4, 74, 46], [28, 50, 22, 6, 51, 23],
                [33, 46, 16, 4, 47, 17], [8, 152, 122, 4, 153, 123], [22, 73, 45, 3, 74, 46], [8, 53, 23, 26, 54, 24],
                [12, 45, 15, 28, 46, 16], [3, 147, 117, 10, 148, 118], [3, 73, 45, 23, 74, 46], [4, 54, 24, 31, 55, 25],
                [11, 45, 15, 31, 46, 16], [7, 146, 116, 7, 147, 117], [21, 73, 45, 7, 74, 46], [1, 53, 23, 37, 54, 24],
                [19, 45, 15, 26, 46, 16], [5, 145, 115, 10, 146, 116], [19, 75, 47, 10, 76, 48], [15, 54, 24, 25, 55, 25],
                [23, 45, 15, 25, 46, 16], [13, 145, 115, 3, 146, 116], [2, 74, 46, 29, 75, 47], [42, 54, 24, 1, 55, 25],
                [23, 45, 15, 28, 46, 16], [17, 145, 115], [10, 74, 46, 23, 75, 47], [10, 54, 24, 35, 55, 25],
                [19, 45, 15, 35, 46, 16], [17, 145, 115, 1, 146, 116], [14, 74, 46, 21, 75, 47], [29, 54, 24, 19, 55, 25],
                [11, 45, 15, 46, 46, 16], [13, 145, 115, 6, 146, 116], [14, 74, 46, 23, 75, 47], [44, 54, 24, 7, 55, 25],
                [59, 46, 16, 1, 47, 17], [12, 151, 121, 7, 152, 122], [12, 75, 47, 26, 76, 48], [39, 54, 24, 14, 55, 25],
                [22, 45, 15, 41, 46, 16], [6, 151, 121, 14, 152, 122], [6, 75, 47, 34, 76, 48], [46, 54, 24, 10, 55, 25],
                [2, 45, 15, 64, 46, 16], [17, 152, 122, 4, 153, 123], [29, 74, 46, 14, 75, 47], [49, 54, 24, 10, 55, 25],
                [24, 45, 15, 46, 46, 16], [4, 152, 122, 18, 153, 123], [13, 74, 46, 32, 75, 47], [48, 54, 24, 14, 55, 25],
                [42, 45, 15, 32, 46, 16], [20, 147, 117, 4, 148, 118], [40, 75, 47, 7, 76, 48], [43, 54, 24, 22, 55, 25],
                [10, 45, 15, 67, 46, 16], [19, 148, 118, 6, 149, 119], [18, 75, 47, 31, 76, 48], [34, 54, 24, 34, 55, 25],
                [20, 45, 15, 61, 46, 16]
            ];
            QRCodeLib._QRRSBlock.getRSBlocks = function(typeNumber, errorCorrectLevel) {
                var rsBlock = QRCodeLib._QRRSBlock.getRsBlockTable(typeNumber, errorCorrectLevel);
                if (rsBlock == undefined) {
                    throw new Error("bad rs block @ typeNumber:" + typeNumber + "/errorCorrectLevel:" + errorCorrectLevel);
                }
                var length = rsBlock.length / 3;
                var list = [];
                for (var i = 0; i < length; i++) {
                    var count = rsBlock[i * 3 + 0];
                    var totalCount = rsBlock[i * 3 + 1];
                    var dataCount = rsBlock[i * 3 + 2];
                    for (var j = 0; j < count; j++) {
                        list.push(new QRCodeLib._QRRSBlock(totalCount, dataCount));
                    }
                }
                return list;
            };
            QRCodeLib._QRRSBlock.getRsBlockTable = function(typeNumber, errorCorrectLevel) {
                switch (errorCorrectLevel) {
                    case QRCode.CorrectLevel.L:
                        return QRCodeLib._QRRSBlock.RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 0];
                    case QRCode.CorrectLevel.M:
                        return QRCodeLib._QRRSBlock.RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 1];
                    case QRCode.CorrectLevel.Q:
                        return QRCodeLib._QRRSBlock.RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 2];
                    case QRCode.CorrectLevel.H:
                        return QRCodeLib._QRRSBlock.RS_BLOCK_TABLE[(typeNumber - 1) * 4 + 3];
                    default:
                        return undefined;
                }
            };
            QRCodeLib._QRBitBuffer = function() {
                this.buffer = [];
                this.length = 0;
            };
            QRCodeLib._QRBitBuffer.prototype = {
                get: function(index) {
                    var bufIndex = Math.floor(index / 8);
                    return ((this.buffer[bufIndex] >>> (7 - index % 8)) & 1) == 1;
                },
                put: function(num, length) {
                    for (var i = 0; i < length; i++) {
                        this.putBit(((num >>> (length - i - 1)) & 1) == 1);
                    }
                },
                getLengthInBits: function() {
                    return this.length;
                },
                putBit: function(bit) {
                    var bufIndex = Math.floor(this.length / 8);
                    if (this.buffer.length <= bufIndex) {
                        this.buffer.push(0);
                    }
                    if (bit) {
                        this.buffer[bufIndex] |= (0x80 >>> (this.length % 8));
                    }
                    this.length++;
                }
            };
            QRCodeLib._QRPolynomial = function(num, shift) {
                if (num.length == undefined) {
                    throw new Error(num.length + "/" + shift);
                }
                var offset = 0;
                while (offset < num.length && num[offset] == 0) {
                    offset++;
                }
                this.num = new Array(num.length - offset + shift);
                for (var i = 0; i < num.length - offset; i++) {
                    this.num[i] = num[i + offset];
                }
            };
            QRCodeLib._QRPolynomial.prototype = {
                get: function(index) {
                    return this.num[index];
                },
                getLength: function() {
                    return this.num.length;
                },
                multiply: function(e) {
                    var num = new Array(this.getLength() + e.getLength() - 1);
                    for (var i = 0; i < this.getLength(); i++) {
                        for (var j = 0; j < e.getLength(); j++) {
                            num[i + j] ^= QRCodeLib._QRMath.gexp(QRCodeLib._QRMath.glog(this.get(i)) + QRCodeLib._QRMath.glog(e.get(j)));
                        }
                    }
                    return new QRCodeLib._QRPolynomial(num, 0);
                },
                mod: function(e) {
                    if (this.getLength() - e.getLength() < 0) {
                        return this;
                    }
                    var ratio = QRCodeLib._QRMath.glog(this.get(0)) - QRCodeLib._QRMath.glog(e.get(0));
                    var num = new Array(this.getLength());
                    for (var i = 0; i < this.getLength(); i++) {
                        num[i] = this.get(i);
                    }
                    for (var i = 0; i < e.getLength(); i++) {
                        num[i] ^= QRCodeLib._QRMath.gexp(QRCodeLib._QRMath.glog(e.get(i)) + ratio);
                    }
                    return (new QRCodeLib._QRPolynomial(num, 0)).mod(e);
                }
            };
            QRCodeLib._QRPolynomial.getErrorCorrectPolynomial = function(errorCorrectLength) {
                var a = new QRCodeLib._QRPolynomial([1], 0);
                for (var i = 0; i < errorCorrectLength; i++) {
                    a = a.multiply(new QRCodeLib._QRPolynomial([1, QRCodeLib._QRMath.gexp(i)], 0));
                }
                return a;
            };
            QRCodeLib._QRMath = {
                glog: function(n) {
                    if (n < 1) {
                        throw new Error("glog(" + n + ")");
                    }
                    return QRCodeLib._QRMath.LOG_TABLE[n];
                },
                gexp: function(n) {
                    while (n < 0) {
                        n += 255;
                    }
                    while (n >= 256) {
                        n -= 255;
                    }
                    return QRCodeLib._QRMath.EXP_TABLE[n];
                },
                EXP_TABLE: new Array(256),
                LOG_TABLE: new Array(256)
            };
            for (var i = 0; i < 8; i++) {
                QRCodeLib._QRMath.EXP_TABLE[i] = 1 << i;
            }
            for (var i = 8; i < 256; i++) {
                QRCodeLib._QRMath.EXP_TABLE[i] = QRCodeLib._QRMath.EXP_TABLE[i - 4] ^ QRCodeLib._QRMath.EXP_TABLE[i - 5] ^ QRCodeLib._QRMath.EXP_TABLE[i - 6] ^ QRCodeLib._QRMath.EXP_TABLE[i - 8];
            }
            for (var i = 0; i < 255; i++) {
                QRCodeLib._QRMath.LOG_TABLE[QRCodeLib._QRMath.EXP_TABLE[i]] = i;
            }
            QRCodeLib.Util = {
                getPatternPosition: function(typeNumber) {
                    return QRCodeLib.Util.PATTERN_POSITION_TABLE[(typeNumber - 1)];
                },
                PATTERN_POSITION_TABLE: [
                    [],
                    [6, 18],
                    [6, 22],
                    [6, 26],
                    [6, 30],
                    [6, 34],
                    [6, 22, 38],
                    [6, 24, 42],
                    [6, 26, 46],
                    [6, 28, 50],
                    [6, 30, 54],
                    [6, 32, 58],
                    [6, 34, 62],
                    [6, 26, 46, 66],
                    [6, 26, 48, 70],
                    [6, 26, 50, 74],
                    [6, 30, 54, 78],
                    [6, 30, 56, 82],
                    [6, 30, 58, 86],
                    [6, 34, 62, 90],
                    [6, 28, 50, 72, 94],
                    [6, 26, 50, 74, 98],
                    [6, 30, 54, 78, 102],
                    [6, 28, 54, 80, 106],
                    [6, 32, 58, 84, 110],
                    [6, 30, 58, 86, 114],
                    [6, 34, 62, 90, 118],
                    [6, 26, 50, 74, 98, 122],
                    [6, 30, 54, 78, 102, 126],
                    [6, 26, 52, 78, 104, 130],
                    [6, 30, 56, 82, 108, 134],
                    [6, 34, 60, 86, 112, 138],
                    [6, 30, 58, 86, 114, 142],
                    [6, 34, 62, 90, 118, 146],
                    [6, 30, 54, 78, 102, 126, 150],
                    [6, 24, 50, 76, 102, 128, 154],
                    [6, 28, 54, 80, 106, 132, 158],
                    [6, 32, 58, 84, 110, 136, 162],
                    [6, 26, 54, 82, 110, 138, 166],
                    [6, 30, 58, 86, 114, 142, 170]
                ],
                getBCHTypeInfo: function(data) {
                    var d = data << 10;
                    while (QRCodeLib.Util.getBCHDigit(d) - QRCodeLib.Util.getBCHDigit(0x537) >= 0) {
                        d ^= (0x537 << (QRCodeLib.Util.getBCHDigit(d) - QRCodeLib.Util.getBCHDigit(0x537)));
                    }
                    return ((data << 10) | d) ^ 0x5412;
                },
                getBCHTypeNumber: function(data) {
                    var d = data << 12;
                    while (QRCodeLib.Util.getBCHDigit(d) - QRCodeLib.Util.getBCHDigit(0x1f25) >= 0) {
                        d ^= (0x1f25 << (QRCodeLib.Util.getBCHDigit(d) - QRCodeLib.Util.getBCHDigit(0x1f25)));
                    }
                    return (data << 12) | d;
                },
                getBCHDigit: function(data) {
                    var digit = 0;
                    while (data != 0) {
                        digit++;
                        data >>>= 1;
                    }
                    return digit;
                },
                getLengthInBits: function(mode, type) {
                    if (1 <= type && type < 10) {
                        switch (mode) {
                            case QRCodeLib.Mode.MODE_NUMBER:
                                return 10;
                            case QRCodeLib.Mode.MODE_ALPHA_NUM:
                                return 9;
                            case QRCodeLib.Mode.MODE_8BIT_BYTE:
                                return 8;
                            case QRCodeLib.Mode.MODE_KANJI:
                                return 8;
                            default:
                                throw new Error("mode:" + mode);
                        }
                    } else if (type < 27) {
                        switch (mode) {
                            case QRCodeLib.Mode.MODE_NUMBER:
                                return 12;
                            case QRCodeLib.Mode.MODE_ALPHA_NUM:
                                return 11;
                            case QRCodeLib.Mode.MODE_8BIT_BYTE:
                                return 16;
                            case QRCodeLib.Mode.MODE_KANJI:
                                return 10;
                            default:
                                throw new Error("mode:" + mode);
                        }
                    } else if (type < 41) {
                        switch (mode) {
                            case QRCodeLib.Mode.MODE_NUMBER:
                                return 14;
                            case QRCodeLib.Mode.MODE_ALPHA_NUM:
                                return 13;
                            case QRCodeLib.Mode.MODE_8BIT_BYTE:
                                return 16;
                            case QRCodeLib.Mode.MODE_KANJI:
                                return 12;
                            default:
                                throw new Error("mode:" + mode);
                        }
                    } else {
                        throw new Error("type:" + type);
                    }
                },
                getMask: function(maskPattern, i, j) {
                    switch (maskPattern) {
                        case 0:
                            return (i + j) % 2 == 0;
                        case 1:
                            return i % 2 == 0;
                        case 2:
                            return j % 3 == 0;
                        case 3:
                            return (i + j) % 3 == 0;
                        case 4:
                            return (Math.floor(i / 2) + Math.floor(j / 3)) % 2 == 0;
                        case 5:
                            return (i * j) % 2 + (i * j) % 3 == 0;
                        case 6:
                            return ((i * j) % 2 + (i * j) % 3) % 2 == 0;
                        case 7:
                            return ((i * j) % 3 + (i + j) % 2) % 2 == 0;
                        default:
                            throw new Error("bad maskPattern:" + maskPattern);
                    }
                },
                getLostPoint: function(qrCode) {
                    var moduleCount = qrCode.getModuleCount();
                    var lostPoint = 0;
                    for (var row = 0; row < moduleCount; row++) {
                        for (var col = 0; col < moduleCount; col++) {
                            var sameCount = 0;
                            var dark = qrCode.isDark(row, col);
                            for (var r = -1; r <= 1; r++) {
                                if (row + r < 0 || moduleCount <= row + r) {
                                    continue;
                                }
                                for (var c = -1; c <= 1; c++) {
                                    if (col + c < 0 || moduleCount <= col + c) {
                                        continue;
                                    }
                                    if (r == 0 && c == 0) {
                                        continue;
                                    }
                                    if (dark == qrCode.isDark(row + r, col + c)) {
                                        sameCount++;
                                    }
                                }
                            }
                            if (sameCount > 5) {
                                lostPoint += (3 + sameCount - 5);
                            }
                        }
                    }
                    for (var row = 0; row < moduleCount - 1; row++) {
                        for (var col = 0; col < moduleCount - 1; col++) {
                            var count = 0;
                            if (qrCode.isDark(row, col)) count++;
                            if (qrCode.isDark(row + 1, col)) count++;
                            if (qrCode.isDark(row, col + 1)) count++;
                            if (qrCode.isDark(row + 1, col + 1)) count++;
                            if (count == 0 || count == 4) {
                                lostPoint += 3;
                            }
                        }
                    }
                    for (var row = 0; row < moduleCount; row++) {
                        for (var col = 0; col < moduleCount - 6; col++) {
                            if (qrCode.isDark(row, col) && !qrCode.isDark(row, col + 1) && qrCode.isDark(row, col + 2) && qrCode.isDark(row, col + 3) && qrCode.isDark(row, col + 4) && !qrCode.isDark(row, col + 5) && qrCode.isDark(row, col + 6)) {
                                lostPoint += 40;
                            }
                        }
                    }
                    for (var col = 0; col < moduleCount; col++) {
                        for (var row = 0; row < moduleCount - 6; row++) {
                            if (qrCode.isDark(row, col) && !qrCode.isDark(row + 1, col) && qrCode.isDark(row + 2, col) && qrCode.isDark(row + 3, col) && qrCode.isDark(row + 4, col) && !qrCode.isDark(row + 5, col) && qrCode.isDark(row + 6, col)) {
                                lostPoint += 40;
                            }
                        }
                    }
                    var darkCount = 0;
                    for (var col = 0; col < moduleCount; col++) {
                        for (var row = 0; row < moduleCount; row++) {
                            if (qrCode.isDark(row, col)) {
                                darkCount++;
                            }
                        }
                    }
                    var ratio = Math.abs(100 * darkCount / moduleCount / moduleCount - 50) / 5;
                    lostPoint += ratio * 10;
                    return lostPoint;
                }
            };
            window.QRCodeLib = QRCodeLib;
        })();
        
        // Wrapper function to generate QR code
        function generateQRCode(text, containerId, size) {
            const container = document.getElementById(containerId);
            if (!container) return;
            
            size = size || 256;
            container.innerHTML = '';
            
            // Create a temporary div for QRCode
            const tempDiv = document.createElement('div');
            tempDiv.style.display = 'none';
            container.appendChild(tempDiv);
            
            // Generate QR code using the library
            try {
                const qrcode = new QRCode(tempDiv, {
                    text: text,
                    width: size,
                    height: size,
                    colorDark: "#000000",
                    colorLight: "#ffffff",
                    correctLevel: QRCode.CorrectLevel.M
                });
                
                // Move the canvas to the container
                const canvas = tempDiv.querySelector('canvas');
                if (canvas) {
                    container.innerHTML = '';
                    canvas.style.display = 'block';
                    canvas.style.margin = '0 auto';
                    container.appendChild(canvas);
                }
            } catch (e) {
                container.innerHTML = '<p style="color: var(--red-alert);">Erreur lors de la génération du QR code</p>';
                console.error('QR Code generation error:', e);
            }
        }
        
        function closeQRCodeModal() {
            document.getElementById('qrcode-modal').style.display = 'none';
        }
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('qrcode-modal');
            if (event.target === modal) {
                closeQRCodeModal();
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
            <div style="margin-bottom: 16px; padding: 12px; background: rgba(59, 130, 246, 0.1); border-radius: 8px; border-left: 4px solid var(--primary);">
                <p style="margin: 0; color: var(--text-primary); font-size: 14px; font-weight: 500;">
                    📏 Maximum file size: <span id="max-size-display" style="color: var(--primary); font-weight: 600;">Loading...</span>
                </p>
            </div>
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
    
    <!-- QR Code Modal -->
    <div id="qrcode-modal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeQRCodeModal()">&times;</span>
            <h3>📱 QR Code</h3>
            <div class="qrcode-container" id="qrcode-container"></div>
            <p style="color: var(--text-secondary); margin-top: 16px; font-size: 14px;">
                Scan with your device to copy the text content
            </p>
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
            
            // Get max size from stats (or use default 1GB)
            const maxSizeBytes = window.maxFileSizeBytes || (1024 * 1024 * 1024);
            if (totalSize > maxSizeBytes) {
                const maxSizeMB = Math.round(maxSizeBytes / (1024 * 1024));
                const maxSizeDisplay = maxSizeMB >= 1024 
                    ? (maxSizeMB / 1024).toFixed(1) + ' GB' 
                    : maxSizeMB + ' MB';
                showAlert(`Total file size exceeds ${maxSizeDisplay} limit`, 'error');
                return;
            }
            
            // Check individual file sizes
            for (let file of fileList) {
                if (file.size > maxSizeBytes) {
                    const maxSizeMB = Math.round(maxSizeBytes / (1024 * 1024));
                    const maxSizeDisplay = maxSizeMB >= 1024 
                        ? (maxSizeMB / 1024).toFixed(1) + ' GB' 
                        : maxSizeMB + ' MB';
                    showAlert(`File "${file.name}" exceeds ${maxSizeDisplay} limit`, 'error');
                    return;
                }
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
                
                // Display max file size limit and store for validation
                if (stats.max_size_mb) {
                    const maxSizeMB = Math.round(stats.max_size_mb);
                    const maxSizeBytes = maxSizeMB * 1024 * 1024;
                    window.maxFileSizeBytes = maxSizeBytes; // Store for upload validation
                    
                    const maxSizeDisplay = maxSizeMB >= 1024 
                        ? (maxSizeMB / 1024).toFixed(1) + ' GB' 
                        : maxSizeMB + ' MB';
                    document.getElementById('max-size-display').textContent = maxSizeDisplay;
                }
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
            
            // Get current URL for download links
            const currentUrl = window.location.origin;
            const protocol = window.location.protocol;
            const host = window.location.host;
            const baseUrl = protocol + '//' + host;
            
            fileList.innerHTML = files.map(file => {
                const displayName = file.display_name || file.name;
                const downloadUrl = baseUrl + '/download/' + encodeURIComponent(file.name);
                const fileId = escapeHtml(file.name).replace(/[^a-zA-Z0-9]/g, '_');
                
                return `
                <div class="file-item">
                    <div class="file-info">
                        <div class="file-name">${escapeHtml(displayName)}</div>
                        <div class="file-meta">
                            ${formatSize(file.size_mb)} MB • ${formatDate(file.uploaded_at)} • ${file.type === 'text' ? '📝 Text' : '📁 File'}
                        </div>
                        <div class="file-expiry" style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                            Auto-delete: ${formatDate(file.expires_at)}
                        </div>
                    </div>
                    <div class="file-actions">
                        ${file.type === 'text' ? `
                            <button class="btn btn-secondary copy-btn" id="copy-btn-${fileId}" onclick="copyText('${escapeHtml(file.name)}', this)">
                                📋 Copy
                            </button>
                            <button class="btn btn-secondary" onclick="showQRCode('${escapeHtml(file.name)}')">
                                📱 QR Code
                            </button>
                        ` : ''}
                        <button class="btn btn-secondary" id="copy-url-btn-${fileId}" data-url="${downloadUrl.replace(/"/g, '&quot;')}" onclick="copyDownloadUrl('${fileId}', this)">
                            🔗 Copy URL
                        </button>
                        <a href="/download/${encodeURIComponent(file.name)}" class="btn btn-secondary" download>
                            Download
                        </a>
                        <button class="btn btn-danger" onclick="deleteFile('${file.name.replace(/'/g, "\\'")}')">
                            Delete
                        </button>
                    </div>
                </div>
            `;
            }).join('');
        }
        
        async function copyDownloadUrl(fileId, buttonElement) {
            const originalText = buttonElement.innerHTML;
            const originalClass = buttonElement.className;
            
            // Get URL from data attribute
            let url = buttonElement.getAttribute('data-url');
            if (!url) {
                // Fallback: construct URL from current location
                const protocol = window.location.protocol;
                const host = window.location.host;
                const fileName = buttonElement.getAttribute('data-filename') || '';
                url = protocol + '//' + host + '/download/' + encodeURIComponent(fileName);
            }
            
            if (!url) {
                showAlert('Error: Could not get download URL', 'error');
                return;
            }
            
            try {
                // Try modern clipboard API first
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(url);
                    // Success feedback with icon and visual change
                    buttonElement.innerHTML = '✅ Copied!';
                    buttonElement.className = originalClass.replace('btn-secondary', 'btn-primary');
                    buttonElement.style.background = 'linear-gradient(135deg, #22C55E, #16A34A)';
                    buttonElement.style.color = '#FFFFFF';
                    buttonElement.style.borderColor = '#16A34A';
                    buttonElement.style.transform = 'scale(1.05)';
                    buttonElement.style.transition = 'all 0.3s ease';
                    showAlert('Download URL copied to clipboard! You can now use it with wget or curl.', 'success');
                    
                    setTimeout(() => {
                        buttonElement.innerHTML = originalText;
                        buttonElement.className = originalClass;
                        buttonElement.style.background = '';
                        buttonElement.style.color = '';
                        buttonElement.style.borderColor = '';
                        buttonElement.style.transform = '';
                    }, 3000);
                    return;
                }
                
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = url;
                textArea.style.position = 'fixed';
                textArea.style.left = '-9999px';
                textArea.style.top = '0';
                textArea.style.opacity = '0';
                textArea.style.pointerEvents = 'none';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                
                try {
                    const successful = document.execCommand('copy');
                    document.body.removeChild(textArea);
                    
                    if (successful) {
                        // Success feedback with icon and visual change
                        buttonElement.innerHTML = '✅ Copied!';
                        buttonElement.className = originalClass.replace('btn-secondary', 'btn-primary');
                        buttonElement.style.background = 'linear-gradient(135deg, #22C55E, #16A34A)';
                        buttonElement.style.color = '#FFFFFF';
                        buttonElement.style.borderColor = '#16A34A';
                        buttonElement.style.transform = 'scale(1.05)';
                        buttonElement.style.transition = 'all 0.3s ease';
                        showAlert('Download URL copied to clipboard! You can now use it with wget or curl.', 'success');
                        
                        setTimeout(() => {
                            buttonElement.innerHTML = originalText;
                            buttonElement.className = originalClass;
                            buttonElement.style.background = '';
                            buttonElement.style.color = '';
                            buttonElement.style.borderColor = '';
                            buttonElement.style.transform = '';
                        }, 3000);
                    } else {
                        buttonElement.innerHTML = '❌ Failed';
                        buttonElement.style.background = 'rgba(220, 38, 38, 0.2)';
                        showAlert('Failed to copy URL. Please try again.', 'error');
                        setTimeout(() => {
                            buttonElement.innerHTML = originalText;
                            buttonElement.style.background = '';
                        }, 2000);
                    }
                } catch (execError) {
                    document.body.removeChild(textArea);
                    buttonElement.innerHTML = '❌ Error';
                    buttonElement.style.background = 'rgba(220, 38, 38, 0.2)';
                    showAlert('Error copying URL: ' + execError.message, 'error');
                    setTimeout(() => {
                        buttonElement.innerHTML = originalText;
                        buttonElement.style.background = '';
                    }, 2000);
                }
            } catch (error) {
                buttonElement.innerHTML = '❌ Error';
                buttonElement.style.background = 'rgba(220, 38, 38, 0.2)';
                showAlert('Error copying URL: ' + error.message, 'error');
                setTimeout(() => {
                    buttonElement.innerHTML = originalText;
                    buttonElement.style.background = '';
                }, 2000);
            }
        }
        
        async function showQRCode(filename) {
            try {
                const response = await fetch('/api/text/' + encodeURIComponent(filename));
                const result = await response.json();
                
                if (!response.ok || !result.content) {
                    showAlert('Failed to load text content for QR code', 'error');
                    return;
                }
                
                // Show modal
                const modal = document.getElementById('qrcode-modal');
                modal.style.display = 'block';
                
                // Generate QR code with the text content
                generateQRCode(result.content, 'qrcode-container', 256);
            } catch (error) {
                showAlert('Error loading QR code: ' + error.message, 'error');
            }
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
            
            // Ensure filename is properly encoded
            const encodedFilename = encodeURIComponent(filename);
            console.log('[DELETE] Attempting to delete:', filename, 'encoded:', encodedFilename);
            
            try {
                const response = await fetch('/api/delete/' + encodedFilename, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    showAlert('File deleted successfully', 'success');
                    // Refresh file list and stats
                    await loadFiles();
                    await loadStats();
                } else {
                    console.error('[DELETE] Failed:', result);
                    showAlert('Delete failed: ' + (result.error || 'Unknown error'), 'error');
                }
            } catch (error) {
                console.error('[DELETE] Error:', error);
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
    parser.add_argument('--ssl-cert', type=str, default=DEFAULT_SSL_CERT,
                       help='Path to SSL certificate file (enables HTTPS)')
    parser.add_argument('--ssl-key', type=str, default=DEFAULT_SSL_KEY,
                       help='Path to SSL private key file (required if --ssl-cert is set)')
    
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
    
    # Enable HTTPS if certificate and key are provided
    use_https = False
    if args.ssl_cert and args.ssl_key:
        if not os.path.exists(args.ssl_cert):
            print(f"Error: SSL certificate file not found: {args.ssl_cert}")
            return
        if not os.path.exists(args.ssl_key):
            print(f"Error: SSL key file not found: {args.ssl_key}")
            return
        try:
            # Use SSLContext for Python 3.7+ compatibility
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.ssl_cert, args.ssl_key)
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
            use_https = True
        except Exception as e:
            print(f"Error setting up SSL: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # Get network info
    local_ip = get_local_ip()
    protocol = 'https' if use_https else 'http'
    
    print("=" * 60)
    print("Odysafe QuickShare")
    print("=" * 60)
    print(f"Storage directory: {server_instance.storage_dir.absolute()}")
    print(f"Cleanup interval: {args.cleanup_hours} hours")
    print(f"Max file size: {args.max_size} MB")
    print(f"Protocol: {protocol.upper()}")
    print("=" * 60)
    print(f"Server running on:")
    print(f"  Local:   {protocol}://127.0.0.1:{args.port}")
    print(f"  Network: {protocol}://{local_ip}:{args.port}")
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

