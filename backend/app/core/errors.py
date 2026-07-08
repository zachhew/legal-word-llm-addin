class LLMProviderError(Exception):
    def __init__(self, message: str = "LLM provider request failed.") -> None:
        super().__init__(message)


class InvalidLLMResponseError(LLMProviderError):
    def __init__(self, message: str = "LLM provider returned invalid JSON.") -> None:
        super().__init__(message)


class MissingProviderSettingsError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class RequestTooLargeError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
