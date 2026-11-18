"""SocialClient: HTTP dasar + peta galat + backoff eksponensial untuk semua provider."""
import random
import time

import requests

from energyx_social.services.errors import (
    AuthError, PermanentError, RateLimitError, SocialError, TransientError,
)

NETWORK_ERRORS = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)


def parse_json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"data": data}
    except ValueError:
        return {}


def retry_after_seconds(resp):
    value = resp.headers.get("Retry-After")
    try:
        return min(float(value), 300) if value else None
    except ValueError:
        return None


def default_status_error(resp) -> SocialError:
    s = resp.status_code
    if s == 429:
        return RateLimitError(f"HTTP 429 rate limit", status=s, retry_after=retry_after_seconds(resp))
    if s >= 500:
        return TransientError(f"HTTP {s} server error", status=s)
    if s in (401, 403):
        return AuthError(f"HTTP {s} tidak berwenang", status=s)
    return PermanentError(f"HTTP {s}", status=s)


class SocialClient:
    """`error_mapper(resp) -> SocialError | None` dipanggil untuk SETIAP respons (juga 2xx,
    karena TikTok mengembalikan galat di body). None + status >= 400 jatuh ke pemetaan HTTP umum."""

    def __init__(self, name, error_mapper=None, *, timeout=(10, 300), max_retries=4,
                 base_delay=2.0, max_delay=60.0, sleep=time.sleep, session=None):
        self.name = name
        self.error_mapper = error_mapper
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.sleep = sleep
        self.session = session or requests.Session()

    def _map(self, resp):
        err = self.error_mapper(resp) if self.error_mapper else None
        if err is None and resp.status_code >= 400:
            err = default_status_error(resp)
        return err

    def _delay(self, attempt, err):
        if err.retry_after:
            return min(err.retry_after, self.max_delay * 5)
        return min(self.max_delay, self.base_delay * (2 ** attempt)) + random.uniform(0, 1)

    def request(self, method, url, *, params=None, data=None, json=None, headers=None,
                allow_redirects=True, timeout=None):
        attempt = 0
        while True:
            try:
                resp = self.session.request(
                    method, url, params=params, data=data, json=json, headers=headers,
                    timeout=timeout or self.timeout, allow_redirects=allow_redirects,
                )
            except NETWORK_ERRORS as exc:
                err = TransientError(f"{self.name}: galat jaringan ({type(exc).__name__})")
            else:
                err = self._map(resp)
                if err is None:
                    return resp
            if err.retryable and attempt < self.max_retries:
                self.sleep(self._delay(attempt, err))
                attempt += 1
                continue
            raise err
