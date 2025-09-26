#!/usr/bin/env python3
"""
Page fetching module with JavaScript rendering support using Playwright.

This module provides functionality to fetch web pages with full JavaScript rendering,
handle dynamic content loading, and return parsed HTML content for further processing.
Uses robust browser management with proper resource cleanup and pooling.

Author: AI Assistant
Version: 3.0 - Enhanced with robust browser management
"""

import asyncio
import logging
from typing import Optional
from bs4 import BeautifulSoup
from playwright.async_api import Page

from .browser_manager import managed_page, close_browser_manager, close_all_browser_managers

# Configure logging
logger = logging.getLogger(__name__)


class PageFetcher:
    """
    Handles fetching web pages with JavaScript rendering using Playwright.
    """
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize the page fetcher.
        
        Args:
            timeout (int): Page load timeout in seconds
            max_retries (int): Maximum number of retry attempts for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        

async def fetch_page_content(url: str, timeout: int = 60, max_retries: int = 3, 
                           browser_instance_id: Optional[str] = None) -> Optional[BeautifulSoup]:
    """
    Fetch and parse a web page with JavaScript rendering using Playwright.
    Uses the managed browser system for efficient resource management.
    
    Args:
        url (str): URL of the page to fetch
        timeout (int): Page load timeout in seconds
        max_retries (int): Maximum number of retry attempts
        browser_instance_id (Optional[str]): Unique browser instance ID for process isolation
        
    Returns:
        Optional[BeautifulSoup]: Parsed HTML content as BeautifulSoup object, or None if failed
    """
    # Generate unique browser instance ID if not provided
    if browser_instance_id is None:
        import os
        from datetime import datetime
        browser_instance_id = f"page_fetch_{os.getpid()}_{datetime.now().strftime('%H%M%S%f')}"
    for attempt in range(max_retries):
        try:
            logger.debug(f"Attempt {attempt + 1} to fetch: {url}")
            
            # Use managed page for automatic resource cleanup with process-specific browser
            async with managed_page(instance_id=browser_instance_id) as page:
                # Navigate to the page
                response = await page.goto(
                    url, 
                    wait_until='networkidle',
                    timeout=timeout * 1000  # Convert to milliseconds
                )
                
                if response is None:
                    logger.warning(f"No response received for {url}")
                    continue
                    
                if not response.ok:
                    logger.warning(f"HTTP error {response.status} for {url}")
                    continue
                
                # Wait for complete page load
                await _wait_for_complete_load(page, timeout)
                
                # Get the fully rendered HTML content
                html_content = await page.content()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                logger.debug(f"Successfully fetched JavaScript-rendered content from: {url}")
                if soup.title:
                    logger.debug(f"Page title: {soup.title.string}")
                
                return soup
                
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            
        # Wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(1)
    
    logger.error(f"Failed to fetch {url} after {max_retries} attempts")
    return None


