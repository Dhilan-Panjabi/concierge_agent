from asyncio.log import logger
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
import traceback
from pydantic import SecretStr


# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
STEEL_API_KEY = os.getenv("STEEL_API_KEY")
# Initialize OpenAI API client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

controller = Controller()

# Initialize browser automation

browser = Browser(config=BrowserConfig(
    headless=True,
))

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


async def generate_browser_task_prompt(user_message: str, task_type: str, user_id: str) -> str:
    """
    Generates browser task prompt based on task type and user message.
    """
    if task_type == "search":
        prompt = f"""
        TASK: Find real-time information for: "{user_message}"
        
        TIME LIMIT: 90 seconds total
        
        SEARCH STEPS:
        1. [20s] Quick search on Google for best options
        2. [30s] Check official websites/platforms:
           - If flights: Google Flights, airline sites
           - If restaurants: OpenTable, official websites
           - If events: Ticketmaster, venue sites
           - If hotels: Booking.com, hotel sites
        3. [20s] Verify current information:
           - Prices/availability
           - Times/schedules
           - Special conditions
        4. [20s] Get booking details:
           - Direct booking links
           - Contact information
           - Important notes
        
        FORMAT RESULTS:
        1. OPTIONS FOUND:
           - Names/details
           - Current prices
           - Available times
           - Direct booking URLs
        
        2. IMPORTANT INFO:
           - Special conditions
           - Additional fees
           - Requirements
        
        3. BOOKING OPTIONS:
           - Direct booking links
           - Phone numbers
           - Alternative booking methods
        
        Keep responses focused and include all relevant URLs and contact details.
        """

    elif task_type == "availability_check":
        prompt = f"""
        TASK: Check current availability for: "{user_message}"
        
        TIME LIMIT: 90 seconds
        
        STEPS:
        1. [30s] Access relevant booking platform
        2. [30s] Check specific availability
        3. [30s] Verify details and alternatives
        
        FORMAT RESULTS:
        - Available options
        - Current prices
        - Direct booking links
        - Alternative choices
        """

    elif task_type == "booking":
        prompt = f"""
        TASK: Make a booking for: "{user_message}"
        
        TIME LIMIT: 90 seconds
        
        STEPS:
        1. [30s] Access booking system
        2. [30s] Enter required details
        3. [30s] Complete reservation
        
        FORMAT RESULTS:
        - Booking confirmation
        - Important details
        - Next steps
        """

    else:
        prompt = f"""
        TASK: General search for: "{user_message}"
        
        TIME LIMIT: 90 seconds
        
        STEPS:
        1. [30s] Search options
        2. [30s] Compare choices
        3. [30s] Collect details
        
        FORMAT RESULTS:
        - Available options
        - Key information
        - Booking/contact details
        """

    return prompt


async def classify_user_request(message: str, user_id: str):
    """
    Classifies the intent with chat context.
    """
    history = user_data[user_id]['history'][-5:] if user_id in user_data else []
    context = "\nPrevious conversation:\n" + "\n".join(
        [f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" for msg in history]
    )

    prompt = f"""
    {context}
    
    Current message: "{message}"
    
    Classify this request into exactly one category by returning ONLY its number:
    2 - If the request needs real-time information (sports games, current availability, what's happening now)
    1 - If it's only asking for general recommendations without needing current information
    3 - If it's specifically about making a booking
    
    Examples:
    "What's a good Italian restaurant?" -> 2
    "Where can I watch the game tonight?" -> 2
    "Find me a bar showing hockey" -> 2
    "Make a reservation" -> 3
    
    Return ONLY the number (1, 2, or 3). Do not include any other text or explanation.
    """

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}]
    )

    # Extract just the number from the response
    result = response.choices[0].message.content.strip()
    # Remove any non-numeric characters
    result = ''.join(filter(str.isdigit, result))
    return result

# --- 🔍 AVAILABILITY CHECKING ---


