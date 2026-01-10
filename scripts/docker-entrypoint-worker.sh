#!/bin/sh
set -e

echo "Worker starting: Applying database migrations first"

if ! alembic -c src/infrastructure/database/alembic.ini upgrade head; then
    echo "Database migration failed! Exiting worker container..."
    exit 1
fi

echo "Migrations deployed successfully, starting taskiq worker"

exec taskiq worker src.infrastructure.taskiq.worker:worker --tasks-pattern src/infrastructure/taskiq/tasks -fsd
