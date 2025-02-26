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
import psutil
import datetime

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
        
        # Check if we can connect to port 8080 on 0.0.0.0
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('0.0.0.0', 8080))
            sock.close()
            
            if result == 0:
                logger.info("Port 8080 is already in use on 0.0.0.0, assuming health check server is running")
                health_check_server_running = True
                return
        except Exception as e:
            logger.info(f"Error checking 0.0.0.0:8080: {e}")
        
        # If we reach here, try to start our own health check server
        # But first, do a more direct check to avoid the "Address already in use" error
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('0.0.0.0', 8080))
            test_socket.close()
        except socket.error as e:
            logger.info(f"Cannot bind to port 8080: {e}")
            logger.info("Port is already in use, marking health check server as running")
            health_check_server_running = True
            return
            
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
        try:
            health_check_server = HTTPServer(('0.0.0.0', 8080), SimpleHealthCheckHandler)
            logger.info("Health check server created successfully on port 8080")
            health_check_server_running = True
            logger.info("Starting health check server...")
            health_check_server.serve_forever()
        except OSError as e:
            if "Address already in use" in str(e):
                logger.info("Port 8080 is already in use, marking health check server as running")
                health_check_server_running = True
            else:
                raise
    except Exception as e:
        logger.error(f"Error starting health check server: {e}", exc_info=True)
        # Even if we fail, mark as running to prevent endless retries
        health_check_server_running = True

# Start the health check server in a separate thread immediately
health_check_thread = threading.Thread(target=start_health_check_server, daemon=True)
health_check_thread.start()
logger.info("Health check server thread started")

# Set a maximum retry count instead of an endless loop
max_retries = 10
retry_count = 0

# Wait for the health check server to start or for max retries
while not health_check_server_running and retry_count < max_retries:
    logger.info("Waiting for health check server to start...")
    time.sleep(0.5)
    retry_count += 1

