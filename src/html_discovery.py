#!/usr/bin/env python3
"""
HTML discovery module for Website Content Audit Crawler.

This module handles crawling HTML pages to discover internal links and build
a comprehensive list of all pages on a website through recursive link following.
Supports both sequential and concurrent discovery approaches.

Author: AI Assistant
Version: 2.0
"""

import asyncio
import logging
import time
from typing import List, Set, Tuple, Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from collections import deque

from .utils import is_same_domain, clean_url
from .page_fetcher import fetch_page_content
from .browser_manager import managed_page

# Configure logging
logger = logging.getLogger(__name__)


async def discover_html_pages(base_url: str, max_pages: int = None, max_depth: int = 3, 
                            delay: float = 1.0) -> Tuple[List[str], int, Dict[str, str]]:
    """
    Discover all HTML pages on a website through recursive link following.
    
    Args:
        base_url (str): Base URL of the website to crawl
        max_pages (int, optional): Maximum number of pages to discover (None for no limit)
        max_depth (int): Maximum depth to crawl from the base URL
        delay (float): Delay between requests in seconds
        
    Returns:
        Tuple[List[str], int, Dict[str, str]]: Tuple containing:
            - List of discovered URLs
            - Total count of discovered URLs
            - Dictionary of failed URLs with error messages
    """
    logger.info(f"Starting HTML page discovery for {base_url}")
    logger.info(f"Max pages: {max_pages}, Max depth: {max_depth}, Delay: {delay}s")
    
    # Initialize tracking sets and queue
    discovered_urls: Set[str] = set()
    processed_urls: Set[str] = set()
    failed_urls: Set[str] = set()
    
    # Queue stores tuples of (url, depth)
    url_queue = deque([(clean_url(base_url), 0)])
    discovered_urls.add(clean_url(base_url))
    
    pages_processed = 0
    
    while url_queue and (max_pages is None or pages_processed < max_pages):
        current_url, current_depth = url_queue.popleft()
        
        # Skip if already processed or depth exceeded
        if current_url in processed_urls or current_depth > max_depth:
            continue
            
        logger.info(f"Processing page {pages_processed + 1}: {current_url} (depth: {current_depth})")
        
        try:
            # Fetch the page content
            soup = await fetch_page_content(current_url)
            
            if soup is None:
                failed_urls.add(current_url)
                logger.warning(f"Failed to fetch page: {current_url}")
                continue
            
            # Mark as processed
            processed_urls.add(current_url)
            pages_processed += 1
            
            # Discover new links from this page
            if current_depth < max_depth:  # Only follow links if not at max depth
                new_links = _extract_html_links(soup, current_url, base_url)
                
                for link in new_links:
                    clean_link = clean_url(link)
                    if clean_link not in discovered_urls and clean_link not in failed_urls:
                        discovered_urls.add(clean_link)
                        url_queue.append((clean_link, current_depth + 1))
            
            # Add delay between requests to be respectful
            if delay > 0:
                await asyncio.sleep(delay)
                
        except Exception as e:
            failed_urls.add(current_url)
            logger.error(f"Error processing {current_url}: {str(e)}")
    
    # Convert to list for consistent return type
    final_urls = list(discovered_urls)
    
    logger.info(f"HTML discovery completed:")
    logger.info(f"- Total URLs discovered: {len(final_urls)}")
    logger.info(f"- Pages successfully processed: {pages_processed}")
    logger.info(f"- Failed URLs: {len(failed_urls)}")
    
    # Convert failed URLs set to dictionary with error messages
    failed_dict = {}
    for url in failed_urls:
        failed_dict[url] = "Failed to fetch or parse HTML content"
    
    if failed_urls:
        logger.debug(f"Failed URLs: {failed_urls}")
    
    return final_urls, len(final_urls), failed_dict


