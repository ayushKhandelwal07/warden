#!/bin/sh
set -e

# Demo repo checkout at the pinned release (blobless clone, a few seconds).
python -c "from warden import config; from warden.ingest.repo import ensure_repo; ensure_repo(config.DEMO_REF)"

# Empty FalkorDB? Build the graph + golden snapshot. Set WARDEN_BOOTSTRAP=0 to skip.
if [ "${WARDEN_BOOTSTRAP:-1}" = "1" ]; then
  python -m warden.ingest.bootstrap
fi

exec uvicorn warden.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
