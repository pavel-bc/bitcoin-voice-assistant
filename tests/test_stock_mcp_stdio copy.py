# tests/test_stock_mcp_stdio.py

import asyncio
import json
import sys
import os
import pathlib
import logging

# Basic logging setup for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - TEST_CLIENT - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions for MCP Communication ---

async def send_mcp_request(process, request_data):
    """Sends a JSON MCP request to the process stdin and returns the request ID used."""
    try:
        # Ensure params is a dictionary if omitted in simple calls
        if "params" not in request_data:
            request_data["params"] = {}
        # Add jsonrpc version and ensure id exists
        if "jsonrpc" not in request_data:
            request_data["jsonrpc"] = "2.0"
        if "id" not in request_data:
             # Using a simple counter for unique IDs in a test run
            if not hasattr(send_mcp_request, "counter"):
                send_mcp_request.counter = 0
            send_mcp_request.counter += 1
            request_data["id"] = f"test-{send_mcp_request.counter}"

        request_json = json.dumps(request_data) + '\n' # MCP often uses newline delimited JSON
        logger.info(f"Sending Request: {request_json.strip()}")
        process.stdin.write(request_json.encode('utf-8'))
        await process.stdin.drain()
        return request_data["id"] # Return the ID used
    except ProcessLookupError:
        logger.error("Error sending request: Server process already terminated.")
        return None
    except BrokenPipeError:
         logger.error("Error sending request: Broken pipe. Server process likely terminated.")
         return None
    except Exception as e:
        logger.error(f"Error sending request: {e}")
        return None

async def read_mcp_response(process):
    """Reads and parses a JSON MCP response from the process stdout."""
    try:
        response_bytes = await process.stdout.readline()
        if not response_bytes:
            logger.warning("Received no response from server (EOF).")
            return None
        response_json = response_bytes.decode('utf-8').strip()
        logger.info(f"Received Response: {response_json}")
        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response: {response_json}")
            return {"error": {"code": -32700, "message": "Parse error", "data": response_json}}
    except Exception as e:
        logger.error(f"Error reading response: {e}")
        return None

# Task to monitor stderr continuously
async def log_stderr(stderr):
    """Reads and logs lines from the server's stderr stream."""
    while True:
        try:
            line = await stderr.readline()
            if not line:
                logger.info("Stderr stream ended.")
                break
            logger.warning(f"SERVER_STDERR: {line.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")
            break

