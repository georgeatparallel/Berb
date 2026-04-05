"""Berb Topic Approval Launcher - Starts both UI and API servers."""

import os
import sys
import time
import subprocess
import webbrowser
import threading
import requests

# Set API key
os.environ['OPENROUTER_API_KEY'] = '***REMOVED-OPENROUTER-KEY***'

def start_ui_server():
    """Start simple HTTP server for UI."""
    os.chdir(r'E:\Documents\Vibe-Coding\Berb\berb\ui')
    subprocess.run([sys.executable, '-m', 'http.server', '8001'], 
                   creationflags=subprocess.CREATE_NEW_CONSOLE)

def start_api_server():
    """Start FastAPI server for API."""
    os.chdir(r'E:\Documents\Vibe-Coding\Berb')
    subprocess.run([sys.executable, '-m', 'berb.server.web_api_real'],
                   creationflags=subprocess.CREATE_NEW_CONSOLE)

def wait_for_servers():
    """Wait for servers to be ready."""
    print("Waiting for servers to start...")
    for i in range(30):  # 30 seconds max
        time.sleep(1)
        try:
            r = requests.get('http://localhost:8002/healthz', timeout=2)
            if r.status_code == 200:
                print("✅ API server ready!")
                return True
        except:
            pass
        print(f"  Waiting... ({i+1}s)")
    return False

if __name__ == "__main__":
    print("=" * 60)
    print("  Berb Topic Approval System")
    print("=" * 60)
    print()
    
    # Start servers in separate console windows
    print("Starting UI server on port 8001...")
    ui_thread = threading.Thread(target=start_ui_server, daemon=True)
    ui_thread.start()
    
    print("Starting API server on port 8002...")
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    
    # Wait for servers
    if wait_for_servers():
        print()
        print("Opening browser...")
        webbrowser.open('http://localhost:8001/topic-approval.html')
        
        print()
        print("=" * 60)
        print("  ✅ READY!")
        print("=" * 60)
        print()
        print("  UI:  http://localhost:8001/topic-approval.html")
        print("  API: http://localhost:8002")
        print()
        print("  Two console windows opened - keep them running!")
        print()
    else:
        print("❌ Servers failed to start")
        sys.exit(1)
