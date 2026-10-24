#!/bin/bash

set -e

DOCKER_DIR="/Users/mathieu/docker"

echo "=== Mise à jour des Docker Compose ==="

for dir in "$DOCKER_DIR"/*/; do

    if [[ -f "$dir/docker-compose.yml" ]]; then
        compose="docker-compose.yml"
    elif [[ -f "$dir/compose.yml" ]]; then
        compose="compose.yml"
    else
        continue
    fi

    echo ""
    echo "→ $(basename "$dir")"

    cd "$dir"

    if grep -qE '^[[:space:]]+build:' "$compose"; then
        echo "  → Image locale détectée"
        echo "  → Mise à jour de l'image de base + rebuild"
        docker compose build --pull
    else
        echo "  → Images Docker : pull"
        docker compose pull
    fi

    echo "  → Démarrage des conteneurs"
    docker compose up -d

done

echo ""
echo "=== Nettoyage des anciennes images ==="
docker image prune -f

echo ""
echo "=== Mise à jour terminée ==="
