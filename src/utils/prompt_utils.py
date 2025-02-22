"""
Utilities for generating and managing prompts.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptUtils:
    """Handles prompt generation and management"""

    @staticmethod
    def generate_search_prompt(query: str, context: Optional[str] = None) -> str:
        """
        Generates a search prompt with context.
        
        Args:
            query: Search query
            context: Optional context
            
        Returns:
            str: Generated prompt
        """
        base_prompt = f"""
        TASK: Find real-time information for: "{query}"
        
        TIME LIMIT: 90 seconds total
        
        SEARCH STEPS:
        1. [20s] Quick search on Google for best options
        2. [30s] Check official websites/platforms
        3. [20s] Verify current information
        4. [20s] Get booking details
        
        FORMAT RESULTS:
        1. OPTIONS FOUND
        2. IMPORTANT INFO
        3. BOOKING OPTIONS
        """

        if context:
            base_prompt = f"Context: {context}\n\n{base_prompt}"

        return base_prompt

    @staticmethod
    def generate_booking_prompt(booking_info: Dict[str, str]) -> str:
        """
        Generates a booking prompt with user information.
        
        Args:
            booking_info: User booking information
            
        Returns:
            str: Generated prompt
        """
        return f"""
        TASK: Make a booking with the following details:
        
        Customer Information:
        - Name: {booking_info.get('name', 'N/A')}
        - Email: {booking_info.get('email', 'N/A')}
        - Phone: {booking_info.get('phone', 'N/A')}
        
        Booking Details:
        {booking_info.get('details', 'No specific details provided')}
        
        TIME LIMIT: 90 seconds
        
        STEPS:
        1. Access booking system
        2. Enter customer details
        3. Confirm availability
        4. Complete reservation
        
        FORMAT RESULTS:
        - Booking confirmation
        - Important details
        - Next steps
        """

    @staticmethod
    def generate_intent_prompt(message: str, history: Optional[str] = None) -> str:
        """
        Generates an intent classification prompt.
        
        Args:
            message: User message
            history: Optional conversation history
            
        Returns:
            str: Generated prompt
        """
        base_prompt = f"""
        Classify this request into exactly one category:
        
        Message: "{message}"
        
        Categories:
        2 - Needs real-time information
        1 - General recommendations
        3 - Direct booking request
        
        Return ONLY the category number.
        """

        if history:
            base_prompt = f"Conversation History:\n{history}\n\n{base_prompt}"

        return base_prompt

    @staticmethod
    def generate_response_format_prompt(content: str) -> str:
        """
        Generates a response formatting prompt.
        
        Args:
            content: Content to format
            
        Returns:
            str: Generated prompt
        """
        return f"""
        Format the following content for user display:
        
        {content}
        
        FORMATTING GUIDELINES:
        1. Clear structure with sections
        2. Highlight key information
        3. Preserve all URLs and contact details
        4. Use bullet points for readability
        5. Keep under 4000 characters
        6. Maintain friendly tone
        
        FORMAT RESULTS:
        1. Main options/findings
        2. Important details
        3. Next steps or booking information
        """
