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
                greeting = """Hey there! 👋 I'm your booking assistant.

I can help you find restaurants 🍽️, check what's available 📅, and make reservations ✅

What can I help you with today?"""
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
            initial_response = await self.ai_service.get_recommendations(user_message, user_id)
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
            await update.message.reply_text("Let me check that for you...")

            # Get the complete conversation history for context
            history = await self.message_utils.get_user_history(user_id)
            
            # Extract dates from the current message for context
            check_in_date = None
            check_out_date = None
            if 'next weekend' in user_message.lower():
                from datetime import datetime, timedelta
                today = datetime.now()
                days_until_saturday = (5 - today.weekday()) % 7 + 7  # Get next Saturday
                next_saturday = today + timedelta(days=days_until_saturday)
                next_sunday = next_saturday + timedelta(days=1)
                check_in_date = next_saturday.strftime('%Y-%m-%d')
                check_out_date = next_sunday.strftime('%Y-%m-%d')
            elif 'this weekend' in user_message.lower():
                from datetime import datetime, timedelta
                today = datetime.now()
                days_until_saturday = (5 - today.weekday()) % 7  # Get this Saturday
                this_saturday = today + timedelta(days=days_until_saturday)
                this_sunday = this_saturday + timedelta(days=1)
                check_in_date = this_saturday.strftime('%Y-%m-%d')
                check_out_date = this_sunday.strftime('%Y-%m-%d')
            elif 'tomorrow' in user_message.lower():
                from datetime import datetime, timedelta
                tomorrow = datetime.now() + timedelta(days=1)
                check_in_date = tomorrow.strftime('%Y-%m-%d')
            
            # Use the user's exact search query to avoid losing context
            search_query = user_message
            
            # For reference requests like "the third one" or "first option", conversation context is critical
            reference_indicators = ["first", "second", "third", "1st", "2nd", "3rd", "that one", "last one"]
            is_reference_request = any(indicator in user_message.lower() for indicator in reference_indicators)
            
            if is_reference_request:
                logger.info("Reference request detected - using full conversation context")
            
            # Extend the browser timeout for this search to ensure it doesn't time out
            await self.browser_service.extend_timeout(additional_seconds=1800)  # Add 30 minutes to timeout
            
            # Execute browser search with the query and conversation history - PASS USER_ID
            logger.info(f"Executing search with query: {search_query}")
            result = await self.browser_service.execute_search(search_query, "search", user_id)
            response = await self.ai_service.format_response(search_query, result, user_id)

            # Store search context in user data for potential booking
            if 'context' not in context.user_data:
                context.user_data['context'] = {}
            context.user_data['context']['last_search'] = {
                'query': search_query,
                'result': response,
                'check_in': check_in_date,
                'check_out': check_out_date
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
        """Initiates the booking flow after availability check"""
        try:
            user_id = update.message.from_user.id
            user_message = update.message.text.strip()
            
            # Initialize booking context if it doesn't exist
            if 'booking_context' not in context.user_data:
                context.user_data['booking_context'] = {}
            
            # Analyze recent conversation history to extract booking details
            history = await self.message_utils.get_user_history(user_id)
            
            # Look for most recent availability message
            availability_info = {}
            restaurant_name = None
            available_times = []
            party_size = None
            booking_date = None
            
            logger.info(f"Starting booking flow for user {user_id} with message: {user_message}")
            
            # First, extract from bot's last response about availability
            for msg in reversed(history):
                if msg['role'] == 'assistant':
                    content = msg['content'].lower()
                    
                    # Extract restaurant name
                    if not restaurant_name:
                        import re
                        restaurant_match = re.search(r'checked ([^,]+) for', content)
                        if restaurant_match:
                            restaurant_name = restaurant_match.group(1).strip()
                            logger.info(f"Extracted restaurant: {restaurant_name}")
                        
                        # Alternative pattern (they have slots available)
                        if not restaurant_name:
                            restaurant_match = re.search(r'at ([^,]+) (?:and|for|have|has)', content)
                            if restaurant_match:
                                restaurant_name = restaurant_match.group(1).strip()
                                logger.info(f"Extracted restaurant (alt pattern): {restaurant_name}")
                    
                    # Extract times
                    if not available_times:
                        # Look for typical time patterns in the bot's response
                        time_patterns = [
                            r'(\d+:\d+\s*[ap]m)', # 7:30pm
                            r'(\d+\s*[ap]m)',     # 7pm
                            r'at (\d+(?:[:\.]\d+)?)'  # at 7:30 or at 7
                        ]
                        
                        for pattern in time_patterns:
                            time_matches = re.findall(pattern, content, re.IGNORECASE)
                            if time_matches:
                                available_times.extend(time_matches)
                                logger.info(f"Extracted available times: {time_matches}")
                                break
                    
                    # Extract party size
                    if not party_size:
                        party_match = re.search(r'for (\d+) people', content)
                        if party_match:
                            party_size = party_match.group(1)
                            logger.info(f"Extracted party size: {party_size}")
                    
                    # Extract date
                    if not booking_date:
                        # Look for common date patterns
                        date_patterns = {
                            'tomorrow': 1,
                            'tonight': 0,
                            'this evening': 0,
                            'today': 0
                        }
                        
                        for date_term, days_to_add in date_patterns.items():
                            if date_term in content:
                                from datetime import datetime, timedelta
                                booking_date = (datetime.now() + timedelta(days=days_to_add)).strftime('%Y-%m-%d')
                                logger.info(f"Extracted date from '{date_term}': {booking_date}")
                                break
                        
                        # Try to find a day of week
                        days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        for i, day in enumerate(days_of_week):
                            if day in content:
                                from datetime import datetime, timedelta
                                today = datetime.now()
                                current_weekday = today.weekday()
                                days_to_add = (i - current_weekday) % 7
                                if days_to_add == 0:
                                    days_to_add = 7  # Next week if today
                                booking_date = (today + timedelta(days=days_to_add)).strftime('%Y-%m-%d')
                                logger.info(f"Extracted date from day of week '{day}': {booking_date}")
                                break
                    
                    # Break if we found the availability message
                    if (restaurant_name and available_times) or ('available' in content and restaurant_name):
                        break
            
            # Now check user message for specific time selection
            selected_time = None
            
            # First check for explicit time in current message
            import re
            time_in_message = re.search(r'(\d+(?::\d+)?\s*[ap]m)', user_message, re.IGNORECASE)
            if time_in_message:
                selected_time = time_in_message.group(1)
                logger.info(f"User specified time in message: {selected_time}")
            else:
                # Check if user mentioned a specific time from available times
                for time in available_times:
                    normalized_time = time.replace(':', '').replace(' ', '').lower()
                    normalized_msg = user_message.replace(':', '').replace(' ', '').lower()
                    if normalized_time in normalized_msg:
                        selected_time = time
                        logger.info(f"Matched time '{time}' in user message")
                        break
            
            # Store extracted information
            booking_context = context.user_data['booking_context']
            if restaurant_name:
                booking_context['restaurant'] = restaurant_name
            if selected_time:
                booking_context['time'] = selected_time
            if party_size:
                booking_context['party_size'] = party_size
            if booking_date:
                booking_context['date'] = booking_date
            
            # Get saved user profile
            profile = await self.message_utils.get_user_profile(user_id)
            has_profile = profile and all(profile.get(k) for k in ['name', 'email', 'phone'])
            
            # Check what information is still needed
            missing_info = []
            if not booking_context.get('restaurant'):
                missing_info.append('restaurant name')
            if not booking_context.get('time'):
                if available_times:
                    # User didn't specify which time they want from available options
                    time_options = ", ".join(available_times)
                    await update.message.reply_text(f"Which time would you prefer? Available slots are {time_options}.")
                    return NAME  # Use NAME state to collect time preference
                else:
                    missing_info.append('preferred time')
            if not booking_context.get('party_size'):
                missing_info.append('number of people')
            if not booking_context.get('date'):
                missing_info.append('date')
            
            logger.info(f"Booking context: {booking_context}")
            logger.info(f"Missing information: {missing_info}")
            
            # If user has profile, we don't need to ask for those details
            if has_profile:
                # Copy profile to booking info
                for key, value in profile.items():
                    await self.message_utils.set_booking_info(user_id, key, value)
                
                if missing_info:
                    # Still need restaurant details
                    missing_str = ", ".join(missing_info)
                    await update.message.reply_text(f"I need a few more details to complete your booking. Please provide the {missing_str}.")
                    return NAME  # Use NAME state to collect missing restaurant details
                else:
                    # We have all info needed
                    confirmation = (
                        f"Great! I'll book a table at {booking_context['restaurant']} for "
                        f"{booking_context['party_size']} people on {booking_context['date']} at "
                        f"{booking_context['time']}. I'll use your saved contact information."
                    )
                    await update.message.reply_text(confirmation)
                    # Proceed with booking using saved profile
                    return await self.make_booking(update, context)
            else:
                # User doesn't have profile, need to collect contact info
                if missing_info:
                    # First collect restaurant details
                    missing_str = ", ".join(missing_info)
                    await update.message.reply_text(f"I need some details for your booking. Please provide the {missing_str}.")
                    return NAME
                else:
                    # Have restaurant details, need contact info
                    await update.message.reply_text(
                        f"Perfect! I'll book a table at {booking_context['restaurant']} for "
                        f"{booking_context['party_size']} people on {booking_context['date']} at "
                        f"{booking_context['time']}. Now I need your contact details. What's your name?"
                    )
                    return NAME

        except Exception as e:
            logger.error(f"Error starting booking flow: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def handle_booking_info(self, update: Update, context: CallbackContext) -> int:
        """
        Handles booking information collection (either restaurant details or contact info).
        
        Args:
            update: Telegram update object
            context: Callback context
            
        Returns:
            int: Next conversation state
        """
        try:
            user_id = update.message.from_user.id
            message = update.message.text
            booking_context = context.user_data.get('booking_context', {})
            
            logger.info(f"Handling booking info for user {user_id}. Message: {message}")
            
            # Check if we're collecting restaurant details or contact info
            # First check if we have all restaurant details
            has_restaurant_details = all(key in booking_context for key in ['restaurant', 'time', 'party_size', 'date'])
            
            if not has_restaurant_details:
                # We're collecting missing restaurant details
                logger.info(f"Collecting missing restaurant details. Current context: {booking_context}")
                
                # First check if this is a time selection from available options
                if not booking_context.get('time') and booking_context.get('restaurant'):
                    import re
                    # Try to extract time from message - this is likely responding to our "which time?" question
                    time_pattern = re.search(r'(\d+(?::\d+)?\s*[ap]m)', message.lower())
                    if time_pattern:
                        booking_context['time'] = time_pattern.group(1)
                        logger.info(f"Extracted time selection: {booking_context['time']}")
                    else:
                        # Try common time references
                        time_references = {
                            'earliest': 0,  # first available
                            'first': 0,
                            'second': 1,
                            'third': 2,
                            'last': -1,  # last available
                            'latest': -1
                        }
                        
                        # Get available times from context
                        available_times = []
                        history = await self.message_utils.get_user_history(user_id)
                        for msg in reversed(history[:15]):  # Check last 15 messages
                            if msg['role'] == 'assistant' and 'available' in msg['content'].lower():
                                import re
                                # Try to extract times from this message
                                extracted_times = re.findall(r'(\d+:\d+\s*[ap]m|\d+\s*[ap]m)', msg['content'].lower())
                                if extracted_times:
                                    available_times = extracted_times
                                    break
                        
                        # Find which time they meant by reference
                        for ref, idx in time_references.items():
                            if ref in message.lower() and available_times:
                                selected_idx = idx if idx >= 0 else len(available_times) + idx
                                if 0 <= selected_idx < len(available_times):
                                    booking_context['time'] = available_times[selected_idx]
                                    logger.info(f"Selected time by reference '{ref}': {booking_context['time']}")
                                    break
                
                # Try to extract multiple pieces of information if first response
                if len(booking_context) <= 1:
                    logger.info("Attempting to extract multiple booking details from single message")
                    import re
                    
                    # Try to extract restaurant name if not already have it
                    if not booking_context.get('restaurant'):
                        # Look for restaurant name patterns
                        restaurant_patterns = [
                            r'at\s+([^,\.]+)',  # at Restaurant Name
                            r'to\s+([^,\.]+)',  # to Restaurant Name
                            r'^([^,\.]+?)\s+(?:at|for|on)'  # Restaurant Name at/for/on
                        ]
                        
                        for pattern in restaurant_patterns:
                            restaurant_match = re.search(pattern, message)
                            if restaurant_match:
                                potential_name = restaurant_match.group(1).strip()
                                # Skip if it's just a time or number
                                if not re.match(r'^\d+(?::\d+)?\s*(?:am|pm)?$', potential_name, re.IGNORECASE):
                                    booking_context['restaurant'] = potential_name
                                    logger.info(f"Extracted restaurant name: {booking_context['restaurant']}")
                                    break
                    
                    # Try to extract time if not already have it
                    if not booking_context.get('time'):
                        time_match = re.search(r'(\d+(?::\d+)?\s*[ap]m|\d+\s*[ap]m)', message.lower())
                        if time_match:
                            booking_context['time'] = time_match.group(1)
                            logger.info(f"Extracted time: {booking_context['time']}")
                    
                    # Try to extract party size
                    if not booking_context.get('party_size'):
                        party_patterns = [
                            r'(\d+)\s*people',  # 4 people
                            r'(\d+)\s*persons?',  # 4 person(s)
                            r'table\s*for\s*(\d+)',  # table for 4
                            r'for\s*(\d+)'  # for 4
                        ]
                        
                        for pattern in party_patterns:
                            party_match = re.search(pattern, message.lower())
                            if party_match:
                                booking_context['party_size'] = party_match.group(1)
                                logger.info(f"Extracted party size: {booking_context['party_size']}")
                                break
                    
                    # Try to extract date
                    if not booking_context.get('date'):
                        date_keywords = {
                            'tonight': 0,
                            'today': 0,
                            'tomorrow': 1,
                            'day after tomorrow': 2
                        }
                        
                        for keyword, days in date_keywords.items():
                            if keyword in message.lower():
                                from datetime import datetime, timedelta
                                booking_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                                booking_context['date'] = booking_date
                                logger.info(f"Extracted date from '{keyword}': {booking_context['date']}")
                                break
                        
                        # Look for day of week
                        days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        for i, day in enumerate(days_of_week):
                            if day in message.lower():
                                from datetime import datetime, timedelta
                                today = datetime.now()
                                current_weekday = today.weekday()
                                days_to_add = (i - current_weekday) % 7
                                if days_to_add == 0:
                                    days_to_add = 7  # Next week if today
                                booking_date = (today + timedelta(days=days_to_add)).strftime('%Y-%m-%d')
                                booking_context['date'] = booking_date
                                logger.info(f"Extracted date from day of week '{day}': {booking_context['date']}")
                                break
                
                # Just handle a single missing field if there's only one missing
                elif len([k for k in ['restaurant', 'time', 'party_size', 'date'] if k not in booking_context]) == 1:
                    if not booking_context.get('restaurant'):
                        booking_context['restaurant'] = message.strip()
                        logger.info(f"Set restaurant name directly: {booking_context['restaurant']}")
                    elif not booking_context.get('time'):
                        booking_context['time'] = message.strip()
                        logger.info(f"Set time directly: {booking_context['time']}")
                    elif not booking_context.get('party_size'):
                        # Take first word as number or try to extract number
                        import re
                        number_match = re.search(r'(\d+)', message)
                        if number_match:
                            booking_context['party_size'] = number_match.group(1)
                        else:
                            booking_context['party_size'] = message.strip().split()[0]
                        logger.info(f"Set party size directly: {booking_context['party_size']}")
                    elif not booking_context.get('date'):
                        # Try to convert to date or use as is
                        booking_context['date'] = message.strip()
                        logger.info(f"Set date directly: {booking_context['date']}")
                
                # Check if we now have all restaurant details
                has_restaurant_details = all(key in booking_context for key in ['restaurant', 'time', 'party_size', 'date'])
                logger.info(f"Updated booking context: {booking_context}")
                
                if has_restaurant_details:
                    # We have all restaurant details, check if we need contact info
                    profile = await self.message_utils.get_user_profile(user_id)
                    has_profile = profile and all(profile.get(k) for k in ['name', 'email', 'phone'])
                    
                    if has_profile:
                        # Copy profile to booking info
                        for key, value in profile.items():
                            await self.message_utils.set_booking_info(user_id, key, value)
                        
                        # Confirm and proceed
                        confirmation = (
                            f"Great! I'll book a table at {booking_context['restaurant']} for "
                            f"{booking_context['party_size']} people on {booking_context['date']} at "
                            f"{booking_context['time']}. I'll use your saved contact information."
                        )
                        await update.message.reply_text(confirmation)
                        return await self.make_booking(update, context)
                    else:
                        # Need contact info
                        await update.message.reply_text("Perfect! Now I need your contact details. What's your name?")
                        context.user_data['booking_step'] = 0  # Start contact info collection
                        return NAME
                else:
                    # Still missing some restaurant details
                    missing_info = []
                    if not booking_context.get('restaurant'):
                        missing_info.append('restaurant name')
                    if not booking_context.get('time'):
                        missing_info.append('preferred time')
                    if not booking_context.get('party_size'):
                        missing_info.append('number of people')
                    if not booking_context.get('date'):
                        missing_info.append('date')
                    
                    missing_str = ", ".join(missing_info)
                    await update.message.reply_text(f"I still need the following details: {missing_str}")
                    return NAME
            else:
                # We're collecting contact info
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
                logger.info(f"Stored {fields[current_step]}: {message}")
                
                # Move to next step
                next_step = current_step + 1
                context.user_data['booking_step'] = next_step
                
                if next_step < len(fields):
                    await update.message.reply_text(next_prompts[current_step])
                    return next_states[current_step]
                else:
                    # All contact info collected
                    return await self.make_booking(update, context)

        except Exception as e:
            logger.error(f"Error handling booking info: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END

    async def make_booking(self, update: Update, context: CallbackContext) -> int:
        """Makes the actual booking using the browser service"""
        try:
            user_id = update.message.from_user.id
            booking_context = context.user_data.get('booking_context', {})
            booking_info = await self.message_utils.get_booking_info(user_id)
            
            # Format details for the booking task
            restaurant = booking_context.get('restaurant', 'the restaurant')
            time = booking_context.get('time', '8:00 PM')
            party_size = booking_context.get('party_size', '2')
            date = booking_context.get('date', 'tomorrow')
            
            # Format date for human readability
            readable_date = date
            if date and date.startswith('202'):  # Looks like yyyy-mm-dd format
                from datetime import datetime
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%d')
                    readable_date = date_obj.strftime('%A, %B %d')
                except:
                    pass  # Keep original if parsing fails
            
            # Create a detailed booking instruction with all available context
            booking_instruction = (
                f"Make a booking at {restaurant} for {party_size} people on {date} at {time}.\n\n"
                f"Search for the restaurant's reservation page and complete the booking form with the user's information."
                f"Do not ask for additional user information as all required details have been securely provided."
            )
            
            # Send a message indicating booking is in progress
            await update.message.reply_text(
                f"I'm booking your table at {restaurant} for {party_size} people on {readable_date} at {time}. "
                f"This might take a minute..."
            )
            
            # Ensure booking info contains all necessary contact details
            name = booking_info.get('name', '')
            email = booking_info.get('email', '')
            phone = booking_info.get('phone', '')
            
            logger.info(f"Making booking with context: Restaurant={restaurant}, Date={date}, Time={time}, Party={party_size}")
            logger.debug(f"Using contact info: Name={name}, Email={email}, Phone={phone[:4]}*** (partially masked)")
            
            # Execute the booking with task_type="booking" to ensure sensitive data is passed
            result = await self.browser_service.execute_search(
                booking_instruction,
                task_type="booking",
                user_id=user_id
            )
            
            # Format and send response 
            response = await self.ai_service.format_response(
                "Confirm booking details", 
                result, 
                user_id
            )
            
            # Prepare a user-friendly confirmation message
            success_indicators = ["confirmed", "reservation complete", "booked successfully", "booking confirmed"]
            is_successful = any(indicator in result.lower() for indicator in success_indicators)
            
            confirmation_message = (
                f"Your table at {restaurant} is confirmed for {readable_date} at {time} for {party_size} people. "
                f"You'll receive a confirmation email shortly!"
            ) if is_successful else response
            
            await self.message_utils.send_long_message(update, confirmation_message)
            
            # Store the successful booking in history
            await self.message_utils.add_to_history(user_id, "assistant", confirmation_message)
            
            # Clear booking info
            await self.message_utils.clear_booking_info(user_id)
            if 'booking_step' in context.user_data:
                context.user_data['booking_step'] = 0
            if 'booking_context' in context.user_data:
                context.user_data.pop('booking_context')
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error making booking: {e}", exc_info=True)
            await self.handle_error(update, user_id)
            return ConversationHandler.END
