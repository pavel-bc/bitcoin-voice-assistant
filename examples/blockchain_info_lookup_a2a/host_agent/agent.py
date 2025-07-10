import logging
import os
import asyncio

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext

from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

try:
    from .tools import delegate_tool, DISCOVERED_SPECIALIST_AGENTS, initialize_specialist_agents_discovery
except ImportError as e:
    logging.critical(f"Failed to import tools for HostAgent: {e}")
    delegate_tool = None
    DISCOVERED_SPECIALIST_AGENTS = {}
    initialize_specialist_agents_discovery = None

logger = logging.getLogger(__name__)
MODEL_ID_LIVE = os.getenv("LIVE_SERVER_MODEL", "gemini-2.0-flash-live-001")

def get_host_agent_instruction() -> str:
    base_instruction = (
        "You are a friendly assistant interacting via voice and text. "
        "Your primary function is to help users with queries about Bitcoin. "
        "You have access to a specialist agent for this. "
        "Based on the user's request, determine if the specialist agent is suitable. "
        "If so, use the 'delegate_task_to_specialist' tool. Provide the specialist's name and the user's full query.\n"
        "If the user asks for the price of Bitcoin (e.g., 'what's the price of BTC?'), delegate to the specialist. "
        "If the user asks for the balance of a Bitcoin address (e.g., 'check the balance of 1A1zP...'), delegate to the specialist, providing the full query. "
        "After the specialist responds:\n"
        "  - If successful, relay the information clearly (e.g., 'The price of Bitcoin is $65,123 USD.' or 'That address has a balance of 5.2 BTC.').\n"
        "  - If there's an error, inform the user politely (e.g., 'Sorry, I couldn't retrieve that information right now.').\n"
        "Handle other conversational turns naturally.\n\n"
        "Available Specialist Agents:\n"
    )
    if not DISCOVERED_SPECIALIST_AGENTS:
        base_instruction += "- None discovered. You must handle all queries yourself if possible, or state you cannot fulfill the request.\n"
    else:
        for name, card in DISCOVERED_SPECIALIST_AGENTS.items():
            description = card.description or "No description provided."
            base_instruction += f"- Name: '{name}', Description: '{description}'\n"
    
    logger.debug(f"Generated HostAgent Instruction:\n{base_instruction}")
    return base_instruction

host_agent: Optional[Agent] = None

async def create_host_agent() -> Optional[Agent]:
    """Asynchronously initializes specialists and creates the HostAgent."""
    global host_agent
    if initialize_specialist_agents_discovery:
        await initialize_specialist_agents_discovery()
    else:
        logger.error("initialize_specialist_agents_discovery function not available.")
        return None

    if not delegate_tool:
        logger.critical("Host Agent could not be created because 'delegate_tool' failed to load.")
        return None

    current_instruction = get_host_agent_instruction()
    host_agent = Agent(
        name="HostAgentLiveDynamic",
        model=MODEL_ID_LIVE,
        description="User-facing agent that delegates to a Bitcoin specialist.",
        instruction=current_instruction,
        tools=[delegate_tool],
    )
    logger.info(f"ADK Host Agent '{host_agent.name}' created with model '{MODEL_ID_LIVE}'.")
    return host_agent