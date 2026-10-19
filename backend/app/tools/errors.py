class ToolError(Exception):
    """Raised when a tool cannot produce a valid result."""


class RefResolutionError(Exception):
    """Raised when a ${step.path} reference cannot be resolved."""
