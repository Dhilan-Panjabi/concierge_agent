"""
Conversation management for the Telegram bot.
"""
import logging
from typing import Dict, Any
import json

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
PROFILE_NAME, PROFILE_EMAIL, PROFILE_PHONE = range(10, 13)


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
                CommandHandler("menu", self.command_handler.menu_command),
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
                        self.message_handler.handle_cleanup_confirmation
                    )
                ],
                # Profile management states
                PROFILE_NAME: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_profile_input
                    )
                ],
                PROFILE_EMAIL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_profile_input
                    )
                ],
                PROFILE_PHONE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.handle_profile_input
                    )
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.command_handler.cancel_command),
                MessageHandler(
                    filters.Regex("^(📝 Update Profile|👤 View Profile|🔄 Use Saved Profile for Booking|❌ Clear Saved Profile)$"),
                    self.message_handler.handle_menu_choice
                )
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
            message = update.message.text
            current_step = context.user_data.get('booking_step', 0)

            # Define field names and their corresponding states
            fields = ['name', 'email', 'phone']
            next_states = [EMAIL, PHONE, CONFIRMATION_CODE]
            next_prompts = [
                "Great! Now, what's your email?",
                "Perfect! And your phone number?",
                "Thanks! I'll now proceed with the booking."
            ]

            # Store the current input
            await self.message_utils.set_booking_info(user_id, fields[current_step], message)

            # Move to next step
            next_step = current_step + 1
            context.user_data['booking_step'] = next_step

            if next_step < len(fields):
                await update.message.reply_text(next_prompts[current_step])
                return next_states[current_step]
            else:
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

    async def complete_booking(self, update: Update, context: CallbackContext) -> int:
        """Completes the booking process"""
        try:
            user_id = update.message.from_user.id
            booking_info = await self.message_utils.get_booking_info(user_id)
            booking_context = context.user_data.get('booking_context', {})
            
            # Get chat history to extract booking details
            chat_history = await self.message_utils.get_user_history(user_id)
            
            # Find the last search result containing hotel/restaurant details
            search_details = None
            for msg in reversed(list(chat_history)):  # Convert to list before reversing
                if msg['role'] == 'assistant' and ('Room Types & Prices' in msg['content'] or 'Availability' in msg['content']):
                    search_details = msg['content']
                    break
            
            if not search_details:
                await update.message.reply_text("I couldn't find the previous search details. Please try searching again.")
                return ConversationHandler.END

            # Create a detailed booking instruction using all available information
            booking_instruction = (
                f"Using the following search results:\n\n"
                f"{search_details}\n\n"
                f"Make a booking with these customer details:\n"
                f"- Name: {booking_info.get('name')}\n"
                f"- Email: {booking_info.get('email')}\n"
                f"- Phone: {booking_info.get('phone')}\n\n"
                f"Please proceed with the booking using the provided booking link and enter all the customer information."
            )

            # Execute the booking
            await update.message.reply_text("Processing your booking...")
            result = await self.message_handler.browser_service.execute_search(
                booking_instruction,
                task_type="booking",
                user_id=user_id
            )

            # Format and send response with user context
            response = await self.message_handler.ai_service.format_response("Make booking", result, user_id)
            await self.message_utils.send_long_message(update, response)

            # Clear booking info
            await self.message_utils.clear_booking_info(user_id)
            context.user_data['booking_step'] = 0
            context.user_data.pop('booking_context', None)
            context.user_data.get('context', {}).pop('last_search', None)

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error completing booking: {e}", exc_info=True)
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

    async def handle_profile_input(self, update: Update, context: CallbackContext) -> int:
        """Handles profile information input"""
        try:
            user_id = update.message.from_user.id
            message = update.message.text
            current_state = context.user_data.get('profile_step', PROFILE_NAME)

            # Define field names and their corresponding states
            fields = ['name', 'email', 'phone']
            next_states = [PROFILE_EMAIL, PROFILE_PHONE, ConversationHandler.END]
            next_prompts = [
                "Great! Now enter your email:",
                "Perfect! Finally, enter your phone number:",
                "Profile updated successfully! ✅"
            ]

            # Get current field index
            field_index = current_state - PROFILE_NAME

            # Store the current input
            await self.message_utils.set_user_profile(user_id, fields[field_index], message)

            # Send next prompt or finish
            await update.message.reply_text(next_prompts[field_index])

            if field_index < len(fields) - 1:
                # Move to next field
                context.user_data['profile_step'] = next_states[field_index]
                return next_states[field_index]
            else:
                # Clear profile step and end conversation
                context.user_data.pop('profile_step', None)
                return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in handle_profile_input: {e}", exc_info=True)
            await self.message_handler.handle_error(update, user_id)
            return ConversationHandler.END
