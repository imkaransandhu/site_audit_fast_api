#!/usr/bin/env python3
"""
Improved Website Content Audit Crawler

A comprehensive tool for crawling websites and generating detailed content audit reports.
This version provides better organization, error handling, and follows best practices.

Features:
- Sitemap discovery and parsing
- HTML page discovery through link following  
- Comprehensive asset extraction from HTML and CSS
- Improved error handling and logging
- Modular architecture for maintainability

Author: AI Assistant
Version: 2.0
"""

import json
import logging
import asyncio
import concurrent.futures
import os
import threading
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from src.utils import validate_url, sanitize_url_for_filename, ensure_directory_exists
from src.sitemap_parser import get_all_sitemap_urls
from src.html_discovery import discover_html_pages_concurrent
from src.page_fetcher import fetch_page_content, cleanup_browser_resources
from src.asset_extractor import extract_assets_from_page, consolidate_assets, get_assets_summary, get_assets_summary_by_extension

# Configure logging with proper path
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, 'website_audit.log'))
    ]
)
logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    Tracks audit progress for periodic saving functionality.
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.start_time = datetime.now()
        self.current_step = "initializing"
        self.step_start_time = datetime.now()
        self.steps_completed = []
        self.progress_data = {
            'audit_info': {
                'base_url': base_url,
                'start_time': self.start_time.isoformat(),
                'current_step': self.current_step,
                'steps_completed': [],
                'is_final': False
            },
            'sitemap_discovery': {'completed': False, 'urls_found': [], 'total_count': 0},
            'html_discovery': {'completed': False, 'urls_found': [], 'total_count': 0},
            'asset_extraction': {'completed': False, 'progress_percent': 0},
            'crawl_summary': {
                'sitemap_found': False,
                'steps_completed': [],
                'current_step_duration': 0,
                'total_duration': 0
            }
        }
        self.timer_task = None
        self.saving_enabled = True
    
    def start_step(self, step_name: str):
        """Start tracking a new step."""
        if self.current_step != "initializing":
            # Complete previous step
            step_duration = (datetime.now() - self.step_start_time).total_seconds()
            self.steps_completed.append({
                'step': self.current_step,
                'duration_seconds': round(step_duration, 2),
                'completed_at': datetime.now().isoformat()
            })
        
        self.current_step = step_name
        self.step_start_time = datetime.now()
        logger.info(f"🔄 Starting {step_name}")
        
        # Update progress data
        self.progress_data['audit_info']['current_step'] = step_name
        self.progress_data['audit_info']['steps_completed'] = self.steps_completed.copy()
    
    def update_sitemap_progress(self, urls_found: List[str], sitemap_found: bool):
        """Update sitemap discovery progress."""
        self.progress_data['sitemap_discovery'] = {
            'completed': True,
            'urls_found': urls_found,
            'total_count': len(urls_found)
        }
        self.progress_data['crawl_summary']['sitemap_found'] = sitemap_found
        logger.info(f"✅ Sitemap discovery completed: {len(urls_found)} URLs, sitemap_found={sitemap_found}")
    
    def update_html_progress_incremental(self, urls_found: List[str], html_count: int):
        """Update HTML discovery progress incrementally during discovery (not completed)."""
        self.progress_data['html_discovery'] = {
            'completed': False,  # Still in progress
            'urls_found': urls_found,
            'total_count': html_count
        }
        if html_count > 0 and html_count % 50 == 0:  # Log every 50 URLs
            logger.info(f"🔄 HTML discovery in progress: {html_count} URLs found so far")
    
    def update_html_progress(self, urls_found: List[str], html_count: int):
        """Update HTML discovery progress (completed)."""
        self.progress_data['html_discovery'] = {
            'completed': True,
            'urls_found': urls_found,
            'total_count': html_count
        }
        logger.info(f"✅ HTML discovery completed: {html_count} URLs found")
    
    def update_asset_progress_incremental(self, processed_count: int, total_count: int, 
                                         processed_urls: List[str], failed_extractions: Optional[Dict[str, str]] = None):
        """Update asset extraction progress incrementally during processing (not completed)."""
        progress_percent = (processed_count / total_count * 100) if total_count > 0 else 0
        self.progress_data['asset_extraction'] = {
            'completed': False,  # Still in progress
            'progress_percent': round(progress_percent, 1),
            'processed_count': processed_count,
            'total_count': total_count,
            'processed_urls': processed_urls[-50:] if len(processed_urls) > 50 else processed_urls,  # Keep last 50 for report size
            'failed_extractions': failed_extractions or {}
        }
        
        if processed_count % 50 == 0:  # Log every 50 URLs
            logger.info(f"🔄 Asset extraction in progress: {processed_count}/{total_count} ({progress_percent:.1f}%)")
    
    def update_asset_progress(self, processed_count: int, total_count: int, failed_extractions: Optional[Dict[str, str]] = None):
        """Update asset extraction progress (completed)."""
        progress_percent = (processed_count / total_count * 100) if total_count > 0 else 0
        self.progress_data['asset_extraction'] = {
            'completed': processed_count >= total_count,
            'progress_percent': round(progress_percent, 1),
            'processed_count': processed_count,
            'total_count': total_count,
            'failed_extractions': failed_extractions or {}
        }
        
        if processed_count % 100 == 0 or processed_count >= total_count:
            logger.info(f"📊 Asset extraction progress: {processed_count}/{total_count} ({progress_percent:.1f}%)")
            if failed_extractions:
                logger.info(f"❌ Failed asset extractions so far: {len(failed_extractions)}")
    
    def get_current_progress_report(self) -> Dict:
        """Generate current progress report for periodic saving."""
        current_time = datetime.now()
        total_duration = (current_time - self.start_time).total_seconds()
        current_step_duration = (current_time - self.step_start_time).total_seconds()
        
        # Update timing information
        self.progress_data['audit_info']['current_time'] = current_time.isoformat()
        self.progress_data['audit_info']['total_duration_seconds'] = round(total_duration, 2)
        
        self.progress_data['crawl_summary'].update({
            'steps_completed': self.steps_completed.copy(),
            'current_step_duration': round(current_step_duration, 2),
            'total_duration': round(total_duration, 2)
        })
        
        # Create comprehensive interim report structure
        interim_report = self.progress_data.copy()
        
        # Add discovered URLs to interim report if available
        if self.progress_data['sitemap_discovery']['completed']:
            # Sort sitemap URLs for consistent output
            sitemap_urls = sorted(self.progress_data['sitemap_discovery']['urls_found'])
            interim_report['sitemap_discovery']['urls_found'] = sitemap_urls
            
        # Show HTML discovery URLs even if step is not completed (in-progress)
        if self.progress_data['html_discovery']['urls_found']:  # Has URLs regardless of completion status
            # Sort HTML discovery URLs for consistent output
            html_urls = sorted(self.progress_data['html_discovery']['urls_found'])
            interim_report['html_discovery']['urls_found'] = html_urls
            
            # If both sitemap is complete and we have HTML URLs, calculate HTML-only URLs
            if self.progress_data['sitemap_discovery']['completed']:
                sitemap_urls_set = set(self.progress_data['sitemap_discovery']['urls_found'])
                html_urls_set = set(self.progress_data['html_discovery']['urls_found'])
                html_only_urls = html_urls_set - sitemap_urls_set
                sorted_html_only_urls = sorted(html_only_urls)
                
                interim_report['html_only_discovery'] = {
                    'urls_found': sorted_html_only_urls,
                    'total_count': len(sorted_html_only_urls),
                    'description': 'URLs found through HTML discovery but not present in sitemaps'
                }
        
        # Add combined URL statistics if sitemap is complete and we have HTML URLs
        if (self.progress_data['sitemap_discovery']['completed'] and 
            self.progress_data['html_discovery']['urls_found']):  # Don't require completion, just URLs
            
            all_unique_urls = list(set(
                self.progress_data['sitemap_discovery']['urls_found'] + 
                self.progress_data['html_discovery']['urls_found']
            ))
            
            interim_report['crawl_summary']['total_pages_discovered'] = len(all_unique_urls)
            interim_report['crawl_summary']['sitemap_pages'] = self.progress_data['sitemap_discovery']['total_count']
            interim_report['crawl_summary']['html_pages'] = self.progress_data['html_discovery']['total_count']
            interim_report['crawl_summary']['html_only_pages'] = len(html_only_urls) if 'html_only_urls' in locals() else 0
        
        # Show asset extraction progress even if step is not completed (in-progress)
        asset_data = self.progress_data.get('asset_extraction', {})
        if asset_data.get('processed_urls') or asset_data.get('failed_extractions'):
            # Sort processed URLs for consistent output (show last processed URLs)
            processed_urls = asset_data.get('processed_urls', [])
            if processed_urls:
                interim_report['asset_extraction']['processed_urls'] = sorted(processed_urls)
            
            # Include failed extractions if any
            failed_extractions = asset_data.get('failed_extractions', {})
            if failed_extractions:
                interim_report['asset_extraction']['failed_extractions'] = failed_extractions
        
        return interim_report
    
    def finalize_report(self, final_report: Dict) -> Dict:
        """Add final progress tracking information to the complete report."""
        # Complete final step
        if self.current_step != "initializing":
            step_duration = (datetime.now() - self.step_start_time).total_seconds()
            self.steps_completed.append({
                'step': self.current_step,
                'duration_seconds': round(step_duration, 2),
                'completed_at': datetime.now().isoformat()
            })
        
        # Enhance the crawl_summary with our tracking data
        enhanced_crawl_summary = final_report.get('crawl_summary', {})
        enhanced_crawl_summary.update({
            'sitemap_found': self.progress_data['crawl_summary']['sitemap_found'],
            'steps_completed': self.steps_completed,
            'total_steps': len(self.steps_completed),
            'step_details': {step['step']: step['duration_seconds'] for step in self.steps_completed}
        })
        
        final_report['crawl_summary'] = enhanced_crawl_summary
        final_report['audit_info']['is_final'] = True
        
        return final_report
    
    def stop_periodic_saving(self):
        """Stop the periodic saving timer."""
        self.saving_enabled = False
        if self.timer_task:
            self.timer_task.cancel()


