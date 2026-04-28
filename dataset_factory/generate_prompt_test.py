#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import sys
import time
from pathlib import Path
from textwrap import wrap

DEFAULT_LLM_CHOICE = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
DEFAULT_LLM_PROVIDER = "nebius"
DEFAULT_LLM_KEY = "Nebius Key"
ERROR_PREFIXES = ("Error during chat call:", "Error:")


# ---- core task markers (case-insensitive, tolerant to spaces) ----
START_RE = re.compile(r'^\s*//\s*===\s*CORE_TASK_START\s*===.*$', re.IGNORECASE | re.MULTILINE)
END_RE   = re.compile(r'^\s*//\s*===\s*CORE_TASK_END\s*===.*$',   re.IGNORECASE | re.MULTILINE)

# ---- optional: measurement markers  ----
MEAS_START_RE = re.compile(r'^\s*//\s*===\s*MEASUREMENT_START\s*===.*$', re.IGNORECASE | re.MULTILINE)

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def detect_newline(text: str) -> str:
    if "\r\n" in text and "\n" in text:
        return "\n"
    if "\r\n" in text:
        return "\r\n"
    return "\n"

def prefix_dir_with_prompt(rel_path: str) -> str:

    p = Path(rel_path)
    parts = list(p.parts)
    if not parts:
        return rel_path
    parts[0] = "prompt_" + parts[0]
    return str(Path(*parts))

def extract_context_for_model(full_text: str, start_span: tuple[int, int], end_span: tuple[int, int]) -> tuple[str, str, str]:

    start_line_end = start_span[1]
    end_line_start = end_span[0]

    header = full_text[:start_line_end]
    core = full_text[start_line_end:end_line_start]

    after_end = full_text[end_span[0]:]
    m_meas = MEAS_START_RE.search(after_end)
    if m_meas:
        tail_hint = after_end[:m_meas.start()]
    else:
        tail_hint = after_end[:800]  # small hint only
    return header, core, tail_hint

def make_todo_comment(description: str, newline: str) -> str:

    description = " ".join(description.strip().split())
    if not description:
        description = "Describe the intended core task here."

    prefix_first = "// TODO(core task): "
    prefix_next  = "//   "
    lines = wrap(description, width=92)

    if not lines:
        return prefix_first + newline

    out_lines = [prefix_first + lines[0]]
    for ln in lines[1:]:
        out_lines.append(prefix_next + ln)
    return newline.join(out_lines) + newline

def call_openai_describe(
    core_code: str,
    header: str,
    tail_hint: str,
    *,
    llm_choice: str = DEFAULT_LLM_CHOICE,
    llm_provider: str = DEFAULT_LLM_PROVIDER,
    llm_key: str = DEFAULT_LLM_KEY,
) -> str:
    try:
        from .LLM import LLM_model
    except ImportError:
        from LLM import LLM_model

    try:
        from openai import OpenAI
    except Exception as ex:
        raise RuntimeError(
            "Missing dependency: openai\n"
            "Install with: pip install openai"
        ) from ex

    client = LLM_model(llm_choice, llm_key, provider=llm_provider)

    instructions = (
        "You are given a quantum program snippet. "
        "Write a natural-language description of what the snippet does.\n"
        "Requirements:\n"
        "- Mention the involved objects (e.g., which qubits / classical bits / registers / frames / durations) "
        "and the key parameters (angles, indices, durations, constants).\n"
        "- Do NOT include code, do NOT quote any lines, and do NOT use backticks.\n"
        "- Do NOT describe how to write it in any programming language, and do NOT mention punctuation like brackets/parentheses/semicolons.\n"
        "- It is OK to name operations conceptually (e.g., rotations, entangling operations, delays, measurement), "
        "but keep it as a high-level semantic description.\n"
        "- Keep it concise (2–6 sentences).\n"
    )


    user_input = (
        "Context (declarations and earlier operations, for naming only):\n"
        "-----\n"
        f"{header[-2500:]}\n"
        "-----\n"
        "Core snippet to describe (this is what will be replaced):\n"
        "-----\n"
        f"{core_code.strip()}\n"
        "-----\n"
        "Following context (may help disambiguate intent):\n"
        "-----\n"
        f"{tail_hint[:1200]}\n"
        "-----\n"
        "Now write the description."
    )


    resp = client.generate(user_input,instructions,max_tokens=250)
    if not resp or any(resp.startswith(prefix) for prefix in ERROR_PREFIXES):
        raise RuntimeError(f"LLM description generation failed: {resp!r}")
    return resp
    #generate(self, prompt, system_prompt, max_tokens=200):

