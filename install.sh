#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting installation..."

# Update pip
echo "📦 Updating pip..."
pip install --upgrade pip

# Install Python packages
echo "🐍 Installing Python packages..."
pip install -r requirements.txt

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install

# Verify installation
echo "✅ Verifying installation..."
python -c "import playwright; print('Playwright installed successfully')"
python -c "import fastapi; print('FastAPI installed successfully')"
python -c "import requests; print('Requests installed successfully')"
python -c "import beautifulsoup4; print('BeautifulSoup4 installed successfully')" 2>/dev/null || python -c "import bs4; print('BeautifulSoup4 installed successfully')"

echo "🎉 Installation complete!"
echo "Run 'python improved_site_audit.py' to start the CLI application"
echo "Run 'python api_server.py' to start the API server"