async def _save_periodic_progress(progress_tracker: ProgressTracker):
    """
    Save progress report every 10 minutes during audit execution.
    """
    save_interval = 600  # 10 minutes
    
    async def periodic_save():
        while progress_tracker.saving_enabled:
            await asyncio.sleep(save_interval)
            
            if not progress_tracker.saving_enabled:
                break
                
            try:
                progress_report = progress_tracker.get_current_progress_report()
                await _save_audit_report(progress_report, progress_tracker.base_url, is_interim=True)
                logger.info("💾 Periodic progress report saved")
            except Exception as e:
                logger.error(f"❌ Failed to save periodic progress: {e}")
    
    # Start the periodic saving task
    progress_tracker.timer_task = asyncio.create_task(periodic_save())


class WebsiteAuditor:
    """
    Main class for conducting comprehensive website content audits.
    """
    
    def __init__(self, delay: float = 1.0, timeout: int = 30, max_retries: int = 3):
        """
        Initialize the website auditor.
        
        Args:
            delay (float): Delay between requests in seconds
            timeout (int): Request timeout in seconds
            max_retries (int): Maximum number of retries for failed requests
        """
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        
        logger.info(f"WebsiteAuditor initialized with delay={delay}s, timeout={timeout}s, max_retries={max_retries}")


