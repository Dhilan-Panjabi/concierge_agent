"""
Test script for Claude 3.7 browser integration with booking flow.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def test_claude_browser():
    """Test Claude 3.7 browser integration with practical booking flow."""
    try:
        # Configure Claude model via OpenRouter
        claude_llm = ChatOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-3-7-sonnet-20250219",
            temperature=0.1
        )
        
        # Configure browser
        browser_config = BrowserConfig(
            headless=True,
            cdp_url=f'wss://connect.steel.dev?apiKey={os.environ.get("STEEL_API_KEY")}'
        )
        
        # Initialize browser
        browser = Browser(browser_config)
        logger.info("Browser initialized")
        
        # Define sensitive booking information
        sensitive_data = {
            'user_name': 'John Smith',
            'user_email': 'john.smith@example.com',
            'user_phone': '+1 555-123-4567',
        }
        
        # Define test task - Real-world example task that includes finding a booking link
        test_task = """
        Check if Hawksmoor Air Street in London has availability tomorrow night for 2 people.

        Steps:
        1. Search for "Hawksmoor Air Street London reservation"
        2. Find their booking page (likely OpenTable or their own reservation system)
        3. Check availability for tomorrow at 7:30pm for 2 people
        4. Record ALL available time slots for tomorrow evening
        5. Get the DIRECT BOOKING LINK that would allow someone to make a reservation
        6. Note the price range if visible
        7. Check if there are any special offers or deals available

        Important: 
        - Make sure to find and include the EXACT BOOKING URL in your response
        - The response should be formatted for a chat conversation with a customer
        - Make sure to offer to book the reservation directly for the customer
        - Be casual and friendly, like you're texting a friend
        """
        
        logger.info("Starting Claude browser test with practical booking flow")
        
        # Create agent with sensitive data
        agent = Agent(
            task=test_task,
            llm=claude_llm,
            browser=browser,
            sensitive_data=sensitive_data
        )
        
        # Run agent
        logger.info("Running browser agent")
        result = await agent.run()
        
        # Process result
        logger.info(f"Test completed. Result:\n{result}")
        
        # Cleanup browser
        await browser.close()
        logger.info("Browser closed")
        
        return result
    
    except Exception as e:
        logger.error(f"Error in Claude browser test: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        result = asyncio.run(test_claude_browser())
        print("\n=== TEST RESULT ===")
        print(result)
        
        # Examples of different intelligent booking flows
        print("\n=== INTELLIGENT BOOKING FLOW EXAMPLES ===")
        
        print("Example 1: User specifies time with existing profile")
        print("User: Could you check if Hawksmoor is available tomorrow night for 2 people?")
        print("Bot: I checked Hawksmoor Air Street for tomorrow night and they have several tables available for 2 people! They have slots at 7:30pm, 8:00pm, and 9:15pm.\n\nThey're known for their steaks with mains ranging from £26-£40. They also have a pre-theater menu for £35 if you book before 6:30pm.\n\nYou can book directly here: https://www.opentable.co.uk/hawksmoor-air-street\n\nWould you like me to book a table for you? Just let me know which time works best! 😊")
        print("User: Yes, book the 8pm slot please")
        print("Bot: Great! I'll book a table at Hawksmoor Air Street for 2 people tomorrow at 8:00pm. I'll use your saved contact information.")
        print("Bot: Your table at Hawksmoor Air Street is confirmed for tomorrow at 8:00pm for 2 people. You'll receive a confirmation email shortly!")
        
        print("\nExample 2: User doesn't specify time (needs to be asked)")
        print("User: Could you check if Hawksmoor is available tomorrow night for 2 people?")
        print("Bot: I checked Hawksmoor Air Street for tomorrow night and they have several tables available for 2 people! They have slots at 7:30pm, 8:00pm, and 9:15pm.\n\nThey're known for their steaks with mains ranging from £26-£40. They also have a pre-theater menu for £35 if you book before 6:30pm.\n\nYou can book directly here: https://www.opentable.co.uk/hawksmoor-air-street\n\nWould you like me to book a table for you? Just let me know which time works best! 😊")
        print("User: Yes, book it please")
        print("Bot: Which time would you prefer? Available slots are 7:30pm, 8:00pm, and 9:15pm.")
        print("User: 9:15pm works better")
        print("Bot: Great! I'll book a table at Hawksmoor Air Street for 2 people tomorrow at 9:15pm. I'll use your saved contact information.")
        print("Bot: Your table at Hawksmoor Air Street is confirmed for tomorrow at 9:15pm for 2 people. You'll receive a confirmation email shortly!")
        
        print("\nExample 3: No saved profile (needs to collect contact info)")
        print("User: Could you check if Hawksmoor is available tomorrow night for 2 people?")
        print("Bot: I checked Hawksmoor Air Street for tomorrow night and they have several tables available for 2 people! They have slots at 7:30pm, 8:00pm, and 9:15pm.\n\nThey're known for their steaks with mains ranging from £26-£40. They also have a pre-theater menu for £35 if you book before 6:30pm.\n\nYou can book directly here: https://www.opentable.co.uk/hawksmoor-air-street\n\nWould you like me to book a table for you? Just let me know which time works best! 😊")
        print("User: Book for 8pm please")
        print("Bot: Perfect! I'll book a table at Hawksmoor Air Street for 2 people tomorrow at 8:00pm. Now I need your contact details. What's your name?")
        print("User: John Smith")
        print("Bot: Great! Now, what's your email?")
        print("User: john.smith@example.com")
        print("Bot: Perfect! And your phone number?")
        print("User: +44 7700 900123")
        print("Bot: Thanks! I'm booking your table at Hawksmoor Air Street for 2 people on Friday, April 19 at 8:00pm. This might take a minute...")
        print("Bot: Your table at Hawksmoor Air Street is confirmed for tomorrow at 8:00pm for 2 people. You'll receive a confirmation email shortly!")
        
    except KeyboardInterrupt:
        print("Test interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}") 