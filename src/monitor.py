import logging
import os
import signal
import sys
import time
from collections import defaultdict

from src.config import EventConfig, load_config
from src.f1_utils import SESSION_ORDER, parse_event_name
from src.price_tracker import PriceTracker
from src.scraper import PriceScraper
from src.telegram_bot import TelegramNotifier
from src.ticketmaster import EventInfo, PriceRange, TicketmasterClient

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self):
        self.config = load_config()
        self.tm_client = TicketmasterClient(self.config.ticketmaster_api_key)
        self.notifier = TelegramNotifier(
            self.config.telegram_bot_token,
            self.config.telegram_chat_id,
        )
        self.tracker = PriceTracker(self.config.price_history_path)
        self.scraper = PriceScraper()
        self.running = True

    def run(self):
        self._setup_signals()
        self._send_startup_message()

        logger.info("Starting monitoring loop (interval: %ds)", self.config.check_interval_seconds)

        while self.running:
            self.check_all_events()
            remaining = self.config.check_interval_seconds
            while remaining > 0 and self.running:
                time.sleep(min(remaining, 5))
                remaining -= 5

        self.shutdown()

    def check_all_events(self):
        logger.info("Starting check cycle...")
        try:
            for ev_cfg in self.config.events:
                try:
                    self._process_event_config(ev_cfg)
                except Exception as e:
                    logger.error("Error processing config %s: %s", ev_cfg.name or ev_cfg.event_id, e, exc_info=True)

            self.tracker.save()

        except Exception as e:
            logger.error("Unexpected error in check cycle: %s", e, exc_info=True)

    def _process_event_config(self, ev_cfg: EventConfig):
        """Resolve events, scrape prices, group by GP, send summary."""
        # 1. Resolve events from API
        events: list[EventInfo] = []
        if ev_cfg.event_id:
            event = self.tm_client.get_event_details(ev_cfg.event_id)
            if event:
                events.append(event)
        elif ev_cfg.name:
            events = self.tm_client.search_by_name(ev_cfg.name)
            logger.info("Search '%s': %d onsale events", ev_cfg.name, len(events))

        if not events:
            return

        # 2. Parse event names and group by GP
        # gp_name -> {session -> {section -> EventInfo}}
        gp_groups: dict[str, dict[str, dict[str, EventInfo]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        ungrouped: list[EventInfo] = []

        for event in events:
            parsed = parse_event_name(event.name, is_sprint=ev_cfg.sprint)
            if parsed:
                gp_groups[parsed.gp_name][parsed.session][parsed.section] = event
            else:
                ungrouped.append(event)

        # 3. Scrape prices for each event
        all_events = list(events)
        for event in all_events:
            try:
                if not event.price_ranges and event.url:
                    listings = self.scraper.scrape_prices(event.url)
                    event.tickets = listings
                    if listings:
                        prices = [t.price for t in listings]
                        event.price_ranges = [PriceRange(
                            currency=listings[0].currency,
                            min_price=min(prices),
                            max_price=max(prices),
                        )]
            except Exception as e:
                logger.error("Scrape failed for %s: %s", event.name, e)

        # 4. Track prices per event (for change detection)
        for event in all_events:
            try:
                self.tracker.check_and_update(event)
            except Exception as e:
                logger.error("Tracker error for %s: %s", event.event_id, e)

        # 5. Always send grouped summary with current prices
        for gp_name, sessions in gp_groups.items():
            first_event = next(iter(next(iter(sessions.values())).values()))
            msg = self.notifier.format_gp_summary(
                gp_name=gp_name,
                sessions=sessions,
                venue=first_event.location_str,
                language=self.config.language,
                is_sprint=ev_cfg.sprint,
            )
            self.notifier.send_message(msg)

        for event in ungrouped:
            msg = self.notifier.format_event_notification(
                event, None, self.config.language,
            )
            self.notifier.send_message(msg)

        logger.info("Notifications sent for %d GP groups", len(gp_groups))

    def _send_startup_message(self):
        ru = self.config.language == "ru"
        interval_min = self.config.check_interval_seconds // 60
        tracked = len(self.tracker.history)

        event_lines = []
        for ev in self.config.events:
            name = ev.label or ev.name or ev.event_id
            sprint_tag = " (sprint)" if ev.sprint else ""
            event_lines.append(f"  \u2022 {name}{sprint_tag}")
        events_str = "\n".join(event_lines) if event_lines else "  (none)"

        if ru:
            text = (
                "\U0001f916 <b>F1 Ticket Monitor запущен</b>\n"
                f"\u23f0 Интервал: {interval_min} мин.\n"
                f"\U0001f3af Отслеживаемые события:\n{events_str}\n"
                f"\U0001f4ca В истории: {tracked} событий\n"
                f"\U0001f552 Первая проверка: сейчас"
            )
        else:
            text = (
                "\U0001f916 <b>F1 Ticket Monitor started</b>\n"
                f"\u23f0 Interval: {interval_min} min\n"
                f"\U0001f3af Tracked events:\n{events_str}\n"
                f"\U0001f4ca History: {tracked} events\n"
                f"\U0001f552 First check: now"
            )

        self.notifier.send_startup_message(text)

    def _setup_signals(self):
        def handle_stop(signum, frame):
            logger.info("Received signal %s, shutting down...", signum)
            self.running = False

        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)

    def shutdown(self):
        logger.info("Shutting down...")
        self.tracker.save()
        self.tm_client.close()
        self.notifier.close()
        self.scraper.close()
        logger.info("Goodbye!")


def setup_logging():
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def main():
    setup_logging()
    monitor = Monitor()
    monitor.run()


if __name__ == "__main__":
    main()
