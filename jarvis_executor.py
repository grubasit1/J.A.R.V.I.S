"""
JARVIS Autonomous Executor v2 — Kiro-level capabilities:
1. Run any shell command (chained, multi-step)
2. Read/write/edit/search files
3. Plan and execute complex tasks independently
4. Self-correct on errors (up to 3 retries)
5. Iterative: read → understand → modify → verify
6. Can grep/search codebase
7. Can edit specific parts of files (not just overwrite)
8. Chains multiple thinking rounds for complex tasks
"""
import os
import re
import subprocess
import json
import time

HOME = os.path.expanduser("~")
EXEC_LOG = os.path.join(HOME, "jarvis_exec_log.md")
MAX_STEPS = 20
MAX_ITERATIONS = 3
TIMEOUT = 90


def log_exec(action, result):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(EXEC_LOG, "a") as f:
        f.write(f"\n[{ts}] {action}\n→ {result[:500]}\n")


def run_cmd(cmd, timeout=TIMEOUT):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=timeout, cwd=HOME)
        out = (r.stdout + r.stderr).strip()
        log_exec(f"CMD: {cmd}", out or "(no output)")
        return {"ok": r.returncode == 0, "output": out or "(no output)"}
    except subprocess.TimeoutExpired:
        log_exec(f"CMD: {cmd}", "TIMEOUT")
        return {"ok": False, "output": "Command timed out"}
    except Exception as e:
        log_exec(f"CMD: {cmd}", str(e))
        return {"ok": False, "output": str(e)}


def write_file(path, content):
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    log_exec(f"WRITE: {path}", f"{len(content)} bytes")
    return {"ok": True, "output": f"Written: {path}"}


def read_file(path, max_chars=5000):
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    with open(path) as f:
        content = f.read(max_chars)
    return {"ok": True, "output": content}


def edit_file(path, old_str, new_str):
    """Replace a specific string in a file — like Kiro's strReplace."""
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    with open(path) as f:
        content = f.read()
    if old_str not in content:
        return {"ok": False, "output": f"String not found in {path}"}
    content = content.replace(old_str, new_str, 1)
    with open(path, "w") as f:
        f.write(content)
    log_exec(f"EDIT: {path}", f"Replaced {len(old_str)} chars with {len(new_str)} chars")
    return {"ok": True, "output": f"Edited: {path}"}


def append_file(path, content):
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(content)
    log_exec(f"APPEND: {path}", f"{len(content)} bytes")
    return {"ok": True, "output": f"Appended to: {path}"}


def search_files(pattern, path=""):
    """Grep for a pattern across files — like Kiro's grep tool."""
    search_path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    try:
        r = subprocess.run(
            f"grep -rn --include='*.py' --include='*.js' --include='*.html' --include='*.json' --include='*.sh' --include='*.md' '{pattern}' {search_path}",
            shell=True, capture_output=True, text=True, timeout=10, cwd=HOME)
        lines = r.stdout.strip().split('\n')[:20]
        return {"ok": True, "output": "\n".join(lines) if lines[0] else "No matches"}
    except:
        return {"ok": False, "output": "Search failed"}


def list_dir(path=""):
    path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    if not os.path.isdir(path):
        return {"ok": False, "output": f"Not a directory: {path}"}
    items = os.listdir(path)
    dirs = sorted([d + "/" for d in items if os.path.isdir(os.path.join(path, d)) and not d.startswith('.')])
    files = sorted([f for f in items if os.path.isfile(os.path.join(path, f)) and not f.startswith('.')])
    return {"ok": True, "output": "\n".join(dirs[:25] + files[:25])}


