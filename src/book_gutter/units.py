MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0
POINTS_PER_MM = POINTS_PER_INCH / MM_PER_INCH
MM_PER_POINT = MM_PER_INCH / POINTS_PER_INCH


def mm_to_points(mm: float) -> float:
    return mm * POINTS_PER_MM


def points_to_mm(points: float) -> float:
    return points * MM_PER_POINT


def format_mm(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f} mm"


def format_pct(value: float, decimals: int = 0) -> str:
    return f"{value:.{decimals}f}%"
