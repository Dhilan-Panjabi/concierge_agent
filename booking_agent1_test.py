from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
import openai
import asyncio
import os
from dotenv import load_dotenv
from browser_use import ActionResult, Agent, Controller
from browser_use.browser.context import BrowserContext
from browser_use.browser.browser import Browser, BrowserConfig
from langchain_openai import ChatOpenAI
import json
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI API client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

controller = Controller()

# Initialize browser automation
browser = Browser(BrowserConfig(headless=True))

# Store user details and conversation history
user_data = {}

# --- 🔄 INITIALIZATION FUNCTIONS ---


def init_user_history(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'history': [],
            'last_recommendations': None
        }

# --- 🧠 AI PROMPT GENERATION ---


async def generate_browser_task_prompt(user_message: str, intent: str) -> str:
    """
    Generates a browser-use compatible task prompt for any concierge request.
    """
    system_prompt = f"""
    You are a prompt engineer for a web automation system.
    
    User message: "{user_message}"
    Intent: {intent}

    Create a specific browser automation task that:
    1. Identifies the exact type of request (restaurant booking, hotel reservation, event tickets, etc.)
    2. Extracts all relevant details (dates, times, people, preferences, price ranges)
    3. Formats it into a clear, direct browser instruction

    Examples of good task prompts below but make it more detailed for the browser-use not to waste tokens:
    - "check the availability for nobu malibu for 2 people on the 18th for sometime in the 2 oclock go on their reservation site, change the date to given date and time to given time and see what they have availables"
    - "search for 5-star hotels in paris under 300 euros per night for 2 adults from march 15-20"
    - "find concert tickets for taylor swift eras tour in london between 100-200 pounds in august"
    - "look for business class flights from new york to tokyo departing june 5-7 under 3000 dollars"

    Return ONLY the task prompt. No explanations or additional text.
    Make it specific enough for a browser to follow but natural enough for an AI to understand.
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )

    return response.choices[0].message.content.strip()
# --- 🎯 INTENT CLASSIFICATION ---


async def classify_user_request(message):
    prompt = f"""
    The user sent this message: "{message}"
    
    Classify the intent into one of these categories:
    1. Recommendation Request
    2. Availability Check
    3. Booking Request
    4. General Inquiry

    Respond only with the category number (1, 2, 3, or 4).
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip().split(".")[0]

# --- 🔍 AVAILABILITY CHECKING ---


async def format_reply_for_user(user_request: str, agent_result: str) -> str:
    """
    Formats the agent's result into a natural, concierge-style response.
    """
    prompt = f"""
    You are a professional concierge assistant.
    
    Original user request: "{user_request}"
    Browser agent result: "{agent_result}"

    Create a natural, helpful response that:
    1. Acknowledges the user's request
    2. Provides the information clearly
    3. Suggests next steps if applicable
    4. Maintains a professional but friendly tone
    5. Includes all relevant details (times, dates, contact info)

    Examples of good responses:
    - "I've checked O Ya for you, and I'm happy to say they have availability at 7:30 PM this Friday. Would you like me to help you make a reservation?"
    - "I'm sorry, but Giulia is fully booked for your requested time. The earliest availability is next Tuesday at 6:45 PM. They also accept walk-ins at the bar area. Would you like their contact number to discuss other options?"

    Return ONLY the response message. No additional text or explanations.
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()


async def check_availability_with_browser(user_message: str, update: Update):
    """
    Uses browser automation to check availability and formats response for client.
    """
    try:
        task_prompt = await generate_browser_task_prompt(user_message, "availability_check")
        print(f"DEBUG: Generated task prompt: {task_prompt}")

        agent = Agent(
            task=task_prompt,
            llm=ChatOpenAI(model="gpt-4o")
        )

        result = await agent.run()
        print(f"DEBUG: Agent result: {result}")

        # Format the result into a user-friendly response
        formatted_response = await format_reply_for_user(user_message, result)
        return formatted_response

    except Exception as e:
        print(f"DEBUG: Browser automation error: {str(e)}")
        return "❌ Sorry, I encountered an error checking availability. Please try again."

# --- 📝 BOOKING FUNCTIONS ---


async def book_using_browser_use(user_info):
    """
    Uses browser automation to make a booking.
    """
    task_prompt = await generate_browser_task_prompt(
        f"Book {user_info['restaurant']} for {user_info['people']} people on {user_info['date']} at {user_info['time']}",
        "booking"
    )

    try:
        agent = Agent(
            task=task_prompt,
            llm=ChatOpenAI(model="gpt-4o", temperature=0),
            browser=browser
        )
        result = await agent.run()
        return result
    except Exception as e:
        return f"❌ Booking failed: {str(e)}"

# --- 💡 RECOMMENDATION FUNCTIONS ---
# Define required booking details
REQUIRED_INFO = ["name", "email", "phone", "restaurant",
                 "location", "date", "time", "people", "payment_info"]

# Define conversation states
NAME, EMAIL, PHONE, RESTAURANT, LOCATION, DATE, TIME, PEOPLE, PAYMENT = range(
    9)

async def ask_for_info(update: Update, context: CallbackContext) -> int:
    user_id = update.message.chat_id
    message = update.message.text

    if user_id not in user_data:
        user_data[user_id] = {}

    for field in REQUIRED_INFO:
        if field not in user_data[user_id] or not user_data[user_id][field]:
            user_data[user_id][field] = message
            await update.message.reply_text(f"Got it! Now, please provide your {field.replace('_', ' ')}:")
            return REQUIRED_INFO.index(field) + 1

    booking_result = await book_using_browser_use(user_data[user_id])
    await update.message.reply_text(booking_result)

    return ConversationHandler.END

async def get_ai_recommendation(query, user_id=None):
    context = ""
    if user_id and user_id in user_data:
        history = user_data[user_id]['history'][-5:]
        context = "\nPrevious conversation:\n" + "\n".join(
            [f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" for msg in history]
        )

    prompt = f"""
    The user wants a recommendation. Respond casually.
    {context}
    
    Current request: "{query}"
    
    - Suggest 2-3 specific options with brief reasons
    - Number each option clearly (1., 2., 3.)
    - Be engaging and natural
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

