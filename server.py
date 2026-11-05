"""Vistaleon Card Price Checker — ChatGPT plugin (MCP server).

Answers "how much is my Pokemon card worth?" inside ChatGPT.

Price data: TCGdex API (free, no key) — live TCGplayer market prices in USD
plus Cardmarket prices in EUR, refreshed from source on every call.
Buy funnel: every answer links the card on Vistaleon (vistaleon.com search).

Run locally (stdio, for MCP Inspector / Claude Desktop):
    .venv/bin/python server.py

Run as a remote server (what ChatGPT connects to):
    MCP_TRANSPORT=http PORT=8000 .venv/bin/python server.py
    # serves streamable HTTP at http://localhost:8000/mcp
"""

import asyncio
import os
import ssl
import time
import urllib.parse

import httpx
from mcp.server.fastmcp import FastMCP

TCGDEX_BASE = "https://api.tcgdex.net/v2/en"
VISTALEON_SEARCH = "https://vistaleon.com/search?q="
CACHE_TTL_SECONDS = 900  # 15 minutes
MAX_CANDIDATES = 10      # card details fetched per query
MAX_RESULTS = 5          # priced printings returned per query

mcp = FastMCP("vistaleon-card-price-checker")

_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _cache_set(key: str, value: object) -> None:
    _cache[key] = (time.time(), value)


def _http_client() -> httpx.AsyncClient:
    """httpx client with an explicit proxy.

    The VM sets a no_proxy list containing bracketed IPv6 entries that
    httpx cannot parse, so we bypass env proxy handling entirely and pass
    the proxy directly (None on hosts without one = direct connection).
    TLS uses the system cert store (not certifi) so egress proxies with a
    locally trusted CA verify correctly.
    """
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    return httpx.AsyncClient(
        proxy=proxy or None,
        trust_env=False,
        verify=ssl.create_default_context(),
        headers={"User-Agent": "vistaleon-card-price-checker/1.0"},
    )


