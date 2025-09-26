#!/usr/bin/env python3
"""
Sitemap discovery and parsing module for Website Content Audit Crawler.

This module handles finding XML sitemaps from various sources (robots.txt, common locations)
and parsing them to extract all URLs. Supports both regular sitemaps and sitemap index files.

Author: AI Assistant
Version: 2.0
"""

import requests
import logging
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from .utils import validate_url, is_same_domain

# Configure logging
logger = logging.getLogger(__name__)


class SitemapParser:
    """
    Handles sitemap discovery and parsing operations.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the sitemap parser.
        
        Args:
            timeout (int): HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
        })


def get_robots_txt(base_url: str, timeout: int = 30) -> Optional[str]:
    """
    Retrieve robots.txt content from the website.
    
    Args:
        base_url (str): Base URL of the website
        timeout (int): Request timeout in seconds
        
    Returns:
        Optional[str]: Content of robots.txt file, or None if not found/accessible
    """
    try:
        robots_url = urljoin(base_url, '/robots.txt')
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
        })
        
        response = session.get(robots_url, timeout=timeout)
        
        if response.status_code == 200:
            logger.info(f"Successfully retrieved robots.txt from {robots_url}")
            return response.text
        else:
            logger.debug(f"robots.txt not found at {robots_url} (status: {response.status_code})")
            
    except Exception as e:
        logger.debug(f"Failed to retrieve robots.txt from {base_url}: {str(e)}")
    
    return None


def find_sitemap_urls(base_url: str) -> List[str]:
    """
    Find all sitemap URLs by checking robots.txt and common locations.
    
    Args:
        base_url (str): Base URL of the website to search
        
    Returns:
        List[str]: List of sitemap URLs found (may be empty if none found)
    """
    sitemap_urls = []
    
    # Check robots.txt first
    robots_txt = get_robots_txt(base_url)
    if robots_txt:
        sitemap_urls.extend(_extract_sitemaps_from_robots(robots_txt, base_url))
    
    # Check common sitemap locations
    common_locations = [
        '/sitemap.xml',
        '/sitemap_index.xml', 
        '/sitemaps.xml',
        '/sitemap1.xml',
        '/sitemap-index.xml'
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
    })
    
    for location in common_locations:
        try:
            sitemap_url = urljoin(base_url, location)
            response = session.head(sitemap_url, timeout=30)
            
            if response.status_code == 200:
                if sitemap_url not in sitemap_urls:
                    sitemap_urls.append(sitemap_url)
                    logger.info(f"Found sitemap at: {sitemap_url}")
                    
        except Exception as e:
            logger.debug(f"Failed to check sitemap location {location}: {str(e)}")
    
    return sitemap_urls


def _extract_sitemaps_from_robots(robots_txt: str, base_url: str) -> List[str]:
    """
    Extract sitemap URLs from robots.txt content.
    
    Args:
        robots_txt (str): Content of robots.txt file
        base_url (str): Base URL for resolving relative sitemap URLs
        
    Returns:
        List[str]: List of sitemap URLs found in robots.txt
    """
    sitemap_urls = []
    
    for line in robots_txt.split('\n'):
        line = line.strip()
        if line.lower().startswith('sitemap:'):
            sitemap_url = line[8:].strip()  # Remove 'sitemap:' prefix
            
            # Convert relative URLs to absolute
            full_url = urljoin(base_url, sitemap_url)
            
            if validate_url(full_url):
                sitemap_urls.append(full_url)
                logger.info(f"Found sitemap in robots.txt: {full_url}")
    
    return sitemap_urls


def parse_sitemap(sitemap_url: str) -> List[str]:
    """
    Parse a single sitemap XML file and extract all URLs.
    Handles both regular sitemaps and sitemap index files recursively.
    
    Args:
        sitemap_url (str): URL of the sitemap to parse
        
    Returns:
        List[str]: List of URLs extracted from the sitemap
    """
    urls = []
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Website Content Auditor) AppleWebKit/537.36'
        })
        
        response = session.get(sitemap_url, timeout=30)
        response.raise_for_status()
        
        # Parse XML content
        root = ET.fromstring(response.content)
        
        # Handle sitemap index (contains references to other sitemaps)
        if _is_sitemap_index(root):
            logger.info(f"Processing sitemap index: {sitemap_url}")
            child_sitemaps = _extract_child_sitemaps(root)
            
            # Recursively parse each child sitemap
            for child_sitemap in child_sitemaps:
                try:
                    child_urls = parse_sitemap(child_sitemap)
                    urls.extend(child_urls)
                    logger.debug(f"Extracted {len(child_urls)} URLs from child sitemap: {child_sitemap}")
                except Exception as e:
                    logger.warning(f"Failed to parse child sitemap {child_sitemap}: {str(e)}")
        
        else:
            # Regular sitemap - extract URLs directly
            logger.info(f"Processing regular sitemap: {sitemap_url}")
            urls = _extract_urls_from_sitemap(root)
            
        logger.info(f"Successfully parsed sitemap {sitemap_url}: found {len(urls)} URLs")
        
    except Exception as e:
        logger.error(f"Failed to parse sitemap {sitemap_url}: {str(e)}")
    
    return urls


def _is_sitemap_index(root: ET.Element) -> bool:
    """
    Check if the XML root element represents a sitemap index.
    
    Args:
        root (ET.Element): Root element of parsed XML
        
    Returns:
        bool: True if this is a sitemap index, False if regular sitemap
    """
    # Check for sitemap index indicators
    tag_name = root.tag.lower()
    return 'sitemapindex' in tag_name or root.find('.//{*}sitemap') is not None


def _extract_child_sitemaps(root: ET.Element) -> List[str]:
    """
    Extract child sitemap URLs from a sitemap index.
    
    Args:
        root (ET.Element): Root element of sitemap index XML
        
    Returns:
        List[str]: List of child sitemap URLs
    """
    child_sitemaps = []
    
    # Look for sitemap elements in the index
    for sitemap_elem in root.findall('.//{*}sitemap'):
        loc_elem = sitemap_elem.find('.//{*}loc')
        if loc_elem is not None and loc_elem.text:
            sitemap_url = loc_elem.text.strip()
            if validate_url(sitemap_url):
                child_sitemaps.append(sitemap_url)
    
    return child_sitemaps


def _extract_urls_from_sitemap(root: ET.Element) -> List[str]:
    """
    Extract all URLs from a regular sitemap XML.
    
    Args:
        root (ET.Element): Root element of sitemap XML
        
    Returns:
        List[str]: List of URLs found in the sitemap
    """
    urls = []
    
    # Look for URL elements
    for url_elem in root.findall('.//{*}url'):
        loc_elem = url_elem.find('.//{*}loc')
        if loc_elem is not None and loc_elem.text:
            url = loc_elem.text.strip()
            if validate_url(url):
                urls.append(url)
    
    return urls


def get_all_sitemap_urls(base_url: str) -> Tuple[List[str], int]:
    """
    Discover and parse all sitemaps for a website, returning all URLs found.
    
    Args:
        base_url (str): Base URL of the website
        
    Returns:
        Tuple[List[str], int]: Tuple containing (list of all URLs from sitemaps, total count)
    """
    logger.info(f"Starting sitemap discovery for {base_url}")
    
    # Find all sitemap URLs
    sitemap_urls = find_sitemap_urls(base_url)
    
    if not sitemap_urls:
        logger.info(f"No sitemaps found for {base_url}")
        return [], 0
    
    logger.info(f"Found {len(sitemap_urls)} sitemap(s) for {base_url}")
    
    # Parse all sitemaps and collect URLs
    all_urls = []
    parsed_domain = urlparse(base_url).netloc
    
    for sitemap_url in sitemap_urls:
        try:
            sitemap_urls_list = parse_sitemap(sitemap_url)
            
            # Filter URLs to same domain only
            same_domain_urls = [
                url for url in sitemap_urls_list 
                if is_same_domain(url, base_url)
            ]
            
            all_urls.extend(same_domain_urls)
            logger.info(f"Added {len(same_domain_urls)} URLs from {sitemap_url}")
            
        except Exception as e:
            logger.error(f"Failed to process sitemap {sitemap_url}: {str(e)}")
    
    # Remove duplicates while preserving order
    unique_urls = list(dict.fromkeys(all_urls))
    
    logger.info(f"Sitemap discovery completed: {len(unique_urls)} unique URLs found")
    return unique_urls, len(unique_urls)