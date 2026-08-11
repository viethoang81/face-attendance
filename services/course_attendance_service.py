from core import attendance_status as A
from core.database import Database
from services.attendance_service import AttendanceService


class CourseAttendanceService(AttendanceService):
    """
    Dịch vụ báo cáo điểm danh theo LopHocPhan và DangKyHocPhan.

    Kế thừa toàn bộ chức năng xuất Excel của AttendanceService cũ,
    nhưng thay các truy vấn dựa trên lớp hành chính bằng đăng ký
    học phần có hiệu lực tại ngày diễn ra ca học.
    """

    def __init__(self, db: Database):
        super().__init__(db)

    @staticmethod
    def _attendance_actor(connection, attendance_id: int, username: str):
        return connection.execute(
            """
            SELECT tk.id AS taiKhoanId,
                   tk.vaiTro,
                   gv.id AS giangVienId,
                   dd.mssv,
                   dd.isVoided,
                   lhp.giangVienId AS lopHocPhanGiangVienId
            FROM TaiKhoan tk
            LEFT JOIN GiangVien gv ON gv.taiKhoanId = tk.id
            JOIN DiemDanh dd ON dd.id = ?
            JOIN CaHoc ca ON ca.id = dd.caHocId
            JOIN LopHocPhan lhp ON lhp.id = ca.lopHocPhanId
            WHERE tk.username = ? AND tk.isActive = 1
            """,
            (attendance_id, (username or "").strip()),
        ).fetchone()

    def void_attendance(
        self,
        attendance_id: int,
        actor_username: str,
        reason: str,
    ) -> tuple[bool, str]:
        """Hủy hiệu lực một lượt điểm danh nhưng vẫn giữ bản ghi kiểm toán."""
        reason = " ".join((reason or "").split())
        if not reason:
            return False, "Vui lòng nhập lý do hủy điểm danh"

        with self.db.conn() as connection:
            actor = self._attendance_actor(
                connection,
                attendance_id,
                actor_username,
            )
            if not actor:
                return False, "Không tìm thấy điểm danh hoặc tài khoản thao tác"
            allowed = (
                actor["vaiTro"] == "Admin"
                or (
                    actor["vaiTro"] == "GiangVien"
                    and actor["giangVienId"]
                        == actor["lopHocPhanGiangVienId"]
                )
            )
            if not allowed:
                return False, "Bạn không có quyền hủy lượt điểm danh này"
            if actor["isVoided"] == 1:
                return True, "Lượt điểm danh đã được hủy trước đó"

            connection.execute(
                """
                UPDATE DiemDanh
                SET isVoided = 1,
                    voidReason = ?,
                    voidedAt = CURRENT_TIMESTAMP,
                    voidedByTaiKhoanId = ?,
                    updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    reason,
                    actor["taiKhoanId"],
                    attendance_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO AuthLog (
                    actorTaiKhoanId,
                    actorUsernameSnapshot,
                    targetUsernameSnapshot,
                    eventType,
                    success,
                    message
                )
                VALUES (?, ?, ?, 'ATTENDANCE_VOID', 1, ?)
                """,
                (
                    actor["taiKhoanId"],
                    actor_username.strip(),
                    actor["mssv"],
                    reason[:500],
                ),
            )
        return True, "Đã hủy lượt điểm danh và giữ lại lịch sử"

    def restore_attendance(
        self,
        attendance_id: int,
        actor_username: str,
    ) -> tuple[bool, str]:
        """Khôi phục bản ghi đã hủy; thao tác được ghi vào nhật ký."""
        with self.db.conn() as connection:
            actor = self._attendance_actor(
                connection,
                attendance_id,
                actor_username,
            )
            if not actor:
                return False, "Không tìm thấy điểm danh hoặc tài khoản thao tác"
            allowed = (
                actor["vaiTro"] == "Admin"
                or (
                    actor["vaiTro"] == "GiangVien"
                    and actor["giangVienId"]
                        == actor["lopHocPhanGiangVienId"]
                )
            )
            if not allowed:
                return False, "Bạn không có quyền khôi phục lượt điểm danh này"
            if actor["isVoided"] == 0:
                return True, "Lượt điểm danh đang có hiệu lực"

            connection.execute(
                """
                UPDATE DiemDanh
                SET isVoided = 0,
                    voidReason = '',
                    voidedAt = '',
                    voidedByTaiKhoanId = NULL,
                    updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (attendance_id,),
            )
            connection.execute(
                """
                INSERT INTO AuthLog (
                    actorTaiKhoanId,
                    actorUsernameSnapshot,
                    targetUsernameSnapshot,
                    eventType,
                    success,
                    message
                )
                VALUES (?, ?, ?, 'ATTENDANCE_RESTORE', 1, ?)
                """,
                (
                    actor["taiKhoanId"],
                    actor_username.strip(),
                    actor["mssv"],
                    "Khôi phục lượt điểm danh",
                ),
            )
        return True, "Đã khôi phục lượt điểm danh"

    def get_history(
        self,
        maLop: str = "",
        mssv: str = "",
        ngay_from: str = "",
        ngay_to: str = "",
    ) -> list[dict]:
        sql = """
            SELECT dd.id,
                   ca.id AS caHocId,
                   lhp.maLopHocPhan,
                   sv.mssv,
                   sv.hoTen,
                   lhp.tenLopHocPhan AS tenLop,
                   mh.tenMon,
                   ca.tenCa,
                   ca.ngayHoc,
                   ca.gioBatDau || ' - ' || ca.gioKetThuc AS gioHoc,
                   COALESCE(dd.thoiGian, '') AS thoiGian,
                   CASE
                       WHEN dd.id IS NULL OR dd.isVoided = 1 THEN 'ABSENT'
                       ELSE COALESCE(dd.trangThai, 'PRESENT')
                   END AS trangThai,
                   COALESCE(dd.isVoided, 0) AS isVoided,
                   COALESCE(dd.voidReason, '') AS voidReason,
                   COALESCE(dd.voidedAt, '') AS voidedAt
            FROM CaHoc ca
            JOIN LopHocPhan lhp
              ON lhp.id = ca.lopHocPhanId
            JOIN MonHoc mh
              ON mh.maMon = lhp.maMon
            JOIN DangKyHocPhan dk
              ON dk.lopHocPhanId = ca.lopHocPhanId
             AND dk.ngayDangKy <= ca.ngayHoc
             AND (
                 dk.ngayKetThuc = ''
                 OR dk.ngayKetThuc >= ca.ngayHoc
             )
            JOIN SinhVien sv
              ON sv.mssv = dk.mssv
            LEFT JOIN DiemDanh dd
              ON dd.caHocId = ca.id
             AND dd.mssv = sv.mssv
            WHERE (
                COALESCE(ca.daMoDiemDanh, 0) = 1
                OR EXISTS (
                    SELECT 1
                    FROM DiemDanh history_dd
                    WHERE history_dd.caHocId = ca.id
                )
            )
        """
        params = []

        if maLop:
            sql += """
                AND lower(lhp.maLopHocPhan) = lower(?)
            """
            params.append(maLop.strip())

        if mssv:
            sql += " AND sv.mssv LIKE ?"
            params.append(f"%{mssv.strip()}%")

        if ngay_from:
            sql += " AND ca.ngayHoc >= ?"
            params.append(ngay_from)

        if ngay_to:
            sql += " AND ca.ngayHoc <= ?"
            params.append(ngay_to)

        sql += """
            ORDER BY ca.ngayHoc DESC,
                     ca.gioBatDau DESC,
                     sv.hoTen,
                     sv.mssv
        """

        with self.db.conn() as connection:
            rows = [
                dict(row)
                for row in connection.execute(sql, params)
            ]

        for row in rows:
            row["thoiGian"] = self._time_only(
                row.get("thoiGian")
            )

        return rows

    def get_session_full_report(
        self,
        ca_hoc_id: int,
        ma_lop: str = "",
    ) -> list[dict]:
        """
        Danh sách đủ có mặt và vắng của một ca.

        Tham số ma_lop được giữ để tương thích TabAttendance cũ,
        nhưng lớp học phần chính xác luôn được lấy từ ca_hoc_id.
        """

        with self.db.conn() as connection:
            session = connection.execute(
                """
                SELECT ca.id,
                       ca.lopHocPhanId,
                       ca.tenCa,
                       ca.ngayHoc,
                       ca.gioBatDau,
                       ca.gioKetThuc,
                       lhp.maLopHocPhan,
                       lhp.tenLopHocPhan AS tenLop,
                       mh.tenMon
                FROM CaHoc ca
                JOIN LopHocPhan lhp
                  ON lhp.id = ca.lopHocPhanId
                JOIN MonHoc mh
                  ON mh.maMon = lhp.maMon
                WHERE ca.id = ?
                """,
                (ca_hoc_id,),
            ).fetchone()

            if not session:
                return []

            students = connection.execute(
                """
                SELECT sv.mssv,
                       sv.hoTen
                FROM DangKyHocPhan dk
                JOIN SinhVien sv
                  ON sv.mssv = dk.mssv
                WHERE dk.lopHocPhanId = ?
                  AND dk.ngayDangKy <= ?
                  AND (
                      dk.ngayKetThuc = ''
                      OR dk.ngayKetThuc >= ?
                  )
                ORDER BY sv.hoTen, sv.mssv
                """,
                (
                    session["lopHocPhanId"],
                    session["ngayHoc"],
                    session["ngayHoc"],
                ),
            ).fetchall()

            attended_rows = connection.execute(
                """
                SELECT mssv,
                       thoiGian,
                       trangThai
                FROM DiemDanh
                WHERE caHocId = ?
                  AND isVoided = 0
                """,
                (ca_hoc_id,),
            ).fetchall()

        attended = {
            row["mssv"]: dict(row)
            for row in attended_rows
        }

        session = dict(session)
        time_text = (
            f"{session['gioBatDau']} - {session['gioKetThuc']}"
        )

        result = []

        for student in students:
            student_id = student["mssv"]
            attendance = attended.get(student_id)

            if attendance:
                status = A.normalize(attendance["trangThai"])
                attendance_time = self._time_only(
                    attendance["thoiGian"]
                )
            else:
                status = A.ABSENT
                attendance_time = ""

            result.append(
                {
                    "mssv": student_id,
                    "hoTen": student["hoTen"],
                    "tenLop": session["tenLop"],
                    "tenMon": session["tenMon"],
                    "tenCa": session["tenCa"],
                    "ngayHoc": session["ngayHoc"],
                    "gioHoc": time_text,
                    "thoiGian": attendance_time,
                    "trangThai": status,
                }
            )

        return result

    def get_attendance_report(
        self,
        maLop: str = "",
        maMon: str = "",
        ngay_from: str = "",
        ngay_to: str = "",
        scope: str = "course",
    ) -> dict:
        if scope not in {"course", "period"}:
            raise ValueError("Phạm vi báo cáo không hợp lệ")

        if not maLop:
            return self._empty_report(scope)

        with self.db.conn() as connection:
            section = connection.execute(
                """
                SELECT lhp.id,
                       lhp.maLopHocPhan,
                       lhp.maMon,
                       mh.soTiet,
                       mh.tiLeToiThieu
                FROM LopHocPhan lhp
                JOIN MonHoc mh
                  ON mh.maMon = lhp.maMon
                WHERE lower(lhp.maLopHocPhan) = lower(?)
                """,
                (maLop.strip(),),
            ).fetchone()

            if not section:
                return self._empty_report(scope)

            if (
                maMon
                and section["maMon"].casefold()
                != maMon.strip().casefold()
            ):
                return self._empty_report(scope)

            threshold = int(
                section["tiLeToiThieu"]
                or A.DEFAULT_MIN_RATE
            )

            planned_sessions = 0
            if section["soTiet"]:
                planned_sessions = A.planned_session_count(
                    section["soTiet"]
                )
            session_sql = """
                SELECT ca.id,
                       ca.ngayHoc
                FROM CaHoc ca
                WHERE ca.lopHocPhanId = ?
                  AND (
                      COALESCE(ca.daMoDiemDanh, 0) = 1
                      OR EXISTS (
                          SELECT 1
                          FROM DiemDanh dd
                          WHERE dd.caHocId = ca.id
                      )
                  )
            """
            session_params = [section["id"]]

            if scope == "period":
                if ngay_from:
                    session_sql += " AND ca.ngayHoc >= ?"
                    session_params.append(ngay_from)

                if ngay_to:
                    session_sql += " AND ca.ngayHoc <= ?"
                    session_params.append(ngay_to)

            session_sql += """
                ORDER BY ca.ngayHoc, ca.gioBatDau
            """

            sessions = [
                dict(row)
                for row in connection.execute(
                    session_sql,
                    session_params,
                )
            ]

            registration_sql = """
                SELECT dk.mssv,
                       dk.ngayDangKy,
                       dk.ngayKetThuc,
                       dk.trangThai,
                       sv.hoTen
                FROM DangKyHocPhan dk
                JOIN SinhVien sv
                  ON sv.mssv = dk.mssv
                WHERE dk.lopHocPhanId = ?
            """
            registration_params = [section["id"]]

            if scope == "period":
                if ngay_from:
                    registration_sql += """
                        AND (
                            dk.ngayKetThuc = ''
                            OR dk.ngayKetThuc >= ?
                        )
                    """
                    registration_params.append(ngay_from)

                if ngay_to:
                    registration_sql += """
                        AND dk.ngayDangKy <= ?
                    """
                    registration_params.append(ngay_to)

            registration_sql += """
                ORDER BY sv.hoTen, sv.mssv
            """

            registrations = [
                dict(row)
                for row in connection.execute(
                    registration_sql,
                    registration_params,
                )
            ]

            attendance_pairs = set()
            session_ids = [session["id"] for session in sessions]

            if session_ids:
                placeholders = ",".join(
                    "?" for _ in session_ids
                )
                attendance_rows = connection.execute(
                    f"""
                    SELECT mssv,
                           caHocId,
                           trangThai
                    FROM DiemDanh
                    WHERE caHocId IN ({placeholders})
                      AND isVoided = 0
                    """,
                    session_ids,
                ).fetchall()

                attendance_pairs = {
                    (row["mssv"], row["caHocId"])
                    for row in attendance_rows
                    if A.is_present(row["trangThai"])
                }

        sessions_held = len(sessions)

        if scope == "course":
            # Không để tổng số ca nhỏ hơn số ca thực tế đã diễn ra.
            global_total = max(
                planned_sessions,
                sessions_held,
            )
        else:
            # Báo cáo khoảng ngày chỉ tính những ca trong khoảng đó.
            global_total = sessions_held

        remaining_global_sessions = max(
            global_total - sessions_held,
            0,
        )

        result = []

        for registration in registrations:
            student_id = registration["mssv"]
            registration_start = registration["ngayDangKy"]
            registration_end = registration["ngayKetThuc"]

            eligible_sessions = [
                session
                for session in sessions
                if registration_start <= session["ngayHoc"]
                and (
                    not registration_end
                    or registration_end >= session["ngayHoc"]
                )
            ]

            eligible_session_ids = {
                session["id"]
                for session in eligible_sessions
            }

            present_count = sum(
                1
                for session_id in eligible_session_ids
                if (student_id, session_id) in attendance_pairs
            )

            eligible_held_count = len(eligible_sessions)
            absent_count = max(
                eligible_held_count - present_count,
                0,
            )

            if scope == "period":
                student_total = eligible_held_count
                remaining_for_student = 0
            elif registration_end:
                student_total = eligible_held_count
                remaining_for_student = 0

            else:
                remaining_for_student = (
                    remaining_global_sessions
                )
                student_total = (
                    eligible_held_count
                    + remaining_for_student
                )

            attendance_rate = (
                round(
                    present_count / student_total * 100,
                    1,
                )
                if student_total > 0
                else 0.0
            )

            required_present = A.required_present_count(
                student_total,
                threshold,
            )

            maximum_present = (
                min(
                    present_count + remaining_for_student,
                    student_total,
                )
                if student_total > 0
                else present_count
            )

            if scope == "period":
                # Không được xét điều kiện dự thi từ một phần thời gian.
                exam_status = "KHÔNG ÁP DỤNG"

            elif student_total <= 0:
                exam_status = "CHƯA CÓ DỮ LIỆU"

            elif present_count >= required_present:
                exam_status = "ĐỦ ĐIỀU KIỆN"

            elif maximum_present < required_present:
                exam_status = "CẤM THI"

            else:
                exam_status = "CHƯA KẾT LUẬN"

            result.append(
                {
                    "mssv": student_id,
                    "hoTen": registration["hoTen"],
                    "tong_buoi": student_total,
                    "so_buoi_da_hoc": eligible_held_count,
                    "so_co_mat": present_count,
                    "so_vang": absent_count,
                    "ty_le": attendance_rate,
                    "trang_thai_thi": exam_status,
                    "du_dieu_kien": (
                        exam_status == "ĐỦ ĐIỀU KIỆN"
                    ),
                }
            )

        result.sort(
            key=lambda item: (
                item["ty_le"],
                item["hoTen"],
            )
        )

        return {
            "scope": scope,
            "threshold": threshold,
            "total_sessions": global_total,
            "sessions_held": sessions_held,
            "students": result,
        }

    @staticmethod
    def _empty_report(scope: str = "course") -> dict:
        return {
            "scope": scope,
            "threshold": A.DEFAULT_MIN_RATE,
            "total_sessions": 0,
            "sessions_held": 0,
            "students": [],
        }
