from pydantic import BaseModel


class Page[T](BaseModel):
    """Uniform list response shape: {items, total, page, page_size}."""

    items: list[T]
    total: int
    page: int
    page_size: int
