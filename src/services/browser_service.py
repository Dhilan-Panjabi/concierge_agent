"""
Service for browser automation tasks.
"""
import asyncio
import logging
import os
import random
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.agent.service import Agent
from langchain_openai import ChatOpenAI

from src.config.settings import Settings
from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)


class BrowserService:
    """Handles all browser automation tasks"""

    _instance = None
    _browsers = {}  # Dictionary to store browser instances by user_id
    _browser_config = None
    _last_activity_times = {}  # Dictionary to track activity times by user_id
    _inactivity_timeout = 1800  # Increasing timeout from 300 to 1800 seconds (30 minutes)
    _inactivity_check_running = False
    _current_contexts = {}  # Track the current browser context by user_id
    
    # Circuit breaker for Anthropic API
    _anthropic_failures = 0
    _anthropic_circuit_open = False
    _anthropic_circuit_open_time = None
    _anthropic_circuit_reset_after = 300  # Reset circuit after 5 minutes
    _anthropic_failure_threshold = 3  # Open circuit after 3 consecutive failures
    
    # General circuit breaker for API overload
    _circuit_open = False
    _circuit_open_time = None
    _circuit_failure_count = 0
    _circuit_reset_threshold = 3  # Number of failures before opening circuit
    _circuit_cooldown_period = 300  # 5 minutes cooldown when circuit is open

    def __new__(cls, settings: Settings):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(BrowserService, cls).__new__(cls)
        return cls._instance

    def _initialize_claude_llm(self):
        """
        Initialize Claude LLM for browser tasks.
        
        Returns:
            LLM: Initialized Claude LLM
        """
        try:
            # Initialize Claude LLM with OpenRouter
            claude_llm = ChatOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.settings.OPENROUTER_API_KEY,
                model=self.settings.CLAUDE_MODEL,
                max_tokens=4096
            )
            
            logger.info(f"Claude LLM initialized with model: {self.settings.CLAUDE_MODEL}")
            return claude_llm
        except Exception as e:
            logger.error(f"Error initializing Claude LLM: {e}")
            raise

    def _initialize_browser_config(self) -> BrowserConfig:
        """
        Initialize browser configuration.
        
        Returns:
            BrowserConfig: Browser configuration
        """
        try:
            browser_config_dict = self.settings.get_browser_config()
            # BrowserConfig doesn't accept 'browserless' parameter directly
            browser_config = BrowserConfig(
                headless=browser_config_dict['headless'],
            )
            
            # If browserless is enabled, set the browserless_url
            if browser_config_dict.get('browserless', False):
                browser_config.browserless_url = browser_config_dict.get('browserless_url')
                
            logger.info(f"Browser config initialized: {browser_config}")
            return browser_config
        except Exception as e:
            logger.error(f"Error initializing browser config: {e}")
            raise

    async def _check_inactivity(self):
        """Check for browser inactivity and cleanup if needed"""
        try:
            while True:
                # Check each browser instance for inactivity
                current_time = time.time()
                browsers_to_close = []
                
                for user_id, last_activity_time in list(self._last_activity_times.items()):
                    if user_id in self._browsers and last_activity_time is not None:
                        elapsed = current_time - last_activity_time
                        remaining = self._inactivity_timeout - elapsed
                        
                        if elapsed > self._inactivity_timeout:
                            logger.info(f"Browser for user {user_id} inactive for {elapsed:.1f} seconds, cleaning up")
                            browsers_to_close.append(user_id)
                        elif remaining < 300:  # Less than 5 minutes remaining
                            # Log more frequently as we approach timeout
                            if remaining < 60:  # Less than 1 minute
                                logger.info(f"Browser for user {user_id} still active, {remaining/60:.1f} minutes until timeout")
                            else:
                                # Use debug level for more frequent updates when approaching timeout
                                logger.debug(f"Browser for user {user_id} still active, {remaining/60:.1f} minutes until timeout")
                
                # Close inactive browsers
                for user_id in browsers_to_close:
                    await self.cleanup(user_id=user_id)
                
                # Sleep for 60 seconds before checking again
                await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in inactivity check: {e}", exc_info=True)

    async def initialize_browser(self, user_id: int = 1):
        """Initialize browser for a specific user if not already initialized"""
        try:
            # Always create a new browser instance for this user if requested
            if user_id in self._browsers and self._browsers[user_id] is not None:
                logger.warning(f"Browser instance for user {user_id} already exists, closing it first")
                try:
                    await self._browsers[user_id].close()
                except Exception as e:
                    logger.warning(f"Error closing existing browser for user {user_id}: {e}")
                finally:
                    self._browsers[user_id] = None
                    # Reduced wait time from 2 seconds to 1 second
                    await asyncio.sleep(1)
            
            # Check if we need to install Playwright browsers
            await self._ensure_playwright_browsers()
            
            logger.info(f"Initializing new browser instance for user {user_id}")
            self._browsers[user_id] = Browser(self._browser_config)
            # Reduced wait time from 5 seconds to 3 seconds
            await asyncio.sleep(3)
            logger.info(f"Browser initialization completed for user {user_id}")
            
            # Start inactivity check only when the first browser is initialized
            if not self._inactivity_check_running:
                # Create the task in an async context
                self._inactivity_check_running = True
                # Use asyncio.create_task in an async context
                asyncio.create_task(self._check_inactivity())
                logger.info("Browser inactivity check started")
        
            # Update activity timestamp for this user
            self._last_activity_times[user_id] = time.time()
            
            return self._browsers[user_id]
        except Exception as e:
            logger.error(f"Error initializing browser for user {user_id}: {e}")
            raise

    async def _ensure_playwright_browsers(self):
        """Ensure Playwright browsers are installed"""
        try:
            # Check if we're running on Railway
            is_railway = os.environ.get('RAILWAY_ENVIRONMENT', '') != ''
            
            # Only attempt to install browsers if we're on Railway and haven't tried before
            if is_railway and not hasattr(self, '_playwright_browsers_checked'):
                logger.info("Checking Playwright browsers on Railway...")
                
                # Mark that we've checked for browsers
                self._playwright_browsers_checked = True
                
                # Try to create a browser to see if it works
                try:
                    test_config = BrowserConfig(headless=True)
                    test_browser = Browser(test_config)
                    await test_browser.close()
                    logger.info("Playwright browsers are already installed")
                except Exception as e:
                    if "Executable doesn't exist" in str(e) or "Please run the following command" in str(e):
                        logger.warning("Playwright browsers not installed, attempting to install...")
                        
                        # Try to install browsers using subprocess
                        import subprocess
                        try:
                            # Run the playwright install command
                            process = subprocess.Popen(
                                ["playwright", "install", "chromium"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                            
                            if process.returncode == 0:
                                logger.info("Successfully installed Playwright browsers")
                            else:
                                logger.error(f"Failed to install Playwright browsers: {stderr.decode()}")
                                
                            # Also install dependencies
                            process = subprocess.Popen(
                                ["playwright", "install-deps", "chromium"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                            
                            if process.returncode == 0:
                                logger.info("Successfully installed Playwright dependencies")
                            else:
                                logger.error(f"Failed to install Playwright dependencies: {stderr.decode()}")
                                
                        except Exception as install_error:
                            logger.error(f"Error installing Playwright browsers: {install_error}")
                    else:
                        # Some other error occurred
                        logger.error(f"Error checking Playwright browsers: {e}")
        except Exception as e:
            logger.error(f"Error in _ensure_playwright_browsers: {e}")

    async def execute_search(self, query: str, task_type: str = "search", user_id: int = 1) -> str:
        """
        Execute a search or task using the browser.
        
        Args:
            query: The search query or task description
            task_type: Type of task (search, booking, etc.)
            user_id: User ID for tracking browser instances
            
        Returns:
            str: Result of the search or task
        """
        # Update activity timestamp for this user
        self._last_activity_times[user_id] = time.time()
        
        # Check if circuit breaker is open
        if self._circuit_open:
            current_time = time.time()
            if current_time - self._circuit_open_time < self._circuit_cooldown_period:
                cooling_remaining = self._circuit_cooldown_period - (current_time - self._circuit_open_time)
                logger.warning(f"Circuit breaker is open. Cooling down for {cooling_remaining:.1f} more seconds.")
                return "I'm sorry, but our service is currently experiencing high demand. Please try again in a few minutes."
            else:
                # Reset circuit breaker after cooldown period
                logger.info("Circuit breaker cooldown period ended. Resetting circuit breaker.")
                self._circuit_open = False
                self._circuit_failure_count = 0
        
        # Check if Anthropic circuit breaker is open
        if self._anthropic_circuit_open:
            current_time = time.time()
            if current_time - self._anthropic_circuit_open_time < self._anthropic_circuit_reset_after:
                cooling_remaining = self._anthropic_circuit_reset_after - (current_time - self._anthropic_circuit_open_time)
                logger.warning(f"Anthropic API circuit breaker is open. Cooling down for {cooling_remaining:.1f} more seconds.")
                return "I'm sorry, but our service is currently experiencing high demand with the AI provider. Please try again in a few minutes."
            else:
                # Reset Anthropic circuit breaker after cooldown period
                logger.info("Anthropic API circuit breaker cooldown period ended. Resetting circuit breaker.")
                self._anthropic_circuit_open = False
                self._anthropic_failures = 0
        
        # Initialize result
        result = ""
        
        # Get user details for personalized prompts
        user_details = await self._extract_user_details(user_id)
        
        # Track if we need to reset the browser
        need_browser_reset = False
        
        # Keep track of retries
        retries = 0
        max_retries = self.settings.MAX_RETRIES
        
        # Keep track of the keep-alive task
        keep_alive_task = None
        
        while retries <= max_retries:
            try:
                # Initialize browser if needed
                if user_id not in self._browsers or self._browsers[user_id] is None:
                    await self.initialize_browser(user_id)
                
                # Generate task prompt
                prompt = await self.generate_task_prompt(query, task_type, user_details.get("history_context", ""))
                
                # Create a new agent for this task
                agent = Agent(
                    browser=self._browsers[user_id],
                    llm=self.claude_llm,
                    task=prompt
                )
                
                # Start a task to keep the browser active during execution
                async def keep_browser_active():
                    try:
                        while True:
                            # Update activity timestamp every 5 minutes
                            await asyncio.sleep(300)
                            self._last_activity_times[user_id] = time.time()
                            logger.debug(f"Updated browser activity timestamp for user {user_id}")
                    except asyncio.CancelledError:
                        logger.debug("Keep-alive task cancelled")
                    except Exception as e:
                        logger.error(f"Error in keep_browser_active: {e}")
                
                # Start the keep-alive task
                keep_alive_task = asyncio.create_task(keep_browser_active())
                
                # Run the agent with increased max_steps
                try:
                    # Check if we're on Railway or if GIF creation is disabled
                    is_railway = os.environ.get('RAILWAY_ENVIRONMENT', '') != ''
                    disable_gif = os.environ.get('DISABLE_GIF_CREATION', 'false').lower() == 'true'
                    
                    # Run the agent with appropriate parameters
                    if is_railway or disable_gif:
                        agent_result = await agent.run(max_steps=12, disable_history=True)
                    else:
                        agent_result = await agent.run(max_steps=12)
                    
                    # Extract the final result
                    result = self.extract_final_result(agent_result)
                    
                    # Reset Anthropic failures counter on success
                    self._anthropic_failures = 0
                    
                    # Reset circuit failure count on success
                    self._circuit_failure_count = 0
                    
                    # No need to reset browser after successful execution
                    need_browser_reset = False
                    
                    # Break out of retry loop on success
                    break
                    
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # Check for Playwright browser installation issues
                    if "executable doesn't exist" in error_str or "please run the following command" in error_str:
                        logger.warning("Playwright browser installation issue detected")
                        
                        # Try to install browsers
                        try:
                            # Force browser reset
                            need_browser_reset = True
                            
                            # Try to install browsers using subprocess
                            import subprocess
                            logger.info("Attempting to install Playwright browsers...")
                            
                            # Run the playwright install command
                            process = subprocess.Popen(
                                ["playwright", "install", "chromium"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                            
                            if process.returncode == 0:
                                logger.info("Successfully installed Playwright browsers")
                            else:
                                logger.error(f"Failed to install Playwright browsers: {stderr.decode()}")
                            
                            # Provide a user-friendly error message
                            result = "I'm sorry, but I encountered an issue with the browser. Please try again in a moment."
                        except Exception as install_error:
                            logger.error(f"Error installing Playwright browsers: {install_error}")
                            result = "I'm sorry, but I encountered a technical issue. Please try again later."
                    
                    # Check for Anthropic API overload
                    elif any(term in error_str for term in ["overloaded", "502", "too many requests", "rate limit"]):
                        self._anthropic_failures += 1
                        logger.warning(f"Anthropic API overload detected. Failure count: {self._anthropic_failures}")
                        
                        if self._anthropic_failures >= self._anthropic_failure_threshold:
                            logger.warning("Anthropic API circuit breaker opened due to consecutive failures")
                            self._anthropic_circuit_open = True
                            self._anthropic_circuit_open_time = time.time()
                            return "I'm sorry, but our AI service is currently experiencing high demand. Please try again in a few minutes."
                        
                        # Increment general circuit failure count as well
                        self._circuit_failure_count += 1
                        
                        # Need to reset browser after API overload
                        need_browser_reset = True
                        
                        # Provide a user-friendly error message
                        result = "I'm sorry, but I encountered an issue with the search. The service might be experiencing high demand. Let me try again."
                    
                    # Check for other API overload patterns
                    elif any(term in error_str for term in ["timeout", "connection", "network", "socket"]):
                        self._circuit_failure_count += 1
                        logger.warning(f"API connection issue detected. Failure count: {self._circuit_failure_count}")
                        
                        # Need to reset browser after connection issues
                        need_browser_reset = True
                        
                        # Provide a user-friendly error message
                        result = "I'm sorry, but I encountered a connection issue. Let me try again."
                    
                    # Handle other errors
                    else:
                        logger.error(f"Error running agent: {e}")
                        need_browser_reset = True
                        result = f"I encountered an error: {str(e)}"
                    
                    # Check if we should open the circuit breaker
                    if self._circuit_failure_count >= self._circuit_reset_threshold:
                        logger.warning("Circuit breaker opened due to consecutive failures")
                        self._circuit_open = True
                        self._circuit_open_time = time.time()
                        return "I'm sorry, but our service is currently experiencing technical difficulties. Please try again in a few minutes."
            
            except Exception as e:
                logger.error(f"Error in execute_search for user {user_id}: {e}")
                need_browser_reset = True
                result = f"I encountered an error: {str(e)}"
            
            finally:
                # Cancel the keep-alive task
                if keep_alive_task:
                    keep_alive_task.cancel()
                    try:
                        await keep_alive_task
                    except asyncio.CancelledError:
                        pass
            
            # Reset browser if needed before retrying
            if need_browser_reset:
                try:
                    logger.info(f"Resetting browser for user {user_id} before retry")
                    await self.cleanup(user_id=user_id, force=True)
                    await asyncio.sleep(1)  # Short delay before retry
                except Exception as e:
                    logger.error(f"Error resetting browser: {e}")
            
            # Increment retry counter
            retries += 1
            
            # If we've reached max retries, break out of the loop
            if retries > max_retries:
                logger.warning(f"Max retries ({max_retries}) reached for user {user_id}")
                if not result:
                    result = "I'm sorry, but I was unable to complete your request after multiple attempts. Please try again later."
                break
            
            # Exponential backoff with jitter for retries
            if need_browser_reset and retries <= max_retries:
                # Start with 2 seconds, then 4, 8, etc.
                delay = 2 ** retries
                # Add jitter (±25%)
                jitter = delay * 0.25 * (random.random() * 2 - 1)
                delay = max(1, delay + jitter)
                logger.info(f"Retrying in {delay:.1f} seconds (attempt {retries}/{max_retries})")
                await asyncio.sleep(delay)
        
        # Update activity timestamp after execution
        self._last_activity_times[user_id] = time.time()
        
        return result

    async def cleanup(self, user_id: int = None, force=False):
        """
        Clean up browser resources for a specific user or all users.
        
        Args:
            user_id: User ID to clean up, or None for all users
            force: Force cleanup even if browser is active
        """
        try:
            # If user_id is provided, clean up only that user's browser
            if user_id is not None:
                if user_id in self._browsers and self._browsers[user_id] is not None:
                    logger.info(f"Cleaning up browser for user {user_id}")
                    try:
                        await self._browsers[user_id].close()
                    except Exception as e:
                        logger.warning(f"Error closing browser for user {user_id}: {e}")
                    finally:
                        self._browsers[user_id] = None
                        if user_id in self._last_activity_times:
                            del self._last_activity_times[user_id]
                        if user_id in self._current_contexts:
                            del self._current_contexts[user_id]
                else:
                    logger.debug(f"No browser instance to clean up for user {user_id}")
            else:
                # Clean up all browser instances
                logger.info("Cleaning up all browser instances")
                for uid, browser in list(self._browsers.items()):
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.warning(f"Error closing browser for user {uid}: {e}")
                        finally:
                            self._browsers[uid] = None
                
                # Clear all tracking dictionaries
                self._browsers.clear()
                self._last_activity_times.clear()
                self._current_contexts.clear()
                
                logger.info("All browser instances cleaned up")
        
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")

    async def force_close_browser(self, user_id: int = None):
        """
        Force close browser instance(s) without waiting for graceful cleanup.
        
        Args:
            user_id: User ID to force close, or None for all users
        """
        try:
            if user_id is not None:
                # Force close specific user's browser
                if user_id in self._browsers and self._browsers[user_id] is not None:
                    logger.info(f"Force closing browser for user {user_id}")
                    try:
                        await self._browsers[user_id].close()
                    except Exception as e:
                        logger.warning(f"Error force closing browser for user {user_id}: {e}")
                    finally:
                        self._browsers[user_id] = None
                        if user_id in self._last_activity_times:
                            del self._last_activity_times[user_id]
                        if user_id in self._current_contexts:
                            del self._current_contexts[user_id]
            else:
                # Force close all browsers
                for uid, browser in list(self._browsers.items()):
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.warning(f"Error force closing browser for user {uid}: {e}")
                
                # Clear all tracking dictionaries
                self._browsers.clear()
                self._last_activity_times.clear()
                self._current_contexts.clear()
                
                logger.info("All browser instances force closed")
        
        except Exception as e:
            logger.error(f"Error in force_close_browser: {e}")

    async def extend_timeout(self, user_id: int = 1, additional_seconds=1800):
        """
        Extend the inactivity timeout for a specific user's browser.
        
        Args:
            user_id: User ID to extend timeout for
            additional_seconds: Additional seconds to add to timeout
        """
        try:
            # Update the activity timestamp to effectively extend the timeout
            if user_id in self._last_activity_times:
                self._last_activity_times[user_id] = time.time()
                logger.info(f"Extended timeout for user {user_id} by updating activity timestamp")
            else:
                # If no activity timestamp exists, create one
                self._last_activity_times[user_id] = time.time()
                logger.info(f"Created new activity timestamp for user {user_id}")
            
            return True
        except Exception as e:
            logger.error(f"Error extending timeout for user {user_id}: {e}")
            return False

    def __init__(self, settings):
        """Initialize the browser service"""
        self.settings = settings
        self.browser_config = settings.get_browser_config()
        self.timeout_config = settings.get_timeout_config()
        
        # Set up logging specifically for browser operations
        self.logger = logging.getLogger(__name__)
        # Set level to INFO to ensure all browser operations are logged
        self.logger.setLevel(logging.INFO)
        
        # Force browser-use logger to INFO level as well
        browser_use_logger = logging.getLogger('browser_use')
        browser_use_logger.setLevel(logging.INFO)
        
        # Force related loggers to INFO as well
        for logger_name in ['browser_use.agent', 'browser_use.browser', 'browser_use.context']:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
        
        # Log browser configuration
        self.logger.info(f"Browser config initialized: {self.browser_config}")
        self.logger.info("BrowserService initialized")
        
        # Initialize Claude LLM for browser use
        try:
            # Import and configure Claude for browser use
            from browser_use import Agent, AgentConfig, BrowserConfig
            from langchain_anthropic import ChatAnthropic
            
            # Initialize Claude LLM
            self.claude_llm = ChatAnthropic(model=settings.CLAUDE_MODEL)
            self.logger.info(f"Claude LLM initialized with model: {settings.CLAUDE_MODEL}")
            
            # Configure browser
            self.browser_config_obj = BrowserConfig(
                headless=self.browser_config['headless'],
                disable_security=True
            )
            
            self.logger.info(f"Browser config initialized: {self.browser_config_obj}")
        except Exception as e:
            self.logger.error(f"Error initializing Claude LLM or browser config: {e}", exc_info=True)
            raise

    async def reset_circuit_breaker(self):
        """Reset the circuit breaker state."""
        logger.info("Manually resetting circuit breaker state")
        self._circuit_open = False
        self._circuit_open_time = None
        self._circuit_failure_count = 0
        self._anthropic_failures = 0
        self._anthropic_circuit_open = False
        self._anthropic_circuit_open_time = None
        return True

    async def _extract_user_details(self, user_id: int) -> Dict[str, Any]:
        """
        Extract user details and conversation history for personalized prompts.
        
        Args:
            user_id: User ID to retrieve profile for
            
        Returns:
            Dict: User details and history context
        """
        try:
            # Initialize MessageUtils to get user profile and history
            message_utils = MessageUtils()
            user_details = {}
            
            # Get user profile info asynchronously
            profile = await message_utils.get_user_profile(user_id)
            booking_info = await message_utils.get_booking_info(user_id)
            
            # Combine profile and booking info, with booking info taking precedence
            combined_info = {**profile, **booking_info}
            
            # Map the user data to the expected keys used in prompts
            if 'name' in combined_info:
                user_details['user_name'] = combined_info['name']
            
            if 'email' in combined_info:
                user_details['user_email'] = combined_info['email']
                
            if 'phone' in combined_info:
                user_details['user_phone'] = combined_info['phone']
            
            # Get the user's last messages for context
            history = await message_utils.get_user_history(user_id)
            history_context = ""
            
            # Format the last few messages for context
            if history:
                history_context = "\n".join(
                    f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                    for msg in history[-3:]  # Last 3 messages
                )
            
            user_details['history_context'] = history_context
            
            logger.info(f"Extracted user details for user {user_id}: {list(user_details.keys())}")
            return user_details
            
        except Exception as e:
            logger.error(f"Error extracting user details: {e}")
            # Return empty dict on error - agent will handle missing info
            return {'history_context': ''}

    async def generate_task_prompt(self, query: str, task_type: str, history_context: str = "") -> str:
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

    def extract_final_result(self, agent_result: Any) -> str:
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
                
                # If we have results but no extracted content, try to get the last action's result
                if agent_result.all_results:
                    last_action = agent_result.all_results[-1]
                    if hasattr(last_action, 'result') and last_action.result:
                        return f"Found information: {str(last_action.result)}"
                    elif hasattr(last_action, 'action') and last_action.action:
                        return f"Last action performed: {str(last_action.action)}"

            # If we get here, try to extract any useful information from the agent_result
            if hasattr(agent_result, 'result'):
                return str(agent_result.result)
            elif hasattr(agent_result, 'message'):
                return str(agent_result.message)

            return str(agent_result)
        
        except Exception as e:
            logger.error(f"Error extracting final result: {e}")
            # Return a more helpful message with any information we can extract
            try:
                if hasattr(agent_result, 'all_results') and agent_result.all_results:
                    # Try to extract any useful information from the results
                    steps_info = []
                    for i, step in enumerate(agent_result.all_results):
                        step_info = f"Step {i+1}: "
                        if hasattr(step, 'action') and step.action:
                            step_info += f"Action: {step.action}"
                        if hasattr(step, 'result') and step.result:
                            step_info += f", Result: {step.result}"
                        steps_info.append(step_info)
                    
                    if steps_info:
                        return "I found some information, but encountered an error processing the results. Here's what I found:\n\n" + "\n".join(steps_info)
            except:
                pass
                
            return f"I encountered an error while processing the search results: {str(e)}. Please try again with a more specific query."

    async def search_hotels(self, query, location=None, check_in=None, check_out=None):
        """
        Search for hotels based on query and optional parameters.
        
        Args:
            query: Search query
            location: Hotel location
            check_in: Check-in date
            check_out: Check-out date
            
        Returns:
            list: Search results
        """
        self.logger.info(f"Searching hotels with query: {query}, location: {location}, check_in: {check_in}, check_out: {check_out}")
        
        try:
            from browser_use import Agent, AgentConfig
            
            # Construct search URL
            search_term = f"{query} hotel {location}" if location else f"{query} hotel"
            
            # Define the task
            task = f"Search for '{search_term}' and find hotel information"
            if check_in and check_out:
                task += f" for dates {check_in} to {check_out}"
            
            self.logger.info(f"Creating browser agent for task: {task}")
            
            # Create agent
            agent = Agent.create_browser(
                llm=self.claude_llm,
                browser_config=self.browser_config_obj,
                agent_config=AgentConfig(
                    name="HotelSearchAgent",
                    description="Agent for searching hotel information",
                )
            )
            
            self.logger.info("Browser agent created successfully. Starting search...")
            
            # Run search
            result = await agent.run(task)
            
            self.logger.info(f"Search completed. Result type: {type(result)}")
            self.logger.info(f"Search result summary: {result[:200] if isinstance(result, str) else 'Non-string result'}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in hotel search: {e}", exc_info=True)
            return f"Error searching for hotels: {str(e)}"

    async def search_restaurants(self, location, cuisine=None, price_range=None):
        """
        Search for restaurants based on location and optional parameters.
        
        Args:
            location: Restaurant location
            cuisine: Type of cuisine
            price_range: Price range (e.g., '$', '$$', '$$$')
            
        Returns:
            list: Search results
        """
        self.logger.info(f"Searching restaurants with location: {location}, cuisine: {cuisine}, price_range: {price_range}")
        
        try:
            from browser_use import Agent, AgentConfig
            
            # Construct search query
            search_term = f"best restaurants in {location}"
            if cuisine:
                search_term += f" {cuisine} cuisine"
            if price_range:
                search_term += f" {price_range} price range"
            
            # Define the task
            task = f"Search for '{search_term}' and find restaurant recommendations with websites, ratings, and price ranges"
            
            self.logger.info(f"Creating browser agent for restaurant task: {task}")
            
            # Create agent
            agent = Agent.create_browser(
                llm=self.claude_llm,
                browser_config=self.browser_config_obj,
                agent_config=AgentConfig(
                    name="RestaurantSearchAgent",
                    description="Agent for searching restaurant information",
                )
            )
            
            self.logger.info("Restaurant browser agent created successfully. Starting search...")
            
            # Run search
            result = await agent.run(task)
            
            self.logger.info(f"Restaurant search completed. Result type: {type(result)}")
            self.logger.info(f"Restaurant search result summary: {result[:200] if isinstance(result, str) else 'Non-string result'}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in restaurant search: {e}", exc_info=True)
            return f"Error searching for restaurants: {str(e)}"
