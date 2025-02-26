from browser_use import Agent
import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()


async def main():
    # Configure OpenRouter with Claude 3.7
    llm = ChatOpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        model="anthropic/claude-3-7-sonnet-20250219",
    )

    # Define sensitive booking information
    # The model will only see the keys but not the actual values
    sensitive_data = {
        'user_name': 'Dhilan Panjabi',
        'user_email': 'dhilan@gmail.com',
        'user_phone': '+852 6180 2686',
    }

    # Use placeholder names in the task description
    task = """
    Book me a table at Yardbird in Hong Kong.
    
    1. Find the official Yardbird Hong Kong website
    2. Navigate to their reservation/booking page
    3. Fill out the booking form with my information:
       - Name: user_name
       - Email: user_email
       - Phone: user_phone
       - Party size: 2
       - Date: tomorrow
       - Time: 9pm
    4. Complete the booking process
    5. Confirm the booking details
    """

    # Create the agent with sensitive data
    agent = Agent(
        task=task,
        llm=llm,
        sensitive_data=sensitive_data
    )

    # Run the agent
    result = await agent.run(max_steps=18)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
