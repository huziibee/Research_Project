"""Schema validation errors."""


class SchemaValidationError(ValueError):
  """Raised when a record fails canonical schema validation."""

  def __init__(self, message: str, *, field: str | None = None) -> None:
    self.field = field
    if field is not None:
      message = f"{field}: {message}"
    super().__init__(message)