async def conduct_website_audit(base_url: str, max_pages: Optional[int] = None, 
                              max_depth: int = 3, delay: float = 1.0,
                              html_workers: int = 50, asset_workers: int = 50, 
                              batch_size: int = 50,
                              extensions_filter: Optional[List[str]] = None,
                              browser_instance_id: Optional[str] = None) -> Dict:
    """
    Conduct a comprehensive website content audit with concurrent processing and periodic saving.
    
    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl (None for no limit)
        max_depth (int): Maximum depth to crawl (default: 3)
        delay (float): Delay between requests in seconds (default: 1.0)
        html_workers (int): Number of concurrent workers for HTML discovery (default: 10)
        asset_workers (int): Number of concurrent workers for asset extraction (default: 15)
        batch_size (int): Batch size for asset processing (default: 50)
        extensions_filter (Optional[List[str]]): Filter for specific file extensions 
                                               (e.g., ['jpg', 'png', 'pdf', 'mp4'])
                                               Extensions should be lowercase without dots.
                                               If None, extracts all asset types
        browser_instance_id (Optional[str]): Unique browser instance ID for process isolation,
                                            enables running multiple audits simultaneously
        
    Returns:
        Dict: Comprehensive audit report as a structured dictionary
    """
    # Generate unique browser instance ID if not provided
    if browser_instance_id is None:
        browser_instance_id = f"audit_{os.getpid()}_{datetime.now().strftime('%H%M%S%f')}"
    
    logger.info(f"Starting website audit for: {base_url}")
    logger.info(f"Browser instance ID: {browser_instance_id}")
    logger.info(f"Parameters: max_pages={max_pages}, max_depth={max_depth}, delay={delay}")
    logger.info(f"Concurrency: html_workers={html_workers}, asset_workers={asset_workers}, batch_size={batch_size}")
    
    if extensions_filter:
        logger.info(f"Asset extraction filtered to extensions: {extensions_filter}")
    else:
        logger.info("Extracting all asset types")
    
    # Validate input URL
    if not validate_url(base_url):
        error_msg = f"Invalid URL provided: {base_url}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'timestamp': datetime.now().isoformat()
        }
    
    # Initialize progress tracker and start periodic saving
    progress_tracker = ProgressTracker(base_url)
    await _save_periodic_progress(progress_tracker)
    
    audit_start_time = datetime.now()
    
    try:
        # Step 1: Discover URLs from sitemaps
        progress_tracker.start_step("sitemap_discovery")
        logger.info("Step 1: Discovering URLs from sitemaps")
        sitemap_urls, sitemap_count = get_all_sitemap_urls(base_url)
        
        # Determine if sitemap was found
        sitemap_found = sitemap_count > 0
        progress_tracker.update_sitemap_progress(sitemap_urls, sitemap_found)
        
        # Step 2: Discover URLs through CONCURRENT HTML page crawling
        progress_tracker.start_step("html_discovery")
        logger.info("Step 2: Discovering URLs through CONCURRENT HTML page crawling")
        
        # Create progress callback to update tracker incrementally
        def html_progress_callback(urls_found, count):
            progress_tracker.update_html_progress_incremental(urls_found, count)
        
        html_urls, html_count, failed_crawls = await discover_html_pages_concurrent(
            base_url, 
            max_pages=max_pages, 
            max_depth=max_depth, 
            delay=delay,
            max_concurrent=html_workers,
            progress_callback=html_progress_callback,
            browser_instance_id=browser_instance_id
        )
        
        # Final update to mark HTML discovery as completed
        progress_tracker.update_html_progress(html_urls, html_count)
        
        # Step 3: Extract assets from all discovered pages (sitemap + HTML discovery)
        progress_tracker.start_step("asset_extraction")
        logger.info("Step 3: Extracting assets from all discovered pages")
        
        # Combine and deduplicate URLs from both sitemap and HTML discovery
        all_unique_urls = list(set(sitemap_urls + html_urls))
        logger.info(f"Total unique URLs for asset extraction: {len(all_unique_urls)} "
                   f"(sitemap: {sitemap_count}, HTML: {html_count}, combined without duplicates)")
        
        # Initialize asset extraction progress
        progress_tracker.update_asset_progress(0, len(all_unique_urls), {})
        
        page_assets, failed_asset_extractions = await _extract_assets_from_pages_concurrent(
            all_unique_urls, delay, asset_workers, batch_size, progress_tracker, extensions_filter, browser_instance_id
        )
        
        # Step 4: Consolidate and organize assets
        progress_tracker.start_step("consolidating_assets")
        logger.info("Step 4: Consolidating assets")
        consolidated_assets = consolidate_assets(page_assets)
        assets_summary = get_assets_summary_by_extension(consolidated_assets)
        
        # Step 5: Process and organize URL discovery results
        progress_tracker.start_step("finalizing_results")
        logger.info("Step 5: Processing URL discovery results")
        
        # Sort URLs alphabetically
        sorted_sitemap_urls = sorted(sitemap_urls) if sitemap_urls else []
        sorted_html_urls = sorted(html_urls) if html_urls else []
        
        # Find URLs that are in HTML discovery but NOT in sitemap discovery
        sitemap_urls_set = set(sitemap_urls) if sitemap_urls else set()
        html_urls_set = set(html_urls) if html_urls else set()
        html_only_urls = html_urls_set - sitemap_urls_set
        sorted_html_only_urls = sorted(html_only_urls)
        
        logger.info(f"Found {len(sorted_html_only_urls)} additional URLs in HTML discovery not present in sitemaps")
        
        # Calculate audit duration
        audit_end_time = datetime.now()
        audit_duration = (audit_end_time - audit_start_time).total_seconds()
        
        # Combine all failed URLs
        all_failed_urls = {**failed_crawls, **failed_asset_extractions}
        
        # Create comprehensive report
        report = {
            'success': True,
            'audit_info': {
                'base_url': base_url,
                'start_time': audit_start_time.isoformat(),
                'end_time': audit_end_time.isoformat(),
                'duration_seconds': round(audit_duration, 2),
                'parameters': {
                    'max_pages': max_pages,
                    'max_depth': max_depth,
                    'delay_seconds': delay,
                    'html_workers': html_workers,
                    'asset_workers': asset_workers,
                    'batch_size': batch_size
                }
            },
            'sitemap_discovery': {
                'urls_found': sorted_sitemap_urls,
                'total_count': sitemap_count
            },
            'html_discovery': {
                'urls_found': sorted_html_urls,
                'total_count': html_count
            },
            'html_only_discovery': {
                'urls_found': sorted_html_only_urls,
                'total_count': len(sorted_html_only_urls),
                'description': 'URLs found through HTML discovery but not present in sitemaps'
            },
            'failed_crawls': all_failed_urls,
            'crawl_summary': {
                'total_pages_found': len(all_unique_urls),
                'successful_crawls': len(all_unique_urls) - len(failed_asset_extractions),
                'failed_crawls': len(failed_asset_extractions),
                'sitemap_found': sitemap_found  # Added as requested
            },
            'digital_assets': {
                'summary': assets_summary,
                'detailed': consolidated_assets
            }
        }
        
        # Stop periodic saving before final save
        progress_tracker.stop_periodic_saving()
        
        # Finalize report with progress tracking data
        final_report = progress_tracker.finalize_report(report)
        
        # Save final report
        await _save_audit_report(final_report, base_url, is_interim=False)
        
        logger.info(f"Website audit completed successfully for {base_url}")
        logger.info(f"Total pages from sitemaps: {sitemap_count}")
        logger.info(f"Total pages from HTML discovery: {html_count}")
        logger.info(f"Total unique URLs processed for assets: {len(all_unique_urls)}")
        logger.info(f"Additional HTML-only pages: {len(sorted_html_only_urls)}")
        logger.info(f"Failed crawls: {len(failed_crawls)}")
        logger.info(f"Failed asset extractions: {len(failed_asset_extractions)}")
        logger.info(f"Total unique assets found: {assets_summary.get('total', 0)}")
        logger.info(f"Audit duration: {audit_duration:.2f} seconds")
        logger.info(f"Sitemap found: {sitemap_found}")
        
        return final_report
        
    except Exception as e:
        # Stop periodic saving on error
        progress_tracker.stop_periodic_saving()
        
        error_msg = f"Audit failed for {base_url}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        return {
            'success': False,
            'error': error_msg,
            'base_url': base_url,
            'timestamp': datetime.now().isoformat()
        }
    
    finally:
        # Ensure browser resources are cleaned up
        try:
            await cleanup_browser_resources(browser_instance_id)
            logger.info(f"Browser resources cleaned up for instance: {browser_instance_id}")
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")


