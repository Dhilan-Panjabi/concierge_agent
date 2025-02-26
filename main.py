"""
Main entry point for the Telegram Booking Bot.
"""
import asyncio
import logging
import sys
from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackContext
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

    def run(self):
        """Run the bot"""
        try:
            # Add handlers
            self.application.add_handler(
                self.conversation_manager.get_conversation_handler()
            )
            self.application.add_error_handler(self.error_handler)

            # Start the bot
            logger.info("Starting bot...")
            
            # Run the application
            self.application.run_polling(drop_pending_updates=True)

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

    try:
        bot = BookingBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
