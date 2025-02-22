"""
Utilities for message handling and user data management.
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from telegram import Update

logger = logging.getLogger(__name__)


@dataclass
class UserData:
    """Structure for storing user data"""
    history: List[Dict[str, str]] = field(default_factory=list)
    booking_info: Dict[str, str] = field(default_factory=dict)
    last_interaction: float = 0.0


class MessageUtils:
    """Handles message processing and user data management"""

    # Store user data in memory
    _user_data: Dict[int, UserData] = {}

    @classmethod
    def init_user_history(cls, user_id: int) -> None:
        """
        Initialize user history if not exists.
        
        Args:
            user_id: User identifier
        """
        if user_id not in cls._user_data:
            cls._user_data[user_id] = UserData()

    @classmethod
    def add_to_history(cls, user_id: int, role: str, content: str) -> None:
        """
        Add message to user history.
        
        Args:
            user_id: User identifier
            role: Message role ('user' or 'assistant')
            content: Message content
        """
        cls.init_user_history(user_id)
        cls._user_data[user_id].history.append({
            "role": role,
            "content": content
        })
        # Keep only last 10 messages
        cls._user_data[user_id].history = cls._user_data[user_id].history[-10:]

    @classmethod
    def get_user_history(cls, user_id: int) -> List[Dict[str, str]]:
        """
        Get user conversation history.
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Dict[str, str]]: Conversation history
        """
        cls.init_user_history(user_id)
        return cls._user_data[user_id].history

    @classmethod
    def store_booking_info(cls, user_id: int, field: str, value: str) -> None:
        """
        Store booking information for user.
        
        Args:
            user_id: User identifier
            field: Field name
            value: Field value
        """
        cls.init_user_history(user_id)
        cls._user_data[user_id].booking_info[field] = value

    @classmethod
    def get_booking_info(cls, user_id: int) -> Dict[str, str]:
        """
        Get stored booking information.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict[str, str]: Booking information
        """
        cls.init_user_history(user_id)
        return cls._user_data[user_id].booking_info

    @staticmethod
    async def send_long_message(update: Update, text: str, max_length: int = 4000) -> None:
        """
        Splits and sends long messages within Telegram's character limit.
        
        Args:
            update: Telegram update object
            text: Message text
            max_length: Maximum message length
        """
        try:
            if not text:
                logger.warning("Attempted to send empty message")
                return

            text = str(text)
            if len(text) <= max_length:
                await update.message.reply_text(text)
                return

            parts = MessageUtils._split_message(text, max_length)
            await MessageUtils._send_message_parts(update, parts)

        except Exception as e:
            logger.error(f"Error in send_long_message: {e}", exc_info=True)
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