async def _extract_assets_from_pages_concurrent(urls: List[str], delay: float, 
                                              max_concurrent: int = 20, 
                                              batch_size: int = 100,
                                              progress_tracker: Optional[ProgressTracker] = None,
                                              extensions_filter: Optional[List[str]] = None,
                                              browser_instance_id: Optional[str] = None) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Extract assets from pages using concurrent processing with batching and progress tracking.
    Optimized for large-scale websites with thousands of pages.
    
    Args:
        urls (List[str]): List of page URLs to process
        delay (float): Base delay between requests (will be adjusted for concurrency)
        max_concurrent (int): Maximum concurrent requests
        batch_size (int): Number of URLs to process in each batch
        progress_tracker (Optional[ProgressTracker]): Progress tracker for periodic updates
        extensions_filter (Optional[List[str]]): Filter for specific file extensions
                                               (e.g., ['jpg', 'png', 'pdf', 'mp4'])
                                               Extensions should be lowercase without dots
        browser_instance_id (Optional[str]): Unique browser instance ID for process isolation
        
    Returns:
        Tuple[Dict[str, Dict], Dict[str, str]]: Tuple containing:
            - Dictionary mapping page URLs to their filtered asset information
            - Dictionary of failed page URLs with error messages
    """
    page_assets = {}
    failed_assets = {}
    processed_urls = []  # Track processed URLs for incremental reporting
    total_pages = len(urls)
    processed_count = 0
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Adjust delay for concurrent processing (reduce individual delays)
    concurrent_delay = delay / max_concurrent if delay > 0 else 0
    
    logger.info(f"Processing {total_pages} pages with {max_concurrent} concurrent workers in batches of {batch_size}")
    if extensions_filter:
        # Normalize extensions (remove dots, convert to lowercase)
        normalized_extensions = [ext.lower().lstrip('.') for ext in extensions_filter]
        logger.info(f"Filtering assets to extensions: {normalized_extensions}")
    else:
        normalized_extensions = None
    
    async def process_single_url(url: str, batch_num: int, url_num: int) -> None:
        """Process a single URL with concurrency control."""
        nonlocal processed_count, processed_urls
        
        async with semaphore:
            try:
                # Fetch page content with browser instance isolation
                soup = await fetch_page_content(url, browser_instance_id=browser_instance_id)
                
                if soup is None:
                    failed_assets[url] = "Failed to fetch page content"
                    logger.debug(f"❌ Failed to fetch: {url}")
                    
                    # Update progress counter even for failed fetches
                    processed_count += 1
                    processed_urls.append(url)
                    
                    # Update progress tracker with incremental progress if available
                    if progress_tracker:
                        progress_tracker.update_asset_progress_incremental(processed_count, total_pages, processed_urls.copy(), failed_assets)
                    return
                
                # Extract assets from the page
                assets = extract_assets_from_page(soup, url)
                
                # Apply extension filtering if specified
                if normalized_extensions:
                    filtered_assets = {}
                    for category, asset_list in assets.items():
                        filtered_list = []
                        for asset in asset_list:
                            asset_extension = asset.get('extension', '').lower()
                            if asset_extension in normalized_extensions:
                                filtered_list.append(asset)
                        if filtered_list:  # Only include categories with matching assets
                            filtered_assets[category] = filtered_list
                    page_assets[url] = filtered_assets
                    if not filtered_assets:
                        logger.debug(f"🔍 No matching assets found on {url}")
                else:
                    page_assets[url] = assets
                
                # Update progress
                processed_count += 1
                processed_urls.append(url)
                
                # Update progress tracker with incremental progress if available
                if progress_tracker:
                    progress_tracker.update_asset_progress_incremental(processed_count, total_pages, processed_urls.copy(), failed_assets)
                
                # Log progress every 100 pages
                if processed_count % 100 == 0:
                    logger.info(f"✅ Processed {processed_count}/{total_pages} pages ({processed_count/total_pages*100:.1f}%)")
                
                # Add small delay to be respectful to the server
                if concurrent_delay > 0:
                    await asyncio.sleep(concurrent_delay)
                    
            except Exception as e:
                failed_assets[url] = f"Error processing page: {str(e)}"
                logger.debug(f"❌ Error processing {url}: {str(e)}")
                
                # Update progress counter even for failed URLs
                processed_count += 1
                processed_urls.append(url)
                
                # Update progress tracker with incremental progress if available
                if progress_tracker:
                    progress_tracker.update_asset_progress_incremental(processed_count, total_pages, processed_urls.copy(), failed_assets)
    
    # Process URLs in batches to manage memory and connections
    for batch_start in range(0, total_pages, batch_size):
        batch_end = min(batch_start + batch_size, total_pages)
        batch_urls = urls[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        total_batches = (total_pages + batch_size - 1) // batch_size
        
        logger.info(f"🚀 Processing batch {batch_num}/{total_batches} ({len(batch_urls)} pages)")
        
        # Create tasks for this batch
        tasks = []
        for i, url in enumerate(batch_urls):
            task = asyncio.create_task(process_single_url(url, batch_num, i + 1))
            tasks.append(task)
        
        # Wait for all tasks in this batch to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Add delay between batches to prevent overwhelming the server
        if delay > 0 and batch_num < total_batches:
            await asyncio.sleep(delay)
        
        # Log batch completion
        logger.info(f"✅ Completed batch {batch_num}/{total_batches}")
    
    successful_pages = len(page_assets)
    logger.info(f"Asset extraction completed: {successful_pages}/{total_pages} pages processed successfully")
    logger.info(f"Failed asset extractions: {len(failed_assets)}")
    
    return page_assets, failed_assets


async def _extract_assets_from_pages(urls: List[str], delay: float, browser_instance_id: Optional[str] = None) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Legacy sequential asset extraction function (kept for compatibility).
    For better performance on large websites, use _extract_assets_from_pages_concurrent.
    
    Args:
        urls (List[str]): List of page URLs to process
        delay (float): Delay between requests in seconds
        
    Returns:
        Tuple[Dict[str, Dict], Dict[str, str]]: Tuple containing:
            - Dictionary mapping page URLs to their asset information
            - Dictionary of failed page URLs with error messages
    """
    page_assets = {}
    failed_assets = {}
    total_pages = len(urls)
    
    logger.info(f"Extracting assets from {total_pages} pages")
    
    for i, page_url in enumerate(urls, 1):
        try:
            logger.info(f"Processing page {i}/{total_pages}: {page_url}")
            
            # Fetch page content with browser instance isolation
            soup = await fetch_page_content(page_url, browser_instance_id=browser_instance_id)
            
            if soup is None:
                logger.warning(f"Failed to fetch page content: {page_url}")
                failed_assets[page_url] = "Failed to fetch page content"
                continue
            
            # Extract assets from the page
            assets = extract_assets_from_page(soup, page_url)
            page_assets[page_url] = assets
            
            # Log asset summary for this page
            total_assets = sum(len(asset_list) for asset_list in assets.values())
            logger.debug(f"Found {total_assets} assets on {page_url}")
            
            # Add delay between requests
            if delay > 0 and i < total_pages:
                await asyncio.sleep(delay)
                
        except Exception as e:
            logger.error(f"Error processing page {page_url}: {str(e)}")
            failed_assets[page_url] = f"Error processing page: {str(e)}"
    
    successful_pages = len([assets for assets in page_assets.values() if assets])
    logger.info(f"Asset extraction completed: {successful_pages}/{total_pages} pages processed successfully")
    logger.info(f"Failed asset extractions: {len(failed_assets)}")
    
    return page_assets, failed_assets


