"""
Command handlers for the Telegram bot.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import CallbackContext, ConversationHandler

from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)

# Profile states
PROFILE_NAME, PROFILE_EMAIL, PROFILE_PHONE = range(10, 13)

class CommandHandler:
    """Handles all bot commands"""

    def __init__(self):
        self.message_utils = MessageUtils()

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

    async def menu_command(self, update: Update, context: CallbackContext) -> None:
        """Handles the /menu command"""
        keyboard = [
            [KeyboardButton("📝 Update Profile")],
            [KeyboardButton("👤 View Profile")],
            [KeyboardButton("🔄 Use Saved Profile for Booking")],
            [KeyboardButton("❌ Clear Saved Profile")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            "What would you like to do?",
            reply_markup=reply_markup
        )

    async def handle_menu_choice(self, update: Update, context: CallbackContext) -> int:
        """Handles menu button selections"""
        choice = update.message.text
        user_id = update.message.from_user.id

        if choice == "📝 Update Profile":
            await update.message.reply_text("Please enter your name:")
            return PROFILE_NAME
            
        elif choice == "👤 View Profile":
            profile = self.message_utils.get_user_profile(user_id)
            if profile:
                profile_text = (
                    "Your saved profile:\n"
                    f"Name: {profile.get('name', 'Not set')}\n"
                    f"Email: {profile.get('email', 'Not set')}\n"
                    f"Phone: {profile.get('phone', 'Not set')}"
                )
            else:
                profile_text = "No profile saved. Use 'Update Profile' to set your information."
            
            await update.message.reply_text(profile_text)
            return ConversationHandler.END
            
        elif choice == "🔄 Use Saved Profile for Booking":
            profile = self.message_utils.get_user_profile(user_id)
            if profile and all(profile.get(k) for k in ['name', 'email', 'phone']):
                # Copy profile to booking info
                for key, value in profile.items():
                    self.message_utils.set_booking_info(user_id, key, value)
                await update.message.reply_text("Profile loaded for booking! ✅")
            else:
                await update.message.reply_text("Please set up your profile first using 'Update Profile'")
            return ConversationHandler.END
            
        elif choice == "❌ Clear Saved Profile":
            self.message_utils.clear_user_profile(user_id)
            await update.message.reply_text("Profile cleared! 🗑️")
            return ConversationHandler.END

    async def handle_profile_input(self, update: Update, context: CallbackContext) -> int:
        """Handles profile information input"""
        user_id = update.message.from_user.id
        message = update.message.text
        current_state = context.user_data.get('profile_step', PROFILE_NAME)

        if current_state == PROFILE_NAME:
            self.message_utils.set_user_profile(user_id, 'name', message)
            await update.message.reply_text("Great! Now enter your email:")
            context.user_data['profile_step'] = PROFILE_EMAIL
            return PROFILE_EMAIL
            
        elif current_state == PROFILE_EMAIL:
            self.message_utils.set_user_profile(user_id, 'email', message)
            await update.message.reply_text("Perfect! Finally, enter your phone number:")
            context.user_data['profile_step'] = PROFILE_PHONE
            return PROFILE_PHONE
            
        elif current_state == PROFILE_PHONE:
            self.message_utils.set_user_profile(user_id, 'phone', message)
            await update.message.reply_text("Profile updated successfully! ✅")
            context.user_data.pop('profile_step', None)
            return ConversationHandler.END

    @staticmethod
    async def help_command(update: Update, context: CallbackContext) -> None:
        """Handles the /help command"""
        help_message = (
            "Here's how I can help you:\n\n"
            "1. Search for places/events\n"
            "2. Check real-time availability\n"
            "3. Make bookings\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/menu - Open profile management menu\n"
            "/help - Show this help message\n"
            "/cancel - Cancel current operation\n\n"
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
