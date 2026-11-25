"""
tut_brief — Tut's day: leads, replies waiting, posts scheduled, approvals needing her yes.

Read-only. Reads the mirror files Tut's side writes (see docs/tut-link-design.md);
makes no model call and spends no quota.
"""
from core import tut_context as tc

PLUGIN = {
    "name": "tut_brief",
    "description": (
        "Tut's morning brief: how many leads, replies waiting, posts scheduled and "
        "approvals that need her yes, read from the shared Tut state. Use for 'brief me', "
        "'what's my day', 'morning brief', 'what needs my approval'. Read-only: it never "
        "sends, posts or contacts anyone. For a single job's progress use tut_status; "
        "for lead counts only use tut_leads."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "business": {"type": "STRING",
                         "description": "Optional: quantum, maxa, cairo or youtube, to narrow the brief."},
        },
        "required": [],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        biz_in = (parameters or {}).get("business", "")
        business = tc.norm_business(biz_in) if biz_in else ""
        if business == "general":
            business = ""
        today, hours = tc.load_today()
        if not today:
            return (f"{tc.READ_ONLY_MARK} I can't see Tut's state right now — the shared "
                    f"file is missing or unreadable. Say that, and do not guess any numbers.")
        spoken, full = tc.build_brief(today, hours, business)
        n = tc.unpicked_notes()
        extra = f" {n} of her notes are not yet picked up." if n else ""
        if player:
            try:
                player.show_content("Tut — today", full)
                player.write_log(f"JARVIS: {spoken}")
            except Exception:
                pass
        return f"{tc.READ_ONLY_MARK} {spoken}{extra}{tc.freshness(hours)}"
    except Exception as e:
        return f"Sir, the Tut brief failed: {type(e).__name__}. I have no numbers to give."
