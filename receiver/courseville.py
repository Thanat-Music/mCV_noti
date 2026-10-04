"""Authenticated legacy AJAX registration, separate from alpha OAuth.

No credentials or session material is written by this module.
"""
from urllib.parse import urlsplit

BASE = "https://www.mycourseville.com/"


def legacy_account(database, key_path, user_id):
    """Read a specifically selected legacy account without modifying it."""
    import base64
    import sqlite3
    from pathlib import Path
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    db = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = db.execute("SELECT cname,cpass FROM user WHERE user_id=?", (user_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise RuntimeError("legacy_user_not_found")
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    scheme = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    return tuple(key.decrypt(base64.b64decode(value), scheme).decode() for value in row)


class CourseVille:
    def __init__(self, session):
        self.session = session

    def call(self, name, payload=None):
        url = BASE + "?q=courseville/ajax/webpush_" + name
        response = self.session.request("GET" if payload is None else "POST", url,
                                        json=payload, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError("courseville_http_" + str(response.status_code))
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("courseville_session_not_authenticated") from None
        if not isinstance(data, dict):
            raise RuntimeError("courseville_invalid_response")
        return data

    def verify(self, sub):
        listed = self.call("list")
        if listed.get("success") is not True or not isinstance(listed.get("subscriptions"), list):
            raise RuntimeError("courseville_session_not_authenticated")
        checked = self.call("check", {"endpoint": sub["endpoint"]})
        return checked.get("subscribed") is True and any(
            item.get("endpoint") == sub["endpoint"] for item in listed["subscriptions"])

    def publish(self, sub):
        if urlsplit(sub["endpoint"]).scheme != "https":
            raise ValueError("invalid_endpoint")
        result = self.call("publish", {"subscription": sub,
                          "useragent": "mCV_noti standalone receiver/0.1", "platform": "Linux aarch64"})
        if result.get("success") is not True or not self.verify(sub):
            raise RuntimeError("courseville_subscription_not_verified")

    def assignments(self, now=None):
        """Discover the current OAuth client and validate the complete assignment response."""
        from datetime import datetime, timezone, timedelta
        from urllib.parse import urlencode, parse_qs
        from .session import AlphaDiscovery
        local = now or datetime.now(timezone(timedelta(hours=7)))
        semester = 1 if local.month >= 8 else (2 if local.month <= 5 else 3)
        year = local.year if semester == 1 else local.year - 1
        discover = AlphaDiscovery.__new__(AlphaDiscovery)
        discover.session = self.session
        client_id = discover.get_client_id()
        response = self.session.get(BASE + "api/oauth/authorize?" + urlencode({
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "https://alpha.mycourseville.com/", "state": "/course"}),
            allow_redirects=False, timeout=30)
        target = urlsplit(response.headers.get("Location", ""))
        if response.status_code != 302 or target.hostname != "alpha.mycourseville.com":
            raise RuntimeError("alpha_authorization_failed")
        code = parse_qs(target.query).get("code", [None])[0]
        if not code:
            raise RuntimeError("alpha_authorization_code_missing")
        token = self.session.post("https://api.alpha.mycourseville.com/auth/login",
                                  json={"code": code}, timeout=30)
        token.raise_for_status()
        access = token.json()["access_token"]
        query = """query($semester:String!,$year:String!,$filter:AssignmentFilter!) {
            me { myCoursesBySemester(semester:$semester,year:$year) {
                student { courseID title courseNumber courseYear semester
                    assignments(filter:$filter) { courseID id title type status outDate dueDate } }
            } } }"""
        response = self.session.post("https://api.alpha.mycourseville.com/query",
            headers={"Authorization": "Bearer " + access}, timeout=30,
            json={"query": query, "variables": {"semester": str(semester), "year": str(year), "filter": "ALL"}})
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise RuntimeError("alpha_partial_or_failed_query")
        courses = body["data"]["me"]["myCoursesBySemester"]["student"]
        if not isinstance(courses, list) or any(not isinstance(c.get("assignments"), list) for c in courses):
            raise RuntimeError("alpha_invalid_courses")
        return courses


def login(username, password):
    from .session import LoginSession
    scraper = LoginSession(username, password)
    # Bound requests for login and bundle discovery.
    original = scraper.session.request
    def bounded(*args, **kwargs):
        kwargs.setdefault("timeout", 30)
        return original(*args, **kwargs)
    scraper.session.request = bounded
    scraper._get_homepage()
    token = scraper._extract_csrf_token(scraper._get_login_page())
    if not token:
        raise RuntimeError("courseville_login_form_unrecognized")
    response = scraper._perform_login(token)
    if response.status_code != 200:
        raise RuntimeError("courseville_login_failed")
    client = CourseVille(scraper.session)
    result = client.call("list")
    if result.get("success") is not True:
        raise RuntimeError("courseville_login_not_verified")
    return client
