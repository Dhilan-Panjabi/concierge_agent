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
import json

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI API client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Initialize browser automation
browser = Browser(BrowserConfig(headless=True))

# Store user details
user_data = {}

# Define required booking details
REQUIRED_INFO = ["name", "email", "phone", "restaurant",
                 "location", "date", "time", "people", "payment_info"]

# Define conversation states
NAME, EMAIL, PHONE, RESTAURANT, LOCATION, DATE, TIME, PEOPLE, PAYMENT = range(
    9)


# --- 🚀 FUNCTION TO DETECT INTENT ---
async def classify_user_request(message):
    prompt = f"""
    The user sent this message: "{message}"
    
    Classify the intent into one of the following categories:
    1. Recommendation Request (if the user wants a suggestion)
    2. Availability Check (if the user wants to check if a restaurant has availability)
    3. Booking Request (if the user wants to make a reservation)
    4. General Inquiry (if it's not related to any of these)

    Respond only with the category number (1, 2, 3, or 4).
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    intent_raw = response.choices[0].message.content.strip()
    intent = intent_raw.split(".")[0]  # Extract only the number

    print(f"DEBUG: Intent detected -> {intent}")  # Debugging line
    return intent


# --- 🚀 FUNCTION TO GENERATE BOOKING REQUEST ---
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
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()


# --- 🚀 FUNCTION TO BOOK A TABLE USING BROWSER-USE ---
async def book_using_browser_use(user_info):
    task_prompt = f"""
    Visit the booking website for {user_info['restaurant']} and book a table for:
    - Name: {user_info['name']}
    - Email: {user_info['email']}
    - Phone: {user_info['phone']}
    - Date: {user_info['date']}
    - Time: {user_info['time']}
    - People: {user_info['people']}
    - Payment Information: {user_info['payment_info']}

    Confirm the booking and return:
    "✅ Booking confirmed at {user_info['restaurant']} for {user_info['people']} people on {user_info['date']} at {user_info['time']}."
    If failed, return:
    "❌ Could not book at {user_info['restaurant']} for {user_info['date']} at {user_info['time']}."
    """

    try:
        agent = Agent(llm=ChatOpenAI(model="gpt-4o"), browser=browser)
        result = await agent.run(task=task_prompt)
        return result
    except Exception as e:
        return f"❌ Booking failed: {str(e)}"


# --- 🚀 FUNCTION TO CHECK AVAILABILITY USING BROWSER-USE ---
async def check_availability_with_browser(restaurant, date, time, people, update):
    """
    Uses browser automation to check the real-time availability of a restaurant.
    """

    # Notify user before starting availability check
    await update.message.reply_text(f"Yeah, give me a moment! Let me check if {restaurant} has a table for you...")

    # 🔹 Step 1: Ask GPT-4o to determine the restaurant's booking platform
    platform_prompt = f"""
    The user wants to check availability for {restaurant}.

    - Identify the most common **online booking platform** used for reservations at {restaurant}.
    - If it's a large chain like Nobu, it may use OpenTable or Resy.
    - If it's an independent restaurant, check if it uses its **own website**.
    - If no online platform is found, assume it requires a phone call.

    **Respond ONLY with one of these formats:**
    - "Platform: OpenTable"
    - "Platform: Resy"
    - "Platform: SevenRooms"
    - "Platform: Restaurant Website"
    - "Platform: Phone Call"
    """

    platform_response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": platform_prompt}]
    )

    booking_platform = platform_response.choices[0].message.content.strip().split(
        ": ")[-1]

    print(f"DEBUG: Booking platform detected -> {booking_platform}")

    # 🔹 Step 2: Generate a detailed `browser-use` prompt
    if booking_platform == "OpenTable":
        task_prompt = f"""
        1. Open [OpenTable](https://www.opentable.com).
        2. Search for "{restaurant}" in the search bar.
        3. Select the correct restaurant from the search results.
        4. Enter the following details:
           - Date: {date}
           - Time: {time}
           - Party size: {people}
        5. Click "Search Availability."
        6. If a table is available, return:
           "✅ {restaurant} has availability on {date} at {time} for {people} people."
        7. If no tables are available, return:
           "❌ No availability at {restaurant} for {date} at {time} for {people} people."
        """

    elif booking_platform == "Resy":
        task_prompt = f"""
        1. Open [Resy](https://www.resy.com).
        2. Search for "{restaurant}" in the search bar.
        3. Select the correct restaurant.
        4. Enter:
           - Date: {date}
           - Time: {time}
           - Party size: {people}
        5. Click "Search Availability."
        6. If a table is available, return:
           "✅ {restaurant} has availability on {date} at {time} for {people} people."
        7. If no tables are available, return:
           "❌ No availability at {restaurant} for {date} at {time} for {people} people."
        """

    elif booking_platform == "SevenRooms":
        task_prompt = f"""
        1. Open [SevenRooms](https://www.sevenrooms.com/reservations/rhknobu).
        2. Enter:
           - Date: {date}
           - Time: {time}
           - Party size: {people}
        3. Click "Search Availability."
        4. If a table is available, return:
           "✅ {restaurant} has availability on {date} at {time} for {people} people."
        5. If no tables are available, return:
           "❌ No availability at {restaurant} for {date} at {time} for {people} people."
        """

    elif booking_platform == "Restaurant Website":
        task_prompt = f"""
        1. Open the official website of "{restaurant}".
        2. Navigate to "Reservations" or "Book a Table."
        3. Enter:
           - Date: {date}
           - Time: {time}
           - Party size: {people}
        4. Click "Check Availability."
        5. If a table is available, return:
           "✅ {restaurant} has availability on {date} at {time} for {people} people."
        6. If no tables are available, return:
           "❌ No availability at {restaurant} for {date} at {time} for {people} people."
        """

    else:
        task_prompt = f"⚠️ Unable to determine a booking platform for {restaurant}. Please try manually."

    try:
        agent = Agent(task=task_prompt, llm=ChatOpenAI(
            model="gpt-4o"), browser=browser)
        result = await agent.run()
        print(f"DEBUG: Browser result -> {result}")  # Debugging print
        await update.message.reply_text(result)  # Send result to user
        return result
    except Exception as e:
        await update.message.reply_text(f"❌ Error checking availability: {str(e)}")
        return f"❌ Error checking availability: {str(e)}"



# --- 🚀 FUNCTION TO HANDLE AVAILABILITY REQUESTS ---
async def check_availability(update: Update, context: CallbackContext):
    user_message = update.message.text

    prompt = f"""
    Extract the restaurant name, date, time, and number of people from this request:
    "{user_message}"

    Respond ONLY in this valid JSON format:
    {{
        "restaurant": "Example Restaurant",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "people": X
    }}
    Ensure that:
    - The time is a valid 24-hour format (e.g., "14:00").
    - If the user mentions vague times like "afternoon", replace it with "13:00".
    - If the user says "evening", replace it with "19:00".
    - If the user says "morning", replace it with "09:00".
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    try:
        raw_response = response.choices[0].message.content.strip()

        # Ensure valid JSON
        raw_response = raw_response.replace(
            "```json", "").replace("```", "").strip()
        availability_data = json.loads(raw_response)

        restaurant = availability_data["restaurant"]
        date = availability_data["date"]
        time = availability_data["time"]
        people = availability_data["people"]

        time_mapping = {"afternoon": "13:00",
                        "evening": "19:00", "morning": "09:00"}
        time = time_mapping.get(time.lower(), time)

        # Debugging print
        print(f"DEBUG: Extracted JSON -> {availability_data}")

        # Call browser automation to check real-time availability
        await check_availability_with_browser(restaurant, date, time, people, update)

    except Exception as e:
        print(f"DEBUG: Error processing JSON extraction: {e}")
        await update.message.reply_text("❌ Sorry, I couldn't understand your request. Please try again!")



# --- 🚀 FUNCTION TO HANDLE BOOKINGS ---
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


# --- 🚀 FUNCTION TO GENERATE AI RECOMMENDATIONS ---
async def get_ai_recommendation(query):
    prompt = f"""
    The user wants a recommendation. Respond casually.

    - Suggest 2-3 options with brief reasons.
    - Be engaging and natural.

    User request: "{query}"
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content.strip()


async def recommend(update: Update, context: CallbackContext):
    user_message = update.message.text
    recommendation = await get_ai_recommendation(user_message)
    await update.message.reply_text(recommendation)


# --- 🚀 MAIN HANDLER ---
async def handle_user_message(update: Update, context: CallbackContext):
    user_message = update.message.text
    intent = await classify_user_request(user_message)

    if intent == "1":
        await recommend(update, context)
    elif intent == "2":
        await check_availability(update, context)
    elif intent == "3":
        await ask_for_info(update, context)
    else:
        await update.message.reply_text("I can help you with recommendations, checking availability, or making bookings!")


# --- 🚀 START BOT ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler(
        'start', lambda update, context: update.message.reply_text("Hey! I’m Jarvis, your concierge.")))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_user_message))
    application.run_polling()


if __name__ == '__main__':
    main()
