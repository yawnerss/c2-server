#!/usr/bin/env python3
"""
Flask Webhook Server - Receives webhook commands to trigger DDoS attacks
"""
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import threading
import time
import hashlib
import hmac
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# Create Flask app
app = Flask(__name__)
CORS(app)

# Configuration
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your-secret-key-here')
API_KEY = os.environ.get('API_KEY', 'your-api-key-here')
PORT = int(os.environ.get('PORT', 5000))

@dataclass
class AttackJob:
    """Attack job information"""
    id: str
    target: str
    method: str
    duration: int
    rps: int
    created_at: datetime
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    client_id: Optional[str] = None
    results: Dict = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = {
                "requests_sent": 0,
                "success_rate": 0,
                "rps": 0,
                "errors": []
            }

class AttackManager:
    """Manages attack jobs and execution"""
    
    def __init__(self):
        self.jobs: Dict[str, AttackJob] = {}
        self.clients: Dict[str, Dict] = {}
        self.job_lock = threading.Lock()
        self.next_job_id = 1
    
    def create_job(self, target: str, method: str = "http", duration: int = 60, rps: int = 100) -> str:
        """Create a new attack job"""
        job_id = f"job_{self.next_job_id}_{int(time.time())}"
        self.next_job_id += 1
        
        job = AttackJob(
            id=job_id,
            target=target,
            method=method,
            duration=duration,
            rps=rps,
            created_at=datetime.now()
        )
        
        with self.job_lock:
            self.jobs[job_id] = job
        
        # Start attack in background thread
        thread = threading.Thread(target=self.execute_attack, args=(job_id,), daemon=True)
        thread.start()
        
        return job_id
    
    def execute_attack(self, job_id: str):
        """Execute attack job"""
        with self.job_lock:
            if job_id not in self.jobs:
                return
            
            job = self.jobs[job_id]
            job.status = "running"
            job.started_at = datetime.now()
        
        try:
            print(f"[⚡] Starting attack {job_id}")
            print(f"    Target: {job.target}")
            print(f"    Method: {job.method}")
            print(f"    Duration: {job.duration}s")
            
            # Import and execute LAYER7.py tool
            # This is where you integrate with your actual LAYER7.py
            result = self.run_layer7_attack(job)
            
            with self.job_lock:
                job.status = "completed"
                job.completed_at = datetime.now()
                job.results.update(result)
            
            print(f"[✓] Attack {job_id} completed")
            
        except Exception as e:
            with self.job_lock:
                job.status = "failed"
                job.completed_at = datetime.now()
                job.results["errors"].append(str(e))
            
            print(f"[✗] Attack {job_id} failed: {e}")
    
    def run_layer7_attack(self, job: AttackJob) -> Dict:
        """Run the LAYER7.py attack tool"""
        # This is a simulation - replace with actual LAYER7.py integration
        import subprocess
        import sys
        
        # Create command based on method
        if job.method == "http":
            # Layer 7 HTTP attack
            cmd = [
                sys.executable, "-c",
                f"""
import time
import random
print("Starting HTTP attack on {{job.target}}")
requests = 0
start = time.time()
while time.time() - start < {job.duration}:
    time.sleep(0.01)
    requests += 1
    if requests % 100 == 0:
        print(f"Requests: {{requests}}")
print(f"Total: {{requests}} requests")
                """
            ]
        elif job.method == "tcp":
            # TCP SYN flood
            cmd = [
                sys.executable, "-c",
                f"""
import time
print("Starting TCP SYN flood on {{job.target}}")
time.sleep({job.duration})
print("TCP attack completed")
                """
            ]
        else:
            # Default method
            cmd = [
                sys.executable, "-c",
                f"""
import time
print("Starting attack on {{job.target}}")
time.sleep({job.duration})
print("Attack completed")
                """
            ]
        
        # Execute the attack
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=job.duration + 10)
        
        # Parse results
        requests_sent = 0
        output = result.stdout
        
        # Simple parsing - extract numbers from output
        for line in output.split('\n'):
            if 'requests' in line.lower() or 'total' in line.lower():
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    requests_sent = max(requests_sent, int(numbers[0]))
        
        return {
            "requests_sent": requests_sent,
            "success_rate": random.randint(70, 99) if requests_sent > 0 else 0,
            "rps": requests_sent / job.duration if job.duration > 0 else 0
        }
    
    def get_job(self, job_id: str) -> Optional[AttackJob]:
        """Get job by ID"""
        with self.job_lock:
            return self.jobs.get(job_id)
    
    def list_jobs(self, limit: int = 50) -> List[AttackJob]:
        """List all jobs"""
        with self.job_lock:
            jobs = list(self.jobs.values())
            jobs.sort(key=lambda x: x.created_at, reverse=True)
            return jobs[:limit]
    
    def get_stats(self) -> Dict:
        """Get server statistics"""
        with self.job_lock:
            total_jobs = len(self.jobs)
            running = len([j for j in self.jobs.values() if j.status == "running"])
            completed = len([j for j in self.jobs.values() if j.status == "completed"])
            failed = len([j for j in self.jobs.values() if j.status == "failed"])
            
            total_requests = sum(j.results.get("requests_sent", 0) for j in self.jobs.values())
        
        return {
            "total_jobs": total_jobs,
            "running": running,
            "completed": completed,
            "failed": failed,
            "total_requests": total_requests,
            "uptime": int(time.time() - self.start_time) if hasattr(self, 'start_time') else 0
        }

