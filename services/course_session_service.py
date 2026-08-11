import sqlite3
from dataclasses import dataclass
from datetime import date, time

from core.database import Database
from services.session_service import KHUNG_GIO, compute_ca_status


@dataclass
class CaHoc:
    lopHocPhanId: int
    tenCa: str
    ngayHoc: str
    phongHoc: str
    gioBatDau: str
    gioKetThuc: str
    nguoiTao: str = ""
    trangThai: str = "ChuaMo"
    id: int = 0


def _to_time(value: str) -> time | None:
    try:
        hour, minute = map(int, (value or "").split(":"))
        return time(hour, minute)
    except (TypeError, ValueError):
        return None


class CourseSessionService:
    """
    Quản lý ca học theo lớp học phần.

    Các phương thức truy vấn vẫn trả về maLop, tenLop, maMon và tenMon
    để TabAttendance, TabHistory và TabReport cũ tiếp tục sử dụng được.
    Trong ngữ cảnh mới:

    - maLop là mã lớp học phần.
    - tenLop là tên lớp học phần.
    """

    VALID_STATUSES = {
        "ChuaMo",
        "DangDienRa",
        "DaKetThuc",
    }

    BASE_SELECT = """
        SELECT ca.*,
               COALESCE(creator.username, '') AS nguoiTao,
               lhp.maLopHocPhan AS maLop,
               lhp.tenLopHocPhan AS tenLop,
               lhp.maMon,
               lhp.nhom,
               COALESCE(tk.username, '') AS giangVienUsername,
               mh.tenMon,
               hk.id AS hocKyId,
               hk.tenHocKy,
               hk.ngayBatDau AS hocKyBatDau,
               hk.ngayKetThuc AS hocKyKetThuc,
               nh.id AS namHocId,
               nh.tenNamHoc,
               COALESCE(tk.hoTen, '') AS giangVienHoTen
        FROM CaHoc ca
        JOIN LopHocPhan lhp
          ON lhp.id = ca.lopHocPhanId
        JOIN MonHoc mh
          ON mh.maMon = lhp.maMon
        JOIN HocKy hk
          ON hk.id = lhp.hocKyId
        JOIN NamHoc nh
          ON nh.id = hk.namHocId
        LEFT JOIN GiangVien gv
          ON gv.id = lhp.giangVienId
        LEFT JOIN TaiKhoan tk
          ON tk.id = gv.taiKhoanId
        LEFT JOIN TaiKhoan creator
          ON creator.id = ca.nguoiTaoTaiKhoanId
    """

    ATTENDANCE_CONTEXT_SQL = """
        SELECT ca.id,
               ca.trangThai AS caHocTrangThai,
               ca.daMoDiemDanh,
               lhp.trangThai AS lopHocPhanTrangThai,
               lhp.giangVienId,
               COALESCE(tk.vaiTro, '') AS giangVienVaiTro,
               COALESCE(tk.isActive, 0) AS giangVienIsActive
        FROM CaHoc ca
        JOIN LopHocPhan lhp
          ON lhp.id = ca.lopHocPhanId
        LEFT JOIN GiangVien gv
          ON gv.id = lhp.giangVienId
        LEFT JOIN TaiKhoan tk
          ON tk.id = gv.taiKhoanId
        WHERE ca.id = ?
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _attendance_guard_error(
        session,
        require_open: bool = False,
    ) -> str:
        if session is None:
            return "Không tìm thấy ca học"

        section_status = session["lopHocPhanTrangThai"]

        if section_status == "DA_HUY":
            return (
                "Lớp học phần đã bị hủy, "
                "không thể điểm danh"
            )

        if section_status == "DA_KET_THUC":
            return (
                "Lớp học phần đã kết thúc, "
                "không thể mở điểm danh"
            )

        if session["giangVienId"] is None:
            return (
                "Lớp học phần chưa được phân công "
                "giảng viên"
            )

        if (
            session["giangVienVaiTro"] != "GiangVien"
            or session["giangVienIsActive"] != 1
        ):
            return (
                "Giảng viên được phân công không hợp lệ "
                "hoặc tài khoản đã bị khóa"
            )

        if require_open and (
            session["caHocTrangThai"] != "DangDienRa"
            or session["daMoDiemDanh"] != 1
        ):
            return "Ca học chưa được mở điểm danh"

        return ""

    def validate_attendance_session(
        self,
        ca_id: int,
        require_open: bool = True,
    ) -> tuple[bool, str]:
        try:
            ca_id = int(ca_id)
        except (TypeError, ValueError):
            return False, "Ca học không hợp lệ"

        if ca_id <= 0:
            return False, "Ca học không hợp lệ"

        with self.db.conn() as connection:
            session = connection.execute(
                self.ATTENDANCE_CONTEXT_SQL,
                (ca_id,),
            ).fetchone()

        error = self._attendance_guard_error(
            session,
            require_open=require_open,
        )
        if error:
            return False, error

        return True, "Ca học đủ điều kiện điểm danh"

    @staticmethod
    def _account_id(connection, username: str) -> int | None:
        username = (username or "").strip()
        if not username:
            return None
        row = connection.execute(
            """
            SELECT id FROM TaiKhoan
            WHERE username = ?
              AND isActive = 1
              AND vaiTro IN ('Admin', 'GiangVien')
            """,
            (username,),
        ).fetchone()
        return int(row["id"]) if row else None

    # ------------------------------------------------------------------
    # MÔN HỌC - API tương thích với TabReport cũ
    # ------------------------------------------------------------------
    def get_all_mon(self) -> list[dict]:
        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM MonHoc
                ORDER BY maMon
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def get_subjects_for_class(
        self,
        ma_lop: str,
    ) -> list[dict]:
        """
        Lấy môn học của lớp học phần.

        Một LopHocPhan chỉ thuộc một MonHoc nên thông thường danh sách
        trả về có tối đa một phần tử.
        """

        ma_lop = (ma_lop or "").strip()
        if not ma_lop:
            return []

        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT mh.*
                FROM MonHoc mh
                JOIN LopHocPhan lhp
                  ON lhp.maMon = mh.maMon
                WHERE lower(lhp.maLopHocPhan) = lower(?)
                ORDER BY mh.maMon
                """,
                (ma_lop,),
            ).fetchall()

        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # TẠO, SỬA, XÓA CA HỌC
    # ------------------------------------------------------------------
    def create_ca(
        self,
        ca: CaHoc,
    ) -> tuple[int, str]:
        error = self._validate_ca(ca)
        if error:
            return -1, error

        conflict = self._find_schedule_conflict(
            ca.lopHocPhanId,
            ca.ngayHoc,
            ca.gioBatDau,
            ca.gioKetThuc,
            ca.phongHoc,
        )
        if conflict:
            return -1, self._format_conflict(conflict)

        try:
            with self.db.conn() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO CaHoc (
                        lopHocPhanId,
                        tenCa,
                        ngayHoc,
                        phongHoc,
                        gioBatDau,
                        gioKetThuc,
                        trangThai,
                        nguoiTaoTaiKhoanId
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'ChuaMo', ?)
                    """,
                    (
                        ca.lopHocPhanId,
                        ca.tenCa,
                        ca.ngayHoc,
                        ca.phongHoc,
                        ca.gioBatDau,
                        ca.gioKetThuc,
                        self._account_id(connection, ca.nguoiTao),
                    ),
                )
                new_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            return -1, self._integrity_message(exc)

        return new_id, "Tạo ca học thành công"

    def update_ca(
        self,
        ca: CaHoc,
    ) -> tuple[bool, str]:
        if ca.id <= 0:
            return False, "Ca học không hợp lệ"

        with self.db.conn() as connection:
            current = connection.execute(
                """
                SELECT trangThai, daMoDiemDanh
                FROM CaHoc
                WHERE id = ?
                """,
                (ca.id,),
            ).fetchone()

        if not current:
            return False, "Không tìm thấy ca học"

        if (
            current["trangThai"] != "ChuaMo"
            or current["daMoDiemDanh"] == 1
        ):
            return (
                False,
                "Chỉ có thể sửa ca học chưa mở điểm danh",
            )

        error = self._validate_ca(ca)
        if error:
            return False, error

        conflict = self._find_schedule_conflict(
            ca.lopHocPhanId,
            ca.ngayHoc,
            ca.gioBatDau,
            ca.gioKetThuc,
            ca.phongHoc,
            exclude_id=ca.id,
        )
        if conflict:
            return False, self._format_conflict(conflict)

        try:
            with self.db.conn() as connection:
                cursor = connection.execute(
                    """
                    UPDATE CaHoc
                    SET lopHocPhanId = ?,
                        tenCa = ?,
                        ngayHoc = ?,
                        phongHoc = ?,
                        gioBatDau = ?,
                        gioKetThuc = ?
                    WHERE id = ?
                    """,
                    (
                        ca.lopHocPhanId,
                        ca.tenCa,
                        ca.ngayHoc,
                        ca.phongHoc,
                        ca.gioBatDau,
                        ca.gioKetThuc,
                        ca.id,
                    ),
                )

                if cursor.rowcount == 0:
                    return False, "Không tìm thấy ca học"
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật ca học thành công"

    def delete_ca(
        self,
        ca_id: int,
    ) -> tuple[bool, str]:
        with self.db.conn() as connection:
            session = connection.execute(
                """
                SELECT id, daMoDiemDanh
                FROM CaHoc
                WHERE id = ?
                """,
                (ca_id,),
            ).fetchone()

            if not session:
                return False, "Không tìm thấy ca học"

            attendance_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM DiemDanh
                WHERE caHocId = ?
                """,
                (ca_id,),
            ).fetchone()[0]

            if attendance_count > 0:
                return (
                    False,
                    "Không thể xóa: ca học đã có "
                    f"{attendance_count} lượt điểm danh",
                )

            if session["daMoDiemDanh"] == 1:
                return (
                    False,
                    "Không thể xóa ca học đã từng mở điểm danh. "
                    "Hãy giữ lại để bảo toàn lịch sử vắng mặt.",
                )

            connection.execute(
                "DELETE FROM CaHoc WHERE id = ?",
                (ca_id,),
            )

        return True, "Xóa ca học thành công"

    # ------------------------------------------------------------------
    # TRẠNG THÁI CA HỌC
    # ------------------------------------------------------------------
    def set_status(
        self,
        ca_id: int,
        trang_thai: str,
    ) -> tuple[bool, str]:
        if trang_thai not in self.VALID_STATUSES:
            return (
                False,
                f"Trạng thái ca học không hợp lệ: {trang_thai}",
            )

        try:
            with self.db.conn() as connection:
                session = connection.execute(
                    self.ATTENDANCE_CONTEXT_SQL,
                    (ca_id,),
                ).fetchone()

                if session is None:
                    return False, "Không tìm thấy ca học"

                if trang_thai == "DangDienRa":
                    if (
                        session["caHocTrangThai"]
                        == "DaKetThuc"
                    ):
                        return (
                            False,
                            "Ca học đã kết thúc, không thể mở lại",
                        )

                    error = self._attendance_guard_error(
                        session,
                        require_open=False,
                    )
                    if error:
                        return False, error

                    connection.execute(
                        """
                        UPDATE CaHoc
                        SET trangThai = 'DangDienRa',
                            daMoDiemDanh = 1
                        WHERE id = ?
                        """,
                        (ca_id,),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE CaHoc
                        SET trangThai = ?
                        WHERE id = ?
                        """,
                        (trang_thai, ca_id),
                    )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, f"Đã cập nhật trạng thái: {trang_thai}"

    def sync_status(
        self,
        ca_id: int,
    ) -> str:
        """
        Chỉ tự động kết thúc ca đã qua giờ.

        Không tự mở ca vì thao tác mở điểm danh phải do người có quyền
        chủ động thực hiện.
        """

        session = self.get_ca_by_id(ca_id)
        if not session:
            return "ChuaMo"

        current_status = session.get("trangThai", "ChuaMo")

        if current_status == "DaKetThuc":
            return current_status

        computed_status = compute_ca_status(
            session.get("ngayHoc", ""),
            session.get("gioBatDau", ""),
            session.get("gioKetThuc", ""),
        )

        if computed_status == "DaKetThuc":
            self.set_status(ca_id, "DaKetThuc")
            return "DaKetThuc"

        return current_status

    # ------------------------------------------------------------------
    # TRUY VẤN
    # ------------------------------------------------------------------
    def get_ca_by_id(
        self,
        ca_id: int,
    ) -> dict | None:
        with self.db.conn() as connection:
            row = connection.execute(
                self.BASE_SELECT + """
                    WHERE ca.id = ?
                """,
                (ca_id,),
            ).fetchone()

        return dict(row) if row else None

    def get_ca_by_lop(
        self,
        ma_lop: str,
        ngay: str = "",
    ) -> list[dict]:
        """
        API tương thích giao diện cũ.

        ma_lop trong phương thức này là maLopHocPhan.
        """

        ma_lop = (ma_lop or "").strip()
        if not ma_lop:
            return []

        sql = self.BASE_SELECT + """
            WHERE lower(lhp.maLopHocPhan) = lower(?)
        """
        params = [ma_lop]

        if ngay:
            sql += " AND ca.ngayHoc = ?"
            params.append(ngay)

        sql += """
            ORDER BY ca.ngayHoc DESC,
                     ca.gioBatDau ASC,
                     ca.id DESC
        """

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def get_all_ca(
        self,
        ma_lop: str = "",
        ngay_from: str = "",
        ngay_to: str = "",
        trang_thai: str = "",
    ) -> list[dict]:
        sql = self.BASE_SELECT + """
            WHERE 1 = 1
        """
        params = []

        if ma_lop:
            sql += """
                AND lower(lhp.maLopHocPhan) = lower(?)
            """
            params.append(ma_lop.strip())

        if ngay_from:
            sql += " AND ca.ngayHoc >= ?"
            params.append(ngay_from)

        if ngay_to:
            sql += " AND ca.ngayHoc <= ?"
            params.append(ngay_to)

        if trang_thai:
            sql += " AND ca.trangThai = ?"
            params.append(trang_thai)

        sql += """
            ORDER BY ca.ngayHoc DESC,
                     ca.gioBatDau ASC,
                     ca.id DESC
        """

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------
    def _validate_ca(
        self,
        ca: CaHoc,
    ) -> str:
        try:
            ca.lopHocPhanId = int(ca.lopHocPhanId)
        except (TypeError, ValueError):
            return "Lớp học phần không hợp lệ"

        ca.tenCa = " ".join((ca.tenCa or "").split())
        ca.phongHoc = " ".join((ca.phongHoc or "").split())
        ca.nguoiTao = (ca.nguoiTao or "").strip()

        if ca.lopHocPhanId <= 0:
            return "Vui lòng chọn lớp học phần"

        if not ca.tenCa:
            return "Tên ca học không được để trống"

        if not ca.ngayHoc:
            return "Vui lòng chọn ngày học"

        try:
            date.fromisoformat(ca.ngayHoc)
        except (TypeError, ValueError):
            return "Ngày học không hợp lệ"

        if not ca.phongHoc:
            return "Phòng học không được để trống"

        start_time = _to_time(ca.gioBatDau)
        end_time = _to_time(ca.gioKetThuc)

        if start_time is None:
            return "Giờ bắt đầu không hợp lệ"

        if end_time is None:
            return "Giờ kết thúc không hợp lệ"

        if start_time >= end_time:
            return "Giờ bắt đầu phải trước giờ kết thúc"

        with self.db.conn() as connection:
            section = connection.execute(
                """
                SELECT lhp.id,
                       lhp.trangThai,
                       hk.ngayBatDau,
                       hk.ngayKetThuc
                FROM LopHocPhan lhp
                JOIN HocKy hk ON hk.id = lhp.hocKyId
                WHERE lhp.id = ?
                """,
                (ca.lopHocPhanId,),
            ).fetchone()

            creator = self._account_id(
                connection,
                ca.nguoiTao,
            )

        if not section:
            return "Lớp học phần không tồn tại"

        if section["trangThai"] == "DA_HUY":
            return "Không thể tạo ca cho lớp học phần đã hủy"

        if section["trangThai"] == "DA_KET_THUC":
            return "Không thể tạo ca cho lớp học phần đã kết thúc"

        if not (
            section["ngayBatDau"]
            <= ca.ngayHoc
            <= section["ngayKetThuc"]
        ):
            return "Ngày học phải nằm trong thời gian của học kỳ"

        if ca.nguoiTao and not creator:
            return "Người tạo ca không tồn tại hoặc đã bị khóa"

        return ""

    def _find_schedule_conflict(
        self,
        section_id: int,
        ngay_hoc: str,
        gio_bat_dau: str,
        gio_ket_thuc: str,
        phong_hoc: str,
        exclude_id: int = 0,
    ) -> dict | None:
        with self.db.conn() as connection:
            section_conflict = connection.execute(
                """
                SELECT ca.id,
                       ca.tenCa,
                       ca.gioBatDau,
                       ca.gioKetThuc,
                       lhp.maLopHocPhan
                FROM CaHoc ca
                JOIN LopHocPhan lhp
                  ON lhp.id = ca.lopHocPhanId
                WHERE ca.lopHocPhanId = ?
                  AND ca.ngayHoc = ?
                  AND ca.id <> ?
                  AND ca.gioBatDau < ?
                  AND ca.gioKetThuc > ?
                LIMIT 1
                """,
                (
                    section_id,
                    ngay_hoc,
                    exclude_id,
                    gio_ket_thuc,
                    gio_bat_dau,
                ),
            ).fetchone()

            if section_conflict:
                result = dict(section_conflict)
                result["loaiXungDot"] = "lop_hoc_phan"
                return result

            room_conflict = connection.execute(
                """
                SELECT ca.id,
                       ca.tenCa,
                       ca.gioBatDau,
                       ca.gioKetThuc,
                       lhp.maLopHocPhan
                FROM CaHoc ca
                JOIN LopHocPhan lhp
                  ON lhp.id = ca.lopHocPhanId
                WHERE lower(trim(ca.phongHoc))
                        = lower(trim(?))
                  AND ca.ngayHoc = ?
                  AND ca.id <> ?
                  AND ca.gioBatDau < ?
                  AND ca.gioKetThuc > ?
                LIMIT 1
                """,
                (
                    phong_hoc,
                    ngay_hoc,
                    exclude_id,
                    gio_ket_thuc,
                    gio_bat_dau,
                ),
            ).fetchone()

            if room_conflict:
                result = dict(room_conflict)
                result["loaiXungDot"] = "phong_hoc"
                return result

            lecturer_conflict = connection.execute(
                """
                SELECT existing.id,
                       existing.tenCa,
                       existing.gioBatDau,
                       existing.gioKetThuc,
                       existing_lhp.maLopHocPhan,
                       COALESCE(tk.username, '') AS giangVienUsername,
                       COALESCE(tk.hoTen, '') AS giangVienHoTen
                FROM LopHocPhan selected
                JOIN LopHocPhan existing_lhp
                  ON existing_lhp.giangVienId = selected.giangVienId
                JOIN CaHoc existing
                  ON existing.lopHocPhanId = existing_lhp.id
                LEFT JOIN GiangVien gv
                  ON gv.id = selected.giangVienId
                LEFT JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE selected.id = ?
                  AND selected.giangVienId IS NOT NULL
                  AND existing.ngayHoc = ?
                  AND existing.id <> ?
                  AND existing.gioBatDau < ?
                  AND existing.gioKetThuc > ?
                LIMIT 1
                """,
                (
                    section_id,
                    ngay_hoc,
                    exclude_id,
                    gio_ket_thuc,
                    gio_bat_dau,
                ),
            ).fetchone()

            if lecturer_conflict:
                result = dict(lecturer_conflict)
                result["loaiXungDot"] = "giang_vien"
                return result

        return None

    @staticmethod
    def _format_conflict(
        conflict: dict,
    ) -> str:
        session_text = (
            f"'{conflict.get('tenCa', 'Ca học')}' "
            f"({conflict.get('gioBatDau', '')}–"
            f"{conflict.get('gioKetThuc', '')})"
        )
        section_code = conflict.get("maLopHocPhan", "")

        if conflict.get("loaiXungDot") == "phong_hoc":
            return (
                f"Phòng học đang được lớp {section_code} sử dụng "
                f"trong {session_text}"
            )

        if conflict.get("loaiXungDot") == "giang_vien":
            lecturer_name = (
                conflict.get("giangVienHoTen")
                or conflict.get("giangVienUsername")
                or "Giảng viên"
            )
            return (
                f"Giảng viên {lecturer_name} đã có lịch dạy "
                f"lớp {section_code} trong {session_text}"
            )

        return (
            f"Lớp học phần đã có {session_text} "
            "giao với khung giờ được chọn"
        )

    @staticmethod
    def _integrity_message(
        exc: sqlite3.IntegrityError,
    ) -> str:
        error = str(exc).lower()

        if "lop hoc phan bi trung khung gio" in error:
            return "Lớp học phần bị trùng khung giờ"

        if "phong hoc bi trung khung gio" in error:
            return "Phòng học đang được sử dụng trong khung giờ này"

        if "giang vien bi trung lich" in error:
            return "Giảng viên đã có lịch dạy trong khung giờ này"

        if "ngay hoc phai nam" in error:
            return "Ngày học phải nằm trong thời gian của học kỳ"

        if "chua san sang de mo diem danh" in error:
            return (
                "Lớp học phần chưa được phân công "
                "giảng viên đang hoạt động"
            )

        if "foreign key constraint failed" in error:
            return (
                "Lớp học phần hoặc người tạo ca không tồn tại "
                "hoặc không hợp lệ"
            )

        if "check constraint failed" in error:
            return "Thông tin ca học không đáp ứng ràng buộc dữ liệu"

        return "Không thể lưu ca học do ràng buộc cơ sở dữ liệu"