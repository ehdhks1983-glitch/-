class LicenseError(Exception):
    """Base error for the license client."""


class NetworkError(LicenseError):
    """Raised when the license server is unreachable after retries."""
