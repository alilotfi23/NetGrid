class AppError(Exception):
    """Base for all domain errors. Every error surfaces as {"error": {code, message}}."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    message = "Resource not found"


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409
    message = "Resource already exists or is in conflict"


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status_code = 400
    message = "Bad request"


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = 401
    message = "Authentication required"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403
    message = "Insufficient permissions"