# --- 🎮 MESSAGE HANDLING ---


async def handle_user_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_message = update.message.text

    # Initialize user history
    init_user_history(user_id)

    # Add user message to history
    user_data[user_id]['history'].append(
        {"role": "user", "content": user_message})

    try:
        # Check for references to previous recommendations
        if user_data[user_id]['last_recommendations']:
            reference_prompt = f"""
            Given the previous recommendations:
            {user_data[user_id]['last_recommendations']}
            
            And the user's message: "{user_message}"
            
            If they're referring to one of the recommendations, extract these details in JSON:
            {{
                "restaurant": "exact restaurant name",
                "reference": "which number recommendation (1,2,3)",
                "is_reference": true/false
            }}
            Return only the JSON.
            """

            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o",
                messages=[{"role": "system", "content": reference_prompt}]
            )

            try:
                reference_data = json.loads(
                    response.choices[0].message.content.strip())
                if reference_data.get("is_reference"):
                    print(
                        f"DEBUG: Reference detected for {reference_data['restaurant']}")

                    # Modify user_message to include actual restaurant name
                    user_message = user_message.replace(
                        f"the {reference_data['reference']} restaurant",
                        reference_data['restaurant']
                    ).replace(
                        f"number {reference_data['reference']}",
                        reference_data['restaurant']
                    )
                    print(
                        f"DEBUG: Modified message with context: {user_message}")

            except json.JSONDecodeError:
                print("DEBUG: No reference detected in message")

        # Process request with context-aware message
        intent = await classify_user_request(user_message)
        print(f"DEBUG: Detected intent: {intent}")

        response = None

        if intent == "1":  # Recommendation Request
            response = await get_ai_recommendation(user_message, user_id)
            user_data[user_id]['last_recommendations'] = response

        elif intent == "2":  # Availability Check
            await update.message.reply_text("I'll check the availability for you.")
            response = await check_availability_with_browser(user_message, update)

        elif intent == "3":  # Booking Request
            await update.message.reply_text("I'll help you make a booking.")
            response = await book_using_browser_use(user_message)

        else:  # General Inquiry
            response = "I can help you with restaurant recommendations, checking availability, or making bookings. What would you like to do?"

        # Send and store response
        if response:
            await update.message.reply_text(response)
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": str(response)
            })

    except Exception as e:
        print(f"DEBUG: Error in handle_user_message: {str(e)}")
        error_message = "I encountered an error. Please try again."
        await update.message.reply_text(error_message)
        user_data[user_id]['history'].append({
            "role": "assistant",
            "content": error_message
        })

# --- 🚀 BOT INITIALIZATION ---


def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler(
        'start', lambda update, context: update.message.reply_text("Hey! I'm your booking assistant.")))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_user_message))
    application.run_polling()


if __name__ == '__main__':
    main()
