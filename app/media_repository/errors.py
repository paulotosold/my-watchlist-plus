"""Repository-specific errors."""

class ConcurrentEditError(RuntimeError):
    """Raised when an edited value no longer matches its dialog baseline."""


class MetadataRefreshConflict(RuntimeError):
    """Raised when a TMDB snapshot cannot be reconciled without data loss."""
