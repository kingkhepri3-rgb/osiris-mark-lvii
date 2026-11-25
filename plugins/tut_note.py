"""
tut_note — Tut's spoken note, decision or price, saved to the shared inbox for Claude.

The ONLY thing in the Tut link that writes. It appends one timestamped line to
~/Tut-Shared/inbox/notes.jsonl and never edits or deletes anything. A price here
is a record that Tut SAID it — not a verified price.
"""
from core import tut_context as tc

PLUGIN = {
    "name": "tut_note",
    "description": (
        "Save something Tut says to the shared Tut inbox so Claude picks it up: a note, a "
        "decision, a price, a task, a question. Use for 'note this', 'tell Claude', "
        "'remember for Tut', 'the price is…', 'I've decided…'. Business facts, prices and "
        "decisions go ONLY here — never into your own memory tool. It saves her words; it "
        "does not send, post or approve anything."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "Her words, as close to verbatim as heard."},
            "kind": {"type": "STRING",
                     "description": "note, decision, price, task, question or approval_claim."},
            "business": {"type": "STRING",
                         "description": "quantum, maxa, cairo, youtube or general. If unclear use general."},
            "corrects": {"type": "STRING",
                         "description": "Only when fixing an earlier note: that note's id."},
        },
        "required": ["text"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        parameters = parameters or {}
        text = str(parameters.get("text") or "").strip()
        kind = str(parameters.get("kind") or "note").strip().lower()
        business = parameters.get("business") or "general"
        ok, res = tc.append_note(text, kind, business, str(parameters.get("corrects") or ""))
        if not ok:
            return f"Sir, I did NOT save that note — {res}. Tell her it was not saved."
        if player:
            try:
                player.write_log(f"JARVIS: Noted for Tut ({kind}): {text[:80]}")
            except Exception:
                pass
        careful = kind in ("price", "decision", "approval_claim")
        ask = (" Read it back to her in one sentence and ask if it is right; if not, call "
               f"tut_note again with the fix and corrects={res}.") if careful else ""
        extra = (" This is only a record that she said it — not a verified price. Do not quote "
                 "it to anyone." if kind == "price" else "")
        if kind == "approval_claim":
            extra = " Logged unverified; the real approval happens only in the control centre."
        return f"Saved for Tut, note {res}: \"{text[:120]}\".{ask}{extra}"
    except Exception as e:
        return f"Sir, I did NOT save that note — {type(e).__name__}. Tell her it was not saved."
