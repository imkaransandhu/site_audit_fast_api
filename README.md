# Website Content Audit Crawler

A comprehensive Python tool for crawling websites and generating detailed content audit reports. This application provides both a command-line interface and a REST API for conducting thorough website audits.

## Features

- **Sitemap Discovery**: Automatically discovers and parses XML sitemaps
- **HTML Page Discovery**: Follows links to discover all pages on a website
- **Comprehensive Asset Extraction**: Extracts assets from HTML and CSS files
- **Concurrent Processing**: Multi-threaded crawling for improved performance
- **REST API**: FastAPI-based web service for programmatic access
- **Progress Tracking**: Real-time progress monitoring during audits
- **Detailed Logging**: Comprehensive logging with file and console output
- **Export Options**: JSON output with detailed audit results

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd karan_site_audit
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install
```

## Usage

### Command Line Interface

Run a site audit directly from the command line:

```bash
python improved_site_audit.py
```

The script will prompt you for the website URL to audit.

### REST API Server

Start the FastAPI server:

```bash
python api_server.py
```

Or using uvicorn:

```bash
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

#### API Endpoints

- **POST /audit**: Start a new website audit
  ```json
  {
    "url": "https://example.com",
    "max_pages": 100,
    "max_depth": 3
  }
  ```

- **GET /audit/{audit_id}/status**: Check audit progress
- **GET /audit/{audit_id}/result**: Get audit results

## Configuration

### Environment Variables

- `LOG_LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)
- `OUTPUT_DIR`: Directory for output files (default: `data/output/`)

### Customization

The crawler can be customized by modifying the configuration in the main scripts:

- **Max Pages**: Limit the number of pages to crawl
- **Max Depth**: Control how deep the crawler should go
- **Concurrent Workers**: Adjust the number of concurrent threads
- **Timeout Settings**: Modify request timeouts

## Output

The audit generates a comprehensive JSON report including:

- **Site Information**: Basic site metadata
- **Page Discovery**: All discovered pages with metadata
- **Asset Inventory**: Complete list of all assets (images, CSS, JS, etc.)
- **Broken Links**: List of any broken or problematic links
- **Performance Metrics**: Page load times and response codes
- **Summary Statistics**: Overview of findings

### Output Structure

```
data/
├── output/
│   └── [domain]/
│       └── site_crawl.json
└── logs/
    └── website_audit.log
```

## Project Structure

```
├── api_server.py                 # FastAPI REST API server
├── improved_site_audit.py        # Main CLI application
├── requirements.txt              # Python dependencies
├── src/                          # Core modules
│   ├── asset_extractor.py        # Asset extraction logic
│   ├── browser_manager.py        # Browser automation
│   ├── html_discovery.py         # HTML page discovery
│   ├── page_fetcher.py           # Page content fetching
│   ├── sitemap_parser.py         # Sitemap parsing
│   └── utils.py                  # Utility functions
├── prompts/                      # AI prompts (if applicable)
├── data/                         # Output directory
└── logs/                         # Application logs
```

## Dependencies

- **requests**: HTTP library for web requests
- **beautifulsoup4**: HTML/XML parsing
- **playwright**: Browser automation
- **fastapi**: Modern web framework for APIs
- **uvicorn**: ASGI server
- **aiofiles**: Async file operations
- **pydantic**: Data validation

## Logging

The application uses comprehensive logging:

- **Console Output**: Real-time progress and status
- **File Logging**: Detailed logs saved to `logs/website_audit.log`
- **Different Log Levels**: DEBUG, INFO, WARNING, ERROR

## Error Handling

- Graceful handling of network timeouts
- Recovery from temporary connection issues
- Detailed error reporting in logs
- Continuation of audit despite individual page failures

## Performance

- **Concurrent Processing**: Multiple pages processed simultaneously
- **Browser Resource Management**: Efficient browser instance management
- **Memory Optimization**: Cleanup of resources after processing
- **Progress Tracking**: Real-time status updates

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues or questions:

1. Check the logs in `logs/website_audit.log`
2. Review the console output for error messages
3. Open an issue in the repository

## Version History

- **v2.0**: Improved architecture with modular design
- **v3.0**: Added FastAPI REST API interface

---

**Note**: This tool is designed for legitimate website auditing purposes. Please ensure you have permission to crawl the websites you're auditing and respect robots.txt files and rate limiting.