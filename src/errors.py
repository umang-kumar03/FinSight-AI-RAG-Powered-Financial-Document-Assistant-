"""Errors safe to show in the interface (without provider payloads)."""


class ValidationError(ValueError):
    """The submitted input is invalid or exceeds application limits."""


class ServiceError(RuntimeError):
    """A dependency or remote service could not complete a request."""