async def run_server_test():
    """Main function to run the server and test its tools via stdio."""
    process = None # Initialize process variable
    stderr_task = None
    response_task = None
    success_flag = False # Track overall test success

    try:
        # --- Determine Paths ---
        test_script_path = pathlib.Path(__file__).resolve()
        tests_dir = test_script_path.parent
        project_root = tests_dir.parent
        server_script_path = project_root / "mcp_servers" / "stock_mcp_server" / "server.py"

        if not server_script_path.is_file():
            logger.error(f"Server script not found at expected path: {server_script_path}")
            return False # Indicate test failure
        logger.info(f"Found server script at: {server_script_path}")

        # --- Start Server Subprocess ---
        logger.info("Starting server process...")
        process = await asyncio.create_subprocess_exec(
            sys.executable, # Use the same Python interpreter running this test script
            str(server_script_path), # Convert Path object to string for the command
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_root # Set working directory for the server process
        )
        logger.info(f"Server process started (PID: {process.pid}).")

        # Start monitoring stderr immediately
        stderr_task = asyncio.create_task(log_stderr(process.stderr))

        logger.info("Waiting briefly for server initialization...")
        await asyncio.sleep(2) # Allow initialization time

        # --- Test 1: get_stock_price (Success Case) ---
        logger.info("--- Test 1: Calling get_stock_price (GOOG) ---")
        request_id_1 = await send_mcp_request(process, {
            # NOTE: FastMCP tools are invoked via 'tools/call' method
            "method": "tools/call",
            "params": {
                 "name": "get_stock_price", # Tool name
                 "args": {"symbol": "GOOG"} # Arguments for the tool
                 }
            # ID and jsonrpc added by helper
        })
        if not request_id_1: return False # Stop if sending failed

        logger.info(f"Waiting for response to request {request_id_1}...")
        try:
             response_task = asyncio.create_task(read_mcp_response(process))
             await asyncio.wait_for(response_task, timeout=20.0) # Timeout for tool response
             response_1 = response_task.result()
        except asyncio.TimeoutError:
             logger.error("!!! Test 1 Failed: Timeout waiting for server response. !!!")
             if process.returncode is not None:
                 logger.error(f"Server process exited prematurely with code {process.returncode}. Check STDERR logs.")
             raise
        except Exception as e:
             logger.error(f"!!! Test 1 Failed: Error waiting for/reading response: {e} !!!")
             raise

        # Basic Assertions for Test 1
        assert response_1 is not None, "Test 1 Failed: No response received (but no timeout)"
        assert response_1.get("id") == request_id_1, f"Test 1 Failed: ID mismatch (Expected {request_id_1}, Got {response_1.get('id')})"
        # Check for result within the 'result' field from the server's tool function
        assert "result" in response_1, f"Test 1 Failed: Top-level 'result' key missing. Response: {response_1}"
        assert "result" in response_1["result"], f"Test 1 Failed: Nested 'result' key missing. Error: {response_1.get('error', response_1['result'].get('error'))}"
        tool_result = response_1["result"]["result"] # The actual return value of the tool
        assert isinstance(tool_result, dict), "Test 1 Failed: Tool result is not a dictionary"
        assert tool_result.get("symbol") == "GOOG", "Test 1 Failed: Symbol in tool result is incorrect"
        assert "price" in tool_result, "Test 1 Failed: 'price' missing in tool result"
        logger.info("--- Test 1 Passed ---")


        # --- Test 2: get_stock_price (Failure Case - Invalid Symbol) ---
        logger.info("--- Test 2: Calling get_stock_price (INVALID_SYMBOL) ---")
        request_id_2 = await send_mcp_request(process, {
            "method": "tools/call",
            "params": {
                "name": "get_stock_price",
                "args": {"symbol": "INVALID_SYMBOL"}
                }
        })
        if not request_id_2: return False

        logger.info(f"Waiting for response to request {request_id_2}...")
        try:
            response_task = asyncio.create_task(read_mcp_response(process))
            await asyncio.wait_for(response_task, timeout=15.0)
            response_2 = response_task.result()
        except asyncio.TimeoutError:
             logger.error("!!! Test 2 Failed: Timeout waiting for server error response. !!!")
             raise
        except Exception as e:
             logger.error(f"!!! Test 2 Failed: Error waiting for/reading response: {e} !!!")
             raise

        # Basic Assertions for Test 2
        assert response_2 is not None, "Test 2 Failed: No response received"
        assert response_2.get("id") == request_id_2, f"Test 2 Failed: ID mismatch"
        # Expect the error *within* the 'result' field if the tool executed and returned an error dict
        # OR in the top-level 'error' field if FastMCP caught it earlier
        assert "result" in response_2 or "error" in response_2, "Test 2 Failed: Neither 'result' nor 'error' key found"
        if "result" in response_2:
            assert "error" in response_2["result"], "Test 2 Failed: 'error' key missing in result for invalid symbol"
        logger.info(f"--- Test 2 Passed (Received expected error structure) ---")


        # --- Test 3: get_stock_history (Example) ---
        logger.info("--- Test 3: Calling get_stock_history (MSFT, 5d) ---")
        request_id_3 = await send_mcp_request(process, {
            "method": "tools/call",
            "params": {
                "name": "get_stock_history",
                "args": {"symbol": "MSFT", "period": "5d"}
                }
        })
        if not request_id_3: return False

        logger.info(f"Waiting for response to request {request_id_3}...")
        try:
            response_task = asyncio.create_task(read_mcp_response(process))
            await asyncio.wait_for(response_task, timeout=25.0) # History might take longer
            response_3 = response_task.result()
        except asyncio.TimeoutError:
             logger.error("!!! Test 3 Failed: Timeout waiting for history response. !!!")
             raise
        except Exception as e:
             logger.error(f"!!! Test 3 Failed: Error waiting for/reading response: {e} !!!")
             raise

        # Basic Assertions for Test 3
        assert response_3 is not None, "Test 3 Failed: No response"
        assert response_3.get("id") == request_id_3, "Test 3 Failed: ID mismatch"
        assert "result" in response_3, f"Test 3 Failed: Top-level 'result' key missing. Response: {response_3}"
        assert "result" in response_3["result"], f"Test 3 Failed: Nested 'result' key missing. Error: {response_3.get('error', response_3['result'].get('error'))}"
        tool_result_3 = response_3["result"]["result"]
        assert "csv_data" in tool_result_3, "Test 3 Failed: 'csv_data' missing in tool result"
        assert isinstance(tool_result_3["csv_data"], str), "Test 3 Failed: csv_data is not a string"
        assert len(tool_result_3["csv_data"]) > 0, "Test 3 Failed: csv_data is empty"
        logger.info(f"--- Test 3 Passed ---")

        # --- Add more tests here ---

        logger.info("All tests completed successfully.")
        success_flag = True # Mark overall success

    except AssertionError as e:
        logger.error(f"!!! Test Assertion Failed: {e} !!!")
    except asyncio.TimeoutError:
        logger.error("!!! Test Failed due to timeout. !!!")
    except Exception as e:
        logger.error(f"An unexpected error occurred during testing: {e}", exc_info=True) # Log traceback

    finally:
        # --- Cleanup ---
        if stderr_task and not stderr_task.done():
            stderr_task.cancel()
            try: await stderr_task
            except asyncio.CancelledError: logger.info("Stderr listener task cancelled.")

        if process and process.returncode is None:
            logger.info("Terminating server process...")
            try:
                if process.stdin and not process.stdin.is_closing():
                    process.stdin.close()
                    await process.wait()
                else:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                 logger.warning("Server did not terminate gracefully, killing.")
                 process.kill()
            except Exception as e:
                logger.error(f"Error during server termination: {e}")
                if process.returncode is None: process.kill()
            logger.info(f"Server process ended with code {process.returncode}.")
        elif process:
            logger.info(f"Server process already ended with code {process.returncode}.")

    return success_flag # Return overall success status


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting MCP Server Stdio Test Suite...")
    # Ensure the server uses run_in_executor if testing that version
    logger.info("Reminder: Ensure server.py uses run_in_executor for blocking calls.")
    success = asyncio.run(run_server_test())
    logger.info(f"Test Suite Finished. Success: {success}")
    sys.exit(0 if success else 1) # Exit with appropriate status code

