import re
import sqlite3

from core.database import Database


class ClassService:
    """Quản lý lớp hành chính; API ngoài vẫn dùng username của GVCN."""

    BASE_SELECT = """
        SELECT lh.maLop,
               lh.tenLop,
               lh.khoaHoc,
               lh.khoa,
               COALESCE(tk.username, '') AS gvChuNhiem,
               COALESCE(tk.hoTen, '') AS gvChuNhiemTen,
               (
                   SELECT COUNT(*)
                   FROM SinhVien sv
                   WHERE sv.maLop = lh.maLop
                     AND sv.trangThai = 'DANG_HOC'
               ) AS siSo
        FROM LopHoc lh
        LEFT JOIN GiangVien gv
          ON gv.id = lh.giangVienChuNhiemId
        LEFT JOIN TaiKhoan tk
          ON tk.id = gv.taiKhoanId
    """

    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> list[dict]:
        with self.db.conn() as connection:
            rows = connection.execute(
                self.BASE_SELECT + " ORDER BY lh.maLop"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_one(self, ma_lop: str) -> dict | None:
        with self.db.conn() as connection:
            row = connection.execute(
                self.BASE_SELECT + " WHERE lh.maLop = ?",
                ((ma_lop or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _lecturer_id(connection, username: str) -> int | None:
        if not username:
            return None
        row = connection.execute(
            """
            SELECT gv.id
            FROM GiangVien gv
            JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
            WHERE tk.username = ?
              AND tk.vaiTro = 'GiangVien'
              AND tk.isActive = 1
            """,
            (username,),
        ).fetchone()
        return int(row["id"]) if row else None

    @staticmethod
    def _validate(
        ma_lop: str,
        ten_lop: str,
        khoa_hoc: str,
        khoa: str,
    ) -> str:
        if not ma_lop:
            return "Mã lớp không được để trống"
        if not re.fullmatch(r"[A-Z0-9]+", ma_lop):
            return "Mã lớp chỉ gồm chữ in hoa và số"
        if not ten_lop:
            return "Tên lớp không được để trống"
        if not re.fullmatch(r"[A-Z0-9]+", ten_lop):
            return "Tên lớp chỉ gồm chữ in hoa và số"
        if not re.fullmatch(r"\d{4}", khoa_hoc):
            return "Khóa học phải gồm đúng 4 chữ số"
        if not khoa:
            return "Khoa không được để trống"
        if not re.fullmatch(r"[^\W\d_]+(?:\s+[^\W\d_]+)*", khoa):
            return "Khoa chỉ được chứa chữ cái và khoảng trắng"
        return ""

    @staticmethod
    def _integrity_message(
        exc: sqlite3.IntegrityError,
        ma_lop: str,
        ten_lop: str,
    ) -> tuple[bool, str]:
        text = str(exc).lower()
        if "lophoc.malop" in text:
            return False, f"Mã lớp '{ma_lop}' đã tồn tại"
        if "lophoc.tenlop" in text:
            return False, f"Tên lớp '{ten_lop}' đã tồn tại"
        if "foreign key constraint failed" in text:
            return False, "Giảng viên chủ nhiệm không tồn tại"
        if "giang vien chu nhiem" in text:
            return False, (
                "Giảng viên chủ nhiệm không hợp lệ hoặc đã bị vô hiệu hóa"
            )
        return False, "Không thể lưu lớp học do ràng buộc dữ liệu"

    def add(
        self,
        maLop: str,
        tenLop: str,
        khoaHoc: str = "",
        khoa: str = "",
        gv_chu_nhiem: str = "",
    ) -> tuple[bool, str]:
        maLop = (maLop or "").strip().upper()
        tenLop = (tenLop or "").strip().upper()
        khoaHoc = (khoaHoc or "").strip()
        khoa = " ".join((khoa or "").split())
        gv_chu_nhiem = (gv_chu_nhiem or "").strip()

        error = self._validate(maLop, tenLop, khoaHoc, khoa)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                lecturer_id = self._lecturer_id(
                    connection,
                    gv_chu_nhiem,
                )
                if gv_chu_nhiem and lecturer_id is None:
                    return False, (
                        "Giảng viên chủ nhiệm không hợp lệ "
                        "hoặc đã bị vô hiệu hóa"
                    )
                connection.execute(
                    """
                    INSERT INTO LopHoc (
                        maLop, tenLop, khoaHoc, khoa,
                        giangVienChuNhiemId
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        maLop,
                        tenLop,
                        khoaHoc,
                        khoa,
                        lecturer_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return self._integrity_message(exc, maLop, tenLop)
        return True, "Thêm lớp học thành công"

    def update(
        self,
        old_ma_lop: str,
        maLop: str,
        tenLop: str,
        khoaHoc: str = "",
        khoa: str = "",
        gv_chu_nhiem: str = "",
    ) -> tuple[bool, str]:
        old_ma_lop = (old_ma_lop or "").strip()
        maLop = (maLop or "").strip().upper()
        tenLop = (tenLop or "").strip().upper()
        khoaHoc = (khoaHoc or "").strip()
        khoa = " ".join((khoa or "").split())
        gv_chu_nhiem = (gv_chu_nhiem or "").strip()

        if not old_ma_lop:
            return False, "Không xác định được mã lớp cũ"
        error = self._validate(maLop, tenLop, khoaHoc, khoa)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                lecturer_id = self._lecturer_id(
                    connection,
                    gv_chu_nhiem,
                )
                if gv_chu_nhiem and lecturer_id is None:
                    return False, (
                        "Giảng viên chủ nhiệm không hợp lệ "
                        "hoặc đã bị vô hiệu hóa"
                    )

                cursor = connection.execute(
                    """
                    UPDATE LopHoc
                    SET maLop = ?, tenLop = ?, khoaHoc = ?, khoa = ?,
                        giangVienChuNhiemId = ?,
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE maLop = ?
                    """,
                    (
                        maLop,
                        tenLop,
                        khoaHoc,
                        khoa,
                        lecturer_id,
                        old_ma_lop,
                    ),
                )
                if cursor.rowcount == 0:
                    return False, "Không tìm thấy lớp học"
        except sqlite3.IntegrityError as exc:
            return self._integrity_message(exc, maLop, tenLop)
        return True, "Cập nhật lớp học thành công"

    def delete(self, maLop: str) -> tuple[bool, str]:
        maLop = (maLop or "").strip()
        with self.db.conn() as connection:
            row = connection.execute(
                "SELECT 1 FROM LopHoc WHERE maLop = ?",
                (maLop,),
            ).fetchone()
            if not row:
                return False, "Không tìm thấy lớp học"

            student_count = connection.execute(
                "SELECT COUNT(*) FROM SinhVien WHERE maLop = ?",
                (maLop,),
            ).fetchone()[0]
            if student_count:
                return False, (
                    f"Không thể xóa: lớp còn {student_count} sinh viên"
                )
            connection.execute(
                "DELETE FROM LopHoc WHERE maLop = ?",
                (maLop,),
            )
        return True, "Xóa lớp thành công"
