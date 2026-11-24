"""Original burgundy course cards, rendered without string-based JSON substitution."""
import copy
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from .engine import BANGKOK, DAY

ROOT = Path(__file__).parent
HEADER = json.loads((ROOT / "flex_header_template.json").read_text())
BODY = json.loads((ROOT / "flex_body_template.json").read_text())


def replace(value, fields):
    if isinstance(value, dict):
        return {k: replace(v, fields) for k, v in value.items()}
    if isinstance(value, list):
        return [replace(v, fields) for v in value]
    return fields.get(value, value) if isinstance(value, str) else value


def assignment_messages(items, label, now):
    if not items:
        return [{"type": "text", "text": label + "\nNo assignments in this period."}]
    bubbles = []
    for item in items:
        due = item["due"]
        remaining = due - now if due is not None else None
        submitted = item["status"] in ("SUBMITTED", "LATE_SUBMITTED")
        status = "Submitted" if submitted else ("Overdue" if remaining is not None and remaining <= 0 else "Not submitted")
        color = "#188038" if submitted else "#b3261e"
        left = "No deadline" if remaining is None else ("Past due" if remaining <= 0 else f"{int(remaining // DAY)} days {int(remaining % DAY // 3600)} hours")
        course_id, assignment_id = item["id"].split(":", 1)
        fields = {
            "<COURSE_TITLE>": item["course"][:200] or "Course",
            "<ASSIGNMENT_NAME>": item["title"][:500] or "Assignment",
            "<DUE_DATE>": datetime.fromtimestamp(due, BANGKOK).strftime("%d %b %Y %H:%M") if due is not None else "No deadline",
            "<TIME_LEFT>": left, "<TIME_LEFT_COLOR>": color,
            "<TIME_LEFT_WEIGHT>": "bold", "<TIME_LEFT_SIZE>": "md",
            "<STATUS_TEXT>": status, "<STATUS_BG_COLOR>": color,
            "<DETAIL_URL>": "https://alpha.mycourseville.com/course/" + quote(course_id, safe="") + "/assignments/" + quote(assignment_id, safe=""),
        }
        bubble = replace(copy.deepcopy(HEADER), fields)
        bubble["body"]["contents"] = [replace(copy.deepcopy(BODY), fields)]
        bubbles.append(bubble)
    # Six cards per message stays comfortably below the carousel JSON size limit.
    return [{"type": "flex", "altText": label[:400],
             "contents": {"type": "carousel", "contents": bubbles[i:i+6]}}
            for i in range(0, len(bubbles), 6)]
