#!/bin/sh
set -e

echo "Scheduler starting: Applying database migrations first"

if ! alembic -c src/infrastructure/database/alembic.ini upgrade head; then
    echo "Database migration failed! Exiting scheduler container..."
    exit 1
fi

echo "Migrations deployed successfully, starting taskiq scheduler"

exec taskiq scheduler src.infrastructure.taskiq.scheduler:scheduler --tasks-pattern src/infrastructure/taskiq/tasks -fsd
