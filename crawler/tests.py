import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CrawlRun, DownloadedDocument

class StartScrapingViewTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="crawler-tests-")
        self.override = override_settings(PDF_DOWNLOAD_ROOT=self.temp_dir)
        self.override.enable()
        self.download_root = Path(self.temp_dir)

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_persists_crawl_and_documents(self) -> None:
        host_folder = self.download_root / "example.com"
        host_folder.mkdir(parents=True, exist_ok=True)
        pdf_path = host_folder / "example.pdf"
        pdf_content = b"%PDF-1.4 test pdf\n%%EOF"
        pdf_path.write_bytes(pdf_content)

        crawl_output = [
            {
                "url": "https://example.com/example.pdf",
                "path": str(pdf_path),
                "filename": "example.pdf",
                "downloaded_at": "2024-06-01T12:00:00Z",
                "source_page": "https://example.com/page",
                "method": "direct",
            }
        ]
        crawl_metadata = {
            "pages_crawled": "5",
            "started_at": "2024-06-01T11:59:00Z",
            "finished_at": "2024-06-01T12:01:00Z",
        }

        with mock.patch("crawler.views.crawl_and_download", return_value=(crawl_output, crawl_metadata)):
            response = self.client.post(
                reverse("start_scraping"),
                {
                    "url": "https://example.com",
                },
            )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(CrawlRun.objects.count(), 1)
        crawl_run = CrawlRun.objects.first()
        assert crawl_run is not None
        self.assertEqual(crawl_run.start_url, "https://example.com")
        self.assertEqual(crawl_run.pages_crawled, 5)
        self.assertEqual(crawl_run.pdfs_downloaded, 1)
        expected_start = datetime(2024, 6, 1, 11, 59, tzinfo=timezone.utc)
        self.assertLess(abs((crawl_run.started_at - expected_start).total_seconds()), 1)

        documents = DownloadedDocument.objects.filter(run=crawl_run)
        self.assertEqual(documents.count(), 1)
        document = documents.first()
        assert document is not None
        self.assertEqual(document.filename, "example.pdf")
        self.assertEqual(document.pdf_url, "https://example.com/example.pdf")
        self.assertEqual(document.source_page, "https://example.com/page")
        self.assertEqual(document.download_method, "direct")
        self.assertEqual(document.file_size_bytes, len(pdf_content))
        self.assertEqual(len(document.sha256), 64)