def execute_plan(plan_json, gemini_client=None, model=None):
    results = []
    for i, step in enumerate(plan_json[:MAX_STEPS]):
        action = step.get("action", "")
        if action == "cmd":
            r = run_cmd(step.get("value", ""))
        elif action == "write":
            r = write_file(step.get("path", ""), step.get("content", ""))
        elif action == "edit":
            r = edit_file(step.get("path", ""), step.get("old", ""), step.get("new", ""))
        elif action == "append":
            r = append_file(step.get("path", ""), step.get("content", ""))
        elif action == "read":
            r = read_file(step.get("path", ""))
        elif action == "search":
            r = search_files(step.get("pattern", ""), step.get("path", ""))
        elif action == "list":
            r = list_dir(step.get("path", ""))
        else:
            r = {"ok": False, "output": f"Unknown action: {action}"}

        results.append({"step": i + 1, "action": action, **r})

        # Self-correct on failure
        if not r["ok"] and gemini_client and model:
            fix = _ask_for_fix(gemini_client, model, step, r["output"])
            if fix:
                fix_r = run_cmd(fix)
                results.append({"step": f"{i+1}-fix", "action": "cmd", **fix_r})

    return results


def _ask_for_fix(client, model, failed_step, error):
    try:
        prompt = (f"A command failed.\nStep: {json.dumps(failed_step)}\nError: {error}\n"
                  f"Give ONE shell command to fix this. ONLY the command, nothing else.")
        r = client.models.generate_content(model=model, contents=prompt)
        fix = r.text.strip().strip('`').strip()
        return fix if len(fix) < 300 and '\n' not in fix else None
    except:
        return None


def autonomous_task(task_description, gemini_client, model):
    """
    Kiro-level autonomous execution. Iterates up to MAX_ITERATIONS times:
    1. Plan steps based on task + context from previous iteration
    2. Execute steps
    3. If verification fails, iterate with error context
    """
    context = ""
    all_results = []

    for iteration in range(MAX_ITERATIONS):
        plan_prompt = f"""You are JARVIS, an autonomous AI coding agent on Linux (like Cursor/Kiro).
Working directory: {HOME}
Task: {task_description}
{"Previous attempt context: " + context if context else ""}

Available actions (JSON array of steps):
- {{"action": "cmd", "value": "<shell command>"}}
- {{"action": "write", "path": "<filepath>", "content": "<file content>"}}
- {{"action": "edit", "path": "<filepath>", "old": "<exact string to find>", "new": "<replacement string>"}}
- {{"action": "append", "path": "<filepath>", "content": "<content>"}}
- {{"action": "read", "path": "<filepath>"}}
- {{"action": "search", "pattern": "<grep pattern>", "path": "<optional dir>"}}
- {{"action": "list", "path": "<directory>"}}

Strategy:
1. READ existing code first before modifying
2. Use EDIT to change specific parts (not overwrite whole files)
3. VERIFY your changes work (run python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)")
4. Use SEARCH to find where things are defined
5. Max {MAX_STEPS} steps per iteration

Output ONLY a JSON array. No markdown, no explanation."""

        try:
            response = gemini_client.models.generate_content(model=model, contents=plan_prompt)
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()
            plan = json.loads(text)
            if not isinstance(plan, list):
                context = "Failed to parse plan. Try simpler steps."
                continue

            log_exec(f"TASK iter{iteration+1}: {task_description}", f"Plan: {len(plan)} steps")
            results = execute_plan(plan, gemini_client, model)
            all_results.extend(results)

            # Check if everything succeeded
            failures = [r for r in results if not r.get("ok")]
            if not failures:
                break  # Success — no need to iterate

            # Build context for next iteration
            context = f"Iteration {iteration+1} had {len(failures)} failures:\n"
            context += "\n".join(f"- Step {f['step']}: {f['output'][:150]}" for f in failures[:5])

        except json.JSONDecodeError:
            context = "JSON parse error. Use simpler output — raw JSON array only, no backticks."
        except Exception as e:
            context = f"Error: {e}"

    # Final summary
    successes = sum(1 for r in all_results if r.get("ok"))
    failures = len(all_results) - successes
    summary = f"Done. {successes}/{len(all_results)} steps succeeded."
    if failures:
        fails = [r for r in all_results if not r.get("ok")]
        summary += " Issues: " + "; ".join(f["output"][:80] for f in fails[:3])
    else:
        # Report last meaningful output
        for r in reversed(all_results):
            if r.get("ok") and r["output"] not in ("(no output)", ""):
                summary += f" Output: {r['output'][:200]}"
                break
    return summary
