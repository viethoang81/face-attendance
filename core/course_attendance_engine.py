import logging
from core.attendance_engine import AttendanceEngine

logger = logging.getLogger(__name__)

class CourseAttendanceEngine(AttendanceEngine):
    def _get_class_status(
        self,
        mssv: str,
        ca_hoc_id: int,
    ) -> str:
        cache_key = (mssv, ca_hoc_id)

        with self._record_lock:
            cached = self._class_check_cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            with self.db.conn() as connection:
                row = connection.execute(
                    """
                    SELECT sv.mssv,
                           ca.id AS caHocId,
                           EXISTS (
                               SELECT 1
                               FROM DangKyHocPhan dk
                               WHERE dk.mssv = sv.mssv
                                 AND dk.lopHocPhanId
                                       = ca.lopHocPhanId
                                 AND dk.ngayDangKy <= ca.ngayHoc
                                 AND (
                                     dk.ngayKetThuc = ''
                                     OR dk.ngayKetThuc
                                           >= ca.ngayHoc
                                 )
                           ) AS coDangKyHopLe
                    FROM SinhVien sv
                    CROSS JOIN CaHoc ca
                    WHERE sv.mssv = ?
                      AND sv.trangThai = 'DANG_HOC'
                      AND ca.id = ?
                    """,
                    (
                        mssv,
                        ca_hoc_id,
                    ),
                ).fetchone()

            if not row:
                result = "error"
            elif row["coDangKyHopLe"] != 1:
                # Giữ tên trạng thái cũ để TabAttendance không phải sửa.
                result = "wrong_class"
            else:
                result = "ok"

        except Exception as exc:
            logger.error(
                "[CourseAttendanceEngine] "
                "Registration check error: %s",
                exc,
            )
            result = "error"

        with self._record_lock:
            self._class_check_cache[cache_key] = result

            if (
                result == "wrong_class"
                and cache_key not in self._wrong_class_logged
            ):
                logger.warning(
                    "[CourseAttendanceEngine] "
                    "Student has no valid registration: "
                    "MSSV=%s, session=%s",
                    mssv,
                    ca_hoc_id,
                )
                self._wrong_class_logged.add(cache_key)

        return result
