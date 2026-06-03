"""Unified API error type.

Every handled error is rendered as ``{ error_code, message, detail? }``.
"""
from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail
