import os
import logging
import json
from typing import Union, AsyncIterable, Dict, Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from common_impl.server.task_manager import InMemoryTaskManager
from common_impl.types import (
    SendTaskRequest, SendTaskResponse, Task, TaskState, TaskStatus,
    Artifact, TextPart, DataPart, JSONRPCError,
    SendTaskStreamingRequest, SendTaskStreamingResponse, UnsupportedOperationError, JSONRPCResponse
)

from .agent import create_agent_with_mcp_tools

logger = logging.getLogger(__name__)

class BlockchainInfoTaskManager(InMemoryTaskManager):
    """Handles A2A tasks by running the ADK BlockchainInfoAgent."""

    def __init__(self, mcp_server_script_path: str):
        super().__init__()
        self.mcp_server_script_path = mcp_server_script_path
        logger.info(f"BlockchainInfoTaskManager initialized. Will use MCP server at: {self.mcp_server_script_path}")

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles A2A task by instantiating and running the ADK agent."""
        task_params = request.params
        task_id = task_params.id
        session_id = task_params.sessionId
        input_message = task_params.message

        logger.info(f"A2A Task Mgr: Received task '{task_id}' in session '{session_id}'")

        task = await self.upsert_task(task_params)
        task.status.state = TaskState.WORKING
        await self.update_store(task_id, task.status, None)

        # Determine the user's intent from the message parts.
        # This is a simplified logic. A more robust solution might use an LLM call here.
        user_query = ""
        if input_message.parts:
            for part in input_message.parts:
                if isinstance(part, TextPart) and part.text:
                    user_query = part.text.strip()
                    break
        
        if not user_query:
            task.status.state = TaskState.FAILED
            error_artifact = Artifact(name="error_details", parts=[DataPart(data={"error": "No query provided."})])
            task.artifacts = [error_artifact]
            await self.update_store(task_id, task.status, task.artifacts)
            return SendTaskResponse(id=request.id, result=task)

        # --- Run the ADK Agent ---
        adk_result_dict: Dict[str, Any] = {"error": "ADK agent execution failed."}
        exit_stack = None
        try:
            logger.info(f"A2A Task Mgr: Creating ADK Agent for task '{task_id}'...")
            adk_agent, exit_stack = await create_agent_with_mcp_tools(self.mcp_server_script_path)

            temp_session_service = InMemorySessionService()
            temp_adk_session = temp_session_service.create_session(
                app_name=f"adk_task_{task_id}",
                user_id=f"a2a_user_{session_id}",
                session_id=f"adk_run_{task_id}",
                state={}
            )

            adk_runner = Runner(
                agent=adk_agent,
                app_name=temp_adk_session.app_name,
                session_service=temp_session_service,
            )

            adk_content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])
            logger.info(f"A2A Task Mgr: Running ADK agent for task '{task_id}'...")

            async for event in adk_runner.run_async(
                session_id=temp_adk_session.id,
                user_id=temp_adk_session.user_id,
                new_message=adk_content
            ):
                if event.get_function_responses():
                    for func_resp in event.get_function_responses():
                        try:
                            # The response is now a dictionary, not an object with attributes
                            response_dict = func_resp.response
                            if isinstance(response_dict, dict):
                                adk_result_dict = response_dict
                                logger.info(f"A2A Task Mgr: Successfully captured tool result: {adk_result_dict}")
                            else:
                                # Fallback if the structure is different
                                adk_result_dict = {"error": "Unexpected tool response format."}
                            break # Process first tool response
                        except Exception as e:
                            logger.error(f"Error processing tool response event: {e}", exc_info=True)
                            adk_result_dict = {"error": "Internal error processing specialist response."}
                            break
            
            logger.info(f"A2A Task Mgr: ADK agent run finished for task '{task_id}'.")

        except Exception as adk_err:
            logger.exception(f"A2A Task Mgr: Error during ADK agent execution for task '{task_id}': {adk_err}")
            adk_result_dict = {"error": f"Failed to execute ADK agent: {str(adk_err)}"}
        finally:
            if exit_stack:
                logger.info(f"A2A Task Mgr: Cleaning up MCP connection for task '{task_id}'.")
                await exit_stack.aclose()
                logger.info(f"A2A Task Mgr: MCP connection closed for task '{task_id}'.")

        # --- Process Result and Finalize A2A Task ---
        if "error" not in adk_result_dict:
            task.status.state = TaskState.COMPLETED
            result_artifact = Artifact(name="blockchain_data", parts=[DataPart(data=adk_result_dict)])
            task.artifacts = [result_artifact]
            logger.info(f"A2A Task Mgr: Task '{task_id}' COMPLETED successfully.")
        else:
            task.status.state = TaskState.FAILED
            error_msg = adk_result_dict.get("error", "Unknown error from ADK Agent.")
            logger.error(f"A2A Task Mgr: Task '{task_id}' FAILED. Reason: {error_msg}")
            error_artifact = Artifact(name="error_details", parts=[DataPart(data={"error": error_msg})])
            task.artifacts = [error_artifact]

        await self.update_store(task_id, task.status, task.artifacts)
        return SendTaskResponse(id=request.id, result=task)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> Union[AsyncIterable[SendTaskStreamingResponse], JSONRPCResponse]:
        """Streaming is not supported by this agent."""
        logger.warning(f"A2A Task Manager: Received 'tasks/sendSubscribe', but streaming is not supported.")
        return JSONRPCResponse(
            id=request.id,
            error=UnsupportedOperationError(message="Streaming is not supported by this agent.")
        )