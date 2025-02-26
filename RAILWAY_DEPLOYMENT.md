# Railway Deployment Guide

This guide provides instructions for deploying the Texting Concierge Agent to Railway.

## Prerequisites

- A Railway account
- A Telegram bot token
- Required API keys (OpenAI, Deepseek, etc.)

## Deployment Steps

### 1. Set Up Your Railway Project

1. Create a new project in Railway
2. Connect your GitHub repository or use the Railway CLI to deploy

### 2. Configure Environment Variables

Set the following environment variables in your Railway project settings:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `BOT_USERNAME`: Your Telegram bot username
- `WEBHOOK_URL`: Your Railway app URL (e.g., https://your-app.up.railway.app)
- `OPENAI_API_KEY`: Your OpenAI API key
- `DEEPSEEK_API_KEY`: Your Deepseek API key (if using)
- `STEEL_API_KEY`: Your Steel API key (if using)
- `OPENROUTER_API_KEY`: Your OpenRouter API key (if using)
- `BROWSERLESS_URL`: Your Browserless URL (if using)
- `SUPABASE_URL`: Your Supabase URL (if using)
- `SUPABASE_KEY`: Your Supabase key (if using)

### 3. Deploy Your Application

Railway will automatically deploy your application using the `Dockerfile.railway` specified in the `railway.json` file.

### 4. Set Up the Webhook

After deployment, you need to set up the webhook for your Telegram bot. You can use the provided `setup_webhook.py` script:

```bash
python setup_webhook.py --webhook-url https://your-app.up.railway.app
```

To check if the webhook is set up correctly:

```bash
python setup_webhook.py --info
```

To delete the webhook:

```bash
python setup_webhook.py --delete
```

## Troubleshooting

### Memory Issues During Build

If you encounter memory issues during the build process, Railway might be terminating the build due to excessive memory usage. The `Dockerfile.railway` has been optimized to reduce memory usage during the build process.

### Health Check Failures

The application includes a dedicated health check endpoint at `/telegram/webhook` that Railway uses to monitor the health of your application. If your application is failing health checks, check the logs for any errors.

### Webhook Issues

If your bot is not receiving updates, check if the webhook is set up correctly using the `setup_webhook.py` script with the `--info` flag. Make sure the webhook URL matches your Railway app URL.

## Local Testing

You can test your Docker build locally using the provided `docker_build_debug.sh` script:

```bash
./docker_build_debug.sh
```

This script will build the Docker image, run a container with limited resources to simulate the Railway environment, and test the health check endpoint.

## Additional Resources

- [Railway Documentation](https://docs.railway.app/)
- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)
- [Playwright Documentation](https://playwright.dev/python/docs/intro) 