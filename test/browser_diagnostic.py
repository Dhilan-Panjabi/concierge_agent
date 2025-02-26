#!/usr/bin/env python3
"""
Diagnostic script to test browser initialization and persistence between searches.
This script performs two sequential searches to verify if the browser remains open.
"""
import asyncio
import logging
import os
import sys
import time
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Make sure we can import from the parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

from src.config.settings import Settings
from src.services.browser_service import BrowserService

async def run_diagnostic_test():
    """Run a diagnostic test with two sequential searches"""
    try:
        settings = Settings()
        browser_service = BrowserService(settings)
        
        logger.info("=== STARTING BROWSER DIAGNOSTIC TEST ===")
        
        # First search
        logger.info("Performing first search...")
        first_result = await browser_service.execute_search("Check if Yardbird in Hong Kong has availability this Saturday at 8 PM for 2 people")
        logger.info(f"First search completed with result length: {len(first_result)}")
        
        # Add a small delay between searches
        logger.info("Waiting 5 seconds before second search...")
        await asyncio.sleep(5)
        
        # Second search
        logger.info("Performing second search...")
        second_result = await browser_service.execute_search("Check if The Chairman in Hong Kong has availability this Saturday at 8 PM for 2 people")
        logger.info(f"Second search completed with result length: {len(second_result)}")
        
        logger.info("=== DIAGNOSTIC TEST COMPLETED SUCCESSFULLY ===")
        
        # Results
        logger.info("\n=== RESULTS ===")
        logger.info("=== FIRST SEARCH RESULT ===")
        logger.info(first_result[:500] + "..." if len(first_result) > 500 else first_result)
        logger.info("\n=== SECOND SEARCH RESULT ===")
        logger.info(second_result[:500] + "..." if len(second_result) > 500 else second_result)
        
        # Keep the browser open for a while to monitor
        logger.info("\nKeeping the script alive for 30 seconds to monitor browser state...")
        for i in range(6):
            await asyncio.sleep(5)
            logger.info(f"Browser status check ({i+1}/6): Browser instance exists: {browser_service._browser is not None}")
        
        # Clean up at the end
        logger.info("Test complete, cleaning up browser...")
        await browser_service.cleanup(force=True)
        
    except Exception as e:
        logger.error(f"Error during diagnostic test: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(run_diagnostic_test())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True) 