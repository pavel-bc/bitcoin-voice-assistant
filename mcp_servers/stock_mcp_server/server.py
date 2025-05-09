import logging
import asyncio
from mcp.server.fastmcp import FastMCP
import yfinance as yf
import sys
import json
import os
from dotenv import load_dotenv

# Determine the absolute path to the .env file in the project root
# __file__ is the path to the current script (server.py)
# os.path.dirname(__file__) is the directory of server.py
# os.path.join(..., "..", "..") goes up two directories to the project root
project_root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(project_root_env, override=True) # Load variables from .env file

# --- Configuration ---
# Basic logging setup
logging.basicConfig(level=logging.DEBUG, # <--- Change level to DEBUG for more detail
                    stream=sys.stderr,
                    format='%(asctime)s - %(name)s - %(levelname)s - MCP_SERVER - %(message)s')
logger = logging.getLogger(__name__)

# --- FastMCP Server Initialization ---
# Creates a customizable MCP server named "Stock Price Server"
logger.info("Initializing FastMCP server...")
mcp = FastMCP("Stock Price Server") # Name used during initialization

# --- Tool Functions (using decorators) ---

# Note: The get_stock_price function is now directly decorated as a tool.
# It's generally better practice for tools to return structured data (like dicts)
# rather than just floats or strings, to allow for error reporting.

@mcp.tool()
async def get_current_stock_price(symbol: str) -> dict:
    """
    Retrieve the current stock price for the given ticker symbol.
    Returns a dictionary containing the price and currency, or an error message.
    """
    # Log the incoming arguments (part of the MCP request's params)
    logger.debug(f"Tool 'get_current_stock_price' called with args: {{'symbol': '{symbol}'}}")

    # Check MOCK_STOCK_API environment variable
    mock_api_enabled = os.getenv("MOCK_STOCK_API", "False").lower() == "true"

    if mock_api_enabled:
        logger.info("MOCK_STOCK_API is enabled. Returning mock data.")
        result = {
            "symbol": symbol.upper(),
            "price": 123.45,
            "currency": "USD",
            "note": "Mock data (MOCK_STOCK_API enabled)"
        }
        logger.debug(f"Tool 'get_current_stock_price' returning result: {json.dumps(result, indent=2)}")
        return result

    # If MOCK_STOCK_API is not true, proceed with actual API call
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m")

        if not hist.empty:
            price = hist['Close'].iloc[-1]
            currency = ticker.info.get('currency', 'USD')
            result = {
                "symbol": symbol.upper(),
                "price": round(price, 2),
                "currency": currency
            }
            logger.info(f"Tool: Successfully found price {result['price']} {result['currency']} for {symbol} using history.")
        else:
            info = ticker.info
            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
            if price is not None:
                 currency = info.get('currency', 'USD')
                 result = {
                     "symbol": symbol.upper(),
                     "price": round(float(price), 2),
                     "currency": currency
                 }
                 logger.info(f"Tool: Successfully found price {result['price']} {result['currency']} for {symbol} using fallback info.")
            else:
                logger.warning(f"Tool: No current price data found for symbol {symbol} via history or info. Returning mock data.")
                result = {
                    "symbol": symbol.upper(),
                    "price": 123.45,
                    "currency": "USD",
                    "note": "Mock data: Price not found"
                }

    except Exception as e:
        logger.error(f"Tool: Error fetching price for {symbol}: {e}. Returning mock data.", exc_info=False) # Set exc_info=False if stack trace is too verbose
        result = {
            "symbol": symbol.upper(),
            "price": 123.45,
            "currency": "USD",
            "note": f"Mock data: API error ({type(e).__name__})"
        }

    # Log the result dictionary (which will be the MCP response's result field)
    logger.debug(f"Tool 'get_current_stock_price' returning result: {json.dumps(result, indent=2)}")
    return result


# --- Main Execution ---
if __name__ == "__main__":
    # --- To run the MCP server (original behavior) ---
    logger.info("Starting FastMCP Stock Price Server...")
    mcp.run() # defaults to stdio transport
    logger.info("FastMCP Stock Price Server stopped.")

    # --- To test the get_current_stock_price tool standalone ---
    # async def test_tool():
    #     logger.info("Testing 'get_current_stock_price' tool standalone...")
    #     # Test with a common stock symbol
    #     test_symbol = "AAPL"
    #     # test_symbol = "MSFT"
    #     # test_symbol = "GOOGL"
    #     # test_symbol = "INVALID" # To test error handling

    #     print(f"--- Testing with symbol: {test_symbol} ---")
    #     result = await get_current_stock_price(test_symbol)
    #     print(f"--- Result for {test_symbol} ---")
    #     print(json.dumps(result, indent=2))
    #     print("------------------------------------")


    # # Run the standalone test
    # asyncio.run(test_tool())
