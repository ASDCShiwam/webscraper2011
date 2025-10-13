from django.contrib import admin

from .models import CrawlRun, DownloadedDocument


@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):
    list_display = (
        "start_url",
        "pages_crawled",
        "pdfs_downloaded",
        "started_at",
        "completed_at",
    )
    list_filter = ("started_at",)
    search_fields = ("start_url",)


@admin.register(DownloadedDocument)
class DownloadedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "filename",
        "pdf_url",
        "source_page",
        "file_size_bytes",
        "download_method",
        "downloaded_at",
    )
    list_filter = ("download_method", "downloaded_at")
    search_fields = ("filename", "pdf_url", "source_page")
