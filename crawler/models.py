from django.db import models
from django.utils import timezone


class CrawlRun(models.Model):
    """Represents a crawl execution and its high level metadata."""

    start_url = models.URLField(help_text="Starting URL that initiated the crawl")
    download_directory = models.TextField(help_text="Absolute path to the crawl's download folder")
    max_pages = models.PositiveIntegerField(null=True, blank=True)
    max_pdfs = models.PositiveIntegerField(null=True, blank=True)
    pages_crawled = models.PositiveIntegerField(default=0)
    pdfs_downloaded = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:  # pragma: no cover - human readable representation
        return f"CrawlRun({self.start_url})"


class DownloadedDocument(models.Model):
    """Stores metadata about a single PDF captured during a crawl."""

    run = models.ForeignKey(CrawlRun, on_delete=models.CASCADE, related_name="documents")
    pdf_url = models.TextField(help_text="Direct URL used to retrieve the PDF")
    source_page = models.TextField(blank=True, help_text="Web page URL where the PDF link was found")
    filename = models.CharField(max_length=255)
    stored_path = models.TextField(help_text="Filesystem path where the PDF is stored")
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    download_method = models.CharField(max_length=32, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    tags = models.TextField(blank=True, help_text="Comma-separated informative tags from the source page")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-downloaded_at", "id"]

    def __str__(self) -> str:  # pragma: no cover - human readable representation
        return self.filename