def _extract_html_links(soup: BeautifulSoup, current_url: str, base_url: str) -> Set[str]:
    """
    Extract all internal HTML page links from a BeautifulSoup object.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        current_url (str): URL of the current page
        base_url (str): Base URL of the website
        
    Returns:
        Set[str]: Set of internal HTML page URLs found on the page
    """
    links = set()
    
    # Find all anchor tags with href attributes
    for link_tag in soup.find_all('a', href=True):
        href = link_tag.get('href', '').strip()
        
        if not href:
            continue
        
        # Skip certain link types
        if _should_skip_link(href):
            continue
        
        # Convert relative URLs to absolute
        absolute_url = urljoin(current_url, href)
        
        # Only include links from the same domain
        if not is_same_domain(absolute_url, base_url):
            continue
        
        # Only include links that appear to be HTML pages
        if _is_likely_html_page(absolute_url):
            links.add(absolute_url)
    
    logger.debug(f"Found {len(links)} internal HTML links on {current_url}")
    return links


def _should_skip_link(href: str) -> bool:
    """
    Determine if a link should be skipped based on various criteria.
    
    Args:
        href (str): The href attribute value
        
    Returns:
        bool: True if the link should be skipped, False otherwise
    """
    href_lower = href.lower().strip()
    
    # Skip javascript, mailto, tel, and other non-HTTP links
    skip_protocols = ['javascript:', 'mailto:', 'tel:', 'ftp:', 'file:', 'data:']
    for protocol in skip_protocols:
        if href_lower.startswith(protocol):
            return True
    
    # Skip anchor links (same page fragments)
    if href.startswith('#'):
        return True
    
    # Skip URLs that are just query parameters or fragments
    if href.startswith('?') or href.startswith('#'):
        return True
    
    # Skip empty or whitespace-only links
    if not href.strip():
        return True
    
    return False


