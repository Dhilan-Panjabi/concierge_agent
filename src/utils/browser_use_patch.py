"""
Patch for browser_use library to handle font issues on Railway.
"""
import logging
import os
from functools import wraps
import importlib

logger = logging.getLogger(__name__)

def apply_patches():
    """Apply patches to the browser_use library to handle font issues on Railway."""
    try:
        # Check if we're running on Railway
        is_railway = os.environ.get('RAILWAY_ENVIRONMENT', '') != ''
        disable_gif = os.environ.get('DISABLE_GIF_CREATION', 'false').lower() == 'true'
        
        if not (is_railway or disable_gif):
            logger.info("Not running on Railway and GIF creation not disabled - skipping patches")
            return
            
        logger.info("Applying patches to browser_use library for Railway compatibility")
        
        # Try to patch the create_history_gif method in the Agent class
        try:
            from browser_use.agent.service import Agent
            
            # Store the original method
            original_create_history_gif = Agent.create_history_gif
            
            @wraps(original_create_history_gif)
            def patched_create_history_gif(self, output_path=None):
                """Patched version of create_history_gif that handles font issues."""
                try:
                    # Check if we should skip GIF creation
                    if is_railway or disable_gif:
                        logger.info("Skipping GIF creation on Railway or due to DISABLE_GIF_CREATION=true")
                        return None
                    
                    # Call the original method
                    return original_create_history_gif(self, output_path=output_path)
                except OSError as e:
                    if "cannot open resource" in str(e):
                        logger.warning(f"Font resource error during GIF creation: {e}")
                        return None
                    raise
                except Exception as e:
                    logger.warning(f"Error in create_history_gif: {e}")
                    return None
            
            # Replace the method
            Agent.create_history_gif = patched_create_history_gif
            logger.info("Successfully patched Agent.create_history_gif")
            
        except (ImportError, AttributeError) as e:
            logger.warning(f"Could not patch Agent.create_history_gif: {e}")
        
        # Try to patch the run method to add disable_history parameter
        try:
            from browser_use.agent.service import Agent
            
            # Store the original method
            original_run = Agent.run
            
            @wraps(original_run)
            async def patched_run(self, max_steps=None, disable_history=False):
                """Patched version of run that supports disable_history parameter."""
                try:
                    # Call the original method
                    result = await original_run(self, max_steps=max_steps)
                    
                    # Skip GIF creation if disable_history is True
                    if not disable_history and not (is_railway or disable_gif):
                        try:
                            self.create_history_gif()
                        except Exception as e:
                            logger.warning(f"Error creating GIF history: {e}")
                    
                    return result
                except Exception as e:
                    logger.error(f"Error in patched run method: {e}")
                    raise
            
            # Replace the method
            Agent.run = patched_run
            logger.info("Successfully patched Agent.run")
            
        except (ImportError, AttributeError) as e:
            logger.warning(f"Could not patch Agent.run: {e}")
        
    except Exception as e:
        logger.error(f"Error applying patches to browser_use library: {e}") 