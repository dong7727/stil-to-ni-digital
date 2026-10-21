"""Stage-weighted progress; external tools remain at their current stage."""

from collections.abc import Callable

ProgressCallback = Callable[[int, str], None]


class Progress:
    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self.callback = callback
        self.last = -1
        self.message = ""

    def __call__(self, percent: int, message: str) -> None:
        percent = max(self.last, min(100, max(0, percent)))
        if (percent, message) != (self.last, self.message):
            self.last, self.message = percent, message
            if self.callback:
                self.callback(percent, message)
