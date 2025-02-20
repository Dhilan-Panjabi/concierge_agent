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


async def generate_browser_task_prompt(user_message: str, intent: str, user_id: str) -> str:
    """
    Generates a browser-use compatible task prompt with chat context.
    """
    # Get last 5 messages from history
    history = user_data[user_id]['history'][-5:] if user_id in user_data else []
    context = "\nPrevious conversation:\n" + "\n".join(
        [f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" for msg in history]
    )

    system_prompt = f"""
    You are a prompt engineer for a web automation system.
    
    {context}
    
    Current user message: "{user_message}"
    Intent: {intent}

    Create a specific browser automation task that:
    1. Identifies the exact type of request (restaurant booking, hotel reservation, event tickets, etc.)
    2. Extracts all relevant details (dates, times, people, preferences, price ranges)
    3. Formats it into a clear, direct browser instruction

    Examples of good task prompts:
    - "check the availability for nobu malibu for 2 people on the 18th for sometime in the 2 oclock"
    - "search for 5-star hotels in paris under 300 euros per night for 2 adults from march 15-20"

    Return ONLY the task prompt. No explanations or additional text.
    Make it specific enough for a browser to follow but natural enough for an AI to understand.
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}]
    )

    return response.choices[0].message.content.strip()


async def classify_user_request(message: str, user_id: str):
    """
    Classifies the intent with chat context.
    """
    # Get last 5 messages from history
    history = user_data[user_id]['history'][-5:] if user_id in user_data else []
    context = "\nPrevious conversation:\n" + "\n".join(
        [f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" for msg in history]
    )

    prompt = f"""
    {context}
    
    Current message: "{message}"
    
    Classify the intent into one of these categories:
    1. Recommendation Request
    2. Availability Check
    3. Booking Request
    4. General Inquiry

    Respond only with the category number (1, 2, 3, or 4).
    Consider the conversation context when determining the intent.
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

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
        # Get user_id from the update object
        user_id = update.message.from_user.id

        # Pass user_id to generate_browser_task_prompt
        task_prompt = await generate_browser_task_prompt(user_message, "availability_check", user_id)
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
REQUIRED_INFO = ["name", "email", "phone"]
NAME, EMAIL, PHONE = range(3)


async def gather_booking_info(update: Update, context: CallbackContext) -> int:
    """
    Starts the booking information gathering process.
    """
    user_id = update.message.from_user.id

    # Initialize booking info in user_data if not exists
    if 'booking_info' not in user_data[user_id]:
        user_data[user_id]['booking_info'] = {}

    # Start with first field
    await update.message.reply_text("To proceed with the booking, I'll need some details. What's your name?")
    return NAME


async def handle_booking_info(update: Update, context: CallbackContext) -> int:
    """
    Handles the collection of booking information.
    """
    user_id = update.message.from_user.id
    message = update.message.text
    current_field = REQUIRED_INFO[context.user_data.get('booking_step', 0)]

    # Store the provided information
    user_data[user_id]['booking_info'][current_field] = message

    # Move to next field or finish if all collected
    next_step = context.user_data.get('booking_step', 0) + 1
    context.user_data['booking_step'] = next_step

    if next_step < len(REQUIRED_INFO):
        next_field = REQUIRED_INFO[next_step]
        await update.message.reply_text(f"Great! Now, what's your {next_field}?")
        return next_step
    else:
        return await make_booking(update, context)


async def make_booking(update: Update, context: CallbackContext):
    """
    Makes the actual booking using collected information.
    """
    try:
        user_id = update.message.from_user.id
        booking_info = user_data[user_id]['booking_info']

        # Get the last few messages for context
        history = user_data[user_id]['history'][-5:]

        # Print debug information
        print(
            f"DEBUG: Booking info collected: {json.dumps(booking_info, indent=2)}")
        print(f"DEBUG: Chat history: {json.dumps(history, indent=2)}")

        # Extract booking context from history
        context_prompt = f"""
        Given this conversation history:
        {json.dumps(history, indent=2)}

        Extract the restaurant booking details. The most recent request is:
        "{history[-1]['content']}"

        Return these details in JSON format:
        {{
            "restaurant": "name of restaurant",
            "time": "requested time",
            "date": "requested date",
            "party_size": "number of people"
        }}

        For example, if the message is "can you make a reservation for me at kava this friday at 9pm for 3 people",
        return:
        {{
            "restaurant": "Kava",
            "time": "9:00 PM",
            "date": "Friday",
            "party_size": "3"
        }}

        Return ONLY the raw JSON object without any markdown formatting or code blocks.
        Do not include ```json or ``` markers.
        """

        context_response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": context_prompt}]
        )

        try:
            # Clean the response of any markdown formatting
            raw_json = context_response.choices[0].message.content.strip()
            raw_json = raw_json.replace(
                '```json', '').replace('```', '').strip()

            booking_context = json.loads(raw_json)
            print(
                f"DEBUG: Extracted booking context: {json.dumps(booking_context, indent=2)}")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON parsing error: {str(e)}")
            print(f"DEBUG: Raw response: {raw_json}")
            raise Exception(
                "Failed to parse booking details from conversation")

        # Generate booking prompt with context and collected info
        task_prompt = await generate_browser_task_prompt(
            f"""Make a booking at {booking_context['restaurant']} for {booking_context['party_size']} people at {booking_context['time']} on {booking_context['date']} with these details:
            Name: {booking_info['name']}
            Email: {booking_info['email']}
            Phone: {booking_info['phone']}
            """,
            "booking",
            user_id
        )
        print(f"DEBUG: Generated task prompt: {task_prompt}")

        # Create and run the agent
        agent = Agent(
            task=task_prompt,
            llm=ChatOpenAI(model="gpt-4o")
        )

        result = await agent.run()
        print(f"DEBUG: Booking result: {result}")

        # Format the result into a user-friendly response
        formatted_response = await format_reply_for_user(task_prompt, result)
        await update.message.reply_text(formatted_response)

        # Clear booking info after successful booking
        user_data[user_id]['booking_info'] = {}
        context.user_data['booking_step'] = 0

        return ConversationHandler.END

    except Exception as e:
        print(f"DEBUG: Error in make_booking: {str(e)}")
        await update.message.reply_text("Sorry, there was an error making the booking. Please try again.")
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
    """
    Main message handler with booking flow integration.
    """
    user_id = update.message.from_user.id
    user_message = update.message.text.lower()

    # Initialize user history
    init_user_history(user_id)
    user_data[user_id]['history'].append(
        {"role": "user", "content": user_message})

    try:
        # Check if user wants to book after availability check
        if "book it" in user_message or "make a booking" in user_message:
            await update.message.reply_text("I'll help you make that booking!")
            return await gather_booking_info(update, context)

        # Regular intent processing
        intent = await classify_user_request(user_message, user_id)
        print(f"DEBUG: Detected intent: {intent}")

        if intent == "1" or intent == "1. Recommendation Request":
            response = await get_ai_recommendation(user_message, user_id)
            user_data[user_id]['last_recommendations'] = response
            await update.message.reply_text(response)
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": response
            })

        elif intent == "2" or intent == "2. Availability Check":
            await update.message.reply_text("I'll check the availability for you.")
            response = await check_availability_with_browser(user_message, update)
            await update.message.reply_text(response)
            await update.message.reply_text("Would you like me to make a booking for you? Just say 'book it' and I'll help you with that.")
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": response
            })

        elif intent == "3" or intent == "3. Booking Request":
            return await gather_booking_info(update, context)

        else:
            response = "I can help you with restaurant recommendations, checking availability, or making bookings. What would you like to do?"
            await update.message.reply_text(response)
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": response
            })

    except Exception as e:
        print(f"DEBUG: Error in handle_user_message: {str(e)}")
        error_message = "I encountered an error. Please try again."
        await update.message.reply_text(error_message)
        user_data[user_id]['history'].append({
            "role": "assistant",
            "content": error_message
        })


async def start(update: Update, context: CallbackContext):
    """
    Handles the /start command.
    """
    welcome_message = (
        "Hey! I'm your booking assistant. 👋\n\n"
        "I can help you with:\n"
        "• Restaurant recommendations 🍽️\n"
        "• Checking availability 📅\n"
        "• Making reservations ✅\n\n"
        "What would you like to do?"
    )
    await update.message.reply_text(welcome_message)

    # Initialize user history if needed
    user_id = update.message.from_user.id
    init_user_history(user_id)

# Update main function to include all handlers


def main():
    """
    Main function with all handlers setup.
    """
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))

    # Create conversation handler for booking flow
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND,
                           handle_user_message)
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_booking_info)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_booking_info)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_booking_info)],
        },
        fallbacks=[CommandHandler(
            'cancel', lambda u, c: ConversationHandler.END)],
    )

    # Add conversation handler
    application.add_handler(conv_handler)

    # Start the bot
    print("Bot started...")
    application.run_polling()


if __name__ == '__main__':
    main()
