"""
README sanitation and extraction routines.
Implements Rule T7 (valid shell commands vs python statements/cd/git clone)
and extracts clean title, tagline, description, features, and code fences.
"""
from __future__ import annotations

import re
from ..schema import check_for_banned_phrases, is_disallowed_span
from .models import CleanedReadme, ReadmeSentence

VALID_CMD_EXECUTABLES = (
    "python", "python3", "pip", "pip3", "npm", "npx", "yarn", "pnpm", "node",
    "cargo", "go", "docker", "docker-compose", "make", "uvicorn", "gunicorn"
)

DEV_TEST_COMMANDS = (
    "pytest", "tox", "make test", "npm test", "yarn test", "cargo test",
    "go test", "ruff", "black", "mypy", "flake8", "git "
)

DISALLOWED_SECTIONS = {
    "news", "changelog", "announcement", "announcements", "release",
    "releases", "update", "updates", "contributing", "testing",
    "development", "license"
}


def classify_section_header(header: str) -> str:
    h = header.lower().strip()
    if re.search(r"\b(news|changelog|announcements?|release\s*notes?|updates?|what'?s\s*new)\b", h):
        return "news"
    if re.search(r"\b(contributing|development|testing|tests|developing)\b", h):
        return "contributing"
    if re.search(r"\b(license|copyright)\b", h):
        return "license"
    if re.search(r"\b(install|installation|setup|getting\s*started)\b", h):
        return "install"
    if re.search(r"\b(usage|quickstart|examples?|how\s*to\s*use|running)\b", h):
        return "usage"
    if re.search(r"\b(features?|overview|highlights|capabilities|approach|about)\b", h):
        return "features"
    if re.search(r"\b(api|reference|documentation)\b", h):
        return "api"
    return "other"


def is_news_or_date_bullet(text: str) -> bool:
    t = text.strip()
    if re.match(r"^\*{0,2}\[?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{4})\b", t, re.I):
        return True
    if re.match(r"^(?:news|update|what'?s new):", t, re.I):
        return True
    return False


def find_exact_line_range(raw_lines: list[str], target_text: str) -> tuple[int, int]:
    """Find the 1-based start and end line range of target_text in raw_lines. Returns (0, 0) if missing."""
    norm_target = " ".join(target_text.split())
    if not norm_target:
        return 0, 0

    for idx, line in enumerate(raw_lines, start=1):
        norm_line = " ".join(line.split())
        if not norm_line:
            continue
        if norm_target in norm_line or (len(norm_line) >= 15 and norm_line in norm_target):
            return idx, idx

    # Multi-line slice search
    target_lines = [l.strip() for l in target_text.splitlines() if l.strip()]
    if target_lines:
        first_line = target_lines[0]
        for idx, line in enumerate(raw_lines, start=1):
            if first_line in line:
                return idx, min(len(raw_lines), idx + len(target_lines) - 1)

    return 0, 0


def is_prose_line(line: str) -> bool:
    """
    Check if a line is genuine prose according to the rules:
    - Skip: badges, link-only rows, HTML, images, headings, tables, code fences.
    - Must have >= 6 words and >= 60% non-link text.
    """
    s = line.strip()
    if not s:
        return False
    if s.startswith("#") or s.startswith("```") or s.startswith("|") or s.startswith("<") or s.startswith("!["):
        return False
    if re.search(r"\[!\[.*?\]\(.*?\)\]", s):  # badge
        return False

    # Check non-link ratio
    non_link = re.sub(r"\[([^\]]+)\]\([^)]+\)", "", s)
    if len(s) == 0:
        return False
    ratio = len(non_link.strip()) / float(len(s))
    if ratio < 0.60:
        return False

    words = s.split()
    if s.endswith(":") or s.lower().startswith("or if you prefer"):
        return False
    return len(words) >= 4


def is_valid_shell_command(cmd: str) -> bool:
    """
    Rule T7: Validate that cmd is a genuine shell invocation.
    Rejects Python statements ('import x', 'from x import'), cd, git clone, dev/test commands.
    """
    c = cmd.strip()
    if not c or c.startswith("#") or c.startswith(">>>") or c.startswith("..."):
        return False
    # Reject python statements
    if c.startswith("import ") or c.startswith("from ") or " import " in c:
        return False
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=", c):  # assignment
        return False
    # Reject navigation and clone commands
    if c.startswith("cd ") or c == "cd":
        return False
    if c.startswith("git clone") or c.startswith("export ") or c.startswith("source "):
        return False

    # Reject dev and test commands (pytest, tox, make test, etc.)
    for dt in DEV_TEST_COMMANDS:
        if c == dt or c.startswith(dt + " "):
            return False

    tokens = c.split()
    if not tokens:
        return False
    first = tokens[0]
    # Check known executable or relative script execution (./script.sh)
    if first.startswith("./") or first.startswith(".\\"):
        return True
    for exe in VALID_CMD_EXECUTABLES:
        if first == exe or first.endswith("/" + exe) or first.endswith("\\" + exe):
            return True
    return False


