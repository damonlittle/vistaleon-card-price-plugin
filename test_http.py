"""Smoke test over streamable HTTP (the transport ChatGPT connects to)."""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main() -> int:
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "check_card_price", {"card_name": "Charizard", "set_name": "Base Set"}
            )
            text = "\n".join(
                block.text for block in result.content if hasattr(block, "text")
            )
            print(text[:900])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
