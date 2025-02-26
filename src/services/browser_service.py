"""
Browser automation service for web interactions.
"""
import logging
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
import asyncio
import os
import time

from browser_use import Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig
from src.config.settings import Settings
from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)


class BrowserService:
    """Handles all browser automation tasks"""

    _instance = None
    _browser = None
    _browser_config = None
    _last_activity_time = None
    _inactivity_timeout = 300  # 5 minutes inactivity timeout
    _inactivity_check_running = False
    _current_context = None  # Track the current browser context

    def __new__(cls, settings: Settings):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(BrowserService, cls).__new__(cls)
            cls._instance.settings = settings
            cls._instance._browser_config = cls._instance._initialize_browser_config()
            cls._instance._last_activity_time = time.time()
            # Initialize Claude LLM for browser tasks
            cls._instance.claude_llm = cls._instance._initialize_claude_llm()
            
            # The inactivity check will be started in initialize_browser
            
        return cls._instance
    
    def _initialize_claude_llm(self):
        """Initialize Claude LLM via OpenRouter for browser tasks"""
        try:
            from langchain_openai import ChatOpenAI
            
            # Using Claude via OpenRouter
            return ChatOpenAI(
                model=self.settings.CLAUDE_MODEL,
                api_key=self.settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                max_tokens=4096,
                temperature=0.1
            )
        except Exception as e:
            logger.error(f"Failed to initialize Claude LLM: {e}", exc_info=True)
            raise

    def _initialize_browser_config(self) -> BrowserConfig:
        """
        Initializes browser configuration.
        
        Returns:
            BrowserConfig: Configured browser settings
        """
        return BrowserConfig(
            headless=True,
            cdp_url=f'wss://connect.steel.dev?apiKey={self.settings.STEEL_API_KEY}'
        )

    async def _check_inactivity(self):
        """Background task to check for browser inactivity and close if inactive too long"""
        logger.info(f"Starting inactivity check (timeout: {self._inactivity_timeout} seconds)")
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                if self._browser is not None and self._last_activity_time is not None:
                    current_time = time.time()
                    elapsed = current_time - self._last_activity_time
                    if elapsed > self._inactivity_timeout:
                        logger.info(f"Browser inactive for {elapsed:.1f} seconds (timeout: {self._inactivity_timeout}), closing")
                        await self.cleanup(force=False)  # Not forcing, this is a normal inactivity timeout
                    else:
                        remaining = self._inactivity_timeout - elapsed
                        logger.debug(f"Browser still active, {remaining:.1f} seconds until timeout")
            except Exception as e:
                logger.error(f"Error in inactivity check: {e}", exc_info=True)

    async def initialize_browser(self):
        """Initialize browser if not already initialized"""
        try:
            # Always create a new browser instance
            if self._browser is not None:
                logger.warning("Browser instance already exists, closing it first")
                try:
                    await self._browser.close()
                except Exception as e:
                    logger.warning(f"Error closing existing browser: {e}")
                finally:
                    self._browser = None
                    await asyncio.sleep(2)  # Wait before creating a new browser
            
            logger.info("Initializing new browser instance")
            self._browser = Browser(self._browser_config)
            await asyncio.sleep(5)  # Wait for Steel.dev connection to establish
            logger.info("Browser initialization completed")
            
            # Start inactivity check only when the browser is first initialized
            if not self._inactivity_check_running:
                # Create the task in an async context
                self._inactivity_check_running = True
                # Use asyncio.create_task in an async context
                asyncio.create_task(self._check_inactivity())
                logger.info("Browser inactivity check started")
        
            # Update activity timestamp
            self._last_activity_time = time.time()
            
            return self._browser
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}", exc_info=True)
            self._browser = None
            raise

    async def execute_search(self, query: str, task_type: str = "search", user_id: int = 1) -> str:
        """
        Execute a search or task using the browser.
        
        Args:
            query: The search query or task description
            task_type: Type of task (search/booking)
            user_id: User identifier
            
        Returns:
            str: Search result or task output
        """
        retry_count = 0
        max_retries = self.settings.MAX_RETRIES
        
        # Update activity timestamp for inactivity tracking
        self._last_activity_time = time.time()
        
        # Get the user's last messages for context
        history = await MessageUtils().get_user_history(user_id)
        history_context = ""
        
        # Format the last few messages for context
        if history:
            history_context = "\n".join(
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in history[-3:]  # Last 3 messages
            )
        
        # Always close and reset the browser before starting a new search
        # This ensures we start with a fresh browser instance each time
        if self._browser is not None:
            logger.info("Closing existing browser before starting new search")
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                # Always set browser to None regardless of whether close succeeded
                self._browser = None
                await asyncio.sleep(2)  # Wait a bit before creating a new browser
        
        while retry_count < max_retries:
            try:
                # Always initialize a new browser instance for each search
                logger.info("Initializing new browser instance for search")
                await self.initialize_browser()
                
                if self._browser is None:
                    raise Exception("Failed to initialize browser")
                
                # Update the activity timestamp to prevent timeout
                self._last_activity_time = time.time()
                
                # Generate task prompt with history context
                task_prompt = await self.generate_task_prompt(query, task_type, history_context)
                
                # Extract sensitive user details if needed for booking
                sensitive_data = None
                if task_type == "booking":
                    sensitive_data = await self._extract_user_details(user_id)
                
                # Configure agent with the browser instance
                agent = Agent(
                    task=task_prompt,
                    llm=self.claude_llm,  # Use Claude for browser tasks
                    browser=self._browser,  # Use the browser instance directly
                    sensitive_data=sensitive_data
                )
                
                logger.info(f"Running browser agent for task: {task_type}")
                
                # Run the agent and get the result
                result = await agent.run()
                
                # Update activity timestamp after successful execution
                self._last_activity_time = time.time()
                logger.info("Search completed successfully")
                
                # Close the browser after successful execution to ensure clean state for next search
                try:
                    await self.cleanup(force=True)
                except Exception as e:
                    logger.warning(f"Error during post-search browser cleanup: {e}")
                    self._browser = None
                
                return self.extract_final_result(result)
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Search attempt {retry_count} failed: {e}", exc_info=True)
                
                # Always reset browser to None on any error
                if self._browser is not None:
                    try:
                        await self._browser.close()
                    except Exception as close_error:
                        logger.warning(f"Error closing browser after failure: {close_error}")
                    finally:
                        self._browser = None
                
                await asyncio.sleep(3)  # Wait before retrying
                
                # If we've reached max retries, return an error message
                if retry_count >= max_retries:
                    return f"I'm sorry, I encountered an issue while searching. Please try again. Error: {str(e)}"

    async def cleanup(self, force=False):
        """
        Cleanup browser resources.
        
        Args:
            force: Whether to force cleanup even if not initiated by inactivity check
        """
        try:
            if self._browser is not None:
                if force:
                    logger.info("Forcing browser cleanup due to explicit request")
                else:
                    logger.info("Browser cleanup due to inactivity timeout")
                
                try:
                    await self._browser.close()
                    logger.info("Browser closed successfully")
                except Exception as e:
                    logger.error(f"Error during browser close: {e}", exc_info=True)
                finally:
                    # Always set browser to None regardless of whether close succeeded
                    self._browser = None
                    logger.info("Browser reference set to None")
            else:
                logger.info("Browser cleanup called but browser was already None")
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}", exc_info=True)
            # Force reset even if error
            self._browser = None

    @staticmethod
    async def generate_task_prompt(query: str, task_type: str, history_context: str = "") -> str:
        """
        Generates a task prompt for the browser agent.
        
        Args:
            query: User query
            task_type: Type of task
            history_context: Recent conversation history
            
        Returns:
            str: Generated prompt
        """
        # Extract dates if present in query for any date-related searches
        dates = None
        if "next weekend" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_saturday = (5 - today.weekday()) % 7 + 7  # Get next Saturday
            next_saturday = today + timedelta(days=days_until_saturday)
            next_sunday = next_saturday + timedelta(days=1)
            dates = f"{next_saturday.strftime('%Y-%m-%d')} to {next_sunday.strftime('%Y-%m-%d')}"
        elif "this weekend" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_saturday = (5 - today.weekday()) % 7  # Get this Saturday
            this_saturday = today + timedelta(days=days_until_saturday)
            this_sunday = this_saturday + timedelta(days=1)
            dates = f"{this_saturday.strftime('%Y-%m-%d')} to {this_sunday.strftime('%Y-%m-%d')}"
        elif "saturday" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_saturday = (5 - today.weekday()) % 7  # Get this Saturday
            this_saturday = today + timedelta(days=days_until_saturday)
            dates = f"{this_saturday.strftime('%Y-%m-%d')}"
        elif "sunday" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_sunday = (6 - today.weekday()) % 7  # Get this Sunday
            this_sunday = today + timedelta(days=days_until_sunday)
            dates = f"{this_sunday.strftime('%Y-%m-%d')}"
        elif "this friday" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_friday = (4 - today.weekday()) % 7  # Get this Friday
            this_friday = today + timedelta(days=days_until_friday)
            dates = f"{this_friday.strftime('%Y-%m-%d')}"
        elif "tomorrow" in query.lower():
            from datetime import datetime, timedelta
            tomorrow = datetime.now() + timedelta(days=1)
            dates = f"{tomorrow.strftime('%Y-%m-%d')}"
            
        # Extract reservation details from current query
        import re
        
        # Extract party size
        party_size = None
        party_size_patterns = [
            r'(\d+)\s*people',
            r'for\s*(\d+)',
            r'party\s*of\s*(\d+)',
            r'group\s*of\s*(\d+)',
        ]
        
        for pattern in party_size_patterns:
            match = re.search(pattern, query.lower())
            if match:
                party_size = match.group(1)
                break
        
        # Extract time
        time = None
        time_patterns = [
            r'(\d+)(?::(\d+))?\s*(am|pm)',
            r'at\s*(\d+)(?::(\d+))?\s*(am|pm)',
            r'at\s*(\d+)',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, query.lower())
            if match:
                if len(match.groups()) >= 3 and match.group(3):  # Has AM/PM
                    hour = int(match.group(1))
                    minutes = match.group(2) if match.group(2) else "00"
                    ampm = match.group(3).lower()
                    if ampm == "pm" and hour < 12:
                        hour += 12
                    time = f"{hour}:{minutes}"
                else:
                    time = f"{match.group(1)}:00"
                break
                
        # If we couldn't extract, check for references to "same time" or "same party size"
        if "same time" in query.lower() or "same party" in query.lower() or "same" in query.lower():
            # Look for previous reservation details in conversation history
            previous_queries = []
            if history_context:
                lines = history_context.split('\n')
                for line in lines:
                    if line.startswith('User:') or line.startswith('U:'):
                        previous_queries.append(line)
                        
            # Process previous queries in reverse order (most recent first)
            for prev_query in reversed(previous_queries):
                # Extract time from previous queries
                if not time:
                    for pattern in time_patterns:
                        match = re.search(pattern, prev_query.lower())
                        if match:
                            if len(match.groups()) >= 3 and match.group(3):  # Has AM/PM
                                hour = int(match.group(1))
                                minutes = match.group(2) if match.group(2) else "00"
                                ampm = match.group(3).lower()
                                if ampm == "pm" and hour < 12:
                                    hour += 12
                                time = f"{hour}:{minutes}"
                            else:
                                time = f"{match.group(1)}:00"
                            break
                
                # Extract party size from previous queries
                if not party_size:
                    for pattern in party_size_patterns:
                        match = re.search(pattern, prev_query.lower())
                        if match:
                            party_size = match.group(1)
                            break
                
                # If we've found both, no need to keep searching
                if time and party_size:
                    break

        # Check if this is a reference request (e.g., "the first one", "third option")
        reference_indicators = ["first", "second", "third", "1st", "2nd", "3rd", "that one", "last one"]
        is_reference_request = any(indicator in query.lower() for indicator in reference_indicators)
        
        # Extract the specific reference if available
        referenced_item = None
        if is_reference_request:
            import re
            # First, try to find the most recent assistant message with numbered items
            assistant_messages = []
            if history_context:
                # Split into lines to find assistant messages
                lines = history_context.split('\n')
                current_message = ""
                is_assistant = False
                
                for line in lines:
                    if line.startswith('Assistant:') or line.startswith('A:'):
                        is_assistant = True
                        if current_message:
                            assistant_messages.append(current_message)
                        current_message = line
                    elif line.startswith('User:') or line.startswith('U:'):
                        is_assistant = False
                        if current_message:
                            assistant_messages.append(current_message)
                        current_message = ""
                    elif is_assistant:
                        current_message += "\n" + line
                
                if current_message and is_assistant:
                    assistant_messages.append(current_message)
            
            # Find numbered items in the most recent assistant message
            if assistant_messages:
                last_assistant_message = assistant_messages[-1]
                # Look for numbered items (1., 2., 3. or 1-, 2-, 3- or 1), 2), 3))
                numbered_items = re.findall(r'(\d+)[.)-]\s+\*\*([^*]+)\*\*', last_assistant_message)
                
                # If not found, try with bullet points
                if not numbered_items:
                    numbered_items = re.findall(r'-\s+\*\*([^*]+)\*\*', last_assistant_message)
                    if numbered_items:
                        # Convert to numbered format for consistency
                        numbered_items = [(str(i+1), item) for i, item in enumerate(numbered_items)]
                
                # Look for reference to "first", "second", "third", etc.
                if "first" in query.lower() or "1st" in query.lower():
                    item_index = 0
                elif "second" in query.lower() or "2nd" in query.lower():
                    item_index = 1
                elif "third" in query.lower() or "3rd" in query.lower():
                    item_index = 2
                elif "fourth" in query.lower() or "4th" in query.lower():
                    item_index = 3
                else:
                    # Try to extract number from query (e.g., "the 2nd one")
                    num_match = re.search(r'(\d+)', query)
                    if num_match:
                        item_index = int(num_match.group(1)) - 1
                    else:
                        item_index = None
                
                if item_index is not None and numbered_items and item_index < len(numbered_items):
                    referenced_item = numbered_items[item_index][1].strip()
        
        # Extract specific named entities (restaurants/hotels) from the query
        named_entity = None
        if not is_reference_request:
            # Check for explicit restaurant/place mentions in the query
            if history_context:
                # Get all restaurants mentioned in assistant messages
                restaurant_mentions = []
                lines = history_context.split('\n')
                for line in lines:
                    if line.startswith('Assistant:') or line.startswith('A:'):
                        # Look for bold items which are likely restaurant names
                        bold_matches = re.findall(r'\*\*([^*]+)\*\*', line)
                        restaurant_mentions.extend(bold_matches)
                
                # Check if any restaurant name appears in the current query
                for restaurant in restaurant_mentions:
                    if restaurant.lower() in query.lower():
                        named_entity = restaurant
                        break
        
        if task_type == "search":
            prompt = f"""
            !!! IMPORTANT - READ CAREFULLY !!!

            {history_context}
            
            CURRENT REQUEST: "{query}"
            {f'DATES MENTIONED: {dates}' if dates else ''}
            {f'TIME REQUESTED: {time}' if time else ''}
            {f'PARTY SIZE: {party_size} people' if party_size else ''}
            
            THIS IS A REFERENCE REQUEST: {is_reference_request}
            
            REFERENCED ITEM: {referenced_item if referenced_item else ""}
            EXPLICITLY MENTIONED PLACE: {named_entity if named_entity else ""}

            STEP 1: UNDERSTAND WHAT THE USER IS ASKING FOR
            {
            "Based on the user's query and conversation history, they are asking about:" + 
            (f" {referenced_item}" if referenced_item else "") + 
            (f" {named_entity}" if named_entity else "") +
            (f" for {party_size} people" if party_size else "") +
            (f" at {time}" if time else "") +
            (f" on {dates}" if dates else "")
            }
            
            TIME LIMIT: 90 seconds total
            
            SEARCH STEPS:
            1. [15s] VERIFY WHAT THE USER IS LOOKING FOR:
               - If they mentioned a specific restaurant by name (like Yardbird or Amber), search for that
               - If they said "the second one" or similar, find that item in the previous list
               - Remember they're asking about availability for {party_size if party_size else 'their party'} at {time if time else 'the specified time'}
            
            2. [20s] Go to the official website of this SPECIFIC place:
               - For restaurants: Search for "[restaurant name] hong kong official website"
               - Use the restaurant's official site first before third-party booking sites
            
            3. [30s] Check real-time availability for these specific details:
               - Date: {dates if dates else "this weekend"}
               - Time: {time if time else "9pm"} as mentioned
               - Party size: {party_size if party_size else "3"} people
               - Look for reservation system, booking form, or contact information
               - MOST IMPORTANTLY: Find and copy the EXACT BOOKING URL for this restaurant
            
            4. [25s] Gather all relevant details:
               - Whether there is availability for the exact requested time/date/party size
               - If the exact time is not available, what alternatives are offered
               - If they don't take reservations, explain their policy clearly
               - Booking conditions and contact information
               - Price range if available (average cost per person)
               - The DIRECT BOOKING LINK that a user could click to make a reservation
            
            FORMAT RESULTS:
            - Start with a clear statement about the specific restaurant and its availability
            - Be explicit about which restaurant you checked
            - Include price range if available
            - Always include the DIRECT BOOKING LINK if available
            - End with an offer to book on behalf of the user
            
            IMPORTANT: 
            - Make absolutely certain you are checking the CORRECT restaurant from the conversation.
            - The booking link is CRITICAL - users need to be able to book directly.
            - If you find a booking platform (OpenTable, Resy, etc.), provide the EXACT link to that specific restaurant.
            """
            return prompt
        elif task_type == "booking":
            return f"""
            CONVERSATION CONTEXT:
            {history_context}
            
            CURRENT REQUEST: "{query}"
            {f'DATES MENTIONED: {dates}' if dates else ''}
            {f'TIME REQUESTED: {time}' if time else ''}
            {f'PARTY SIZE: {party_size} people' if party_size else ''}
            
            REFERENCED ITEM: {referenced_item if referenced_item else ""}
            EXPLICITLY MENTIONED PLACE: {named_entity if named_entity else ""}
            
            Using the conversation context above, proceed with booking exactly what the user is asking for in their most recent request.
            Be sure to focus on the specific restaurant and booking details mentioned in the conversation history.
            
            TIME LIMIT: 90 seconds
            
            STEPS:
            1. [20s] Identify the exact place to book based on the conversation
               - If they mentioned a specific restaurant by name, book that one
               - If they referred to "the second one" or similar, find that item in the previous list
            
            2. [30s] Access the official booking system for the specific place
               - Use the party size: {party_size if party_size else "Not specified"}
               - For the date: {dates if dates else "Not specified"}
               - At time: {time if time else "Not specified"}
            
            3. [40s] Enter all required customer details
               - Use the following placeholders for personal information:
               - Name: user_name
               - Email: user_email
               - Phone: user_phone
            
            FORMAT RESULTS:
            - Booking confirmation details
            - Important information about the booking
            - Next steps required to complete the booking
            - Contact information
            """
        
        # Default to search prompt if task_type is not recognized
        return f"""
            CONVERSATION CONTEXT:
            {history_context}
            
            CURRENT REQUEST: "{query}"
            {f'DATES MENTIONED: {dates}' if dates else ''}
            {f'TIME REQUESTED: {time}' if time else ''}
            {f'PARTY SIZE: {party_size} people' if party_size else ''}
            
            REFERENCED ITEM: {referenced_item if referenced_item else ""}
            EXPLICITLY MENTIONED PLACE: {named_entity if named_entity else ""}
            
            Using the conversation context above, focus on finding information about exactly what the user is asking about in their most recent request.
            Pay special attention if they're referring to something specific from earlier in the conversation.
            
            TIME LIMIT: 90 seconds total
            
            SEARCH STEPS:
            1. [20s] Identify the specific place the user is referring to
            2. [20s] Go directly to official website/platform for that specific place
            3. [30s] Check real-time information and availability for the specified party size and time
            4. [20s] Gather important details and booking information
            
            FORMAT RESULTS CLEARLY WITH ALL FOUND INFORMATION.
            """

    @staticmethod
    def extract_final_result(agent_result: Any) -> str:
        """
        Extracts the final result from agent response.
        
        Args:
            agent_result: Result from browser agent
            
        Returns:
            str: Extracted result
        """
        try:
            if isinstance(agent_result, str):
                return agent_result

            if hasattr(agent_result, 'all_results'):
                completed_actions = [
                    r for r in agent_result.all_results
                    if r.is_done and r.extracted_content
                ]
                if completed_actions:
                    return completed_actions[-1].extracted_content

                actions_with_content = [
                    r for r in agent_result.all_results
                    if r.extracted_content
                ]
                if actions_with_content:
                    return actions_with_content[-1].extracted_content

            return str(agent_result)

        except Exception as e:
            logger.error(f"Error extracting final result: {e}", exc_info=True)
            return str(agent_result)

    async def _extract_user_details(self, user_id: int) -> Dict[str, str]:
        """
        Extract sensitive user details for booking.
        
        Args:
            user_id: User ID to retrieve profile for
            
        Returns:
            Dict[str, str]: Sensitive user data
        """
        try:
            # Initialize MessageUtils to get user profile and booking info
            message_utils = MessageUtils()
            sensitive_data = {}
            
            # Get user profile info asynchronously
            profile = await message_utils.get_user_profile(user_id)
            booking_info = await message_utils.get_booking_info(user_id)
            
            # Combine profile and booking info, with booking info taking precedence
            combined_info = {**profile, **booking_info}
            
            # Map the user data to the expected keys used in prompts
            if 'name' in combined_info:
                sensitive_data['user_name'] = combined_info['name']
            
            if 'email' in combined_info:
                sensitive_data['user_email'] = combined_info['email']
                
            if 'phone' in combined_info:
                sensitive_data['user_phone'] = combined_info['phone']
            
            logger.info(f"Extracted sensitive user details for booking: {list(sensitive_data.keys())}")
            return sensitive_data
            
        except Exception as e:
            logger.error(f"Error extracting user details: {e}", exc_info=True)
            # Return empty dict on error - agent will handle missing info
            return {}

    # Additional method to close browser resources explicitly when needed
    async def force_close_browser(self):
        """
        Force close the browser and reset the instance to None.
        This is a more aggressive version of cleanup that ensures the browser is closed.
        """
        logger.info("Force closing browser")
        try:
            if self._browser is not None:
                try:
                    await self._browser.close()
                    logger.info("Browser force closed successfully")
                except Exception as e:
                    logger.error(f"Error during force browser close: {e}", exc_info=True)
                finally:
                    # Always set browser to None regardless of whether close succeeded
                    self._browser = None
                    logger.info("Browser reference force reset to None")
                    await asyncio.sleep(2)  # Wait a bit after closing
            else:
                logger.info("Force close called but browser was already None")
            return True
        except Exception as e:
            logger.error(f"Unexpected error during force browser close: {e}", exc_info=True)
            # Force reset even if error
            self._browser = None
            return False
