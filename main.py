# main.py - Professional Instagram Spam Tool
from flask import Flask, render_template, request, redirect, jsonify, session
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired
import threading
import time
import random
import os
import json
import logging
from datetime import datetime
import uuid
import re

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hawk_sujal_pro_2025_secure")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state
app_state = {
    "running": False,
    "sent": 0,
    "failed": 0,
    "threads_active": 0,
    "logs": [],
    "status": "Ready",
    "start_time": None,
    "total_targets": 0
}

# Configuration with defaults
config = {
    "mode": "username",
    "username": "",
    "password": "",
    "sessionid": "",
    "targets": "",  # Can be thread_id or comma-separated usernames
    "message_type": "thread",  # thread, dm, comment, post_comment
    "messages": "",
    "delay": 2.5,
    "delay_random": True,
    "cycle": 25,
    "break_time": 45,
    "max_threads": 3,
    "use_proxy": False,
    "proxy_list": "",
    "rotate_proxy": False,
    "max_retries": 3,
    "stop_on_challenge": False
}

# Advanced device fingerprints (updated 2025)
DEVICES = [
    {
        "phone_manufacturer": "Google",
        "phone_model": "Pixel 8 Pro",
        "android_version": 35,
        "android_release": "15.0.0",
        "app_version": "325.0.0.42.111"
    },
    {
        "phone_manufacturer": "Samsung",
        "phone_model": "SM-S928B",
        "android_version": 35,
        "android_release": "15.0.0",
        "app_version": "324.0.0.41.110"
    },
    {
        "phone_manufacturer": "OnePlus",
        "phone_model": "PJZ110",
        "android_version": 35,
        "android_release": "15.0.0", 
        "app_version": "322.0.0.40.108"
    },
    {
        "phone_manufacturer": "Xiaomi",
        "phone_model": "23127PN0CC",
        "android_version": 35,
        "android_release": "15.0.0",
        "app_version": "325.0.0.42.111"
    },
    {
        "phone_manufacturer": "Apple",
        "phone_device": "iPhone15,3",
        "device_string": "iPhone15,3",
        "app_version": "325.0.0.42.111",
        "ios_version": "18.0.0"
    }
]

# Session management
active_sessions = {}
worker_threads = []

# Helper functions
def log_message(message, level="info"):
    """Add log message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    if level == "error":
        log_entry = f"❌ {log_entry}"
    elif level == "success":
        log_entry = f"✅ {log_entry}"
    elif level == "warning":
        log_entry = f"⚠️ {log_entry}"
    
    app_state["logs"].append(log_entry)
    
    # Keep only last 500 logs
    if len(app_state["logs"]) > 500:
        app_state["logs"] = app_state["logs"][-500:]
    
    logger.info(message)
    return log_entry

def create_client(device_index=0):
    """Create Instagram client with device settings"""
    cl = Client()
    
    # Set random device
    device = random.choice(DEVICES)
    
    # Android settings
    if "android_version" in device:
        cl.set_device(device)
        user_agent = f"Instagram {device['app_version']} Android ({device['android_version']}/{device['android_release']}; 480dpi; 1080x2400; {device['phone_manufacturer']}/{device['phone_model']}; {random.choice(['google', 'samsung', 'oneplus'])}; {device['phone_model'].lower()}; en_US)"
    # iOS settings
    else:
        cl.set_device({
            "device_string": device["device_string"],
            "phone_manufacturer": device["phone_manufacturer"],
            "phone_device": device["phone_device"],
            "phone_model": device["phone_device"],
            "phone_dpi": "460dpi",
            "phone_resolution": "1170x2532",
            "phone_chipset": "Apple A16 Bionic",
            "version_code": "325000000"
        })
        user_agent = f"Instagram {device['app_version']} iPhone OS {device['ios_version']} (like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    
    cl.set_user_agent(user_agent)
    cl.delay_range = [5, 15]  # Realistic delays
    cl.request_timeout = 30
    
    return cl

def safe_login(client, username, password, session_id=None):
    """Safe login with retries and error handling"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if session_id:
                # Try session login
                settings = {
                    "sessionid": session_id,
                    "username": username,
                    "device_settings": random.choice(DEVICES)
                }
                client.set_settings(settings)
                client.login_by_sessionid(session_id)
                return True, "session"
            else:
                # Username/password login
                client.login(username, password)
                return True, "credentials"
                
        except ChallengeRequired as e:
            log_message(f"Challenge required: {str(e)[:100]}", "warning")
            return False, "challenge_required"
            
        except LoginRequired as e:
            log_message(f"Login required: {str(e)[:100]}", "warning")
            return False, "login_required"
            
        except Exception as e:
            error_msg = str(e)
            if "checkpoint" in error_msg.lower():
                return False, "checkpoint_required"
            elif "password" in error_msg.lower():
                return False, "wrong_password"
            elif attempt < max_retries - 1:
                wait_time = random.uniform(5, 15)
                log_message(f"Login attempt {attempt+1} failed, retrying in {wait_time:.1f}s...", "warning")
                time.sleep(wait_time)
            else:
                return False, error_msg[:150]
    
    return False, "max_retries_exceeded"