async def _save_audit_report(report: Dict, base_url: str, is_interim: bool = False) -> None:
    """
    Save audit report to a JSON file with support for interim and final reports.
    
    Args:
        report (Dict): The audit report to save
        base_url (str): Base URL of the audited website
        is_interim (bool): Whether this is an interim progress report or final report
        
    Returns:
        None
        
    Raises:
        Exception: If file saving fails
    """
    try:
        # Create safe filename from URL
        safe_url = sanitize_url_for_filename(base_url)
        
        # Create output directory structure
        output_dir = f"data/output/{safe_url}"
        
        # Ensure directory exists
        ensure_directory_exists(f"{output_dir}/site_crawl.json")
        
        # Always save as site_crawl.json
        main_file_path = f"{output_dir}/site_crawl.json"
        
        # Save main report to JSON file with atomic write
        temp_file_path = f"{main_file_path}.tmp"
        
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump([report], f, indent=2, ensure_ascii=False)
        
        # Atomic move to final location
        os.rename(temp_file_path, main_file_path)
        
        report_type = "INTERIM" if is_interim else "FINAL"
        logger.info(f"💾 {report_type} audit report saved to: {main_file_path}")
        
        # For interim reports, also save a timestamped copy
        if is_interim:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            interim_filename = f"site_crawl_interim_{timestamp}.json"
            interim_file_path = f"{output_dir}/{interim_filename}"
            
            # Save timestamped interim copy
            interim_temp_file_path = f"{interim_file_path}.tmp"
            
            with open(interim_temp_file_path, 'w', encoding='utf-8') as f:
                json.dump([report], f, indent=2, ensure_ascii=False)
            
            # Atomic move to final location
            os.rename(interim_temp_file_path, interim_file_path)
            
            logger.info(f"💾 Interim backup saved to: {interim_file_path}")
        
    except Exception as e:
        logger.error(f"Failed to save audit report: {str(e)}")
        raise


