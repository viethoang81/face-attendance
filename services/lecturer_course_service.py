from __future__ import annotations

import unicodedata

from core.database import Database
from services.academic_service import (
    REGISTRATION_STATUSES,
)


_ALLOWED_REGISTRATION_FILTERS = frozenset(
    REGISTRATION_STATUSES | {""}
)


class LecturerCourseService:
    """
    Cung cấp dữ liệu chỉ đọc về các lớp học phần
    được phân công cho giảng viên đang đăng nhập.
    """

    def __init__(
        self,
        db: Database,
        current_user: dict,
    ):
        self.db = db
        # Tạo bản sao để danh tính không bị thay đổi từ bên ngoài.
        self.current_user = dict(current_user or {})

    @property
    def username(self) -> str:
        return str(
            self.current_user.get("username", "") or ""
        ).strip()

    @property
    def is_lecturer(self) -> bool:
        return (
            self.current_user.get("vaiTro") == "GiangVien"
            and bool(self.username)
        )

    @staticmethod
    def _to_section_id(value) -> int:
        try:
            section_id = int(value)
        except (TypeError, ValueError):
            return 0

        return section_id if section_id > 0 else 0

    @staticmethod
    def _search_value(value) -> str:
        """
        Chuẩn hóa Unicode và chữ hoa/thường.

        Tìm kiếm được xử lý sau khi SQL đã phân quyền,
        do đó %, _ và \\ được coi là ký tự bình thường.
        """
        return unicodedata.normalize(
            "NFKC",
            str(value or ""),
        ).casefold()

    def list_assigned_sections(self) -> list[dict]:
        if not self.is_lecturer:
            return []

        sql = """
            SELECT lhp.id AS lopHocPhanId,
                   lhp.maLopHocPhan,
                   lhp.tenLopHocPhan,
                   lhp.maMon,
                   mh.tenMon,
                   mh.soTiet,
                   mh.tiLeToiThieu,
                   lhp.hocKyId,
                   hk.tenHocKy,
                   nh.tenNamHoc,
                   lhp.nhom,
                   lhp.siSoToiDa,
                   lhp.trangThai
                       AS lopHocPhanTrangThai,
                   COUNT(dk.id) AS tongDangKy,
                   COUNT(
                       CASE
                           WHEN dk.trangThai = 'DANG_HOC'
                           THEN 1
                       END
                   ) AS siSoHienTai
            FROM LopHocPhan lhp
            JOIN GiangVien gv
              ON gv.id = lhp.giangVienId
            JOIN TaiKhoan tk
              ON tk.id = gv.taiKhoanId
            JOIN MonHoc mh
              ON mh.maMon = lhp.maMon
            JOIN HocKy hk
              ON hk.id = lhp.hocKyId
            JOIN NamHoc nh
              ON nh.id = hk.namHocId
            LEFT JOIN DangKyHocPhan dk
              ON dk.lopHocPhanId = lhp.id
            WHERE tk.username = ?
              AND tk.vaiTro = 'GiangVien'
              AND tk.isActive = 1
              AND lhp.trangThai <> 'DA_HUY'
            GROUP BY lhp.id
            ORDER BY nh.ngayBatDau DESC,
                     hk.ngayBatDau DESC,
                     lhp.maLopHocPhan
        """

        with self.db.conn() as connection:
            rows = connection.execute(
                sql,
                (self.username,),
            ).fetchall()

        return [dict(row) for row in rows]

    def can_access_section(
        self,
        section_id: int,
    ) -> bool:
        """
        Dùng cho kiểm thử hoặc các chức năng bổ sung sau này.

        list_section_students() vẫn tự kiểm tra quyền
        trong cùng câu SQL, không dựa vào hàm này.
        """
        section_id = self._to_section_id(section_id)

        if not self.is_lecturer or not section_id:
            return False

        with self.db.conn() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM LopHocPhan lhp
                JOIN GiangVien gv
                  ON gv.id = lhp.giangVienId
                JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE lhp.id = ?
                  AND tk.username = ?
                  AND tk.vaiTro = 'GiangVien'
                  AND tk.isActive = 1
                  AND lhp.trangThai <> 'DA_HUY'
                """,
                (
                    section_id,
                    self.username,
                ),
            ).fetchone()

        return row is not None

    def list_section_students(
        self,
        section_id: int,
        keyword: str = "",
        registration_status: str = "",
    ) -> list[dict]:
        section_id = self._to_section_id(section_id)
        keyword = " ".join(
            str(keyword or "").split()
        )
        registration_status = str(
            registration_status or ""
        ).strip()

        if not self.is_lecturer or not section_id:
            return []

        if (
            registration_status
            not in _ALLOWED_REGISTRATION_FILTERS
        ):
            raise ValueError(
                "Trạng thái đăng ký không hợp lệ"
            )

        sql = """
            SELECT dk.id AS dangKyId,
                   sv.mssv,
                   sv.hoTen,
                   sv.maLop,
                   lh.tenLop,
                   sv.trangThai
                       AS sinhVienTrangThai,
                   dk.ngayDangKy,
                   dk.ngayKetThuc,
                   dk.trangThai
                       AS dangKyTrangThai,
                   lhp.maLopHocPhan,
                   lhp.tenLopHocPhan,
                   lhp.maMon,
                   mh.tenMon,
                   lhp.trangThai
                       AS lopHocPhanTrangThai,
                   EXISTS (
                       SELECT 1
                       FROM MauKhuonMat mkm
                       WHERE mkm.mssv = sv.mssv
                         AND mkm.isActive = 1
                   ) AS coKhuonMat
            FROM LopHocPhan lhp
            JOIN GiangVien gv
              ON gv.id = lhp.giangVienId
            JOIN TaiKhoan tk
              ON tk.id = gv.taiKhoanId
            JOIN DangKyHocPhan dk
              ON dk.lopHocPhanId = lhp.id
            JOIN SinhVien sv
              ON sv.mssv = dk.mssv
            JOIN LopHoc lh
              ON lh.maLop = sv.maLop
            JOIN MonHoc mh
              ON mh.maMon = lhp.maMon
            WHERE lhp.id = ?
              AND tk.username = ?
              AND tk.vaiTro = 'GiangVien'
              AND tk.isActive = 1
              AND lhp.trangThai <> 'DA_HUY'
        """

        params = [
            section_id,
            self.username,
        ]

        if registration_status:
            sql += " AND dk.trangThai = ?"
            params.append(registration_status)

        sql += """
            ORDER BY sv.hoTen COLLATE NOCASE,
                     sv.mssv
        """

        with self.db.conn() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    sql,
                    params,
                ).fetchall()
            ]

        if not keyword:
            return rows

        needle = self._search_value(keyword)

        return [
            row
            for row in rows
            if (
                needle
                in self._search_value(row["mssv"])
                or needle
                in self._search_value(row["hoTen"])
            )
        ]