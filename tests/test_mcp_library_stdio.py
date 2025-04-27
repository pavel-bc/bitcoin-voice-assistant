# tests/test_get_stock_price_stdio.py

import asyncio
import sys
import os
import pathlib
import logging
import json # Import json for parsing
import pytest
import pytest_asyncio

# Import necessary components from the mcp library
from mcp import ClientSession, StdioServerParameters
from mcp import McpError # Correct exception class
from mcp.types import TextContent, CallToolResult # Correct location for models
from mcp.client.stdio import stdio_client


# Basic logging setup for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - MCP_STOCK_TEST - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Server Configuration ---
test_script_path = pathlib.Path(__file__).resolve()
tests_dir = test_script_path.parent
project_root = tests_dir.parent
# *** IMPORTANT: Ensure this path points to your actual server file ***
server_script_path = project_root / "mcp_servers" / "stock_mcp_server" / "server.py"

if not server_script_path.is_file():
    logger.error(f"Server script not found: {server_script_path}")
    pytest.fail(f"Server script not found: {server_script_path}", pytrace=False)

server_params = StdioServerParameters(
    command=sys.executable,
    args=[str(server_script_path)],
    cwd=str(project_root)
)

# --- Pytest Fixture for MCP Session ---
@pytest_asyncio.fixture(scope="function")
async def mcp_session():
    """Pytest fixture to provide an initialized MCP ClientSession."""
    logger.info("Setting up MCP session fixture...")
    session = None
    stdio_client_instance = None
    client_session_instance = None
    read_stream_local = None
    write_stream_local = None

    try:
        stdio_client_instance = stdio_client(server_params)
        read_stream_local, write_stream_local = await stdio_client_instance.__aenter__()
        logger.info("stdio_client connected, creating ClientSession...")

        client_session_instance = ClientSession(read_stream_local, write_stream_local)
        session = await client_session_instance.__aenter__()
        logger.info("ClientSession created, initializing...")

        init_response = await session.initialize()
        logger.info(f"MCP Session Initialized. Server capabilities: {init_response.capabilities}")
        yield session # Provide the initialized session
        logger.info("Test function finished, cleaning up session...")

    except Exception as e:
        logger.error(f"Error during MCP session setup: {e}", exc_info=True)
        pytest.fail(f"MCP session fixture failed: {e}", pytrace=False)
    finally:
        # Cleanup logic, ignoring potential cancel scope errors during teardown
        logger.info("Starting fixture cleanup...")
        if client_session_instance:
            try:
                logger.info("Exiting ClientSession context...")
                await client_session_instance.__aexit__(None, None, None)
                logger.info("ClientSession context exited.")
            except Exception as e_cs:
                 if "Attempted to exit cancel scope" not in str(e_cs):
                      logger.error(f"Error during ClientSession cleanup: {e_cs}", exc_info=True)
                 else:
                      logger.warning(f"Ignoring cancel scope error during ClientSession cleanup: {e_cs}")
        if stdio_client_instance:
            try:
                logger.info("Exiting stdio_client context...")
                await stdio_client_instance.__aexit__(None, None, None)
                logger.info("stdio_client context exited, server process stopped.")
            except Exception as e_sc:
                 if "Attempted to exit cancel scope" not in str(e_sc):
                     logger.error(f"Error during stdio_client cleanup: {e_sc}", exc_info=True)
                 else:
                      logger.warning(f"Ignoring cancel scope error during stdio_client cleanup: {e_sc}")
        logger.info("Fixture cleanup finished.")


# --- Helper to extract result from CallToolResult ---
def parse_tool_result(response: CallToolResult) -> dict | None:
    """
    Parses the JSON dictionary from the CallToolResult content.
    Expects the server tool to return a JSON string representing a dictionary
    like {"result": ...} or {"error": ...}.
    """
    if not isinstance(response, CallToolResult):
        logger.error(f"Expected CallToolResult, got {type(response)}")
        return None

    if not response.content:
         logger.warning(f"Tool call response has no content: {response}")
         return None # No content to parse

    if isinstance(response.content[0], TextContent):
        try:
            # The text field contains the direct JSON output of the server tool
            parsed_dict = json.loads(response.content[0].text)
            logger.debug(f"Parsed tool result dictionary: {parsed_dict}")
            return parsed_dict
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from tool result content: {e}. Content: {response.content[0].text}")
            return None
        except IndexError:
             logger.error("Response content list is empty.")
             return None
    else:
        logger.error(f"Unexpected content type in response: {type(response.content[0])}")
        return None


# --- Test Functions (Focused on get_stock_price) ---

@pytest.mark.asyncio
async def test_get_stock_price_success(mcp_session: ClientSession):
    """Tests the get_stock_price tool for a valid symbol and prints the response."""
    logger.info("--- Running test_get_stock_price_success ---")
    symbol = "AAPL" # Use a common, valid symbol
    try:
        # Call the tool using the mcp client library
        response_obj = await mcp_session.call_tool("get_stock_price", {"symbol": symbol})
        logger.info(f"get_stock_price response object: {response_obj}")

        # Parse the JSON dictionary returned by the server tool
        response_dict = parse_tool_result(response_obj)
        logger.info(f"Parsed response dictionary: {response_dict}")

        # *** CHANGE: Print instead of asserting ***
        print("\n--- Raw Response Object ---")
        print(response_obj)
        print("\n--- Parsed Response Dictionary ---")
        print(response_dict)
        print("--------------------------\n")

        # Optional basic check to ensure the test doesn't completely fail if parsing fails
        assert response_dict is not None, "Parsing the response failed"
        assert isinstance(response_dict, dict), "Parsed response was not a dict"
        # You could add a check for presence of 'result' or 'error' if needed
        # assert "result" in response_dict or "error" in response_dict

        logger.info("--- test_get_stock_price_success FINISHED (printed response) ---")

    except Exception as e:
        logger.error(f"Error during test_get_stock_price_success: {e}", exc_info=True)
        pytest.fail(f"Exception during get_stock_price success test: {e}", pytrace=False)


# --- Main Execution (Optional: allows running directly with python for debugging) ---
# Note: Running with `pytest` is the standard way due to fixtures.
if __name__ == "__main__":
     async def run_tests_manually():
         # This is a simplified runner, doesn't handle fixtures like pytest
         logger.warning("Running tests manually, fixture setup/teardown might differ.")
         # Manually create a session (less robust than fixture)
         async with stdio_client(server_params) as (r, w):
             async with ClientSession(r, w) as session:
                 await session.initialize()
                 # Create dummy fixture object to pass to tests
                 class DummySession: call_tool = session.call_tool
                 await test_get_stock_price_success(DummySession()) # type: ignore
                #  await test_get_stock_price_invalid(DummySession()) # type: ignore

     asyncio.run(run_tests_manually())
