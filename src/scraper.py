import logging
import re
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, TimeoutError as PwTimeout

logger = logging.getLogger(__name__)


@dataclass
class TicketListing:
    section: str
    row: str
    price: float
    currency: str = "USD"


# Pattern: "Sec SF-2 • Row 11\nVerified Ticket\n$130.00"
# Text spans multiple lines, so use re.DOTALL
LISTING_RE = re.compile(
    r"Sec\s+(.+?)\s*[•·]\s*Row\s+(\S+).*?\$\s*([\d,]+(?:\.\d{2})?)",
    re.DOTALL,
)


class PriceScraper:
    def __init__(self):
        self._pw = None
        self._browser: Optional[Browser] = None

    def _ensure_browser(self):
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)

    def scrape_prices(self, event_url: str, max_listings: int = 40) -> list[TicketListing]:
        """Load a Ticketmaster event page and extract ticket listings."""
        if not event_url:
            return []

        self._ensure_browser()
        page = None

        try:
            page = self._browser.new_page()

            # Use 'load' instead of 'networkidle' — more reliable,
            # then wait explicitly for ticket list elements
            page.goto(event_url, wait_until="load", timeout=30000)

            # Wait for ticket listings to appear (JS-rendered)
            try:
                page.wait_for_selector(
                    'li[role="menuitem"]',
                    state="attached",
                    timeout=20000,
                )
                # Extra pause for all items to render
                page.wait_for_timeout(2000)
            except PwTimeout:
                logger.warning("No ticket listings found on %s", event_url[:80])
                return []

            # Collect all ticket listing items on the page
            items = page.query_selector_all('li[role="menuitem"]')
            listings: list[TicketListing] = []

            for item in items[:max_listings]:
                text = item.inner_text().strip()
                m = LISTING_RE.search(text)
                if m:
                    price_str = m.group(3).replace(",", "")
                    listings.append(TicketListing(
                        section=m.group(1),
                        row=m.group(2),
                        price=float(price_str),
                    ))

            logger.info("Scraped %d listings from %s", len(listings), event_url[:80])
            return listings

        except Exception as e:
            logger.error("Scrape failed for %s: %s", event_url[:80], e)
            return []
        finally:
            if page:
                page.close()

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
