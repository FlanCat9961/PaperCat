class PaperCatError(Exception):
    """Base exception for all PaperCat errors."""


class ConfigError(PaperCatError):
    """Raised when configuration loading or validation fails."""


class LockBusyError(PaperCatError):
    """Raised when another PaperCat process already holds the lock."""


class SourceError(PaperCatError):
    """Base exception for wallpaper source failures."""


class SourceAuthError(SourceError):
    """Raised when source authentication is missing or invalid."""


class SourceNetworkError(SourceError):
    """Raised when a source network or HTTP request fails."""


class SourceRateLimitError(SourceError):
    """Raised when a source rate limit is hit."""


class LibraryError(PaperCatError):
    """Raised when wallpaper library persistence or filesystem work fails."""


class MonitorError(PaperCatError):
    """Raised when monitor detection fails."""
