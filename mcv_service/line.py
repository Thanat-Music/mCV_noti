"""LINE delivery with stable retry keys and no response-body logging."""
import uuid
import requests


class DeliveryError(Exception):
    def __init__(self, status, permanent):
        self.status, self.permanent = status, permanent
        super().__init__("line_delivery_failed")


class Line:
    def __init__(self, token, recipient, session=None):
        self.token, self.recipient = token, recipient
        self.session = session or requests.Session()

    def send(self, text, retry_key):
        chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
        for index in range(0, len(chunks), 5):
            key = str(uuid.uuid5(uuid.UUID(retry_key), str(index)))
            result = self.session.post("https://api.line.me/v2/bot/message/push", timeout=30,
                headers={"Authorization": "Bearer " + self.token, "X-Line-Retry-Key": key},
                json={"to": self.recipient,
                      "messages": [{"type": "text", "text": part} for part in chunks[index:index+5]]})
            if result.status_code == 409 and result.headers.get("x-line-accepted-request-id"):
                continue
            if result.status_code != 200:
                raise DeliveryError(result.status_code, 400 <= result.status_code < 500 and result.status_code != 429)
