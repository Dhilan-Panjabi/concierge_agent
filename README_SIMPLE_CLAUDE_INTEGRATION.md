# Claude 3.7 Sonnet Integration for Browser Tasks

This guide explains how to use Claude 3.7 Sonnet via OpenRouter for browser automation tasks such as availability checking and bookings.

## Overview

The integration uses Claude 3.7 Sonnet with the browser-use library through LangChain's ChatOpenAI class by connecting to OpenRouter's API. This approach provides excellent performance for browser automation tasks while maintaining a simple implementation.

## Setup Requirements

### API Keys
- **OpenRouter API Key**: Used to access Claude 3.7 via OpenRouter
- **Steel Browser API Key**: For browser automation through browser-use library

### Environment Variables
Add these to your `.env` file:
```
OPENROUTER_API_KEY=your_openrouter_api_key_here
STEEL_API_KEY=your_steel_api_key_here
```

### Required Packages
```
pip install langchain langchain_openai browser-use httpx python-dotenv
```

## Basic Usage

### Initializing Claude with OpenRouter
```python
from langchain_openai import ChatOpenAI

claude_llm = ChatOpenAI(
    model="anthropic/claude-3-sonnet-20240229",
    openai_api_key="your_openrouter_api_key",
    openai_api_base="https://openrouter.ai/api/v1",
    max_tokens=4096
)
```

### Creating a Browser Agent
```python
from browser_use import Agent, BrowserConfig

# Configure browser options
browser_config = BrowserConfig(
    headless=True,
    connection_url="https://www.steel.net"
)

# Initialize browser
browser = await create_browser_with_retry(browser_config)

# Create a task instruction
task = "Check for dinner availability at Hawksmoor in London for tomorrow night for 2 people. Look for open time slots between 7-9pm."

# Create an agent with Claude 3.7
agent = Agent(task=task, llm=claude_llm, browser=browser)

# For booking tasks, include sensitive data
sensitive_data = {
    "user_name": "John Smith",
    "user_email": "john.smith@example.com",
    "user_phone": "07700 900123"
}

# Create an agent with sensitive data for bookings
booking_agent = Agent(task=booking_task, llm=claude_llm, browser=browser, sensitive_data=sensitive_data)
```

## Smart Booking Flow

The system implements an intelligent conversation flow that keeps track of what information has been provided throughout the conversation and only asks for information that is still missing.

### Expected Conversation Flow

1. **User asks about availability:**
   ```
   User: "Could you check if Hawksmoor is available tomorrow night for 2 people?"
   ```

2. **Bot responds with available times, price info, and a direct booking link:**
   ```
   Bot: "I checked Hawksmoor Air Street for tomorrow night and they have several tables available for 2 people! They have slots at 7:30pm, 8:00pm, and 9:15pm.

   They're known for their steaks with mains ranging from £26-£40. They also have a pre-theater menu for £35 if you book before 6:30pm.

   You can book directly here: https://www.opentable.co.uk/hawksmoor-air-street

   Would you like me to book a table for you? Just let me know which time works best! 😊"
   ```

3. **User confirms booking with or without specifying a time:**
   ```
   User: "Yes, book the 8:00pm slot please"
   ```
   or
   ```
   User: "Book it please"
   ```

4. **Bot intelligently determines what information is still needed:**
   
   If time was not specified:
   ```
   Bot: "Which time would you prefer? Available slots are 7:30pm, 8:00pm, and 9:15pm."
   ```
   
   If user has a saved profile:
   ```
   Bot: "Great! I'll book a table at Hawksmoor Air Street for 2 people tomorrow at 8:00pm. I'll use your saved contact information."
   ```
   
   If user doesn't have a profile:
   ```
   Bot: "Perfect! I'll book a table at Hawksmoor Air Street for 2 people tomorrow at 8:00pm. Now I need your contact details. What's your name?"
   ```

5. **Bot collects any missing information and confirms booking:**
   ```
   Bot: "Your table at Hawksmoor Air Street is confirmed for tomorrow at 8:00pm for 2 people. You'll receive a confirmation email shortly!"
   ```

### Smart Booking Features

1. **Conversation Memory**
   - The system remembers details mentioned earlier in the conversation
   - Extracts restaurant name, party size, date, and available times
   - Won't ask for information that was already provided

2. **Intelligent Information Extraction**
   - Parses natural language inputs to extract booking details
   - Understands references like "first option" or "earliest time" 
   - Recognizes time formats like "8pm" or "7:30 PM"

3. **Profile Integration**
   - Uses saved profiles to avoid asking for contact details
   - Only asks for specific missing information

4. **Smart Confirmation Process**
   - Clearly summarizes the booking details before processing
   - Provides user-friendly confirmation messages once booking is complete

## Testing

To test the integration, run the test script:
```
python test/claude_browser_test.py
```

The script demonstrates how Claude 3.7 handles browser automation for a restaurant availability check and displays examples of different booking flows.

## Troubleshooting

- **API Key Issues**: Verify your OpenRouter and Steel API keys are correct and properly set in the environment
- **Browser Initialization Failures**: Check your internet connection or try with `headless=False` to see what's happening
- **Unexpected Behavior**: Enable debug logging to see more details about the execution flow
- **Missing Information**: Ensure you're providing all the required information for booking (restaurant, date, time, party size, contact details)

## Example Bot Response for Availability

```
I checked Hawksmoor Air Street for tomorrow night and they have several tables available for 2 people! They have slots at 7:30pm, 8:00pm, and 9:15pm.

They're known for their steaks with mains ranging from £26-£40. They also have a pre-theater menu for £35 if you book before 6:30pm.

You can book directly here: https://www.opentable.co.uk/hawksmoor-air-street

Would you like me to book a table for you? Just let me know which time works best! 😊
``` 