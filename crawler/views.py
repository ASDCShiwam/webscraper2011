import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpRequest
from django.shortcuts import render
from typing import Optional  # Import Optional from typing

from .crawler import crawl_and_download  # Import the crawl logic from the crawler.py file

logger = logging.getLogger(__name__)

def _initial_context() -> dict:
    """Initialize the context for rendering."""
    return {"message": None, "documents": [], "error": None}

def _store_context(request: HttpRequest, context: dict) -> dict:
    """Persist the latest crawl context in the user's session."""
    request.session["LAST_CONTEXT"] = context
    request.session.modified = True
    return context

def _sanitize_path_segment(value: str) -> str:
    """Sanitize URL path segment to be used as a directory name."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    sanitized = sanitized.strip("._-")
    return sanitized or "site"

def _derive_download_directory(base_dir: Path, start_url: str) -> Path:
    """Derive the download directory based on the start URL."""
    parsed = urlparse(start_url)
    host = parsed.hostname or parsed.netloc or start_url
    if host:
        host = host.lower()
    port = parsed.port
    key = f"{host}_{port}" if port else host
    folder_name = _sanitize_path_segment(key)
    return base_dir / folder_name

def normalize_start_url(raw_url: str) -> str:
    """Normalize the start URL to ensure it's fully qualified."""
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        parsed = parsed._replace(scheme="http")
    if not parsed.netloc:
        parsed = urlparse(f"{parsed.scheme}://{parsed.path}")
    if not parsed.netloc:
        raise ValueError("A valid hostname is required to start crawling.")
    return urlunparse(parsed)

def parse_limit(value: str, field_name: str) -> Optional[int]:
    """Convert a form value into an optional positive integer."""
    value = value.strip()
    if not value:
        return None

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc

    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")

    return parsed

def format_downloaded_documents(documents: list) -> list:
    """Format the downloaded documents for rendering."""
    formatted = []
    for doc in documents:
        path = Path(doc["path"])
        size_kb = None
        if path.exists():
            size_kb = round(path.stat().st_size / 1024, 2)

        downloaded_at = doc.get("downloaded_at")
        readable_timestamp = downloaded_at
        if downloaded_at:
            try:
                parsed = datetime.fromisoformat(downloaded_at.replace("Z", "+00:00"))
                readable_timestamp = parsed.strftime("%Y-%m-%d %H:%M:%S %Z") or downloaded_at
            except ValueError:
                readable_timestamp = downloaded_at

        formatted.append(
            {
                **doc,
                "filename": path.name if path.name else doc.get("filename"),
                "size_kb": size_kb,
                "downloaded_display": readable_timestamp,
            }
        )

    return sorted(
        formatted,
        key=lambda item: item.get("downloaded_at") or "",
        reverse=True,
    )

def index(request):
    """Handle the index page request."""
    context = _initial_context()
    context.update(request.session.get("LAST_CONTEXT", {}))
    return render(request, 'index.html', context)

def start_scraping(request):
    """Handle the start scraping request."""
    if request.method == 'POST':
        website_url = request.POST.get('url', '').strip()
        if not website_url:
            context = _store_context(
                request,
                {
                    **_initial_context(),
                    "error": "A website URL is required.",
                }
            )
            return render(request, 'index.html', context, status=400)

        # Normalize URL and set limits
        try:
            start_url = normalize_start_url(website_url)
            max_pages = parse_limit(request.POST.get('max_pages', ''), "Maximum pages")
            max_pdfs = parse_limit(request.POST.get('max_pdfs', ''), "Maximum PDFs")
        except ValueError as exc:
            context = _store_context(request, {**_initial_context(), "error": str(exc)})
            return render(request, 'index.html', context, status=400)

        # Define download directory and start crawling
        base_download_dir: Path = Path(
            getattr(settings, "PDF_DOWNLOAD_ROOT", settings.BASE_DIR / "downloaded_pdfs")
        )
        download_folder = _derive_download_directory(base_download_dir, start_url)
        download_folder.mkdir(parents=True, exist_ok=True)

        # Allow only the same host to be crawled
        parsed_start = urlparse(start_url)
        allowed_hosts = {parsed_start.netloc}
        if parsed_start.hostname:
            allowed_hosts.add(parsed_start.hostname)

        # Call the crawl_and_download function
        downloaded_documents = crawl_and_download(
            start_url,
            download_folder,
            allowed_hosts=allowed_hosts,
            max_pages=max_pages,
            max_pdfs=max_pdfs
        )

        # Format the documents for rendering
        documents = format_downloaded_documents(downloaded_documents)

        # Create a message with the crawl summary
        message = {
            "website_url": start_url,
            "downloaded": len(downloaded_documents),
            "max_pages": max_pages,
            "max_pdfs": max_pdfs,
            "download_directory": str(download_folder.resolve()),
        }

        # Store context for session and render
        context = _store_context(
            request,
            {
                "message": message,
                "documents": documents,
                "error": None,
            }
        )

        return render(request, 'index.html', context)

    return HttpResponseBadRequest("Invalid request method.")