def send_direct_message(client, target, message):
    """Send DM to user"""
    try:
        # Check if target is thread_id or username
        if target.isdigit():
            thread_id = int(target)
            result = client.direct_send(message, thread_ids=[thread_id])
        else:
            # Get user_id from username
            user_id = client.user_id_from_username(target)
            result = client.direct_send(message, user_ids=[user_id])
        
        return True, result.id
    except Exception as e:
        error_msg = str(e)
        if "feedback_required" in error_msg:
            return False, "feedback_required"
        elif "rate limit" in error_msg.lower():
            return False, "rate_limit"
        elif "spam" in error_msg.lower():
            return False, "spam_detected"
        else:
            return False, error_msg[:100]

def post_comment(client, post_url, comment):
    """Post comment on a post"""
    try:
        media_id = client.media_pk_from_url(post_url)
        result = client.media_comment(media_id, comment)
        return True, result.pk
    except Exception as e:
        return False, str(e)[:100]

def like_post(client, post_url):
    """Like a post"""
    try:
        media_id = client.media_pk_from_url(post_url)
        client.media_like(media_id)
        return True, "liked"
    except Exception as e:
        return False, str(e)[:100]

def follow_user(client, username):
    """Follow a user"""
    try:
        user_id = client.user_id_from_username(username)
        client.user_follow(user_id)
        return True, "followed"
    except Exception as e:
        return False, str(e)[:100]

