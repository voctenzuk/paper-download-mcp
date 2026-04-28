"""
File management and naming utilities.
"""

import os
import re
from urllib.parse import unquote, urlparse

from ..config.settings import settings
from ..metadata_utils import extract_metadata, generate_filename_from_metadata
from ..utils.logging import get_logger

logger = get_logger(__name__)


class FileManager:
    """Handles file operations and naming."""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or settings.output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_filename(self, doi: str, html_content: str | None = None) -> str:
        """Generate a filename based on DOI and optionally paper metadata."""
        # Default filename based on DOI
        filename = self._clean_filename(doi.replace("/", "_"))

        # If we have HTML, try to extract metadata
        if html_content:
            metadata = extract_metadata(html_content)

            if metadata and "title" in metadata and "year" in metadata:
                return generate_filename_from_metadata(metadata["title"], metadata["year"], doi)
            else:
                # Fallback to simple title extraction
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html_content, "html.parser")

                title_elem = soup.find("title")
                if title_elem and title_elem.text and "sci-hub" not in title_elem.text.lower():
                    title = title_elem.text.strip()
                    filename = self._clean_filename(title[:50])

        return f"{filename}.pdf"

    def generate_filename_from_url(self, url: str) -> str:
        """Generate a reasonable filename from a direct URL."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return self.generate_filename(url, html_content=None)

        # Prefer the last path segment as filename
        basename = os.path.basename((parsed.path or "").rstrip("/"))
        basename = unquote(basename).strip()

        # Avoid meaningless basenames for endpoints like ".../pdf/" or ".../download"
        meaningless = {"", "pdf", "download", "index", "index.php"}
        if basename.lower() in meaningless:
            basename = f"{parsed.netloc}{parsed.path}".replace("/", "_").strip("_")

        safe = self._clean_filename(basename)
        if not safe.lower().endswith(".pdf"):
            safe = f"{safe}.pdf"
        return safe

    def get_output_path(self, filename: str) -> str:
        """Get full output path for a filename."""
        return os.path.join(self.output_dir, filename)

    # Phrases unique to the Sci-Hub manifest/promo PDF that sci.bban.top and
    # similar legacy backends serve when the requested article is not in
    # their cache. We require >=2 token matches to avoid rejecting legitimate
    # articles that happen to mention Sci-Hub in passing.
    _SCIHUB_PLACEHOLDER_TOKENS = (
        "Decentralized Science",
        "Sci-Hub coins",
        "Sci-Net tokenomics",
        "Roadmap towards Open Science",
    )
    # Known placeholder file hashes — fast-path before invoking pypdf.
    # Update when Sci-Hub rotates its manifest PDF.
    _SCIHUB_PLACEHOLDER_MD5S = frozenset({
        "724d6ba324097ba3aa1a7fc52802cd28",  # June 2025 manifest
    })

    def validate_file(self, file_path: str) -> bool:
        """Validate downloaded file."""
        if not os.path.exists(file_path):
            return False

        file_size = os.path.getsize(file_path)
        if file_size < settings.MIN_FILE_SIZE:
            logger.warning(f"Downloaded file is suspiciously small: {file_size} bytes")
            return False

        if self._looks_like_scihub_placeholder(file_path):
            logger.warning(
                f"Downloaded file matches Sci-Hub placeholder PDF (manifest/promo); "
                f"treating {file_path} as failure"
            )
            return False

        return True

    @classmethod
    def _looks_like_scihub_placeholder(cls, file_path: str) -> bool:
        """Detect Sci-Hub manifest/promo PDF served as fallback for missing articles.

        Two checks:
        1. md5 of the file against a known-placeholder blacklist (cheap, exact).
        2. Extracted first-page text against placeholder tokens (robust to
           rotation; requires pypdf at runtime — silently skipped if absent).
        """
        import hashlib
        try:
            with open(file_path, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()
        except OSError:
            return False
        if digest in cls._SCIHUB_PLACEHOLDER_MD5S:
            return True

        try:
            import pypdf  # type: ignore
        except ImportError:
            return False

        try:
            reader = pypdf.PdfReader(file_path)
            if len(reader.pages) == 0:
                return False
            first_page_text = reader.pages[0].extract_text() or ""
        except Exception:
            return False

        hits = sum(1 for tok in cls._SCIHUB_PLACEHOLDER_TOKENS if tok in first_page_text)
        return hits >= 2

    def _clean_filename(self, filename: str) -> str:
        """Create a safe filename from potentially unsafe string."""
        # Replace unsafe characters
        unsafe_chars = r'[<>:"/\\|?*]'
        filename = re.sub(unsafe_chars, "_", filename)

        # Limit length
        if len(filename) > settings.MAX_FILENAME_LENGTH:
            filename = filename[: settings.MAX_FILENAME_LENGTH]

        return filename
