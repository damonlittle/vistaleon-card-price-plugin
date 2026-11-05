# Vistaleon Card Price Checker — ChatGPT plugin

Answers **"how much is my Pokemon card worth?"** inside ChatGPT, with live
TCGplayer market prices and a buy link to Vistaleon on every answer.

## How it works

- **One tool:** `check_card_price(card_name, set_name?)`
  - "Charizard" → top printings by market value (Base Set Charizard holo: $987.13 market)
  - "Charizard, Base Set" → only printings from that set family
  - Unknown card → honest "not found, check spelling" (no invented prices)
- **Price data:** TCGdex API (free, no key) — live TCGplayer low / market / high in USD.
  Pokemon TCG API was tested as a backup; it returned 500s from this network.
- **Funnel:** every card links to `vistaleon.com/search?q=<card name>`.
- **Stack:** Python 3.12, MCP Python SDK v1 (`mcp<2`, FastMCP), httpx.
  Transport is streamable HTTP, the transport ChatGPT plugin extensions use.

## Tested live (Nov 4, 2026)

- `check_card_price("Charizard")` → Base Set holo $987.13 market, Legendary
  Collection $899.99, Blaine's Charizard $699.99, 5 of 126 printings shown.
- `check_card_price("Charizard", "Base Set")` → only Base Set family printings.
- `check_card_price("Umbreon ex")` → Prismatic Evolutions SIR $1,178.25 market.
- Unknown card → clean not-found message.
- Both transports verified: stdio (MCP client) and streamable HTTP on :8000.

## Run it

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Local / MCP Inspector:
.venv/bin/python server.py

# Remote server (what ChatGPT connects to):
MCP_TRANSPORT=http PORT=8000 .venv/bin/python server.py
# serves http://localhost:8000/mcp
```

Tests: `.venv/bin/python test_client.py` (stdio) and `test_http.py` (HTTP,
needs the server running on :8000 first).

## Deploy it (needed before anyone can use it in ChatGPT)

The server needs a public HTTPS URL. Easiest path, no code changes:

1. Push this folder to a GitHub repo.
2. **Railway** (railway.app): New Project → Deploy from GitHub → it reads the
   `Dockerfile` and sets `PORT` automatically. Or **Render**: New Web Service
   → Docker → same repo. Or **Fly.io**: `fly launch` with the Dockerfile.
3. Note the public URL, e.g. `https://vistaleon-card-prices.up.railway.app/mcp`.

No secrets needed: no API keys, no database. TCGdex is free and keyless.

## Connect it in ChatGPT

1. In ChatGPT, turn on **Developer Mode** (Settings → Apps / Developer).
2. Create an app / add an MCP server with the public URL above.
3. Test in chat: "How much is my Charizard from Base Set worth?"
4. Confirm the answer shows the price and the Vistaleon link.

## Get it into the plugin directory (the distribution play)

Once it works connected in Developer Mode, submit it for the ChatGPT plugin
directory through OpenAI's developer submission flow (directory listing needs
their review; the exact submission form lives in the OpenAI developer docs,
which change fast, so follow the current flow there rather than a saved link).
Use the name, description and example prompts in `plugin-metadata.md`.

## Plugin metadata

See `plugin-metadata.md` for the directory name, description written in the
exact words people type into ChatGPT, and example prompts.
