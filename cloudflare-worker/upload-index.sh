#!/bin/bash

# Upload index.html to R2 bucket for the worker to serve
echo "Uploading index.html to R2 bucket..."

# Use wrangler to upload the file
wrangler r2 object put quill-auto-blogger/index.html --file=index.html

echo "Upload complete!"
echo "Your worker should now serve the index.html file from the root path (/)"
