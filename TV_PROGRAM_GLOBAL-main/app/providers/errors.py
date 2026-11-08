"""Greske izvora rasporeda. Svaka ima kratak kod za prikaz i logovanje."""


class ProviderError(Exception):
    code = "provider_error"


class NetworkError(ProviderError):
    """Nema veze, istekao rok, neispravan SSL ili prekinuta veza."""

    code = "network"


class HttpStatusError(ProviderError):
    """Server je vratio HTTP gresku (npr. 404, 500)."""

    code = "http"

    def __init__(self, status, message=""):
        super().__init__(message or "HTTP %s" % status)
        self.status = status


class RateLimitedError(ProviderError):
    """Server trazi pauzu (HTTP 429 ili 503 sa Retry-After)."""

    code = "rate_limited"

    def __init__(self, retry_after=None):
        super().__init__("Izvor trazi pauzu")
        self.retry_after = retry_after


class ResponseTooLargeError(ProviderError):
    code = "too_large"


class EmptyResponseError(ProviderError):
    """Odgovor je prazan."""

    code = "empty"


class ParseError(ProviderError):
    """Odgovor nije ispravan XMLTV."""

    code = "parse"


class EmptyScheduleError(ProviderError):
    """Fajl je ispravan, ali nema nijednu emisiju za trazenu stanicu."""

    code = "empty_schedule"


class ZoneUnavailableError(ProviderError):
    """Vremenska zona stanice nije poznata ili nije dostupna na uredjaju."""

    code = "zone"


class InvalidSourceError(ProviderError):
    """Oznaka stanice kod izvora nije dozvoljenog oblika."""

    code = "invalid_source"
