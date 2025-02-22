"""
Conversation management for the Telegram bot.
"""
import logging
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)

from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)

# Conversation states
NAME, EMAIL, PHONE, CONFIRMATION_CODE, BROWSER_CLEANUP = range(5)


class ConversationManager:
    """Manages conversation flows and states"""

    def __init__(self, message_handler, command_handler):
        self.message_handler = message_handler
        self.command_handler = command_handler
        self.message_utils = MessageUtils()

    def get_conversation_handler(self) -> ConversationHandler:
        """
        Creates and returns the main conversation handler.
        
        Returns:
            ConversationHandler: Configured conversation handler
        """
        return ConversationHandler(
            entry_points=[
                CommandHandler("start", self.command_handler.start_command),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self.message_handler.handle_user_message
                )
            ],
            states={
                NAME: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_booking_info
                    )
                ],
                EMAIL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_booking_info
                    )
                ],
                PHONE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_booking_info
                    )
                ],
                CONFIRMATION_CODE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_confirmation_code
                    )
                ],
                BROWSER_CLEANUP: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.message_handler.handle_user_message
                    )
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.command_handler.cancel_command)
            ],
        )

    async def handle_booking_info(self, update: Update, context: CallbackContext) -> int:
        """
        Handles the collection of booking information.
        
        Args:
            update: Telegram update object
            context: Callback context
            
        Returns:
            int: Next conversation state
        """
        try:
            user_id = update.message.from_user.id
            current_state = context.user_data.get('booking_step', 0)

            # Store the current input
            field_names = ['name', 'email', 'phone']
            self.message_utils.store_booking_info(
                user_id,
                field_names[current_state],
                update.message.text
            )

            # Move to next state
            next_state = current_state + 1
            if next_state < len(field_names):
                prompt_messages = [
                    "Great! Now, what's your email?",
                    "Perfect! And your phone number?"
                ]
                await update.message.reply_text(prompt_messages[next_state - 1])
                context.user_data['booking_step'] = next_state
                return [EMAIL, PHONE][next_state - 1]

            return await self.complete_booking(update, context)

        except Exception as e:
            logger.error(f"Error in handle_booking_info: {e}", exc_info=True)
            await self.message_handler.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_confirmation_code(
        self,
        update: Update,
        context: CallbackContext
    ) -> int:
        """Handles confirmation code verification"""
        try:
            user_id = update.message.from_user.id
            confirmation_code = update.message.text

            # Verify confirmation code logic here
            if self.verify_confirmation_code(confirmation_code):
                await update.message.reply_text(
                    "Great! Your booking is confirmed. Enjoy!"
                )
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "Invalid confirmation code. Please try again."
                )
                return CONFIRMATION_CODE

        except Exception as e:
            logger.error(
                f"Error in handle_confirmation_code: {e}", exc_info=True)
            await self.message_handler.handle_error(update, user_id)
            return ConversationHandler.END

    @staticmethod
    def verify_confirmation_code(code: str) -> bool:
        """
        Verifies the confirmation code.
        
        Args:
            code: Confirmation code to verify
            
        Returns:
            bool: True if code is valid
        """
        # Add your confirmation code verification logic here
        return len(code) == 6 and code.isdigit()
