# specialist_agents/stock_info_agent/task_manager.py
import os
import logging
import json
from typing import Union, AsyncIterable # <--- Import these

from common.server.task_manager import InMemoryTaskManager # Use the base class
from common.types import (
    SendTaskRequest, SendTaskResponse, Task, TaskState, TaskStatus,
    Artifact, TextPart, DataPart, JSONRPCError, InternalError,
    SendTaskStreamingRequest, SendTaskStreamingResponse, # <--- Import these
    UnsupportedOperationError, JSONRPCResponse # <--- Import these
)
# Import the MCP client logic function
from .mcp_client_logic import call_mcp_get_stock_price

logger = logging.getLogger(__name__)

class StockInfoTaskManager(InMemoryTaskManager):
    """Handles A2A tasks for retrieving stock information via an MCP server."""

    def __init__(self, mcp_server_script_path: str):
        super().__init__()
        if not mcp_server_script_path or not os.path.isabs(mcp_server_script_path):
             raise ValueError("Configuration Error: An absolute path to the MCP server script is required.")
        if not os.path.exists(mcp_server_script_path):
             raise FileNotFoundError(f"Configuration Error: MCP server script not found at: {mcp_server_script_path}")
        self.mcp_server_script_path = mcp_server_script_path
        logger.info(f"StockInfoTaskManager initialized. Will use MCP server at: {self.mcp_server_script_path}")

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles the primary A2A task: getting stock price."""
        # Log the full incoming request
        logger.info(f"A2A Task Manager: Received Full Request: {request.model_dump_json(indent=2)}")

        task_params = request.params
        task_id = task_params.id
        session_id = task_params.sessionId
        input_message = task_params.message

        logger.info(f"A2A Task Manager: Received task '{task_id}' in session '{session_id}'")

        # 1. Create/Update Task State in memory
        task = await self.upsert_task(task_params) # Inherited method
        task.status.state = TaskState.WORKING
        await self.update_store(task_id, task.status, None) # Update store with WORKING state
        logger.debug(f"A2A Task Manager: Task '{task_id}' state set to WORKING.")

        # 2. Extract Ticker Symbol from Input Message
        symbol = None
        if input_message.parts:
            for part in input_message.parts:
                # Check if it's TextPart before accessing .text
                if isinstance(part, TextPart) and part.text:
                    symbol = part.text.strip()
                    logger.info(f"A2A Task Manager: Extracted symbol '{symbol}' for task '{task_id}'.")
                    break # Use the first text part found

        if not symbol:
            logger.error(f"A2A Task Manager: No ticker symbol found in request for task '{task_id}'.")
            task.status.state = TaskState.FAILED
            task.status.message = None # Clear any previous message
            error_msg = "Error: Ticker symbol not provided in the request."
            error_artifact = Artifact(name="error_details", parts=[DataPart(data={"error": error_msg})])
            task.artifacts = [error_artifact]
            await self.update_store(task_id, task.status, task.artifacts) # Save FAILED state
            response = SendTaskResponse(id=request.id, result=task)
            logger.info(f"A2A Task Manager: Sending Response (Symbol not found): {response.model_dump_json(indent=2)}")
            return response

        # 3. Call MCP Client Logic
        logger.info(f"A2A Task Manager: Calling MCP logic for task '{task_id}', symbol '{symbol}'...")
        try:
            # This function now handles launching/communicating with the MCP server
            mcp_result: dict = await call_mcp_get_stock_price(symbol, self.mcp_server_script_path)
            logger.info(f"A2A Task Manager: Received result from MCP logic for task '{task_id}': {mcp_result}")

            # 4. Process MCP Result and Finalize A2A Task
            if isinstance(mcp_result, dict) and "error" not in mcp_result and "price" in mcp_result:
                task.status.state = TaskState.COMPLETED
                task.status.message = None # Clear any previous message
                # Package successful result as a DataPart artifact
                result_artifact = Artifact(name="stock_price_data", parts=[DataPart(data=mcp_result)])
                task.artifacts = [result_artifact]
                logger.info(f"A2A Task Manager: Task '{task_id}' COMPLETED successfully.")
            else:
                # Handle errors reported either by MCP client logic or the tool itself
                task.status.state = TaskState.FAILED
                task.status.message = None # Clear any previous message
                error_msg = mcp_result.get("error", "Unknown error from MCP tool/interaction.")
                logger.error(f"A2A Task Manager: Task '{task_id}' FAILED. Reason: {error_msg}")
                error_artifact = Artifact(name="error_details", parts=[DataPart(data={"error": error_msg})])
                task.artifacts = [error_artifact]

            # Update the final state in the store
            await self.update_store(task_id, task.status, task.artifacts)

        except Exception as e:
            logger.exception(f"A2A Task Manager: Unhandled exception processing task '{task_id}': {e}")
            task.status.state = TaskState.FAILED
            task.status.message = None
            error_artifact = Artifact(name="error_details", parts=[DataPart(data={"error": f"Internal server error processing task."})])
            task.artifacts = [error_artifact]
            # Update store before potentially returning a JSONRPCError
            await self.update_store(task_id, task.status, task.artifacts)
            # Return a JSONRPCError for severe internal issues
            response = SendTaskResponse(id=request.id, error=InternalError(message=f"Internal processing error for task {task_id}"))
            logger.error(f"A2A Task Manager: Sending JSONRPC Error Response (Unhandled Exception): {response.model_dump_json(indent=2)}")
            return response

        # 5. Return A2A Response containing the final task object
        response = SendTaskResponse(id=request.id, result=task)
        logger.info(f"A2A Task Manager: Sending Final Response: {response.model_dump_json(indent=2)}")
        return response
    
    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> Union[AsyncIterable[SendTaskStreamingResponse], JSONRPCResponse]:
        """Handles streaming requests - intentionally not supported by this agent."""
        task_id = request.params.id if request.params else "unknown"
        logger.warning(f"A2A Task Manager: Received 'tasks/sendSubscribe' request for task {task_id}, but streaming is not supported by this agent.")
        # Log the incoming request
        logger.info(f"A2A Task Manager: Received Full Request (sendSubscribe): {request.model_dump_json(indent=2)}")
        # Return an error compliant with JSON-RPC and A2A types
        response = JSONRPCResponse(
            id=request.id,
            error=UnsupportedOperationError(
                message="Streaming (tasks/sendSubscribe) is not supported by this agent."
            )
        )
        logger.warning(f"A2A Task Manager: Sending UnsupportedOperation Error Response: {response.model_dump_json(indent=2)}")
        return response

    # Override other handlers as needed, e.g., return "Unsupported" error
    # async def on_get_task(...) -> GetTaskResponse: ...
    # async def on_cancel_task(...) -> CancelTaskResponse: ...
    # async def on_send_task_subscribe(...) -> ... : # Return UnsupportedOperationError