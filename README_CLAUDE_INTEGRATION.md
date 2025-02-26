# Claude 3.7 Sonnet Browser Integration

This integration allows you to use Claude 3.7 Sonnet via OpenRouter for browser automation tasks directly with the browser-use library.

## Overview

The integration uses LangChain's `ChatOpenAI` class with OpenRouter configuration to directly access Claude 3.7 Sonnet for browser tasks without requiring a custom adapter.

## Installation

Install the required packages:

```bash
pip install langchain langchain_openai browser-use python-dotenv
```

## Configuration

Add your API keys to your `.env` file:

```
OPENROUTER_API_KEY=your_openrouter_api_key
STEEL_API_KEY=your_steel_api_key
```

## Usage

### Running the Test Script

To test the Claude browser integration:

```bash
python test/claude_browser_test.py
```

This will run a test task that checks availability at a restaurant using Claude 3.7 Sonnet.

### Using in Your Code

The `BrowserService` class is configured to use Claude 3.7 for browser tasks:

```python
# Initialize Claude 3.7 via OpenRouter
claude_llm = ChatOpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    model="anthropic/claude-3-7-sonnet-20250219",
    temperature=0.1
)

# Create agent with Claude
agent = Agent(
    task=task_prompt,
    llm=claude_llm,
    browser=browser,
    sensitive_data=sensitive_data
)
```

Example usage with the `BrowserService`:

```python
# This will use Claude 3.7 for browser automation
result = await browser_service.execute_search(
    "Check availability at Yardbird for tomorrow",
    task_type="search",
    user_id=123
)

# For booking with sensitive data
result = await browser_service.execute_search(
    "Book a table at Yardbird",
    task_type="booking",  # This triggers sensitive data handling
    user_id=123  # User ID is used to retrieve profile information
)
```

## Handling Sensitive Data

The integration securely handles sensitive user data:

1. User data (name, email, phone) is stored in your database
2. The `_extract_user_details` method retrieves this data when needed
3. Data is passed to the browser agent using placeholders in prompts
4. The `sensitive_data` parameter ensures personal information is not exposed in model prompts

In your prompts, use placeholders like:
- `user_name`
- `user_email`
- `user_phone`

These will be automatically replaced with actual user data during browser automation.

## Troubleshooting

If you encounter issues:

1. Check that your OpenRouter API key is valid and has access to Claude 3.7 Sonnet
2. Ensure all required packages are installed
3. Check the logs for error messages
4. Verify that the browser is properly configured with your Steel API key

## Notes

- The default Claude model is "anthropic/claude-3-7-sonnet-20250219"
- You may need to adjust temperature settings based on your specific use case
- The browser-use library handles the communication between the LLM and the browser 