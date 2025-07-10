import asyncio
import os
import sys
import logging
from contextlib import AsyncExitStack

# --- ADK Imports ---
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# --- MCP Client Imports ---
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

# --- Environment Loading ---
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
MODEL = os.getenv('BLOCKCHAIN_INFO_AGENT_MODEL', "gemini-2.0-flash-001")

# --- MCP Tool Loading Function ---
async def get_mcp_tools_async(mcp_server_script_path: str) -> tuple[list, AsyncExitStack]:
    """Connects to the MCP server via stdio and retrieves its tools."""
    logger.info(f"Attempting to connect to MCP server via stdio: {mcp_server_script_path}")
    try:
        connection_params = StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_script_path],
        )
        tools, exit_stack = await MCPToolset.from_server(
            connection_params=connection_params
        )
        logger.info(f"Successfully connected to MCP server and retrieved {len(tools)} tool(s).")
        return tools, exit_stack
    except Exception as e:
        logger.error(f"Failed to connect to MCP server or get tools: {e}", exc_info=True)
        raise

# --- ADK Agent Definition Function ---
async def create_agent_with_mcp_tools(mcp_server_script_path: str) -> tuple[Agent, AsyncExitStack]:
    """Creates the ADK Agent, equipping it with tools from the MCP server."""
    mcp_tools, exit_stack = await get_mcp_tools_async(mcp_server_script_path)

    blockchain_info_agent = Agent(
        name="blockchain_info_agent",
        model=MODEL,
        description="Provides Bitcoin price and address balance information using external tools.",
        instruction="You are an assistant that provides Bitcoin blockchain information. "
                    "If asked for the price of Bitcoin, use the 'get_bitcoin_price' tool. "
                    "If asked for the balance of a specific Bitcoin address, use the 'get_address_balance' tool, passing the address as the 'address' argument. "
                    "The tools return a dictionary with the requested information or an 'error'. "
                    "Relay the information clearly to the user. If a tool returns an error, state that.",
        tools=mcp_tools,
    )
    logger.info(f"ADK Agent '{blockchain_info_agent.name}' created with MCP tools.")
    return blockchain_info_agent, exit_stack