async def format_reply_for_user(user_request: str, agent_result: str) -> str:
    """
    Formats the agent's result into a detailed, concierge-style response with all relevant links and information.
    """
    prompt = f"""
    You are a helpful and professional concierge assistant.
    
    Original request: "{user_request}"
    Search results: "{agent_result}"

    Create a detailed, friendly response that includes ALL of the following:
    1. Warm greeting and acknowledgment of the request
    2. Main findings and recommendations
    3. For EACH option found:
       - Full details (price, timing, ratings, etc.)
       - Direct booking/information links
       - Contact information
       - Special conditions or requirements
    4. Important notes (fees, policies, restrictions)
    5. Next steps and booking options
    6. Offer for additional assistance

    REQUIRED FORMAT:
    Start with a friendly greeting and summary.
    Then list each option with ALL details and links.
    End with next steps and offer to help.

    EXAMPLE FORMAT:
    "I've found several excellent options for you! Let me share the details:

    1. [Property/Venue Name] - $X
       • Full details (size, type, timing, etc.)
       • Rating: X.X (X reviews)
       • Direct booking: [exact URL]
       • Contact: [phone/email]
       • Special notes: [any important details]

    2. [Next option with same detailed format]

    Important Information:
    • [List all fees, policies, requirements]
    • [Include cancellation policies]
    • [Note any time-sensitive details]

    Direct Booking Links:
    • [Option 1 Name]: [exact URL]
    • [Option 2 Name]: [exact URL]

    I can help you book any of these options directly or provide more information. Would you like to:
    1. Get more details about any option?
    2. See additional choices?
    3. Proceed with booking?

    Just let me know how I can assist!"

    Return the response maintaining ALL links and contact information exactly as provided in the search results.

    IMPORTANT:
    - Keep responses concise but informative
    - Focus on the most relevant details
    - Limit repetitive information
    - Use bullet points for better readability
    - Keep total response under 4000 characters when possible
    
    """

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error formatting reply: {str(e)}")
        return str(agent_result)  # Fallback to raw result if formatting fails


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
            llm=ChatOpenAI(model="gpt-4o"),
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
NAME, EMAIL, PHONE, CONFIRMATION_CODE = range(4)


async def handle_confirmation_code(update: Update, context: CallbackContext):
    """
    Handles the confirmation code input and completes the booking.
    """
    try:
        user_id = update.message.from_user.id
        confirmation_code = update.message.text.strip()

        # Get the existing agent from context
        agent = context.user_data.get('current_agent')
        if not agent:
            await update.message.reply_text("Sorry, the booking session has expired. Please start over.")
            return ConversationHandler.END

        # Continue the booking with the confirmation code
        result = await agent.continue_task(f"Enter confirmation code: {confirmation_code}")
        print(f"DEBUG: Booking result after confirmation: {result}")

        # Convert result to string if it isn't already
        result_text = str(result)

        # Format and send response
        formatted_response = await format_reply_for_user("Complete booking with confirmation code", result_text)
        await update.message.reply_text(formatted_response)

        # Clear booking info after successful booking
        user_data[user_id]['booking_info'] = {}
        context.user_data['booking_step'] = 0
        context.user_data['current_agent'] = None

        return ConversationHandler.END

    except Exception as e:
        print(f"DEBUG: Error in handle_confirmation_code: {str(e)}")
        print(f"DEBUG: Error type: {type(e)}")
        print(f"DEBUG: Full error traceback:", traceback.format_exc())
        await update.message.reply_text("Sorry, there was an error with the confirmation code. Please try again.")
        return ConversationHandler.END


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

        # Start the booking process
        result = await agent.run()
        print(f"DEBUG: Initial booking result: {result}")

        # Convert result to string and check for confirmation code requirement
        result_text = str(result)
        print(f"DEBUG: Result text: {result_text}")

        # Check if confirmation code is needed
        if any(keyword in result_text.lower() for keyword in ["confirmation", "verification", "code", "verify", "email"]):
            # Store the agent in context for later use
            context.user_data['current_agent'] = agent

            # Store booking context for later use
            context.user_data['booking_context'] = booking_context

            # Ask user for confirmation code
            await update.message.reply_text(result_text)
            await update.message.reply_text("Please enter the confirmation code from your email to complete the booking.")

            # Add to history
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": result_text
            })

            return CONFIRMATION_CODE

        # If no confirmation needed, complete booking
        formatted_response = await format_reply_for_user(task_prompt, result_text)
        await update.message.reply_text(formatted_response)

        # Add to history
        user_data[user_id]['history'].append({
            "role": "assistant",
            "content": formatted_response
        })

        # Clear booking info
        user_data[user_id]['booking_info'] = {}
        context.user_data['booking_step'] = 0

        return ConversationHandler.END

    except Exception as e:
        print(f"DEBUG: Error in make_booking: {str(e)}")
        print(f"DEBUG: Error type: {type(e)}")
        print(f"DEBUG: Full error traceback:", traceback.format_exc())

        error_message = "Sorry, there was an error making the booking. Please try again."
        await update.message.reply_text(error_message)

        # Add error to history
        user_data[user_id]['history'].append({
            "role": "assistant",
            "content": error_message
        })

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


