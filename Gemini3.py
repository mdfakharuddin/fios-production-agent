from flask import Flask, request, jsonify, send_from_directory
import requests
import json
import re
import uuid
import time
import random
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import base64
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.route("/")
def home():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# Global storage for proxies
PROXIES = []
SESSION_POOL = []
POOL_LOCK = threading.Lock()
# Background executor for replenishing sessions
EXECUTOR = ThreadPoolExecutor(max_workers=3)

def load_proxies():
    """Load proxies from proxies.txt file or environment variable"""
    global PROXIES
    PROXIES = []
    
    # 1. Try loading from Environment Variable (Best for Vercel)
    env_proxies = os.environ.get('PROXY_LIST')
    if env_proxies:
        try:
            # Support comma-separated or newline-separated
            if ',' in env_proxies:
                items = env_proxies.split(',')
            else:
                items = env_proxies.split('\n')
            
            for item in items:
                if item.strip():
                    PROXIES.append(item.strip())
            print(f"Loaded {len(PROXIES)} proxies from Environment Variable.")
        except Exception as e:
            print(f"Error parsing PROXY_LIST env var: {e}")

    # 2. Try loading from file (fallback / local dev)
    try:
        # Adjusted path for Vercel environment where file might be in different location relative to function
        proxy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxies.txt')
        if os.path.exists(proxy_path):
            with open(proxy_path, 'r') as f:
                lines = f.readlines()
                file_proxies = [line.strip() for line in lines if line.strip() and not line.startswith('#')]
                PROXIES.extend(file_proxies)
                # Remove duplicates
                PROXIES = list(set(PROXIES))
            print(f"Loaded proxies from file. Total unique proxies: {len(PROXIES)}")
    except Exception as e:
        print(f"Error loading proxies from file: {e}")

def get_random_proxy():
    """Get a formatted proxy dict for requests"""
    if not PROXIES:
        return None
    
    proxy_url = random.choice(PROXIES)
    return {
        "http": proxy_url,
        "https": proxy_url
    }

def get_random_user_agent():
    """Rotate User Agents to avoid detection"""
    uas = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0'
    ]
    return random.choice(uas)

