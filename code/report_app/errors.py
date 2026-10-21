class AppError(Exception):
    """Expected error safe to expose to the local UI, without provider secrets."""

    def __init__(self, message, status=400, code="invalid_input"):
        super().__init__(message)
        self.status = status
        self.code = code
