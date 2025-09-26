#!/usr/bin/env python3
"""
Asset extraction module for Website Content Audit Crawler.

This module handles extraction of digital assets from HTML pages and CSS files,
including images, documents, media files, and other downloadable resources.

Author: AI Assistant
Version: 2.0
"""

import re
import requests
import logging
from typing import Dict, List, Set, Optional
from collections import defaultdict
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup

from .utils import get_file_extension, clean_url

# Configure logging
logger = logging.getLogger(__name__)


class AssetExtractor:
    """
    Handles extraction of digital assets from web pages and CSS files.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the asset extractor.
        
        Args:
            timeout (int): HTTP request timeout for fetching external CSS files
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
        })
        
        # Define asset categories and their file extensions
        self.asset_categories = {
            'images': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff', 'tif'],
            'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'odt', 'ods'],
            'media': ['mp4', 'mp3', 'wav', 'avi', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'mkv', 'm4v', 'aac'],
            'archives': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'],
            'fonts': ['woff', 'woff2', 'ttf', 'eot', 'otf'],
            'stylesheets': ['css'],
            'scripts': ['js'],
            'other': []  # Will be populated with unmatched extensions
        }


def extract_assets_from_page(soup: BeautifulSoup, page_url: str, 
                           extensions_filter: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
    """
    Extract all digital assets from a single HTML page with optional extension filtering.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content of the page
        page_url (str): URL of the page being analyzed
        extensions_filter (Optional[List[str]]): Filter for specific file extensions 
                                               (e.g., ['jpg', 'png', 'pdf', 'mp4'])
                                               Extensions should be lowercase without dots.
                                               If None, extracts all asset types
        
    Returns:
        Dict[str, List[Dict]]: Dictionary with asset categories as keys and lists of asset info as values
                              Each asset info dict contains: {'url': str, 'found_on': str, 'element': str}
    """
    logger.debug(f"Extracting assets from page: {page_url}")
    if extensions_filter:
        logger.debug(f"Filtering to extensions: {extensions_filter}")
    
    assets = defaultdict(list)
    
    # Extract assets from HTML elements
    _extract_html_assets(soup, page_url, assets, extensions_filter)
    
    # Extract assets from CSS (inline styles and style tags)
    _extract_css_assets(soup, page_url, assets, extensions_filter)
    
    # Convert defaultdict to regular dict for return
    result = dict(assets)
    
    # Count total assets found
    total_assets = sum(len(asset_list) for asset_list in result.values())
    if extensions_filter:
        logger.debug(f"Found {total_assets} filtered assets on {page_url}")
    else:
        logger.debug(f"Found {total_assets} assets on {page_url}")
    
    return result


def _extract_html_assets(soup: BeautifulSoup, page_url: str, assets: defaultdict, 
                        extensions_filter: Optional[List[str]] = None) -> None:
    """
    Extract assets from HTML elements with optional extension filtering.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        page_url (str): URL of the current page
        assets (defaultdict): Assets dictionary to update
        extensions_filter (Optional[List[str]]): Filter for specific file extensions
        
    Returns:
        None: Updates the assets dictionary in-place
    """
    # Define HTML elements and their asset attributes
    element_selectors = {
        'img': ['src', 'data-src', 'data-original', 'srcset'],
        'a': ['href'],
        'link': ['href'],
        'source': ['src', 'srcset'],
        'video': ['src', 'poster'],
        'audio': ['src'],
        'embed': ['src'],
        'object': ['data'],
        'iframe': ['src'],
        'script': ['src']
    }
    
    for tag_name, attributes in element_selectors.items():
        elements = soup.find_all(tag_name)
        
        for element in elements:
            for attr in attributes:
                attr_value = element.get(attr)
                
                if not attr_value:
                    continue
                
                # Handle srcset attribute (multiple URLs)
                if attr == 'srcset':
                    urls = _parse_srcset(attr_value)
                    for url in urls:
                        _process_single_asset(url, page_url, tag_name, attr, assets, extensions_filter)
                else:
                    _process_single_asset(attr_value, page_url, tag_name, attr, assets, extensions_filter)


def _extract_css_assets(soup: BeautifulSoup, page_url: str, assets: defaultdict,
                       extensions_filter: Optional[List[str]] = None) -> None:
    """
    Extract assets referenced in CSS (inline styles, style tags, and external CSS) with optional extension filtering.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        page_url (str): URL of the current page
        assets (defaultdict): Assets dictionary to update
        extensions_filter (Optional[List[str]]): Filter for specific file extensions
        
    Returns:
        None: Updates the assets dictionary in-place
    """
    # Extract from inline style attributes
    elements_with_style = soup.find_all(attrs={'style': True})
    for element in elements_with_style:
        style_content = element.get('style', '')
        css_urls = _extract_urls_from_css(style_content)
        
        for css_url in css_urls:
            _process_single_asset(css_url, page_url, 'style', 'inline', assets, extensions_filter)
    
    # Extract from <style> tags
    style_tags = soup.find_all('style')
    for style_tag in style_tags:
        style_content = style_tag.get_text()
        css_urls = _extract_urls_from_css(style_content)
        
        for css_url in css_urls:
            _process_single_asset(css_url, page_url, 'style', 'embedded', assets, extensions_filter)
    
    # Extract from external CSS files
    css_links = soup.find_all('link', {'rel': 'stylesheet', 'href': True})
    for css_link in css_links:
        css_url = css_link.get('href')
        if css_url:
            _extract_assets_from_external_css(css_url, page_url, assets, extensions_filter)


def _process_single_asset(asset_url: str, page_url: str, element: str, attribute: str, 
                         assets: defaultdict, extensions_filter: Optional[List[str]] = None) -> None:
    """
    Process a single asset URL and categorize it with optional extension filtering.
    
    Args:
        asset_url (str): The asset URL to process
        page_url (str): The page where the asset was found
        element (str): HTML element that contained the asset
        attribute (str): HTML attribute that contained the asset
        assets (defaultdict): Assets dictionary to update
        extensions_filter (Optional[List[str]]): Filter for specific file extensions
        
    Returns:
        None: Updates the assets dictionary in-place
    """
    if not asset_url or not asset_url.strip():
        return
    
    # Convert relative URLs to absolute
    full_url = urljoin(page_url, asset_url.strip())
    
    # Handle image optimization services (Next.js, Vercel, etc.)
    actual_url = _resolve_optimized_image_url(full_url)
    
    # Get file extension
    extension = get_file_extension(actual_url)
    
    if not extension:
        logger.debug(f"No extension found for URL: {actual_url}")
        return
    
    extension_lower = extension.lower()
    
    # Apply extension filter if specified
    if extensions_filter and extension_lower not in extensions_filter:
        logger.debug(f"Extension '{extension_lower}' filtered out for URL: {actual_url}")
        return
    
    # Categorize the asset
    category = _categorize_asset(extension_lower)
    
    # Create asset info
    asset_info = {
        'url': full_url,
        'actual_url': actual_url if actual_url != full_url else full_url,
        'found_on': page_url,
        'element': element,
        'attribute': attribute,
        'extension': extension_lower
    }
    
    assets[category].append(asset_info)
    logger.debug(f"Added {category} asset ({extension_lower}): {full_url}")


def _resolve_optimized_image_url(url: str) -> str:
    """
    Resolve URLs from image optimization services to get the actual image URL.
    
    Args:
        url (str): URL that might be from an image optimization service
        
    Returns:
        str: Actual image URL or original URL if not an optimization service
    """
    parsed_url = urlparse(url)
    
    # Check for URL parameter (Next.js/Vercel image optimization)
    if parsed_url.query:
        query_params = parse_qs(parsed_url.query)
        if 'url' in query_params:
            # Extract the actual image URL from the 'url' parameter
            actual_url = query_params['url'][0]
            logger.debug(f"Resolved optimized image URL: {url} -> {actual_url}")
            return actual_url
    
    return url


def _parse_srcset(srcset: str) -> List[str]:
    """
    Parse srcset attribute to extract individual URLs.
    
    Args:
        srcset (str): The srcset attribute value
        
    Returns:
        List[str]: List of URLs extracted from srcset
    """
    urls = []
    
    # Split by comma and extract URLs (ignore width/density descriptors)
    entries = srcset.split(',')
    
    for entry in entries:
        entry = entry.strip()
        if entry:
            # Take only the URL part (before any width/density descriptor)
            url = entry.split()[0]
            urls.append(url)
    
    return urls


def _extract_urls_from_css(css_content: str) -> List[str]:
    """
    Extract URLs from CSS content using regex patterns.
    
    Args:
        css_content (str): CSS content as string
        
    Returns:
        List[str]: List of URLs found in the CSS
    """
    urls = []
    
    # Regex patterns to match url() declarations in CSS
    url_patterns = [
        r"url\(['\"]([^'\"]+)['\"]\)",  # url("path") or url('path')
        r"url\(([^)]+)\)"              # url(path) without quotes
    ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, css_content, re.IGNORECASE)
        for match in matches:
            # Clean the URL (remove quotes, spaces)
            clean_match = match.strip().strip('\'"')
            if clean_match:
                urls.append(clean_match)
    
    return urls


def _extract_assets_from_external_css(css_url: str, page_url: str, assets: defaultdict,
                                     extensions_filter: Optional[List[str]] = None) -> None:
    """
    Fetch external CSS file and extract assets from it with optional extension filtering.
    
    Args:
        css_url (str): URL of the CSS file
        page_url (str): URL of the page that references this CSS
        assets (defaultdict): Assets dictionary to update
        extensions_filter (Optional[List[str]]): Filter for specific file extensions
        
    Returns:
        None: Updates the assets dictionary in-place
    """
    try:
        # Convert relative CSS URL to absolute
        full_css_url = urljoin(page_url, css_url)
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
        })
        
        response = session.get(full_css_url, timeout=30)
        response.raise_for_status()
        
        # Extract URLs from CSS content
        css_urls = _extract_urls_from_css(response.text)
        
        for css_asset_url in css_urls:
            # Resolve relative URLs against the CSS file's URL
            absolute_css_asset_url = urljoin(full_css_url, css_asset_url)
            _process_single_asset(absolute_css_asset_url, page_url, 'css', 'external', assets, extensions_filter)
        
        logger.debug(f"Processed external CSS file: {full_css_url} ({len(css_urls)} assets)")
        
    except Exception as e:
        logger.warning(f"Failed to process external CSS {css_url}: {str(e)}")


def _categorize_asset(extension: str) -> str:
    """
    Categorize an asset based on its file extension.
    
    Args:
        extension (str): File extension (without dot)
        
    Returns:
        str: Asset category name
    """
    asset_categories = {
        'images': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff', 'tif'],
        'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'odt', 'ods'],
        'media': ['mp4', 'mp3', 'wav', 'avi', 'mov', 'wmv', 'flv', 'webm', 'ogg', 'mkv', 'm4v', 'aac'],
        'archives': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'],
        'fonts': ['woff', 'woff2', 'ttf', 'eot', 'otf'],
        'stylesheets': ['css'],
        'scripts': ['js']
    }
    
    extension_lower = extension.lower()
    
    for category, extensions in asset_categories.items():
        if extension_lower in extensions:
            return category
    
    return 'other'


def consolidate_assets(page_assets: Dict[str, Dict[str, List[Dict]]]) -> Dict[str, List[Dict]]:
    """
    Consolidate assets from multiple pages, removing duplicates and tracking usage.
    
    Args:
        page_assets (Dict[str, Dict[str, List[Dict]]]): Assets organized by page URL
                    Format: {page_url: {category: [asset_info, ...]}}
        
    Returns:
        Dict[str, List[Dict]]: Consolidated assets by category with usage information
                              Each asset includes 'usage_count' and 'found_on_pages' fields
    """
    logger.info("Consolidating assets from all pages")
    
    consolidated = defaultdict(lambda: defaultdict(lambda: {
        'url': '',
        'actual_url': '',
        'extension': '',
        'usage_count': 0,
        'found_on_pages': set(),
        'elements': set(),
        'attributes': set()
    }))
    
    # Process assets from all pages
    for page_url, page_asset_dict in page_assets.items():
        for category, assets_list in page_asset_dict.items():
            for asset in assets_list:
                asset_url = asset['actual_url']
                
                # Update consolidated asset info
                consolidated_asset = consolidated[category][asset_url]
                consolidated_asset['url'] = asset.get('url', asset_url)
                consolidated_asset['actual_url'] = asset_url
                consolidated_asset['extension'] = asset.get('extension', '')
                consolidated_asset['usage_count'] += 1
                consolidated_asset['found_on_pages'].add(page_url)
                consolidated_asset['elements'].add(asset.get('element', ''))
                consolidated_asset['attributes'].add(asset.get('attribute', ''))
    
    # Convert to final format
    final_result = {}
    
    for category, assets_dict in consolidated.items():
        category_assets = []
        
        for asset_url, asset_info in assets_dict.items():
            # Convert sets to lists for JSON serialization
            final_asset = {
                'url': asset_info['url'],
                'actual_url': asset_info['actual_url'],
                'extension': asset_info['extension'],
                'usage_count': asset_info['usage_count'],
                'found_on_pages': list(asset_info['found_on_pages']),
                'elements': list(asset_info['elements']),
                'attributes': list(asset_info['attributes'])
            }
            category_assets.append(final_asset)
        
        # Sort by usage count (most used first)
        category_assets.sort(key=lambda x: x['usage_count'], reverse=True)
        final_result[category] = category_assets
    
    # Log summary
    total_unique_assets = sum(len(assets) for assets in final_result.values())
    logger.info(f"Asset consolidation completed: {total_unique_assets} unique assets across {len(final_result)} categories")
    
    for category, assets in final_result.items():
        logger.info(f"  - {category}: {len(assets)} unique assets")
    
    return final_result


def get_assets_summary(consolidated_assets: Dict[str, List[Dict]]) -> Dict[str, int]:
    """
    Generate a summary of assets by category.
    
    Args:
        consolidated_assets (Dict[str, List[Dict]]): Consolidated assets by category
        
    Returns:
        Dict[str, int]: Summary with asset counts by category and total
    """
    summary = {}
    total = 0
    
    for category, assets in consolidated_assets.items():
        count = len(assets)
        summary[category] = count
        total += count
    
    summary['total'] = total
    return summary


def get_assets_summary_by_extension(consolidated_assets: Dict[str, List[Dict]]) -> Dict[str, int]:
    """
    Generate a summary of assets grouped by file extension instead of predefined categories.
    
    Args:
        consolidated_assets (Dict[str, List[Dict]]): Consolidated assets by category
        
    Returns:
        Dict[str, int]: Summary with asset counts by extension type and total
                       Example: {'jpg': 15, 'png': 12, 'css': 3, 'js': 8, 'pdf': 2, 'total': 40}
    """
    extension_summary = {}
    total = 0
    
    # Iterate through all categories and assets
    for category, assets in consolidated_assets.items():
        for asset in assets:
            extension = asset.get('extension', 'unknown')
            if extension:
                extension_summary[extension] = extension_summary.get(extension, 0) + 1
                total += 1
    
    # Sort extensions by count (most common first) and then alphabetically
    sorted_extensions = sorted(extension_summary.items(), key=lambda x: (-x[1], x[0]))
    
    # Create final summary dict with sorted extensions
    summary = {}
    for extension, count in sorted_extensions:
        summary[extension] = count
    
    summary['total'] = total
    
    logger.debug(f"Extension summary: {len(summary)-1} unique extensions, {total} total assets")
    return summary