def extract_snlm0e_token(html):
    snlm0e_patterns = [
        r'"SNlM0e":"([^"]+)"',
        r"'SNlM0e':'([^']+)'",
        r'SNlM0e["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"FdrFJe":"([^"]+)"',
        r"'FdrFJe':'([^']+)'",
        r'FdrFJe["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"cfb2h":"([^"]+)"',
        r"'cfb2h':'([^']+)'",
        r'cfb2h["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'at["\']?\s*[:=]\s*["\']([^"\']{50,})["\']',
        r'"at":"([^"]+)"',
        r'"token":"([^"]+)"',
        r'data-token["\']?\s*=\s*["\']([^"\']+)["\']',
    ]
    
    for i, pattern in enumerate(snlm0e_patterns):
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            token = match.group(1)
            if len(token) > 20:
                return token
    
    return None

def extract_from_script_tags(html):
    # Optimized Pure Regex extraction (No BeautifulSoup) from script tags
    script_content_pattern = r'<script[^>]*>(.*?)</script>'
    matches = re.finditer(script_content_pattern, html, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        script_content = match.group(1)
        if not script_content: 
            continue
            
        if 'SNlM0e' in script_content or 'FdrFJe' in script_content:
            token = extract_snlm0e_token(script_content)
            if token:
                return token
        
        json_patterns = [
            r'\{[^}]*"[^"]*token[^"]*"[^}]*\}',
            r'\{[^}]*SNlM0e[^}]*\}',
            r'\{[^}]*FdrFJe[^}]*\}'
        ]
        
        for pattern in json_patterns:
            inner_matches = re.finditer(pattern, script_content, re.IGNORECASE)
            for inner_match in inner_matches:
                try:
                    json_str = inner_match.group(0)
                    json_obj = json.loads(json_str)
                    
                    for key, value in json_obj.items():
                        if isinstance(value, str) and len(value) > 50:
                            return value
                except:
                    continue
    
    return None

def extract_build_and_session_params(html):
    params = {}
    
    bl_patterns = [
        r'bl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'"bl":"([^"]+)"',
        r'buildLabel["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'boq[_-]assistant[^"\']*_(\d+\.\d+[^"\']*)',
        r'/_/BardChatUi.*?bl=([^&"\']+)',
    ]
    
    for pattern in bl_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['bl'] = match.group(1)
            break
    
    fsid_patterns = [
        r'f\.sid["\']?\s*[:=]\s*["\']?([^"\'&\s]+)',
        r'"fsid":"([^"]+)"',
        r'f\.sid=([^&"\']+)',
        r'sessionId["\']?\s*[:=]\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in fsid_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            params['fsid'] = match.group(1)
            break
    
    reqid_match = re.search(r'_reqid["\']?\s*[:=]\s*["\']?(\d+)', html)
    if reqid_match:
        params['reqid'] = int(reqid_match.group(1))
    
    if not params.get('bl'):
        params['bl'] = 'boq_assistant-bard-web-server_20251217.07_p5'
    
    if not params.get('fsid'):
        params['fsid'] = str(-1 * int(time.time() * 1000))
    
    if not params.get('reqid'):
        params['reqid'] = int(time.time() * 1000) % 1000000
    
    return params

def create_new_session():
    """Create a new session, preferably with a proxy"""
    session = requests.Session()
    
    # Configure Proxy
    proxy = get_random_proxy()
    if proxy:
        session.proxies.update(proxy)
    
    url = 'https://gemini.google.com/app'
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'none',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-dest': 'document',
        'upgrade-insecure-requests': '1',
        'cache-control': 'no-cache',
        'pragma': 'no-cache'
    }
    
    try:
        response = session.get(url, headers=headers, timeout=15)
        html = response.text
        
        cookies = {}
        for cookie in session.cookies:
            cookies[cookie.name] = cookie.value
        
        snlm0e = extract_snlm0e_token(html)
        
        if not snlm0e:
            snlm0e = extract_from_script_tags(html)
        
        if not snlm0e:
            return None
        
        params = extract_build_and_session_params(html)
        
        scraped_data = {
            'session': session,
            'cookies': cookies,
            'snlm0e': snlm0e,
            'bl': params['bl'],
            'fsid': params['fsid'],
            'reqid': params['reqid'],
            'html': html[:100], 
            'proxy_used': proxy
        }
        
        return scraped_data
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        return None

def replenish_pool(target_size=5):
    """Refill session pool in background"""
    current_size = 0
    with POOL_LOCK:
        current_size = len(SESSION_POOL)
        
    if current_size < target_size:
        for _ in range(target_size - current_size):
            try:
                EXECUTOR.submit(_create_and_add_session) 
            except Exception:
                pass

def _create_and_add_session():
    s = create_new_session()
    if s:
        with POOL_LOCK:
            SESSION_POOL.append(s)

def get_session_from_pool():
    with POOL_LOCK:
        if SESSION_POOL:
            return SESSION_POOL.pop(0)
    return None

def return_session_to_pool(session_data):
    with POOL_LOCK:
        if len(SESSION_POOL) < 10:
            SESSION_POOL.append(session_data)

def build_payload(prompt, snlm0e, image_data=None):
    escaped_prompt = prompt.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    session_id = uuid.uuid4().hex
    request_uuid = str(uuid.uuid4()).upper()
    
    # Image part if provided as the 7th element [6]
    image_part = 0
    if image_data:
        # Standard Bard vision structure: [[["", 0, [data, null, "image/jpeg"]]]]
        image_part = [[["", 0, [image_data, None, "image/jpeg"]]]]
    
    # Payload structure verified for Gemini
    payload_data = [
        [escaped_prompt, 0, None, None, None, None, image_part],
        ["en-US"],
        ["", "", "", None, None, None, None, None, None, ""],
        snlm0e,
        session_id,
        None,
        [0],
        1,
        None,
        None,
        1,
        0,
        None,
        None,
        None,
        None,
        None,
        [[0]],
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        1,
        None,
        None,
        [4],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        [2],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        None,
        None,
        None,
        None,
        None,
        request_uuid,
        None,
        []
    ]
    
    payload_str = json.dumps(payload_data, separators=(',', ':'))
    escaped_payload = payload_str.replace('\\', '\\\\').replace('"', '\\"')
    
    return {
        'f.req': f'[null,"{escaped_payload}"]',
        '': ''
    }

def parse_streaming_response(response_text):
    lines = response_text.strip().split('\n')
    full_text = ""
    for line in lines:
        if not line or line.startswith(')]}'): continue
        try:
            if line.isdigit(): continue
            data = json.loads(line)
            if isinstance(data, list) and len(data) > 0:
                if data[0][0] == "wrb.fr" and len(data[0]) > 2:
                    inner_json = data[0][2]
                    if inner_json:
                        parsed = json.loads(inner_json)
                        if isinstance(parsed, list) and len(parsed) > 4:
                            content_array = parsed[4]
                            if isinstance(content_array, list) and len(content_array) > 0:
                                first_item = content_array[0]
                                if isinstance(first_item, list) and len(first_item) > 0:
                                    text_array = first_item[1]
                                    if len(text_array) > 0:
                                        text_content = text_array[0]
                                        if isinstance(text_content, str) and len(text_content) > len(full_text):
                                            full_text = text_content
        except Exception: continue
    
    if full_text:
        full_text = full_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    return full_text if full_text else None

def perform_chat_request(prompt, session_data, image_data=None):
    session = session_data['session']
    cookies = session_data['cookies']
    snlm0e = session_data['snlm0e']
    bl = session_data['bl']
    fsid = session_data['fsid']
    reqid = session_data['reqid']
    
    base_url = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
    url = f"{base_url}?bl={bl}&f.sid={fsid}&hl=en-US&_reqid={reqid}&rt=c"
    
    payload = build_payload(prompt, snlm0e, image_data)
    cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
    
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'origin': 'https://gemini.google.com',
        'referer': 'https://gemini.google.com/',
        'Cookie': cookie_str
    }
    
    if session_data.get('proxy_used'):
        session.proxies.update(session_data['proxy_used'])

    response = session.post(url, data=payload, headers=headers, timeout=60)
    return response

