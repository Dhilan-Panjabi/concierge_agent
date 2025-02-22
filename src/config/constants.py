"""
Application constants and enums.
"""
from enum import Enum
from typing import Dict, List


class ConversationState(Enum):
    """Conversation states for the bot"""
    NAME = 0
    EMAIL = 1
    PHONE = 2
    CONFIRMATION_CODE = 3


class IntentType(Enum):
    """User intent types"""
    GENERAL_RECOMMENDATION = "1"
    REALTIME_SEARCH = "2"
    DIRECT_BOOKING = "3"


class MessageType(Enum):
    """Message types for history"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Prompt templates
PROMPT_TEMPLATES: Dict[str, str] = {
    "search": """
    TASK: Find real-time information for: "{query}"
    TIME LIMIT: {timeout} seconds total
    
    SEARCH STEPS:
    1. [{step1_time}s] Quick search on Google for best options
    2. [{step2_time}s] Check official websites/platforms
    3. [{step3_time}s] Verify current information
    4. [{step4_time}s] Get booking details
    
    FORMAT RESULTS:
    1. OPTIONS FOUND
    2. IMPORTANT INFO
    3. BOOKING OPTIONS
    """,

    "booking": """
    TASK: Make a booking for: "{query}"
    TIME LIMIT: {timeout} seconds
    
    STEPS:
    1. Access booking system
    2. Enter required details
    3. Complete reservation
    
    FORMAT RESULTS:
    - Booking confirmation
    - Important details
    - Next steps
    """
}

# Error messages
ERROR_MESSAGES: Dict[str, str] = {
    "general": "Sorry, I encountered an error. Please try again.",
    "booking": "Sorry, there was an error with the booking process.",
    "search": "Sorry, I couldn't complete the search. Please try again.",
    "timeout": "The operation timed out. Please try again.",
    "validation": "Please provide valid information.",
}

# Booking fields
REQUIRED_BOOKING_FIELDS: List[str] = ['name', 'email', 'phone']

# Time constants
TIMEOUT_SEARCH: int = 90
TIMEOUT_BOOKING: int = 60
MESSAGE_DELAY: float = 0.5
