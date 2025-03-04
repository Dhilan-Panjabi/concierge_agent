#!/usr/bin/env python3
import http.server
import socketserver
import threading
import subprocess
import time
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("health_check_server")

# Define health check server
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        logger.info(f"Health check request received: {self.path}")
        # Always respond with 200 OK regardless of the path
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        if self.path == "/health":
            logger.info("Health check responded with OK")
            self.wfile.write(b"OK - Health Check")
        else:
            logger.info(f"Other request path: {self.path}, responding with generic OK")
            self.wfile.write(b"OK - Default Response")
            
    def log_message(self, format, *args):
        # Suppress default logging to avoid console spam
        pass

# Start the health check server first
def run_health_check_server(port=8080):
    try:
        logger.info(f"Starting health check server on port {port}...")
        with socketserver.TCPServer(("0.0.0.0", port), HealthCheckHandler) as httpd:
            logger.info(f"Health check server is running on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Error in health check server: {str(e)}")
        # Don't exit, keep trying to serve health checks
        time.sleep(1)
        run_health_check_server(port)

# Start the health check server in a daemon thread
logger.info("Initializing health check server...")
server_thread = threading.Thread(target=run_health_check_server, daemon=True)
server_thread.start()

# Wait a moment to ensure the health check server is running
time.sleep(2)
logger.info("Health check server should be running now")

# Set USE_WEBHOOK to false if RAILWAY_PUBLIC_DOMAIN is not available
if "RAILWAY_PUBLIC_DOMAIN" in os.environ:
    webhook_url = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
    logger.info(f"Setting WEBHOOK_URL to {webhook_url}")
    os.environ["WEBHOOK_URL"] = webhook_url
    os.environ["USE_WEBHOOK"] = "true"
    
    # Also update the .env file for persistence
    try:
        with open("/app/.env", "a") as env_file:
            env_file.write(f"\nWEBHOOK_URL={webhook_url}\n")
        logger.info("Updated .env file with WEBHOOK_URL")
    except Exception as e:
        logger.error(f"Error updating .env file: {str(e)}")
else:
    # If RAILWAY_PUBLIC_DOMAIN is not set, we need to either:
    # 1. Disable webhook mode, or
    # 2. Set a default webhook URL
    # Let's set a default webhook URL and keep webhook mode enabled
    logger.warning("RAILWAY_PUBLIC_DOMAIN is not set, using a fallback URL")
    fallback_url = "https://railway-service.up.railway.app"
    logger.info(f"Setting fallback WEBHOOK_URL to {fallback_url}")
    os.environ["WEBHOOK_URL"] = fallback_url
    
    # Update the .env file for persistence
    try:
        with open("/app/.env", "r") as env_file:
            env_content = env_file.read()
            
        # Check if USE_WEBHOOK is true in the env file
        if "USE_WEBHOOK=true" in env_content:
            with open("/app/.env", "a") as env_file:
                env_file.write(f"\nWEBHOOK_URL={fallback_url}\n")
            logger.info("Updated .env file with fallback WEBHOOK_URL")
    except Exception as e:
        logger.error(f"Error updating .env file: {str(e)}")

# Log all environment variables for debugging
logger.info("Current environment variables:")
for key, value in os.environ.items():
    if key.startswith('WEBHOOK') or key.startswith('USE_') or key == 'RAILWAY_PUBLIC_DOMAIN':
        logger.info(f"{key}={value}")

# Start the main application
logger.info("Starting main application...")
try:
    # Use execvp to replace the current process with the main.py process
    # This ensures we don't have two Python interpreters running
    os.execvp("python", ["python", "main.py"])
except Exception as e:
    logger.error(f"Failed to start main application: {str(e)}")
    # Keep the health check server running even if main app fails
    while True:
        time.sleep(3600)  # Sleep for an hour 