def should_offer_booking(result) -> bool:
    """
    Determines if we should offer booking based on search results.
    """
    booking_indicators = ['reservation',
                          'available', 'book', 'time slot', 'seating']

    # Convert AgentHistoryList or any other type to string
    result_str = str(result)

    try:
        return any(indicator in result_str.lower() for indicator in booking_indicators)
    except AttributeError:
        print(f"DEBUG: Result type: {type(result)}")
        print(f"DEBUG: Result content: {result}")
        return False

async def handle_error(update: Update, context: CallbackContext):
    """
    Generic error handler that sends an error message to the user.
    """
    error_message = "Sorry, something went wrong. Please try again later."
    await update.message.reply_text(error_message)

async def format_detailed_reply(user_request: str, agent_result: str) -> dict:
    """
    Formats the agent's result into a detailed, structured response.
    """
    prompt = f"""
    You are a professional concierge assistant.
    
    Original user request: "{user_request}"
    Browser agent result: "{agent_result}"

    Create a response with these components:
    1. Main message: Clear summary of findings
    2. Links: Extract any URLs mentioned (website, booking pages)
    3. Venue details: Names, addresses, contact info
    4. Current availability/schedules
    5. Booking options
    
    Return a JSON object with these keys:
    {{
        "main_message": "The formatted main response",
        "links": {{"venue_name": "url", ...}},
        "venues": [{{
            "name": "venue name",
            "address": "address",
            "contact": "contact info",
            "availability": "current availability"
        }}]
    }}
    """

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        )

        # Parse the JSON response
        result = json.loads(response.choices[0].message.content.strip())
        return result
    except Exception as e:
        logger.error(f"Error formatting detailed reply: {str(e)}")
        return {
            "main_message": agent_result,
            "links": {},
            "venues": []
        }
    

async def send_long_message(update: Update, text: str, max_length: int = 4000):
    """
    Splits and sends long messages within Telegram's character limit.
    """
    if len(text) <= max_length:
        await update.message.reply_text(text)
        return

    # Split message into parts
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break

        # Find the last complete sentence or line within the limit
        split_point = text.rfind('\n', 0, max_length)
        if split_point == -1:
            split_point = text.rfind('. ', 0, max_length)
        if split_point == -1:
            split_point = max_length

        parts.append(text[:split_point])
        text = text[split_point:].strip()

    # Send each part with a continuation indicator
    for i, part in enumerate(parts):
        if len(parts) > 1:
            indicator = f"(Part {i+1}/{len(parts)})\n\n"
            await update.message.reply_text(indicator + part)
        else:
            await update.message.reply_text(part)

