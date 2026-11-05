"""Who is acting in the current request (the web UI's user picker).

The web layer sets it per request; models stamp it on records they create
(a screening step's ``screened_by``, an allocation's ``recorded_by``). Code
outside a request (scripts, tests) has no actor unless it sets one.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

current_actor: ContextVar[Optional[str]] = ContextVar("current_actor", default=None)


@contextmanager
def acting_as(username: Optional[str]) -> Iterator[None]:
    token = current_actor.set(username or None)
    try:
        yield
    finally:
        current_actor.reset(token)
