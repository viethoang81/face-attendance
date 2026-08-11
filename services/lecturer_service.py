from core.database import Database


class LecturerService:
    """Phân quyền chủ nhiệm; username chỉ là khóa giao tiếp với UI."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _lecturer_id(connection, username: str) -> int | None:
        username = (username or "").strip()
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

    def get_homeroom_classes(self, username: str) -> list[dict]:
        with self.db.conn() as connection:
            lecturer_id = self._lecturer_id(connection, username)
            if lecturer_id is None:
                return []
            rows = connection.execute(
                """
                SELECT lh.maLop,
                       lh.tenLop,
                       lh.khoaHoc,
                       lh.khoa,
                       (
                           SELECT COUNT(*)
                           FROM SinhVien sv
                           WHERE sv.maLop = lh.maLop
                             AND sv.trangThai = 'DANG_HOC'
                       ) AS siSo
                FROM LopHoc lh
                WHERE lh.giangVienChuNhiemId = ?
                ORDER BY lh.maLop
                """,
                (lecturer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_homeroom_class_codes(self, username: str) -> list[str]:
        return [
            row["maLop"]
            for row in self.get_homeroom_classes(username)
        ]

    def is_homeroom_of(self, username: str, ma_lop: str) -> bool:
        ma_lop = (ma_lop or "").strip()
        if not ma_lop:
            return False
        with self.db.conn() as connection:
            lecturer_id = self._lecturer_id(connection, username)
            if lecturer_id is None:
                return False
            row = connection.execute(
                """
                SELECT 1 FROM LopHoc
                WHERE maLop = ? AND giangVienChuNhiemId = ?
                """,
                (ma_lop, lecturer_id),
            ).fetchone()
        return row is not None

    def is_homeroom_of_student(
        self,
        username: str,
        mssv: str,
    ) -> bool:
        mssv = (mssv or "").strip()
        if not mssv:
            return False
        with self.db.conn() as connection:
            lecturer_id = self._lecturer_id(connection, username)
            if lecturer_id is None:
                return False
            row = connection.execute(
                """
                SELECT 1
                FROM SinhVien sv
                JOIN LopHoc lh ON lh.maLop = sv.maLop
                WHERE sv.mssv = ?
                  AND lh.giangVienChuNhiemId = ?
                """,
                (mssv, lecturer_id),
            ).fetchone()
        return row is not None

    def get_homeroom_students(
        self,
        username: str,
        ma_lop: str = "",
        kw: str = "",
    ) -> list[dict]:
        codes = self.get_homeroom_class_codes(username)
        if ma_lop:
            if ma_lop not in codes:
                return []
            codes = [ma_lop]
        if not codes:
            return []

        placeholders = ",".join("?" for _ in codes)
        sql = f"""
            SELECT sv.*, lh.tenLop,
                   substr(sv.ngaySinh, 9, 2) || '/' ||
                   substr(sv.ngaySinh, 6, 2) || '/' ||
                   substr(sv.ngaySinh, 1, 4) AS ngaySinh
            FROM SinhVien sv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            WHERE sv.maLop IN ({placeholders})
        """
        params = list(codes)
        kw = (kw or "").strip()
        if kw:
            sql += " AND (sv.mssv LIKE ? OR sv.hoTen LIKE ?)"
            params.extend([f"%{kw}%", f"%{kw}%"])
        sql += " ORDER BY sv.maLop, sv.hoTen"

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
