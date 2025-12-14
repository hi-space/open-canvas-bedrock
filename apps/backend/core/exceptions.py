"""
Custom exceptions for the application.
"""
from typing import Optional


class AppException(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)


class NotFoundError(AppException):
    """Resource not found exception."""
    def __init__(self, resource: str, resource_id: str):
        message = f"{resource} {resource_id} not found"
        super().__init__(message, status_code=404)


class ValidationError(AppException):
    """Validation error exception."""
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message, status_code=400, detail=detail)


class InternalServerError(AppException):
    """Internal server error exception."""
    def __init__(self, message: str = "Internal server error", detail: Optional[str] = None):
        super().__init__(message, status_code=500, detail=detail)

