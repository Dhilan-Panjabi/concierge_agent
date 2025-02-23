"""
Database service using Supabase for data persistence.
"""
import logging
from typing import Dict, Any, Optional, List
import asyncio
from supabase import create_client, Client

from src.config.settings import Settings

logger = logging.getLogger(__name__)

class SupabaseService:
    """Handles all database operations using Supabase"""

    _instance = None
    _client: Optional[Client] = None

    def __new__(cls, settings: Settings):
        if cls._instance is None:
            cls._instance = super(SupabaseService, cls).__new__(cls)
            cls._instance.settings = settings
            cls._instance._initialize_client()
        return cls._instance

    def _initialize_client(self) -> None:
        """Initialize Supabase client"""
        try:
            self._client = create_client(
                self.settings.SUPABASE_URL,
                self.settings.SUPABASE_KEY
            )
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}", exc_info=True)
            raise

    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Get user profile from database"""
        try:
            response = await asyncio.to_thread(
                lambda: self._client.table('user_profiles').select('*').eq('user_id', user_id).execute()
            )
            if response.data:
                return response.data[0]
            return {}
        except Exception as e:
            logger.error(f"Error getting user profile: {e}", exc_info=True)
            return {}

    async def set_user_profile(self, user_id: int, profile_data: Dict[str, Any]) -> None:
        """Set or update user profile"""
        try:
            existing = await self.get_user_profile(user_id)
            if existing:
                await asyncio.to_thread(
                    lambda: self._client.table('user_profiles').update(profile_data).eq('user_id', user_id).execute()
                )
            else:
                profile_data['user_id'] = user_id
                await asyncio.to_thread(
                    lambda: self._client.table('user_profiles').insert(profile_data).execute()
                )
        except Exception as e:
            logger.error(f"Error setting user profile: {e}", exc_info=True)

    async def delete_user_profile(self, user_id: int) -> None:
        """Delete user profile"""
        try:
            await asyncio.to_thread(
                lambda: self._client.table('user_profiles').delete().eq('user_id', user_id).execute()
            )
        except Exception as e:
            logger.error(f"Error deleting user profile: {e}", exc_info=True)

    async def get_user_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user conversation history"""
        try:
            response = await asyncio.to_thread(
                lambda: self._client.table('chat_history').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(50).execute()
            )
            return response.data
        except Exception as e:
            logger.error(f"Error getting chat history: {e}", exc_info=True)
            return []

    async def add_to_history(self, user_id: int, role: str, content: str) -> None:
        """Add message to chat history"""
        try:
            await asyncio.to_thread(
                lambda: self._client.table('chat_history').insert({
                    'user_id': user_id,
                    'role': role,
                    'content': content
                }).execute()
            )
        except Exception as e:
            logger.error(f"Error adding to chat history: {e}", exc_info=True)

    async def get_booking_info(self, user_id: int) -> Dict[str, Any]:
        """Get user's current booking information"""
        try:
            response = await asyncio.to_thread(
                lambda: self._client.table('booking_info').select('*').eq('user_id', user_id).is_('completed', False).execute()
            )
            if response.data:
                return response.data[0]
            return {}
        except Exception as e:
            logger.error(f"Error getting booking info: {e}", exc_info=True)
            return {}

    async def set_booking_info(self, user_id: int, field: str, value: str) -> None:
        """Set booking information field"""
        try:
            booking_info = await self.get_booking_info(user_id)
            if booking_info:
                await asyncio.to_thread(
                    lambda: self._client.table('booking_info').update({field: value}).eq('id', booking_info['id']).execute()
                )
            else:
                await asyncio.to_thread(
                    lambda: self._client.table('booking_info').insert({
                        'user_id': user_id,
                        field: value,
                        'completed': False
                    }).execute()
                )
        except Exception as e:
            logger.error(f"Error setting booking info: {e}", exc_info=True)

    async def clear_booking_info(self, user_id: int) -> None:
        """Clear current booking information"""
        try:
            await asyncio.to_thread(
                lambda: self._client.table('booking_info').update({'completed': True}).eq('user_id', user_id).is_('completed', False).execute()
            )
        except Exception as e:
            logger.error(f"Error clearing booking info: {e}", exc_info=True) 