def clean_readme(raw_text: str | None) -> CleanedReadme:
    """
    Clean raw README content by removing HTML tags, badges, images, and link syntax.
    Classifies sections into {news, install, usage, features, api, contributing, license, other}.
    Excludes news and contributing sections from feeding features, description, or commands.
    """
    if not raw_text or not raw_text.strip():
        return CleanedReadme()

    raw_lines = raw_text.splitlines()

    # 1. Extract title
    title = ""
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_text, re.IGNORECASE | re.DOTALL)
    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

    if not title:
        for line in raw_lines:
            s = line.strip()
            if s.startswith("#") and not s.startswith("##"):
                title = s.lstrip("#").strip()
                break

    if not title:
        for line in raw_lines:
            s = line.strip()
            if not s or s.startswith("<") or s.startswith("[![") or s.startswith("![") or s.startswith("```"):
                continue
            non_link = re.sub(r"\[([^\]]+)\]\([^)]+\)", "", s).strip()
            if len(s) > 0 and len(non_link) / float(len(s)) < 0.60:
                continue
            title = s.lstrip("#").strip()
            break

    # 2. Extract sections & bullet features & prose description sentences & code fences by section
    sections: dict[str, str] = {}
    current_sec = "intro"
    current_sec_kind = "intro"
    sec_lines: list[str] = []
    features: list[str] = []
    feature_sentences: list[ReadmeSentence] = []
    description_sentences: list[ReadmeSentence] = []
    tagline = ""

    all_fences: list[str] = []
    allowed_fences: list[str] = []
    in_fence = False
    fence_buf: list[str] = []

    for line_idx, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()

        # Track code fences line by line to keep section association
        if line.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_buf = []
            else:
                in_fence = False
                fence_text = "\n".join(fence_buf).strip()
                if fence_text:
                    all_fences.append(fence_text)
                    if current_sec_kind not in DISALLOWED_SECTIONS:
                        allowed_fences.append(fence_text)
            continue

        if in_fence:
            fence_buf.append(raw_line)
            continue

        if not line:
            continue

        if line.startswith("##"):
            sections[current_sec] = "\n".join(sec_lines).strip()
            current_sec = line.lstrip("#").strip()
            current_sec_kind = classify_section_header(current_sec)
            sec_lines = []
            continue

        line_no_html = re.sub(r"<[^>]+>", "", line).strip()
        line_no_badges = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", line_no_html).strip()
        if line_no_badges:
            sec_lines.append(line_no_badges)

        # Do NOT extract features or description from news/contributing/license sections
        if current_sec_kind in DISALLOWED_SECTIONS:
            continue

        bullet_m = re.match(r"^[-*+]\s+(.*)", line) or re.match(r"^\d+\.\s+(.*)", line)
        if bullet_m:
            item = bullet_m.group(1).strip()
            if is_news_or_date_bullet(item):
                continue
            item_clean = re.sub(r"<[^>]+>", "", item)
            item_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item_clean)
            item_clean = re.sub(r"[`*]", "", item_clean).strip()
            if len(item_clean.split()) >= 3 and not item_clean.startswith("http"):
                features.append(item_clean)
                feature_sentences.append(ReadmeSentence(text=item_clean, raw_text=line, start_line=line_idx, end_line=line_idx))

        if is_prose_line(line):
            prose_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
            prose_clean = re.sub(r"<[^>]+>", "", prose_clean)
            prose_clean = re.sub(r"[`*]", "", prose_clean).strip()

            raw_sents = re.split(r"(?<=[.!?])\s+", prose_clean)
            for sent in raw_sents:
                sent_clean = sent.strip()
                if len(sent_clean.split()) >= 6 and not is_disallowed_span(sent_clean) and not sent_clean.endswith(":"):
                    rs = ReadmeSentence(text=sent_clean, start_line=line_idx, end_line=line_idx)
                    description_sentences.append(rs)
                    if not tagline and not check_for_banned_phrases(sent_clean):
                        tagline = sent_clean

    sections[current_sec] = "\n".join(sec_lines).strip()

    description = tagline
    if not description and description_sentences:
        description = description_sentences[0].text
    if not description:
        intro_text = sections.get("intro", "")
        intro_lines = [
            l.strip() for l in intro_text.splitlines()
            if l.strip() and l.strip() != title and not l.strip().startswith("#") and not l.strip().startswith("<")
        ]
        if intro_lines:
            description = intro_lines[0]

    # 3. Extract install & usage commands (T7) from allowed sections only
    install_candidates: list[str] = []
    usage_candidates: list[str] = []

    for fence in allowed_fences:
        for fline in fence.splitlines():
            fl = fline.strip()
            if fl.startswith("$ ") or fl.startswith("> "):
                fl = fl[2:].strip()
            if not fl or fl.startswith("#"):
                continue
            if re.search(r"\b(pip|pip3|npm|pnpm|yarn|cargo)\s+install\b", fl) or fl.startswith("conda install"):
                if fl not in install_candidates:
                    install_candidates.append(fl)
            elif is_valid_shell_command(fl):
                if fl not in usage_candidates:
                    usage_candidates.append(fl)

    # T7: Choose ONE install command (pip/npm/yarn/cargo over conda/apt)
    ordered_installs: list[str] = []
    preferred_prefixes = ("pip install", "pip3 install", "npm install", "yarn add", "cargo add", "pnpm install")
    for pref in preferred_prefixes:
        for c in install_candidates:
            if c.startswith(pref) and c not in ordered_installs:
                ordered_installs.append(c)
    for c in install_candidates:
        if c not in ordered_installs:
            ordered_installs.append(c)

    return CleanedReadme(
        title=title,
        tagline=tagline,
        description=description,
        description_sentences=description_sentences,
        features=features,
        feature_sentences=feature_sentences,
        sections=sections,
        code_fences=all_fences,
        install_commands=ordered_installs,
        usage_commands=usage_candidates,
        raw_lines=raw_lines,
    )
