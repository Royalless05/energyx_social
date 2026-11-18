import re


class SocialError(Exception):
    """Galat dasar.

    retryable          -> klien mengulang di dalam proses dengan backoff eksponensial.
    reschedule_minutes -> bila tetap gagal, publisher menjadwalkan ulang kanal ini (None = gagal permanen).
    """

    retryable = False
    reschedule_minutes = None

    def __init__(self, message="", *, code=None, status=None, retry_after=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retry_after = retry_after


class RateLimitError(SocialError):
    retryable = True
    reschedule_minutes = 15


class TransientError(SocialError):
    retryable = True
    reschedule_minutes = 10


class QuotaExceededError(SocialError):
    """Kuota harian habis: tidak ada gunanya mengulang dalam proses yang sama."""
    reschedule_minutes = 360


class AuthError(SocialError):
    pass


class PermanentError(SocialError):
    pass


class MediaError(PermanentError):
    pass


class UnsupportedOperation(PermanentError):
    pass


_PATTERNS = [
    re.compile(r"(?i)(access_token|refresh_token|client_secret|app_secret|fb_exchange_token|client_key)"
               r"([\"'=:\s]+)([A-Za-z0-9._\-~+/]{8,})"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-~+/]{8,})"),
]


def redact(text, secrets=()) -> str:
    """Hapus rahasia dari teks sebelum masuk Error Log / kolom error_log / email."""
    text = str(text or "")
    for secret in secrets or ():
        if secret and len(secret) >= 6:
            text = text.replace(secret, "[REDACTED]")
    text = _PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    text = _PATTERNS[1].sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    return text
