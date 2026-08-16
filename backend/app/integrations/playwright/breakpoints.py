from typing import NamedTuple


class Viewport(NamedTuple):
    width: int
    height: int


STANDARD_BREAKPOINTS: dict[str, Viewport] = {
    "mobile": Viewport(375, 667),
    "tablet": Viewport(768, 1024),
    "desktop": Viewport(1440, 900),
}
