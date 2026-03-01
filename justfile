IMAGE_NAME := "mmwb"

# Default target
default:
    @just --list

# Docker targets
build tag="latest":
    # Build Docker image
    docker build -t {{IMAGE_NAME}}:{{tag}} .

run: test
    # Build and Run Docker container
    docker build -t {{IMAGE_NAME}}:local .
    docker run --rm --network host --env-file .env {{IMAGE_NAME}}:local

shell:
    # Open a shell into the running container
    docker-compose exec {{IMAGE_NAME}} sh

# Cleanup targets


clean-docker:
    # Clean up Docker images and containers
    docker system prune -f
    docker volume prune -f


push-gitdocker tag="latest":
    # Build and push bot image
    docker build --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) -t {{IMAGE_NAME}}:{{tag}} .
    docker tag {{IMAGE_NAME}}:{{tag}} ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
    docker push ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
    # Build and push webapp image
    docker build -f Dockerfile.webapp --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) -t {{IMAGE_NAME}}-webapp:{{tag}} .
    docker tag {{IMAGE_NAME}}-webapp:{{tag}} ghcr.io/montelibero/{{IMAGE_NAME}}-webapp:{{tag}}
    docker push ghcr.io/montelibero/{{IMAGE_NAME}}-webapp:{{tag}}

fmt:
    cd bot && uv run --package mmwb-bot ruff format .

lint:
    cd bot && uv run --package mmwb-bot ruff check .
    cd bot && uv run --package mmwb-bot mypy core

typecheck-full:
    cd bot && uv run --package mmwb-bot mypy .

test:
    cd bot && uv run --package mmwb-bot pytest tests/

test-fast:
    cd bot && uv run --package mmwb-bot pytest tests/core tests/infrastructure tests/other -m "not integration"

test-e2e-smoke:
    cd bot && uv run --package mmwb-bot pytest tests/routers/test_common_start.py tests/routers/test_add_wallet.py tests/routers/test_wallet_setting.py tests/routers/test_send.py tests/routers/test_trade.py tests/routers/test_swap.py tests/routers/test_sign.py tests/routers/test_inout.py -m "not external"

test-external:
    cd bot && uv run --package mmwb-bot pytest tests/external -m external

arch-test:
    uv run python .linters/check_import_boundaries.py
    uv run python .linters/check_docs_contract.py

secret-scan:
    docker run --rm -v "$PWD:/repo" -w /repo zricethezav/gitleaks:v8.24.2 detect --source=. --no-git --redact --config=.gitleaks.toml

metrics:
    uv run python .linters/metrics_snapshot.py

start-task task_id title="":
    uv run python .linters/create_exec_plan.py {{task_id}} --title "{{title}}"

finish-task plan_name:
    uv run python .linters/complete_exec_plan.py {{plan_name}}

check: fmt lint test arch-test

check-fast: lint test-fast arch-test
