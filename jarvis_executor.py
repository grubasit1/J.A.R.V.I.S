"""
JARVIS Autonomous Executor v3 — Kiro-level capabilities:
1. Structured planning with visible step display
2. Multi-file awareness (reads project structure before editing)
3. Semantic code search (grep + import/dependency tracing)
4. Web search during execution (DuckDuckGo)
5. Context loading (reads related files before modifying)
6. Test running and verification
7. Large file reads (up to 50KB)
8. Self-correcting with iterative refinement (up to 5 retries)
9. Edit specific parts of files (strReplace-style)
10. Multi-file refactoring (rename across files)
"""
import os
import re
import subprocess
import json
import time
import traceback

HOME = os.path.expanduser("~")
EXEC_LOG = os.path.join(HOME, "jarvis_exec_log.md")
PLAN_FILE = "/tmp/jarvis_current_plan.json"
MAX_STEPS = 30
MAX_ITERATIONS = 5
TIMEOUT = 120


# === LOGGING ===

def log_exec(action, result):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(EXEC_LOG, "a") as f:
        f.write(f"\n[{ts}] {action}\n→ {result[:500]}\n")


def update_task_progress(task_name, progress):
    """Push progress to HUD live task display."""
    try:
        tf = "/tmp/jarvis_tasks_live.json"
        tasks = json.load(open(tf)) if os.path.exists(tf) else []
        found = False
        for t in tasks:
            if t.get("name") == task_name:
                t["progress"] = progress
                found = True
        if not found:
            tasks.append({"name": task_name, "progress": progress})
        json.dump(tasks, open(tf, "w"))
    except:
        pass


# === CORE ACTIONS ===

def run_cmd(cmd, timeout=TIMEOUT):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=timeout, cwd=HOME)
        out = (r.stdout + r.stderr).strip()
        log_exec(f"CMD: {cmd}", out or "(no output)")
        return {"ok": r.returncode == 0, "output": out[:3000] or "(no output)"}
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
    return {"ok": True, "output": f"Written: {path} ({len(content)} bytes)"}


def read_file(path, max_chars=50000):
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    try:
        with open(path) as f:
            content = f.read(max_chars)
        return {"ok": True, "output": content}
    except Exception as e:
        return {"ok": False, "output": f"Read error: {e}"}


def edit_file(path, old_str, new_str, replace_all=False):
    """Replace specific string in file — like Kiro's strReplace."""
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    with open(path) as f:
        content = f.read()
    if old_str not in content:
        # Fuzzy match — try stripping whitespace differences
        stripped = content.replace(" ", "").replace("\t", "")
        target = old_str.replace(" ", "").replace("\t", "")
        if target not in stripped:
            return {"ok": False, "output": f"String not found in {path}. File has {len(content)} chars."}
    if replace_all:
        content = content.replace(old_str, new_str)
    else:
        content = content.replace(old_str, new_str, 1)
    with open(path, "w") as f:
        f.write(content)
    log_exec(f"EDIT: {path}", f"Replaced {len(old_str)} → {len(new_str)} chars")
    return {"ok": True, "output": f"Edited: {path}"}


def insert_at_line(path, line_num, content):
    """Insert content at a specific line number."""
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    with open(path) as f:
        lines = f.readlines()
    lines.insert(line_num, content + "\n")
    with open(path, "w") as f:
        f.writelines(lines)
    return {"ok": True, "output": f"Inserted at line {line_num} in {path}"}


def append_file(path, content):
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(content)
    log_exec(f"APPEND: {path}", f"{len(content)} bytes")
    return {"ok": True, "output": f"Appended to: {path}"}


# === CODEBASE AWARENESS ===

