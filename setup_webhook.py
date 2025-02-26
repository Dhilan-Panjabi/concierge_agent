#!/usr/bin/env python
"""
Script to set up the webhook URL for the Telegram bot.
"""
import argparse
import logging
import os
import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def setup_webhook(token, webhook_url, webhook_path="/telegram/webhook"):
    """
    Set up the webhook URL for the Telegram bot.
    
    Args:
        token: Telegram bot token
        webhook_url: Base URL for the webhook
        webhook_path: Path for the webhook
    """
    # Construct the full webhook URL
    full_webhook_url = f"{webhook_url.rstrip('/')}{webhook_path}"
    
    # Construct the Telegram API URL
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    # Set up the webhook
    response = requests.post(
        api_url,
        json={
            "url": full_webhook_url,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "callback_query"]
        }
    )
    
    # Check the response
    if response.status_code == 200 and response.json().get("ok"):
        logger.info(f"Webhook set up successfully: {full_webhook_url}")
        return True
    else:
        logger.error(f"Failed to set up webhook: {response.text}")
        return False

def get_webhook_info(token):
    """
    Get information about the current webhook.
    
    Args:
        token: Telegram bot token
    """
    # Construct the Telegram API URL
    api_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    
    # Get the webhook info
    response = requests.get(api_url)
    
    # Check the response
    if response.status_code == 200 and response.json().get("ok"):
        webhook_info = response.json().get("result", {})
        logger.info(f"Current webhook info: {webhook_info}")
        return webhook_info
    else:
        logger.error(f"Failed to get webhook info: {response.text}")
        return None

def delete_webhook(token):
    """
    Delete the current webhook.
    
    Args:
        token: Telegram bot token
    """
    # Construct the Telegram API URL
    api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    
    # Delete the webhook
    response = requests.post(
        api_url,
        json={
            "drop_pending_updates": True
        }
    )
    
    # Check the response
    if response.status_code == 200 and response.json().get("ok"):
        logger.info("Webhook deleted successfully")
        return True
    else:
        logger.error(f"Failed to delete webhook: {response.text}")
        return False

def main():
    """Main entry point"""
    # Load environment variables
    load_dotenv()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Set up the webhook URL for the Telegram bot")
    parser.add_argument("--token", help="Telegram bot token")
    parser.add_argument("--webhook-url", help="Base URL for the webhook")
    parser.add_argument("--webhook-path", default="/telegram/webhook", help="Path for the webhook")
    parser.add_argument("--info", action="store_true", help="Get information about the current webhook")
    parser.add_argument("--delete", action="store_true", help="Delete the current webhook")
    args = parser.parse_args()
    
    # Get the token from arguments or environment variables
    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Telegram bot token is required")
        return
    
    # Check if we should get webhook info
    if args.info:
        get_webhook_info(token)
        return
    
    # Check if we should delete the webhook
    if args.delete:
        delete_webhook(token)
        return
    
    # Get the webhook URL from arguments or environment variables
    webhook_url = args.webhook_url or os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        logger.error("Webhook URL is required")
        return
    
    # Get the webhook path from arguments or environment variables
    webhook_path = args.webhook_path or os.environ.get("WEBHOOK_PATH", "/telegram/webhook")
    
    # Set up the webhook
    setup_webhook(token, webhook_url, webhook_path)

if __name__ == "__main__":
    main() 