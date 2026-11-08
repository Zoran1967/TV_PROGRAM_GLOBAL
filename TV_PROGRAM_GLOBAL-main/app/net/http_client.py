"""HTTP preuzimanje sa rokom, ogranicenom velicinom i kontrolisanim ponovnim pokusajima.

- samo https (http samo uz allow_http=True, koristi se u testovima);
- preusmeravanje sa https na http je blokirano;
- gzip se raspakuje uz ogranicenje velicine;
- ponovni pokusaji samo za mrezne greske i HTTP 5xx; 4xx se ne ponavlja;
- na HTTP 429 (i 503) sa kratkim Retry-After ceka se i pokusava jos jednom.
"""

import http.client
import logging
import socket
import ssl
import time
import urllib.error
import urllib.request
import zlib
from urllib.parse import urlparse

from app.providers.errors import (
    EmptyResponseError,
    HttpStatusError,
    NetworkError,
    ParseError,
    RateLimitedError,
    ResponseTooLargeError,
)
from app.version import __version__

LOGGER = logging.getLogger(__name__)

USER_AGENT = "TV_PROGRAM_GLOBAL/%s (schedule viewer)" % __version__
DEFAULT_TIMEOUT = 15.0
DEFAULT_TOTAL_TIMEOUT = 40.0
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_RETRY_AFTER = 10.0
CHUNK_SIZE = 64 * 1024


class _NoDowngradeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(req.full_url).scheme == "https" and urlparse(newurl).scheme != "https":
            raise NetworkError("Preusmeravanje na nesiguran http je blokirano")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context():
    """SSL kontekst sa certifi sertifikatima (Android nema sistemske sertifikate za Python)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # certifi nije dostupan: koristi se podrazumevani kontekst
        return ssl.create_default_context()


def build_opener():
    return urllib.request.build_opener(
        _NoDowngradeRedirect(), urllib.request.HTTPSHandler(context=_ssl_context())
    )


def _retry_after_seconds(headers):
    value = headers.get("Retry-After") if headers else None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _read_body(response, max_bytes, deadline):
    body = bytearray()
    # read1 vraca ono sto je stiglo, pa se rok proverava i kad server salje polako
    reader = getattr(response, "read1", response.read)
    while True:
        if time.monotonic() > deadline:
            raise NetworkError("Preuzimanje je trajalo predugo")
        chunk = reader(CHUNK_SIZE)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLargeError("Odgovor je veci od %d bajtova" % max_bytes)
    return bytes(body)


def _maybe_gunzip(body, headers, max_bytes):
    encoding = (headers.get("Content-Encoding") or "").lower() if headers else ""
    if "gzip" not in encoding and not body.startswith(b"\x1f\x8b"):
        return body
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = decompressor.decompress(body, max_bytes + 1)
    except zlib.error as error:
        raise ParseError("Neispravan gzip: %s" % error)
    if len(data) > max_bytes or decompressor.unconsumed_tail:
        raise ResponseTooLargeError("Raspakovani odgovor je veci od %d bajtova" % max_bytes)
    if not decompressor.eof:
        raise ParseError("Nepotpun gzip")
    return data


def _attempt(opener, request, timeout, max_bytes, total_timeout):
    deadline = time.monotonic() + total_timeout
    try:
        with opener.open(request, timeout=timeout) as response:
            body = _read_body(response, max_bytes, deadline)
            headers = response.headers
            declared = (headers.get("Content-Length") or "").strip() if headers else ""
            if declared.isdigit() and len(body) < int(declared):
                raise NetworkError(
                    "Odgovor je prekinut (%d od %s bajtova)" % (len(body), declared)
                )
    except urllib.error.HTTPError as error:
        if error.code in (429, 503):
            retry_after = _retry_after_seconds(error.headers)
            if error.code == 429 or retry_after is not None:
                raise RateLimitedError(retry_after)
        raise HttpStatusError(error.code)
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError,
            http.client.HTTPException, OSError) as error:
        reason = getattr(error, "reason", error)
        raise NetworkError("%s: %s" % (type(error).__name__, reason))
    data = _maybe_gunzip(body, headers, max_bytes)
    if not data.strip():
        raise EmptyResponseError("Prazan odgovor")
    return data


def fetch_bytes(url, timeout=DEFAULT_TIMEOUT, max_bytes=DEFAULT_MAX_BYTES, retries=2,
                backoff=1.0, allow_http=False, opener=None, sleep=time.sleep,
                total_timeout=DEFAULT_TOTAL_TIMEOUT):
    """Preuzima adresu i vraca sadrzaj (bajtove). Baca ProviderError ili ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("Neispravna adresa")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError("Dozvoljen je samo https")
    opener = opener or build_opener()
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    )
    attempts = retries + 1
    for attempt in range(attempts):
        last = attempt + 1 >= attempts
        try:
            data = _attempt(opener, request, timeout, max_bytes, total_timeout)
            LOGGER.info("Preuzeto %d bajtova sa %s", len(data), parsed.netloc)
            return data
        except RateLimitedError as error:
            if last or error.retry_after is None or error.retry_after > MAX_RETRY_AFTER:
                raise
            sleep(error.retry_after)
        except HttpStatusError as error:
            if last or error.status < 500:
                raise
            sleep(backoff * (2 ** attempt))
        except NetworkError:
            if last:
                raise
            sleep(backoff * (2 ** attempt))
        LOGGER.warning("Ponovni pokusaj %d/%d za %s", attempt + 1, retries, parsed.netloc)
