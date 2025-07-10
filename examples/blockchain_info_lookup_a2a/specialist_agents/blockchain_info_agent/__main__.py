import os
import logging
import click
from dotenv import load_dotenv

from common_impl.server import A2AServer
from common_impl.types import AgentCard, AgentCapabilities, AgentSkill

from .task_manager import BlockchainInfoTaskManager

# --- Configuration ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path, override=True)

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper(),
                    format='%(asctime)s - %(name)s - %(levelname)s - A2A_SERVER - %(message)s')
logger = logging.getLogger(__name__)

# --- Environment Variable Defaults ---
ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_HOST = os.getenv("BLOCKCHAIN_INFO_AGENT_A2A_SERVER_HOST")
ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_PORT = os.getenv("BLOCKCHAIN_INFO_AGENT_A2A_SERVER_PORT")
ENV_BLOCKCHAIN_MCP_SERVER_PATH = os.getenv("BLOCKCHAIN_MCP_SERVER_PATH")

@click.command()
@click.option("--host", default=ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_HOST, required=not ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_HOST)
@click.option("--port", default=ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_PORT, type=int, required=not ENV_BLOCKCHAIN_INFO_AGENT_A2A_SERVER_PORT)
@click.option("--mcp-server-path", default=ENV_BLOCKCHAIN_MCP_SERVER_PATH, required=not ENV_BLOCKCHAIN_MCP_SERVER_PATH)
def main(host: str, port: int, mcp_server_path: str):
    """Starts the BlockchainInfoAgent A2A Server."""
    logger.info("Starting BlockchainInfoAgent A2A Server...")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  MCP Server Script Path: {mcp_server_path}")

    if not os.path.isabs(mcp_server_path):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        mcp_server_path = os.path.join(project_root, mcp_server_path)
        logger.info(f"Resolved MCP server path to: {mcp_server_path}")
    
    if not os.path.exists(mcp_server_path):
        logger.error(f"Error: MCP server script not found at: '{mcp_server_path}'")
        return

    try:
        capabilities = AgentCapabilities(streaming=False)
        skills = [
            AgentSkill(
                id="get_bitcoin_price_skill",
                name="Get Bitcoin Price",
                description="Retrieves the current price of Bitcoin in major currencies.",
                tags=["blockchain", "bitcoin", "price"],
                examples=["What is the price of Bitcoin?", "BTC price"],
                outputModes=["application/json"]
            ),
            AgentSkill(
                id="get_address_balance_skill",
                name="Get Address Balance",
                description="Retrieves the final balance for a given Bitcoin address.",
                tags=["blockchain", "bitcoin", "balance", "address"],
                examples=["What is the balance of 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa?", "Check balance for 3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"],
                outputModes=["application/json"]
            )
        ]
        
        agent_card = AgentCard(
            name="BlockchainInfoAgent",
            description="Provides Bitcoin price and address balance information.",
            url=f"http://{host}:{port}",
            provider={"organization": "ProjectHorizon"},
            version="1.0.0",
            defaultInputModes=["text/plain"],
            defaultOutputModes=["application/json"],
            capabilities=capabilities,
            skills=skills,
            authentication=None
        )
        logger.info(f"Agent Card created for: {agent_card.name}")

        task_manager = BlockchainInfoTaskManager(mcp_server_script_path=mcp_server_path)
        server = A2AServer(
            agent_card=agent_card,
            task_manager=task_manager,
            host=host,
            port=port,
        )
        logger.info(f"A2A Server configured to listen on {host}:{port}")
        server.start()

    except Exception as e:
        logger.critical(f"An unexpected error occurred during server startup: {e}", exc_info=True)

if __name__ == "__main__":
    main()