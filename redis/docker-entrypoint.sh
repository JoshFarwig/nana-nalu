#!/bin/sh
set -e

# TODO: refactor to use secret rather than env var

if [ -f /run/secrets/redis__password ]; then
  PASSWORD=$(cat /run/secrets/redis__password)
elif [ -n "$REDIS__PASSWORD" ]; then
  PASSWORD="$REDIS__PASSWORD"
else
  # startup redis with out password
  echo "starting up redis server without password"
  exec redis-server
fi

# startup redis with password
echo "starting up redis server with password"
exec redis-server --requirepass "$PASSWORD"
