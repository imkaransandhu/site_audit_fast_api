#!/usr/bin/env python3
"""
Robust Playwright Browser Management Module

This module provides centralized, efficient browser management with proper resource cleanup,
browser pooling, and error handling for the website audit system.

Features:
- Browser instance pooling for efficiency
- Automatic resource cleanup
- Context-based isolation
- Error handling and recovery
- Memory management

Author: AI Assistant
Version: 1.0
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, AsyncGenerator
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Centralized browser management with pooling and proper cleanup.
    """
    
    def __init__(self, 
                 max_browsers: int = 3,
                 max_contexts_per_browser: int = 10,
                 browser_args: Optional[list] = None):
        """
        Initialize the browser manager.
        
        Args:
            max_browsers (int): Maximum number of browser instances to maintain
            max_contexts_per_browser (int): Maximum contexts per browser
            browser_args (Optional[list]): Custom browser launch arguments
        """
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.browser_args = browser_args or [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-blink-features=AutomationControlled',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--memory-pressure-off'  # Prevent memory pressure cleanup
        ]
        
        self._playwright: Optional[Playwright] = None
        self._browsers: list = []
        self._browser_contexts: Dict[Browser, int] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._closed = False

    async def initialize(self) -> None:
        """Initialize the browser manager with Playwright instance."""
        if self._initialized or self._closed:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            try:
                self._playwright = await async_playwright().start()
                logger.info(f"BrowserManager initialized with max_browsers={self.max_browsers}")
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize BrowserManager: {e}")
                raise

    async def _get_or_create_browser(self) -> Browser:
        """Get an existing browser or create a new one if needed."""
        # Try to find a browser with available contexts
        for browser in self._browsers:
            if self._browser_contexts.get(browser, 0) < self.max_contexts_per_browser:
                try:
                    # Check if browser is still connected
                    if browser.is_connected():
                        return browser
                    else:
                        # Remove disconnected browser
                        self._browsers.remove(browser)
                        if browser in self._browser_contexts:
                            del self._browser_contexts[browser]
                except Exception:
                    # Browser is invalid, remove it
                    if browser in self._browsers:
                        self._browsers.remove(browser)
                    if browser in self._browser_contexts:
                        del self._browser_contexts[browser]
        
        # Create new browser if we haven't reached the limit
        if len(self._browsers) < self.max_browsers:
            try:
                browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=self.browser_args
                )
                self._browsers.append(browser)
                self._browser_contexts[browser] = 0
                logger.debug(f"Created new browser. Total browsers: {len(self._browsers)}")
                return browser
            except Exception as e:
                logger.error(f"Failed to create new browser: {e}")
                raise
        
        # If we're at the limit, use the browser with the fewest contexts
        if self._browsers:
            browser = min(self._browsers, key=lambda b: self._browser_contexts.get(b, 0))
            return browser
        
        raise RuntimeError("No browsers available and cannot create new ones")

    @asynccontextmanager
    async def get_page(self, **context_options) -> AsyncGenerator[Page, None]:
        """
        Get a page instance with automatic cleanup.
        
        Args:
            **context_options: Options to pass to browser.new_context()
            
        Yields:
            Page: A Playwright page instance
        """
        if not self._initialized:
            await self.initialize()
            
        if self._closed:
            raise RuntimeError("BrowserManager has been closed")
        
        context = None
        page = None
        browser = None
        
        try:
            async with self._lock:
                browser = await self._get_or_create_browser()
                self._browser_contexts[browser] = self._browser_contexts.get(browser, 0) + 1
            
            # Create context with default options
            default_context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'extra_http_headers': {
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            }
            default_context_options.update(context_options)
            
            context = await browser.new_context(**default_context_options)
            page = await context.new_page()
            
            logger.debug(f"Created page in context. Browser contexts: {self._browser_contexts.get(browser, 0)}")
            
            yield page
            
        except Exception as e:
            logger.error(f"Error in get_page: {e}")
            raise
            
        finally:
            # Cleanup resources
            if page:
                try:
                    await page.close()
                    logger.debug("Page closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")
                    
            if context:
                try:
                    await context.close()
                    logger.debug("Context closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
                    
            # Update context count
            if browser and browser in self._browser_contexts:
                async with self._lock:
                    self._browser_contexts[browser] = max(0, self._browser_contexts[browser] - 1)

    @asynccontextmanager
    async def get_browser_context(self, **context_options) -> AsyncGenerator[BrowserContext, None]:
        """
        Get a browser context with automatic cleanup.
        
        Args:
            **context_options: Options to pass to browser.new_context()
            
        Yields:
            BrowserContext: A Playwright browser context instance
        """
        if not self._initialized:
            await self.initialize()
            
        if self._closed:
            raise RuntimeError("BrowserManager has been closed")
        
        context = None
        browser = None
        
        try:
            async with self._lock:
                browser = await self._get_or_create_browser()
                self._browser_contexts[browser] = self._browser_contexts.get(browser, 0) + 1
            
            # Create context with default options
            default_context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'extra_http_headers': {
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            }
            default_context_options.update(context_options)
            
            context = await browser.new_context(**default_context_options)
            
            yield context
            
        except Exception as e:
            logger.error(f"Error in get_browser_context: {e}")
            raise
            
        finally:
            # Cleanup resources
            if context:
                try:
                    await context.close()
                    logger.debug("Context closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
                    
            # Update context count
            if browser and browser in self._browser_contexts:
                async with self._lock:
                    self._browser_contexts[browser] = max(0, self._browser_contexts[browser] - 1)

    async def close(self) -> None:
        """Close all browsers and cleanup resources."""
        if self._closed:
            return
            
        logger.info("Closing BrowserManager...")
        
        async with self._lock:
            self._closed = True
            
            # Close all browsers
            for browser in self._browsers:
                try:
                    if browser.is_connected():
                        await browser.close()
                        logger.debug("Browser closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")
            
            # Close playwright instance
            if self._playwright:
                try:
                    await self._playwright.stop()
                    logger.debug("Playwright instance stopped")
                except Exception as e:
                    logger.warning(f"Error stopping Playwright: {e}")
            
            # Clear references
            self._browsers.clear()
            self._browser_contexts.clear()
            self._playwright = None
            self._initialized = False
        
        logger.info("BrowserManager closed successfully")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get current browser manager statistics."""
        return {
            'initialized': self._initialized,
            'closed': self._closed,
            'total_browsers': len(self._browsers),
            'max_browsers': self.max_browsers,
            'browser_contexts': dict(self._browser_contexts),
            'total_active_contexts': sum(self._browser_contexts.values())
        }


# Process-isolated browser manager instances
import os
_process_browser_managers: Dict[str, BrowserManager] = {}


def _get_process_instance_key(instance_id: Optional[str] = None) -> str:
    """Generate a unique key for this process and instance."""
    process_id = os.getpid()
    if instance_id:
        return f"pid_{process_id}_{instance_id}"
    else:
        return f"pid_{process_id}_default"


async def get_browser_manager(instance_id: Optional[str] = None) -> BrowserManager:
    """
    Get or create a browser manager instance isolated by process and optional instance ID.
    
    Args:
        instance_id (Optional[str]): Optional unique identifier for multiple instances 
                                   within the same process
    
    Returns:
        BrowserManager: A process-isolated browser manager instance
    """
    instance_key = _get_process_instance_key(instance_id)
    
    if instance_key not in _process_browser_managers or _process_browser_managers[instance_key]._closed:
        # Create unique browser args with process-specific port
        process_id = os.getpid()
        base_debug_port = 9222 + (process_id % 1000)
        
        # Add instance offset if instance_id is provided
        if instance_id:
            instance_hash = hash(instance_id) % 100
            base_debug_port += instance_hash
        
        browser_args = [
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-web-security',
            '--disable-blink-features=AutomationControlled',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--memory-pressure-off'
        ]
        
        _process_browser_managers[instance_key] = BrowserManager(browser_args=browser_args)
        await _process_browser_managers[instance_key].initialize()
        
        logger.info(f"Created process-isolated browser manager: {instance_key} (port: {base_debug_port})")
    
    return _process_browser_managers[instance_key]


async def close_browser_manager(instance_id: Optional[str] = None) -> None:
    """
    Close a specific browser manager instance.
    
    Args:
        instance_id (Optional[str]): Optional unique identifier for the instance to close
    """
    instance_key = _get_process_instance_key(instance_id)
    
    if instance_key in _process_browser_managers and not _process_browser_managers[instance_key]._closed:
        await _process_browser_managers[instance_key].close()
        del _process_browser_managers[instance_key]
        
        # Cleanup temp profile directory
        import shutil
        profile_path = f'/tmp/browser_profile_{instance_key}'
        try:
            shutil.rmtree(profile_path)
            logger.debug(f"Cleaned up browser profile: {profile_path}")
        except Exception as e:
            logger.debug(f"Could not cleanup browser profile {profile_path}: {e}")


async def close_all_browser_managers() -> None:
    """Close all browser manager instances for this process."""
    for instance_key in list(_process_browser_managers.keys()):
        try:
            if not _process_browser_managers[instance_key]._closed:
                await _process_browser_managers[instance_key].close()
        except Exception as e:
            logger.warning(f"Error closing browser manager {instance_key}: {e}")
    
    _process_browser_managers.clear()


# Backward compatibility - maintain global browser manager functions
async def get_global_browser_manager() -> BrowserManager:
    """Get or create the global browser manager instance (backward compatibility)."""
    return await get_browser_manager(instance_id=None)


async def close_global_browser_manager() -> None:
    """Close the global browser manager instance (backward compatibility)."""
    await close_browser_manager(instance_id=None)


@asynccontextmanager
async def managed_page(instance_id: Optional[str] = None, **context_options) -> AsyncGenerator[Page, None]:
    """
    Convenience function to get a managed page from a process-isolated browser manager.
    
    Args:
        instance_id (Optional[str]): Optional unique identifier for browser instance
        **context_options: Options to pass to browser.new_context()
        
    Yields:
        Page: A Playwright page instance
    """
    manager = await get_browser_manager(instance_id=instance_id)
    async with manager.get_page(**context_options) as page:
        yield page


@asynccontextmanager  
async def managed_browser_context(instance_id: Optional[str] = None, **context_options) -> AsyncGenerator[BrowserContext, None]:
    """
    Convenience function to get a managed browser context from a process-isolated browser manager.
    
    Args:
        instance_id (Optional[str]): Optional unique identifier for browser instance
        **context_options: Options to pass to browser.new_context()
        
    Yields:
        BrowserContext: A Playwright browser context instance
    """
    manager = await get_browser_manager(instance_id=instance_id)
    async with manager.get_browser_context(**context_options) as context:
        yield context