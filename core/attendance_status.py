# core/attendance_status.py
# Mã trạng thái
PRESENT = "PRESENT"
LATE = "LATE"
EXCUSED = "EXCUSED"
UNEXCUSED = "UNEXCUSED"
ABSENT = "ABSENT"

ALL_STATUSES = (PRESENT, LATE, EXCUSED, UNEXCUSED, ABSENT)

DEFAULT_MIN_RATE = 75
SO_TIET_MOI_CA = 3

LABELS = {
    PRESENT: "Có mặt",
    LATE: "Đi muộn",
    EXCUSED: "Vắng có phép",
    UNEXCUSED: "Vắng không phép",
    ABSENT: "Vắng",
}

COLORS = {
    PRESENT: "#E1F5EE",
    LATE: "#FAEEDA",
    EXCUSED: "#E7F0FA",
    UNEXCUSED: "#FCEBEB",
    ABSENT: "#FCEBEB",
}

# Chỉ PRESENT + LATE được tính là có mặt khi tính chuyên cần
PRESENT_STATES = frozenset({PRESENT, LATE})

ABSENCE_STATES = frozenset({EXCUSED, UNEXCUSED, ABSENT})
ABSENCE_LABELS = frozenset(LABELS[s] for s in ABSENCE_STATES)

_LEGACY_MAP = {
    "Co mat": PRESENT,
    "Có mặt": PRESENT,
    "Tre": LATE,
    "Trễ": LATE,
    "Di muon": LATE,
    "Đi muộn": LATE,
    "Vang mat": ABSENT,
    "Vắng mặt": ABSENT,
    "Vang": ABSENT,
    "Vắng": ABSENT,
}

def normalize(value) -> str:
    """Chuẩn hóa một giá trị trạng thái bất kỳ về mã chuẩn."""
    if not value:
        return ABSENT
    text = str(value).strip()
    if text in ALL_STATUSES:
        return text
    return _LEGACY_MAP.get(text, ABSENT)

def label(value) -> str:
    return LABELS.get(normalize(value), LABELS[ABSENT])

def color(value) -> str:
    return COLORS.get(normalize(value), "#FFFFFF")

def is_present(value) -> bool:
    return normalize(value) in PRESENT_STATES
def planned_session_count(total_periods: int) -> int:
    try:
        total_periods = int(total_periods)
    except (TypeError, ValueError):
        return 0

    if total_periods <= 0:
        return 0

    return (
        total_periods
        + SO_TIET_MOI_CA
        - 1
    ) // SO_TIET_MOI_CA


def required_present_count(
    total_sessions: int,
    minimum_rate: int,
) -> int:
    try:
        total_sessions = int(total_sessions)
        minimum_rate = int(minimum_rate)
    except (TypeError, ValueError):
        return 0

    if total_sessions <= 0:
        return 0

    minimum_rate = max(0, min(minimum_rate, 100))

    return (
        total_sessions * minimum_rate + 99
    ) // 100