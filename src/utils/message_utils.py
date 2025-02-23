"""
Message utilities for handling user data and messages.
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from telegram import Update
from src.services.supabase_service import SupabaseService
from src.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class UserData:
    """Structure for storing user data"""
    history: List[Dict[str, str]] = field(default_factory=list)
    booking_info: Dict[str, str] = field(default_factory=dict)
    last_interaction: float = 0.0


class MessageUtils:
    """Utility class for handling messages and user data"""

    _instance = None
    _user_data: Dict[int, Dict[str, Any]] = {}  # Cache for current session

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MessageUtils, cls).__new__(cls)
            cls._instance.settings = Settings()
            cls._instance.db = SupabaseService(cls._instance.settings)
        return cls._instance

    @classmethod
    async def init_user_history(cls, user_id: int) -> None:
        """Initialize user history if not exists"""
        if user_id not in cls._user_data:
            cls._user_data[user_id] = {
                'history': await cls._instance.db.get_user_history(user_id),
                'booking_info': await cls._instance.db.get_booking_info(user_id),
                'has_seen_greeting': False,
                'profile': await cls._instance.db.get_user_profile(user_id)
            }

    @classmethod
    async def should_show_greeting(cls, user_id: int) -> bool:
        """Check if greeting should be shown and mark as shown"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        
        # Only show greeting if user has no history and hasn't seen it before
        has_history = bool(cls._user_data[user_id].get('history', []))
        has_seen_greeting = cls._user_data[user_id].get('has_seen_greeting', False)
        
        should_show = not has_history and not has_seen_greeting
        
        if should_show:
            cls._user_data[user_id]['has_seen_greeting'] = True
            
        return should_show

    @classmethod
    async def add_to_history(cls, user_id: int, role: str, content: str) -> None:
        """Add message to user history"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        
        # Add to cache
        if 'history' not in cls._user_data[user_id]:
            cls._user_data[user_id]['history'] = []
        cls._user_data[user_id]['history'].append({
            'role': role,
            'content': content
        })
        
        # Add to database
        await cls._instance.db.add_to_history(user_id, role, content)

    @classmethod
    async def get_user_history(cls, user_id: int) -> List[Dict[str, str]]:
        """Get user conversation history"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        return cls._user_data[user_id].get('history', [])

    @classmethod
    async def get_user_profile(cls, user_id: int) -> Dict[str, str]:
        """Get user profile information"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        return cls._user_data[user_id].get('profile', {})

    @classmethod
    async def set_user_profile(cls, user_id: int, field: str, value: str) -> None:
        """Set user profile field"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        
        # Update cache
        if 'profile' not in cls._user_data[user_id]:
            cls._user_data[user_id]['profile'] = {}
        cls._user_data[user_id]['profile'][field] = value
        
        # Update database
        await cls._instance.db.set_user_profile(user_id, cls._user_data[user_id]['profile'])

    @classmethod
    async def clear_user_profile(cls, user_id: int) -> None:
        """Clear user profile"""
        if user_id in cls._user_data:
            cls._user_data[user_id]['profile'] = {}
        await cls._instance.db.delete_user_profile(user_id)

    @classmethod
    async def get_booking_info(cls, user_id: int) -> Dict[str, str]:
        """Get user booking information"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        return cls._user_data[user_id].get('booking_info', {})

    @classmethod
    async def set_booking_info(cls, user_id: int, field: str, value: str) -> None:
        """Set booking information field"""
        if user_id not in cls._user_data:
            await cls.init_user_history(user_id)
        
        # Update cache
        if 'booking_info' not in cls._user_data[user_id]:
            cls._user_data[user_id]['booking_info'] = {}
        cls._user_data[user_id]['booking_info'][field] = value
        
        # Update database
        await cls._instance.db.set_booking_info(user_id, field, value)

    @classmethod
    async def clear_booking_info(cls, user_id: int) -> None:
        """Clear booking information"""
        if user_id in cls._user_data:
            cls._user_data[user_id]['booking_info'] = {}
        await cls._instance.db.clear_booking_info(user_id)

    @staticmethod
    async def send_long_message(update: Update, text: str, max_length: int = 4000) -> None:
        """Send long messages in chunks if needed"""
        try:
            if not text:
                logger.warning("Attempted to send empty message")
                return

            text = str(text)
            if len(text) <= max_length:
                await update.message.reply_text(text)
                return

            # Split message into parts
            parts = []
            while text:
                if len(text) <= max_length:
                    parts.append(text)
                    break

                split_point = text.rfind('\n', 0, max_length)
                if split_point == -1:
                    split_point = text.rfind('. ', 0, max_length)
                if split_point == -1:
                    split_point = max_length

                parts.append(text[:split_point])
                text = text[split_point:].strip()

            # Send each part
            for i, part in enumerate(parts):
                if len(parts) > 1:
                    indicator = f"(Part {i+1}/{len(parts)})\n\n"
                    await update.message.reply_text(indicator + part)
                else:
                    await update.message.reply_text(part)

        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            await update.message.reply_text(
                "Sorry, I encountered an error sending the response."
            )

    @staticmethod
    def _split_message(text: str, max_length: int) -> List[str]:
        """
        Splits message into parts based on max length.
        
        Args:
            text: Message text
            max_length: Maximum length per part
            
        Returns:
            List[str]: Message parts
        """
        parts = []
        while text:
            if len(text) <= max_length:
                parts.append(text)
                break

            # Find the last complete sentence or line within the limit
            split_point = text.rfind('\n', 0, max_length)
            if split_point == -1:
                split_point = text.rfind('. ', 0, max_length)
            if split_point == -1:
                split_point = text.rfind(' ', 0, max_length)
            if split_point == -1:
                split_point = max_length

            parts.append(text[:split_point].strip())
            text = text[split_point:].strip()

        return parts

    @staticmethod
    async def _send_message_parts(update: Update, parts: List[str]) -> None:
        """
        Sends message parts with proper formatting.
        
        Args:
            update: Telegram update object
            parts: Message parts to send
        """
        for i, part in enumerate(parts):
            try:
                if len(parts) > 1:
                    indicator = f"(Part {i+1}/{len(parts)})\n\n"
                    await update.message.reply_text(indicator + part)
                else:
                    await update.message.reply_text(part)
                # Add small delay between messages to prevent rate limiting
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(
                    f"Error sending message part {i+1}: {e}", exc_info=True)
