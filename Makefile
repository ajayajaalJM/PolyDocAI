.PHONY: setup dev test lint backend-test frontend-test backend-lint

setup:
	./scripts/setup.sh

dev:
	./dev.sh

test: backend-test frontend-test

backend-test:
	cd backend && source .venv/bin/activate && pytest -q

frontend-test:
	cd frontend && npm test -- --run

backend-lint:
	cd backend && source .venv/bin/activate && ruff check app tests && black --check app tests

lint: backend-lint
	cd frontend && npm run lint
