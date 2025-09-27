#!/bin/bash
set -e

echo "🚀 Render deployment starting..."

# Install system dependencies first
echo "🔧 Installing system dependencies..."
apt-get update
apt-get install -y \
    libgtk-4-1 \
    libgraphene-1.0-0 \
    libgstgl1.0-0 \
    libgstcodecparsers1.0-0 \
    libenchant-2-2 \
    libsecret-1-0 \
    libmanette-0.2-0 \
    libgles2-mesa \
    libnss3 \
    libxss1 \
    libasound2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright with all dependencies
echo "🌐 Installing Playwright browsers..."
playwright install --with-deps chromium firefox webkit

echo "✅ Render build completed!"