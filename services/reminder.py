from __future__ import annotations
import os, json
from pathlib import Path
from datetime import datetime, timedelta
import schedule, time

DATA_DIR = Path("data")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

def _post_discord(msg: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests  # already in reqs
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
    except Exception:
        pass

def scan_and_notify() -> None:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    for day_dir in DATA_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        for digest_path in sorted(day_dir.glob("PRE-CLEANED-*digest.json")):
            try:
                obj = json.loads(digest_path.read_text())
            except Exception:
                continue
            for p in obj.get("story_packets", []):
                exp = p.get("explainer", {})
                req = exp.get("required", False)
                status = exp.get("status", "missing")
                merged_at = p.get("merged_at")
                if not (req and status == "missing" and merged_at):
                    continue
                try:
                    merged_dt = datetime.fromisoformat(merged_at.replace("Z","+00:00"))
                except Exception:
                    continue
                if merged_dt < cutoff:
                    _post_discord(f"⏰ Reminder: `{p.get('id')}` **{p.get('title_human','Story')}** still needs an explainer. Try `/record_start {p.get('id')}`.")
                    
def run_forever():
    schedule.every(30).minutes.do(scan_and_notify)
    while True:
        schedule.run_pending()
        time.sleep(10)

if __name__ == "__main__":
    run_forever()
