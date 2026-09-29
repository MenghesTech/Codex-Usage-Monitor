from __future__ import annotations

from collections.abc import Sequence


Rect = tuple[int, int, int, int]
Point = tuple[int, int]
Size = tuple[int, int]


def _intersection_area(a: Rect, b: Rect) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[0] + a[2], b[0] + b[2])
    bottom = min(a[1] + a[3], b[1] + b[3])
    return max(0, right - left) * max(0, bottom - top)


def _covered_area(widget: Rect, screens: Sequence[Rect]) -> int:
    intersections = []
    for screen in screens:
        left = max(widget[0], screen[0])
        top = max(widget[1], screen[1])
        right = min(widget[0] + widget[2], screen[0] + screen[2])
        bottom = min(widget[1] + widget[3], screen[1] + screen[3])
        if right > left and bottom > top:
            intersections.append((left, top, right, bottom))
    if not intersections:
        return 0

    x_edges = sorted({edge for rect in intersections for edge in (rect[0], rect[2])})
    area = 0
    for left, right in zip(x_edges, x_edges[1:]):
        intervals = sorted(
            (top, bottom)
            for x1, top, x2, bottom in intersections
            if x1 < right and x2 > left
        )
        covered_height = 0
        if intervals:
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start > end:
                    covered_height += end - start
                    start, end = next_start, next_end
                else:
                    end = max(end, next_end)
            covered_height += end - start
        area += (right - left) * covered_height
    return area


def _clamp(value: int, low: int, high: int) -> int:
    return low if high < low else max(low, min(value, high))


def _clamp_to_screen(position: Point, size: Size, screen: Rect) -> Point:
    x, y = position
    width, height = size
    sx, sy, sw, sh = screen
    return (
        _clamp(x, sx, sx + sw - width),
        _clamp(y, sy, sy + sh - height),
    )


def recover_position(
    position: Point, size: Size, screens: Sequence[Rect]
) -> Point:
    """Return the smallest safe correction for the current screen layout."""
    if not screens:
        return position

    widget = (position[0], position[1], size[0], size[1])
    widget_area = max(0, size[0]) * max(0, size[1])
    intersections = [_intersection_area(widget, screen) for screen in screens]

    # A widget spanning adjacent screens is still fully visible.
    if widget_area and _covered_area(widget, screens) >= widget_area:
        return position

    best_area = max(intersections, default=0)
    if best_area:
        screen = screens[intersections.index(best_area)]
        return _clamp_to_screen(position, size, screen)

    # The old monitor disappeared. Preserve spatial intent by selecting the
    # nearest remaining available geometry, then clamp into it.
    center_x = position[0] + size[0] / 2
    center_y = position[1] + size[1] / 2

    def distance_squared(screen: Rect) -> float:
        sx, sy, sw, sh = screen
        nearest_x = max(sx, min(center_x, sx + sw))
        nearest_y = max(sy, min(center_y, sy + sh))
        return (center_x - nearest_x) ** 2 + (center_y - nearest_y) ** 2

    nearest = min(screens, key=distance_squared)
    return _clamp_to_screen(position, size, nearest)


def anchor_position(anchor: str, size: Size, screen: Rect, margin: int) -> Point:
    sx, sy, sw, sh = screen
    width, height = size
    positions = {
        "tl": (sx + margin, sy + margin),
        "tr": (sx + sw - width - margin, sy + margin),
        "bl": (sx + margin, sy + sh - height - margin),
        "br": (sx + sw - width - margin, sy + sh - height - margin),
        "cl": (sx + margin, sy + (sh - height) // 2),
        "cr": (sx + sw - width - margin, sy + (sh - height) // 2),
    }
    return positions.get(anchor, (sx + margin, sy + margin))
