"""
Command handlers for the Telegram bot.
"""
import logging
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles all bot commands"""

    @staticmethod
    async def start_command(update: Update, context: CallbackContext) -> None:
        """
        Handles the /start command.
        
        Args:
            update: Telegram update object
            context: Callback context
        """
        welcome_message = (
            "Hey! I'm your booking assistant. 👋\n\n"
            "I can help you with:\n"
            "• Restaurant recommendations 🍽️\n"
            "• Checking availability 📅\n"
            "• Making reservations ✅\n\n"
            "What would you like to do?"
        )
        await update.message.reply_text(welcome_message)

    @staticmethod
    async def help_command(update: Update, context: CallbackContext) -> None:
        """Handles the /help command"""
        help_message = (
            "Here's how I can help you:\n\n"
            "1. Search for places/events\n"
            "2. Check real-time availability\n"
            "3. Make bookings\n\n"
            "Just tell me what you're looking for!"
        )
        await update.message.reply_text(help_message)

    @staticmethod
    async def cancel_command(update: Update, context: CallbackContext) -> int:
        """Handles the /cancel command"""
        await update.message.reply_text(
            "Current operation cancelled. What else can I help you with?"
        )
        return ConversationHandler.END
