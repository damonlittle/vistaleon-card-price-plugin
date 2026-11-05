"""Smoke test: exercise check_card_price over stdio and print results."""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        env=dict(os.environ),  # child needs the egress proxy vars
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])
            cases = [
                {"card_name": "Charizard"},
                {"card_name": "Charizard", "set_name": "Base Set"},
                {"card_name": "Umbreon ex"},
                {"card_name": "Not A Real Card Zzz"},
            ]
            for args in cases:
                result = await session.call_tool("check_card_price", args)
                text = "\n".join(
                    block.text for block in result.content if hasattr(block, "text")
                )
                print("=" * 70)
                print("ARGS:", args)
                print(text[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