def extract_final_result(agent_result) -> str:
    """
    Extracts the final result from AgentHistoryList object.
    """
    try:
        # If it's already a string, return it
        if isinstance(agent_result, str):
            return agent_result
            
        # Get all results that are marked as done and have content
        completed_actions = [r for r in agent_result.all_results if r.is_done and r.extracted_content]
        
        # If we have completed actions, return the last one
        if completed_actions:
            return completed_actions[-1].extracted_content
            
        # If no completed actions, try to get any action with content
        actions_with_content = [r for r in agent_result.all_results if r.extracted_content]
        if actions_with_content:
            return actions_with_content[-1].extracted_content
            
        # If all else fails, convert the entire result to string
        return str(agent_result)
        
    except Exception as e:
        print(f"DEBUG: Error extracting final result: {str(e)}")
        print(f"DEBUG: Result type: {type(agent_result)}")
        print(f"DEBUG: Raw result: {agent_result}")
        return str(agent_result)
    
async def handle_user_message(update: Update, context: CallbackContext):
    """
    Main message handler with improved error handling and detailed information.
    """
    user_id = update.message.from_user.id
    user_message = update.message.text.lower()
    response = None

    try:
        # Initialize user history
        init_user_history(user_id)
        user_data[user_id]['history'].append({
            "role": "user",
            "content": user_message
        })

        # Check for booking intent
        if any(phrase in user_message for phrase in ["book it", "make a booking", "reserve"]):
            response = "I'll help you make that booking!"
            await update.message.reply_text(response)
            return await gather_booking_info(update, context)

        # Classify intent
        intent = await classify_user_request(user_message, user_id)
        print(f"DEBUG: Detected intent: {intent}")

        if intent == "2":  # Browser search needed
            await update.message.reply_text("Let me search for current options...")

            # Generate and execute browser task
            task_prompt = await generate_browser_task_prompt(user_message, "search", user_id)
            agent = Agent(
                task=task_prompt,
                llm=ChatOpenAI(model="gpt-4o"),
            )
            result = await agent.run()
            final_result = extract_final_result(result)

            # Format the response
            formatted_response = await format_reply_for_user(user_message, final_result)
            
            # Send the main response
            await send_long_message(update, formatted_response)

            # Store in history
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": formatted_response
            })

            # Offer booking if applicable
            if should_offer_booking(formatted_response):
                booking_options = (
                    "\n\nI can help you in two ways:\n"
                    "1. Say 'book it' and I'll make the booking for you automatically\n"
                    "2. Use the links above to book directly yourself"
                )
                await update.message.reply_text(booking_options)
                response = formatted_response + booking_options

        elif intent == "1":  # General recommendations
            response = await get_ai_recommendation(user_message, user_id)
            await update.message.reply_text(response)

        elif intent == "3":  # Direct booking
            response = "Let's get your booking information."
            await update.message.reply_text(response)
            return await gather_booking_info(update, context)

        else:
            response = "I can help you with recommendations, checking availability, finding information, or making bookings. What would you like to do?"
            await update.message.reply_text(response)

        # Store in history if not already stored
        if response and response != user_data[user_id]['history'][-1].get('content', None):
            user_data[user_id]['history'].append({
                "role": "assistant",
                "content": response
            })

        return ConversationHandler.END

    except Exception as e:
        print(f"DEBUG: Error in handle_user_message: {str(e)}")
        print(f"DEBUG: Full error traceback:", traceback.format_exc())
        error_message = "I encountered an error. Please try again."
        await update.message.reply_text(error_message)

        user_data[user_id]['history'].append({
            "role": "assistant",
            "content": error_message
        })
        return ConversationHandler.END

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
    Main function with conversation handler setup.
    """
    application = Application.builder().token(BOT_TOKEN).build()

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
            CONFIRMATION_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation_code)],
        },
        fallbacks=[CommandHandler(
            'cancel', lambda u, c: ConversationHandler.END)],
    )

    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == '__main__':
    main()
