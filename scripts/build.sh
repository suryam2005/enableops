#!/bin/bash
# Build script for Railway deployment
echo "🔧 Starting EnableOps build process..."

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Generate Prisma client
echo "🗄️ Generating Prisma client..."
python -m prisma generate

# Push database schema
echo "📋 Setting up database schema..."
python -m prisma db push --accept-data-loss

echo "✅ Build process completed successfully!"