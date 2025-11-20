import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpRequest
from django.shortcuts import render
from django.utils import timezone
from typing import Optional, Tuple  # Import Optional from typing

from .crawler import crawl_and_download  # Import the crawl logic from the crawler.py file
from .models import CrawlRun, DownloadedDocument

logger = logging.getLogger(__name__)

def _build_status(state: str, website: Optional[str] = None, **extra: object) -> dict:
    """Create a normalized status payload for the UI."""
    return {
        "state": state,
        "website": website,
        "pages_crawled": _safe_int(extra.get("pages_crawled")),
        "downloaded": _safe_int(extra.get("downloaded")),
        "message": extra.get("message") or "",
        "last_updated": timezone.now().isoformat(),
    }


def _initial_context() -> dict:
    """Initialize the context for rendering."""
    return {
        "message": None,
        "documents": [],
        "error": None,
        "current_status": _build_status("Idle", message="Waiting to start a crawl."),
    }


def _update_current_status(request: HttpRequest, status: dict) -> dict:
    """Persist only the live crawling status details in the session."""
    request.session["CURRENT_STATUS"] = status
    request.session.modified = True
    return status

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


def _safe_int(value: Optional[object], default: int = 0) -> int:
    """Safely cast a value to an integer."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


from datetime import datetime, timezone
from typing import Optional

from datetime import datetime, timezone as dt_timezone
from django.utils import timezone  # Django's module

def _parse_iso_timestamp(raw_value: Optional[str]) -> Optional[datetime]:
    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)

    return parsed.astimezone(dt_timezone.utc)




def _collect_file_metadata(path: Path) -> Tuple[Optional[int], str]:
    """Return the file size in bytes and SHA-256 hash for the given path."""
    if not path.exists():
        return None, ""

    size = path.stat().st_size
    sha256 = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(8192), b""):
            sha256.update(chunk)

    return size, sha256.hexdigest()

def index(request):
    """Handle the index page request."""
    context = _initial_context()
    context.update(request.session.get("LAST_CONTEXT", {}))
    context["current_status"] = request.session.get(
        "CURRENT_STATUS",
        _build_status("Idle", message="Waiting to start a crawl."),
    )
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
            context = _store_context(
                request,
                {
                    **_initial_context(),
                    "error": str(exc),
                    "current_status": _update_current_status(
                        request,
                        _build_status(
                            "Error", website_url or None, message=str(exc)
                        ),
                    ),
                },
            )
            return render(request, 'index.html', context, status=400)

        # Define download directory and start crawling
        base_download_dir: Path = Path(
            getattr(settings, "PDF_DOWNLOAD_ROOT", settings.BASE_DIR / "downloaded_pdfs")
        )
        download_folder = _derive_download_directory(base_download_dir, start_url)
        download_folder.mkdir(parents=True, exist_ok=True)

        # Flag the crawl as running so the status panel reflects live work
        _update_current_status(
            request,
            _build_status(
                "Running",
                start_url,
                pages_crawled=0,
                downloaded=0,
                message="Crawling in progress…",
            ),
        )

        # Allow only the same host to be crawled
        parsed_start = urlparse(start_url)
        allowed_hosts = {parsed_start.netloc}
        if parsed_start.hostname:
            allowed_hosts.add(parsed_start.hostname)

        # Call the crawl_and_download function
        crawl_started_at = timezone.now()

        downloaded_documents, crawl_metadata = crawl_and_download(
            start_url,
            download_folder,
            allowed_hosts=allowed_hosts,
            max_pages=max_pages,
            max_pdfs=max_pdfs
        )

        crawl_completed_at = timezone.now()

        # Format the documents for rendering
        documents = format_downloaded_documents(downloaded_documents)

        # Create a message with the crawl summary
        pages_crawled = _safe_int(crawl_metadata.get("pages_crawled"), 0)
        current_status = _build_status(
            "Completed",
            start_url,
            pages_crawled=pages_crawled,
            downloaded=len(downloaded_documents),
            message="Crawl finished successfully.",
        )

        # Refresh the live status to match the final state
        _update_current_status(request, current_status)

        message = {
            "website_url": start_url,
            "downloaded": len(downloaded_documents),
            "max_pages": max_pages,
            "max_pdfs": max_pdfs,
            "download_directory": str(download_folder.resolve()),
            "pages_crawled": pages_crawled,
        }

        # Persist crawl summary and document metadata to the database
        started_at = _parse_iso_timestamp(crawl_metadata.get("started_at")) or crawl_started_at
        completed_at = _parse_iso_timestamp(crawl_metadata.get("finished_at")) or crawl_completed_at

        with transaction.atomic():
            crawl_run = CrawlRun.objects.create(
                start_url=start_url,
                download_directory=str(download_folder.resolve()),
                max_pages=max_pages,
                max_pdfs=max_pdfs,
                pages_crawled=pages_crawled,
                pdfs_downloaded=len(downloaded_documents),
                started_at=started_at,
                completed_at=completed_at,
            )

            for document in downloaded_documents:
                raw_path = document.get("path")
                path_value = Path(raw_path) if raw_path else None
                size_bytes, sha256 = _collect_file_metadata(path_value) if path_value else (None, "")

                DownloadedDocument.objects.create(
                    run=crawl_run,
                    pdf_url=document.get("url", ""),
                    source_page=document.get("source_page", ""),
                    filename=document.get("filename") or (path_value.name if path_value else "document.pdf"),
                    stored_path=str(path_value) if path_value else "",
                    file_size_bytes=size_bytes,
                    downloaded_at=_parse_iso_timestamp(document.get("downloaded_at")) or completed_at,
                    download_method=document.get("method", ""),
                    sha256=sha256,
                )

        # Store context for session and render
        context = _store_context(
            request,
            {
                "message": message,
                "documents": documents,
                "error": None,
                "current_status": current_status,
            }
        )

        return render(request, 'index.html', context)

    return HttpResponseBadRequest("Invalid request method.")
