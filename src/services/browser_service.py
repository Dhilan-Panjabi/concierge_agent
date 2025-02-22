"""
Browser automation service for web interactions.
"""
import logging
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI

from browser_use import Agent, Controller
from browser_use.browser.browser import Browser, BrowserConfig
from src.config.settings import Settings

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
        if self._browser is None:
            logger.info("Initializing new browser instance")
            self._browser = Browser(self.browser_config)

    async def execute_search(self, query: str, task_type: str = "search") -> str:
        """
        Executes a browser search and returns results.
        
        Args:
            query: Search query
            task_type: Type of search task
            
        Returns:
            str: Search results
        """
        try:
            # Ensure browser is initialized
            await self.initialize_browser()

            task_prompt = await self.generate_task_prompt(query, task_type)
            agent = Agent(
                task=task_prompt,
                llm=self.openai_llm,
                browser=self._browser,
            )
            result = await agent.run()
            return self.extract_final_result(result)

        except Exception as e:
            logger.error(f"Error executing search: {e}", exc_info=True)
            # Don't cleanup on error, just return error message
            return f"Error during search: {str(e)}"

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
    async def generate_task_prompt(query: str, task_type: str) -> str:
        """
        Generates a task prompt for the browser agent.
        
        Args:
            query: User query
            task_type: Type of task
            
        Returns:
            str: Generated prompt
        """
        prompts = {
            "search": f"""
            TASK: Find real-time information for: "{query}"
            
            TIME LIMIT: 90 seconds total
            
            SEARCH STEPS:
            1. [20s] Quick search on Google for best options
            2. [30s] Check official websites/platforms:
               - If restaurants: OpenTable, official websites
               - If events: Ticketmaster, venue sites
               - If hotels: Booking.com, hotel sites
               - If activities: TripAdvisor, official sites
            3. [20s] Verify current information:
               - Availability
               - Pricing
               - Ratings/Reviews
               - Contact details
            4. [20s] Get booking details:
               - Direct booking links
               - Contact information
               - Important notes
            
            FORMAT RESULTS:
            1. OPTIONS FOUND:
               - Names/details
               - Current prices
               - Available times
               - Direct booking URLs
            
            2. IMPORTANT INFO:
               - Special conditions
               - Additional fees
               - Requirements
            
            3. BOOKING OPTIONS:
               - Direct booking links
               - Phone numbers
               - Alternative booking methods
            """,
            "booking": f"""
            TASK: Make a booking for: "{query}"
            
            TIME LIMIT: 90 seconds
            
            STEPS:
            1. [30s] Access booking system
            2. [30s] Enter required details
            3. [30s] Complete reservation
            
            FORMAT RESULTS:
            - Booking confirmation
            - Important details
            - Next steps
            """
        }
        return prompts.get(task_type, prompts["search"])

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
