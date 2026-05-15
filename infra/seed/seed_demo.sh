#!/usr/bin/env bash
# RADA demo seed runner. DEV ONLY.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
echo "Seeding demo data from $here/demo_data.sql"
docker compose exec -T postgres psql -U rada -d pc_monitor -v ON_ERROR_STOP=1 < "$here/demo_data.sql"
echo "Seed OK."
