# minimal_mcp_client_bare.py
# A bare-bones script to connect via stdio and print a stock price.

import asyncio
import sys
import os
import pathlib
import json

# Assume mcp is installed
from mcp import ClientSession, StdioServerParameters
from mcp.types import TextContent, CallToolResult
from mcp.client.stdio import stdio_client

# --- Configuration ---
SYMBOL_TO_QUERY = "AAPL" # Change this to the desired stock symbol

# --- Server Configuration ---
project_root = pathlib.Path.cwd()
server_script_path = project_root / "mcp_servers" / "stock_mcp_server" / "server.py"

# No check if server file exists

server_params = StdioServerParameters(
    command=sys.executable,
    args=[str(server_script_path)],
    cwd=str(project_root)
)

# --- Main Async Function ---
async def get_price_minimal():
    """Connects, calls tool, extracts and prints price."""
    # Connect and start session
    async with stdio_client(server_params) as (read_stream, write_stream), \
               ClientSession(read_stream, write_stream) as session:

        # Initialize
        await session.initialize()

        # Call tool
        response_obj: CallToolResult = await session.call_tool(
            "get_stock_price",
            {"symbol": SYMBOL_TO_QUERY}
        )

        # --- Minimal Parsing and Printing ---
        # Directly attempt to parse and extract, assuming success and correct structure
        # This will raise errors (IndexError, TypeError, JSONDecodeError, KeyError) if anything is wrong
        parsed_dict = json.loads(response_obj.content[0].text)
        print(parsed_dict)
        # stock_data = parsed_dict["result"]
        price = parsed_dict["price"]
        # # currency = stock_data.get('currency', '') # Optionally get currency
        # # print(f"{price} {currency}") # Print with currency
        print(price) # Print only the price

# --- Run the main function ---
if __name__ == "__main__":
    asyncio.run(get_price_minimal())
