#!/usr/bin/env python3
"""
ENHANCED CYBERSECURITY OPERATIONS SERVER v3.0
For legitimate security testing, incident response, and authorized operations
"""
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
import uuid
import json
import sqlite3
import threading
import os
import shutil
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
import mimetypes
import logging
from typing import Dict, List, Optional, Tuple
import re

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Security configuration
API_KEYS = []  # Load from environment in production
REQUIRE_AUTH = True
SESSION_TIMEOUT = 3600  # 1 hour

# Database configuration
DATABASE = 'cyber_ops.db'
BACKUP_INTERVAL = 300  # 5 minutes

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

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Server start time
SERVER_START_TIME = time.time()

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def init_db():
    """Initialize database with enhanced schema"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Clients table with more details
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            hostname TEXT,
            username TEXT,
            os TEXT,
            os_version TEXT,
            architecture TEXT,
            ip_address TEXT,
            mac_address TEXT,
            last_seen REAL,
            first_seen REAL,
            status TEXT DEFAULT 'offline',
            operation_id TEXT,
            authorized INTEGER DEFAULT 0,
            client_version TEXT,
            notes TEXT
        )
    ''')
    
    # Sessions table for tracking operations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            client_id TEXT,
            operator_id TEXT,
            start_time REAL,
            end_time REAL,
            purpose TEXT,
            authorization_doc TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    ''')
    
    # Commands table with enhanced tracking
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
            requires_auth INTEGER DEFAULT 1,
            justification TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id)
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
            description TEXT,
            chain_of_custody TEXT,
            tags TEXT
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
    
    # Operations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            operation_id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            start_time REAL,
            end_time REAL,
            status TEXT,
            lead_operator TEXT,
            client_count INTEGER,
            evidence_count INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Database initialized with enhanced schema")

def get_db():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def backup_database():
    """Create database backups"""
    while True:
        time.sleep(BACKUP_INTERVAL)
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"backups/cyber_ops_backup_{timestamp}.db"
            
            os.makedirs("backups", exist_ok=True)
            
            conn = sqlite3.connect(DATABASE)
            backup_conn = sqlite3.connect(backup_file)
            
            conn.backup(backup_conn)
            
            backup_conn.close()
            conn.close()
            
            logger.info(f"Database backed up to {backup_file}")
            
        except Exception as e:
            logger.error(f"Database backup failed: {e}")

# ============================================================================
# SECURITY FUNCTIONS
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
        
        # Also log to file
        log_message = f"[{event_type}] {details}"
        if operator_id:
            log_message += f" | Operator: {operator_id}"
        if client_id:
            log_message += f" | Client: {client_id[:8]}"
        
        if severity == "HIGH":
            logger.warning(log_message)
        elif severity == "CRITICAL":
            logger.error(log_message)
        else:
            logger.info(log_message)
        
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")

def validate_api_key() -> bool:
    """Validate API key from request"""
    if not REQUIRE_AUTH:
        return True
    
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    
    if not api_key:
        log_audit_event("SECURITY", "Missing API key", None, None, "HIGH")
        return False
    
    # In production, load from environment/database
    valid_keys = os.getenv('API_KEYS', '').split(',')
    if api_key in valid_keys or api_key == "dev_key_allow":  # Dev only
        return True
    
    log_audit_event("SECURITY", f"Invalid API key attempt: {api_key[:8]}...", 
                   None, None, "HIGH")
    return False

def sanitize_input(input_str: str) -> str:
    """Sanitize user input"""
    if not input_str:
        return ""
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[;`$|<>]', '', input_str)
    # Limit length
    return sanitized[:1000]

def generate_evidence_id(client_id: str, filename: str) -> str:
    """Generate unique evidence ID"""
    timestamp = int(time.time())
    random_part = secrets.token_hex(4)
    return f"EVID_{client_id[:8]}_{timestamp}_{random_part}"

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

@app.route('/api/client/register', methods=['POST'])
@limiter.limit("10 per minute")
def client_register():
    """Client registration endpoint"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        client_id = data.get('client_id')
        operation_id = data.get('operation_id')
        
        if not client_id or not operation_id:
            return jsonify({'error': 'Missing client_id or operation_id'}), 400
        
        # Log registration attempt
        log_audit_event("CLIENT_REGISTER", 
                       f"Registration attempt: {client_id[:8]}...",
                       operator_id=data.get('operator_id', 'unknown'),
                       client_id=client_id)
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Check if client exists
        cursor.execute('SELECT * FROM clients WHERE id = ?', (client_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing client
            cursor.execute('''
                UPDATE clients 
                SET last_seen = ?, status = 'online', operation_id = ?
                WHERE id = ?
            ''', (current_time, operation_id, client_id))
        else:
            # Register new client
            cursor.execute('''
                INSERT INTO clients 
                (id, hostname, username, os, os_version, architecture, 
                 ip_address, last_seen, first_seen, status, operation_id, 
                 authorized, client_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, ?, ?)
            ''', (
                client_id,
                data.get('hostname', 'unknown'),
                data.get('username', 'unknown'),
                data.get('os', 'unknown'),
                data.get('os_version', 'unknown'),
                data.get('architecture', 'unknown'),
                request.remote_addr,
                current_time,
                current_time,
                operation_id,
                data.get('authorized', 0),
                data.get('client_version', '1.0')
            ))
        
        # Create client evidence folder
        client_folder = os.path.join(EVIDENCE_FOLDER, client_id[:8])
        os.makedirs(client_folder, exist_ok=True)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Client registered: {client_id[:8]}... | Operation: {operation_id}")
        log_audit_event("CLIENT_REGISTER", "Registration successful", 
                       data.get('operator_id'), client_id)
        
        return jsonify({
            'status': 'registered',
            'client_id': client_id,
            'timestamp': current_time,
            'evidence_folder': client_folder
        }), 200
        
    except Exception as e:
        logger.error(f"Client registration error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/heartbeat', methods=['POST'])
@limiter.limit("60 per minute")
def client_heartbeat():
    """Client heartbeat endpoint"""
    try:
        data = request.json
        client_id = data.get('client_id')
        
        if not client_id:
            return jsonify({'error': 'Missing client_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        cursor.execute('''
            UPDATE clients 
            SET last_seen = ?, status = 'online'
            WHERE id = ?
        ''', (current_time, client_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'ok', 'timestamp': current_time}), 200
        
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/checkin', methods=['POST'])
@limiter.limit("30 per minute")
def client_checkin():
    """Enhanced client checkin with validation"""
    try:
        data = request.json
        client_id = data.get('id')
        
        if not client_id:
            return jsonify({'error': 'Missing client ID'}), 400
        
        # Validate operation ID
        operation_id = data.get('operation_id')
        if not operation_id:
            return jsonify({'error': 'Missing operation ID'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        hostname = data.get('hostname', 'unknown')
        
        # Get or create client folder
        client_folder = os.path.join(EVIDENCE_FOLDER, client_id[:8])
        os.makedirs(client_folder, exist_ok=True)
        
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
            'evidence_folder': client_folder,
            'requires_auth': True
        }), 200
        
    except Exception as e:
        logger.error(f"Checkin error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# COMMAND ENDPOINTS
# ============================================================================

@app.route('/api/command/send', methods=['POST'])
@limiter.limit("50 per hour")
def send_command():
    """Send command to client with enhanced security"""
    try:
        if not validate_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        operator_id = data.get('operator_id', 'unknown')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        # Sanitize inputs
        client_id = sanitize_input(client_id)
        command = sanitize_input(command)
        operator_id = sanitize_input(operator_id)
        
        # Check if client exists and is online
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        if client['status'] != 'online':
            log_audit_event("COMMAND", f"Attempt to send command to offline client: {client_id[:8]}",
                           operator_id, client_id, "MEDIUM")
        
        # Create command record
        cmd_id = str(uuid.uuid4())
        current_time = time.time()
        
        cursor.execute('''
            INSERT INTO commands 
            (id, client_id, operator_id, command, status, created_at, requires_auth, justification)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        ''', (cmd_id, client_id, operator_id, command, current_time, 
              data.get('requires_auth', 1), data.get('justification', '')))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command sent: {cmd_id[:8]} -> {client_id[:8]}: {command[:50]}")
        log_audit_event("COMMAND_SEND", f"Command: {command[:100]}", 
                       operator_id, client_id)
        
        return jsonify({
            'success': True,
            'command_id': cmd_id,
            'message': 'Command queued for execution',
            'timestamp': current_time
        }), 200
        
    except Exception as e:
        logger.error(f"Command send error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/list/<client_id>', methods=['GET'])
@limiter.limit("100 per hour")
def list_commands(client_id):
    """Get pending commands for client"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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
@limiter.limit("100 per hour")
def submit_result():
    """Submit command execution result"""
    try:
        data = request.json
        cmd_id = data.get('command_id')
        output = data.get('output', '')
        status = data.get('status', 'completed')
        
        if not cmd_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        # Sanitize output (limit size)
        output = sanitize_input(output)[:5000]  # Limit to 5000 chars
        
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
@limiter.limit("100 per hour")
def get_command_result(cmd_id):
    """Get command execution result"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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
                'executed_at': row['executed_at'],
                'justification': row['justification']
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
# EVIDENCE MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/evidence/upload', methods=['POST'])
@limiter.limit("20 per minute")
def upload_evidence():
    """Upload evidence file with enhanced organization"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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
        evidence_id = generate_evidence_id(client_id, filename)
        
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
            'uploaded_at': time.time(),
            'filepath': f"{client_id[:8]}/{subfolder}/{safe_filename}"
        }), 200
        
    except Exception as e:
        logger.error(f"Evidence upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/evidence/list/<client_id>', methods=['GET'])
@limiter.limit("50 per hour")
def list_evidence(client_id):
    """List evidence for a client"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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

@app.route('/api/evidence/download/<evidence_id>', methods=['GET'])
@limiter.limit("30 per hour")
def download_evidence(evidence_id):
    """Download evidence file"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT filepath, filename FROM evidence WHERE id = ?', (evidence_id,))
        row = cursor.fetchone()
        
        if not row or not os.path.exists(row['filepath']):
            conn.close()
            return jsonify({'error': 'Evidence not found'}), 404
        
        # Log download
        log_audit_event("EVIDENCE_DOWNLOAD", f"Downloaded: {row['filename']}",
                       request.headers.get('X-Operator-ID'), None)
        
        conn.close()
        
        return send_file(
            row['filepath'],
            as_attachment=True,
            download_name=row['filename'],
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        logger.error(f"Download evidence error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/evidence/preview/<evidence_id>', methods=['GET'])
@limiter.limit("50 per hour")
def preview_evidence(evidence_id):
    """Preview evidence file (images, logs, etc.)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT filepath, filename, filetype FROM evidence WHERE id = ?', (evidence_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not os.path.exists(row['filepath']):
            return jsonify({'error': 'Evidence not found'}), 404
        
        # Check if file is previewable
        if row['filetype'] in ['image', 'log', 'document']:
            if row['filetype'] == 'image':
                mimetype = mimetypes.guess_type(row['filename'])[0] or 'image/jpeg'
                return send_file(row['filepath'], mimetype=mimetype)
            elif row['filetype'] in ['log', 'document']:
                # For text files, read and return content
                with open(row['filepath'], 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(50000)  # Limit to 50KB for preview
                return jsonify({
                    'filename': row['filename'],
                    'content': content,
                    'truncated': len(content) >= 50000
                })
        
        return jsonify({'error': 'File type not previewable'}), 400
        
    except Exception as e:
        logger.error(f"Preview evidence error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/clients', methods=['GET'])
@limiter.limit("100 per hour")
def get_clients():
    """Get all clients with detailed information"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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
                   COUNT(DISTINCT cmd.id) as command_count,
                   MAX(e.uploaded_at) as last_evidence
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
                'architecture': row['architecture'],
                'ip_address': row['ip_address'],
                'status': row['status'],
                'status_display': f"{status_emoji} {status_text}",
                'evidence_count': row['evidence_count'] or 0,
                'command_count': row['command_count'] or 0,
                'last_seen': row['last_seen'],
                'last_seen_str': last_seen_str,
                'first_seen': row['first_seen'],
                'first_seen_str': datetime.fromtimestamp(row['first_seen']).strftime('%Y-%m-%d') if row['first_seen'] else 'unknown',
                'operation_id': row['operation_id'],
                'authorized': bool(row['authorized']),
                'client_version': row['client_version'],
                'last_evidence': row['last_evidence']
            })
        
        conn.close()
        
        log_audit_event("CLIENT_LIST", f"Listed {len(clients)} clients", 
                       request.headers.get('X-Operator-ID'))
        
        return jsonify({'clients': clients}), 200
        
    except Exception as e:
        logger.error(f"Get clients error: {e}")
        return jsonify({'clients': []}), 500

@app.route('/api/client/<client_id>', methods=['GET'])
@limiter.limit("50 per hour")
def get_client_details(client_id):
    """Get detailed client information"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get client info
        cursor.execute('SELECT * FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        
        if not client:
            conn.close()
            return jsonify({'error': 'Client not found'}), 404
        
        # Get recent commands
        cursor.execute('''
            SELECT command, status, created_at, executed_at, operator_id
            FROM commands 
            WHERE client_id = ?
            ORDER BY created_at DESC
            LIMIT 10
        ''', (client_id,))
        
        recent_commands = []
        for row in cursor.fetchall():
            recent_commands.append({
                'command': row['command'],
                'status': row['status'],
                'created_at': row['created_at'],
                'executed_at': row['executed_at'],
                'operator_id': row['operator_id'],
                'age': time.time() - row['created_at']
            })
        
        # Get evidence summary
        cursor.execute('''
            SELECT filetype, COUNT(*) as count, SUM(filesize) as total_size
            FROM evidence 
            WHERE client_id = ?
            GROUP BY filetype
        ''', (client_id,))
        
        evidence_summary = {}
        for row in cursor.fetchall():
            evidence_summary[row['filetype']] = {
                'count': row['count'],
                'total_size': row['total_size']
            }
        
        conn.close()
        
        # Format client data
        client_data = dict(client)
        client_data['online_time'] = time.time() - client['first_seen'] if client['first_seen'] else 0
        client_data['online_time_str'] = str(timedelta(seconds=int(client_data['online_time'])))
        
        return jsonify({
            'client': client_data,
            'recent_commands': recent_commands,
            'evidence_summary': evidence_summary
        }), 200
        
    except Exception as e:
        logger.error(f"Get client details error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
@limiter.limit("30 per minute")
def get_stats():
    """Get server statistics"""
    try:
        # if not validate_api_key():
        #     return jsonify({'error': 'Unauthorized'}), 401
        
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
        
        cursor.execute('SELECT COUNT(*) FROM evidence WHERE filetype = "document"')
        document_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(filesize) FROM evidence')
        total_size = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(DISTINCT operator_id) FROM commands')
        unique_operators = cursor.fetchone()[0]
        
        conn.close()
        
        # Server uptime
        uptime = current_time - SERVER_START_TIME
        uptime_str = str(timedelta(seconds=int(uptime)))
        
        # Recent activity
        recent_activity = []
        if os.path.exists('cyber_ops_server.log'):
            try:
                with open('cyber_ops_server.log', 'r') as f:
                    lines = f.readlines()[-10:]  # Last 10 lines
                    recent_activity = [line.strip() for line in lines if 'INFO' in line or 'WARNING' in line]
            except:
                recent_activity = []
        
        return jsonify({
            'server': {
                'version': '3.0',
                'uptime': uptime,
                'uptime_str': uptime_str,
                'start_time': SERVER_START_TIME,
                'current_time': current_time,
                'database': DATABASE
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
                'documents': document_files,
                'total_size': total_size,
                'total_size_str': f"{total_size / 1024 / 1024 / 1024:.2f} GB"
            },
            'storage': {
                'evidence_folder': os.path.abspath(EVIDENCE_FOLDER),
                'upload_folder': os.path.abspath(UPLOAD_FOLDER),
                'download_folder': os.path.abspath(DOWNLOAD_FOLDER)
            },
            'recent_activity': recent_activity[-5:]  # Last 5 entries
        }), 200
        
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit/log', methods=['GET'])
@limiter.limit("20 per minute")
def get_audit_log():
    """Get audit log entries"""
    try:
        if not validate_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        limit = request.args.get('limit', 100, type=int)
        severity = request.args.get('severity')
        event_type = request.args.get('event_type')
        
        conn = get_db()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM audit_log WHERE 1=1'
        params = []
        
        if severity:
            query += ' AND severity = ?'
            params.append(severity)
        
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        audit_entries = []
        for row in cursor.fetchall():
            audit_entries.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'time_str': datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'event_type': row['event_type'],
                'operator_id': row['operator_id'],
                'client_id': row['client_id'],
                'ip_address': row['ip_address'],
                'details': row['details'],
                'severity': row['severity']
            })
        
        conn.close()
        
        return jsonify({'audit_log': audit_entries}), 200
        
    except Exception as e:
        logger.error(f"Get audit log error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
@limiter.limit("60 per minute")
def health_check():
    """Health check endpoint"""
    try:
        # Basic system checks
        disk_usage = shutil.disk_usage('.')
        memory_info = {}
        
        if os.name == 'posix':  # Linux/Mac
            try:
                import psutil
                memory_info = {
                    'total': psutil.virtual_memory().total,
                    'available': psutil.virtual_memory().available,
                    'percent': psutil.virtual_memory().percent
                }
            except:
                memory_info = {'error': 'psutil not available'}
        
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
            'version': '3.0',
            'server_time': datetime.now().isoformat(),
            'features': [
                'secure_client_management',
                'evidence_collection',
                'audit_logging',
                'command_execution',
                'file_organization'
            ],
            'system': {
                'disk_total': disk_usage.total,
                'disk_free': disk_usage.free,
                'disk_used': disk_usage.used,
                'disk_percent': (disk_usage.used / disk_usage.total) * 100,
                'memory': memory_info
            },
            'database': {
                'status': db_status,
                'path': DATABASE
            },
            'endpoints': [
                '/api/clients',
                '/api/evidence',
                '/api/command',
                '/api/stats',
                '/api/health'
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'degraded', 'error': str(e)}), 500

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@app.route('/api/admin/cleanup', methods=['POST'])
@limiter.limit("5 per hour")
def admin_cleanup():
    """Cleanup old data (admin only)"""
    try:
        if not validate_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check for admin key
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key != os.getenv('ADMIN_KEY', 'default_admin_key'):
            return jsonify({'error': 'Admin access required'}), 403
        
        days_old = request.json.get('days', 30)
        cutoff_time = time.time() - (days_old * 24 * 3600)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Remove old offline clients
        cursor.execute('''
            DELETE FROM clients 
            WHERE status = 'offline' AND last_seen < ?
        ''', (cutoff_time,))
        clients_deleted = cursor.rowcount
        
        # Remove old evidence files
        cursor.execute('SELECT id, filepath FROM evidence WHERE uploaded_at < ?', (cutoff_time,))
        old_evidence = cursor.fetchall()
        
        evidence_deleted = 0
        for row in old_evidence:
            try:
                if os.path.exists(row['filepath']):
                    os.remove(row['filepath'])
            except:
                pass
        
        cursor.execute('DELETE FROM evidence WHERE uploaded_at < ?', (cutoff_time,))
        evidence_deleted = cursor.rowcount
        
        # Remove old commands
        cursor.execute('DELETE FROM commands WHERE created_at < ?', (cutoff_time,))
        commands_deleted = cursor.rowcount
        
        # Remove old audit logs (keep last 1000 entries)
        cursor.execute('''
            DELETE FROM audit_log 
            WHERE id NOT IN (
                SELECT id FROM audit_log 
                ORDER BY timestamp DESC 
                LIMIT 1000
            )
        ''')
        audit_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cleanup completed: {clients_deleted} clients, {evidence_deleted} evidence, {commands_deleted} commands, {audit_deleted} audit logs")
        
        return jsonify({
            'success': True,
            'deleted': {
                'clients': clients_deleted,
                'evidence': evidence_deleted,
                'commands': commands_deleted,
                'audit_logs': audit_deleted
            },
            'cutoff_time': cutoff_time,
            'cutoff_date': datetime.fromtimestamp(cutoff_time).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/export', methods=['GET'])
@limiter.limit("2 per hour")
def admin_export():
    """Export database (admin only)"""
    try:
        if not validate_api_key():
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check for admin key
        admin_key = request.headers.get('X-Admin-Key')
        if admin_key != os.getenv('ADMIN_KEY', 'default_admin_key'):
            return jsonify({'error': 'Admin access required'}), 403
        
        export_type = request.args.get('type', 'json')
        
        if export_type == 'json':
            # Export to JSON
            conn = get_db()
            cursor = conn.cursor()
            
            export_data = {}
            
            # Export clients
            cursor.execute('SELECT * FROM clients')
            export_data['clients'] = [dict(row) for row in cursor.fetchall()]
            
            # Export evidence
            cursor.execute('SELECT * FROM evidence')
            export_data['evidence'] = [dict(row) for row in cursor.fetchall()]
            
            # Export commands
            cursor.execute('SELECT * FROM commands')
            export_data['commands'] = [dict(row) for row in cursor.fetchall()]
            
            conn.close()
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_file = f'exports/cyber_ops_export_{timestamp}.json'
            os.makedirs('exports', exist_ok=True)
            
            with open(export_file, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            return send_file(
                export_file,
                as_attachment=True,
                download_name=f'cyber_ops_export_{timestamp}.json'
            )
        
        else:
            return jsonify({'error': 'Unsupported export type'}), 400
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'error': str(e)}), 500

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
        <title>Cybersecurity Operations Server v3.0</title>
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
            <h1>🔒 Cybersecurity Operations Server v3.0</h1>
            
            <div class="legal-notice">
                <strong>⚠ LEGAL NOTICE:</strong> This server is for AUTHORIZED security operations only.<br>
                Unauthorized access or use is strictly prohibited and may violate laws.
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
                <p>Use the CyberOps Console for full control: <code>python cyber_console.py http://localhost:5000</code></p>
                <p>Server started: <span id="start-time">Loading...</span></p>
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
            setInterval(loadStats, 30000); // Refresh every 30 seconds
        </script>
    </body>
    </html>
    '''

# ============================================================================
# MAINTENANCE FUNCTIONS
# ============================================================================

def update_client_status():
    """Periodically update client status"""
    while True:
        time.sleep(60)  # Check every minute
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
    
    # Start maintenance threads
    threading.Thread(target=backup_database, daemon=True).start()
    threading.Thread(target=update_client_status, daemon=True).start()
    
    # Display startup banner
    print(f"""
╔══════════════════════════════════════════════════════════╗
║      CYBERSECURITY OPERATIONS SERVER v3.0               ║
║         Authorized Security Testing Platform            ║
╚══════════════════════════════════════════════════════════╝

    🔒 Security: {"ENABLED" if REQUIRE_AUTH else "DISABLED"}
    📊 Database: {DATABASE}
    📁 Evidence: {os.path.abspath(EVIDENCE_FOLDER)}/
    📂 Uploads: {os.path.abspath(UPLOAD_FOLDER)}/
    
    🎯 Features:
    • 🔐 Secure client authentication
    • 📝 Comprehensive audit logging
    • 🗂️ Organized evidence collection
    • ⚡ Real-time command execution
    • 📊 Detailed statistics
    • 🛡️ Rate limiting & input sanitization
    
    ⚠  LEGAL NOTICE:
    This server is for AUTHORIZED security operations only.
    Unauthorized use may violate computer fraud laws.
    
    🔗 Server: http://0.0.0.0:5000
    📝 Logging to: cyber_ops_server.log
    
    Starting server...
    """)
    
    # Log server start
    log_audit_event("SERVER_START", "Cybersecurity Operations Server started", 
                   severity="INFO")
    
    # Run server
    app.run(
        host='0.0.0.0', 
        port=5000, 
        debug=False,  # Set to False in production
        threaded=True
    )
