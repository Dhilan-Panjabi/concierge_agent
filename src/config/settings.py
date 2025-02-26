"""
Configuration settings for the application.
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Application settings and configuration"""

    def __init__(self):
        """Initialize settings from environment variables"""
        # Load environment variables
        load_dotenv()

        # Bot settings
        self.BOT_TOKEN: str = self._get_env('TELEGRAM_BOT_TOKEN')
        self.BOT_USERNAME: str = self._get_env('BOT_USERNAME', 'YourBot')

        # Webhook settings
        self.USE_WEBHOOK: bool = self._get_env_bool('USE_WEBHOOK', False)
        self.WEBHOOK_URL: Optional[str] = os.getenv('WEBHOOK_URL')
        self.WEBHOOK_PORT: int = self._get_env_int('PORT', 8443)
        self.WEBHOOK_PATH: str = self._get_env('WEBHOOK_PATH', '')
        
        # API Keys
        self.OPENAI_API_KEY: str = self._get_env('OPENAI_API_KEY')
        self.DEEPSEEK_API_KEY: Optional[str] = os.getenv('DEEPSEEK_API_KEY', '')
        self.STEEL_API_KEY: str = self._get_env('STEEL_API_KEY')
        self.OPENROUTER_API_KEY: str = self._get_env('OPENROUTER_API_KEY')

        # Browser settings
        self.BROWSER_HEADLESS: bool = self._get_env_bool(
            'BROWSER_HEADLESS', True)
        self.BROWSER_BROWSERLESS: bool = self._get_env_bool(
            'BROWSER_BROWSERLESS', True)
        self.BROWSERLESS_URL: str = self._get_env(
            'BROWSERLESS_URL',
            'wss://chrome.browserless.io'
        )

        # AI Model settings
        self.GPT_MODEL: str = self._get_env('GPT_MODEL', 'gpt-4o')
        self.DEEPSEEK_MODEL: str = self._get_env(
            'DEEPSEEK_MODEL', 'deepseek-reasoner')
        self.CLAUDE_MODEL: str = self._get_env(
            'CLAUDE_MODEL', 'anthropic/claude-3-7-sonnet-20250219')

        # Initialize AI models
        self.deepseek_llm = self._initialize_deepseek()

        # Timeouts and limits
        self.SEARCH_TIMEOUT: int = self._get_env_int('SEARCH_TIMEOUT', 90)
        self.MAX_RETRIES: int = self._get_env_int('MAX_RETRIES', 3)
        self.MESSAGE_CHUNK_SIZE: int = self._get_env_int(
            'MESSAGE_CHUNK_SIZE', 4000)

        # Storage settings
        self.MAX_HISTORY_LENGTH: int = self._get_env_int(
            'MAX_HISTORY_LENGTH', 10)

        # Supabase settings
        self.SUPABASE_URL: str = self._get_env('SUPABASE_URL')
        self.SUPABASE_KEY: str = self._get_env('SUPABASE_KEY')

        # Validate settings
        self._validate_settings()

    def _get_env(self, key: str, default: Optional[str] = None) -> str:
        """
        Get environment variable with validation.
        
        Args:
            key: Environment variable key
            default: Default value if not found
            
        Returns:
            str: Environment variable value
            
        Raises:
            ValueError: If required variable is missing
        """
        value = os.getenv(key, default)
        if value is None:
            error_msg = f"Missing required environment variable: {key}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        return value

    def _get_env_bool(self, key: str, default: bool) -> bool:
        """
        Get boolean environment variable.
        
        Args:
            key: Environment variable key
            default: Default value
            
        Returns:
            bool: Environment variable value
        """
        value = os.getenv(key, str(default)).lower()
        return value in ('true', '1', 'yes', 'y', 't')

    def _get_env_int(self, key: str, default: int) -> int:
        """
        Get integer environment variable.
        
        Args:
            key: Environment variable key
            default: Default value
            
        Returns:
            int: Environment variable value
        """
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            logger.warning(
                f"Invalid integer value for {key}, using default: {default}")
            return default

    def _initialize_deepseek(self) -> Optional[ChatOpenAI]:
        """
        Initialize DeepSeek AI model.
        
        Returns:
            Optional[ChatOpenAI]: Initialized DeepSeek model or None if API key is not available
        """
        # Skip initialization if DEEPSEEK_API_KEY is not provided
        if not self.DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY not provided, DeepSeek model will not be available")
            return None
            
        try:
            return ChatOpenAI(
                base_url='https://api.deepseek.com/v1',
                model=self.DEEPSEEK_MODEL,
                api_key=SecretStr(self.DEEPSEEK_API_KEY),
            )
        except Exception as e:
            logger.error(f"Error initializing DeepSeek: {e}")
            return None  # Return None instead of raising exception

    def _validate_settings(self) -> None:
        """
        Validate all settings are properly configured.
        
        Raises:
            ValueError: If validation fails
        """
        required_settings = [
            ('BOT_TOKEN', self.BOT_TOKEN),
            ('OPENAI_API_KEY', self.OPENAI_API_KEY),
            ('STEEL_API_KEY', self.STEEL_API_KEY),
            ('SUPABASE_URL', self.SUPABASE_URL),
            ('SUPABASE_KEY', self.SUPABASE_KEY),
            ('OPENROUTER_API_KEY', self.OPENROUTER_API_KEY),
        ]

        # Add webhook URL validation only if webhook mode is enabled
        if self.USE_WEBHOOK and not self.WEBHOOK_URL:
            # Instead of failing, set a default webhook URL for Railway deployments
            default_url = "https://railway-service.up.railway.app"
            logger.warning(f"WEBHOOK_URL not set. Using default URL: {default_url}")
            self.WEBHOOK_URL = default_url

        for name, value in required_settings:
            if not value:
                error_msg = f"Missing required setting: {name}"
                logger.error(error_msg)
                raise ValueError(error_msg)

    def get_browser_config(self) -> dict:
        """
        Get browser configuration dictionary.
        
        Returns:
            dict: Browser configuration
        """
        return {
            'headless': self.BROWSER_HEADLESS,
            'browserless': self.BROWSER_BROWSERLESS,
            'browserless_url': self.BROWSERLESS_URL,
        }

    def get_timeout_config(self) -> dict:
        """
        Get timeout configuration dictionary.
        
        Returns:
            dict: Timeout configuration
        """
        return {
            'search_timeout': self.SEARCH_TIMEOUT,
            'max_retries': self.MAX_RETRIES,
        }
        
    def get_webhook_config(self) -> dict:
        """
        Get webhook configuration dictionary.
        
        Returns:
            dict: Webhook configuration
        """
        return {
            'use_webhook': self.USE_WEBHOOK,
            'webhook_url': self.WEBHOOK_URL,
            'webhook_port': self.WEBHOOK_PORT,
            'webhook_path': self.WEBHOOK_PATH,
        }
