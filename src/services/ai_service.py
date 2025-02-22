"""
AI service for natural language processing and response generation.
"""
import logging
import json
import asyncio
from typing import Optional, List, Dict

from openai import OpenAI
from src.config.settings import Settings

logger = logging.getLogger(__name__)


class AIService:
    """Handles all AI-related tasks"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def classify_intent(self, message: str, user_id: str) -> str:
        """
        Classifies user message intent.
        
        Args:
            message: User message
            user_id: User identifier
            
        Returns:
            str: Classified intent
        """
        try:
            history = self._get_user_history(user_id)
            context = self._format_history_context(history)

            prompt = f"""
            {context}
            
            Current message: "{message}"
            
            Classify this request into exactly one category by returning ONLY its number:
            2 - If the request needs real-time information (sports games, current availability, what's happening now)
            1 - If it's only asking for general recommendations without needing current information
            3 - If it's specifically about making a booking
            
            Examples:
            "What's a good Italian restaurant?" -> 2
            "Where can I watch the game tonight?" -> 2
            "Find me a bar showing hockey" -> 2
            "Make a reservation" -> 3
            
            Return ONLY the number (1, 2, or 3). Do not include any other text or explanation.
            """

            response = await self._get_ai_response(prompt)
            return response.strip()

        except Exception as e:
            logger.error(f"Error classifying intent: {e}", exc_info=True)
            return "2"  # Default to search intent on error

    async def format_response(self, user_request: str, agent_result: str) -> str:
        """
        Formats the agent's result into a user-friendly response.
        
        Args:
            user_request: Original user request
            agent_result: Result from browser agent
            
        Returns:
            str: Formatted response
        """
        try:
            prompt = f"""
            USER REQUEST: {user_request}
            
            SEARCH RESULTS: {agent_result}
            
            FORMAT GUIDELINES:
            1. Structure the response clearly with sections
            2. Highlight key information (prices, times, contact details)
            3. Include all URLs and contact information exactly as provided
            4. Add helpful context where needed
            5. Keep the tone friendly and helpful
            6. Use bullet points for better readability
            7. Keep total response under 4000 characters when possible
            
            IMPORTANT:
            - Keep all URLs and contact information intact
            - Maintain accuracy of prices and availability
            - Include booking instructions if relevant
            """

            response = await self._get_ai_response(prompt)
            return response.strip()

        except Exception as e:
            logger.error(f"Error formatting response: {e}", exc_info=True)
            return str(agent_result)

    async def _get_ai_response(self, prompt: str) -> str:
        """
        Gets response from AI model.
        
        Args:
            prompt: Input prompt
            
        Returns:
            str: AI response
        """
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}]
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error getting AI response: {e}", exc_info=True)
            raise

    def _get_user_history(self, user_id: str) -> List[Dict[str, str]]:
        """
        Gets user conversation history.
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Dict[str, str]]: Conversation history
        """
        from src.utils.message_utils import MessageUtils
        return MessageUtils.get_user_history(user_id)[-5:]  # Last 5 messages

    @staticmethod
    def _format_history_context(history: List[Dict[str, str]]) -> str:
        """
        Formats conversation history into context string.
        
        Args:
            history: Conversation history
            
        Returns:
            str: Formatted context
        """
        if not history:
            return ""

        context = "\nPrevious conversation:\n"
        context += "\n".join(
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in history
        )
        return context

    async def get_recommendations(self, query: str) -> str:
        """
        Gets recommendations using GPT without browser automation.
        
        Args:
            query: User query for recommendations
            
        Returns:
            str: Formatted recommendations
        """
        try:
            prompt = f"""
            You are a knowledgeable travel and hospitality assistant. The user is asking for recommendations.
            
            USER REQUEST: "{query}"
            
            Provide detailed recommendations following these guidelines:
            1. Suggest 3-4 specific options
            2. For each option include:
               - Name and brief description
               - Price range ($, $$, $$$, $$$$)
               - Known for / Highlights
               - Location/Area
               - Best for (type of traveler/occasion)
            3. Keep the tone friendly and conversational
            4. Format with clear sections and bullet points
            5. End with a note offering to check real-time availability
            
            Focus on providing accurate, helpful information without real-time data.
            """

            response = await self._get_ai_response(prompt)
            return response.strip()

        except Exception as e:
            logger.error(f"Error getting recommendations: {e}", exc_info=True)
            return "I apologize, but I encountered an error while getting recommendations. Please try again."
