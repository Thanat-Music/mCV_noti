"""Export signup and policy HTML for review without credentials or network calls."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcv_service.enrollment import signup_html
from mcv_service.policies import policy_html


def main():
    directory = ROOT / 'docs' / 'previews'
    directory.mkdir(parents=True, exist_ok=True)
    form = signup_html('preview-only-not-a-live-signup-token')
    form = form.replace('href="/terms"', 'href="terms.html"').replace('href="/privacy"', 'href="privacy.html"')
    form = form.replace('<form method="post" action="/register">', '<form>')
    form = form.replace('<input name="username"', '<input disabled name="username"')
    form = form.replace('<input name="password"', '<input disabled name="password"')
    form = form.replace('<button>Request registration</button>', '<button type="button" disabled>Preview only - registration disabled</button>')
    form = form.replace('<h1>Join mCV Notifier</h1>', '<h1>Join mCV Notifier</h1><p><strong>PREVIEW ONLY</strong></p>')
    (directory / 'signup.html').write_text(form, encoding='utf-8')
    for kind in ('terms', 'privacy'):
        page = policy_html(kind).replace('href="/terms"', 'href="terms.html"').replace('href="/privacy"', 'href="privacy.html"')
        (directory / (kind + '.html')).write_text(page, encoding='utf-8')
    print('Preview written to docs/previews/signup.html (no live signup or credentials).')


if __name__ == '__main__':
    main()
