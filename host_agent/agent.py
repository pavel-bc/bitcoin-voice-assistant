import logging
import os
from google.adk.agents import Agent # Main ADK Agent class
from google.adk.agents.callback_context import CallbackContext # For callback type hints
from google.adk.tools import ToolContext, BaseTool # For callback type hints
from typing import Optional, Dict, Any # For callback type hints
from google.adk.agents.run_config import RunConfig


# --- Load Environment Variables ---
from dotenv import load_dotenv
# Assumes .env is in the parent directory (project root)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

# --- Import the A2A Client Tool ---
try:
    # Use relative import assuming tools.py is in the same package
    from .tools import stock_a2a_tool
except ImportError:
    logging.critical("Failed to import 'stock_a2a_tool' from '.tools'. Ensure tools.py exists and A2A common library is accessible.")
    stock_a2a_tool = None # Set to None to prevent agent creation failure later

logger = logging.getLogger(__name__)

# --- Model Configuration ---
# IMPORTANT: Use a model ID that supports the Live API for run_live
# Check Google AI Studio or Vertex AI docs for current Live API compatible models
MODEL_ID_LIVE = os.getenv("LIVE_SERVER_MODEL", "gemini-2.0-flash-live-001") # Example, verify availability


# --- Host Agent Definition ---
host_agent = None
if stock_a2a_tool: # Only define if the tool was imported successfully
    host_agent = Agent(
        name="HostAgentLive",
        model=MODEL_ID_LIVE, # Use the Live API compatible model ID
        description="User-facing agent handling voice/text and delegating stock queries via A2A.",
        instruction="You are a friendly financial assistant interacting via voice and text." # If the user says 'Hello' just say 'Hello' back.",
                    "Your primary function is to provide current stock prices. "
                    "When a user asks for the price of a specific stock (e.g., 'price of GOOGL', 'how is MSFT doing?'), "
                    "first identify the stock ticker symbol from their request. "
                    "Then, use the 'call_specialist_stock_agent' tool to get the price information. "
                    "This tool takes the 'symbol' as input. "
                    "Once you receive the result from the tool: "
                    "- If the status is 'success', clearly state the price and currency (e.g., 'Microsoft (MSFT) is currently trading at $150.25 USD.'). "
                    "- If the status is 'error', inform the user politely about the issue (e.g., 'Sorry, I couldn't retrieve the price for that symbol right now.'). "
                    "Handle other conversational turns naturally.",
        # Provide the A2A client tool
        tools=[stock_a2a_tool],
    )
    logger.info(f"ADK Host Agent '{host_agent.name}' created with model '{MODEL_ID_LIVE}'.")
else:
    logger.critical("Host Agent could not be created because the A2A tool ('stock_a2a_tool') failed to load.")
