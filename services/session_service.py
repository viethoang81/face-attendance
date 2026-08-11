from datetime import date, datetime, time


KHUNG_GIO = [
    ("Ca 1  -  07:00 – 09:00", "Ca 1", "07:00", "09:00"),
    ("Ca 2  -  09:15 – 11:15", "Ca 2", "09:15", "11:15"),
    ("Ca 3  -  13:00 – 15:00", "Ca 3", "13:00", "15:00"),
    ("Ca 4  -  15:15 – 17:15", "Ca 4", "15:15", "17:15"),
    ("Ca 5  -  18:00 – 20:00", "Ca 5", "18:00", "20:00"),
]


def _to_time(hhmm: str) -> time | None:
    try:
        hour, minute = map(int, (hhmm or "").split(":"))
        return time(hour, minute)
    except (TypeError, ValueError):
        return None


def compute_ca_status(
    ngay_hoc: str,
    gio_bat_dau: str,
    gio_ket_thuc: str,
) -> str:
    now = datetime.now()
    today = now.date()

    try:
        session_date = date.fromisoformat(ngay_hoc)
    except (TypeError, ValueError):
        return "ChuaMo"

    start_time = _to_time(gio_bat_dau)
    end_time = _to_time(gio_ket_thuc)

    if start_time is None or end_time is None:
        return "ChuaMo"

    if session_date > today:
        return "ChuaMo"

    if session_date < today:
        return "DaKetThuc"

    current_time = now.time().replace(
        second=0,
        microsecond=0,
    )

    if current_time < start_time:
        return "ChuaMo"

    if current_time <= end_time:
        return "DangDienRa"

    return "DaKetThuc"