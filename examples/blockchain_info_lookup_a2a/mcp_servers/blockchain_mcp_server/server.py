import logging
import asyncio
import httpx
import sys
import json
import os
from dotenv import load_dotenv

# Determine the absolute path to the .env file in the project root
project_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(project_root_env, override=True)

# --- Configuration ---
logging.basicConfig(level=logging.DEBUG,
                    stream=sys.stderr,
                    format='%(asctime)s - %(name)s - %(levelname)s - MCP_SERVER - %(message)s')
logger = logging.getLogger(__name__)

# --- FastMCP Server Initialization ---
from mcp.server.fastmcp import FastMCP
logger.info("Initializing FastMCP server...")
mcp = FastMCP("Blockchain Info Server")

# --- Tool Functions ---

@mcp.tool()
async def get_bitcoin_price() -> dict:
    """
    Retrieves the current Bitcoin price in major currencies.
    """
    logger.debug("Tool 'get_bitcoin_price' called.")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.blockchain.com/ticker")
            response.raise_for_status()
            data = response.json()
            # For simplicity, we'll return a few major currencies
            result = {
                "USD": data.get("USD", {}).get("last"),
                "EUR": data.get("EUR", {}).get("last"),
                "GBP": data.get("GBP", {}).get("last"),
            }
            logger.info(f"Successfully retrieved Bitcoin price: {result}")
            return result
    except Exception as e:
        logger.error(f"Error fetching Bitcoin price: {e}", exc_info=True)
        return {"error": str(e)}

@mcp.tool()
async def get_address_balance(address: str) -> dict:
    """
    Retrieves the balance for a given Bitcoin address.
    """
    logger.debug(f"Tool 'get_address_balance' called with address: {address}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://blockchain.info/rawaddr/{address}")
            response.raise_for_status()
            data = response.json()
            # Extract relevant balance information
            # Balance is in Satoshi, so convert to BTC
            final_balance_satoshi = data.get("final_balance", 0)
            final_balance_btc = final_balance_satoshi / 100_000_000
            result = {
                "address": data.get("address"),
                "final_balance_btc": final_balance_btc,
                "total_received_btc": data.get("total_received", 0) / 100_000_000,
                "n_tx": data.get("n_tx"),
            }
            logger.info(f"Successfully retrieved balance for {address}: {result}")
            return result
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 500:
             logger.error(f"Invalid Bitcoin address format or address not found for: {address}")
             return {"error": "Invalid Bitcoin address or address not found."}
        logger.error(f"HTTP error fetching address balance for {address}: {e}", exc_info=True)
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Error fetching address balance for {address}: {e}", exc_info=True)
        return {"error": str(e)}

# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting FastMCP Blockchain Info Server...")
    mcp.run()
    logger.info("FastMCP Blockchain Info Server stopped.")