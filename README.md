# Telegram Booking Bot

A Telegram bot that helps users find restaurants, check availability, and make reservations.

## Features

- Restaurant recommendations
- Real-time availability checking
- Reservation booking
- User profile management
- Multi-user support with webhook mode

## Setup

### Prerequisites

- Python 3.9+
- A Telegram Bot Token (from BotFather)
- API keys for OpenAI, DeepSeek, Steel, and OpenRouter

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the required environment variables (see below)

### Environment Variables

Required environment variables:

```
# Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
BOT_USERNAME=your_bot_username

# API Keys
OPENAI_API_KEY=your_openai_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
STEEL_API_KEY=your_steel_api_key
OPENROUTER_API_KEY=your_openrouter_api_key

# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Browser Configuration
BROWSER_HEADLESS=true
BROWSER_BROWSERLESS=true
BROWSERLESS_URL=wss://chrome.browserless.io

# Model Configuration
GPT_MODEL=gpt-4o
DEEPSEEK_MODEL=deepseek-reasoner
CLAUDE_MODEL=anthropic/claude-3-7-sonnet-20250219

# Timeouts and Limits
SEARCH_TIMEOUT=90
MAX_RETRIES=3
MESSAGE_CHUNK_SIZE=4000
MAX_HISTORY_LENGTH=10

# GIF Creation (for Railway)
DISABLE_GIF_CREATION=true
```

### Webhook Mode Configuration

To run the bot in webhook mode (recommended for production), add these variables:

```
# Webhook Configuration
USE_WEBHOOK=true
WEBHOOK_URL=https://your-app-url.railway.app
PORT=8443
WEBHOOK_PATH=/webhook
```

## Running the Bot

### Polling Mode (Development)

For local development, run the bot in polling mode:

```
python main.py
```

### Webhook Mode (Production)

For production deployment, set the webhook environment variables and run:

```
python main.py
```

The bot will automatically detect the webhook configuration and start in webhook mode.

## Deployment

### Railway Deployment

1. Create a new project on Railway
2. Connect your GitHub repository
3. Add the required environment variables
4. Set `USE_WEBHOOK=true` and configure the webhook URL
5. Deploy the application

## Architecture

The bot is built with a modular architecture:

- `main.py`: Entry point and bot initialization
- `src/bot/`: Telegram bot handlers and conversation management
- `src/services/`: Core services (browser automation, AI)
- `src/config/`: Configuration and settings
- `src/utils/`: Utility functions and helpers

## Multi-User Support

The bot supports multiple concurrent users when running in webhook mode. Each user gets their own browser instance that is automatically managed and cleaned up after inactivity.

## License

MIT 