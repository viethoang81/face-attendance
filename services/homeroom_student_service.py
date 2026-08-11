from __future__ import annotations

import sqlite3

from core.database import Database
from services.student_service import Student, StudentService


class HomeroomStudentService:
    """Quản lý sinh viên trong đúng lớp chủ nhiệm của giảng viên hiện tại."""

    _DENIED = (
        "Bạn không có quyền quản lý sinh viên ngoài lớp chủ nhiệm "
        "được phân công."
    )
    _STATUS_DENIED = (
        "Giảng viên chủ nhiệm không được thay đổi trạng thái sinh viên "
        "bằng thao tác chung. Vui lòng dùng chức năng Cho thôi học."
    )

    def __init__(self, db: Database, current_user: dict):
        self.db = db
        self.current_user = dict(current_user or {})
        self._base = StudentService(db, self.current_user)

    @property
    def username(self) -> str:
        return str(self.current_user.get("username", "") or "").strip()

    @property
    def _has_lecturer_claim(self) -> bool:
        return (
            self.current_user.get("vaiTro") == "GiangVien"
            and bool(self.username)
        )

    def _active_lecturer_id(self, connection) -> int | None:
        if not self._has_lecturer_claim:
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
            (self.username,),
        ).fetchone()
        return int(row["id"]) if row else None

    @staticmethod
    def _owns_class(connection, lecturer_id: int, ma_lop: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM LopHoc
            WHERE maLop = ?
              AND giangVienChuNhiemId = ?
            """,
            ((ma_lop or "").strip(), lecturer_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _owns_student(connection, lecturer_id: int, mssv: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM SinhVien sv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            WHERE sv.mssv = ?
              AND lh.giangVienChuNhiemId = ?
            """,
            ((mssv or "").strip(), lecturer_id),
        ).fetchone()
        return row is not None

    def get_allowed_classes(self) -> list[dict]:
        if not self._has_lecturer_claim:
            return []

        with self.db.conn() as connection:
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
                JOIN GiangVien gv
                  ON gv.id = lh.giangVienChuNhiemId
                JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE tk.username = ?
                  AND tk.vaiTro = 'GiangVien'
                  AND tk.isActive = 1
                ORDER BY lh.maLop
                """,
                (self.username,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_all(self, trang_thai: str = "") -> list[dict]:
        return self.search(trang_thai=trang_thai)

    def search(
        self,
        kw: str = "",
        maLop: str = "",
        trang_thai: str = "",
    ) -> list[dict]:
        if not self._has_lecturer_claim:
            return []

        keyword = f"%{(kw or '').strip()}%"
        sql = f"""
            SELECT {StudentService.SELECT_FIELDS}
            FROM SinhVien sv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            JOIN GiangVien gv
              ON gv.id = lh.giangVienChuNhiemId
            JOIN TaiKhoan tk
              ON tk.id = gv.taiKhoanId
            WHERE tk.username = ?
              AND tk.vaiTro = 'GiangVien'
              AND tk.isActive = 1
              AND (sv.mssv LIKE ? OR sv.hoTen LIKE ?)
        """
        params = [self.username, keyword, keyword]

        ma_lop = (maLop or "").strip()
        if ma_lop:
            sql += " AND sv.maLop = ?"
            params.append(ma_lop)

        trang_thai = (trang_thai or "").strip()
        if trang_thai:
            sql += " AND sv.trangThai = ?"
            params.append(trang_thai)

        sql += " ORDER BY sv.maLop, sv.hoTen, sv.mssv"

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_by_mssv(self, mssv: str) -> dict | None:
        mssv = (mssv or "").strip()
        if not self._has_lecturer_claim or not mssv:
            return None

        with self.db.conn() as connection:
            row = connection.execute(
                f"""
                SELECT {StudentService.SELECT_FIELDS}
                FROM SinhVien sv
                JOIN LopHoc lh ON lh.maLop = sv.maLop
                JOIN GiangVien gv
                  ON gv.id = lh.giangVienChuNhiemId
                JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE sv.mssv = ?
                  AND tk.username = ?
                  AND tk.vaiTro = 'GiangVien'
                  AND tk.isActive = 1
                """,
                (mssv, self.username),
            ).fetchone()
        return dict(row) if row else None

    def can_manage_student(self, mssv: str) -> bool:
        mssv = (mssv or "").strip()
        if not self._has_lecturer_claim or not mssv:
            return False

        with self.db.conn() as connection:
            lecturer_id = self._active_lecturer_id(connection)
            return bool(
                lecturer_id is not None
                and self._owns_student(connection, lecturer_id, mssv)
            )

    def can_modify_student(self, mssv: str) -> bool:
        """Sinh viên thôi học vẫn được xem nhưng không được sửa/đăng ký mặt."""
        mssv = (mssv or "").strip()
        if not self._has_lecturer_claim or not mssv:
            return False

        with self.db.conn() as connection:
            lecturer_id = self._active_lecturer_id(connection)
            if lecturer_id is None:
                return False
            row = connection.execute(
                """
                SELECT 1
                FROM SinhVien sv
                JOIN LopHoc lh ON lh.maLop = sv.maLop
                WHERE sv.mssv = ?
                  AND sv.trangThai = 'DANG_HOC'
                  AND lh.giangVienChuNhiemId = ?
                """,
                (mssv, lecturer_id),
            ).fetchone()
        return row is not None

    def add(self, sv: Student) -> tuple[bool, str]:
        try:
            with self.db.conn() as connection:
                # Khóa writer trước khi kiểm tra quyền để phân công GVCN
                # không thể thay đổi giữa bước kiểm tra và INSERT.
                connection.execute("BEGIN IMMEDIATE")

                lecturer_id = self._active_lecturer_id(connection)
                if lecturer_id is None:
                    return False, self._DENIED

                error = self._base._validate(sv)
                if error:
                    return False, error

                if not self._owns_class(
                    connection,
                    lecturer_id,
                    sv.maLop,
                ):
                    return False, self._DENIED

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
                        self._base._date_to_db(sv.ngaySinh),
                        sv.gioiTinh,
                        sv.maLop,
                        sv.email,
                        sv.soDienThoai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._base._integrity_message(exc, sv.mssv)
        except sqlite3.Error:
            return False, "Không thể thêm sinh viên do lỗi cơ sở dữ liệu"

        return True, "Thêm sinh viên thành công"

    def update(
        self,
        old_mssv: str,
        sv: Student,
    ) -> tuple[bool, str]:
        old_mssv = (old_mssv or "").strip()
        if not old_mssv:
            return False, "Không xác định được MSSV cũ"

        try:
            with self.db.conn() as connection:
                # BEGIN IMMEDIATE giữ kiểm tra lớp nguồn, lớp đích và UPDATE
                # trong cùng một transaction có khóa ghi.
                connection.execute("BEGIN IMMEDIATE")

                lecturer_id = self._active_lecturer_id(connection)
                if lecturer_id is None:
                    return False, self._DENIED

                if not self._owns_student(
                    connection,
                    lecturer_id,
                    old_mssv,
                ):
                    return False, self._DENIED

                current = connection.execute(
                    "SELECT trangThai FROM SinhVien WHERE mssv = ?",
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

                error = self._base._validate(
                    sv,
                    exclude_mssv=old_mssv,
                )
                if error:
                    return False, error

                if not self._owns_class(
                    connection,
                    lecturer_id,
                    sv.maLop,
                ):
                    return False, self._DENIED

                cursor = connection.execute(
                    """
                    UPDATE SinhVien
                    SET mssv = ?, hoTen = ?, ngaySinh = ?,
                        gioiTinh = ?, maLop = ?, email = ?,
                        soDienThoai = ?, updatedAt = CURRENT_TIMESTAMP
                    WHERE mssv = ?
                    """,
                    (
                        sv.mssv,
                        sv.hoTen,
                        self._base._date_to_db(sv.ngaySinh),
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
            return False, self._base._integrity_message(exc, sv.mssv)
        except sqlite3.Error:
            return False, "Không thể cập nhật sinh viên do lỗi cơ sở dữ liệu"

        return True, "Cập nhật sinh viên thành công"

    def can_hard_delete(self, mssv: str) -> tuple[bool, str]:
        if not self.can_manage_student(mssv):
            return False, self._DENIED
        return self._base.can_hard_delete(
            mssv,
            actor=self.current_user,
        )

    def purge_student(self, mssv: str) -> tuple[bool, str]:
        # Base service vẫn kiểm tra lại quyền dưới BEGIN IMMEDIATE.
        return self._base.purge_student(
            mssv,
            actor=self.current_user,
        )

    def withdraw_student(
        self,
        mssv: str,
        effective_date: str,
    ) -> tuple[bool, str]:
        return self._base.withdraw_student(
            mssv,
            actor=self.current_user,
            effective_date=effective_date,
        )

    def delete(self, mssv: str) -> tuple[bool, str]:
        """Alias cũ chỉ thực hiện thôi học, không tự quyết định purge."""
        from datetime import date

        return self.withdraw_student(mssv, date.today().isoformat())

    def set_status(
        self,
        mssv: str,
        status: str,
    ) -> tuple[bool, str]:
        del mssv, status
        return False, self._STATUS_DENIED
