# Convenience targets. On Windows without `make`, run the underlying commands
# directly (see README) or use `make` from Git Bash / WSL.

.PHONY: help install dev-install lint format typecheck test cov ingest run \
        milvus-up milvus-down compose-up compose-down eval docker-build

help:
	@echo "install       Install runtime dependencies"
	@echo "dev-install   Install runtime + dev/test/eval dependencies"
	@echo "lint          Run ruff linter"
	@echo "format        Auto-format with ruff"
	@echo "typecheck     Run mypy"
	@echo "test          Run unit tests"
	@echo "cov           Run tests with coverage report"
	@echo "milvus-up     Start Milvus (+etcd/minio) via docker compose"
	@echo "milvus-down   Stop Milvus stack"
	@echo "ingest        Build the vector index from data/"
	@echo "run           Run the API + UI locally (uvicorn --reload)"
	@echo "eval          Run the RAG + RBAC evaluation gate"
	@echo "docker-build  Build the production Docker image"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements-dev.txt

lint:
	ruff check app evaluation scripts tests

format:
	ruff check --fix app evaluation scripts tests
	ruff format app evaluation scripts tests

typecheck:
	mypy app

test:
	pytest

cov:
	pytest --cov=app --cov-report=term-missing --cov-report=xml

milvus-up:
	docker compose up -d etcd minio milvus

milvus-down:
	docker compose down

ingest:
	python -m scripts.ingest

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

eval:
	python -m evaluation.run_eval

docker-build:
	docker build -t finsolve-rbac-chatbot:local .
