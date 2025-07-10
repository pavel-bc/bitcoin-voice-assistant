BASE_DIR = examples/blockchain_info_lookup_a2a

specialist:
	cd $(BASE_DIR) && python -m specialist_agents.blockchain_info_agent

server:
	cd $(BASE_DIR) && python -m app.live_server

webui:
	open http://127.0.0.1:8000

.PHONY: specialist server webui