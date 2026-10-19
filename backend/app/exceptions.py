"""
Custom domain exceptions for smart farming assistant.
Ensures honest error handling without fabricating transcripts or mock data.
"""

class STTUnavailableError(Exception):
    """Raised when no Speech-to-Text engine is available or all STT engines fail."""
    def __init__(self, message: str = "Speech-to-text service is unavailable. Please try again or type your question."):
        super().__init__(message)
        self.message = message

class TranslationUnavailableError(Exception):
    """Raised when no translation engine is available and dictionary fallback cannot handle the query."""
    def __init__(self, message: str = "Translation service is temporarily unavailable. Please try again later or type in English."):
        super().__init__(message)
        self.message = message