def replace_core_blocks(
    full_text: str,
    *,
    llm_choice: str = DEFAULT_LLM_CHOICE,
    llm_provider: str = DEFAULT_LLM_PROVIDER,
    llm_key: str = DEFAULT_LLM_KEY,
) -> tuple[str, int]:

    newline = detect_newline(full_text)
    replaced = 0
    cursor = 0
    out = []

    while True:
        m_start = START_RE.search(full_text, pos=cursor)
        if not m_start:
            out.append(full_text[cursor:])
            break

        m_end = END_RE.search(full_text, pos=m_start.end())
        if not m_end:
            out.append(full_text[cursor:])
            break

        out.append(full_text[cursor:m_start.end()])

        header, core, tail_hint = extract_context_for_model(full_text, m_start.span(), m_end.span())

        desc = call_openai_describe(
            core,
            header,
            tail_hint,
            llm_choice=llm_choice,
            llm_provider=llm_provider,
            llm_key=llm_key,
        )

        out.append(newline)
        out.append(make_todo_comment(desc, newline))
        out.append(newline)

        out.append(full_text[m_end.start():m_end.end()])

        cursor = m_end.end()
        replaced += 1

    return "".join(out), replaced

def process_one_file(
    rel_path: str,
    *,
    llm_choice: str = DEFAULT_LLM_CHOICE,
    llm_provider: str = DEFAULT_LLM_PROVIDER,
    llm_key: str = DEFAULT_LLM_KEY,
) -> tuple[str, str, int]:
    in_path = Path(rel_path)
    text = in_path.read_text(encoding="utf-8")
    new_text, n = replace_core_blocks(
        text,
        llm_choice=llm_choice,
        llm_provider=llm_provider,
        llm_key=llm_key,
    )

    out_rel = prefix_dir_with_prompt(rel_path)
    out_path = Path(out_rel)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_text, encoding="utf-8")

    return rel_path, out_rel, n


def generate_prompt_files(
    file_paths: list[str],
    *,
    max_tries: int = 5,
    sleep_seconds: float = 0.15,
    llm_choice: str = DEFAULT_LLM_CHOICE,
    llm_provider: str = DEFAULT_LLM_PROVIDER,
    llm_key: str = DEFAULT_LLM_KEY,
) -> list[tuple[str, str, int]]:
    results: list[tuple[str, str, int]] = []

    def run_with_retry(fn):
        delay = 1.5
        for attempt in range(1, max_tries + 1):
            try:
                return fn()
            except Exception as ex:
                if attempt == max_tries:
                    raise
                eprint(f"[warn] attempt {attempt}/{max_tries} failed: {ex}")
                time.sleep(delay)
                delay = min(delay * 1.8, 20.0)

    for rel in file_paths:
        if not Path(rel).exists():
            eprint(f"[skip] missing: {rel}")
            continue

        def job():
            return process_one_file(
                rel,
                llm_choice=llm_choice,
                llm_provider=llm_provider,
                llm_key=llm_key,
            )

        src, dst, n_blocks = run_with_retry(job)
        results.append((src, dst, n_blocks))
        if n_blocks > 0:
            eprint(f"[ok] {src} -> {dst} (core blocks: {n_blocks})")
        else:
            eprint(f"[ok] {src} -> {dst} (no core block found)")
        time.sleep(sleep_seconds)

    return results

def main():
    index_path = Path("tasks_index.json")
    if not index_path.exists():
        raise FileNotFoundError("tasks_index.json not found in current directory.")

    data = json.loads(index_path.read_text(encoding="utf-8"))

    all_files = []
    for k in ["timing", "classical", "pulse", "complex"]:
        all_files.extend(data.get(k, []))

    results = generate_prompt_files(all_files)
    total = len(results)
    replaced_files = sum(1 for _, _, n_blocks in results if n_blocks > 0)
    total_blocks = sum(n_blocks for _, _, n_blocks in results)

    eprint(f"\nDone. processed_files={total} replaced_files={replaced_files} total_core_blocks={total_blocks}")

if __name__ == "__main__":
    main()
