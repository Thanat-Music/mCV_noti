from receiver.session import LoginSession, AlphaDiscovery


class Response:
    status_code = 200
    headers = {}

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_login_form_and_post_without_diagnostics(capsys):
    login = LoginSession('test-user', 'test-password')
    token = login._extract_csrf_token(Response('<input name="_token" value="csrf">'))
    calls = []
    login.session.post = lambda url, **kwargs: calls.append((url, kwargs)) or Response('ok')
    login._perform_login(token)
    assert calls[0][1]['data'] == {'_token': 'csrf', 'username': 'test-user',
                                  'password': 'test-password', 'remember': 'on'}
    assert capsys.readouterr().out == ''
    assert login._extract_csrf_token(Response('<html>changed form</html>')) is None


def test_alpha_client_discovery_uses_current_bundle():
    discovery = AlphaDiscovery()
    calls = []
    def get(url):
        calls.append(url)
        if len(calls) == 1:
            return Response('<script src="/assets/index-current.js"></script>')
        return Response('"https://www.mycourseville.com/api/oauth/authorize?client_id=abcdefghijklmnopqrstuv"')
    discovery.session.get = get
    assert discovery.get_client_id() == 'abcdefghijklmnopqrstuv'
    assert calls[1] == 'https://alpha.mycourseville.com/assets/index-current.js'
