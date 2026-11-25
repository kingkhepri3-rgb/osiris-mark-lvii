"""
tut_leads — how many leads Scout has found, and which are hot. Read-only.

Scout only finds leads; nothing here contacts anyone. Reads the shared Tut state.
"""
from core import tut_context as tc

PLUGIN = {
    "name": "tut_leads",
    "description": (
        "How many leads there are and which are hot, from Tut's shared state (Scout's "
        "leads table). Use for 'how many leads', 'any hot leads', 'travel enquiries'. "
        "Read-only: it cannot contact, email or message any lead, and Scout never does "
        "either. For the whole day's brief use tut_brief."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "business": {"type": "STRING",
                         "description": "Optional: quantum, maxa, cairo or youtube."},
            "track": {"type": "STRING",
                      "description": "Optional lead track, e.g. travel_enquiry."},
        },
        "required": [],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        parameters = parameters or {}
        business = tc.norm_business(parameters.get("business", "")) if parameters.get("business") else ""
        if business == "general":
            business = ""
        track = str(parameters.get("track") or "").strip().lower()

        today, hours = tc.load_today()
        if not today or not isinstance(today.get("leads"), dict):
            return (f"{tc.READ_ONLY_MARK} I can't see the leads right now — the shared Tut "
                    f"state is missing or has no leads section. Say that; give no numbers.")
        leads = today["leads"]

        if track:
            n = tc._count((leads.get("by_track") or {}).get(track))
            if n is None:
                return (f"{tc.READ_ONLY_MARK} The state doesn't break out a '{track}' track, "
                        f"so I can't give that number.")
            total, label = n, f"{track} leads"
        elif business:
            total, label = tc._count((leads.get("by_business") or {}).get(business)), f"{business} leads"
        else:
            total, label = tc._count(leads.get("total")), "leads"

        hot = tc._filter(leads.get("hot"), business)
        if total is None:
            return f"{tc.READ_ONLY_MARK} There is no lead count on file for that."
        text = f"{total} {label}, {age_ok(hours)}."
        if hot:
            text += f" {len(hot)} hot: " + ", ".join(tc._label(x) for x in hot[:5]) + "."
        else:
            text += " None marked hot."
        if player:
            try:
                player.write_log(f"JARVIS: {text}")
            except Exception:
                pass
        return f"{tc.READ_ONLY_MARK} {text}{tc.freshness(hours)}"
    except Exception as e:
        return f"Sir, the leads check failed: {type(e).__name__}. I have no numbers to give."


def age_ok(hours) -> str:
    return tc.age_phrase(hours)
