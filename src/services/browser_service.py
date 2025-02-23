"""
Browser automation service for web interactions.
"""
import logging
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
import asyncio

from browser_use import Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig
from src.config.settings import Settings
from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)


class BrowserService:
    """Handles all browser automation tasks"""

    _instance = None
    _browser = None

    def __new__(cls, settings: Settings):
        if cls._instance is None:
            cls._instance = super(BrowserService, cls).__new__(cls)
            cls._instance.settings = settings
            cls._instance.browser_config = cls._instance._initialize_browser_config()
            cls._instance.controller = Controller()
            cls._instance.openai_llm = ChatOpenAI(
                model="gpt-4o",
                api_key=settings.OPENAI_API_KEY
            )
        return cls._instance

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

    async def initialize_browser(self):
        """Initialize browser if not already initialized"""
        try:
            if self._browser is None:
                logger.info("Initializing new browser instance")
                self._browser = Browser(self.browser_config)
                await asyncio.sleep(2)  # Give more time for Steel.dev connection
                logger.info("Browser initialization completed")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}", exc_info=True)
            self._browser = None
            raise

    async def execute_search(self, query: str, task_type: str = "search") -> str:
        """
        Executes a browser search and returns results.
        
        Args:
            query: Search query
            task_type: Type of search task
            
        Returns:
            str: Search results
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Initialize browser if needed
                if self._browser is None:
                    await self.initialize_browser()

                # Get recent chat history from MessageUtils
                message_utils = MessageUtils()
                # We'll get this from the singleton instance that already exists
                history = await message_utils.get_user_history(1)  # Using 1 as default user_id
                recent_history = history[-2:] if len(history) >= 2 else history  # Get last 2 messages
                
                # Format history for context
                history_context = "\nRECENT CONVERSATION:\n"
                for msg in recent_history:
                    role = "User" if msg['role'] == 'user' else "Assistant"
                    history_context += f"{role}: {msg['content']}\n"

                task_prompt = await self.generate_task_prompt(query, task_type, history_context)
                agent = Agent(
                    task=task_prompt,
                    llm=self.openai_llm,
                    browser=self._browser,
                )
                result = await agent.run()
                return self.extract_final_result(result)

            except Exception as e:
                retry_count += 1
                logger.error(f"Search attempt {retry_count} failed: {e}", exc_info=True)
                
                # On error, cleanup and try to reinitialize
                await self.cleanup()
                await asyncio.sleep(2)  # Wait before retrying
                
                if retry_count >= max_retries:
                    return "Unable to complete the search after multiple attempts. Please try again later."

    async def cleanup(self):
        """Cleanup browser resources"""
        try:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
                logger.info("Browser cleanup completed")
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}", exc_info=True)

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
        # Extract dates if present in query
        dates = None
        if "next weekend" in query.lower():
            from datetime import datetime, timedelta
            today = datetime.now()
            days_until_saturday = (5 - today.weekday()) % 7 + 7  # Get next Saturday
            next_saturday = today + timedelta(days=days_until_saturday)
            next_sunday = next_saturday + timedelta(days=1)
            dates = f"{next_saturday.strftime('%Y-%m-%d')} to {next_sunday.strftime('%Y-%m-%d')}"

        if task_type == "search":
            return f"""
            {history_context}
            
            CURRENT REQUEST: "{query}"
            {f'DATES: {dates}' if dates else ''}
            
            Using the conversation context above, focus on finding information about the specific item/place mentioned in the recent messages.
            
            TIME LIMIT: 90 seconds total
            
            SEARCH STEPS:
            1. [20s] Go directly to official website/platform based on the query type:
               - For hotels: Check the hotel's official website first, then Booking.com
               - For restaurants: Check official website, then OpenTable
               - For events: Check venue site, then Ticketmaster
               - For activities: Check official site, then TripAdvisor
            
            2. [30s] Check real-time information:
               - Current availability for specified dates
               - Pricing and rates
               - Room types/options available
               - Special offers or packages
            
            3. [20s] Gather important details:
               - Booking conditions
               - Cancellation policies
               - Check-in/check-out times
               - Included amenities
               - Additional fees
            
            4. [20s] Collect booking information:
               - Direct booking links
               - Contact numbers
               - Email addresses
               - Alternative booking methods
            
            FORMAT RESULTS:
            1. AVAILABILITY & PRICING:
               - List all available options
               - Current rates in local currency
               - Special offers if any
            
            2. IMPORTANT DETAILS:
               - Key policies and conditions
               - Required deposits
               - Included services
               - Additional fees
            
            3. BOOKING OPTIONS:
               - Direct booking links
               - Contact information
               - Alternative booking methods
            
            Note: Focus on providing accurate, current information from official sources.
            """
        elif task_type == "booking":
            return f"""
            {history_context}
            
            CURRENT REQUEST: "{query}"
            
            Using the conversation context above, proceed with booking the specific item/place mentioned in the recent messages.
            
            TIME LIMIT: 90 seconds
            
            STEPS:
            1. [30s] Access the official booking system
            2. [30s] Enter all required details
            3. [30s] Complete the reservation process
            
            FORMAT RESULTS:
            - Booking confirmation details
            - Important information
            - Next steps required
            - Contact information
            """
        
        # Default to search prompt if task_type is not recognized
        return f"""
            {history_context}
            
            CURRENT REQUEST: "{query}"
            
            Using the conversation context above, focus on finding information about the specific item/place mentioned in the recent messages.
            
            TIME LIMIT: 90 seconds total
            
            SEARCH STEPS:
            1. [20s] Go directly to official website/platform based on the query type
            2. [30s] Check real-time information and availability
            3. [20s] Gather important details and policies
            4. [20s] Collect booking information
            
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
