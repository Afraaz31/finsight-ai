#!/bin/sh
# Start FinSight inside the Space: the API first (internal), then the UI on the public port 7860.
set -e

# Saved answers are keyed on the SEC figures file's timestamp; restore the original one so they still match
python -c "import json, os; m = json.load(open('deploy_meta.json')); os.utime('data/financial/metrics.csv', ns=(m['metrics_mtime_ns'], m['metrics_mtime_ns']))"

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# Wait for the API (it loads the embedding model and the search index) before the UI starts
python - <<'EOF'
import time, urllib.request
for _ in range(180):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
        print("FinSight API is ready", flush=True)
        break
    except Exception:
        time.sleep(1)
else:
    print("FinSight API did not answer /health within 3 minutes; starting the UI anyway", flush=True)
EOF

exec streamlit run frontend/app.py --server.port 7860 --server.address 0.0.0.0 --server.headless true
