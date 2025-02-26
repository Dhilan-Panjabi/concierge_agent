#!/usr/bin/env python
"""
Simple health check script for Railway.
"""
import sys
import requests
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_health():
    """Check if the health check endpoint is responding."""
    try:
        logger.info("Checking health of application...")
        response = requests.get("http://localhost:8080/telegram/webhook", timeout=5)
        logger.info(f"Health check response: {response.status_code}")
        
        if response.status_code == 200:
            logger.info("Health check passed!")
            return True
        else:
            logger.error(f"Health check failed with status code: {response.status_code}")
            return False
    except requests.RequestException as e:
        logger.error(f"Health check failed with exception: {e}")
        return False

if __name__ == "__main__":
    if check_health():
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Failure 