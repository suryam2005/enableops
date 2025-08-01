#!/bin/bash
# Build script for Railway deployment
echo "🔧 Starting EnableOps build process..."

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Generate Prisma client
echo "🗄️ Generating Prisma client..."
python -m prisma generate

# Run database migration
echo "🔧 Running database migration..."
python scripts/migrate_database.py

echo "✅ Build process completed successfully!"