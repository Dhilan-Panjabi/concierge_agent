"""
AI service for natural language processing and response generation.
"""
import logging
import json
import asyncio
from typing import Optional, List, Dict

from openai import OpenAI
from src.config.settings import Settings
from src.utils.message_utils import MessageUtils

logger = logging.getLogger(__name__)


class AIService:
    """Handles all AI-related tasks"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.message_utils = MessageUtils()

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
            history = await self._get_user_history(user_id)
            context = self._format_history_context(history)

            prompt = f"""
            {context}
            
            Current message: "{message}"
            
            Classify this request into exactly one category by returning ONLY its number:
            2 - If the request needs real-time information (sports games, current availability, what's happening now)
            1 - If it's only asking for general recommendations without needing current information
            3 - If it's specifically about making a booking
            4 - If it's a profile management request (update profile, view profile, etc.)
            
            Examples:
            "What's a good Italian restaurant?" -> 2
            "Where can I watch the game tonight?" -> 2
            "Find me a bar showing hockey" -> 2
            "Make a reservation" -> 3
            "Update my profile" -> 4
            
            Return ONLY the number (1, 2, 3, or 4). Do not include any other text or explanation.
            """

            response = await self._get_ai_response(prompt)
            return response.strip()

        except Exception as e:
            logger.error(f"Error classifying intent: {e}", exc_info=True)
            return "2"  # Default to search intent on error

    async def format_response(self, user_request: str, agent_result: str, user_id: int = 1) -> str:
        """
        Formats the agent's result into a user-friendly response.
        
        Args:
            user_request: Original user request
            agent_result: Result from browser agent
            user_id: User identifier for retrieving conversation context
            
        Returns:
            str: Formatted response
        """
        try:
            # Get conversation history for context
            history = await self._get_user_history(user_id)
            context = self._format_history_context(history)
            
            # Check if this is an availability search response that should offer booking
            is_availability_search = any(term in user_request.lower() for term in 
                ['available', 'availability', 'reservation', 'book', 'free', 'slot'])
            has_booking_link = 'http' in agent_result and any(domain in agent_result.lower() for domain in 
                ['opentable', 'resy', 'bookatable', 'sevenrooms', 'tock'])
            
            # Special instructions for availability responses
            booking_instruction = ""
            if is_availability_search and has_booking_link:
                booking_instruction = """
                IMPORTANT BOOKING FLOW REQUIREMENTS:
                1. Make sure to clearly include the DIRECT BOOKING LINK in your response
                2. End your response by explicitly offering to book on behalf of the user with text like:
                   "Would you like me to book a table for you? Just let me know which time works best!"
                3. If the user has previously saved their details, mention that you'll use those details
                """
            
            prompt = f"""
            {context}
            
            CURRENT USER REQUEST: {user_request}
            
            SEARCH RESULTS: {agent_result}
            
            {booking_instruction}
            
            FORMAT GUIDELINES:
            1. Response Style:
               - Write like you're texting a friend - casual and conversational
               - Use a friendly tone with occasional emojis where appropriate
               - Keep sentences shorter like in text messages
               - Use contractions (don't, I'll, there's)
            
            2. Content Structure:
               - Start with a brief overview of availability
               - Mention 2-3 room options with prices
               - Note any special deals or important policies
               - Include booking info but keep it brief
               - ALWAYS include any booking links that are in the search results
            
            3. Formatting:
               - Avoid formal bullet points or numbered lists
               - Use natural breaks between topics
               - Bold only the most essential info (like prices)
               - Keep paragraphs short - 1-3 sentences max
            
            4. End with:
               - A simple question to continue the conversation
               - If this is an availability check, offer to book on their behalf
            
            IMPORTANT: 
            - Make it feel like a helpful friend texting, not a formal report
            - Include accurate pricing and availability from the search results
            - Don't use formal headers or sections
            - MAINTAIN CONTEXT from previous conversation - if the user is asking about "the third place" or "that hotel", 
              use the conversation history to determine which specific place they're referring to
            - If there are any booking links in the search results, ALWAYS include them in your response
            
            Overall, make your response feel like a text message conversation while still including the key information.
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

    async def _get_user_history(self, user_id: str) -> List[Dict[str, str]]:
        """
        Gets user conversation history.
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Dict[str, str]]: Conversation history
        """
        history = await self.message_utils.get_user_history(int(user_id))
        return history[-5:] if history else []  # Last 5 messages

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

    async def get_recommendations(self, query: str, user_id: int) -> str:
        """
        Gets recommendations using GPT without browser automation.
        
        Args:
            query: User query for recommendations
            user_id: User identifier for retrieving conversation context
            
        Returns:
            str: Formatted recommendations
        """
        try:
            # Get conversation history for context
            history = await self._get_user_history(user_id)
            context = self._format_history_context(history)

            prompt = f"""
            {context}
            
            Current request: "{query}"
            
            You are a friendly booking assistant texting with a user. The user is asking for recommendations.
            
            IMPORTANT: Use the conversation CONTEXT above to maintain continuity. If the user previously mentioned a location 
            and is now just specifying a cuisine type or activity, ALWAYS recommend places in the previously mentioned location.
            
            For example, if they first asked about restaurants in Boston, and then said "I'm more in the mood for Japanese", 
            you should recommend Japanese restaurants in Boston, not in any other city.
            
            Provide casual, conversational recommendations as if you're texting a friend. Follow these guidelines:
            1. Keep it brief but informative (like a text message)
            2. Use a casual, friendly tone with occasional emojis
            3. For each option include only the most essential details:
               - Name
               - Quick 1-line description
               - Price ($ to $$$$)
               - 1-2 standout features
               - Location (ensuring it matches the context of the conversation)
            4. Don't use formal formatting like bullet points or sections
            5. Use natural texting language (shorter sentences, contractions, etc.)
            6. End with a quick question to keep the conversation going
            
            Make sure your response reads like a text message from a knowledgeable friend rather than a formal recommendation.
            """

            response = await self._get_ai_response(prompt)
            return response.strip()

        except Exception as e:
            logger.error(f"Error getting recommendations: {e}", exc_info=True)
            return "Sorry, I hit a snag getting those recommendations. Mind trying again?"