def conduct_website_audit_sync(
    base_url: str,
    max_pages: Optional[int] = None,
    max_depth: int = 3,
    delay: float = 1.0,
    html_workers: int = 10,
    asset_workers: int = 15,
    batch_size: int = 50,
    extensions_filter: Optional[List[str]] = [
        # Images
        'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico',
        # Documents
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt',
        # Video
        'mp4', 'webm', 'avi', 'mov',
        # Audio
        'mp3', 'wav', 'ogg', 'aac'
    ],
    browser_instance_id: Optional[str] = None
) -> Dict:
    """
    Synchronous wrapper for the async website audit function with extension filtering.

    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl
        max_depth (int): Maximum depth to crawl
        delay (float): Delay between requests in seconds
        html_workers (int): Number of HTML discovery workers
        asset_workers (int): Number of asset extraction workers
        batch_size (int): Batch size for processing
        extensions_filter (Optional[List[str]]): Filter for specific file extensions

    Returns:
        Dict: Comprehensive audit report as a structured dictionary
    """
    try:
        try:
            loop = asyncio.get_running_loop()
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        conduct_website_audit(
                            base_url=base_url,
                            max_pages=max_pages,
                            max_depth=max_depth,
                            delay=delay,
                            html_workers=html_workers,
                            asset_workers=asset_workers,
                            batch_size=batch_size,
                            extensions_filter=extensions_filter,
                            browser_instance_id=browser_instance_id
                        )
                    )
                finally:
                    new_loop.close()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            return asyncio.run(
                conduct_website_audit(
                    base_url=base_url,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    delay=delay,
                    html_workers=html_workers,
                    asset_workers=asset_workers,
                    batch_size=batch_size,
                    extensions_filter=extensions_filter,
                    browser_instance_id=browser_instance_id
                )
            )
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        return {
            'success': False,
            'error': f"Sync wrapper error: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }


def conduct_large_scale_audit(base_url: str, max_pages: Optional[int] = None,
                             html_workers: int = 20, asset_workers: int = 25) -> Dict:
    """
    Optimized audit function for large-scale websites (10,000+ pages).
    Uses aggressive concurrent processing settings with periodic saving.
    
    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl
        html_workers (int): Number of HTML discovery workers
        asset_workers (int): Number of asset extraction workers
        
    Returns:
        Dict: Comprehensive audit report as a structured dictionary
    """
    logger.info(f"🚀 Starting LARGE-SCALE audit for: {base_url}")
    
    # Estimate processing time
    estimated_pages = max_pages or 10000
    estimated_time_minutes = (estimated_pages * 1 / 20) / 60  # 20 concurrent workers, 1s per page
    logger.info(f"📊 Estimated processing time: {estimated_time_minutes:.1f} minutes for {estimated_pages} pages")
    logger.info(f"💾 Progress will be saved every 3 minutes during execution")
    
    return conduct_website_audit_sync(
        base_url=base_url,
        max_pages=max_pages,
        max_depth=20,  # Deep crawling for comprehensive coverage
        delay=0.05,    # Very fast processing (50ms delay)
        html_workers=html_workers,  # Configurable HTML discovery workers
        asset_workers=asset_workers,  # Configurable asset extraction workers
        batch_size=100  # Large batches for efficiency
    )


# Convenience functions for specific extension filtering
def conduct_images_audit(base_url: str, max_pages: Optional[int] = None) -> Dict:
    """
    Extract only image files (jpg, png, gif, webp, svg, etc.).
    
    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl
        
    Returns:
        Dict: Audit report containing only image assets
    """
    logger.info(f"🖼️ Starting IMAGES-ONLY audit for: {base_url}")
    
    return conduct_website_audit_sync(
        base_url=base_url,
        max_pages=max_pages,
        extensions_filter=['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff', 'tif']
    )


def conduct_documents_audit(base_url: str, max_pages: Optional[int] = None) -> Dict:
    """
    Extract only document files (pdf, doc, docx, xls, etc.).
    
    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl
        
    Returns:
        Dict: Audit report containing only document assets
    """
    logger.info(f"📄 Starting DOCUMENTS-ONLY audit for: {base_url}")
    
    return conduct_website_audit_sync(
        base_url=base_url,
        max_pages=max_pages,
        extensions_filter=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'odt', 'ods']
    )


