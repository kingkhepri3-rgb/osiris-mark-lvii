"""
tut_status — where a named job stands (Jensen film, Ep6, Messenger Phase 2, …).

Read-only. Reads the shared jobs list Tut's side writes. No match means "no
record" — it never guesses a status.
"""
from core import tut_context as tc

PLUGIN = {
    "name": "tut_status",
    "description": (
        "State of one named job from Tut's shared jobs list: where it stands, last update, "
        "and what is blocking it. Use for 'status of the Jensen film', 'where is Ep6', "
        "'Messenger Phase 2?'. Read-only. For the whole day use tut_brief."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "job": {"type": "STRING", "description": "The job's name as she says it."},
        },
        "required": ["job"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        query = str((parameters or {}).get("job") or "").strip()
        if not query:
            return "Sir, which job do you mean?"
        jobs, hours = tc.load_jobs()
        if not jobs:
            return (f"{tc.READ_ONLY_MARK} I can't see Tut's job list right now — the shared "
                    f"file is missing or empty. Say that; do not guess a status.")
        job, ties = tc.find_job(query, jobs)
        if ties:
            return f"Sir, '{query}' could mean {' or '.join(ties[:3])}. Ask which one."
        if not job:
            return (f"{tc.READ_ONLY_MARK} There is no record of a job called '{query}'. "
                    f"Say exactly that; do not guess.")
        bits = [f"{job['name']}: {job.get('state') or 'no state recorded'}"]
        if job.get("updated"):
            bits.append(f"last updated {job['updated']}")
        if job.get("blocker"):
            bits.append(f"blocked by {job['blocker']}")
        if job.get("owner"):
            bits.append(f"with {job['owner']}")
        text = "; ".join(bits) + f" ({tc.age_phrase(hours)})."
        if player:
            try:
                player.write_log(f"JARVIS: {text}")
            except Exception:
                pass
        return f"{tc.READ_ONLY_MARK} {text}{tc.freshness(hours)}"
    except Exception as e:
        return f"Sir, the status check failed: {type(e).__name__}. I have no status to give."