# If we hit max retries, assume the server is running anyway
if retry_count >= max_retries and not health_check_server_running:
    logger.warning("Reached maximum retries waiting for health check server. Continuing anyway.")
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
            # Log the bot username to confirm we're connected to the right bot
            me = await self.application.bot.get_me()
            logger.info(f"Bot connected successfully. Username: @{me.username}, ID: {me.id}")
            logger.info("Bot is ready to receive messages")
            
            # Nothing else to initialize asynchronously at the moment
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
                logger.error(f"Error for user {user_id}: {context.error}", exc_info=context.error)
                
                # Log more details about the update
                update_type = None
                if update.message:
                    update_type = "message"
                    content = update.message.text if update.message.text else "[non-text content]"
                    logger.error(f"Error occurred while processing message: '{content}'")
                elif update.callback_query:
                    update_type = "callback_query" 
                    content = update.callback_query.data
                    logger.error(f"Error occurred while processing callback query: '{content}'")
                
                logger.error(f"Error details - Update ID: {update.update_id}, Type: {update_type}")

                if isinstance(context.error, NetworkError):
                    await update.message.reply_text(ERROR_MESSAGES["timeout"])
                else:
                    await update.message.reply_text(ERROR_MESSAGES["general"])
            else:
                logger.error(f"Update caused error but no user information is available: {context.error}", exc_info=context.error)
                if update:
                    logger.error(f"Update ID: {update.update_id}, Update type: {type(update)}")

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
        # Check if the global health check server is already running
        global health_check_server_running
        if health_check_server_running:
            logger.info("Health check server is already running, not starting a new one")
            return None
            
        # Try to check if the port is already in use
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('0.0.0.0', port))
            test_socket.close()
        except socket.error:
            logger.info(f"Port {port} is already in use, not starting a new health check server")
            return None
        
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
            
            # Add a simple diagnostic command
            async def echo_command(update: Update, context: CallbackContext) -> None:
                """Simple command to echo back a message to confirm the bot is working"""
                logger.info(f"Received echo command from user {update.effective_user.id}")
                await update.message.reply_text(f"Echo: I received your command! Bot is working.")
            
            # Add a debug command for more detailed diagnostics
            async def debug_command(update: Update, context: CallbackContext) -> None:
                """Debug command to show detailed information about the bot's state"""
                logger.info(f"Received debug command from user {update.effective_user.id}")
                
                # Get bot info
                me = await self.application.bot.get_me()
                webhook_info = await self.application.bot.get_webhook_info()
                
                # Check health check server status
                health_status = "Running" if health_check_server_running else "Not running"
                
                # Get memory usage
                try:
                    process = psutil.Process(os.getpid())
                    memory_usage = process.memory_info().rss / 1024 / 1024  # in MB
                    memory_info = f"{memory_usage:.2f} MB"
                except Exception as e:
                    logger.error(f"Error getting memory usage: {e}")
                    memory_info = "Error getting memory usage"
                
                # Get uptime
                try:
                    start_time = datetime.datetime.strptime(
                        os.environ.get('APP_START_TIME', time.strftime('%Y-%m-%d %H:%M:%S')),
                        '%Y-%m-%d %H:%M:%S'
                    )
                    uptime = datetime.datetime.now() - start_time
                except Exception as e:
                    logger.error(f"Error calculating uptime: {e}")
                    uptime = "Unknown"
                
                # Check active users
                active_users = len(MessageUtils._user_data)
                
                # Compile debug information
                debug_info = [
                    f"🤖 Bot: {me.first_name} (@{me.username})",
                    f"🆔 Bot ID: {me.id}",
                    f"📊 Webhook URL: {webhook_info.url or 'None'}",
                    f"📡 Pending updates: {webhook_info.pending_update_count}",
                    f"🏥 Health check server: {health_status}",
                    f"🔄 Mode: {'Webhook' if webhook_info.url else 'Polling'}",
                    f"⚙️ Railway instance ID: {os.environ.get('RAILWAY_REPLICA_ID', 'Not on Railway')}",
                    f"🌐 Environment: {'Railway' if os.environ.get('RAILWAY_SERVICE_ID') else 'Local'}",
                    f"⏱️ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"⏳ Uptime: {uptime}",
                    f"💾 Memory usage: {memory_info}",
                    f"👥 Active users: {active_users}",
                    f"🔍 Python version: {sys.version.split()[0]}"
                ]
                
                try:
                    await update.message.reply_text("\n".join(debug_info))
                except Exception as e:
                    logger.error(f"Error sending debug info: {e}")
                    # Try sending a shorter version
                    await update.message.reply_text(f"Bot is running as {me.username}. Error showing full debug: {str(e)}")
            
            # Register the commands
            self.application.add_handler(
                TelegramCommandHandler("echo", echo_command)
            )
            self.application.add_handler(
                TelegramCommandHandler("debug", debug_command)
            )
            logger.info("Added diagnostic command handlers")
            
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
                    
                    # Log webhook and health check server ports for debugging
                    logger.info(f"Webhook configuration: URL={webhook_url}, Port={webhook_port}, Path={webhook_path}")
                    logger.info(f"Health check server is running: {health_check_server_running}")
                    logger.info(f"Environment PORT value: {os.environ.get('PORT', 'Not set')}")
                    
                    if not webhook_url:
                        logger.error("WEBHOOK_URL is required for webhook mode")
                        sys.exit(1)
                    
                    # Since we're on Railway with health check server already running,
                    # We'll use polling mode but maintain the webhook URL for external access
                    logger.info("Running on Railway with health check server. Using polling mode instead of webhook.")
                    
                    # Check if this is a multi-instance deployment on Railway
                    railway_instance_id = os.environ.get('RAILWAY_REPLICA_ID')
                    railway_service_id = os.environ.get('RAILWAY_SERVICE_ID')
                    
                    logger.info(f"Railway instance info - Replica ID: {railway_instance_id}, Service ID: {railway_service_id}")
                    
                    # When running on Railway, treat any instance as the primary
                    # This is because Railway uses UUIDs for replica IDs, not sequential numbers
                    # Since our railway.json is configured for only 1 replica, any running instance is primary
                    is_primary_instance = True  # When running on Railway with 1 replica, always poll for updates
                    logger.info(f"Is primary instance that should poll for updates: {is_primary_instance}")
                    
                    # Configure signals for graceful shutdown
                    import signal
                    
                    # Define signal handlers for graceful shutdown
                    async def signal_handler():
                        logger.info("Received termination signal, shutting down...")
                        await self.shutdown()
                    
                    # Register signal handlers
                    loop = asyncio.get_running_loop()
                    loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(signal_handler()))
                    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(signal_handler()))
                    
                    # Start the application in polling mode
                    await self.application.initialize()
                    await self.application.start()
                    
                    # Delete any existing webhook before starting polling
                    logger.info("Deleting any existing webhook before starting polling")
                    await self.application.bot.delete_webhook()
                    
                    # Check if there are multiple instances running
                    try:
                        # Get webhook info to check if another instance has set a webhook
                        webhook_info = await self.application.bot.get_webhook_info()
                        if webhook_info.url:
                            logger.warning(f"Another instance has set a webhook at {webhook_info.url}. This instance will not poll for updates.")
                            # Just keep the application alive without polling
                            while True:
                                await asyncio.sleep(60)
                    except Exception as e:
                        logger.error(f"Error checking webhook info: {e}", exc_info=True)
                    
                    # Only poll for updates on the primary instance
                    if is_primary_instance:
                        try:
                            # Use the built-in polling mechanism which is more reliable
                            logger.info("Starting to poll for updates on primary instance using built-in method...")
                            
                            # Double-check there are no webhooks
                            webhook_info = await self.application.bot.get_webhook_info()
                            logger.info(f"Current webhook status - URL: {webhook_info.url}, Pending updates: {webhook_info.pending_update_count}")
                            
                            if webhook_info.url:
                                logger.info("Deleting existing webhook before polling")
                                await self.application.bot.delete_webhook()
                                webhook_info = await self.application.bot.get_webhook_info()
                                logger.info(f"Webhook status after deletion - URL: {webhook_info.url}")
                            
                            # Configure the updater with proper settings
                            logger.info("Starting polling with application.updater.start_polling()")
                            try:
                                await self.application.updater.start_polling(
                                    drop_pending_updates=True,
                                    allowed_updates=["message", "callback_query", "inline_query"],
                                    close_loop=False  # We'll manage the loop ourselves
                                )
                                logger.info("Polling started successfully. Bot is now listening for messages.")
                                
                                # Log telemetry info to confirm connection
                                me = await self.application.bot.get_me()
                                logger.info(f"Connected to Telegram as {me.first_name} (@{me.username})")
                                logger.info("Waiting for messages from users...")
                            except Exception as polling_error:
                                logger.error(f"Error starting polling: {polling_error}", exc_info=True)
                                # Try fallback method
                                logger.info("Trying manual polling as fallback")
                                # Keep the loop running
                                offset = 0
                                while True:
                                    try:
                                        updates = await self.application.bot.get_updates(offset=offset, timeout=30)
                                        logger.info(f"Received {len(updates)} updates")
                                        for update in updates:
                                            offset = update.update_id + 1
                                            await self.application.process_update(update)
                                        await asyncio.sleep(1)
                                    except Exception as e:
                                        logger.error(f"Error in fallback polling: {e}", exc_info=True)
                                        await asyncio.sleep(5)
                            
                            # Keep the main loop running
                            logger.info("Polling started successfully. Bot is now listening for messages.")
                            logger.info("Waiting for messages from users...")
                            while True:
                                try:
                                    await asyncio.sleep(60)  # Just keep the loop alive
                                    # Check bot status every minute
                                    try:
                                        me = await self.application.bot.get_me()
                                        logger.debug(f"Bot is still connected as {me.username}")
                                    except Exception as check_error:
                                        logger.error(f"Error checking bot status: {check_error}")
                                        # Try to reconnect
                                        logger.info("Attempting to reconnect...")
                                        try:
                                            await self.application.updater.start_polling(
                                                drop_pending_updates=False,  # Keep existing updates
                                                allowed_updates=["message", "callback_query", "inline_query"],
                                                close_loop=False
                                            )
                                            logger.info("Reconnected successfully")
                                        except Exception as reconnect_error:
                                            logger.error(f"Failed to reconnect: {reconnect_error}")
                                except Exception as loop_error:
                                    logger.error(f"Error in main loop: {loop_error}")
                                    # Don't exit the loop no matter what
                                    await asyncio.sleep(10)  # Wait before next iteration
                        except Exception as e:
                            logger.error(f"Critical error in polling setup: {e}", exc_info=True)
                            raise
                    else:
                        # Non-primary instances should just stay alive for health checks but not poll
                        logger.info("This is not the primary instance. Health check server active, but not polling for updates.")
                        while True:
                            await asyncio.sleep(60)  # Just keep the process alive
                else:
                    # Start the bot in polling mode
                    logger.info("Starting bot in polling mode...")
                    await self.application.initialize()
                    await self.application.start()
                    
                    try:
                        # Make sure any webhook is deleted
                        webhook_info = await self.application.bot.get_webhook_info()
                        logger.info(f"Current webhook status - URL: {webhook_info.url}, Pending updates: {webhook_info.pending_update_count}")
                        
                        if webhook_info.url:
                            logger.info("Deleting existing webhook before polling")
                            await self.application.bot.delete_webhook()
                        
                        # Use the built-in polling method which is more reliable
                        logger.info("Starting polling with built-in method...")
                        await self.application.updater.start_polling(
                            drop_pending_updates=True,
                            allowed_updates=["message", "callback_query", "inline_query"]
                        )
                        
                        # Log telemetry info to confirm connection
                        me = await self.application.bot.get_me()
                        logger.info(f"Connected to Telegram as {me.first_name} (@{me.username})")
                        
                        # Keep the app running
                        logger.info("Polling started successfully. Bot is now listening for messages.")
                        logger.info("Waiting for messages from users...")
                        while True:
                            await asyncio.sleep(3600)  # Sleep for an hour
                    except Exception as e:
                        logger.error(f"Error in polling mode: {e}", exc_info=True)
                        raise
            
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
    
    # Set and log the application start time
    start_time = time.strftime('%Y-%m-%d %H:%M:%S')
    os.environ['APP_START_TIME'] = start_time
    logger.info(f"Application start time: {start_time}")

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
