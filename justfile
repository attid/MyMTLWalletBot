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
    docker build -t {{IMAGE_NAME}}:{{tag}} .
    docker tag {{IMAGE_NAME}} ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}
    docker push ghcr.io/montelibero/{{IMAGE_NAME}}:{{tag}}

test:
    uv run pytest