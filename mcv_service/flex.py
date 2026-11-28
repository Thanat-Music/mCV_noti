"""Typed notification cards, rendered without string-based JSON substitution."""
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from .engine import BANGKOK, DAY

ROOT = Path(__file__).parent
HEADER = json.loads((ROOT / "flex_header_template.json").read_text())
BODY = json.loads((ROOT / "flex_body_template.json").read_text())

THEMES = {
    "homework": ("Homework · next 7 days", "#4d0000"),
    "initial_summary": ("Your open assignments", "#4d0000"),
    "new_assignment": ("New assignment", "#1565C0"),
    "deadline_changed": ("Deadline updated", "#B45309"),
    "deadline_summary": ("Due soon", "#B3261E"),
    "push_assignment": ("Assignment update", "#1565C0"),
    "push_announcement": ("Announcement", "#6D28D9"),
    "push_material": ("Learning material", "#00796B"),
    "push_score": ("Score update", "#4338CA"),
    "push_other": ("Course update", "#475569"),
    "incident": ("Refresh needs attention", "#B3261E"),
    "recovery": ("Refresh restored", "#188038"),
}


def text_block(text, **options):
    return {"type": "text", "text": str(text), "wrap": True, **options}


def decorate(bubble, label, color, note=None):
    heading = bubble["header"]["contents"][0]
    if label:
        heading["text"] = label + " " + heading["text"]
    bubble["styles"]["header"]["backgroundColor"] = color
    if note:
        bubble["footer"] = {"type": "box", "layout": "vertical", "contents": [
            text_block(note, size="xs", color="#6a7585")]}


def notice_messages(kind, text, note=None, title=None, url=None, course=None):
    label, color = THEMES.get(kind, THEMES["push_other"])
    heading, background, action_label = {
        "push_material": ("MATERIAL", "#E6F4F1", "Open material"),
        "push_score": ("SCORE", "#EEF0FF", "View score"),
        "push_announcement": ("ANNOUNCEMENT", "#F3ECFC", "Read announcement"),
        "push_assignment": ("ASSIGNMENT UPDATE", "#EAF2FC", "View assignment"),
        "push_other": ("COURSE UPDATE", "#F1F5F9", "Open CourseVille"),
        "new_assignment": ("NEW ASSIGNMENT", "#EAF2FC", "View assignment"),
        "deadline_changed": ("DEADLINE UPDATED", "#FFF4E5", "View assignment"),
        "incident": ("REFRESH DELAYED", "#FCECEB", None),
        "recovery": ("REFRESH RESTORED", "#EAF5ED", None),
    }.get(kind, ("HOMEWORK", "#F7EFEF", None))
    # Preserve long incoming content across cards without exceeding text limits.
    parts = [text[i:i+2000] for i in range(0, len(text), 2000)] or [""]
    bubbles = []
    for part in parts:
        content = []
        if course:
            content.append(text_block(course[:200], size="xl", weight="bold", color="#2d3138"))
        if title:
            content.append(text_block(title[:500], size="lg", weight="regular", color="#2d3138"))
        if part:
            content.append(text_block(part, size="md", color="#475569"))
        if action_label:
            content.append({"type": "button", "style": "primary", "height": "sm",
                "margin": "lg", "color": color, "action": {"type": "uri",
                "label": action_label if url else "Open CourseVille",
                "uri": url or "https://www.mycourseville.com/"}})
        if note:
            content.append(text_block(note, size="xs", color="#6a7585", margin="lg"))
        boundary = {"#E6F4F1": "#BBDDD5", "#EEF0FF": "#CED2F0",
                    "#F3ECFC": "#DCCCEF", "#EAF2FC": "#C5D9EF",
                    "#FFF4E5": "#EED6B3"}.get(background, "#D5DAE0")
        bubble = {"type": "bubble", "body": {
            "type": "box", "layout": "vertical", "paddingAll": "xl",
            "spacing": "md", "backgroundColor": background,
            "borderWidth": "1px", "borderColor": boundary, "cornerRadius": "lg",
            "contents": [text_block(heading, size="sm", weight="bold", color=color)] + content}}
        bubbles.append(bubble)
    return [{"type": "flex", "altText": (label + ": " + (title or text))[:400],
             "contents": {"type": "carousel", "contents": bubbles[i:i+6]}}
            for i in range(0, len(bubbles), 6)]


