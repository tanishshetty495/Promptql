#!/usr/bin/env python3
"""
Unified startup script for PromptQL Schema-Aware Text-to-SQL Engine
Starts both backend and frontend services with a single command.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path
import threading

def start_backend():
    """Start the FastAPI backend server"""
    print("🚀 Starting PromptQL Backend...")
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Monitor and print backend output
    for line in iter(backend_process.stdout.readline, ''):
        if line:
            print(f"[BACKEND] {line.rstrip()}")

    backend_process.wait()

def start_frontend():
    """Start the frontend HTTP server"""
    print("🌐 Starting Frontend Server...")
    frontend_dir = Path(__file__).parent / "frontend"
    frontend_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8080"],
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Monitor and print frontend output
    for line in iter(frontend_process.stdout.readline, ''):
        if line:
            print(f"[FRONTEND] {line.rstrip()}")

    frontend_process.wait()

def main():
    print("=" * 60)
    print("🚀 Starting PromptQL - Schema-Aware Text-to-SQL Engine")
    print("=" * 60)
    print("📝 Using SECRET_KEY from .env file (line 2)")
    print("🔧 Backend will be available at: http://localhost:8000")
    print("🌐 Frontend will be available at: http://localhost:8080")
    print("📖 API documentation: http://localhost:8000/docs")
    print("=" * 60)

    # Start backend in a separate thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # Give backend time to start
    print("⏳ Waiting for backend to start...")
    time.sleep(3)

    # Start frontend server in a separate thread
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()

    # Give frontend time to start
    print("⏳ Waiting for frontend to start...")
    time.sleep(2)

    # Open browser
    frontend_url = "http://localhost:8080"
    print(f"\n🎉 PromptQL is now running!")
    print(f"📡 Backend API:  http://localhost:8000")
    print(f"🌐 Frontend UI:  {frontend_url}")
    print(f"📖 API Docs:     http://localhost:8000/docs")
    print("\n💡 Tip: Keep this terminal running to maintain both services")
    print("   Press Ctrl+C to stop both servers\n")

    # Open browser after a brief delay
    time.sleep(1)
    try:
        webbrowser.open(frontend_url)
        print(f"🌐 Opened {frontend_url} in your default browser")
    except Exception as e:
        print(f"⚠️  Could not open browser automatically: {e}")
        print(f"   Please manually open: {frontend_url}")

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down PromptQL...")
        print("   Backend and frontend services will stop...")
        sys.exit(0)

if __name__ == "__main__":
    main()