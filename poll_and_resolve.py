#!/usr/bin/env python3
import os
import time
import subprocess
import httpx
import json
from datetime import datetime
from pathlib import Path

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set the {name} environment variable before running this script")
    return value


# Configuration
FORGEJO_TOKEN = _require_env("FORGEJO_TOKEN")
LLM_API_KEY = _require_env("LLM_API_KEY")
LLM_MODEL = _require_env("LLM_MODEL")
REPO = "johba/harb"
PROCESSED_FILE = ".processed_issues.json"
POLL_INTERVAL = 300  # 5 minutes
LABEL_TO_WATCH = "fix-me"  # Change this to your preferred label

# Propagate to subprocess environment
os.environ["LLM_API_KEY"] = LLM_API_KEY
os.environ["LLM_MODEL"] = LLM_MODEL
os.environ["FORGEJO_TOKEN"] = FORGEJO_TOKEN

def load_processed():
    try:
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))
    except:
        return set()

def save_processed(processed):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(list(processed), f)

def check_issues():
    """Check for issues with the specified label"""
    headers = {'Authorization': f'token {FORGEJO_TOKEN}'}
    all_issues = []
    page = 1

    while True:
        # First get ALL issues (Forgejo API doesn't support label filtering directly)
        response = httpx.get(
            f'https://codeberg.org/api/v1/repos/{REPO}/issues',
            params={'state': 'open', 'page': str(page), 'limit': '50'},
            headers=headers
        )
        response.raise_for_status()
        issues = response.json()

        if not issues:
            break

        # Filter for issues with the fix-me label
        for issue in issues:
            labels = [label['name'] for label in issue.get('labels', [])]
            if LABEL_TO_WATCH in labels:
                all_issues.append(issue)

        page += 1

        # Forgejo returns less than limit when no more pages
        if len(issues) < 50:
            break

    return all_issues

def estimate_cost(issue_complexity="medium"):
    """Estimate API cost per issue"""
    costs = {
        "gpt-4o": {"simple": 0.30, "medium": 0.75, "complex": 1.50},
        "gpt-4-turbo": {"simple": 0.50, "medium": 1.25, "complex": 2.50},
        "gpt-3.5-turbo": {"simple": 0.05, "medium": 0.15, "complex": 0.30},
        "claude-3-5-sonnet-20241022": {"simple": 0.20, "medium": 0.50, "complex": 1.00},
        "claude-sonnet-4-20250514": {"simple": 0.25, "medium": 0.60, "complex": 1.20},
        "claude-3-opus-20240229": {"simple": 0.40, "medium": 1.00, "complex": 2.00},
        "claude-3-haiku-20240307": {"simple": 0.02, "medium": 0.05, "complex": 0.10}
    }
    model = os.environ["LLM_MODEL"]
    model_key = model.split('/')[-1]
    return costs.get(
        model_key, {"simple": 0.20, "medium": 0.50, "complex": 1.00}
    )[issue_complexity]

def main():
    processed = load_processed()
    workspace_base = Path(os.environ.get("WORKSPACE_BASE") or Path.home() / "workspace")
    workspace_base = workspace_base.expanduser()
    workspace_base.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for issues with label '{LABEL_TO_WATCH}'...")
            issues = check_issues()

            print(f"Found {len(issues)} total issues with '{LABEL_TO_WATCH}' label")

            new_issues = [i for i in issues if str(i['number']) not in processed]

            if new_issues:
                print(f"Found {len(new_issues)} new issue(s) to process")

                for issue in new_issues:
                    issue_num = str(issue['number'])
                    print(f"\n📝 Processing issue #{issue_num}: {issue['title']}")
                    print(f"   Labels: {[l['name'] for l in issue.get('labels', [])]}")
                    print(f"   Estimated cost: ${estimate_cost():.2f}")

                    # Run OpenHands with correct arguments
                    # Set workspace environment variable and disable browser
                    env = os.environ.copy()
                    env['WORKSPACE_BASE'] = str(workspace_base)
                    env['ENABLE_BROWSER'] = 'false'  # Disable browser to avoid /workspace error
                    env['USE_BROWSER'] = 'false'
                    env['PLAYWRIGHT_BROWSERS_PATH'] = os.path.expanduser('~/.cache/ms-playwright')  # Use home dir for browser cache

                    cmd = [
                        'poetry', 'run', 'python', '-m',
                        'openhands.resolver.resolve_issue',
                        '--selected-repo', REPO,
                        '--issue-number', issue_num,
                        '--token', FORGEJO_TOKEN,
                        '--username', 'johba',  # Your Codeberg username
                        '--base-domain', 'codeberg.org',  # Important for Forgejo detection
                        '--llm-model', LLM_MODEL,
                        '--llm-api-key', LLM_API_KEY,
                        '--output-dir', f'output/issue_{issue_num}'
                    ]

                    # Add max-iterations to prevent runaway
                    cmd.extend(['--max-iterations', '30'])

                    # Always use local runtime (no Docker)
                    cmd.extend(['--runtime', 'local'])

                    print(f"   Running command: {' '.join(cmd[:6])}...")

                    # Create log file for this issue
                    log_file = f'output/issue_{issue_num}_log.txt'
                    os.makedirs('output', exist_ok=True)

                    # Run with timeout and better output capture
                    try:
                        result = subprocess.run(
                            cmd,
                            cwd='/home/johba/OpenHands',
                            env=env,  # Use modified environment with WORKSPACE_BASE
                            capture_output=True,
                            text=True,
                            timeout=1800  # No timeout - let it run to completion
                        )

                        # Save full output to log file
                        with open(log_file, 'w') as f:
                            f.write(f"Command: {' '.join(cmd)}\n")
                            f.write(f"Return code: {result.returncode}\n\n")
                            f.write("STDOUT:\n")
                            f.write(result.stdout)
                            f.write("\nSTDERR:\n")
                            f.write(result.stderr)

                        if result.returncode == 0:
                            processed.add(issue_num)
                            save_processed(processed)
                            print(f"✅ Successfully processed issue #{issue_num}")
                            print(f"   A PR should be created soon...")
                        else:
                            print(f"❌ Failed to process issue #{issue_num} (exit code: {result.returncode})")
                            if result.stderr:
                                print(f"   Error (last 1000 chars):")
                                print(f"   {result.stderr[-1000:]}")
                            print(f"   Full log saved to: {log_file}")

                    except subprocess.TimeoutExpired:
                        print(f"❌ Timeout processing issue #{issue_num} after 10 minutes")
                        print(f"   This might be a complex issue - check {log_file} for details")
            else:
                print(f"No new issues to process (already processed: {len(processed)} issues)")

            print(f"\n💤 Sleeping for {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n👋 Stopping polling script")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"Retrying in {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
