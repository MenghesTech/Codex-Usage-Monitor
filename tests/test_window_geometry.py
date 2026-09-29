from src.window_geometry import anchor_position, recover_position


FULL = (290, 175)
COMPACT = (290, 65)


def test_valid_position_is_preserved():
    screens = [(0, 0, 1920, 1040)]
    assert recover_position((800, 300), FULL, screens) == (800, 300)


def test_partially_outside_is_minimally_clamped():
    screens = [(0, 0, 1920, 1040)]
    assert recover_position((1800, 980), FULL, screens) == (1630, 865)


def test_completely_outside_moves_to_nearest_available_screen():
    screens = [(0, 0, 1920, 1040)]
    assert recover_position((4000, 200), FULL, screens) == (1630, 200)


def test_disappeared_monitor_recovers_from_negative_coordinates():
    old_position = (-1700, 300)
    remaining_screens = [(0, 0, 1920, 1040)]
    assert recover_position(old_position, FULL, remaining_screens) == (0, 300)


def test_widget_spanning_adjacent_screens_remains_unchanged():
    screens = [(-1920, 0, 1920, 1040), (0, 0, 1920, 1040)]
    assert recover_position((-100, 300), FULL, screens) == (-100, 300)


def test_duplicated_screen_geometry_does_not_double_count_visibility():
    screens = [(0, 0, 1920, 1040), (0, 0, 1920, 1040)]
    assert recover_position((1800, 300), FULL, screens) == (1630, 300)


def test_compact_and_full_sizes_recover_independently():
    screens = [(0, 0, 1280, 720)]
    assert recover_position((1100, 680), COMPACT, screens) == (990, 655)
    assert recover_position((1100, 680), FULL, screens) == (990, 545)


def test_anchor_positions_respect_available_geometry():
    screen = (-1920, 40, 1920, 1000)
    assert anchor_position("tl", FULL, screen, 14) == (-1906, 54)
    assert anchor_position("br", FULL, screen, 14) == (-304, 851)
