"""Send four clearly labeled design previews to the primary LINE account."""
import json
import re
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcv_service.flex import assignment_messages, push_messages
from mcv_service.push_types import classify_push


def main():
    token = None
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and key.strip() == "CHANNEL_ACCESS_TOKEN":
            token = value.strip().strip("\"'")
    with closing(sqlite3.connect((ROOT / "database/main.db").as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT Line_uid FROM user WHERE user_id=?", ("u1",)).fetchone()
    recipient = (row[0] or "").strip() if row else ""
    if not token or not re.fullmatch(r"U[0-9a-fA-F]{32}", recipient):
        raise SystemExit("Missing token or invalid u1 LINE ID. Check .env and run scripts/update_line_user.py.")
    messages = assignment_messages([
        dict(id="preview:sample", course="PREVIEW | Linear Control Systems",
             title="HW 7 - Sample assignment", due=time.time() + 86400, status="ASSIGNED")
    ], "PREVIEW | Due soon", time.time(), kind="deadline_summary",
        note="Design preview only | Last update shown inside the card")
    # Keep Detail visible; preview buttons safely open the real CourseVille homepage.
    action_row = messages[0]["contents"]["contents"][0]["body"]["contents"][2]["contents"][-1]
    action_row["contents"][-1]["action"]["uri"] = "https://www.mycourseville.com/"
    for kind in ("homework", "new_assignment", "deadline_changed"):
        sample = assignment_messages([
            dict(id="preview:sample", course="PREVIEW | Linear Control Systems",
                 title="HW 7 - Sample assignment", due=time.time()+86400, status="ASSIGNED")
        ], "PREVIEW | Homework", time.time(), kind=kind, note="Design preview only")
        card = sample[0]["contents"]["contents"][0]
        button = card["body"]["contents"][2]["contents"][-1]["contents"][-1]
        button["action"]["uri"] = "https://www.mycourseville.com/"
        messages[0]["contents"]["contents"].append(card)
    grouped = {}
    samples = json.loads((ROOT / "scripts/notification_samples.json").read_text(encoding="utf-8"))
    for payload in samples:
        kind = classify_push(payload)
        sample = push_messages(kind, payload)[0]
        card = sample["contents"]["contents"][0]
        card["body"]["contents"].append({"type": "text", "text": "PREVIEW | Historical notification",
            "size": "xs", "color": "#6a7585", "wrap": True, "margin": "lg"})
        grouped.setdefault(kind, []).append(card)
    for kind, cards in grouped.items():
        messages.append({"type": "flex", "altText": "PREVIEW | " + kind,
            "contents": {"type": "carousel", "contents": cards}})
    request = Request("https://api.line.me/v2/bot/message/push",
        data=json.dumps(dict(to=recipient, messages=messages)).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "X-Line-Retry-Key": str(uuid.uuid4())}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            print("LINE accepted thirteen preview cards in five messages. HTTP", response.status)
    except HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8')}") from None
    except (URLError, OSError):
        raise SystemExit("Could not connect to LINE API. Delivery was not confirmed.") from None


if __name__ == "__main__":
    main()
