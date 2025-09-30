#!/usr/bin/env python3
import os
import time
import subprocess
import httpx
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from threading import Thread


API_BASE = "https://codeberg.org/api/v1"

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
REPO_ROOT = Path(__file__).resolve().parent
POLL_INTERVAL = 300  # 5 minutes
LABEL_TO_WATCH = "fix-me"  # Change this to your preferred label

# Propagate to subprocess environment
os.environ["LLM_API_KEY"] = LLM_API_KEY
os.environ["LLM_MODEL"] = LLM_MODEL
os.environ["FORGEJO_TOKEN"] = FORGEJO_TOKEN


def sanitize_command(cmd):
    sensitive_flags = {"--token", "--llm-api-key"}
    sanitized_parts = []
    skip_next = False

    for idx, part in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue

        if part in sensitive_flags:
            sanitized_parts.append(part)
            if idx + 1 < len(cmd):
                sanitized_parts.append("***")
                skip_next = True
        elif any(part.startswith(flag + "=") for flag in sensitive_flags):
            flag, _ = part.split("=", 1)
            sanitized_parts.append(f"{flag}=***")
        else:
            sanitized_parts.append(part)

    return " ".join(sanitized_parts)


ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi(value: str) -> str:
    return ANSI_ESCAPE.sub("", value)


def iso_timestamp(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds") + "Z"


def run_logged_command(
    cmd: list[str],
    log_path: str,
    cwd: str,
    env: dict[str, str],
    label: str,
    timeout: float | None,
) -> subprocess.CompletedProcess:
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    start_time = datetime.now()
    sanitized = sanitize_command(cmd)
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    with open(log_path, 'w', encoding='utf-8') as fh:
        fh.write(f"{label}: {sanitized}\n")
        fh.write(f"Started: {iso_timestamp(start_time)}\n")
        fh.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        def consume(stream, prefix, buffer):
            if stream is None:
                return
            for line in stream:
                clean = strip_ansi(line.rstrip('\n'))
                buffer.append(clean + '\n')
                fh.write(f"[{prefix}] {clean}\n")
                fh.flush()

        threads = [
            Thread(target=consume, args=(proc.stdout, 'stdout', stdout_chunks), daemon=True),
            Thread(target=consume, args=(proc.stderr, 'stderr', stderr_chunks), daemon=True),
        ]

        for thread in threads:
            thread.start()

        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            for thread in threads:
                thread.join()
            end_time = datetime.now()
            fh.write(f"Finished: {iso_timestamp(end_time)}\n")
            fh.write("Result: timeout\n")
            fh.flush()
            raise

        for thread in threads:
            thread.join()

        end_time = datetime.now()
        fh.write(f"Finished: {iso_timestamp(end_time)}\n")
        fh.write(f"Duration: {(end_time - start_time).total_seconds():.2f}s\n")
        fh.write(f"Exit code: {returncode}\n")
        fh.flush()

    stdout_text = ''.join(stdout_chunks)
    stderr_text = ''.join(stderr_chunks)
    return subprocess.CompletedProcess(cmd, returncode, stdout_text, stderr_text)


def load_processed():
    try:
        with open(PROCESSED_FILE) as f:
            data = json.load(f)
            if isinstance(data, list):
                return {str(item) for item in data}
            return {str(data)}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"⚠️  Unable to load {PROCESSED_FILE}: {exc}. Starting with empty processed set.")
        return set()


def save_processed(processed):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(sorted(processed), f, indent=2)


def ensure_processed_log_exists(processed):
    processed_path = Path(PROCESSED_FILE)
    if not processed_path.exists():
        save_processed(processed)


def tail_log(log_path: str, max_lines: int = 40, max_chars: int = 4000) -> str:
    try:
        with open(log_path, 'r') as fh:
            lines = fh.readlines()
    except OSError as exc:
        return f"(unable to read log file: {exc})"

    error_markers = (
        "Traceback (most recent call last)",
        "ERROR:",
        "Exception",
    )

    for idx, line in enumerate(lines):
        if any(marker in line for marker in error_markers):
            start = max(0, idx - 5)
            end = min(len(lines), idx + max_lines)
            snippet = ''.join(lines[start:end])
            break
    else:
        snippet = ''.join(lines[-max_lines:])

    if len(snippet) > max_chars:
        snippet = snippet[:max_chars]

    return snippet.strip()


