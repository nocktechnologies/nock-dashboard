#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Installing dependencies..."
npm install

echo "Generating icons..."
npm run icons

echo "Building NockCC Desktop for macOS..."
npm run build

echo ""
echo "Done! App is in dist/"
echo "To install: open dist/NockCC-1.0.0.dmg"
