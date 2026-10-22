import asyncio
import os

from mcp import Client

# Real tools now require auth: pass a JWT via the token argument
# (export MCP_TEST_TOKEN first), or expect 401-style error dicts.
TOKEN = os.environ.get("MCP_TEST_TOKEN")


async def main():
    async def call(name, args):
        if TOKEN:
            args = {**args, "token": TOKEN}
        return await client.call_tool(name, args)

    async with Client("http://127.0.0.1:8001/mcp") as client:

        # Discover tools
        result = await client.list_tools()

        print("AVAILABLE TOOLS:")
        for tool in result.tools:
            print(f"- {tool.name}")

        # Call list_orders
        print("\nCALLING list_orders...")

        orders = await call(
            "list_orders",
            {"status": "pending", "limit": 5},
        )

        print(orders.content)


if __name__ == "__main__":
    asyncio.run(main())