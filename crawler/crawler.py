import hashlib
import logging
import os
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from urllib.parse import ParseResult, urljoin, urldefrag, urlparse, quote, unquote, parse_qs

import bs4
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

VERIFY_SSL = os.getenv("CRAWLER_VERIFY_SSL", "true").lower() not in {"0", "false", "no"}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)
_SESSION.verify = VERIFY_SSL

PDF_PATTERN = re.compile(r"[^'\"()<>\\\s]+\.pdf(?:[?#][^'\"()<>\\\s]*)?", re.IGNORECASE)

# Pattern to extract PDF paths from JavaScript onclick handlers
ONCLICK_PDF_PATTERN = re.compile(
    r"(?:downloadWithWatermark|download|openPDF|viewPDF|getPDF)\s*\(\s*['\"]([^'\"]+\.pdf[^'\"]*)['\"]",
    re.IGNORECASE
)

logger = logging.getLogger(__name__)


def crawl_and_download(
    start_url: str,
    download_folder: Path,
    retries: int = 3,
    delay: int = 5,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    max_pages: Optional[int] = None,
    max_pdfs: Optional[int] = None,
    status_callback: Optional[Callable[[Dict[str, object]], None]] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """
    Crawl website and download PDFs.
    
    Supports TWO watermark methods:
    1. JavaScript onclick: onclick="downloadWithWatermark('pdf/file.pdf')"
    2. Direct href: href="watermark11/download.php?show=Document Name"
    """

    download_folder = Path(download_folder)
    download_folder.mkdir(parents=True, exist_ok=True)

    visited: Set[str] = set()
    queue: deque[str] = deque([start_url])
    downloaded: List[Dict[str, str]] = []
    downloaded_urls: Set[str] = set()
    allowed: Optional[Set[str]] = None
    started_at = datetime.utcnow()
    
    if allowed_hosts:
        allowed = set()
        for host in allowed_hosts:
            lowered = host.lower()
            allowed.add(lowered)
            if ":" in lowered:
                allowed.add(lowered.split(":", 1)[0])

    pages_crawled = 0
    
    print(f"\n{'='*80}")
    print(f"🚀 PDF Crawler Started")
    print(f"   Target: {start_url}")
    print(f"   Output: {download_folder}")
    print(f"{'='*80}\n")

    def emit_status(
        state: str,
        message: str,
        *,
        pages: Optional[int] = None,
        downloaded_count: Optional[int] = None,
        current_url: Optional[str] = None,
    ) -> None:
        if not status_callback:
            return

        payload = {
            "state": state,
            "website": start_url,
            "pages_crawled": pages if pages is not None else pages_crawled,
            "downloaded": downloaded_count if downloaded_count is not None else len(downloaded),
            "message": message,
        }

        if current_url:
            payload["current_url"] = current_url

        try:
            status_callback(payload)
        except Exception:
            logger.exception("Status callback failed")

    emit_status("Running", "Crawling started", pages=0, downloaded_count=0)
    
    max_pdf_limit_hit = False

    while queue and not max_pdf_limit_hit:
        if max_pages is not None and pages_crawled >= max_pages:
            logger.info("Reached maximum page limit of %s", max_pages)
            break

        current_url = queue.popleft()
        if current_url in visited:
            continue
        
        visited.add(current_url)
        pages_crawled += 1

        print(f"\n[Page {pages_crawled}] 🔍 Crawling: {current_url}")
        emit_status(
            "Running",
            f"Crawling page {pages_crawled}: {current_url}",
            current_url=current_url,
        )

        response = _request_with_retries(current_url, retries=retries, delay=delay)
        if response is None:
            continue

        if not _is_html_response(response):
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            logger.warning("Skipping %s: unable to parse HTML (%s)", current_url, exc)
            continue

        # METHOD 1: JavaScript onclick with PDF path (dgis.army.mil)
        onclick_pdfs = _extract_onclick_pdfs(soup, current_url)
        
        # METHOD 2: Direct watermark href (sigweb.army.mil)
        watermark_hrefs = _extract_watermark_hrefs(soup, current_url)
        
        # METHOD 3: Regular PDF links
        regular_pdfs = _extract_regular_pdf_links(soup, current_url)
        
        total_found = len(onclick_pdfs) + len(watermark_hrefs) + len(regular_pdfs)
        print(f"   📄 Found {total_found} PDFs ({len(onclick_pdfs)} onclick, {len(watermark_hrefs)} watermark, {len(regular_pdfs)} direct)")
        emit_status(
            "Running",
            f"Found {total_found} PDFs on page {pages_crawled}",
            current_url=current_url,
        )
        
        # Download onclick PDFs (Method 1)
        for pdf_path in onclick_pdfs:
            if pdf_path in downloaded_urls:
                continue

            pdf_info = download_onclick_watermark(pdf_path, download_folder, current_url)

            if pdf_info:
                pdf_info["source_page"] = current_url
                pdf_info["method"] = "onclick"
                downloaded.append(pdf_info)
                downloaded_urls.add(pdf_path)

                emit_status(
                    "Running",
                    f"Downloaded onclick PDF: {pdf_info.get('filename', pdf_path)}",
                )

                if max_pdfs is not None and len(downloaded) >= max_pdfs:
                    logger.info("Reached maximum PDF limit of %s", max_pdfs)
                    max_pdf_limit_hit = True
                    break

        if max_pdf_limit_hit:
            break

        # Download watermark hrefs (Method 2)
        for watermark_url in watermark_hrefs:
            if watermark_url in downloaded_urls:
                continue
            
            pdf_info = download_watermark_href(watermark_url, download_folder, current_url)

            if pdf_info:
                pdf_info["source_page"] = current_url
                pdf_info["method"] = "watermark_href"
                downloaded.append(pdf_info)
                downloaded_urls.add(watermark_url)

                emit_status(
                    "Running",
                    f"Downloaded watermark PDF: {pdf_info.get('filename', watermark_url)}",
                )

                if max_pdfs is not None and len(downloaded) >= max_pdfs:
                    logger.info("Reached maximum PDF limit of %s", max_pdfs)
                    max_pdf_limit_hit = True
                    break

        if max_pdf_limit_hit:
            break

        # Download regular PDFs (Method 3)
        for pdf_url in regular_pdfs:
            parsed_pdf = urlparse(pdf_url)
            if allowed and not _is_allowed_host(parsed_pdf, allowed):
                continue

            if pdf_url in downloaded_urls:
                continue

            pdf_info = download_direct_pdf(pdf_url, download_folder, current_url)
            if pdf_info:
                pdf_info["source_page"] = current_url
                pdf_info["method"] = "direct"
                downloaded.append(pdf_info)
                downloaded_urls.add(pdf_url)

                emit_status(
                    "Running",
                    f"Downloaded direct PDF: {pdf_info.get('filename', pdf_url)}",
                )

                if max_pdfs is not None and len(downloaded) >= max_pdfs:
                    logger.info("Reached maximum PDF limit of %s", max_pdfs)
                    max_pdf_limit_hit = True
                    break

        if max_pdf_limit_hit:
            break

        # Queue new links for crawling
        if not max_pdf_limit_hit:
            links_found = 0
            for link in soup.select("a[href]"):
                href = link.get("href")
                if not href:
                    continue

                href, _ = urldefrag(href)
                if not href or href == "#":
                    continue

                full_url = urljoin(current_url, href)
                parsed = urlparse(full_url)

                if parsed.scheme not in {"http", "https"}:
                    continue

                if allowed and not _is_allowed_host(parsed, allowed):
                    continue

                # Skip direct PDF links (handled separately)
                if parsed.path.lower().endswith(".pdf"):
                    continue

                # Skip watermark download URLs (handled separately)
                if 'watermark' in parsed.path.lower() and 'download.php' in parsed.path.lower():
                    continue

                # Skip non-content files
                skip_ext = {'.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.ico', '.svg', '.woff', '.ttf', '.mp4', '.mp3'}
                if any(parsed.path.lower().endswith(ext) for ext in skip_ext):
                    continue

                if full_url not in visited and full_url not in queue:
                    queue.append(full_url)
                    links_found += 1

            if links_found > 0:
                print(f"   🔗 Queued {links_found} new links (Total in queue: {len(queue)})")
                emit_status(
                    "Running",
                    f"Queued {links_found} new links",
                    current_url=current_url,
                )

    print(f"\n{'='*80}")
    print(f"✅ Crawling Complete!")
    print(f"   Pages crawled: {pages_crawled}")
    print(f"   PDFs downloaded: {len(downloaded)}")
    print(f"   Saved to: {download_folder}")
    print(f"{'='*80}\n")

    emit_status(
        "Completed",
        "Crawl finished successfully.",
        pages=pages_crawled,
        downloaded_count=len(downloaded),
    )

    finished_at = datetime.utcnow()

    metadata: Dict[str, str] = {
        "pages_crawled": str(pages_crawled),
        "started_at": started_at.isoformat() + "Z",
        "finished_at": finished_at.isoformat() + "Z",
    }

    return downloaded, metadata


def _extract_onclick_pdfs(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract PDF paths from JavaScript onclick handlers.
    Example: onclick="downloadWithWatermark('pdf/Laptop_Policy.pdf')"
    """
    discovered: List[str] = []
    seen = set()
    
    for element in soup.find_all(attrs={"onclick": True}):
        onclick = element.get("onclick", "")
        if not onclick:
            continue
            
        for match in ONCLICK_PDF_PATTERN.finditer(onclick):
            pdf_path = match.group(1)
            if pdf_path not in seen:
                discovered.append(pdf_path)
                seen.add(pdf_path)
                logger.info("Found onclick PDF: %s", pdf_path)
    
    return discovered


def _extract_watermark_hrefs(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract watermark download URLs from href attributes.
    
    Examples:
    - href="watermark11/download.php?show=Document Name"
    - href="watermark/download.php?show=Policy"
    """
    discovered: List[str] = []
    seen = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').strip()
        if not href:
            continue
        
        # Check if this is a watermark download link
        href_lower = href.lower()
        
        # Pattern 1: watermark*/download.php
        if 'watermark' in href_lower and 'download.php' in href_lower:
            full_url = urljoin(base_url, href)
            if full_url not in seen:
                discovered.append(full_url)
                seen.add(full_url)
                logger.info("Found watermark href: %s", full_url)
        
        # Pattern 2: other watermark patterns
        elif any(pattern in href_lower for pattern in ['getpdf', 'showpdf', 'viewpdf', 'downloadpdf']):
            full_url = urljoin(base_url, href)
            if full_url not in seen:
                discovered.append(full_url)
                seen.add(full_url)
                logger.info("Found watermark href: %s", full_url)
    
    return discovered


def _extract_regular_pdf_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Extract direct PDF links from href attributes."""
    discovered: List[str] = []
    seen = set()
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').strip()
        if href.lower().endswith('.pdf'):
            full_url = urljoin(base_url, href)
            if full_url not in seen:
                discovered.append(full_url)
                seen.add(full_url)
    
    return discovered


def download_onclick_watermark(pdf_path: str, folder: Path, base_url: str) -> Optional[Dict[str, str]]:
    """
    Download PDF using JavaScript onclick method (dgis.army.mil style).
    
    Transforms: pdf/DDGIT Policies/Laptop_Policy.pdf
    To: https://dgis.army.mil/watermark/download.php?show=DDGIT%20Policies%2FLaptop_Policy
    """
    
    folder.mkdir(parents=True, exist_ok=True)
    
    pdf_name = os.path.basename(pdf_path) or "downloaded.pdf"
    target_path = _unique_target_path(folder, pdf_name, pdf_path)
    
    if target_path.exists():
        return {
            "url": pdf_path,
            "path": str(target_path),
            "filename": target_path.name,
            "downloaded_at": datetime.utcfromtimestamp(target_path.stat().st_mtime).isoformat() + "Z",
        }
    
    # Transform path like JavaScript does
    file_name = pdf_path
    if file_name.startswith("pdf/"):
        file_name = file_name[4:]
    if file_name.endswith(".pdf"):
        file_name = file_name[:-4]
    
    encoded_name = quote(file_name, safe='')
    
    parsed_base = urlparse(base_url)
    watermark_url = f"{parsed_base.scheme}://{parsed_base.netloc}/watermark/download.php?show={encoded_name}"
    
    print(f"   💧 Onclick: {pdf_name}")
    print(f"      URL: {watermark_url}")
    
    response = _get_with_ssl_fallback(watermark_url, timeout=60, stream=False, referer=base_url)
    if not response or response.status_code != 200:
        print(f"      ✗ Failed (Status: {response.status_code if response else 'No response'})")
        return None
    
    pdf_content = _extract_pdf_from_response(response.content)
    if not pdf_content or not _is_valid_pdf(pdf_content):
        print(f"      ✗ Invalid PDF")
        return None
    
    with open(target_path, "wb") as f:
        f.write(pdf_content)
    
    print(f"      ✅ Downloaded ({len(pdf_content)/1024:.1f} KB)")
    
    return {
        "url": pdf_path,
        "path": str(target_path),
        "filename": target_path.name,
        "downloaded_at": datetime.utcnow().isoformat() + "Z",
    }


def download_watermark_href(watermark_url: str, folder: Path, referer: str) -> Optional[Dict[str, str]]:
    """
    Download PDF from direct watermark URL (sigweb.army.mil style).
    
    Example URL: https://sigweb.army.mil/watermark11/download.php?show=Nomination%20of%20Offrs%20on%20SODE-115%20course
    """
    
    folder.mkdir(parents=True, exist_ok=True)
    
    # Extract PDF name from URL
    pdf_name = _extract_pdf_name_from_url(watermark_url)
    target_path = _unique_target_path(folder, pdf_name, watermark_url)
    
    if target_path.exists():
        return {
            "url": watermark_url,
            "path": str(target_path),
            "filename": target_path.name,
            "downloaded_at": datetime.utcfromtimestamp(target_path.stat().st_mtime).isoformat() + "Z",
        }
    
    print(f"   💧 Watermark: {pdf_name}")
    print(f"      URL: {watermark_url}")
    
    # Make request
    response = _get_with_ssl_fallback(watermark_url, timeout=60, stream=False, referer=referer)
    
    if not response:
        print(f"      ✗ No response")
        return None
    
    if response.status_code != 200:
        print(f"      ✗ Status {response.status_code}")
        return None
    
    # Check if we got HTML error instead of PDF
    content_type = response.headers.get('Content-Type', '').lower()
    if 'text/html' in content_type and 'application/pdf' not in content_type:
        print(f"      ⚠️  Got HTML instead of PDF")
        # Try to see if it's a redirect or error page
        if b'<html' in response.content[:200].lower():
            print(f"      Response starts with: {response.content[:100]}")
            return None
    
    # Extract PDF content
    pdf_content = _extract_pdf_from_response(response.content)
    
    if not pdf_content:
        print(f"      ✗ No PDF found in response ({len(response.content)} bytes)")
        print(f"      First 200 bytes: {response.content[:200]}")
        return None
    
    if not _is_valid_pdf(pdf_content):
        print(f"      ✗ Invalid PDF")
        return None
    
    # Check for better filename in Content-Disposition header
    content_disp = response.headers.get('Content-Disposition', '')
    if 'filename=' in content_disp:
        match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disp)
        if match:
            better_name = match.group(1).strip('\'"')
            if better_name and better_name.endswith('.pdf'):
                pdf_name = _sanitize_filename(better_name)
                target_path = _unique_target_path(folder, pdf_name, watermark_url)
    
    # Save PDF
    with open(target_path, "wb") as f:
        f.write(pdf_content)
    
    print(f"      ✅ Downloaded ({len(pdf_content)/1024:.1f} KB)")
    
    return {
        "url": watermark_url,
        "path": str(target_path),
        "filename": target_path.name,
        "downloaded_at": datetime.utcnow().isoformat() + "Z",
    }


def download_direct_pdf(pdf_url: str, folder: Path, referer: str) -> Optional[Dict[str, str]]:
    """Download direct PDF link."""
    
    folder.mkdir(parents=True, exist_ok=True)
    
    parsed = urlparse(pdf_url)
    pdf_name = os.path.basename(parsed.path) or "downloaded.pdf"
    target_path = _unique_target_path(folder, pdf_name, pdf_url)
    
    if target_path.exists():
        return {
            "url": pdf_url,
            "path": str(target_path),
            "filename": target_path.name,
            "downloaded_at": datetime.utcfromtimestamp(target_path.stat().st_mtime).isoformat() + "Z",
        }
    
    print(f"   📄 Direct: {pdf_name}")
    
    response = _get_with_ssl_fallback(pdf_url, timeout=30, stream=False, referer=referer)
    if not response or response.status_code != 200:
        print(f"      ✗ Failed")
        return None
    
    pdf_content = _extract_pdf_from_response(response.content)
    if not pdf_content or not _is_valid_pdf(pdf_content):
        print(f"      ✗ Invalid")
        return None
    
    with open(target_path, "wb") as f:
        f.write(pdf_content)
    
    print(f"      ✅ Downloaded ({len(pdf_content)/1024:.1f} KB)")
    
    return {
        "url": pdf_url,
        "path": str(target_path),
        "filename": target_path.name,
        "downloaded_at": datetime.utcnow().isoformat() + "Z",
    }


def _extract_pdf_name_from_url(url: str) -> str:
    """
    Extract PDF name from watermark URL.
    
    Examples:
    - watermark11/download.php?show=Nomination of Offrs on SODE-115 course
      → Nomination_of_Offrs_on_SODE-115_course.pdf
    
    - watermark/download.php?show=Policy Document
      → Policy_Document.pdf
    """
    parsed = urlparse(url)
    
    # Try to parse query parameters
    try:
        params = parse_qs(parsed.query)
        
        # Check for 'show' parameter (most common)
        if 'show' in params and params['show']:
            name = params['show'][0]
            if name:
                sanitized = _sanitize_filename(unquote(name))
                # Ensure .pdf extension
                if not sanitized.lower().endswith('.pdf'):
                    sanitized = sanitized + '.pdf'
                return sanitized
        
        # Check for other common parameters
        for key in ['file', 'document', 'pdf', 'name', 'title']:
            if key in params and params[key]:
                name = params[key][0]
                if name:
                    sanitized = _sanitize_filename(unquote(name))
                    # Ensure .pdf extension
                    if not sanitized.lower().endswith('.pdf'):
                        sanitized = sanitized + '.pdf'
                    return sanitized
    
    except Exception as e:
        logger.debug("Error parsing query params: %s", e)
    
    # Fallback: use hash of URL
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"watermark_{url_hash}.pdf"


def _sanitize_filename(name: str) -> str:
    """Clean filename for filesystem."""
    # Decode URL encoding
    name = unquote(name)
    
    # Remove .pdf extension if present (we'll add it back)
    if name.lower().endswith('.pdf'):
        name = name[:-4]
    
    # Replace problematic characters with underscore
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.replace('\n', '_').replace('\r', '_').replace('\t', '_')
    
    # Replace multiple spaces/underscores with single underscore
    name = re.sub(r'[ _]+', '_', name)
    
    # Remove leading/trailing spaces and underscores
    name = name.strip(' _.')
    
    # Limit length
    if len(name) > 200:
        name = name[:200]
    
    # If empty after sanitization
    if not name:
        name = f"document_{int(time.time())}"
    
    # ENSURE .pdf extension is always added
    if not name.lower().endswith('.pdf'):
        name = name + '.pdf'
    
    return name


def _is_allowed_host(parsed: ParseResult, allowed: Set[str]) -> bool:
    netloc = parsed.netloc.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    return netloc in allowed or hostname in allowed


def _iter_attribute_strings(value: object) -> Iterator[str]:
    if value is None:
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_attribute_strings(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_attribute_strings(item)
        return
    yield str(value)


def _get_with_ssl_fallback(url: str, *, timeout: int, stream: bool = False, referer: Optional[str] = None) -> Optional[requests.Response]:
    """Perform GET request with SSL fallback."""
    headers = {}
    if referer:
        headers["Referer"] = referer
    
    try:
        return _SESSION.get(url, timeout=timeout, stream=stream, headers=headers)
    except requests.exceptions.SSLError:
        if not VERIFY_SSL:
            return None
        try:
            return _SESSION.get(url, timeout=timeout, stream=stream, verify=False, headers=headers)
        except:
            return None
    except:
        return None


def _request_with_retries(url: str, retries: int = 3, delay: int = 5, referer: Optional[str] = None) -> Optional[requests.Response]:
    """Fetch URL with retries."""
    for attempt in range(retries):
        response = _get_with_ssl_fallback(url, timeout=15, referer=referer)
        if response and response.status_code == 200:
            return response
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def _is_html_response(response: requests.Response) -> bool:
    """Check if response is HTML."""
    content_type = response.headers.get("Content-Type", "").lower()
    return "html" in content_type or "xml" in content_type or content_type.startswith("text/")


def _unique_target_path(folder: Path, pdf_name: str, url: str) -> Path:
    """Generate unique file path."""
    candidate = folder / pdf_name
    if not candidate.exists():
        return candidate
    
    stem, suffix = os.path.splitext(pdf_name)
    hashed = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return folder / f"{stem}_{hashed}{suffix or '.pdf'}"


def _is_valid_pdf(content: bytes) -> bool:
    """Validate PDF content."""
    if not content or len(content) < 5:
        return False
    return content.startswith(b'%PDF-') and b'%%EOF' in content[-1024:]


def _extract_pdf_from_response(content: bytes) -> Optional[bytes]:
    """
    Extract pure PDF from response, removing debug output.
    
    Handles cases where server outputs debug text before PDF:
    Debug: File found...
    Debug: Processing...
    %PDF-1.4
    [binary data]
    %%EOF
    """
    if not content:
        return None
    
    # Find PDF header
    pdf_start = content.find(b'%PDF-')
    
    if pdf_start == -1:
        return None
    
    if pdf_start > 0:
        logger.info("Stripped %d bytes of debug output", pdf_start)
    
    return content[pdf_start:]