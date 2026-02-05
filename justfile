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

test:
    cd bot && uv run --package mmwb-bot pytest tests/