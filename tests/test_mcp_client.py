# live-agent-project/tests/test_mcp_client.py
import asyncio
import json
import os
import sys
import httpx # Use HTTP client
import logging
import uuid # For unique request IDs

# Assuming 'mcp' package installed from PyPI provides types correctly
try:
    from mcp import types as mcp_types
except ImportError:
    print("ERROR: Cannot import 'mcp.types'. Ensure 'mcp' package is installed correctly.")
    sys.exit(1)

# --- Configuration ---
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://localhost:8002/mcp")
# Define the protocol versions the *client* supports/expects
CLIENT_SUPPORTED_MCP_VERSION = "2025-03-26"
JSONRPC_VERSION_LITERAL = "2.0"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)


# --- HTTP MCP Client Helper ---
async def send_mcp_request(
    client: httpx.AsyncClient,
    method: str,
    params: dict | None = None,
    request_id: int | str | None = None # Allow explicit None for notifications
    ) -> dict | None: # Return None for notifications or if no result expected
    """Sends a JSON-RPC request/notification via HTTP POST and returns the parsed result or None."""
    if request_id is None and method.startswith("notifications/"):
        # Construct notification
        request_payload = {
            "jsonrpc": JSONRPC_VERSION_LITERAL,
            "method": method,
        }
        if params is not None:
            request_payload["params"] = params
    elif request_id is not None:
         # Construct request
         request_payload = {
            "jsonrpc": JSONRPC_VERSION_LITERAL,
            "id": request_id,
            "method": method,
        }
         if params is not None:
            request_payload["params"] = params
    else:
        raise ValueError("request_id must be provided for non-notification methods")


    logger.debug(f"Test Client: Sending: {json.dumps(request_payload)}")
    try:
        response = await client.post(MCP_SERVER_URL, json=request_payload, timeout=15.0) # Increased timeout slightly
        logger.debug(f"Test Client: Received Status Code: {response.status_code}")

        # Handle notification responses (HTTP 204 No Content)
        if response.status_code == 204 and method.startswith("notifications/"):
            logger.debug("Test Client: Received HTTP 204 for notification, as expected.")
            return None # No JSON body expected

        response.raise_for_status() # Raise exception for other 4xx/5xx HTTP errors

        # Check if there's content to parse
        if not response.content:
             # This shouldn't happen for successful requests expecting a result
             if not method.startswith("notifications/"):
                 logger.error(f"Test Client: Received empty response body for method '{method}' which expected a result.")
                 raise RuntimeError(f"Empty response body for method '{method}'")
             else:
                 # This case is unlikely given the 204 check above, but handle defensively
                 logger.warning(f"Test Client: Received empty body for notification '{method}', though HTTP 204 is preferred.")
                 return None

        response_data = response.json()
        logger.debug(f"Test Client: Received JSON response: {response_data}")

        # Check for JSON-RPC level errors
        if "error" in response_data:
            err = response_data["error"]
            err_code = err.get('code', 'N/A')
            err_msg = err.get('message', 'Unknown Error')
            err_data = err.get('data')
            logger.error(f"Test Client: JSON-RPC Error received: Code={err_code}, Msg='{err_msg}', Data={err_data}")
            # Raise an exception to signal test failure
            raise RuntimeError(f"JSON-RPC Error {err_code}: {err_msg}")

        # Return result only if it exists (it won't for notifications)
        return response_data.get("result")

    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP Error: {exc.response.status_code} - Body: {exc.response.text}")
        raise
    except httpx.RequestError as exc:
        logger.error(f"HTTP Request Error (e.g., connection refused): {exc}")
        raise
    except json.JSONDecodeError as exc:
         logger.error(f"Failed to decode JSON response: {exc}")
         logger.error(f"Raw response text: {response.text}")
         raise
    except Exception as exc:
        logger.error(f"An unexpected error occurred in send_mcp_request: {exc}", exc_info=True)
        raise

