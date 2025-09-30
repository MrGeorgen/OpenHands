#!/bin/bash
# Clean up files before retrying a failed issue

set -euo pipefail

# Detect the most recent issue based on output artifacts
_detect_latest_issue() {
    if [ ! -d output ]; then
        return 0
    fi

    local latest
    latest=$(find output -maxdepth 1 -type d -name 'issue_*' -printf '%f\n' 2>/dev/null \
        | sed -E 's/^issue_([0-9]+)$/\1/' | sort -nr | head -n1)

    if [ -n "$latest" ]; then
        echo "$latest"
        return 0
    fi

    latest=$(find output -maxdepth 1 -type f -name 'issue_*_log.txt' -printf '%f\n' 2>/dev/null \
        | sed -E 's/^issue_([0-9]+)_log\.txt$/\1/' | sort -nr | head -n1)

    if [ -n "$latest" ]; then
        echo "$latest"
        return 0
    fi

    return 0
}

ISSUE_NUM="${1:-}"

if [ -z "$ISSUE_NUM" ]; then
    ISSUE_NUM=$(_detect_latest_issue)
fi

if [ -z "$ISSUE_NUM" ]; then
    echo "Unable to determine an issue number automatically." >&2
    echo "Usage: $0 <issue-number>" >&2
    exit 1
fi

echo "Cleaning up for issue #$ISSUE_NUM..."

# Remove output artifacts for this issue
rm -rf "output/issue_${ISSUE_NUM}/"
rm -f "output/issue_${ISSUE_NUM}_log.txt" "output/issue_${ISSUE_NUM}_pr_log.txt"

# Remove from processed list so it will be retried
if [ -f .processed_issues.json ]; then
    python3 - "$ISSUE_NUM" <<'PYCODE'
import json
import sys
from pathlib import Path

issue = sys.argv[1]
path = Path('.processed_issues.json')
with path.open() as fh:
    data = json.load(fh)

if isinstance(data, list):
    if issue in data:
        data.remove(issue)
        with path.open('w') as fh:
            json.dump(data, fh, indent=2)
        print(f"Removed issue #{issue} from processed list")
    else:
        print(f"Issue #{issue} not found in processed list")
else:
    print('Processed issues file not in expected list format; leaving unchanged')
PYCODE
fi

echo "✅ Cleaned up issue #$ISSUE_NUM"
echo "You can now run: python3 poll_and_resolve.py"