def worker_thread(worker_id, config_data, messages_list, targets_list):
    """Worker thread for spamming"""
    log_message(f"Thread {worker_id} started", "success")
    
    # Create client
    client = create_client(worker_id)
    
    # Login
    login_success, login_result = safe_login(
        client,
        config_data["username"],
        config_data["password"],
        config_data["sessionid"] if config_data["mode"] == "session" else None
    )
    
    if not login_success:
        log_message(f"Thread {worker_id} login failed: {login_result}", "error")
        return
    
    log_message(f"Thread {worker_id} logged in successfully", "success")
    
    message_count = 0
    target_index = 0
    
    while app_state["running"] and target_index < len(targets_list):
        try:
            target = targets_list[target_index % len(targets_list)]
            message = random.choice(messages_list)
            
            # Send based on message type
            if config_data["message_type"] == "dm":
                success, result = send_direct_message(client, target, message)
                action_type = "DM"
            elif config_data["message_type"] == "comment":
                success, result = post_comment(client, target, message)
                action_type = "Comment"
            elif config_data["message_type"] == "like":
                success, result = like_post(client, target)
                action_type = "Like"
            elif config_data["message_type"] == "follow":
                success, result = follow_user(client, target)
                action_type = "Follow"
            else:  # thread
                success, result = send_direct_message(client, target, message)
                action_type = "Thread Message"
            
            if success:
                app_state["sent"] += 1
                message_count += 1
                log_entry = f"Thread {worker_id}: {action_type} #{app_state['sent']} to {target[:20]}"
                if len(message) < 30:
                    log_entry += f" → {message}"
                else:
                    log_entry += f" → {message[:30]}..."
                log_message(log_entry, "success")
            else:
                app_state["failed"] += 1
                log_message(f"Thread {worker_id}: Failed to send to {target[:20]} - {result}", "error")
                
                # Check if we should stop on certain errors
                if result in ["feedback_required", "challenge_required"] and config_data.get("stop_on_challenge"):
                    log_message(f"Thread {worker_id} stopping due to {result}", "warning")
                    break
            
            # Cycle break
            if message_count % config_data["cycle"] == 0 and message_count > 0:
                break_time = config_data["break_time"]
                log_message(f"Thread {worker_id}: Taking break for {break_time}s after {config_data['cycle']} messages", "warning")
                for i in range(break_time):
                    if not app_state["running"]:
                        break
                    time.sleep(1)
            
            # Delay with randomness
            delay = config_data["delay"]
            if config_data["delay_random"]:
                delay = random.uniform(delay * 0.7, delay * 1.3)
            
            for i in range(int(delay * 10)):
                if not app_state["running"]:
                    break
                time.sleep(0.1)
            
            target_index += 1
            
        except Exception as e:
            error_msg = str(e)
            log_message(f"Thread {worker_id} error: {error_msg[:100]}", "error")
            time.sleep(random.uniform(5, 10))
    
    log_message(f"Thread {worker_id} stopped", "warning")
    app_state["threads_active"] -= 1

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Stop any running process
        app_state["running"] = False
        time.sleep(2)
        
        # Clear old state
        app_state["logs"] = []
        app_state["sent"] = 0
        app_state["failed"] = 0
        app_state["status"] = "Starting..."
        
        # Update config from form
        config.update({
            "mode": request.form.get('mode', 'username'),
            "username": request.form.get('username', '').strip(),
            "password": request.form.get('password', '').strip(),
            "sessionid": request.form.get('sessionid', '').strip(),
            "targets": request.form.get('targets', '').strip(),
            "message_type": request.form.get('message_type', 'thread'),
            "messages": request.form.get('messages', '').strip(),
            "delay": float(request.form.get('delay', 2.5)),
            "delay_random": request.form.get('delay_random') == 'on',
            "cycle": int(request.form.get('cycle', 25)),
            "break_time": int(request.form.get('break_time', 45)),
            "max_threads": int(request.form.get('max_threads', 3)),
            "use_proxy": request.form.get('use_proxy') == 'on',
            "proxy_list": request.form.get('proxy_list', '').strip(),
            "rotate_proxy": request.form.get('rotate_proxy') == 'on',
            "max_retries": int(request.form.get('max_retries', 3)),
            "stop_on_challenge": request.form.get('stop_on_challenge') == 'on'
        })
        
        # Parse targets
        targets_list = []
        if config["targets"]:
            # Split by comma, newline, or space
            targets = re.split(r'[,|\n\s]+', config["targets"])
            targets_list = [t.strip() for t in targets if t.strip()]
        
        # Parse messages
        messages_list = [m.strip() for m in config["messages"].split('\n') if m.strip()]
        
        if not targets_list:
            log_message("❌ Error: No targets provided!", "error")
            app_state["status"] = "No targets"
        elif not messages_list:
            log_message("❌ Error: No messages provided!", "error")
            app_state["status"] = "No messages"
        else:
            app_state["running"] = True
            app_state["start_time"] = datetime.now()
            app_state["total_targets"] = len(targets_list)
            app_state["status"] = "BOMBING ACTIVE"
            app_state["threads_active"] = 0
            
            log_message(f"🚀 SPAMMER STARTED - HAWK SUJAL PRO 2025", "success")
            log_message(f"📊 Targets: {len(targets_list)} | Messages: {len(messages_list)} | Threads: {config['max_threads']}", "info")
            
            # Start worker threads
            for i in range(config["max_threads"]):
                if not app_state["running"]:
                    break
                    
                thread = threading.Thread(
                    target=worker_thread,
                    args=(i + 1, config, messages_list, targets_list),
                    daemon=True
                )
                thread.start()
                worker_threads.append(thread)
                app_state["threads_active"] += 1
                time.sleep(random.uniform(0.5, 2))  # Stagger thread starts
            
            log_message(f"✅ All {config['max_threads']} threads started successfully", "success")
    
    # Prepare stats
    stats = {
        "running": app_state["running"],
        "sent": app_state["sent"],
        "failed": app_state["failed"],
        "threads_active": app_state["threads_active"],
        "logs": app_state["logs"][-50:],  # Last 50 logs
        "status": app_state["status"],
        "total_targets": app_state["total_targets"]
    }
    
    return render_template('index.html', **stats, cfg=config)

