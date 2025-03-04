#!/usr/bin/env python
"""
Test script to verify browser reuse between searches with extended timeout.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import after environment variables are loaded
from src.config.settings import Settings
from src.services.browser_service import BrowserService

async def run_sequential_searches():
    """Run multiple searches in sequence to test browser reuse with extended timeout"""
    logger.info("Starting browser reuse test with extended timeout")
    
    # Initialize settings and browser service
    settings = Settings()
    browser_service = BrowserService(settings)
    
    # Log the initial timeout value
    logger.info(f"Initial inactivity timeout: {browser_service._inactivity_timeout} seconds ({browser_service._inactivity_timeout/60:.1f} minutes)")
    
    # First search
    logger.info("Starting first search")
    result1 = await browser_service.execute_search("What are the best restaurants in London?")
    logger.info(f"First search completed, result length: {len(result1)}")
    
    # Wait a bit to simulate user interaction
    logger.info("Waiting 5 seconds between searches...")
    await asyncio.sleep(5)
    
    # Second search with extended timeout
    logger.info("Extending timeout before second search")
    await browser_service.extend_timeout(additional_seconds=1800)  # Add 30 more minutes
    
    logger.info("Starting second search")
    result2 = await browser_service.execute_search("What are the best hotels in Paris?")
    logger.info(f"Second search completed, result length: {len(result2)}")
    
    # Third search to test multiple sequential searches
    logger.info("Waiting 5 seconds between searches...")
    await asyncio.sleep(5)
    
    logger.info("Starting third search")
    result3 = await browser_service.execute_search("When is the next Manchester United game?")
    logger.info(f"Third search completed, result length: {len(result3)}")
    
    # Test complete
    logger.info("Browser reuse test completed successfully!")
    return True

if __name__ == "__main__":
    asyncio.run(run_sequential_searches()) 