def conduct_media_audit(base_url: str, max_pages: Optional[int] = None) -> Dict:
    """
    Extract only media files (mp4, mp3, avi, mov, etc.).
    
    Args:
        base_url (str): The website URL to audit
        max_pages (Optional[int]): Maximum number of pages to crawl
        
    Returns:
        Dict: Audit report containing only media assets
    """
    logger.info(f"🎬 Starting MEDIA-ONLY audit for: {base_url}")
    
    return conduct_website_audit_sync(
        base_url=base_url,
        max_pages=max_pages,
        extensions_filter=['mp4', 'mp3', 'wav', 'avi', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'mkv', 'm4v', 'aac']
    )


def conduct_custom_extension_audit(base_url: str, extensions: List[str], 
                                 max_pages: Optional[int] = None) -> Dict:
    """
    Extract assets with specific file extensions.
    
    Args:
        base_url (str): The website URL to audit
        extensions (List[str]): List of file extensions to find (e.g., ['pdf', 'docx', 'mp4'])
        max_pages (Optional[int]): Maximum number of pages to crawl
        
    Returns:
        Dict: Audit report containing only specified file extensions
    """
    logger.info(f"🔍 Starting CUSTOM EXTENSION audit for: {base_url}")
    logger.info(f"Target extensions: {extensions}")
    
    return conduct_website_audit_sync(
        base_url=base_url,
        max_pages=max_pages,
        extensions_filter=extensions
    )


