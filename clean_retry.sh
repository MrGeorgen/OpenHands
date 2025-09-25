#!/bin/bash
# Clean up files before retrying a failed issue

ISSUE_NUM=${1:-22}

echo "Cleaning up for issue #$ISSUE_NUM..."

# Remove output directory for this issue
rm -rf output/issue_${ISSUE_NUM}/

# Remove from processed list so it will be retried
if [ -f .processed_issues.json ]; then
    python3 -c "
import json
data = json.load(open('.processed_issues.json'))
if '$ISSUE_NUM' in data:
    data.remove('$ISSUE_NUM')
    json.dump(data, open('.processed_issues.json', 'w'))
    print('Removed issue #$ISSUE_NUM from processed list')
"
fi

echo "✅ Cleaned up issue #$ISSUE_NUM"
echo "You can now run: python3 poll_and_resolve.py"
