from __future__ import annotations

from typing import Protocol


class SupportsNotify(Protocol):
    def notify(self, title: str, message: str) -> None:
        ...
