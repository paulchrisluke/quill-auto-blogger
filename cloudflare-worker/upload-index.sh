#!/bin/bash

# Enable strict mode for fail-fast behavior
set -euo pipefail
IFS=$'\n\t'

# Change to script directory for reliable relative paths
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
BUCKET_KEY="${1:-quill-auto-blogger/index.html}"
SOURCE_FILE="${2:-index.html}"

# Extract bucket and key from first argument
if [[ "$BUCKET_KEY" == *"/"* ]]; then
    BUCKET="${BUCKET_KEY%/*}"
    KEY="${BUCKET_KEY#*/}"
else
    echo "Error: Invalid bucket/key format. Use: bucket/key"
    echo "Example: quill-auto-blogger/index.html"
    exit 1
fi

# Validate prerequisites
echo "Validating prerequisites..."

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "Error: wrangler is not installed or not in PATH"
    echo "Install with: npm install -g wrangler"
    exit 1
fi

# Check if wrangler is authenticated
if ! wrangler whoami &> /dev/null; then
    echo "Error: wrangler is not authenticated"
    echo "Run: wrangler login"
    exit 1
fi

# Check if source file exists
if [[ ! -f "$SOURCE_FILE" ]]; then
    echo "Error: Source file '$SOURCE_FILE' not found"
    echo "Current directory: $(pwd)"
    echo "Available files:"
    ls -la
    exit 1
fi

# Upload index.html to R2 bucket
echo "Uploading $SOURCE_FILE to R2 bucket '$BUCKET' with key '$KEY'..."

# Use wrangler to upload the file with explicit content type
if wrangler r2 object put "$BUCKET/$KEY" --file="$SOURCE_FILE" --content-type="text/html"; then
    echo "Upload complete!"
    echo "Your worker should now serve the $SOURCE_FILE file from the root path (/)"
else
    echo "Error: Upload failed"
    exit 1
fi