def push_messages(kind, payload):
    notification = payload.get("notification")
    content = notification if isinstance(notification, dict) else payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    title = content.get("title")
    title = re.sub(r" - (Assignment|Material|Announcement|Score)\s*$", "", title,
                   flags=re.IGNORECASE) if isinstance(title, str) else None
    course = content.get("message")
    course = course if isinstance(course, str) and course.strip() else None
    body = content.get("body")
    body = body if isinstance(body, str) and body.strip() else None
    url = None
    for container in (content, data, payload):
        for key in ("url", "link", "click_action", "clickAction"):
            value = container.get(key)
            if not isinstance(value, str):
                continue
            try:
                parsed = urlsplit(value)
                if parsed.scheme == "https" and parsed.hostname in (
                        "www.mycourseville.com", "mycourseville.com", "alpha.mycourseville.com") and not parsed.username and not parsed.password:
                    url = value
                    break
            except ValueError:
                pass
        if url:
            break
    return notice_messages(kind, body or ("" if title else "Open CourseVille for details."),
                           title=title, course=course, url=url)


def replace(value, fields):
    if isinstance(value, dict):
        return {k: replace(v, fields) for k, v in value.items()}
    if isinstance(value, list):
        return [replace(v, fields) for v in value]
    return fields.get(value, value) if isinstance(value, str) else value


def homework_style(bubble, kind, note):
    label, background = {
        "new_assignment": ("NEW ASSIGNMENT", "#14365D"),
        "deadline_changed": ("DEADLINE UPDATED", "#593819"),
        "deadline_summary": ("HOMEWORK DUE", "#4d0000"),
    }.get(kind, ("HOMEWORK", "#4d0000"))
    decorate(bubble, "", background, note)
    for section in ("header", "body", "footer"):
        if section in bubble:
            bubble[section]["backgroundColor"] = background
        bubble["styles"][section] = {"backgroundColor": background, "separator": False}

    def readable(value):
        if isinstance(value, dict):
            if value.get("type") == "text":
                value["color"] = {"#6a7585": "#D8D2D2", "#b3261e": "#FFB4AB",
                                  "#188038": "#A8DAB5"}.get(value.get("color"), "#FFFFFF")
            for child in value.values():
                readable(child)
        elif isinstance(value, list):
            for child in value:
                readable(child)
    readable(bubble)
    # A carousel aligns separate headers to its tallest header. Keep all content
    # in one naturally sized body so longer course names don't push other cards down.
    heading = bubble["header"]["contents"][0]
    heading.update(margin="md", flex=0)
    content = [text_block(label, size="sm", weight="bold", color="#D8D2D2", flex=0), heading]
    for block in bubble["body"]["contents"]:
        block.update(margin="lg", flex=0)
        if block.get("type") == "box":
            title = block["contents"][0]
            title.update(margin="none", flex=0, gravity="top")
        content.append(block)
    if note:
        content.append(text_block(note, size="xs", color="#D8D2D2", margin="lg", flex=0))
    bubble.clear()
    bubble.update(type="bubble", body={"type": "box", "layout": "vertical",
        "paddingAll": "xl", "backgroundColor": background, "contents": content})
    return bubble


def assignment_messages(items, label, now, kind="homework", note=None):
    if not items:
        bubble = replace(copy.deepcopy(HEADER), {"<COURSE_TITLE>": "Homework"})
        bubble["body"]["contents"] = [text_block("No assignments in this period.", size="lg")]
        return [{"type": "flex", "altText": label[:400],
                 "contents": homework_style(bubble, kind, note)}]
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
        homework_style(bubble, kind, note)
        bubbles.append(bubble)
    # Six cards per message stays comfortably below the carousel JSON size limit.
    return [{"type": "flex", "altText": label[:400],
             "contents": {"type": "carousel", "contents": bubbles[i:i+6]}}
            for i in range(0, len(bubbles), 6)]
