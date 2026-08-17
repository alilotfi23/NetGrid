from app.core.pagination import Page


def test_page_shape():
    page = Page[int](items=[1, 2, 3], total=100, page=1, page_size=10)
    assert page.items == [1, 2, 3]
    assert page.total == 100
    assert page.page == 1
    assert page.page_size == 10


def test_page_requires_all_fields():
    try:
        Page[int](items=[1])
    except Exception:
        return
    raise AssertionError("Page should require total, page, page_size")
