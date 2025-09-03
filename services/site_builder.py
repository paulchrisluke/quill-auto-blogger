"""
Simple site builder service for static HTML files.
Copies existing HTML files to out/site/ directory.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class SiteBuilder:
    """Builds static site files in out/site/ directory."""
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("out/site")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def build(self) -> dict[str, bool]:
        """Build static site files by copying existing HTML files."""
        results = {}
        
        # Copy index.html from root if it exists
        index_source = Path("index.html")
        if index_source.exists():
            try:
                shutil.copy2(index_source, self.output_dir / "index.html")
                logger.info(f"✓ Built index.html")
                results["index.html"] = True
            except Exception as e:
                logger.error(f"✗ Failed to build index.html: {e}")
                results["index.html"] = False
        else:
            logger.warning("index.html not found in root directory")
            results["index.html"] = False
        

        
        return results
    
    def get_built_files(self) -> list[Path]:
        """Get list of built files."""
        if not self.output_dir.exists():
            return []
        
        return [f for f in self.output_dir.iterdir() if f.is_file()]