# --- Test Logic ---
async def main():
    test_run_id = str(uuid.uuid4())[:8] # Unique ID for this test run
    logger.info(f"--- Starting MCP Client Test (Run ID: {test_run_id}) ---")
    logger.info(f"Target Server URL: {MCP_SERVER_URL}")

    # Use a context manager for the client for proper cleanup
    async with httpx.AsyncClient() as client:
        try:
            # 1. Initialize
            logger.info("Step 1: Sending 'initialize' request...")
            init_params = {
                "protocolVersion": CLIENT_SUPPORTED_MCP_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "MCPTestClient", "version": "0.2"}
            }
            init_result = await send_mcp_request(client, "initialize", init_params, request_id=f"init-{test_run_id}")
            server_protocol_version = init_result.get('protocolVersion')
            logger.info(f"Initialize Result: Server using protocol: {server_protocol_version}")
            logger.info(f"Server Capabilities: {init_result.get('capabilities')}")
            # Basic validation
            assert server_protocol_version == SUPPORTED_MCP_VERSION, f"Server protocol mismatch: Expected {SUPPORTED_MCP_VERSION}, got {server_protocol_version}"
            assert init_result.get('capabilities', {}).get('tools') is not None, "Server did not report 'tools' capability"
            logger.info("Step 1: Initialize successful.")


            # 2. Send Initialized Notification
            logger.info("\nStep 2: Sending 'initialized' notification...")
            # Request ID must be None for notifications
            await send_mcp_request(client, "notifications/initialized", request_id=None)
            logger.info("Step 2: Initialized notification sent.")


            # 3. List Tools
            logger.info("\nStep 3: Sending 'tools/list' request...")
            tools_result_data = await send_mcp_request(client, "tools/list", request_id=f"list-{test_run_id}")
            tools_result = mcp_types.ListToolsResult.model_validate(tools_result_data) # Validate structure

            logger.info("Available MCP Tools:")
            if not tools_result.tools:
                logger.error("FAIL: No tools returned by server!")
                return
            mcp_tool_name = ""
            for tool in tools_result.tools:
                logger.info(f"- Name: {tool.name}, Desc: {tool.description}")
                # Simple check based on expected tool name
                if tool.name == "get_current_stock_price":
                    mcp_tool_name = tool.name
                    # Validate schema structure (basic)
                    assert tool.inputSchema.get("type") == "object"
                    assert "ticker_symbol" in tool.inputSchema.get("properties", {})
                    assert "ticker_symbol" in tool.inputSchema.get("required", [])
            if not mcp_tool_name:
                logger.error("FAIL: Could not find the expected tool 'get_current_stock_price'.")
                return
            logger.info("Step 3: List Tools successful.")


            # 4. Call Tool (Successful Case)
            ticker_success = "MSFT"
            logger.info(f"\nStep 4: Calling '{mcp_tool_name}' for ticker '{ticker_success}'...")
            call_params_success = {"name": mcp_tool_name, "arguments": {"ticker_symbol": ticker_success}}
            call_result_data = await send_mcp_request(client, "tools/call", call_params_success, request_id=f"call-ok-{test_run_id}")
            call_result_ok = mcp_types.CallToolResult.model_validate(call_result_data)

            logger.info("MCP Tool Result (Success Case):")
            assert not call_result_ok.isError, f"Expected success, but isError was True. Content: {call_result_ok.content}"
            assert call_result_ok.content and isinstance(call_result_ok.content[0], mcp_types.TextContent), "Expected TextContent in result"
            logger.info(f"  Raw Content: {call_result_ok.content[0].text}")
            try:
                parsed_content = json.loads(call_result_ok.content[0].text)
                assert "price" in parsed_content and "currency" in parsed_content and "symbol" in parsed_content, "Missing expected keys in parsed content"
                assert parsed_content["symbol"] == ticker_success, f"Ticker mismatch: Expected {ticker_success}, got {parsed_content['symbol']}"
                logger.info(f"  Parsed Content: {parsed_content}")
            except (json.JSONDecodeError, TypeError):
                logger.error("FAIL: Content was not valid JSON.")
                raise AssertionError("Tool success content was not valid JSON")
            logger.info("Step 4: Call Tool (Success) successful.")


            # 5. Call Tool (Error Case - Invalid Ticker)
            ticker_fail = "INVALIDTICKERXYZ"
            logger.info(f"\nStep 5: Calling '{mcp_tool_name}' for invalid ticker '{ticker_fail}'...")
            call_params_fail = {"name": mcp_tool_name, "arguments": {"ticker_symbol": ticker_fail}}
            call_result_data_fail = await send_mcp_request(client, "tools/call", call_params_fail, request_id=f"call-err-{test_run_id}")
            call_result_fail = mcp_types.CallToolResult.model_validate(call_result_data_fail)

            logger.info("MCP Tool Result (Error Case):")
            assert call_result_fail.isError, f"Expected isError=True for invalid ticker, got False. Content: {call_result_fail.content}"
            assert call_result_fail.content and isinstance(call_result_fail.content[0], mcp_types.TextContent), "Expected TextContent in error result"
            logger.info(f"  Raw Error Content: {call_result_fail.content[0].text}")
            try:
                parsed_error = json.loads(call_result_fail.content[0].text)
                assert "error" in parsed_error, "Error dictionary should contain 'error' key"
                logger.info(f"  Parsed Error Content: {parsed_error}")
                assert "not found" in parsed_error["error"].lower() or "unavailable" in parsed_error["error"].lower(), "Error message doesn't indicate symbol not found"
            except (json.JSONDecodeError, TypeError):
                logger.error("FAIL: Error content was not valid JSON.")
                raise AssertionError("Tool error content was not valid JSON")
            logger.info("Step 5: Call Tool (Error) successful.")

            logger.info("\n--- MCP Client Test Completed Successfully ---")

        except httpx.RequestError as e:
             logger.error(f"\n--- MCP Client Test FAILED: Cannot connect to server at {MCP_SERVER_URL} ---")
             logger.error(f"    Error: {e}")
             logger.error("    Please ensure the MCP server is running and accessible.")
        except RuntimeError as e:
            logger.error(f"\n--- MCP Client Test FAILED: {e} ---")
        except AssertionError as e:
             logger.error(f"\n--- MCP Client Test FAILED: Assertion Error ---")
             logger.error(f"    Details: {e}")
        except Exception as e:
            logger.error(f"\n--- MCP Client Test FAILED: An unexpected error occurred ---", exc_info=True)


# --- Entry Point ---
if __name__ == "__main__":
    asyncio.run(main())