def chat_with_gemini(prompt, image_data=None):
    start_time = time.time()
    replenish_pool(target_size=5)
    scraped = get_session_from_pool()
    
    if not scraped:
        scraped = create_new_session()
        
    if not scraped:
        return {'success': False, 'error': 'Failed to establish session with Gemini'}
    
    try:
        response = perform_chat_request(prompt, scraped, image_data)
        
        if response.status_code != 200:
            scraped = create_new_session()
            if scraped:
                response = perform_chat_request(prompt, scraped, image_data)
                if response.status_code == 200:
                    return_session_to_pool(scraped)
            if response.status_code != 200:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        else:
            return_session_to_pool(scraped)
            
        result = parse_streaming_response(response.text)
        end_time = time.time()
        
        replenish_pool(target_size=5)
        
        if result:
            return {
                'success': True,
                'response': result,
                'metadata': {
                    'response_time': f'{round(end_time - start_time, 2)}s',
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'model': 'gemini',
                    'proxy': (scraped.get('proxy_used') or {}).get('http', 'None')
                }
            }
        else:
            return {'success': False, 'error': 'No response received from Gemini'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Auto-replenish on cold start
try:
    replenish_pool(target_size=5)
except:
    pass

@app.route('/api/status')
def status_api():
    proxy_count = len(PROXIES)
    session_count = 0
    with POOL_LOCK:
        session_count = len(SESSION_POOL)
        
    return jsonify({
        'success': True,
        'message': 'AutoTagger AI Backend Active',
        'api_dev': '@ISmartCoder',
        'status': {
            'proxies_loaded': proxy_count,
            'active_sessions': session_count
        }
    })

@app.route('/api/ask', methods=['GET', 'POST'])
def ask_gemini():
    image_data = None
    if request.method == 'POST':
        # Handle JSON or multipart
        if request.is_json:
            data = request.get_json()
            prompt = data.get('prompt') if data else None
        else:
            prompt = request.form.get('prompt')
            if 'image' in request.files:
                image_file = request.files['image']
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
    else:
        prompt = request.args.get('prompt')
    
    if not prompt:
        return jsonify({'success': False, 'error': 'Missing prompt'}), 400
    
    if len(prompt.strip()) == 0:
        return jsonify({'success': False, 'error': 'Prompt cannot be empty'}), 400
    
    result = chat_with_gemini(prompt, image_data)
    result['api_dev'] = '@ISmartCoder'
    
    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 500

@app.errorhandler(500)
def internal_error(error):
    error_msg = str(error)
    if hasattr(error, 'original_exception'):
        error_msg = str(error.original_exception)
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'details': error_msg
    }), 500

if __name__ == '__main__':
    load_proxies()
    app.run(debug=True, host='0.0.0.0', port=5001)