def _is_likely_html_page(url: str) -> bool:
    """
    Determine if a URL is likely to be an HTML page rather than an asset.
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if likely an HTML page, False if likely an asset
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Common asset file extensions to exclude
    asset_extensions = {
        # Images
        'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico',
        # Documents
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf',
        # Media
        'mp4', 'mp3', 'wav', 'avi', 'mov', 'wmv', 'flv', 'webm', 'ogg',
        # Archives
        'zip', 'rar', '7z', 'tar', 'gz',
        # Web assets
        'css', 'js', 'json', 'xml', 'rss',
        # Other
        'woff', 'woff2', 'ttf', 'eot'
    }
    
    # Check if URL ends with an asset extension
    if '.' in path:
        extension = path.split('.')[-1].split('?')[0].split('#')[0]  # Remove query params
        if extension in asset_extensions:
            return False
    
    # URLs without extensions or with HTML extensions are likely HTML pages
    html_extensions = {'html', 'htm', 'php', 'asp', 'aspx', 'jsp'}
    
    if '.' in path:
        extension = path.split('.')[-1].split('?')[0].split('#')[0]
        return extension in html_extensions or extension == ''
    
    # URLs without file extensions are likely HTML pages
    return True


async def get_page_links_batch(urls: List[str], base_url: str, concurrent_limit: int = 5) -> dict:
    """
    Get all internal links from multiple pages concurrently.
    
    Args:
        urls (List[str]): List of URLs to process
        base_url (str): Base URL of the website
        concurrent_limit (int): Maximum number of concurrent requests
        
    Returns:
        dict: Dictionary mapping URLs to sets of links found on each page
    """
    semaphore = asyncio.Semaphore(concurrent_limit)
    results = {}
    
    async def process_single_page(url: str):
        async with semaphore:
            try:
                soup = await fetch_page_content(url)
                if soup:
                    links = _extract_html_links(soup, url, base_url)
                    results[url] = links
                    logger.debug(f"Found {len(links)} links on {url}")
                else:
                    results[url] = set()
                    logger.warning(f"Failed to fetch {url}")
            except Exception as e:
                results[url] = set()
                logger.error(f"Error processing {url}: {str(e)}")
    
    # Create tasks for all URLs
    tasks = [process_single_page(url) for url in urls]
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


def discover_html_pages_sync(base_url: str, max_pages: int = None, max_depth: int = 3, 
                           delay: float = 1.0) -> Tuple[List[str], int]:
    """
    Synchronous wrapper for the async HTML page discovery function.
    
    Args:
        base_url (str): Base URL of the website to crawl
        max_pages (int, optional): Maximum number of pages to discover
        max_depth (int): Maximum depth to crawl from the base URL
        delay (float): Delay between requests in seconds
        
    Returns:
        Tuple[List[str], int]: Tuple containing (list of discovered URLs, total count)
    """
    try:
        # Try to use existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is already running, create a new thread
            import concurrent.futures
            import threading
            
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        discover_html_pages(base_url, max_pages, max_depth, delay)
                    )
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        
        return loop.run_until_complete(discover_html_pages(base_url, max_pages, max_depth, delay))
        
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(discover_html_pages(base_url, max_pages, max_depth, delay))


async def discover_html_pages_concurrent(base_url: str, max_pages: int = None, max_depth: int = 3, 
                                        delay: float = 1.0, max_concurrent: int = 10, 
                                        progress_callback=None, browser_instance_id: Optional[str] = None) -> Tuple[List[str], int, Dict[str, str]]:
    """
    Discover HTML pages using concurrent processing for much faster performance.
    
    Args:
        base_url (str): Base URL of the website to crawl
        max_pages (int, optional): Maximum number of pages to discover (None for no limit)
        max_depth (int): Maximum depth to crawl from the base URL
        delay (float): Base delay between requests in seconds (adjusted for concurrency)
        max_concurrent (int): Maximum number of concurrent workers
        progress_callback (callable, optional): Callback function(urls_list, count) to report incremental progress
        browser_instance_id (Optional[str]): Unique browser instance ID for process isolation
        
    Returns:
        Tuple[List[str], int, Dict[str, str]]: Tuple containing:
            - List of discovered URLs
            - Total count of discovered URLs
            - Dictionary of failed URLs with error messages
    """
    # Generate unique browser instance ID if not provided
    if browser_instance_id is None:
        import os
        from datetime import datetime
        browser_instance_id = f"html_discovery_{os.getpid()}_{datetime.now().strftime('%H%M%S%f')}"
    start_time = time.time()
    logger.info(f"Starting CONCURRENT HTML page discovery for {base_url}")
    logger.info(f"Parameters: max_pages={max_pages}, max_depth={max_depth}, workers={max_concurrent}")
    
    # Data structures for concurrent processing
    discovered_urls = {base_url}
    processed_urls = set()
    processing_urls = set()  # Currently being processed
    failed_urls = {}
    url_queue = asyncio.Queue()
    
    # Add base URL to processing queue
    await url_queue.put((base_url, 0))
    
    # Semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Adjust delay for concurrent processing
    concurrent_delay = delay / max_concurrent if delay > 0 else 0
    
    # Statistics
    pages_processed = 0
    
    # Track active workers
    active_workers = 0
    workers_lock = asyncio.Lock()
    
    async def worker(worker_id: int):
        """Worker coroutine to process URLs concurrently."""
        nonlocal pages_processed, active_workers
        
        async with workers_lock:
            active_workers += 1
        
        worker_processed = 0
        consecutive_timeouts = 0
        
        try:
            while True:
                try:
                    # Increased timeout and better termination logic
                    url, depth = await asyncio.wait_for(url_queue.get(), timeout=5.0)
                    consecutive_timeouts = 0  # Reset timeout counter
                    
                    # Check if we should continue processing
                    if (url in processed_urls or 
                        len(discovered_urls) >= (max_pages or float('inf'))):
                        url_queue.task_done()
                        continue
                    
                    # Mark as being processed
                    if url in processing_urls:
                        url_queue.task_done()
                        continue
                    
                    processing_urls.add(url)
                    processed_urls.add(url)
                    worker_processed += 1
                    pages_processed += 1
                    
                    # Process URL with semaphore control
                    async with semaphore:
                        new_urls = await process_single_page_concurrent(
                            url, depth, base_url, max_depth, worker_id, browser_instance_id
                        )
                        
                        # Add newly discovered URLs to queue and discovered set
                        for new_url in new_urls:
                            if (new_url not in discovered_urls and 
                                new_url not in processing_urls and
                                len(discovered_urls) < (max_pages or float('inf'))):
                                discovered_urls.add(new_url)
                                await url_queue.put((new_url, depth + 1))
                    
                    # Remove from processing set
                    processing_urls.discard(url)
                    
                    # Log progress and call progress callback (from worker 0 only to avoid spam)
                    if worker_id == 0 and worker_processed % 5 == 0:
                        elapsed = time.time() - start_time
                        rate = pages_processed / elapsed if elapsed > 0 else 0
                        logger.info(f"🔍 Worker progress: {pages_processed} processed, {len(discovered_urls)} discovered "
                                  f"({rate:.1f} pages/sec)")
                        
                        # Call progress callback if provided
                        if progress_callback:
                            try:
                                progress_callback(list(discovered_urls), len(discovered_urls))
                            except Exception as e:
                                logger.warning(f"Progress callback error: {e}")
                    
                    url_queue.task_done()
                    
                    # Add delay to be respectful to the server
                    if concurrent_delay > 0:
                        await asyncio.sleep(concurrent_delay)
                        
                except asyncio.TimeoutError:
                    consecutive_timeouts += 1
                    
                    # Only exit if we've had multiple timeouts AND there are no active tasks
                    if consecutive_timeouts >= 3 and url_queue.empty():
                        logger.debug(f"Worker {worker_id} stopping after {consecutive_timeouts} consecutive timeouts")
                        break
                    
                    # Check if other workers are still active
                    async with workers_lock:
                        if active_workers <= 1 and url_queue.empty():
                            logger.debug(f"Worker {worker_id} is last active worker, stopping")
                            break
                            
                except Exception as e:
                    logger.error(f"Worker {worker_id} error processing {url if 'url' in locals() else 'unknown'}: {str(e)}")
                    if 'url' in locals():
                        failed_urls[url] = f"Worker error: {str(e)}"
                        processing_urls.discard(url)
                    url_queue.task_done()
                    
        except Exception as e:
            logger.error(f"Worker {worker_id} fatal error: {str(e)}")
            
        finally:
            async with workers_lock:
                active_workers -= 1
            logger.debug(f"Worker {worker_id} processed {worker_processed} URLs")
    
    async def process_single_page_concurrent(url: str, depth: int, base_url: str, max_depth: int, worker_id: int, browser_instance_id: str) -> List[str]:
        """Process a single page using managed browser instance for efficient resource management."""
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        try:
            # Use managed page with specific browser instance for process isolation
            async with managed_page(instance_id=browser_instance_id) as page:
                # Better loading strategy for JavaScript-heavy sites
                await page.goto(url, timeout=60000, wait_until='networkidle')
                
                # Wait for JavaScript to render dynamic content
                await page.wait_for_timeout(2000)
                
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                
                logger.debug(f"Worker {worker_id}: Successfully processed {url}")
                
                if not soup:
                    failed_urls[url] = "Failed to parse page content"
                    return []
                
                # Extract new URLs if within depth limit
                new_urls = []
                if depth < max_depth:
                    links_found = 0
                    for link in soup.find_all('a', href=True):
                        href = link.get('href')
                        if href and _is_valid_html_url(href):
                            absolute_url = urljoin(base_url, href)
                            if is_same_domain(absolute_url, base_url):
                                new_urls.append(absolute_url)
                                links_found += 1
                    
                    logger.debug(f"Worker {worker_id}: Found {links_found} valid HTML links on {url}")
                    # Remove duplicates and filter out already discovered URLs
                    new_urls = [link for link in set(new_urls) if link not in discovered_urls and link not in processing_urls]
                
                return new_urls
            
        except Exception as e:
            failed_urls[url] = f"Processing error: {str(e)}"
            logger.debug(f"Worker {worker_id} error processing {url}: {str(e)}")
            return []
    
    # Start concurrent workers
    logger.info(f"🚀 Starting {max_concurrent} concurrent workers for HTML discovery")
    workers = [asyncio.create_task(worker(i)) for i in range(max_concurrent)]
    
    # Wait for all URLs to be processed with better completion detection
    try:
        await url_queue.join()
    except:
        pass
    
    # Wait a bit for any final URL additions
    await asyncio.sleep(1.0)
    
    # Wait for remaining queue items if any
    if not url_queue.empty():
        try:
            await url_queue.join()
        except:
            pass
    
    # Cancel workers gracefully
    for worker in workers:
        worker.cancel()
    
    # Wait for workers to finish
    await asyncio.gather(*workers, return_exceptions=True)
    
    # Final results
    final_urls = list(discovered_urls)
    final_urls.sort()  # Sort alphabetically for consistency
    
    # Convert failed URLs set to dictionary with error messages
    failed_dict = {}
    for url in failed_urls:
        if url not in failed_dict:
            failed_dict[url] = failed_urls.get(url, "Failed to fetch or parse HTML content")
    
    total_time = time.time() - start_time
    successful_count = len(processed_urls)
    logger.info(f"✅ CONCURRENT HTML discovery completed:")
    logger.info(f"   • Total URLs discovered: {len(final_urls)}")
    logger.info(f"   • Successfully processed: {successful_count}")
    logger.info(f"   • Failed URLs: {len(failed_dict)}")
    logger.info(f"   • Processing time: {total_time:.2f}s")
    logger.info(f"   • Average rate: {successful_count/total_time:.1f} pages/sec")
    
    if failed_dict:
        logger.debug(f"Failed URLs: {list(failed_dict.keys())[:5]}...")  # Show first 5
    
    return final_urls, successful_count, failed_dict


def _is_valid_html_url(url: str) -> bool:
    """
    Check if a URL is likely to be an HTML page, not an asset.
    Focuses on file extension checking without path-based filtering.
    
    Args:
        url (str): The URL to check
        
    Returns:
        bool: True if it's likely an HTML page, False otherwise
    """
    from urllib.parse import urlparse, unquote
    
    # Skip empty URLs, fragments, and non-HTTP protocol links
    if not url or not url.strip():
        return False
    
    url = url.strip()
    if (url.startswith('#') or url.startswith('javascript:') or url.startswith('mailto:') or 
        url.startswith('tel:') or url.startswith('data:') or url.startswith('ftp:')):
        return False
    
    # Skip URLs that are just query parameters or fragments
    if url.startswith('?') or url.startswith('#'):
        return False
    
    # Parse the URL to get the path and clean it
    try:
        parsed = urlparse(unquote(url))
        path = parsed.path.lower().strip('/')
        
        # Additional checks for query parameters that indicate non-HTML content
        if parsed.query:
            return False
        
        # Skip if fragment identifier suggests non-HTML content
        if parsed.fragment:
            return False
                    
    except Exception:
        return False
    
    # Skip common asset file extensions
    asset_extensions = {
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tiff', '.ico',
        # Documents
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf',
        # Media
        '.mp4', '.mp3', '.avi', '.mov', '.wav', '.m4v', '.wmv', '.flv', '.webm',
        # Archives
        '.zip', '.rar', '.tar', '.gz', '.7z',
        # Code/Data files
        '.css', '.js', '.json', '.xml', '.csv', '.sql',
        # Fonts
        '.woff', '.woff2', '.ttf', '.eot', '.otf'
    }
    
    # Check if URL ends with any asset extension
    for ext in asset_extensions:
        if path.endswith(ext):
            return False
    
    # Note: Query parameter filtering is now handled above in the main parsing section
    
    # If no extension or HTML-like extension, likely an HTML page
    html_extensions = {'.html', '.htm', '.php', '.asp', '.aspx', '.jsp'}
    
    # Check if it has an HTML extension
    for ext in html_extensions:
        if path.endswith(ext):
            return True
    
    # If no extension (like /about or /contact), likely HTML
    if '.' not in path.split('/')[-1]:
        return True
    
    return False