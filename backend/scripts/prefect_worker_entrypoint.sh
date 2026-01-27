#!/bin/bash

set -e

POOL_NAME="forecasts"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Starting Prefect worker entrypoint..."
echo "  PREFECT_API_URL: ${PREFECT_API_URL:-NOT SET}"
echo "  Work pool: $POOL_NAME"
echo ""

if [ -z "$PREFECT_API_URL" ]; then
  echo "ERROR: PREFECT_API_URL environment variable is not set"
  exit 1
fi

echo "Waiting for Prefect server at $PREFECT_API_URL..."
retries=0
until python -c "import urllib.request; urllib.request.urlopen('$PREFECT_API_URL/health')" >/dev/null 2>&1; do
  retries=$((retries + 1))
  if [ $retries -ge $MAX_RETRIES ]; then
    echo "ERROR: Prefect server not available after $MAX_RETRIES attempts"
    exit 1
  fi
  echo "  Attempt $retries/$MAX_RETRIES, server not ready, waiting ${RETRY_INTERVAL}s..."
  sleep $RETRY_INTERVAL
done
echo "Prefect server is ready"

echo "Ensuring work pool '$POOL_NAME' exists..."
if prefect work-pool inspect "$POOL_NAME" >/dev/null 2>&1; then
  echo "  Work pool '$POOL_NAME' already exists"
else
  echo "  Creating work pool '$POOL_NAME'..."
  prefect work-pool create "$POOL_NAME" --type process
  echo "  Work pool created"
fi

echo "Deploying flows from prefect.yaml..."
prefect deploy --all
echo "Flows deployed"

echo "Starting Prefect worker for pool '$POOL_NAME'..."
exec prefect worker start --pool "$POOL_NAME"
