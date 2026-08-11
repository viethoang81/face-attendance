import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from core.database import Database


@dataclass
class Student:
    mssv: str
    hoTen: str
    maLop: str
    ngaySinh: str = ""
    gioiTinh: str = "Nam"
    email: str = ""
    soDienThoai: str = ""


class StudentService:
    """Quản lý sinh viên, không xóa vật lý dữ liệu có lịch sử."""

    SELECT_FIELDS = """
        sv.mssv,
        sv.hoTen,
        substr(sv.ngaySinh, 9, 2) || '/' ||
        substr(sv.ngaySinh, 6, 2) || '/' ||
        substr(sv.ngaySinh, 1, 4) AS ngaySinh,
        sv.gioiTinh,
        sv.maLop,
        sv.email,
        sv.soDienThoai,
        sv.trangThai,
        sv.createdAt,
        sv.updatedAt,
        lh.tenLop
    """

    def __init__(self, db: Database, current_user: dict | None = None):
        self.db = db
        self.current_user = dict(current_user or {})

    @staticmethod
    def _date_to_db(value: str) -> str:
        return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")

    def add(self, sv: Student) -> tuple[bool, str]:
        error = self._validate(sv)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO SinhVien (
                        mssv, hoTen, ngaySinh, gioiTinh,
                        maLop, email, soDienThoai, trangThai
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'DANG_HOC')
                    """,
                    (
                        sv.mssv,
                        sv.hoTen,
                        self._date_to_db(sv.ngaySinh),
                        sv.gioiTinh,
                        sv.maLop,
                        sv.email,
                        sv.soDienThoai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc, sv.mssv)
        return True, "Thêm sinh viên thành công"

    def get_all(self, trang_thai: str = "") -> list[dict]:
        sql = f"""
            SELECT {self.SELECT_FIELDS}
            FROM SinhVien sv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            WHERE 1 = 1
        """
        params = []
        if trang_thai:
            sql += " AND sv.trangThai = ?"
            params.append(trang_thai)
        sql += " ORDER BY sv.maLop, sv.hoTen"

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_by_mssv(self, mssv: str) -> dict | None:
        with self.db.conn() as connection:
            row = connection.execute(
                f"""
                SELECT {self.SELECT_FIELDS}
                FROM SinhVien sv
                JOIN LopHoc lh ON lh.maLop = sv.maLop
                WHERE sv.mssv = ?
                """,
                ((mssv or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def search(
        self,
        kw: str = "",
        maLop: str = "",
        trang_thai: str = "",
    ) -> list[dict]:
        sql = f"""
            SELECT {self.SELECT_FIELDS}
            FROM SinhVien sv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            WHERE (sv.mssv LIKE ? OR sv.hoTen LIKE ?)
        """
        keyword = f"%{(kw or '').strip()}%"
        params = [keyword, keyword]
        if maLop:
            sql += " AND sv.maLop = ?"
            params.append(maLop.strip())
        if trang_thai:
            sql += " AND sv.trangThai = ?"
            params.append(trang_thai.strip())
        sql += " ORDER BY sv.hoTen, sv.mssv"

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_name_map(self) -> dict[str, str]:
        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT mssv, hoTen
                FROM SinhVien
                WHERE trangThai = 'DANG_HOC'
                """
            ).fetchall()
        return {row["mssv"]: row["hoTen"] for row in rows}

    def update(
        self,
        old_mssv: str,
        sv: Student,
    ) -> tuple[bool, str]:
        old_mssv = (old_mssv or "").strip()
        error = self._validate(sv, exclude_mssv=old_mssv)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    """
                    SELECT trangThai
                    FROM SinhVien
                    WHERE mssv = ?
                    """,
                    (old_mssv,),
                ).fetchone()
                if not current:
                    return False, "Không tìm thấy sinh viên"
                if current["trangThai"] != "DANG_HOC":
                    return (
                        False,
                        "Sinh viên không ở trạng thái Đang học; "
                        "thông tin chỉ được phép xem",
                    )

                cursor = connection.execute(
                    """
                    UPDATE SinhVien
                    SET mssv = ?, hoTen = ?, ngaySinh = ?,
                        gioiTinh = ?, maLop = ?, email = ?,
                        soDienThoai = ?, updatedAt = CURRENT_TIMESTAMP
                    WHERE mssv = ?
                      AND trangThai = 'DANG_HOC'
                    """,
                    (
                        sv.mssv,
                        sv.hoTen,
                        self._date_to_db(sv.ngaySinh),
                        sv.gioiTinh,
                        sv.maLop,
                        sv.email,
                        sv.soDienThoai,
                        old_mssv,
                    ),
                )
                if cursor.rowcount == 0:
                    return False, "Không tìm thấy sinh viên"
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc, sv.mssv)
        return True, "Cập nhật sinh viên thành công"

    def _actor_username(self, actor=None) -> str:
        if isinstance(actor, dict):
            value = actor.get("username", "")
        elif actor is not None:
            value = actor
        else:
            value = self.current_user.get("username", "")
        return str(value or "").strip()

    def _active_actor(self, connection, actor=None):
        username = self._actor_username(actor)
        if not username:
            return None
        return connection.execute(
            """
            SELECT tk.id AS taiKhoanId,
                   tk.username,
                   tk.vaiTro,
                   gv.id AS giangVienId
            FROM TaiKhoan tk
            LEFT JOIN GiangVien gv ON gv.taiKhoanId = tk.id
            WHERE lower(tk.username) = lower(?)
              AND tk.isActive = 1
            """,
            (username,),
        ).fetchone()

    @staticmethod
    def _actor_can_manage_student(connection, actor_row, student) -> bool:
        if not actor_row or not student:
            return False
        if actor_row["vaiTro"] == "Admin":
            return True
        if actor_row["vaiTro"] != "GiangVien":
            return False
        if actor_row["giangVienId"] is None:
            return False
        return connection.execute(
            """
            SELECT 1
            FROM LopHoc
            WHERE maLop = ?
              AND giangVienChuNhiemId = ?
            """,
            (student["maLop"], actor_row["giangVienId"]),
        ).fetchone() is not None

    @staticmethod
    def _hard_delete_counts(
        connection,
        mssv: str,
    ) -> tuple[int, int, int]:
        row = connection.execute(
            """
            SELECT (
                       SELECT COUNT(*)
                       FROM DangKyHocPhan dk
                       WHERE dk.mssv = sv.mssv
                   ) AS registrationCount,
                   (
                       SELECT COUNT(*)
                       FROM DiemDanh dd
                       WHERE dd.mssv = sv.mssv
                   ) AS attendanceCount,
                   (
                       SELECT COUNT(*)
                       FROM AuthLog al
                       WHERE al.targetUsernameSnapshot = sv.mssv
                         AND al.eventType = 'STUDENT_WITHDRAW'
                         AND al.success = 1
                   ) AS withdrawalCount
            FROM SinhVien sv
            WHERE sv.mssv = ?
            """,
            (mssv,),
        ).fetchone()
        if not row:
            return 0, 0, 0
        return (
            int(row["registrationCount"]),
            int(row["attendanceCount"]),
            int(row["withdrawalCount"]),
        )

    @staticmethod
    def _write_student_audit(
        connection,
        actor_row,
        mssv: str,
        event_type: str,
        message: str,
    ):
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
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                actor_row["taiKhoanId"],
                actor_row["username"],
                mssv,
                event_type,
                message[:500],
            ),
        )

    def can_hard_delete(
        self,
        mssv: str,
        actor=None,
    ) -> tuple[bool, str]:
        """Chỉ cho purge khi sinh viên chưa có đăng ký và điểm danh."""
        mssv = (mssv or "").strip()
        if not mssv:
            return False, "Không xác định được sinh viên"

        with self.db.conn() as connection:
            student = connection.execute(
                "SELECT mssv, maLop FROM SinhVien WHERE mssv = ?",
                (mssv,),
            ).fetchone()
            if not student:
                return False, "Không tìm thấy sinh viên"

            actor_row = self._active_actor(connection, actor)
            if not self._actor_can_manage_student(
                connection,
                actor_row,
                student,
            ):
                return False, "Bạn không có quyền quản lý sinh viên này"

            (
                registration_count,
                attendance_count,
                withdrawal_count,
            ) = self._hard_delete_counts(connection, mssv)

        if registration_count or attendance_count or withdrawal_count:
            if withdrawal_count:
                return False, (
                    "Sinh viên đã từng được xử lý thôi học nên phải giữ "
                    "lại hồ sơ và dấu vết học vụ"
                )
            return False, (
                "Sinh viên đã phát sinh dữ liệu học vụ "
                f"({registration_count} đăng ký, "
                f"{attendance_count} lượt điểm danh)"
            )
        return True, "Sinh viên chưa phát sinh dữ liệu học vụ"

    def purge_student(
        self,
        mssv: str,
        actor=None,
    ) -> tuple[bool, str]:
        """Xóa vĩnh viễn hồ sơ sạch trong một transaction duy nhất."""
        mssv = (mssv or "").strip()
        if not mssv:
            return False, "Không xác định được sinh viên"

        try:
            with self.db.conn() as connection:
                connection.execute("BEGIN IMMEDIATE")
                student = connection.execute(
                    """
                    SELECT mssv, hoTen, maLop
                    FROM SinhVien
                    WHERE mssv = ?
                    """,
                    (mssv,),
                ).fetchone()
                if not student:
                    return False, "Không tìm thấy sinh viên"

                actor_row = self._active_actor(connection, actor)
                if not self._actor_can_manage_student(
                    connection,
                    actor_row,
                    student,
                ):
                    return False, "Bạn không có quyền xóa sinh viên này"

                (
                    registration_count,
                    attendance_count,
                    withdrawal_count,
                ) = self._hard_delete_counts(connection, mssv)
                if (
                    registration_count
                    or attendance_count
                    or withdrawal_count
                ):
                    return False, (
                        "Sinh viên đã phát sinh dữ liệu học vụ nên "
                        "không thể xóa vĩnh viễn"
                    )

                connection.execute(
                    "DELETE FROM MauKhuonMat WHERE mssv = ?",
                    (mssv,),
                )
                deleted = connection.execute(
                    "DELETE FROM SinhVien WHERE mssv = ?",
                    (mssv,),
                )
                if deleted.rowcount != 1:
                    return False, "Không thể xóa hồ sơ sinh viên"

                self._write_student_audit(
                    connection,
                    actor_row,
                    mssv,
                    "STUDENT_PURGE",
                    "Xóa vĩnh viễn hồ sơ sinh viên chưa phát sinh dữ liệu học vụ",
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc, mssv)
        except sqlite3.Error:
            return False, "Không thể xóa sinh viên do lỗi cơ sở dữ liệu"

        return True, (
            "Đã xóa vĩnh viễn hồ sơ và mẫu khuôn mặt của sinh viên "
            f"'{mssv}'"
        )

    def withdraw_student(
        self,
        mssv: str,
        actor=None,
        effective_date: str = "",
    ) -> tuple[bool, str]:
        """Cho thôi học, giữ nguyên mọi lịch sử đã phát sinh."""
        mssv = (mssv or "").strip()
        if not mssv:
            return False, "Không xác định được sinh viên"

        effective_date = (effective_date or date.today().isoformat()).strip()
        try:
            effective_day = date.fromisoformat(effective_date)
        except ValueError:
            return False, "Ngày hiệu lực thôi học không hợp lệ"
        today = date.today()
        if effective_day != today:
            return False, (
                "Phiên bản hiện tại chỉ hỗ trợ cho thôi học có hiệu lực "
                "ngay trong ngày hôm nay; hệ thống chưa có cơ chế lên lịch "
                "thôi học cho ngày khác"
            )
        last_active_date = (effective_day - timedelta(days=1)).isoformat()

        try:
            with self.db.conn() as connection:
                connection.execute("BEGIN IMMEDIATE")
                student = connection.execute(
                    """
                    SELECT mssv, hoTen, maLop, trangThai
                    FROM SinhVien
                    WHERE mssv = ?
                    """,
                    (mssv,),
                ).fetchone()
                if not student:
                    return False, "Không tìm thấy sinh viên"

                actor_row = self._active_actor(connection, actor)
                if not self._actor_can_manage_student(
                    connection,
                    actor_row,
                    student,
                ):
                    return False, "Bạn không có quyền cho sinh viên thôi học"

                conflicting_history = connection.execute(
                    """
                    SELECT MAX(ca.ngayHoc) AS latestHistoryDate
                    FROM DangKyHocPhan dk
                    JOIN CaHoc ca
                      ON ca.lopHocPhanId = dk.lopHocPhanId
                    WHERE dk.mssv = ?
                      AND dk.trangThai = 'DANG_HOC'
                      AND dk.ngayDangKy <= ca.ngayHoc
                      AND (
                          dk.ngayKetThuc = ''
                          OR dk.ngayKetThuc >= ca.ngayHoc
                      )
                      AND ca.ngayHoc >= ?
                      AND (
                          COALESCE(ca.daMoDiemDanh, 0) = 1
                          OR EXISTS (
                              SELECT 1
                              FROM DiemDanh history_dd
                              WHERE history_dd.caHocId = ca.id
                          )
                      )
                    """,
                    (mssv, effective_date),
                ).fetchone()
                latest_history_date = (
                    conflicting_history["latestHistoryDate"]
                    if conflicting_history
                    else None
                )
                if latest_history_date:
                    return False, (
                        "Ngày hiệu lực phải sau ngày có lịch sử gần nhất "
                        f"({latest_history_date}) để không làm mất dữ liệu vắng"
                    )

                removed_future = connection.execute(
                    """
                    DELETE FROM DangKyHocPhan
                    WHERE mssv = ?
                      AND trangThai = 'DANG_HOC'
                      AND ngayDangKy >= ?
                    """,
                    (mssv, effective_date),
                ).rowcount

                ended_active = connection.execute(
                    """
                    UPDATE DangKyHocPhan
                    SET trangThai = 'DA_HUY',
                        ngayKetThuc = ?,
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE mssv = ?
                      AND trangThai = 'DANG_HOC'
                      AND ngayDangKy < ?
                    """,
                    (last_active_date, mssv, effective_date),
                ).rowcount

                deactivated_faces = connection.execute(
                    """
                    UPDATE MauKhuonMat
                    SET isActive = 0
                    WHERE mssv = ? AND isActive = 1
                    """,
                    (mssv,),
                ).rowcount

                if (
                    student["trangThai"] == "THOI_HOC"
                    and ended_active == 0
                    and removed_future == 0
                    and deactivated_faces == 0
                ):
                    return True, (
                        "Sinh viên đã ở trạng thái thôi học; "
                        "không có dữ liệu nào cần thay đổi"
                    )

                connection.execute(
                    """
                    UPDATE SinhVien
                    SET trangThai = 'THOI_HOC',
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE mssv = ?
                    """,
                    (mssv,),
                )

                self._write_student_audit(
                    connection,
                    actor_row,
                    mssv,
                    "STUDENT_WITHDRAW",
                    (
                        f"Thôi học có hiệu lực từ {effective_date}; "
                        f"kết thúc {ended_active} đăng ký, "
                        f"hủy {removed_future} đăng ký chưa có hiệu lực, "
                        f"vô hiệu hóa {deactivated_faces} mẫu khuôn mặt"
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc, mssv)
        except sqlite3.Error:
            return False, "Không thể cho thôi học do lỗi cơ sở dữ liệu"

        return True, (
            "Đã chuyển sinh viên sang trạng thái thôi học từ "
            f"{effective_date}; toàn bộ lịch sử được giữ nguyên"
        )

    def set_status(
        self,
        mssv: str,
        status: str,
    ) -> tuple[bool, str]:
        if status == "THOI_HOC":
            return self.withdraw_student(
                mssv,
                effective_date=date.today().isoformat(),
            )

        valid_statuses = {"DANG_HOC", "BAO_LUU", "DINH_CHI", "TOT_NGHIEP"}
        if status not in valid_statuses:
            return False, "Trạng thái sinh viên không hợp lệ"

        mssv = (mssv or "").strip()
        with self.db.conn() as connection:
            cursor = connection.execute(
                """
                UPDATE SinhVien
                SET trangThai = ?, updatedAt = CURRENT_TIMESTAMP
                WHERE mssv = ?
                """,
                (status, mssv),
            )
            if cursor.rowcount == 0:
                return False, "Không tìm thấy sinh viên"
            connection.execute(
                """
                UPDATE MauKhuonMat
                SET isActive = ?
                WHERE mssv = ?
                """,
                (1 if status == "DANG_HOC" else 0, mssv),
            )
        return True, "Đã cập nhật trạng thái sinh viên"

    def delete(self, mssv: str) -> tuple[bool, str]:
        """Alias tương thích cũ; luôn là nghiệp vụ thôi học, không purge."""
        return self.withdraw_student(
            mssv,
            effective_date=date.today().isoformat(),
        )

    def _validate(
        self,
        sv: Student,
        exclude_mssv: str = "",
    ) -> str:
        sv.mssv = (sv.mssv or "").strip()
        sv.hoTen = " ".join((sv.hoTen or "").split())
        sv.maLop = (sv.maLop or "").strip()
        sv.ngaySinh = (sv.ngaySinh or "").strip()
        sv.gioiTinh = (sv.gioiTinh or "").strip()
        sv.email = (sv.email or "").strip().lower()
        sv.soDienThoai = re.sub(
            r"\s+",
            "",
            (sv.soDienThoai or "").strip(),
        )

        if not sv.mssv or not sv.mssv.isdigit():
            return "MSSV chỉ được chứa chữ số và không được để trống"
        if len(sv.hoTen) < 3:
            return "Họ tên phải có ít nhất 3 ký tự"
        if not re.fullmatch(r"[^\W\d_]+(?:\s+[^\W\d_]+)*", sv.hoTen):
            return "Họ tên chỉ được chứa chữ cái và khoảng trắng"
        if not sv.maLop:
            return "Vui lòng chọn lớp"
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", sv.ngaySinh):
            return "Ngày sinh không đúng định dạng DD/MM/YYYY"
        try:
            parsed = datetime.strptime(sv.ngaySinh, "%d/%m/%Y")
        except ValueError:
            return "Ngày sinh không tồn tại"
        if parsed.year < 1900 or parsed > datetime.now():
            return "Ngày sinh phải từ năm 1900 đến hiện tại"
        if sv.gioiTinh not in {"Nam", "Nữ", "Khác"}:
            return "Giới tính không hợp lệ"
        if not re.fullmatch(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
            sv.email,
        ):
            return "Email không đúng định dạng"
        if not re.fullmatch(r"(0[2-9])\d{8,9}", sv.soDienThoai):
            return (
                "Số điện thoại không hợp lệ "
                "(bắt đầu bằng 0, gồm 10-11 chữ số)"
            )

        with self.db.conn() as connection:
            if not connection.execute(
                "SELECT 1 FROM LopHoc WHERE maLop = ?",
                (sv.maLop,),
            ).fetchone():
                return "Lớp được chọn không tồn tại"
            duplicate = connection.execute(
                """
                SELECT 1
                FROM SinhVien
                WHERE mssv <> ?
                  AND (
                      mssv = ?
                      OR lower(email) = lower(?)
                      OR soDienThoai = ?
                  )
                """,
                (
                    exclude_mssv,
                    sv.mssv,
                    sv.email,
                    sv.soDienThoai,
                ),
            ).fetchone()
            if duplicate:
                return "MSSV, email hoặc số điện thoại đã được sử dụng"
        return ""

    @staticmethod
    def _integrity_message(
        exc: sqlite3.IntegrityError,
        mssv: str,
    ) -> str:
        text = str(exc).lower()
        if "sinhvien.mssv" in text:
            return f"MSSV '{mssv}' đã tồn tại"
        if "sinhvien.email" in text:
            return "Email đã được sử dụng bởi sinh viên khác"
        if "sinhvien.sodienthoai" in text:
            return "Số điện thoại đã được sử dụng bởi sinh viên khác"
        if "lam sai lich su" in text:
            return (
                "Không thể kết thúc đăng ký vì sẽ làm sai lịch sử điểm danh"
            )
        if "xoa dang ky da co lich su" in text:
            return (
                "Không thể hủy đăng ký vì đã có lịch sử điểm danh hoặc vắng"
            )
        if "du lieu hoc vu" in text:
            return (
                "Sinh viên đã có dữ liệu học vụ nên không thể xóa vĩnh viễn"
            )
        if "foreign key constraint failed" in text:
            return "Lớp hoặc dữ liệu liên kết không tồn tại"
        return "Không thể lưu sinh viên do ràng buộc dữ liệu"

    def _email_exists(
        self,
        email: str,
        exclude_mssv: str = "",
    ) -> bool:
        with self.db.conn() as connection:
            return connection.execute(
                """
                SELECT 1 FROM SinhVien
                WHERE lower(email) = lower(?) AND mssv <> ?
                """,
                (email, exclude_mssv),
            ).fetchone() is not None

    def _phone_exists(
        self,
        phone: str,
        exclude_mssv: str = "",
    ) -> bool:
        with self.db.conn() as connection:
            return connection.execute(
                """
                SELECT 1 FROM SinhVien
                WHERE soDienThoai = ? AND mssv <> ?
                """,
                (phone, exclude_mssv),
            ).fetchone() is not None
