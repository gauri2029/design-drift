class LLMNotConfiguredError(Exception):
    """Raised when ANTHROPIC_API_KEY is not configured."""


class LLMResponseError(Exception):
    """Raised when the model's response didn't parse against the expected schema."""
