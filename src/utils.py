#!/usr/bin/env python3
"""
Utility functions for the Website Content Audit Crawler.

This module provides helper functions for URL validation, path sanitization,
and other common operations used across the website auditing system.

Author: AI Assistant
Version: 2.0
"""

import re
import os
import logging
from urllib.parse import urlparse
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)


def validate_url(url: str) -> bool:
    """
    Validate URL format and basic accessibility requirements.
    
    Args:
        url (str): The URL to validate
        
    Returns:
        bool: True if URL is valid and properly formatted, False otherwise
        
    Raises:
        None: Catches all exceptions and returns False for invalid URLs
    """
    try:
        parsed = urlparse(url)
        # Check if URL has scheme (http/https) and netloc (domain)
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"Invalid URL format: {url}")
            return False
        
        # Only allow http and https protocols
        if parsed.scheme not in ['http', 'https']:
            logger.warning(f"Unsupported URL scheme: {parsed.scheme}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"URL validation error for {url}: {str(e)}")
        return False


def sanitize_url_for_filename(url: str) -> str:
    """
    Convert a URL to a safe filename by removing invalid characters and common prefixes.
    
    Args:
        url (str): The URL to sanitize
        
    Returns:
        str: Sanitized filename safe for filesystem operations
        
    Example:
        "https://www.example.com/page" -> "example_com_page"
    """
    # Remove protocol and www.
    clean_url = re.sub(r'^(https?://)?(www\.)?', '', url, flags=re.IGNORECASE)
    
    # Replace invalid filename characters with underscores
    safe_filename = re.sub(r'[^\w\-_.]', '_', clean_url)
    
    # Remove multiple consecutive underscores
    safe_filename = re.sub(r'_+', '_', safe_filename)
    
    # Remove leading/trailing underscores
    safe_filename = safe_filename.strip('_')
    
    return safe_filename


def ensure_directory_exists(file_path: str) -> None:
    """
    Create directory structure for a given file path if it doesn't exist.
    
    Args:
        file_path (str): Full path to a file (directory will be created for parent)
        
    Returns:
        None
        
    Raises:
        OSError: If directory cannot be created due to permissions or other issues
    """
    try:
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
    except OSError as e:
        logger.error(f"Failed to create directory for {file_path}: {str(e)}")
        raise


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs belong to the same domain.
    
    Args:
        url1 (str): First URL to compare
        url2 (str): Second URL to compare
        
    Returns:
        bool: True if both URLs are from the same domain, False otherwise
    """
    try:
        domain1 = urlparse(url1).netloc.lower()
        domain2 = urlparse(url2).netloc.lower()
        return domain1 == domain2
    except Exception as e:
        logger.warning(f"Domain comparison error between {url1} and {url2}: {str(e)}")
        return False


def clean_url(url: str) -> str:
    """
    Clean URL by removing fragments and normalizing format.
    
    Args:
        url (str): URL to clean
        
    Returns:
        str: Cleaned URL without fragments and with normalized format
    """
    try:
        parsed = urlparse(url)
        # Remove fragment (everything after #)
        cleaned = parsed._replace(fragment='').geturl()
        return cleaned
    except Exception as e:
        logger.warning(f"URL cleaning error for {url}: {str(e)}")
        return url


def get_file_extension(url: str) -> Optional[str]:
    """
    Extract file extension from URL path, handling special cases like data URLs.
    
    Args:
        url (str): URL to extract extension from
        
    Returns:
        Optional[str]: File extension without the dot, or None if no extension found
        
    Example:
        "https://example.com/image.jpg" -> "jpg"
        "https://example.com/page" -> None
        "data:image/svg+xml,<svg>...</svg>" -> "svg"
    """
    try:
        # Handle data URLs
        if url.startswith('data:'):
            if 'image/svg+xml' in url:
                return 'svg'
            elif 'image/png' in url:
                return 'png'
            elif 'image/jpeg' in url or 'image/jpg' in url:
                return 'jpg'
            elif 'image/gif' in url:
                return 'gif'
            elif 'image/webp' in url:
                return 'webp'
            elif 'image/' in url:
                # Extract image type from data URL
                match = re.search(r'data:image/([^;,]+)', url)
                if match:
                    img_type = match.group(1).lower()
                    # Clean up common variations
                    if img_type == 'jpeg':
                        return 'jpg'
                    return img_type
            elif 'text/css' in url:
                return 'css'
            elif 'application/javascript' in url or 'text/javascript' in url:
                return 'js'
            return None  # Unknown data URL type
        
        # Handle mailto URLs
        if url.startswith('mailto:'):
            return None  # Not a file
        
        # Parse the URL to get the path
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Remove query parameters and fragments for extension detection
        if '?' in path:
            path = path.split('?')[0]
        if '#' in path:
            path = path.split('#')[0]
        
        # Get file extension
        if '.' in path:
            extension = path.split('.')[-1]
            
            # Clean up extension - only keep alphanumeric characters
            extension = re.sub(r'[^a-zA-Z0-9]', '', extension)
            
            # Validate extension length (reasonable file extensions are 1-10 chars)
            if len(extension) > 10 or len(extension) == 0:
                return None
            
            # Handle common variations
            if extension == 'jpeg':
                return 'jpg'
            elif extension == 'htm':
                return 'html'
                
            return extension
        
        return None
        
    except Exception as e:
        logger.warning(f"Extension extraction error for {url}: {str(e)}")
        return None