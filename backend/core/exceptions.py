"""
Custom application exceptions.
"""
from typing import Any, Dict, Optional


class PromptQLException(Exception):
    """Base exception for PromptQL application."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseConnectionError(PromptQLException):
    """Raised when database connection fails."""

    def __init__(self, message: str = "Database connection failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=503, details=details)


class CredentialEncryptionError(PromptQLException):
    """Raised when credential encryption/decryption fails."""

    def __init__(self, message: str = "Credential encryption failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class SchemaExtractionError(PromptQLException):
    """Raised when schema extraction fails."""

    def __init__(self, message: str = "Schema extraction failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class QueryValidationError(PromptQLException):
    """Raised when SQL query validation fails."""

    def __init__(self, message: str = "Invalid SQL query", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class QueryExecutionError(PromptQLException):
    """Raised when query execution fails."""

    def __init__(self, message: str = "Query execution failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class LLMServiceError(PromptQLException):
    """Raised when LLM service fails."""

    def __init__(self, message: str = "LLM service error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=503, details=details)


class RetrievalError(PromptQLException):
    """Raised when schema retrieval fails."""

    def __init__(self, message: str = "Schema retrieval failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class ConfigurationError(PromptQLException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str = "Invalid configuration", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)