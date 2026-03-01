import html
import logging
from typing import Optional

import httpx

from src.f1_utils import SESSION_ORDER, session_emoji, session_label
from src.price_tracker import PriceChange
from src.ticketmaster import EventInfo

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = httpx.Client(timeout=10.0)
        self.api_url = TELEGRAM_API.format(token=bot_token)

    def send_message(self, text: str) -> bool:
        try:
            r = self.client.post(self.api_url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if r.status_code != 200:
                logger.error("Telegram error %d: %s", r.status_code, r.text)
                return False
            return True
        except Exception as e:
            logger.error("Failed to send Telegram message: %s", e)
            return False

    def send_startup_message(self, config_summary: str) -> bool:
        return self.send_message(config_summary)

    def format_event_notification(
        self,
        event: EventInfo,
        price_change: Optional[PriceChange] = None,
        language: str = "ru",
    ) -> str:
        name = html.escape(event.name)
        location = html.escape(event.location_str) if event.location_str else "N/A"
        date_str = self._format_date(event, language)
        price_str = self._format_price(event)
        link_text = "Купить билеты" if language == "ru" else "Buy tickets"

        lines = [
            f"\U0001f3ce <b>{name}</b>",
            f"\U0001f4cd {location}",
            f"\U0001f4c5 {date_str}",
            f"\U0001f4b0 {price_str}",
        ]

        # Show cheapest tickets if scraped
        if event.tickets:
            sorted_tickets = sorted(event.tickets, key=lambda t: t.price)[:3]
            header = "Лучшие предложения:" if language == "ru" else "Best deals:"
            lines.append(f"\U0001f39f {header}")
            for t in sorted_tickets:
                lines.append(f"  Sec {t.section} \u2022 Row {t.row} \u2014 ${t.price:,.2f}")

        if price_change:
            change_line = self._format_price_change_line(price_change, language)
            if change_line:
                lines.append(change_line)

        if event.url:
            lines.append(f'\U0001f517 <a href="{html.escape(event.url)}">{link_text}</a>')

        return "\n".join(lines)

    def format_gp_summary(
        self,
        gp_name: str,
        sessions: dict[str, dict[str, EventInfo]],
        venue: str,
        language: str = "ru",
        is_sprint: bool = False,
    ) -> str:
        """
        Format a consolidated GP summary grouped by session type.

        sessions: {session_type -> {section_name -> EventInfo}}
        """
        ru = language == "ru"
        link_text = "Купить билеты" if ru else "Buy tickets"

        lines = [
            f"\U0001f3ce <b>{html.escape(gp_name)}</b>",
            f"\U0001f4cd {html.escape(venue)}",
        ]

        # Sort sessions: race first, then qualifying, then practice
        sorted_sessions = sorted(
            sessions.items(),
            key=lambda x: SESSION_ORDER.get(x[0], 99),
        )

        for sess_type, sections in sorted_sessions:
            emoji = session_emoji(sess_type)
            label = session_label(sess_type, language)

            # Get date from first event in this session
            first_event = next(iter(sections.values()))
            date_str = self._format_date(first_event, language)

            lines.append(f"\n{emoji} <b>{label}</b> — {date_str}")

            # Sort sections by min price
            section_items = []
            for section_name, event in sections.items():
                min_price = None
                best_row = ""
                if event.tickets:
                    cheapest = min(event.tickets, key=lambda t: t.price)
                    min_price = cheapest.price
                    best_row = cheapest.row
                elif event.price_ranges:
                    min_price = event.price_ranges[0].min_price
                section_items.append((section_name, min_price, best_row, event))

            section_items.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))

            for section_name, min_price, best_row, event in section_items:
                if min_price is not None:
                    row_str = f", Row {best_row}" if best_row else ""
                    price_str = f"от ${min_price:,.2f}{row_str}"
                else:
                    price_str = "нет цен" if ru else "no prices"
                lines.append(f"  {html.escape(section_name)}: {price_str}")

        # Add links to all events (just the first per section of race day)
        race_sections = sessions.get("race", {})
        if race_sections:
            first_race = next(iter(race_sections.values()))
            if first_race.url:
                lines.append(f'\n\U0001f517 <a href="{html.escape(first_race.url)}">{link_text}</a>')

        return "\n".join(lines)

    def _format_price(self, event: EventInfo) -> str:
        if not event.price_ranges:
            return "Цены пока не доступны"
        pr = event.price_ranges[0]
        sym = _currency_symbol(pr.currency)
        return f"{sym}{pr.min_price:,.2f} — {sym}{pr.max_price:,.2f}"

    def _format_date(self, event: EventInfo, language: str) -> str:
        if event.date_tba:
            return "Дата уточняется" if language == "ru" else "Date TBA"
        parts = []
        if event.start_date:
            parts.append(event.start_date)
        if event.time_tba:
            parts.append("(время уточняется)" if language == "ru" else "(time TBA)")
        elif event.start_time:
            parts.append(event.start_time[:5])  # "14:00:00" -> "14:00"
        return " ".join(parts) if parts else "N/A"

    def _format_price_change_line(self, change: PriceChange, language: str) -> str:
        sym = _currency_symbol(change.currency)
        ru = language == "ru"

        if change.change_type == "new_event":
            return "\U0001f195 Новое событие найдено!" if ru else "\U0001f195 New event found!"

        if change.change_type == "prices_removed":
            return "\u274c Цены больше не доступны" if ru else "\u274c Prices no longer available"

        if change.change_type == "min_decreased":
            label = "Мин. цена упала" if ru else "Min price dropped"
            return f"\u2b07\ufe0f {label}: {sym}{change.old_min:,.2f} \u2192 {sym}{change.new_min:,.2f}"

        if change.change_type == "min_increased":
            label = "Мин. цена выросла" if ru else "Min price increased"
            return f"\u2b06\ufe0f {label}: {sym}{change.old_min:,.2f} \u2192 {sym}{change.new_min:,.2f}"

        if change.change_type == "max_decreased":
            label = "Макс. цена упала" if ru else "Max price dropped"
            return f"\u2b07\ufe0f {label}: {sym}{change.old_max:,.2f} \u2192 {sym}{change.new_max:,.2f}"

        if change.change_type == "max_increased":
            label = "Макс. цена выросла" if ru else "Max price increased"
            return f"\u2b06\ufe0f {label}: {sym}{change.old_max:,.2f} \u2192 {sym}{change.new_max:,.2f}"

        return ""

    def close(self):
        self.client.close()


def _currency_symbol(currency: str) -> str:
    return {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "CAD": "C$"}.get(currency, currency + " ")
