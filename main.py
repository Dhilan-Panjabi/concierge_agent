"""
Main entry point for the Telegram Booking Bot.
"""
import asyncio
import logging
import sys
import os
from typing import Optional
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
import time

from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler as TelegramCommandHandler
from telegram.error import NetworkError, Conflict

from src.config.settings import Settings
from src.config.constants import ERROR_MESSAGES
from src.services.browser_service import BrowserService
from src.services.ai_service import AIService
from src.bot.handlers import MessageHandler
from src.bot.commands import CommandHandler
from src.bot.conversation import ConversationManager
from src.utils.message_utils import MessageUtils
from src.utils.browser_use_patch import apply_patches

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Apply patches for Railway compatibility
apply_patches()

# Global flag to indicate if the health check server is running
health_check_server_running = False
health_check_server = None

# Start a simple HTTP server for health checks immediately
def start_health_check_server():
    global health_check_server_running, health_check_server
    try:
        # First, check if the port is already in use (which would mean our start.py health check is running)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8080))
        sock.close()
        
        if result == 0:
            # Port is already in use, likely by the health check server from start.py
            logger.info("Port 8080 is already in use, assuming health check server is already running")
            health_check_server_running = True
            return
        
        # Also try connecting using 0.0.0.0
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # This might fail with permission error, but that's expected
            result = sock.connect_ex(('0.0.0.0', 8080))
            if result == 0 or result == 13:  # Success or permission error (which likely means the port is in use)
                logger.info("Port 8080 is in use by a process bound to 0.0.0.0, assuming health check server is already running")
                health_check_server_running = True
                sock.close()
                return
        except:
            # If we can't connect to 0.0.0.0, that's fine, continue
            pass
        finally:
            sock.close()
            
        # Otherwise, continue to start our own health check server
        class SimpleHealthCheckHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                logger.info(f"Health check request received: {self.path}")
                # Always respond with 200 OK regardless of the path
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
                logger.info("Health check responded with 200 OK")
            
            def log_message(self, format, *args):
                logger.info("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))
        
        # Start the server on port 8080
        health_check_server = HTTPServer(('0.0.0.0', 8080), SimpleHealthCheckHandler)
        logger.info("Health check server created successfully on port 8080")
        health_check_server_running = True
        logger.info("Starting health check server...")
        health_check_server.serve_forever()
    except Exception as e:
        logger.error(f"Error starting health check server: {e}", exc_info=True)

# Start the health check server in a separate thread immediately
health_check_thread = threading.Thread(target=start_health_check_server, daemon=True)
health_check_thread.start()
logger.info("Health check server thread started")

# Wait for the health check server to start
for _ in range(20):  # Try for up to 10 seconds
    if health_check_server_running:
        logger.info("Health check server is running")
        break
    logger.info("Waiting for health check server to start...")
    time.sleep(0.5)

# Skip the port test if we've already confirmed the health check server is running
if health_check_server_running:
    logger.info("Skipping port test as health check server is already confirmed running")
else:
    # Test if the port is actually open and listening
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', 8080))
            if result == 0:
                logger.info("Health check server port is open and listening")
                health_check_server_running = True
            else:
                # Try connecting to 0.0.0.0 as well
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                    s2.settimeout(1)
                    try:
                        result2 = s2.connect_ex(('0.0.0.0', 8080))
                        if result2 == 0 or result2 == 13:  # Success or permission error
                            logger.info("Health check server port is open on 0.0.0.0")
                            health_check_server_running = True
                        else:
                            logger.warning(f"Health check server port test on 0.0.0.0 returned code: {result2}")
                    except Exception as e:
                        logger.warning(f"Error testing health check server on 0.0.0.0: {e}")
                        
                # Even if both tests fail, consider the health check running if started by start.py
                if not health_check_server_running:
                    logger.warning("Health check server port tests failed, but continuing anyway as it might be handled by start.py")
                    health_check_server_running = True
    except Exception as e:
        logger.warning(f"Error testing health check server port: {e}")
        # Continue anyway, as the health check server might be running in start.py
        logger.info("Continuing despite port test error as health check might be handled by start.py")
        health_check_server_running = True


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check requests"""
    
    def do_GET(self):
        """Handle GET requests"""
        logger.info(f"Health check request received: {self.path}")
        # Always respond with 200 OK regardless of the path
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        logger.info("Health check responded with 200 OK")
    
    def log_message(self, format, *args):
        """Override to reduce log noise"""
        logger.info("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))


class BookingBot:
    """Main bot class that ties all components together"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BookingBot, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize bot and all its components"""
        if not self._initialized:
            try:
                # Initialize settings
                self.settings = Settings()

                # Initialize services
                self.browser_service = BrowserService(self.settings)
                self.ai_service = AIService(self.settings)

                # Initialize handlers
                self.message_handler = MessageHandler(
                    browser_service=self.browser_service,
                    ai_service=self.ai_service
                )
                self.command_handler = CommandHandler()

                # Initialize conversation manager
                self.conversation_manager = ConversationManager(
                    message_handler=self.message_handler,
                    command_handler=self.command_handler
                )

                # Initialize application
                self.application = Application.builder().token(self.settings.BOT_TOKEN).build()

                self._initialized = True
                logger.info("Bot components initialized successfully")

            except Exception as e:
                logger.critical(f"Failed to initialize bot: {e}", exc_info=True)
                sys.exit(1)

    async def initialize(self):
        """Async initialization for components that require an event loop"""
        try:
            # Nothing to initialize asynchronously at the moment
            # Browser will be initialized on first use
            pass
        except Exception as e:
            logger.error(f"Error in async initialization: {e}", exc_info=True)
            raise

    async def error_handler(self, update: Optional[Update], context: CallbackContext) -> None:
        """Global error handler for the bot"""
        try:
            if update and update.effective_user:
                user_id = update.effective_user.id
                logger.error(f"Error for user {user_id}: {context.error}")

                if isinstance(context.error, NetworkError):
                    await update.message.reply_text(ERROR_MESSAGES["timeout"])
                else:
                    await update.message.reply_text(ERROR_MESSAGES["general"])
            else:
                logger.error(f"Update caused error: {context.error}")

        except Exception as e:
            logger.error(f"Error in error handler: {e}", exc_info=True)

    async def health_check(self, update: Update, context: CallbackContext) -> None:
        """Health check endpoint for the webhook server"""
        await update.message.reply_text("Bot is running!")

    async def shutdown(self):
        """Gracefully shut down the bot and clean up resources"""
        try:
            logger.info("Shutting down bot and cleaning up resources...")
            
            # Clean up all browser instances
            await self.browser_service.cleanup()
            
            # Clear message data
            MessageUtils._user_data.clear()
            
            logger.info("Bot shutdown complete")
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}", exc_info=True)

    def start_health_check_server(self, port=8080):
        """Start a simple HTTP server for health checks"""
        try:
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            logger.info(f"Starting health check server on port {port}")
            
            # Run the server in a separate thread
            thread = threading.Thread(target=server.serve_forever)
            thread.daemon = True
            thread.start()
            
            return server
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}", exc_info=True)
            return None

    def run(self):
        """Run the bot in either polling or webhook mode"""
        try:
            # Add handlers
            self.application.add_handler(
                self.conversation_manager.get_conversation_handler()
            )
            
            # Add health check command
            self.application.add_handler(
                TelegramCommandHandler("health", self.health_check)
            )
            
            self.application.add_error_handler(self.error_handler)

            # Get webhook configuration from settings
            webhook_config = self.settings.get_webhook_config()
            use_webhook = webhook_config['use_webhook']
            
            # Initialize async components
            async def start():
                await self.initialize()
                
                if use_webhook:
                    webhook_url = webhook_config['webhook_url']
                    webhook_port = webhook_config['webhook_port']
                    webhook_path = webhook_config['webhook_path']
                    
                    if not webhook_url:
                        logger.error("WEBHOOK_URL is required for webhook mode")
                        sys.exit(1)
                    
                    # Start health check server on the same port as the webhook
                    # health_check_server = self.start_health_check_server(port=8080)
                    
                    # Configure webhook
                    webhook_url = f"{webhook_url}{webhook_path}"
                    logger.info(f"Starting bot in webhook mode at {webhook_url} on port {webhook_port}")
                    
                    # Register shutdown handler for graceful termination
                    import signal
                    
                    # Define signal handlers for graceful shutdown
                    async def signal_handler():
                        logger.info("Received termination signal, shutting down...")
                        # if health_check_server:
                        #     health_check_server.shutdown()
                        await self.shutdown()
                    
                    # Register signal handlers
                    self.application.add_signal_handler(signal.SIGINT, signal_handler)
                    self.application.add_signal_handler(signal.SIGTERM, signal_handler)
                    
                    # Start the application
                    await self.application.start()
                    await self.application.update_bot()
                    
                    # Add a custom webhook handler that also serves as a health check
                    from telegram.ext import CommandHandler
                    
                    # Define a simple health check handler
                    async def health_check_handler(update, context):
                        if update is None:  # Direct HTTP request
                            return True  # Return success for health checks
                        else:  # Telegram update
                            await update.message.reply_text("Bot is running!")
                            return True
                    
                    # Register the health check handler
                    self.application.add_handler(CommandHandler("healthcheck", health_check_handler))
                    
                    # Setup the webhook
                    await self.application.setup_webhook(
                        listen="0.0.0.0",
                        port=webhook_port,
                        url_path=webhook_path,
                        webhook_url=webhook_url
                    )
                    
                    # Start the webhook
                    await self.application.start_webhook(
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"]
                    )
                    
                    # Keep the app running
                    while True:
                        await asyncio.sleep(3600)  # Sleep for an hour
                else:
                    # Start the bot in polling mode
                    logger.info("Starting bot in polling mode...")
                    await self.application.initialize()
                    await self.application.start()
                    await self.application.updater.start_polling(drop_pending_updates=True)
                    
                    # Keep the app running
                    while True:
                        await asyncio.sleep(3600)  # Sleep for an hour
            
            # Run the async function
            asyncio.run(start())

        except Exception as e:
            logger.critical(f"Failed to start bot: {e}", exc_info=True)
            raise
        finally:
            # Only clear message data, don't cleanup browser
            MessageUtils._user_data.clear()
            logger.info("Message data cleared")


def main():
    """Main entry point"""
    # Set up event loop policy for Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Configure more verbose logging for debugging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.info("Starting application...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current directory: {os.getcwd()}")

    try:
        # Start the bot
        logger.info("Initializing bot...")
        bot = BookingBot()
        logger.info("Starting bot...")
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
