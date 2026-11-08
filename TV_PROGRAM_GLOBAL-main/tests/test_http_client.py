"""Testovi HTTP klijenta sa pravim lokalnim serverom (bez interneta)."""

import gzip
import http.server
import os
import socket
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.net.http_client import fetch_bytes  # noqa: E402
from app.providers.errors import (  # noqa: E402
    EmptyResponseError,
    HttpStatusError,
    NetworkError,
    ParseError,
    RateLimitedError,
    ResponseTooLargeError,
)


class Handler(http.server.BaseHTTPRequestHandler):
    routes = {}
    hits = {}
    user_agents = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path
        Handler.hits[path] = Handler.hits.get(path, 0) + 1
        Handler.user_agents.append(self.headers.get("User-Agent"))
        responder = Handler.routes[path]
        responder(self, Handler.hits[path])


def send(handler, status, body=b"", headers=None):
    handler.send_response(status)
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


@pytest.fixture
def server():
    Handler.routes, Handler.hits, Handler.user_agents = {}, {}, []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def get(base, path, **kwargs):
    kwargs.setdefault("allow_http", True)
    kwargs.setdefault("backoff", 0.0)
    kwargs.setdefault("retries", 2)
    return fetch_bytes(base + path, **kwargs)


def test_plain_response_and_user_agent(server):
    Handler.routes["/a"] = lambda h, n: send(h, 200, b"<tv/>")
    assert get(server, "/a") == b"<tv/>"
    assert Handler.user_agents[0].startswith("TV_PROGRAM_GLOBAL/")


def test_gzip_with_header(server):
    body = gzip.compress(b"<tv>podaci</tv>")
    Handler.routes["/g"] = lambda h, n: send(h, 200, body, {"Content-Encoding": "gzip"})
    assert get(server, "/g") == b"<tv>podaci</tv>"


def test_gzip_without_header(server):
    body = gzip.compress(b"<tv>podaci</tv>")
    Handler.routes["/g"] = lambda h, n: send(h, 200, body)
    assert get(server, "/g") == b"<tv>podaci</tv>"


def test_corrupt_gzip_is_a_parse_error(server):
    Handler.routes["/g"] = lambda h, n: send(h, 200, b"\x1f\x8b\x08\x00broken", {"Content-Encoding": "gzip"})
    with pytest.raises(ParseError):
        get(server, "/g")


def test_gzip_bomb_is_rejected(server):
    bomb = gzip.compress(b"0" * 5_000_000)
    assert len(bomb) < 20_000
    Handler.routes["/b"] = lambda h, n: send(h, 200, bomb, {"Content-Encoding": "gzip"})
    with pytest.raises(ResponseTooLargeError):
        get(server, "/b", max_bytes=100_000)


def test_large_response_is_rejected(server):
    Handler.routes["/big"] = lambda h, n: send(h, 200, b"x" * 2_000_000)
    with pytest.raises(ResponseTooLargeError):
        get(server, "/big", max_bytes=1000)


def test_empty_body(server):
    Handler.routes["/e"] = lambda h, n: send(h, 200, b"")
    with pytest.raises(EmptyResponseError):
        get(server, "/e")
    Handler.routes["/w"] = lambda h, n: send(h, 200, b"  \n ")
    with pytest.raises(EmptyResponseError):
        get(server, "/w")


def test_404_is_not_retried(server):
    Handler.routes["/n"] = lambda h, n: send(h, 404, b"nema")
    with pytest.raises(HttpStatusError) as info:
        get(server, "/n")
    assert info.value.status == 404
    assert Handler.hits["/n"] == 1


def test_server_error_is_retried_then_succeeds(server):
    Handler.routes["/s"] = lambda h, n: send(h, 500) if n < 3 else send(h, 200, b"<tv/>")
    sleeps = []
    assert get(server, "/s", sleep=sleeps.append, backoff=1.0) == b"<tv/>"
    assert Handler.hits["/s"] == 3
    assert sleeps == [1.0, 2.0]


def test_server_error_gives_up_after_retries(server):
    Handler.routes["/s"] = lambda h, n: send(h, 502)
    with pytest.raises(HttpStatusError) as info:
        get(server, "/s")
    assert info.value.status == 502
    assert Handler.hits["/s"] == 3


def test_retries_zero_means_single_attempt(server):
    Handler.routes["/s"] = lambda h, n: send(h, 500)
    with pytest.raises(HttpStatusError):
        get(server, "/s", retries=0)
    assert Handler.hits["/s"] == 1


def test_rate_limit_with_short_retry_after_waits_and_retries(server):
    Handler.routes["/r"] = lambda h, n: send(h, 429, b"", {"Retry-After": "2"}) if n == 1 else send(h, 200, b"<tv/>")
    sleeps = []
    assert get(server, "/r", sleep=sleeps.append) == b"<tv/>"
    assert sleeps == [2.0]


def test_rate_limit_with_long_retry_after_raises(server):
    Handler.routes["/r"] = lambda h, n: send(h, 429, b"", {"Retry-After": "600"})
    with pytest.raises(RateLimitedError) as info:
        get(server, "/r", sleep=lambda s: None)
    assert info.value.retry_after == 600.0
    assert Handler.hits["/r"] == 1


def test_rate_limit_without_retry_after_raises(server):
    Handler.routes["/r"] = lambda h, n: send(h, 429)
    with pytest.raises(RateLimitedError):
        get(server, "/r")
    assert Handler.hits["/r"] == 1


def test_timeout_is_a_network_error(server):
    def slow(handler, n):
        time.sleep(1.0)
        send(handler, 200, b"<tv/>")

    Handler.routes["/slow"] = slow
    started = time.monotonic()
    with pytest.raises(NetworkError):
        get(server, "/slow", timeout=0.2, retries=0)
    assert time.monotonic() - started < 0.9


def test_connection_refused_is_a_network_error():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    with pytest.raises(NetworkError):
        fetch_bytes("http://127.0.0.1:%d/x" % port, allow_http=True, retries=0)


def test_connection_closed_mid_response_is_a_network_error(server):
    def broken(handler, n):
        handler.send_response(200)
        handler.send_header("Content-Length", "1000")
        handler.end_headers()
        handler.wfile.write(b"samo malo")
        handler.wfile.flush()
        handler.close_connection = True

    Handler.routes["/broken"] = broken
    with pytest.raises(NetworkError):
        get(server, "/broken", retries=0)


def test_redirect_within_http_is_followed(server):
    Handler.routes["/old"] = lambda h, n: send(h, 302, b"", {"Location": "/new"})
    Handler.routes["/new"] = lambda h, n: send(h, 200, b"<tv/>")
    assert get(server, "/old") == b"<tv/>"


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "ftp://example.com/x", "file:///etc/passwd",
                                 "javascript:alert(1)", "", "https://", "example.com/x"])
def test_unsafe_or_invalid_urls_are_refused(url):
    with pytest.raises(ValueError):
        fetch_bytes(url)


def test_total_timeout_stops_slow_trickle(server):
    def trickle(handler, n):
        handler.send_response(200)
        handler.send_header("Content-Length", "100000")
        handler.end_headers()
        try:
            for _ in range(100):
                handler.wfile.write(b"x" * 100)
                handler.wfile.flush()
                time.sleep(0.05)
        except OSError:
            pass

    Handler.routes["/t"] = trickle
    started = time.monotonic()
    with pytest.raises(NetworkError):
        get(server, "/t", timeout=1.0, total_timeout=0.3, retries=0)
    assert time.monotonic() - started < 2.0
