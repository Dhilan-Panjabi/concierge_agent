"""
Message handlers for the Telegram bot.
"""
import logging
from typing import Optional, Dict

from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler

from src.services.browser_service import BrowserService
from src.services.ai_service import AIService
from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)

# Add conversation states
BROWSER_CLEANUP = 5  # New state for browser cleanup confirmation

class MessageHandler:
    """Handles all incoming messages and their processing"""

    def __init__(self, browser_service: BrowserService, ai_service: AIService):
        self.browser_service = browser_service
        self.ai_service = ai_service
        self.message_utils = MessageUtils()

    async def handle_user_message(self, update: Update, context: CallbackContext) -> Optional[int]:
        """
        Main message handler for user interactions.
        
        Args:
            update: Telegram update object
            context: Callback context
            
        Returns:
            Optional[int]: Conversation state or None
        """
        try:
            user_id = update.message.from_user.id
            user_message = update.message.text.lower()

            # Check if we're in cleanup confirmation state
            if context.user_data.get('awaiting_cleanup_confirmation'):
                return await self.handle_cleanup_confirmation(update, context, user_message)

            # Check for cleanup command
            if "done browsing" in user_message.lower():
                await update.message.reply_text(
                    "Are you done with browsing? This will close the current browser session. (yes/no)"
                )
                context.user_data['awaiting_cleanup_confirmation'] = True
                return BROWSER_CLEANUP

            # Initialize user history
            self.message_utils.init_user_history(user_id)

            # Store message in history
            self.message_utils.add_to_history(user_id, "user", user_message)

            # Check for booking intent
            if any(phrase in user_message for phrase in ["book it", "make a booking", "reserve"]):
                return await self.start_booking_flow(update, context)

            # Get intent classification
            intent = await self.ai_service.classify_intent(user_message, user_id)
            logger.info(f"Detected intent: {intent} for user {user_id}")

            # Handle different intents
            if intent == "1":  # General recommendations - Use GPT first
                return await self.handle_recommendation_intent(update, user_message, user_id)
            elif intent == "2":  # Real-time info needed - Use browser
                return await self.handle_search_intent(update, user_message, user_id)
            elif intent == "3":  # Direct booking
                return await self.start_booking_flow(update, context)
            else:
                return await self.handle_default_response(update, user_id)

        except Exception as e:
            logger.error(f"Error in handle_user_message: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_recommendation_intent(self, update: Update, user_message: str, user_id: int) -> int:
        """Handles recommendation-related intents using GPT first"""
        try:
            # First, get AI recommendations without browser
            initial_response = await self.ai_service.get_recommendations(user_message)
            await self.message_utils.send_long_message(update, initial_response)

            # Store in history
            self.message_utils.add_to_history(user_id, "assistant", initial_response)

            # Offer to check real-time availability
            follow_up = (
                "\n\nWould you like me to check real-time availability or current prices for any of these options? "
                "Just let me know which one you're interested in!"
            )
            await update.message.reply_text(follow_up)

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in handle_recommendation_intent: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_search_intent(self, update: Update, user_message: str, user_id: int) -> int:
        """Handles search-related intents requiring real-time data"""
        try:
            await update.message.reply_text("Let me check real-time availability...")

            # Execute browser search for real-time data
            result = await self.browser_service.execute_search(user_message)
            response = await self.ai_service.format_response(user_message, result)

            # Send response
            await self.message_utils.send_long_message(update, response)

            # Store in history
            self.message_utils.add_to_history(user_id, "assistant", response)

            # Offer booking if applicable
            if self.should_offer_booking(response):
                await self.send_booking_options(update)

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in handle_search_intent: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_cleanup_confirmation(self, update: Update, context: CallbackContext, user_message: str) -> int:
        """Handle browser cleanup confirmation"""
        context.user_data['awaiting_cleanup_confirmation'] = False
        
        if user_message.lower() in ['yes', 'y']:
            await self.browser_service.cleanup()
            await update.message.reply_text("Browser session closed. You can start a new search anytime!")
        else:
            await update.message.reply_text("Keeping the browser session active. You can continue searching!")
        
        return ConversationHandler.END

    @staticmethod
    async def handle_error(update: Update, user_id: int) -> None:
        """Handles errors in message processing"""
        error_message = "I encountered an error. Please try again."
        await update.message.reply_text(error_message)
        MessageUtils.add_to_history(user_id, "assistant", error_message)

    @staticmethod
    def should_offer_booking(response: str) -> bool:
        """Determines if booking options should be offered"""
        booking_indicators = ["available",
                              "book now", "reservation", "schedule"]
        return any(indicator in response.lower() for indicator in booking_indicators)

    @staticmethod
    async def send_booking_options(update: Update) -> None:
        """Sends booking options to user"""
        booking_options = (
            "\n\nI can help you in two ways:\n"
            "1. Say 'book it' and I'll make the booking for you automatically\n"
            "2. Use the links above to book directly yourself"
        )
        await update.message.reply_text(booking_options)