async def _wait_for_complete_load(page: Page, max_wait_time: int = 10) -> None:
    """
    Wait for complete page loading using multiple strategies.
    
    Args:
        page (Page): Playwright page instance
        max_wait_time (int): Maximum additional wait time in seconds
        
    Returns:
        None
    """
    try:
        # Wait for network to be idle (no requests for 500ms)
        await page.wait_for_load_state('networkidle', timeout=max_wait_time * 1000)
        logger.debug("Network idle state reached")
        
        # Wait for DOM content to be loaded
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        logger.debug("DOM content loaded")
        
        # Wait for any jQuery operations to complete (if jQuery is present)
        try:
            await page.evaluate("""
                new Promise((resolve) => {
                    if (typeof jQuery !== 'undefined' && jQuery.active > 0) {
                        const checkJQuery = () => {
                            if (jQuery.active === 0) {
                                resolve();
                            } else {
                                setTimeout(checkJQuery, 100);
                            }
                        };
                        checkJQuery();
                    } else {
                        resolve();
                    }
                })
            """, timeout=3000)
            logger.debug("jQuery operations completed")
        except Exception:
            # jQuery not present or evaluation failed - continue
            pass
        
        # Wait for common loading indicators to disappear
        try:
            common_selectors = [
                '.loading',
                '.spinner',
                '.loader',
                '[data-loading="true"]',
                '.fa-spinner',
                '.fa-circle-o-notch'
            ]
            
            for selector in common_selectors:
                try:
                    # Wait for loading indicators to disappear (if they exist)
                    await page.wait_for_selector(selector, state='detached', timeout=2000)
                    logger.debug(f"Loading indicator {selector} disappeared")
                except Exception:
                    # Selector not found or didn't disappear - continue
                    continue
                    
        except Exception:
            pass
        
        # Wait for page height to stabilize (indicating dynamic content has loaded)
        try:
            previous_height = 0
            stable_count = 0
            
            for _ in range(5):  # Check up to 5 times
                current_height = await page.evaluate('document.body.scrollHeight')
                
                if current_height == previous_height:
                    stable_count += 1
                    if stable_count >= 2:  # Height stable for 2 consecutive checks
                        logger.debug("Page height stabilized")
                        break
                else:
                    stable_count = 0
                    
                previous_height = current_height
                await asyncio.sleep(0.5)  # Wait 500ms between checks
                
        except Exception as e:
            logger.debug(f"Page height stabilization check failed: {str(e)}")
        
        # Final small delay to ensure everything is settled
        await asyncio.sleep(0.5)
        
    except Exception as e:
        logger.debug(f"Complete load waiting failed: {str(e)}")


def fetch_page_sync(url: str, timeout: int = 30, max_retries: int = 3) -> Optional[BeautifulSoup]:
    """
    Synchronous wrapper for the async page fetching function.
    
    Args:
        url (str): URL of the page to fetch
        timeout (int): Page load timeout in seconds
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        Optional[BeautifulSoup]: Parsed HTML content as BeautifulSoup object, or None if failed
    """
    try:
        # Try to use existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is already running, we need to use nest_asyncio
            import nest_asyncio
            nest_asyncio.apply()
        
        return loop.run_until_complete(fetch_page_content(url, timeout, max_retries))
        
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(fetch_page_content(url, timeout, max_retries))


async def cleanup_browser_resources(browser_instance_id: Optional[str] = None) -> None:
    """
    Cleanup browser resources for a specific instance or all instances.
    Should be called when shutting down the application or finishing with a specific browser instance.
    
    Args:
        browser_instance_id (Optional[str]): Specific browser instance to cleanup, 
                                           or None to cleanup all instances
    """
    if browser_instance_id:
        await close_browser_manager(instance_id=browser_instance_id)
        logger.info(f"Browser resources cleaned up for instance: {browser_instance_id}")
    else:
        await close_all_browser_managers()
        logger.info("All browser resources cleaned up")


async def batch_fetch_pages(urls: list, timeout: int = 30, max_retries: int = 3, 
                          concurrent_limit: int = 5, browser_instance_id: Optional[str] = None) -> dict:
    """
    Fetch multiple pages concurrently with a concurrency limit.
    Uses the managed browser system for efficient resource management.
    
    Args:
        urls (list): List of URLs to fetch
        timeout (int): Page load timeout in seconds
        max_retries (int): Maximum number of retry attempts per URL
        concurrent_limit (int): Maximum number of concurrent requests
        browser_instance_id (Optional[str]): Unique browser instance ID for process isolation
        
    Returns:
        dict: Dictionary mapping URLs to their BeautifulSoup objects (or None if failed)
    """
    semaphore = asyncio.Semaphore(concurrent_limit)
    results = {}
    
    async def fetch_with_semaphore(url: str):
        async with semaphore:
            result = await fetch_page_content(url, timeout, max_retries, browser_instance_id)
            results[url] = result
            return result
    
    # Create tasks for all URLs
    tasks = [fetch_with_semaphore(url) for url in urls]
    
    try:
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Batch fetch completed: {len([r for r in results.values() if r is not None])}/{len(urls)} successful")
    except Exception as e:
        logger.error(f"Batch fetch error: {e}")
    
    return results