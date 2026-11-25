"""
core/tut_context.py — the one place Osiris touches Tut's shared state.

See docs/tut-link-design.md. Short version:

    ~/Tut-Shared/mirror/   Tut's side writes, Osiris only READS
        rules.md  facts.md  today.json  jobs.json
    ~/Tut-Shared/inbox/    Osiris appends notes.jsonl; Tut's side writes acks.jsonl

Nothing here calls a model, the network, or Qt, and nothing here raises: a
missing or unreadable file is reported in words, never guessed. The folder is
~/Tut-Shared unless the TUT_SHARED environment variable names another.

The tut_* plugins and the connect-time prompt block (main.py) both go through
this module, so there is one implementation of "where is Tut's state" and "how
old is it".
"""
from __future__ import annotations

import difflib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

READ_ONLY_MARK = "[TUT READ-ONLY — speak only these facts, add nothing]"

SYNC_INTERVAL_H = 4          # the control centre syncs every 4 hours
STALE_AFTER_H = 2 * SYNC_INTERVAL_H

RULES_CAP = 1200
FACTS_CAP = 1200
BLOCK_CAP = 3000
NOTE_TEXT_CAP = 1000
NOTE_LINE_CAP = 4000         # bytes; one O_APPEND write stays atomic below this

BUSINESSES = ("quantum", "maxa", "cairo", "youtube", "general")
KINDS = ("note", "decision", "price", "task", "question", "approval_claim")

_BUSINESS_ALIASES = {
    "quantum": "quantum", "quantum solutions": "quantum", "msp": "quantum", "tms": "quantum",
    "maxa": "maxa", "maxa holidays": "maxa", "holidays": "maxa", "travel": "maxa",
    "cairo": "cairo", "createsbycairo": "cairo", "creates by cairo": "cairo",
    "youtube": "youtube", "chrono nexus": "youtube", "tech saga": "youtube",
    "metta loop": "youtube", "channel": "youtube",
    "general": "general", "": "general",
}

# Used ONLY while mirror/rules.md does not exist yet. Once Tut's exporter writes
# that file it wins and this text is never shown — one source, not two.
BUILTIN_RULES = """\
STANDING RULES (built-in until Tut's rules file arrives):
1. Nothing public without Tut's exact go-ahead. Never post, publish, send, schedule or reply publicly.
2. Burmese copy only on her literal word "Approved". You cannot approve it; log a spoken "Approved" with tut_note as an approval_claim, unverified.
3. Never invent prices, availability or confirmations. Not on file = say "that isn't on file".
4. Scout never contacts anyone. Neither do you.
5. Business scope only: Quantum Solutions, Maxa Holidays, CreatesbyCairo, YouTube (Chrono Nexus, Tech Saga, Metta Loop).
6. She uploads long videos from YouTube Studio herself. There is no upload tool.
7. You never edit video, touch Flow, replace Claude, or spend money. No new paid provider or subscription without her approval.
8. Business facts, prices and decisions go ONLY through tut_note — never your own memory tool.
9. Always say how old Tut's state is, and say plainly when it is stale or missing.
10. Never open Facebook, email or any social or mail site or app, and never add monitors for them, unless she asks in that same turn. During briefings do only the briefing."""


# ── paths ────────────────────────────────────────────────────────────────────
def shared_dir() -> Path:
    env = os.environ.get("TUT_SHARED", "").strip()
    return Path(env).expanduser() if env else Path.home() / "Tut-Shared"


def _mirror(name: str) -> Path:
    return shared_dir() / "mirror" / name


def _inbox(name: str) -> Path:
    return shared_dir() / "inbox" / name