async def _tcgdex_get(client: httpx.AsyncClient, path: str):
    cached = _cache_get(path)
    if cached is not None:
        return cached
    resp = await client.get(f"{TCGDEX_BASE}{path}", timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    _cache_set(path, data)
    return data


def _money(value) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def _variant_prices(card: dict) -> list[dict]:
    """Flatten TCGdex variants_detailed into readable USD price rows.

    TCGdex repeats the same finish pricing across variant records, so rows
    with identical finish + prices are merged, keeping the most detail.
    """
    merged: dict[tuple, dict] = {}
    for variant in card.get("variants_detailed") or []:
        pricing = variant.get("pricing") or {}
        tcg = pricing.get("tcgplayer") or {}
        for finish, prices in tcg.items():
            if not isinstance(prices, dict):
                continue
            market = prices.get("marketPrice")
            if market is None:
                continue
            key = (finish, market, prices.get("lowPrice"), prices.get("highPrice"))
            row = merged.get(key)
            extras = {p for p in (variant.get("subtype") or "", ", ".join(variant.get("stamp") or [])) if p}
            if row is None:
                merged[key] = {
                    "finish": finish,
                    "market": market,
                    "low": prices.get("lowPrice"),
                    "high": prices.get("highPrice"),
                    "extras": extras,
                }
            else:
                row["extras"] |= extras
    rows = []
    for row in merged.values():
        row["extras"] = ", ".join(sorted(row["extras"]))
        rows.append(row)
    return rows


def _format_card(card: dict) -> str:
    name = card.get("name", "Unknown card")
    set_info = card.get("set") or {}
    set_name = set_info.get("name", "Unknown set")
    rarity = card.get("rarity") or "Unknown rarity"
    image = card.get("image") or ""
    prices = _variant_prices(card)
    vistaleon = VISTALEON_SEARCH + urllib.parse.quote_plus(name)

    lines = [f"## {name} — {set_name} ({rarity})"]
    if not prices:
        lines.append("No live TCGplayer market price listed for this printing right now.")
    for row in prices:
        label = row["finish"].replace("holofoil", "Holo").replace("reverseHolofoil", "Reverse Holo")
        if row["extras"]:
            label += f" ({row['extras']})"
        lines.append(
            f"- **{label}: market {_money(row['market'])}** "
            f"(low {_money(row['low'])} / high {_money(row['high'])})"
        )
    if image:
        lines.append(f"Card image: {image}")
    lines.append(f"Buy it on Vistaleon: {vistaleon}")
    return "\n".join(lines)


@mcp.tool()
async def check_card_price(card_name: str, set_name: str | None = None) -> str:
    """Check the current market price of a Pokemon card.

    Use when someone asks how much a Pokemon card is worth, what a card
    sells for, or whether to buy or sell a card.

    Args:
        card_name: Card name, e.g. "Charizard", "Pikachu", "Umbreon ex".
        set_name: Optional set name to pin down one printing,
            e.g. "Base Set", "Delta Reign", "151".
    """
    card_name = (card_name or "").strip()
    if not card_name:
        return "Tell me the card name and I will look up its price, for example 'Charizard' or 'Espeon ex'."

    async with _http_client() as client:
        try:
            query = urllib.parse.quote(card_name)
            matches = await _tcgdex_get(client, f"/cards?name={query}")
        except httpx.HTTPStatusError as exc:
            return (
                f"Could not reach the price database right now (HTTP {exc.response.status_code}). "
                "Try again in a minute."
            )
        except httpx.HTTPError:
            return "Could not reach the price database right now. Try again in a minute."

    if not matches:
        return (
            f'No Pokemon card found named "{card_name}". Check the spelling, '
            "or add the set it is from, for example 'Charizard Base Set'."
        )

    # Brief search results carry no set name, but the card id starts with
    # the set id ("base1-4" is Base Set). When a set was given, resolve it
    # and keep only printings from that set.
    candidates = matches
    set_label = ""
    wanted = ""
    if set_name:
        wanted = set_name.strip().lower()
        set_ids: list[str] = []
        sets: list[dict] = []
        try:
            async with _http_client() as client:
                sets = await _tcgdex_get(client, "/sets")
            set_ids = [
                s["id"]
                for s in sets
                if wanted in (s.get("name") or "").lower() and s.get("id")
            ]
        except httpx.HTTPError:
            pass
        if set_ids:
            prefixed = [
                m
                for m in matches
                if any((m.get("id") or "").startswith(sid + "-") for sid in set_ids)
            ]
            if prefixed:
                candidates = prefixed
                set_label = next(
                    (s["name"] for s in sets if s["id"] == set_ids[0]), set_name
                )
            else:
                return (
                    f'Found printings of "{card_name}" but none in a set matching "{set_name}". '
                    "Try a different set name, or leave the set out to see the main printings."
                )

    # Fetch details for the top candidates in parallel.
    ids = [m.get("id") for m in candidates[:MAX_CANDIDATES] if m.get("id")]
    async with _http_client() as client:
        try:
            details = await asyncio.gather(
                *[_tcgdex_get(client, f"/cards/{card_id}") for card_id in ids],
                return_exceptions=True,
            )
        except httpx.HTTPError:
            return "Could not reach the price database right now. Try again in a minute."

    cards = [d for d in details if isinstance(d, dict)]
    if set_name and not set_label:
        # No set id matched; fall back to the set name on the details.
        narrowed = [
            c for c in cards if wanted in ((c.get("set") or {}).get("name") or "").lower()
        ]
        if narrowed:
            cards = narrowed
            set_label = set_name

    if not cards or (set_name and not set_label):
        return (
            f'Found printings of "{card_name}" but none in a set matching "{set_name}". '
            "Try a different set name, or leave the set out to see the main printings."
        )

    # Most valuable printings first: that is usually the one people mean
    # when they ask what a card is worth.
    def _top_market(card: dict) -> float:
        prices = _variant_prices(card)
        return max((p["market"] for p in prices), default=0.0)

    cards.sort(key=_top_market, reverse=True)
    shown = cards[:MAX_RESULTS]

    header = (
        f"Market prices for **{card_name}**"
        + (f" from **{set_label}**" if set_label else "")
        + " (TCGplayer market, USD):"
    )
    body = "\n\n".join(_format_card(c) for c in shown)
    footer = ""
    total = len(candidates) if set_label else len(matches)
    if len(cards) > MAX_RESULTS or total > len(cards):
        footer = (
            f"\n\nShowing {len(shown)} of {total} printings found. "
            "Add a set name to narrow it to one printing."
        )
    return header + "\n\n" + body + footer


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", "8000"))
        mcp.settings.port = port
        mcp.settings.host = "0.0.0.0"
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
