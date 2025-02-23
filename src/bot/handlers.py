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
NAME, EMAIL, PHONE, CONFIRMATION_CODE, BROWSER_CLEANUP = range(5)  # Updated states
PROFILE_NAME, PROFILE_EMAIL, PROFILE_PHONE = range(10, 13)  # Profile states

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
            user_message = update.message.text

            # Initialize user history first
            await self.message_utils.init_user_history(user_id)

            # Handle menu choices first
            if user_message in ["📝 Update Profile", "👤 View Profile", "🔄 Use Saved Profile for Booking", "❌ Clear Saved Profile"]:
                return await self.handle_menu_choice(update, context)

            # Show greeting only for the very first message
            if await self.message_utils.should_show_greeting(user_id):
                greeting = """Hey! I'm your booking assistant. 👋

I can help you with:
• Restaurant recommendations 🍽️
• Checking availability 📅
• Making reservations ✅

What would you like to do?"""
                await update.message.reply_text(greeting)
                # Store the greeting in history to avoid showing it again
                await self.message_utils.add_to_history(user_id, "assistant", greeting)
                return ConversationHandler.END

            # Convert to lowercase for processing
            user_message = user_message.lower()
            
            # Store message in history
            await self.message_utils.add_to_history(user_id, "user", user_message)

            # Get intent classification
            intent = await self.ai_service.classify_intent(user_message, user_id)
            logger.info(f"Detected intent: {intent} for user {user_id}")

            # Handle different intents
            if intent == "4":  # Profile management
                return await self.handle_menu_choice(update, context)
            elif intent == "1":  # General recommendations
                return await self.handle_recommendation_intent(update, user_message, user_id)
            elif intent == "2":  # Real-time info needed
                return await self.handle_search_intent(update, user_message, user_id, context)
            elif intent == "3":  # Direct booking
                return await self.start_booking_flow(update, context)
            else:
                return await self.handle_default_response(update, user_id)

        except Exception as e:
            logger.error(f"Error in handle_user_message: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_menu_choice(self, update: Update, context: CallbackContext) -> int:
        """Handles menu button selections"""
        choice = update.message.text
        user_id = update.message.from_user.id

        try:
            if choice == "📝 Update Profile":
                await update.message.reply_text("Please enter your name:")
                return PROFILE_NAME
                
            elif choice == "👤 View Profile":
                profile = await self.message_utils.get_user_profile(user_id)
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
                profile = await self.message_utils.get_user_profile(user_id)
                if profile and all(profile.get(k) for k in ['name', 'email', 'phone']):
                    # Copy profile to booking info
                    for key, value in profile.items():
                        await self.message_utils.set_booking_info(user_id, key, value)
                    await update.message.reply_text("Profile loaded for booking! ✅")
                else:
                    await update.message.reply_text("Please set up your profile first using 'Update Profile'")
                return ConversationHandler.END
                
            elif choice == "❌ Clear Saved Profile":
                await self.message_utils.clear_user_profile(user_id)
                await update.message.reply_text("Profile cleared! 🗑️")
                return ConversationHandler.END

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in handle_menu_choice: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_recommendation_intent(self, update: Update, user_message: str, user_id: int) -> int:
        """Handles recommendation-related intents using GPT first"""
        try:
            # First, get AI recommendations without browser
            initial_response = await self.ai_service.get_recommendations(user_message)
            await self.message_utils.send_long_message(update, initial_response)

            # Store in history
            await self.message_utils.add_to_history(user_id, "assistant", initial_response)

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

    async def handle_search_intent(self, update: Update, user_message: str, user_id: int, context: CallbackContext) -> int:
        """Handles search-related intents requiring real-time data"""
        try:
            await update.message.reply_text("Let me check real-time availability...")

            # Get conversation history to build context
            history = await self.message_utils.get_user_history(user_id)
            
            # Build context from history, focusing on most recent messages
            search_context = {
                'hotel': None,
                'location': None,
                'check_in': None,
                'check_out': None
            }
            
            # Extract context from recent history (last 3 messages)
            recent_history = history[-3:]
            for msg in reversed(recent_history):  # Process from most recent to older
                content = msg['content'].lower()
                
                # Look for hotel mentions in the most recent context
                if 'hotel principe di savoia' in content.lower():
                    search_context['hotel'] = 'Hotel Principe di Savoia'
                    search_context['location'] = 'Milan, Italy'
                elif 'bulgari hotel milano' in content.lower():
                    search_context['hotel'] = 'Bulgari Hotel Milano'
                    search_context['location'] = 'Milan, Italy'
                elif 'excelsior hotel gallia' in content.lower():
                    search_context['hotel'] = 'Excelsior Hotel Gallia'
                    search_context['location'] = 'Milan, Italy'
                elif 'mandarin oriental, milan' in content.lower():
                    search_context['hotel'] = 'Mandarin Oriental'
                    search_context['location'] = 'Milan, Italy'

            # Parse dates from the current message
            if 'next weekend' in user_message.lower():
                from datetime import datetime, timedelta
                today = datetime.now()
                days_until_saturday = (5 - today.weekday()) % 7 + 7  # Get next Saturday
                next_saturday = today + timedelta(days=days_until_saturday)
                next_sunday = next_saturday + timedelta(days=1)
                search_context['check_in'] = next_saturday.strftime('%Y-%m-%d')
                search_context['check_out'] = next_sunday.strftime('%Y-%m-%d')

            # Build a detailed search query
            if search_context['hotel'] and search_context['location']:
                search_query = f"Check availability and pricing for {search_context['hotel']} in {search_context['location']} "
                if search_context['check_in'] and search_context['check_out']:
                    search_query += f"from {search_context['check_in']} to {search_context['check_out']}. "
                search_query += "Include room types, rates, and amenities."
            else:
                # If no specific hotel found in context, use the original message
                search_query = user_message

            # Execute browser search with detailed query
            result = await self.browser_service.execute_search(search_query)
            response = await self.ai_service.format_response(search_query, result)

            # Store search context in user data
            if 'context' not in context.user_data:
                context.user_data['context'] = {}
            context.user_data['context']['last_search'] = {
                'query': search_query,
                'result': response,
                'hotel': search_context['hotel'],
                'location': search_context['location'],
                'check_in': search_context['check_in'],
                'check_out': search_context['check_out']
            }

            # Send response
            await self.message_utils.send_long_message(update, response)

            # Store in history
            await self.message_utils.add_to_history(user_id, "assistant", response)

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
        await MessageUtils().add_to_history(user_id, "assistant", error_message)

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

    async def start_booking_flow(self, update: Update, context: CallbackContext) -> int:
        """Starts the booking information collection flow"""
        try:
            user_id = update.message.from_user.id
            current_message = update.message.text.lower()
            
            # Get the last search context
            last_search = context.user_data.get('context', {}).get('last_search', {})
            search_query = last_search.get('query', '')
            search_result = last_search.get('result', '')

            # Extract restaurant and time information
            booking_details = {
                'restaurant': None,
                'time': None,
                'party_size': None
            }

            # Try to extract from search query
            if "oishii" in search_query.lower():
                booking_details['restaurant'] = "Oishii Boston"
            if "people" in search_query.lower():
                try:
                    party_size = int(''.join(filter(str.isdigit, search_query)))
                    booking_details['party_size'] = party_size
                except ValueError:
                    pass

            # Try to extract from current message
            if "8pm" in current_message or "8:00" in current_message:
                booking_details['time'] = "8:00 PM"
            elif "8:30" in current_message or "830" in current_message:
                booking_details['time'] = "8:30 PM"
            
            # Store the booking context
            context.user_data['booking_context'] = {
                'restaurant': booking_details['restaurant'],
                'time': booking_details['time'],
                'party_size': booking_details['party_size'],
                'original_search': search_query,
                'current_request': current_message
            }
            
            # Initialize booking step
            context.user_data['booking_step'] = 0
            
            await update.message.reply_text("To proceed with the booking, I'll need some details. What's your name?")
            return NAME

        except Exception as e:
            logger.error(f"Error in start_booking_flow: {e}", exc_info=True)
            await self.handle_error(update, update.message.from_user.id)
            return ConversationHandler.END

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

            # Store the current input using MessageUtils
            await self.message_utils.set_booking_info(user_id, fields[current_step], message)

            # Move to next step
            next_step = current_step + 1
            context.user_data['booking_step'] = next_step

            if next_step < len(fields):
                # If there are more fields to collect
                await update.message.reply_text(next_prompts[current_step])
                return next_states[current_step]
            else:
                # All information collected, proceed with booking
                return await self.make_booking(update, context)

        except Exception as e:
            logger.error(f"Error in handle_booking_info: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def make_booking(self, update: Update, context: CallbackContext) -> int:
        """
        Makes the actual booking using collected information.
        
        Args:
            update: Telegram update object
            context: Callback context
            
        Returns:
            int: Next conversation state
        """
        try:
            user_id = update.message.from_user.id
            booking_info = await self.message_utils.get_booking_info(user_id)

            # Execute the booking
            await update.message.reply_text("Processing your booking...")
            result = await self.browser_service.execute_search(
                f"Book with details: {booking_info}",
                task_type="booking"
            )

            # Format and send response
            response = await self.ai_service.format_response("Make booking", result)
            await self.message_utils.send_long_message(update, response)

            # Clear booking info
            await self.message_utils.clear_booking_info(user_id)
            context.user_data['booking_step'] = 0

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in make_booking: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END
