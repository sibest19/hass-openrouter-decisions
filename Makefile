.PHONY: setup lint format test ha ha-stop ha-logs
setup:
	uv sync
	uv run pre-commit install
lint:
	uv run ruff check custom_components tests scripts
	uv run ruff format --check custom_components tests scripts
format:
	uv run ruff check --fix custom_components tests scripts
	uv run ruff format custom_components tests scripts
test:
	uv run pytest
ha:
	docker compose up -d
ha-stop:
	docker compose down
ha-logs:
	docker compose logs -f homeassistant
