#!/bin/bash
set -e

if [ -f /run/secrets/redis__password ]; then
  PASSWORD=$(cat /run/secrets/redis__password)
elif [ -n "$REDIS__PASSWORD"]; then
  PASSWORD = "$REDIS__PASSWORD"
else
  # startup redis w/o password
  exec redis-server
fi

# startup redis w/ password
exec redis-server --requirepass "$PASSWORD"