def post_issue_comment(issue_num: str, body: str) -> None:
    url = f"{API_BASE}/repos/{REPO}/issues/{issue_num}/comments"
    headers = {'Authorization': f'token {FORGEJO_TOKEN}'}
    response = httpx.post(url, json={'body': body}, headers=headers, timeout=30)
    response.raise_for_status()

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

def ensure_prerequisites():
    if shutil.which("tmux") is None:
        raise RuntimeError("tmux is required but was not found in PATH. Install it (e.g. apt install tmux) before running.")


def main():
    ensure_prerequisites()
    processed = load_processed()
    ensure_processed_log_exists(processed)
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
                        result = run_logged_command(
                            cmd=cmd,
                            log_path=log_file,
                            cwd=str(REPO_ROOT),
                            env=env,  # Use modified environment with WORKSPACE_BASE
                            label='Command',
                            timeout=None,
                        )

                        if result.returncode == 0:
                            processed.add(issue_num)
                            save_processed(processed)
                            print(f"✅ Successfully processed issue #{issue_num}")

                            # Create PR for the resolved issue
                            print(f"   Creating PR for issue #{issue_num}...")
                            pr_cmd = [
                                'poetry', 'run', 'python', '-m',
                                'openhands.resolver.send_pull_request',
                                '--selected-repo', REPO,
                                '--issue-number', issue_num,
                                '--token', FORGEJO_TOKEN,
                                '--username', 'johba',
                                '--base-domain', 'codeberg.org',
                                '--pr-type', 'ready',  # Create a ready PR (not draft)
                                '--llm-model', 'anthropic/claude-3-5-sonnet-latest',
                                '--llm-api-key', os.environ.get('LLM_API_KEY'),
                                '--output-dir', f'output/issue_{issue_num}'
                            ]

                            pr_log_file = f'output/issue_{issue_num}_pr_log.txt'

                            try:
                                pr_result = run_logged_command(
                                    cmd=pr_cmd,
                                    log_path=pr_log_file,
                                    cwd=str(REPO_ROOT),
                                    env=env,
                                    label='PR Command',
                                    timeout=300,
                                )

                                if pr_result.returncode == 0:
                                    print(f"   ✅ PR created successfully!")
                                    # Extract PR URL from output if available
                                    if 'created:' in pr_result.stdout:
                                        for line in pr_result.stdout.split('\n'):
                                            if 'created:' in line:
                                                print(f"   {line.strip()}")
                                                break
                                else:
                                    print(f"   ⚠️ PR creation failed (exit code: {pr_result.returncode})")
                                    if pr_result.stderr:
                                        print(f"   Error: {pr_result.stderr[:500]}")
                            except subprocess.TimeoutExpired:
                                print(f"   ⚠️ PR creation timed out after 5 minutes")
                            except Exception as e:
                                print(f"   ⚠️ PR creation error: {str(e)}")
                                print(f"   See log: {pr_log_file}")
                        else:
                            print(f"❌ Failed to process issue #{issue_num} (exit code: {result.returncode})")
                            if result.stderr:
                                print(f"   Error (last 1000 chars):")
                                print(f"   {result.stderr[-1000:]}")
                            print(f"   Full log saved to: {log_file}")
                            comment_body = (
                                f"OpenHands attempt failed for issue #{issue_num} with exit code {result.returncode}.\n"
                                f"Log file: `{log_file}`\n\n"
                            )
                            snippet = tail_log(log_file)
                            if snippet:
                                comment_body += f"```\n{snippet}\n```"
                            try:
                                post_issue_comment(issue_num, comment_body)
                                print("   Posted failure summary as issue comment")
                            except Exception as comment_error:
                                print(f"   ⚠️  Failed to post issue comment: {comment_error}")

                    except subprocess.TimeoutExpired:
                        print(f"❌ Timeout processing issue #{issue_num} after 10 minutes")
                        print(f"   This might be a complex issue - check {log_file} for details")
                        comment_body = (
                            f"OpenHands attempt timed out after 10 minutes for issue #{issue_num}.\n"
                            f"Log file: `{log_file}`\n\n"
                        )
                        snippet = tail_log(log_file)
                        if snippet:
                            comment_body += f"```\n{snippet}\n```"
                        try:
                            post_issue_comment(issue_num, comment_body)
                            print("   Posted timeout summary as issue comment")
                        except Exception as comment_error:
                            print(f"   ⚠️  Failed to post issue comment: {comment_error}")
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
