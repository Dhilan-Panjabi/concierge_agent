#!/usr/bin/env python3
"""
Test script for executing multiple searches in sequence.
This verifies the browser remains open between searches.
"""
import asyncio
import logging
import os
import sys
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Add parent directory to path so we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Import after environment variables are loaded
from src.config.settings import Settings
from src.services.browser_service import BrowserService

async def run_multiple_searches():
    """Run multiple searches in sequence to test browser persistence"""
    settings = Settings()
    browser_service = BrowserService(settings)
    
    try:
        # First search
        logger.info("===== STARTING FIRST SEARCH =====")
        result1 = await browser_service.execute_search(
            "Check availability for Yardbird in Hong Kong this Saturday at a 8 PM for 2 people"
        )
        logger.info(f"First search completed successfully. Result length: {len(result1)}")
        logger.info(f"First search result excerpt: {result1[:200]}...")
        
        # Verify browser is still active
        logger.info(f"Browser status after first search: {'Active' if browser_service._browser is not None else 'Not active'}")
        
        # Wait briefly
        logger.info("Waiting 5 seconds before next search...")
        await asyncio.sleep(5)
        
        # Second search  
        logger.info("===== STARTING SECOND SEARCH =====")
        result2 = await browser_service.execute_search(
            "Find flights from New York to London next weekend"
        )
        logger.info(f"Second search completed successfully. Result length: {len(result2)}")
        logger.info(f"Second search result excerpt: {result2[:200]}...")
        
        # Verify browser is still active
        logger.info(f"Browser status after second search: {'Active' if browser_service._browser is not None else 'Not active'}")
        
        # Wait briefly
        logger.info("Waiting 5 seconds before next search...")
        await asyncio.sleep(5)
        
        # Third search
        logger.info("===== STARTING THIRD SEARCH =====")
        result3 = await browser_service.execute_search(
            "Check availability at the Mondrian hotel in London for this weekend"
        )
        logger.info(f"Third search completed successfully. Result length: {len(result3)}")
        logger.info(f"Third search result excerpt: {result3[:200]}...")
        
        # Final browser status check
        logger.info(f"Browser status after all searches: {'Active' if browser_service._browser is not None else 'Not active'}")
        
        # Log all completed searches
        logger.info("===== ALL SEARCHES COMPLETED SUCCESSFULLY =====")
        logger.info(f"Completed 3 consecutive searches with browser remaining active")
        
        # Explicitly force close the browser at the end of the test
        logger.info("Test complete. Force closing browser...")
        await browser_service.force_close_browser()
        logger.info("Browser force closed.")
        
    except Exception as e:
        logger.error(f"Error during multiple search test: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(run_multiple_searches())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception in test: {e}", exc_info=True) 