if __name__ == "__main__":
    # Example usage
    print("Website Content Audit Crawler v2.1 - Enhanced with Periodic Saving")
    print("=" * 70)
    
    # Configure more detailed logging for demonstration
    logging.getLogger().setLevel(logging.INFO)
    
    # Example audit with user-configurable settings
    test_url = "https://www.gnmotors.co.nz/"
    
    print(f"Starting enhanced audit of: {test_url}")
    print(f"🔄 Progress saved every 3 minutes")
    print(f"📊 Enhanced crawl_summary includes sitemap_found status")
    print()
    
if __name__ == "__main__":
    # Example usage with extension filtering
    print("Website Content Audit Crawler v2.1 - Enhanced with Extension Filtering")
    print("=" * 70)
    
    # Configure more detailed logging for demonstration
    logging.getLogger().setLevel(logging.INFO)
    
    # Example audit with user-configurable settings
    test_url = "https://www.gnmotors.co.nz/"
    
    print(f"Starting extension filtering audit of: {test_url}")
    print(f"🔄 Progress saved every 10 minutes")
    print(f"� Extension filtering examples")
    print()
    
    # Example 1: Extract only JPG and PNG images
    print("🖼️ Example 1: Extracting only JPG and PNG images...")
    images_result = conduct_custom_extension_audit(
        test_url, 
        extensions=['jpg', 'jpeg', 'png'], 
        max_pages=50
    )
    
    if images_result['success']:
        total_images = images_result['digital_assets']['summary']['total']
        print(f"Found {total_images} JPG/PNG images")
    
    print()
    
    # Example 2: Extract only PDF documents
    print("📄 Example 2: Extracting only PDF documents...")
    pdf_result = conduct_custom_extension_audit(
        test_url, 
        extensions=['pdf'], 
        max_pages=50
    )
    
    if pdf_result['success']:
        total_pdfs = pdf_result['digital_assets']['summary']['total']
        print(f"Found {total_pdfs} PDF documents")
    
    print()
    
    # Example 3: Using convenience function for all images
    print("🖼️ Example 3: Extracting all image types using convenience function...")
    all_images_result = conduct_images_audit(test_url, max_pages=50)
    
    if all_images_result['success']:
        total_all_images = all_images_result['digital_assets']['summary']['total']
        print(f"Found {total_all_images} images of all types")
    
    print()
    
    # Example 4: Extract multiple specific types
    print("🔍 Example 4: Extracting PDFs, images, and videos...")
    mixed_result = conduct_custom_extension_audit(
        test_url, 
        extensions=['pdf', 'jpg', 'png', 'mp4', 'mov'], 
        max_pages=50
    )
    
    if mixed_result['success']:
        total_mixed = mixed_result['digital_assets']['summary']['total']
        print(f"Found {total_mixed} assets (PDFs, images, videos)")
    
    print()
    
    # Example 5: Standard full audit (no filtering)
    print("📋 Example 5: Standard audit (all asset types)...")
    full_result = conduct_website_audit_sync(
        base_url=test_url,
        max_pages=50,
        max_depth=3,
        delay=0.5,
        html_workers=5,
        asset_workers=10,
        batch_size=25
    )
    
    if full_result['success']:
        print("✅ Full audit completed successfully!")
        print(f"Sitemap URLs found: {full_result['sitemap_discovery']['total_count']}")
        print(f"HTML pages discovered: {full_result['html_discovery']['total_count']}")
        print(f"Total unique assets: {full_result['digital_assets']['summary']['total']}")
        print(f"Audit duration: {full_result['audit_info']['duration_seconds']} seconds")
        print(f"Sitemap found: {full_result['crawl_summary']['sitemap_found']}")
        
        # Print asset breakdown by category
        assets_by_category = full_result['digital_assets']['summary_by_category']
        print("\nAssets by category:")
        for category, count in assets_by_category.items():
            if count > 0:
                print(f"  {category}: {count}")
        
    else:
        print(f"❌ Audit failed: {full_result['error']}")
    
    print("\n" + "=" * 70)
    print("Extension filtering examples completed!")
    print("Use the convenience functions or specify custom extensions as needed.")