# ── safe reads ───────────────────────────────────────────────────────────────
def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def read_json(path: Path) -> Optional[Any]:
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _parse_ts(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def age_hours(data: Any, path: Path) -> Optional[float]:
    """Hours since the state was generated: its own generated_at, else file mtime."""
    ts = _parse_ts(data.get("generated_at")) if isinstance(data, dict) else None
    if ts is None:
        try:
            ts = path.stat().st_mtime
        except OSError:
            return None
    return max(0.0, (time.time() - ts) / 3600.0)


def age_phrase(hours: Optional[float]) -> str:
    if hours is None:
        return "of unknown age"
    if hours < 1:
        return "as of under an hour ago"
    n = int(round(hours))
    if n < 48:
        return f"as of {n} hour{'s' if n != 1 else ''} ago"
    d = int(round(hours / 24))
    return f"as of {d} days ago"


def freshness(hours: Optional[float]) -> str:
    """'' when fresh, else a plain warning to speak."""
    if hours is None:
        return " I can't tell how old this is."
    if hours > STALE_AFTER_H:
        return " This is STALE — older than two syncs — say so."
    return ""


def load_today() -> tuple[Optional[dict], Optional[float]]:
    path = _mirror("today.json")
    data = read_json(path)
    if not isinstance(data, dict):
        return None, None
    return data, age_hours(data, path)


def load_jobs() -> tuple[list[dict], Optional[float]]:
    path = _mirror("jobs.json")
    data = read_json(path)
    if data is None:
        return [], None
    items = data.get("jobs") if isinstance(data, dict) else data
    jobs: list[dict] = []
    if isinstance(items, dict):
        for k, v in items.items():
            if isinstance(v, dict):
                jobs.append({"name": k, **v})
    elif isinstance(items, list):
        jobs = [j for j in items if isinstance(j, dict) and j.get("name")]
    return jobs, age_hours(data, path)


# ── formatting helpers ───────────────────────────────────────────────────────
def norm_business(value: Any) -> str:
    return _BUSINESS_ALIASES.get(str(value or "").strip().lower(), "")


def _count(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, (list, tuple, dict)):
        return len(v)
    return None


def _label(x: Any) -> str:
    if isinstance(x, dict):
        return str(x.get("title") or x.get("name") or x.get("id") or "?")
    return str(x)


def _biz_of(x: Any) -> str:
    return norm_business(x.get("business") or x.get("business_id")) if isinstance(x, dict) else ""


def _filter(items: Any, business: str) -> list:
    if not isinstance(items, list):
        return []
    if not business:
        return items
    return [i for i in items if _biz_of(i) == business]


def digest(today: Optional[dict], hours: Optional[float]) -> str:
    """Four short lines for the connect-time block."""
    if not today:
        return "TODAY: Tut's state is unavailable right now — say so if asked."
    leads = today.get("leads") or {}
    parts = []
    t = _count(leads.get("total"))
    h = _count(leads.get("hot"))
    if t is not None:
        parts.append(f"{t} leads" + (f", {h} hot" if h is not None else ""))
    r = _count((today.get("replies") or {}).get("waiting"))
    if r is not None:
        parts.append(f"{r} replies waiting")
    p = _count((today.get("posts") or {}).get("scheduled"))
    if p is not None:
        parts.append(f"{p} posts scheduled")
    a = _count((today.get("approvals") or {}).get("pending"))
    if a is not None:
        parts.append(f"{a} approvals need her yes")
    body = "; ".join(parts) if parts else "no counts in the file"
    return f"TODAY ({age_phrase(hours)}): {body}.{freshness(hours)}"


def context_block() -> str:
    """The block main.py adds to the Live system prompt at every connect. ≤ BLOCK_CAP."""
    try:
        rules = (read_text(_mirror("rules.md")) or "").strip() or BUILTIN_RULES
        facts = (read_text(_mirror("facts.md")) or "").strip()
        today, hours = load_today()
        parts = ["[TUT LINK — Tut is the boss; you are Osiris, her voice. Read-only except tut_note.]",
                 rules[:RULES_CAP]]
        if facts:
            parts.append("BUSINESS FACTS (only these are on file; anything else: \"that isn't on file\"):\n"
                         + facts[:FACTS_CAP])
        else:
            parts.append("BUSINESS FACTS: none on file yet. Do not state prices or availability.")
        parts.append(digest(today, hours))
        return ("\n\n".join(parts))[:BLOCK_CAP] + "\n"
    except Exception as e:                       # never break a connect
        print(f"[Tut] context block skipped: {type(e).__name__}: {e}")
        return ""


# ── brief / leads / status text ──────────────────────────────────────────────
def build_brief(today: dict, hours: Optional[float], business: str = "") -> tuple[str, str]:
    """(spoken, full). Spoken ≤ 5 short lines; full goes to the HUD panel."""
    leads = today.get("leads") or {}
    hot = _filter(leads.get("hot"), business)
    replies = today.get("replies") or {}
    posts = _filter((today.get("posts") or {}).get("scheduled"), business)
    appr = _filter((today.get("approvals") or {}).get("pending"), business)

    total = _count(leads.get("total")) if not business else \
        _count((leads.get("by_business") or {}).get(business))
    spoken = [f"Tut's state, {age_phrase(hours)}."]
    if total is not None:
        spoken.append(f"Leads: {total}" + (f", {len(hot)} hot." if hot else "."))
    w = _count(replies.get("waiting"))
    if w is not None and not business:
        spoken.append(f"Replies waiting: {w}.")
    # A section the exporter could not supply is "not available", never "0":
    # saying zero would be a confirmation nobody gave.
    posts_known = isinstance((today.get("posts") or {}).get("scheduled"), list)
    appr_known = isinstance((today.get("approvals") or {}).get("pending"), list)
    spoken.append(f"Posts scheduled: {len(posts)}." if posts_known
                  else "Posts scheduled: not available.")
    if appr_known:
        spoken.append(f"Approvals needing her yes: {len(appr)}" +
                      (f" — {', '.join(_label(x) for x in appr[:3])}." if appr else "."))
    else:
        spoken.append("Approvals needing her yes: not available.")

    full = ["TUT — TODAY" + (f" ({business})" if business else ""), age_phrase(hours), ""]
    if total is not None:
        full.append(f"Leads: {total}")
    for x in hot:
        full.append(f"  HOT: {_label(x)}")
    if w is not None and not business:
        old = replies.get("oldest_age_h")
        full.append(f"Replies waiting: {w}" + (f" (oldest {old} h)" if old is not None else ""))
    full.append(f"Posts scheduled: {len(posts)}" if posts_known else "Posts scheduled: not available")
    for x in posts[:8]:
        when = x.get("when", "") if isinstance(x, dict) else ""
        full.append(f"  {_label(x)} {when}".rstrip())
    full.append(f"Approvals needing her yes: {len(appr)}" if appr_known
                else "Approvals needing her yes: not available")
    for x in appr[:8]:
        full.append(f"  {_label(x)}")
    return " ".join(spoken), "\n".join(full)


def find_job(query: str, jobs: list[dict]) -> tuple[Optional[dict], list[str]]:
    """(match, ties). A tie returns (None, [names]) so the caller can ask."""
    q = re.sub(r"\s+", " ", (query or "").strip().lower())
    if not q:
        return None, []
    names = {}
    for j in jobs:
        names[str(j["name"]).lower()] = j
        for al in j.get("aliases") or []:
            names[str(al).lower()] = j
    if q in names:
        return names[q], []
    subs = {id(v): v for k, v in names.items() if q in k or k in q}
    if len(subs) == 1:
        return next(iter(subs.values())), []
    if len(subs) > 1:
        return None, sorted({str(v["name"]) for v in subs.values()})
    close = difflib.get_close_matches(q, list(names), n=3, cutoff=0.6)
    uniq = {id(names[c]): names[c] for c in close}
    if len(uniq) == 1:
        return next(iter(uniq.values())), []
    if len(uniq) > 1:
        return None, sorted({str(v["name"]) for v in uniq.values()})
    return None, []


# ── the inbox (the only thing Osiris writes) ─────────────────────────────────
def _last_line(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            lines = f.read().splitlines()
        return lines[-1].decode("utf-8") if lines else ""
    except Exception:
        return ""


def unpicked_notes() -> Optional[int]:
    """Notes not yet acknowledged by Tut's side; None if the inbox can't be read."""
    raw = read_text(_inbox("notes.jsonl"))
    if raw is None:
        return 0 if not _inbox("notes.jsonl").exists() else None
    ids = []
    for ln in raw.splitlines():
        try:
            ids.append(json.loads(ln)["id"])
        except Exception:
            pass
    acked = set()
    for ln in (read_text(_inbox("acks.jsonl")) or "").splitlines():
        try:
            a = json.loads(ln)
            acked.add(a.get("id") or a.get("note_id"))
        except Exception:
            pass
    return sum(1 for i in ids if i not in acked)


def append_note(text: str, kind: str = "note", business: str = "general",
                corrects: str = "") -> tuple[bool, str]:
    """Append one line to inbox/notes.jsonl. Returns (ok, note_id or reason).

    Verified, not assumed: the last line is read back and compared before ok."""
    try:
        text = (text or "").strip()
        if not text:
            return False, "there was nothing to save"
        if len(text) > NOTE_TEXT_CAP:
            return False, f"that is too long to save as one note ({len(text)} characters, limit {NOTE_TEXT_CAP})"
        kind = kind if kind in KINDS else "note"
        biz = norm_business(business) or "general"
        now = datetime.now(timezone.utc)
        nid = now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)
        rec = {"id": nid, "ts": now.isoformat(timespec="seconds"), "kind": kind,
               "business": biz, "text": text, "said_via": "voice",
               "status": "tut-stated-unverified", "source": "osiris"}
        if corrects:
            rec["corrects"] = str(corrects)[:64]
        line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
        if len(line) > NOTE_LINE_CAP:
            return False, "that is too long to save as one note"

        path = _inbox("notes.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            except Exception:
                pass                              # advisory only; O_APPEND still holds
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)

        last = _last_line(path)
        if not last or json.loads(last).get("id") != nid:
            return False, "I wrote it but could not read it back, so I can't confirm it was saved"
        return True, nid
    except Exception as e:
        return False, f"the inbox could not be written ({type(e).__name__})"