@app.route('/stop')
def stop_spammer():
    app_state["running"] = False
    app_state["status"] = "STOPPED"
    log_message("⏹️ SPAMMER STOPPED BY USER", "warning")
    
    # Clear worker threads
    worker_threads.clear()
    
    time.sleep(1)
    return redirect('/')

@app.route('/api/status')
def api_status():
    """API endpoint for real-time status"""
    return jsonify({
        "running": app_state["running"],
        "sent": app_state["sent"],
        "failed": app_state["failed"],
        "threads_active": app_state["threads_active"],
        "status": app_state["status"],
        "logs": app_state["logs"][-20:],  # Last 20 logs
        "total_targets": app_state["total_targets"],
        "uptime": str(datetime.now() - app_state["start_time"]) if app_state["start_time"] else "0:00:00"
    })

@app.route('/api/get_session')
def get_session():
    """Get session ID for current login"""
    if config["mode"] == "session" and config["sessionid"]:
        return jsonify({"sessionid": config["sessionid"]})
    
    # Try to get session from logged in client
    if worker_threads and hasattr(worker_threads[0], 'client'):
        try:
            session_id = worker_threads[0].client.get_settings().get("sessionid")
            if session_id:
                return jsonify({"sessionid": session_id})
        except:
            pass
    
    return jsonify({"error": "No session available"})

@app.route('/api/validate_target', methods=['POST'])
def validate_target():
    """Validate target (thread or username)"""
    data = request.json
    target = data.get('target', '')
    
    if not target:
        return jsonify({"valid": False, "error": "Empty target"})
    
    # Check if it's a numeric thread ID
    if target.isdigit():
        return jsonify({
            "valid": True,
            "type": "thread_id",
            "target": target
        })
    
    # Check if it's a URL
    if target.startswith(('http://', 'https://')):
        # Check if it's an Instagram URL
        if 'instagram.com/p/' in target:
            return jsonify({
                "valid": True,
                "type": "post_url",
                "target": target
            })
        elif 'instagram.com/' in target and '/p/' not in target:
            # Extract username from URL
            username = target.split('instagram.com/')[-1].split('/')[0].replace('@', '')
            return jsonify({
                "valid": True,
                "type": "username",
                "target": username
            })
    
    # Assume it's a username
    if re.match(r'^[a-zA-Z0-9._]{1,30}$', target):
        return jsonify({
            "valid": True,
            "type": "username",
            "target": target
        })
    
    return jsonify({"valid": False, "error": "Invalid target format"})

@app.route('/test_login', methods=['POST'])
def test_login():
    """Test login credentials"""
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    session_id = data.get('sessionid', '')
    
    if not username:
        return jsonify({"success": False, "error": "Username required"})
    
    if not password and not session_id:
        return jsonify({"success": False, "error": "Password or Session ID required"})
    
    # Create test client
    client = create_client()
    
    # Try login
    success, result = safe_login(client, username, password, session_id)
    
    if success:
        # Get session ID
        settings = client.get_settings()
        session_id = settings.get("sessionid", "")
        
        return jsonify({
            "success": True,
            "message": "Login successful!",
            "sessionid": session_id,
            "user_id": client.user_id
        })
    else:
        return jsonify({
            "success": False,
            "error": result
        })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
