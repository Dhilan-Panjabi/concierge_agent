from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
)
import openai
import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Initialize browser automation
browser = Browser(BrowserConfig(headless=True))

# Store user details temporarily
user_data = {}

# Define required details
REQUIRED_INFO = ["name", "email", "phone", "restaurant",
                 "location", "date", "time", "people", "payment_info"]

# Define conversation states
NAME, EMAIL, PHONE, RESTAURANT, LOCATION, DATE, TIME, PEOPLE, PAYMENT = range(
    9)

# Function to classify user intent


async def classify_user_request(message):
    prompt = f"""
    The user sent this message: "{message}"
    
    Classify the intent into one of the following categories:
    1. Recommendation Request (if the user wants a suggestion)
    2. Booking Request (if the user wants to make a reservation)
    3. General Inquiry (if it's not related to either)

    Respond only with the category number.
    """

    response = await asyncio.to_thread(
        openai.ChatCompletion.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response["choices"][0]["message"]["content"].strip()

# Function to generate structured booking request


async def generate_booking_prompt(user_info):
    prompt = f"""
    The user wants to book a restaurant. Here are the details:

    - Name: {user_info['name']}
    - Email: {user_info['email']}
    - Phone: {user_info['phone']}
    - Restaurant: {user_info['restaurant']}
    - Location: {user_info['location']}
    - Date: {user_info['date']}
    - Time: {user_info['time']}
    - People: {user_info['people']}
    - Payment Information: {user_info['payment_info']}

    Convert this information into a structured JSON format.
    """

    response = await asyncio.to_thread(
        openai.ChatCompletion.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response["choices"][0]["message"]["content"].strip()

# Browser automation function


async def book_using_browser_use(task_prompt):
    try:
        agent = Agent(llm=ChatOpenAI(model="gpt-4o"), browser=browser)
        result = await agent.run(task=task_prompt)
        return f"✅ Booking confirmed: {result}"
    except Exception as e:
        return f"❌ Booking failed: {str(e)}"

# Function to start the bot


async def start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Hey! I’m Jarvis, your personal concierge. What can I help you with today?")
    return NAME  # Move to the next state

# Function to collect user details step-by-step


async def ask_for_info(update: Update, context: CallbackContext) -> int:
    user_id = update.message.chat_id
    message = update.message.text

    if user_id not in user_data:
        user_data[user_id] = {}

    # Get next required field
    for field in REQUIRED_INFO:
        if field not in user_data[user_id] or not user_data[user_id][field]:
            user_data[user_id][field] = message
            await update.message.reply_text(f"Got it! Now, please provide your {field.replace('_', ' ')}:")
            return REQUIRED_INFO.index(field) + 1  # Move to the next state

    # Once all info is collected, proceed to booking
    structured_task = await generate_booking_prompt(user_data[user_id])
    booking_result = await book_using_browser_use(structured_task)
    await update.message.reply_text(booking_result)

    return ConversationHandler.END

# Function to generate AI-based restaurant or hotel recommendations


async def get_ai_recommendation(query):
    prompt = f"""
    The user is looking for a recommendation. Respond casually like a friend.

    - Be natural and fun.
    - Don't be robotic or formal.
    - If it's a restaurant request, suggest a couple of places with quick reasons why they’re great.
    - If it’s about travel, events, or something else, be helpful but keep it casual.

    User message: "{query}"
    """

    response = await asyncio.to_thread(
        openai.ChatCompletion.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response["choices"][0]["message"]["content"].strip()

# Function to handle recommendations


async def recommend(update: Update, context: CallbackContext):
    user_message = update.message.text
    recommendation = await get_ai_recommendation(user_message)
    await update.message.reply_text(recommendation)

# Function to cancel booking


async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("No problem! Let me know if you need anything else.")
    return ConversationHandler.END


def main():
    # Initialize bot application
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for booking flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            RESTAURANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            PEOPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
            PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_info)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    # Handler for recommendations
    application.add_handler(MessageHandler(filters.Regex(
        r'(?i)recommend|suggest|where should I go'), recommend))

    # Start the bot
    application.run_polling()


if __name__ == '__main__':
    main()
