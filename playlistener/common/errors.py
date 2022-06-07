class BotError(Exception):
    """Parent class for all exceptions."""

    def __init__(self, reason: str, details: str = None):
        """Store details in addition to reason."""

        super().__init__(reason)
        self.details = details


class UsageError(BotError):
    """Thrown when the user fucks up."""


class InternalError(BotError):
    """Thrown when the bot fucks up."""