# Initialize attack manager
attack_manager = AttackManager()
attack_manager.start_time = time.time()

# HTML template for web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>DDoS Webhook Server</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #0a0a0a; color: #00ff00; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .panel { background: #111; border: 1px solid #00ff00; padding: 20px; margin: 20px 0; border-radius: 5px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-box { background: #222; padding: 15px; border-radius: 5px; text-align: center; }
        .form-group { margin: 15px 0; }
        input, select, button { padding: 10px; margin: 5px; width: 100%; max-width: 300px; }
        button { background: #00aa00; color: white; border: none; cursor: pointer; }
        button:hover { background: #00cc00; }
        .job { background: #222; padding: 10px; margin: 10px 0; border-left: 4px solid #00ff00; }
        .job.running { border-color: #ffff00; }
        .job.completed { border-color: #00ff00; }
        .job.failed { border-color: #ff0000; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 DDoS Webhook Server</h1>
            <p>Control panel for distributed attacks</p>
        </div>
        
        <div class="panel">
            <h2>📊 Server Stats</h2>
            <div class="stats">
                <div class="stat-box">
                    <h3>{{ stats.total_jobs }}</h3>
                    <p>Total Jobs</p>
                </div>
                <div class="stat-box">
                    <h3>{{ stats.running }}</h3>
                    <p>Running</p>
                </div>
                <div class="stat-box">
                    <h3>{{ stats.completed }}</h3>
                    <p>Completed</p>
                </div>
                <div class="stat-box">
                    <h3>{{ stats.total_requests | default(0) | intcomma }}</h3>
                    <p>Total Requests</p>
                </div>
            </div>
        </div>
        
        <div class="panel">
            <h2>🎯 Start New Attack</h2>
            <form id="attackForm">
                <div class="form-group">
                    <label>Target URL:</label><br>
                    <input type="text" name="target" placeholder="https://example.com" required>
                </div>
                <div class="form-group">
                    <label>Attack Method:</label><br>
                    <select name="method">
                        <option value="http">HTTP (Layer 7)</option>
                        <option value="tcp">TCP (SYN Flood)</option>
                        <option value="udp">UDP (Amplification)</option>
                        <option value="icmp">ICMP (Ping Flood)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Duration (seconds):</label><br>
                    <input type="number" name="duration" value="60" min="10" max="3600">
                </div>
                <div class="form-group">
                    <label>Requests Per Second:</label><br>
                    <input type="number" name="rps" value="100" min="1" max="10000">
                </div>
                <button type="submit">⚡ Start Attack</button>
            </form>
        </div>
        
        <div class="panel">
            <h2>📋 Recent Jobs</h2>
            <div id="jobsList">
                {% for job in jobs %}
                <div class="job {{ job.status }}">
                    <strong>#{{ job.id }}</strong> - {{ job.target }}<br>
                    <small>
                        Status: {{ job.status }} | 
                        Method: {{ job.method }} | 
                        Created: {{ job.created_at.strftime('%H:%M:%S') }}
                        {% if job.results.requests_sent > 0 %}
                        | Requests: {{ job.results.requests_sent | intcomma }}
                        {% endif %}
                    </small>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="panel">
            <h2>🔗 Webhook Endpoints</h2>
            <pre>
POST /webhook/attack
Content-Type: application/json
Authorization: Bearer YOUR_API_KEY

{
    "target": "https://example.com",
    "method": "http",
    "duration": 60,
    "rps": 100,
    "secret": "your-webhook-secret"
}

GET /api/jobs - List all jobs
GET /api/jobs/&lt;job_id&gt; - Get job status
GET /api/stats - Get server stats
            </pre>
        </div>
    </div>
    
    <script>
        document.getElementById('attackForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            const response = await fetch('/webhook/attack', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            alert(result.message || 'Attack started!');
            location.reload();
        });
        
        // Auto-refresh jobs every 10 seconds
        setInterval(() => {
            location.reload();
        }, 10000);
    </script>
</body>
</html>
"""

def verify_webhook_signature(payload, signature, secret):
    """Verify webhook signature"""
    if not secret:
        return True  # No secret configured
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

def verify_api_key():
    """Verify API key from header"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        return token == API_KEY
    
    return False

@app.route('/')
def index():
    """Main web interface"""
    stats = attack_manager.get_stats()
    jobs = attack_manager.list_jobs(limit=20)
    
    # Add intcomma filter for template
    import locale
    locale.setlocale(locale.LC_ALL, '')
    
    def intcomma(value):
        try:
            return locale.format_string("%d", value, grouping=True)
        except:
            return str(value)
    
    return render_template_string(
        HTML_TEMPLATE,
        stats=stats,
        jobs=jobs,
        intcomma=intcomma
    )

@app.route('/webhook/attack', methods=['POST'])
def webhook_attack():
    """Webhook endpoint to trigger attacks"""
    try:
        # Verify request
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        data = request.get_json()
        
        # Verify signature (optional)
        signature = request.headers.get('X-Webhook-Signature')
        payload = json.dumps(data, sort_keys=True)
        
        if not verify_webhook_signature(payload, signature or '', WEBHOOK_SECRET):
            return jsonify({"error": "Invalid webhook signature"}), 401
        
        # Verify API key (alternative auth)
        if not verify_api_key() and WEBHOOK_SECRET != 'your-secret-key-here':
            return jsonify({"error": "Invalid API key"}), 401
        
        # Validate required fields
        required_fields = ['target']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Extract parameters
        target = data['target']
        method = data.get('method', 'http')
        duration = int(data.get('duration', 60))
        rps = int(data.get('rps', 100))
        
        # Validate parameters
        if duration < 1 or duration > 3600:
            return jsonify({"error": "Duration must be between 1 and 3600 seconds"}), 400
        
        if rps < 1 or rps > 10000:
            return jsonify({"error": "RPS must be between 1 and 10000"}), 400
        
        valid_methods = ['http', 'tcp', 'udp', 'icmp']
        if method not in valid_methods:
            return jsonify({"error": f"Invalid method. Must be one of: {', '.join(valid_methods)}"}), 400
        
        # Create attack job
        job_id = attack_manager.create_job(target, method, duration, rps)
        
        return jsonify({
            "success": True,
            "message": f"Attack started with job ID: {job_id}",
            "job_id": job_id,
            "target": target,
            "method": method,
            "duration": duration,
            "rps": rps
        }), 202
        
    except ValueError as e:
        return jsonify({"error": f"Invalid parameter: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """API endpoint to list all jobs"""
    jobs = attack_manager.list_jobs()
    return jsonify({
        "jobs": [asdict(job) for job in jobs],
        "total": len(jobs)
    })

@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """API endpoint to get job status"""
    job = attack_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify(asdict(job))

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint to get server statistics"""
    stats = attack_manager.get_stats()
    return jsonify(stats)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════╗
    ║    DDOS WEBHOOK SERVER              ║
    ║    [CREATED BY: (BTR) DDOS DIVISION]║
    ║    [USE AT YOUR OWN RISK]           ║
    ╚══════════════════════════════════════╝
    """)
    
    print(f"[📡] Server starting on port {PORT}")
    print(f"[🔗] Web interface: http://localhost:{PORT}")
    print(f"[🔐] Webhook endpoint: POST http://localhost:{PORT}/webhook/attack")
    print(f"[📊] API endpoint: GET http://localhost:{PORT}/api/stats")
    print("\n[⚡] Waiting for webhook commands...\n")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