def search_files(pattern, path="", include=""):
    """Grep for pattern across codebase — like Kiro's grep tool."""
    search_path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    inc = ""
    if include:
        inc = " ".join(f"--include='{x}'" for x in include.split(","))
    else:
        inc = "--include='*.py' --include='*.js' --include='*.html' --include='*.json' --include='*.sh' --include='*.md' --include='*.css' --include='*.yaml' --include='*.yml' --include='*.toml'"
    try:
        r = subprocess.run(
            f"grep -rn {inc} '{pattern}' {search_path} 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=10, cwd=HOME)
        lines = r.stdout.strip().split('\n')[:30]
        return {"ok": True, "output": "\n".join(lines) if lines[0] else "No matches"}
    except:
        return {"ok": False, "output": "Search failed"}


def find_files(pattern, path=""):
    """Find files by name pattern."""
    search_path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    try:
        r = subprocess.run(
            f"find {search_path} -name '{pattern}' -not -path '*/.*' -not -path '*/__pycache__/*' -not -path '*/node_modules/*' 2>/dev/null | head -30",
            shell=True, capture_output=True, text=True, timeout=10)
        return {"ok": True, "output": r.stdout.strip() or "No files found"}
    except:
        return {"ok": False, "output": "Find failed"}


def list_dir(path="", depth=1):
    """List directory with optional depth."""
    path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    if not os.path.isdir(path):
        return {"ok": False, "output": f"Not a directory: {path}"}
    try:
        r = subprocess.run(
            f"find {path} -maxdepth {depth} -not -path '*/.*' | sort | head -50",
            shell=True, capture_output=True, text=True, timeout=5)
        return {"ok": True, "output": r.stdout.strip()}
    except:
        items = os.listdir(path)
        dirs = sorted([d + "/" for d in items if os.path.isdir(os.path.join(path, d)) and not d.startswith('.')])
        files = sorted([f for f in items if os.path.isfile(os.path.join(path, f)) and not f.startswith('.')])
        return {"ok": True, "output": "\n".join(dirs[:25] + files[:25])}


def find_imports(filepath):
    """Trace imports/dependencies of a Python file."""
    path = filepath if os.path.isabs(filepath) else os.path.join(HOME, filepath)
    if not os.path.exists(path):
        return {"ok": False, "output": f"File not found: {path}"}
    with open(path) as f:
        content = f.read()
    imports = re.findall(r'^(?:from|import)\s+(\S+)', content, re.MULTILINE)
    local_imports = []
    stdlib = []
    for imp in imports:
        mod = imp.split('.')[0]
        local_path = os.path.join(os.path.dirname(path), mod + ".py")
        home_path = os.path.join(HOME, mod + ".py")
        if os.path.exists(local_path):
            local_imports.append(f"{mod} → {local_path}")
        elif os.path.exists(home_path):
            local_imports.append(f"{mod} → {home_path}")
        else:
            stdlib.append(mod)
    out = ""
    if local_imports:
        out += "Local dependencies:\n" + "\n".join(f"  {x}" for x in local_imports)
    if stdlib:
        out += f"\nExternal packages: {', '.join(set(stdlib))}"
    return {"ok": True, "output": out or "No imports found"}


def get_project_structure(path=""):
    """Get a tree overview of the project."""
    search_path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    r = subprocess.run(
        f"find {search_path} -maxdepth 2 -name '*.py' -o -name '*.js' -o -name '*.html' -o -name '*.json' -o -name '*.sh' | grep -v __pycache__ | grep -v node_modules | grep -v '/\\.' | sort",
        shell=True, capture_output=True, text=True, timeout=5, cwd=HOME)
    return {"ok": True, "output": r.stdout.strip()[:3000]}


# === WEB SEARCH ===

def web_search(query):
    """Search the web during execution — like Kiro's web_search."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        out = "\n".join(f"- {r['title']}: {r['body']}" for r in results)
        return {"ok": True, "output": out or "No results"}
    except Exception as e:
        return {"ok": False, "output": f"Search error: {e}"}


# === TESTING ===

def run_tests(path="", cmd=""):
    """Run tests — auto-detect pytest/unittest or use custom command."""
    if cmd:
        return run_cmd(cmd)
    # Auto-detect
    if os.path.exists(os.path.join(HOME, "pytest.ini")) or os.path.exists(os.path.join(HOME, "setup.py")):
        return run_cmd("python3 -m pytest --tb=short -q 2>&1 | tail -20")
    if path:
        return run_cmd(f"python3 -m py_compile {path} && python3 {path}")
    return run_cmd("python3 -m py_compile *.py 2>&1 | head -10")


def verify_syntax(path):
    """Quick syntax check on a Python file."""
    path = path if os.path.isabs(path) else os.path.join(HOME, path)
    return run_cmd(f"python3 -c \"import py_compile; py_compile.compile('{path}', doraise=True)\"")


# === MULTI-FILE REFACTORING ===

def rename_symbol(old_name, new_name, path=""):
    """Rename a function/variable across all files — like Kiro's rename."""
    search_path = path if os.path.isabs(path) else os.path.join(HOME, path or "")
    # Find all occurrences
    find_result = search_files(old_name, search_path)
    if "No matches" in find_result["output"]:
        return {"ok": False, "output": f"'{old_name}' not found in codebase"}
    # Replace in all files
    r = run_cmd(f"find {search_path} -name '*.py' -exec sed -i 's/\\b{old_name}\\b/{new_name}/g' {{}} +")
    if r["ok"]:
        r["output"] = f"Renamed '{old_name}' → '{new_name}' across project"
    return r


# === PLAN EXECUTION ENGINE ===

def execute_plan(plan_json, gemini_client=None, model=None, task_name="Task"):
    results = []
    total = len(plan_json)

    for i, step in enumerate(plan_json[:MAX_STEPS]):
        action = step.get("action", "")
        progress = int((i + 1) / total * 100)
        update_task_progress(task_name, progress)

        if action == "cmd":
            r = run_cmd(step.get("value", ""), timeout=step.get("timeout", TIMEOUT))
        elif action == "write":
            r = write_file(step.get("path", ""), step.get("content", ""))
        elif action == "edit":
            r = edit_file(step.get("path", ""), step.get("old", ""), step.get("new", ""),
                         step.get("replace_all", False))
        elif action == "insert":
            r = insert_at_line(step.get("path", ""), step.get("line", 0), step.get("content", ""))
        elif action == "append":
            r = append_file(step.get("path", ""), step.get("content", ""))
        elif action == "read":
            r = read_file(step.get("path", ""), step.get("max_chars", 50000))
        elif action == "search":
            r = search_files(step.get("pattern", ""), step.get("path", ""),
                           step.get("include", ""))
        elif action == "find":
            r = find_files(step.get("pattern", ""), step.get("path", ""))
        elif action == "list":
            r = list_dir(step.get("path", ""), step.get("depth", 1))
        elif action == "imports":
            r = find_imports(step.get("path", ""))
        elif action == "structure":
            r = get_project_structure(step.get("path", ""))
        elif action == "web_search":
            r = web_search(step.get("query", ""))
        elif action == "test":
            r = run_tests(step.get("path", ""), step.get("cmd", ""))
        elif action == "verify":
            r = verify_syntax(step.get("path", ""))
        elif action == "rename":
            r = rename_symbol(step.get("old", ""), step.get("new", ""), step.get("path", ""))
        else:
            r = {"ok": False, "output": f"Unknown action: {action}"}

        results.append({"step": i + 1, "action": action, **r})

        # Self-correct on failure
        if not r["ok"] and gemini_client and model:
            fix = _ask_for_fix(gemini_client, model, step, r["output"], results)
            if fix:
                fix_r = run_cmd(fix)
                results.append({"step": f"{i+1}-fix", "action": "auto-fix", **fix_r})

    update_task_progress(task_name, 100)
    return results


def _ask_for_fix(client, model, failed_step, error, prev_results):
    try:
        context = "\n".join(f"Step {r['step']}: {r['action']} → {'OK' if r['ok'] else 'FAIL'}"
                           for r in prev_results[-5:])
        prompt = (f"A step failed in an autonomous execution.\n"
                  f"Recent context:\n{context}\n\n"
                  f"Failed step: {json.dumps(failed_step)}\nError: {error}\n\n"
                  f"Give ONE shell command to fix this. ONLY the command, no explanation.")
        r = client.models.generate_content(model=model, contents=prompt)
        fix = r.text.strip().strip('`').strip()
        if fix.startswith("```"):
            fix = fix.split("\n", 1)[-1].rstrip("`").strip()
        return fix if len(fix) < 500 and fix.count('\n') <= 1 else None
    except:
        return None


# === MAIN ENTRY POINT ===

def autonomous_task(task_description, gemini_client, model):
    """
    Kiro-level autonomous execution:
    1. Understand project structure first
    2. Plan with visible steps
    3. Read related files before modifying
    4. Execute with self-correction
    5. Verify changes work
    """
    context = ""
    all_results = []
    task_short = task_description[:40]

    # Phase 0: Gather project context
    structure = get_project_structure()
    project_ctx = structure["output"][:2000] if structure["ok"] else ""

    for iteration in range(MAX_ITERATIONS):
        plan_prompt = f"""You are JARVIS, a Kiro-level autonomous AI coding agent on Linux.
Working directory: {HOME}
Task: {task_description}

PROJECT FILES:
{project_ctx}

{"PREVIOUS ATTEMPT: " + context if context else ""}

AVAILABLE ACTIONS (output as JSON array):
- {{"action": "cmd", "value": "<shell command>"}}
- {{"action": "write", "path": "<filepath>", "content": "<full file content>"}}
- {{"action": "edit", "path": "<filepath>", "old": "<exact string to find>", "new": "<replacement>"}}
- {{"action": "insert", "path": "<filepath>", "line": <number>, "content": "<content>"}}
- {{"action": "append", "path": "<filepath>", "content": "<content>"}}
- {{"action": "read", "path": "<filepath>"}}
- {{"action": "search", "pattern": "<grep regex>", "path": "<optional dir>", "include": "<optional *.py,*.js>"}}
- {{"action": "find", "pattern": "<filename glob>", "path": "<optional dir>"}}
- {{"action": "list", "path": "<directory>", "depth": <1-3>}}
- {{"action": "imports", "path": "<python file>"}}
- {{"action": "structure", "path": "<optional dir>"}}
- {{"action": "web_search", "query": "<search query>"}}
- {{"action": "test", "path": "<optional file>", "cmd": "<optional test command>"}}
- {{"action": "verify", "path": "<python file>"}}
- {{"action": "rename", "old": "<old_name>", "new": "<new_name>", "path": "<optional dir>"}}

STRATEGY (follow this order):
1. READ existing files before modifying them
2. SEARCH for relevant code/definitions to understand context
3. Plan edits that are minimal and precise (use "edit" not "write" for existing files)
4. VERIFY syntax after changes
5. TEST if possible
6. If modifying multiple files, check IMPORTS to understand dependencies

Output ONLY a valid JSON array. No markdown fences, no explanation."""

        try:
            response = gemini_client.models.generate_content(model=model, contents=plan_prompt)
            text = response.text.strip()
            # Extract JSON from possible markdown wrapping
            if "```" in text:
                blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
                text = blocks[0].strip() if blocks else text
            # Clean common issues
            if text.startswith("json"):
                text = text[4:].strip()

            plan = json.loads(text)
            if not isinstance(plan, list):
                context = "Output was not a JSON array. Return ONLY [...steps...]"
                continue

            # Save plan for visibility
            try:
                json.dump({"task": task_description, "iteration": iteration + 1,
                          "steps": [{"action": s.get("action"), "detail": s.get("path") or s.get("value") or s.get("query", "")} for s in plan]},
                         open(PLAN_FILE, "w"), indent=2)
            except:
                pass

            log_exec(f"TASK iter{iteration+1}: {task_description}", f"Plan: {len(plan)} steps")
            results = execute_plan(plan, gemini_client, model, task_short)
            all_results.extend(results)

            # Check success
            failures = [r for r in results if not r.get("ok")]
            if not failures:
                break

            # Build context for retry
            context = f"Iteration {iteration+1} had {len(failures)} failures:\n"
            context += "\n".join(f"- Step {f['step']} ({f['action']}): {f['output'][:200]}" for f in failures[:5])
            # Also include successful reads for context
            reads = [r for r in results if r.get("ok") and r["action"] in ("read", "search", "imports")]
            if reads:
                context += "\n\nContext from reads:\n"
                context += "\n".join(f"- {r['output'][:300]}" for r in reads[:3])

        except json.JSONDecodeError as e:
            context = f"JSON parse error: {e}. Return ONLY a raw JSON array, no markdown."
        except Exception as e:
            context = f"Error: {e}\n{traceback.format_exc()[:300]}"

    # Cleanup task from HUD
    try:
        tf = "/tmp/jarvis_tasks_live.json"
        tasks = json.load(open(tf)) if os.path.exists(tf) else []
        tasks = [t for t in tasks if t.get("name") != task_short]
        json.dump(tasks, open(tf, "w"))
    except:
        pass

    # Summary
    successes = sum(1 for r in all_results if r.get("ok"))
    failures = len(all_results) - successes
    summary = f"Done. {successes}/{len(all_results)} steps succeeded across {min(iteration+1, MAX_ITERATIONS)} iterations."
    if failures:
        fails = [r for r in all_results if not r.get("ok")]
        summary += " Issues: " + "; ".join(f["output"][:80] for f in fails[:3])
    else:
        for r in reversed(all_results):
            if r.get("ok") and r["output"] not in ("(no output)", "") and r["action"] != "read":
                summary += f" Last output: {r['output'][:200]}"
                break
    return summary
