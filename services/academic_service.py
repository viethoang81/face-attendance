import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from core.database import Database


ACADEMIC_STATUSES = {
    "SAP_DIEN_RA",
    "DANG_DIEN_RA",
    "DA_KET_THUC",
}

COURSE_SECTION_STATUSES = {
    "MO_DANG_KY",
    "DANG_HOC",
    "DA_KET_THUC",
    "DA_HUY",
}

REGISTRATION_STATUSES = {
    "DANG_HOC",
    "DA_HUY",
    "HOAN_THANH",
    "DINH_CHI",
}


@dataclass
class NamHocData:
    tenNamHoc: str
    ngayBatDau: str
    ngayKetThuc: str
    trangThai: str = "SAP_DIEN_RA"
    id: int = 0


@dataclass
class HocKyData:
    namHocId: int
    tenHocKy: str
    ngayBatDau: str
    ngayKetThuc: str
    trangThai: str = "SAP_DIEN_RA"
    id: int = 0


@dataclass
class MonHocData:
    maMon: str
    tenMon: str
    soTiet: int = 45
    tiLeToiThieu: int = 75


@dataclass
class LopHocPhanData:
    maLopHocPhan: str
    maMon: str
    hocKyId: int
    tenLopHocPhan: str
    nhom: str = "01"
    siSoToiDa: int = 60
    giangVienUsername: str = ""
    trangThai: str = "MO_DANG_KY"
    id: int = 0


@dataclass
class DangKyHocPhanData:
    mssv: str
    lopHocPhanId: int
    ngayDangKy: str
    trangThai: str = "DANG_HOC"
    ngayKetThuc: str = ""
    id: int = 0


class AcademicService:
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
    # ------------------------------------------------------------------
    # NĂM HỌC
    # ------------------------------------------------------------------
    def list_school_years(self) -> list[dict]:
        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT nh.*,
                       COUNT(hk.id) AS soHocKy
                FROM NamHoc nh
                LEFT JOIN HocKy hk ON hk.namHocId = nh.id
                GROUP BY nh.id
                ORDER BY nh.ngayBatDau DESC, nh.id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def create_school_year(
        self,
        data: NamHocData,
    ) -> tuple[bool, str]:
        error = self._validate_school_year(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO NamHoc (
                        tenNamHoc,
                        ngayBatDau,
                        ngayKetThuc,
                        trangThai
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        data.tenNamHoc,
                        data.ngayBatDau,
                        data.ngayKetThuc,
                        data.trangThai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Thêm năm học thành công"

    def update_school_year(
        self,
        data: NamHocData,
    ) -> tuple[bool, str]:
        if data.id <= 0:
            return False, "Năm học không hợp lệ"

        error = self._validate_school_year(data)
        if error:
            return False, error

        with self.db.conn() as connection:
            exists = connection.execute(
                "SELECT id FROM NamHoc WHERE id = ?",
                (data.id,),
            ).fetchone()

            if not exists:
                return False, "Không tìm thấy năm học"

            invalid_semester = connection.execute(
                """
                SELECT tenHocKy
                FROM HocKy
                WHERE namHocId = ?
                  AND (
                      ngayBatDau < ?
                      OR ngayKetThuc > ?
                  )
                LIMIT 1
                """,
                (
                    data.id,
                    data.ngayBatDau,
                    data.ngayKetThuc,
                ),
            ).fetchone()

            if invalid_semester:
                return (
                    False,
                    "Khoảng thời gian mới không bao phủ học kỳ "
                    f"'{invalid_semester['tenHocKy']}'",
                )

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    UPDATE NamHoc
                    SET tenNamHoc = ?,
                        ngayBatDau = ?,
                        ngayKetThuc = ?,
                        trangThai = ?
                    WHERE id = ?
                    """,
                    (
                        data.tenNamHoc,
                        data.ngayBatDau,
                        data.ngayKetThuc,
                        data.trangThai,
                        data.id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật năm học thành công"

    def delete_school_year(
        self,
        school_year_id: int,
    ) -> tuple[bool, str]:
        try:
            with self.db.conn() as connection:
                row = connection.execute(
                    "SELECT id FROM NamHoc WHERE id = ?",
                    (school_year_id,),
                ).fetchone()

                if not row:
                    return False, "Không tìm thấy năm học"

                semester_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM HocKy
                    WHERE namHocId = ?
                    """,
                    (school_year_id,),
                ).fetchone()[0]

                if semester_count:
                    return (
                        False,
                        "Không thể xóa năm học đang có học kỳ",
                    )

                connection.execute(
                    "DELETE FROM NamHoc WHERE id = ?",
                    (school_year_id,),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Xóa năm học thành công"

    # ------------------------------------------------------------------
    # HỌC KỲ
    # ------------------------------------------------------------------
    def list_semesters(
        self,
        school_year_id: int = 0,
    ) -> list[dict]:
        sql = """
            SELECT hk.*,
                   nh.tenNamHoc,
                   nh.ngayBatDau AS namHocBatDau,
                   nh.ngayKetThuc AS namHocKetThuc,
                   COUNT(lhp.id) AS soLopHocPhan
            FROM HocKy hk
            JOIN NamHoc nh ON nh.id = hk.namHocId
            LEFT JOIN LopHocPhan lhp ON lhp.hocKyId = hk.id
            WHERE 1 = 1
        """
        params = []

        if school_year_id:
            sql += " AND hk.namHocId = ?"
            params.append(school_year_id)

        sql += """
            GROUP BY hk.id
            ORDER BY nh.ngayBatDau DESC, hk.ngayBatDau
        """

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def create_semester(
        self,
        data: HocKyData,
    ) -> tuple[bool, str]:
        error = self._validate_semester(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO HocKy (
                        namHocId,
                        tenHocKy,
                        ngayBatDau,
                        ngayKetThuc,
                        trangThai
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        data.namHocId,
                        data.tenHocKy,
                        data.ngayBatDau,
                        data.ngayKetThuc,
                        data.trangThai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Thêm học kỳ thành công"

    def update_semester(
        self,
        data: HocKyData,
    ) -> tuple[bool, str]:
        if data.id <= 0:
            return False, "Học kỳ không hợp lệ"

        error = self._validate_semester(data)
        if error:
            return False, error

        with self.db.conn() as connection:
            exists = connection.execute(
                "SELECT id FROM HocKy WHERE id = ?",
                (data.id,),
            ).fetchone()

            if not exists:
                return False, "Không tìm thấy học kỳ"

            invalid_session = connection.execute(
                """
                SELECT ca.ngayHoc
                FROM CaHoc ca
                JOIN LopHocPhan lhp
                  ON lhp.id = ca.lopHocPhanId
                WHERE lhp.hocKyId = ?
                  AND (
                      ca.ngayHoc < ?
                      OR ca.ngayHoc > ?
                  )
                LIMIT 1
                """,
                (
                    data.id,
                    data.ngayBatDau,
                    data.ngayKetThuc,
                ),
            ).fetchone()

            if invalid_session:
                return (
                    False,
                    "Khoảng thời gian mới không bao phủ toàn bộ "
                    "ca học hiện có",
                )

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    UPDATE HocKy
                    SET namHocId = ?,
                        tenHocKy = ?,
                        ngayBatDau = ?,
                        ngayKetThuc = ?,
                        trangThai = ?
                    WHERE id = ?
                    """,
                    (
                        data.namHocId,
                        data.tenHocKy,
                        data.ngayBatDau,
                        data.ngayKetThuc,
                        data.trangThai,
                        data.id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật học kỳ thành công"

    def delete_semester(
        self,
        semester_id: int,
    ) -> tuple[bool, str]:
        try:
            with self.db.conn() as connection:
                row = connection.execute(
                    "SELECT id FROM HocKy WHERE id = ?",
                    (semester_id,),
                ).fetchone()

                if not row:
                    return False, "Không tìm thấy học kỳ"

                section_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM LopHocPhan
                    WHERE hocKyId = ?
                    """,
                    (semester_id,),
                ).fetchone()[0]

                if section_count:
                    return (
                        False,
                        "Không thể xóa học kỳ đang có lớp học phần",
                    )

                connection.execute(
                    "DELETE FROM HocKy WHERE id = ?",
                    (semester_id,),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Xóa học kỳ thành công"

    # ------------------------------------------------------------------
    # MÔN HỌC
    # ------------------------------------------------------------------
    def list_subjects(self) -> list[dict]:
        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT mh.*,
                       COUNT(lhp.id) AS soLopHocPhan
                FROM MonHoc mh
                LEFT JOIN LopHocPhan lhp ON lhp.maMon = mh.maMon
                GROUP BY mh.maMon
                ORDER BY mh.maMon
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def create_subject(
        self,
        data: MonHocData,
    ) -> tuple[bool, str]:
        error = self._validate_subject(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO MonHoc (
                        maMon,
                        tenMon,
                        soTiet,
                        tiLeToiThieu
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        data.maMon,
                        data.tenMon,
                        data.soTiet,
                        data.tiLeToiThieu,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Thêm môn học thành công"

    def update_subject(
        self,
        old_subject_code: str,
        data: MonHocData,
    ) -> tuple[bool, str]:
        old_subject_code = (old_subject_code or "").strip().upper()

        if not old_subject_code:
            return False, "Không xác định được môn học cần sửa"

        error = self._validate_subject(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                cursor = connection.execute(
                    """
                    UPDATE MonHoc
                    SET maMon = ?,
                        tenMon = ?,
                        soTiet = ?,
                        tiLeToiThieu = ?
                    WHERE maMon = ?
                    """,
                    (
                        data.maMon,
                        data.tenMon,
                        data.soTiet,
                        data.tiLeToiThieu,
                        old_subject_code,
                    ),
                )

                if cursor.rowcount == 0:
                    return False, "Không tìm thấy môn học"
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật môn học thành công"

    def delete_subject(
        self,
        subject_code: str,
    ) -> tuple[bool, str]:
        subject_code = (subject_code or "").strip().upper()

        if not subject_code:
            return False, "Mã môn học không hợp lệ"

        with self.db.conn() as connection:
            section_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM LopHocPhan
                WHERE maMon = ?
                """,
                (subject_code,),
            ).fetchone()[0]

            if section_count:
                return (
                    False,
                    "Không thể xóa môn học đang được dùng bởi "
                    f"{section_count} lớp học phần",
                )

            cursor = connection.execute(
                "DELETE FROM MonHoc WHERE maMon = ?",
                (subject_code,),
            )

            if cursor.rowcount == 0:
                return False, "Không tìm thấy môn học"

        return True, "Xóa môn học thành công"

    # ------------------------------------------------------------------
    # LỚP HỌC PHẦN
    # ------------------------------------------------------------------
    def list_course_sections(
        self,
        semester_id: int = 0,
        lecturer_username: str = "",
        include_cancelled: bool = True,
    ) -> list[dict]:
        sql = """
            SELECT lhp.*,
                   COALESCE(tk.username, '') AS giangVienUsername,
                   mh.tenMon,
                   mh.soTiet,
                   mh.tiLeToiThieu,
                   hk.tenHocKy,
                   hk.ngayBatDau AS hocKyBatDau,
                   hk.ngayKetThuc AS hocKyKetThuc,
                   nh.tenNamHoc,
                   COALESCE(tk.hoTen, '') AS giangVienHoTen,
                   COUNT(
                       CASE
                           WHEN dk.trangThai = 'DANG_HOC'
                           THEN 1
                       END
                   ) AS siSoHienTai
            FROM LopHocPhan lhp
            JOIN MonHoc mh ON mh.maMon = lhp.maMon
            JOIN HocKy hk ON hk.id = lhp.hocKyId
            JOIN NamHoc nh ON nh.id = hk.namHocId
            LEFT JOIN GiangVien gv
              ON gv.id = lhp.giangVienId
            LEFT JOIN TaiKhoan tk
              ON tk.id = gv.taiKhoanId
            LEFT JOIN DangKyHocPhan dk
              ON dk.lopHocPhanId = lhp.id
            WHERE 1 = 1
        """
        params = []

        if semester_id:
            sql += " AND lhp.hocKyId = ?"
            params.append(semester_id)

        lecturer_username = (lecturer_username or "").strip()
        if lecturer_username:
            sql += """
                AND lower(tk.username) = lower(?)
            """
            params.append(lecturer_username)

        if not include_cancelled:
            sql += " AND lhp.trangThai <> 'DA_HUY'"

        sql += """
            GROUP BY lhp.id
            ORDER BY nh.ngayBatDau DESC,
                     hk.ngayBatDau DESC,
                     lhp.maLopHocPhan
        """

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def get_course_section(
        self,
        section_id: int,
    ) -> dict | None:
        with self.db.conn() as connection:
            row = connection.execute(
                """
                SELECT lhp.*,
                   COALESCE(tk.username, '') AS giangVienUsername,
                       mh.tenMon,
                       hk.tenHocKy,
                       hk.ngayBatDau AS hocKyBatDau,
                       hk.ngayKetThuc AS hocKyKetThuc,
                       nh.tenNamHoc,
                       COALESCE(tk.hoTen, '') AS giangVienHoTen
                FROM LopHocPhan lhp
                JOIN MonHoc mh ON mh.maMon = lhp.maMon
                JOIN HocKy hk ON hk.id = lhp.hocKyId
                JOIN NamHoc nh ON nh.id = hk.namHocId
                LEFT JOIN GiangVien gv
                  ON gv.id = lhp.giangVienId
                LEFT JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE lhp.id = ?
                """,
                (section_id,),
            ).fetchone()

        return dict(row) if row else None

    def get_course_section_by_code(
        self,
        section_code: str,
    ) -> dict | None:
        section_code = (section_code or "").strip()

        with self.db.conn() as connection:
            row = connection.execute(
                """
                SELECT lhp.*,
                   COALESCE(tk.username, '') AS giangVienUsername,
                       mh.tenMon,
                       hk.tenHocKy,
                       hk.ngayBatDau AS hocKyBatDau,
                       hk.ngayKetThuc AS hocKyKetThuc,
                       nh.tenNamHoc,
                       COALESCE(tk.hoTen, '') AS giangVienHoTen
                FROM LopHocPhan lhp
                JOIN MonHoc mh ON mh.maMon = lhp.maMon
                JOIN HocKy hk ON hk.id = lhp.hocKyId
                JOIN NamHoc nh ON nh.id = hk.namHocId
                LEFT JOIN GiangVien gv
                  ON gv.id = lhp.giangVienId
                LEFT JOIN TaiKhoan tk
                  ON tk.id = gv.taiKhoanId
                WHERE lower(lhp.maLopHocPhan) = lower(?)
                """,
                (section_code,),
            ).fetchone()

        return dict(row) if row else None

    def create_course_section(
        self,
        data: LopHocPhanData,
    ) -> tuple[bool, str]:
        error = self._validate_course_section(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO LopHocPhan (
                        maLopHocPhan,
                        maMon,
                        hocKyId,
                        tenLopHocPhan,
                        nhom,
                        siSoToiDa,
                        giangVienId,
                        trangThai
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data.maLopHocPhan,
                        data.maMon,
                        data.hocKyId,
                        data.tenLopHocPhan,
                        data.nhom,
                        data.siSoToiDa,
                        self._lecturer_id(connection, data.giangVienUsername),
                        data.trangThai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Thêm lớp học phần thành công"

    def update_course_section(
        self,
        data: LopHocPhanData,
    ) -> tuple[bool, str]:
        if data.id <= 0:
            return False, "Lớp học phần không hợp lệ"

        error = self._validate_course_section(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                current_size = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM DangKyHocPhan
                    WHERE lopHocPhanId = ?
                      AND trangThai = 'DANG_HOC'
                    """,
                    (data.id,),
                ).fetchone()[0]

                if current_size > data.siSoToiDa:
                    return (
                        False,
                        "Sĩ số tối đa không được nhỏ hơn số sinh viên "
                        f"đang học ({current_size})",
                    )

                cursor = connection.execute(
                    """
                    UPDATE LopHocPhan
                    SET maLopHocPhan = ?,
                        maMon = ?,
                        hocKyId = ?,
                        tenLopHocPhan = ?,
                        nhom = ?,
                        siSoToiDa = ?,
                        giangVienId = ?,
                        trangThai = ?
                    WHERE id = ?
                    """,
                    (
                        data.maLopHocPhan,
                        data.maMon,
                        data.hocKyId,
                        data.tenLopHocPhan,
                        data.nhom,
                        data.siSoToiDa,
                        self._lecturer_id(connection, data.giangVienUsername),
                        data.trangThai,
                        data.id,
                    ),
                )

                if cursor.rowcount == 0:
                    return False, "Không tìm thấy lớp học phần"
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật lớp học phần thành công"

    def delete_course_section(
        self,
        section_id: int,
    ) -> tuple[bool, str]:
        try:
            with self.db.conn() as connection:
                row = connection.execute(
                    "SELECT id FROM LopHocPhan WHERE id = ?",
                    (section_id,),
                ).fetchone()

                if not row:
                    return False, "Không tìm thấy lớp học phần"

                session_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM CaHoc
                    WHERE lopHocPhanId = ?
                    """,
                    (section_id,),
                ).fetchone()[0]

                if session_count:
                    return (
                        False,
                        "Không thể xóa lớp học phần đang có ca học",
                    )

                connection.execute(
                    """
                    DELETE FROM LopHocPhan
                    WHERE id = ?
                    """,
                    (section_id,),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Xóa lớp học phần thành công"

    def can_lecturer_access(
        self,
        lecturer_username: str,
        section_code: str,
    ) -> bool:
        lecturer_username = (lecturer_username or "").strip()
        section_code = (section_code or "").strip()
        if not lecturer_username or not section_code:
            return False

        with self.db.conn() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM LopHocPhan lhp
                JOIN GiangVien gv ON gv.id = lhp.giangVienId
                JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                WHERE lower(lhp.maLopHocPhan) = lower(?)
                  AND lower(tk.username) = lower(?)
                  AND lhp.trangThai <> 'DA_HUY'
                  AND tk.isActive = 1
                """,
                (section_code, lecturer_username),
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # ĐĂNG KÝ HỌC PHẦN
    # ------------------------------------------------------------------
    def list_students(self) -> list[dict]:
        with self.db.conn() as connection:
            rows = connection.execute(
                """
                SELECT sv.mssv,
                       sv.hoTen,
                       sv.maLop,
                       lh.tenLop
                FROM SinhVien sv
                JOIN LopHoc lh ON lh.maLop = sv.maLop
                WHERE sv.trangThai = 'DANG_HOC'
                ORDER BY sv.hoTen, sv.mssv
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def list_registrations(
        self,
        section_id: int = 0,
    ) -> list[dict]:
        sql = """
            SELECT dk.*,
                   sv.hoTen,
                   sv.maLop,
                   lh.tenLop,
                   lhp.maLopHocPhan,
                   lhp.tenLopHocPhan,
                   mh.maMon,
                   mh.tenMon
            FROM DangKyHocPhan dk
            JOIN SinhVien sv ON sv.mssv = dk.mssv
            JOIN LopHoc lh ON lh.maLop = sv.maLop
            JOIN LopHocPhan lhp
              ON lhp.id = dk.lopHocPhanId
            JOIN MonHoc mh ON mh.maMon = lhp.maMon
            WHERE 1 = 1
        """
        params = []

        if section_id:
            sql += " AND dk.lopHocPhanId = ?"
            params.append(section_id)

        sql += """
            ORDER BY lhp.maLopHocPhan, sv.hoTen, sv.mssv
        """

        with self.db.conn() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def create_registration(
        self,
        data: DangKyHocPhanData,
    ) -> tuple[bool, str]:
        error = self._validate_registration(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                connection.execute(
                    """
                    INSERT INTO DangKyHocPhan (
                        mssv,
                        lopHocPhanId,
                        ngayDangKy,
                        ngayKetThuc,
                        trangThai
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        data.mssv,
                        data.lopHocPhanId,
                        data.ngayDangKy,
                        data.ngayKetThuc,
                        data.trangThai,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Đăng ký học phần thành công"

    def update_registration(
        self,
        data: DangKyHocPhanData,
    ) -> tuple[bool, str]:
        if data.id <= 0:
            return False, "Đăng ký học phần không hợp lệ"

        error = self._validate_registration(data)
        if error:
            return False, error

        try:
            with self.db.conn() as connection:
                cursor = connection.execute(
                    """
                    UPDATE DangKyHocPhan
                    SET mssv = ?,
                        lopHocPhanId = ?,
                        ngayDangKy = ?,
                        ngayKetThuc = ?,
                        trangThai = ?,
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        data.mssv,
                        data.lopHocPhanId,
                        data.ngayDangKy,
                        data.ngayKetThuc,
                        data.trangThai,
                        data.id,
                    ),
                )

                if cursor.rowcount == 0:
                    return False, "Không tìm thấy đăng ký học phần"
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Cập nhật đăng ký học phần thành công"

    def delete_registration(
        self,
        registration_id: int,
    ) -> tuple[bool, str]:
        """Xóa khi chưa có lịch sử; nếu đã có thì kết thúc đăng ký."""
        try:
            with self.db.conn() as connection:
                connection.execute("BEGIN IMMEDIATE")
                registration = connection.execute(
                    """
                    SELECT dk.id, dk.ngayDangKy, dk.ngayKetThuc,
                           dk.trangThai,
                           MAX(
                               CASE
                                   WHEN ca.ngayHoc >= dk.ngayDangKy
                                    AND (
                                        dk.ngayKetThuc = ''
                                        OR ca.ngayHoc <= dk.ngayKetThuc
                                    )
                                    AND (
                                        COALESCE(ca.daMoDiemDanh, 0) = 1
                                        OR EXISTS (
                                            SELECT 1
                                            FROM DiemDanh any_dd
                                            WHERE any_dd.caHocId = ca.id
                                        )
                                    )
                                   THEN ca.ngayHoc
                               END
                           ) AS ngayHocCuoi
                    FROM DangKyHocPhan dk
                    LEFT JOIN CaHoc ca
                      ON ca.lopHocPhanId = dk.lopHocPhanId
                    WHERE dk.id = ?
                    GROUP BY dk.id
                    """,
                    (registration_id,),
                ).fetchone()
                if not registration:
                    return False, "Không tìm thấy đăng ký học phần"

                if registration["ngayHocCuoi"] is not None:
                    if registration["trangThai"] != "DANG_HOC":
                        return True, (
                            "Đăng ký đã kết thúc; lịch sử điểm danh "
                            "được giữ nguyên"
                        )
                    end_date = max(
                        date.today().isoformat(),
                        registration["ngayDangKy"],
                        registration["ngayHocCuoi"],
                    )
                    connection.execute(
                        """
                        UPDATE DangKyHocPhan
                        SET trangThai = 'DA_HUY', ngayKetThuc = ?,
                            updatedAt = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (end_date, registration_id),
                    )
                    return True, (
                        "Đã kết thúc đăng ký; lịch sử điểm danh được giữ nguyên"
                    )

                connection.execute(
                    "DELETE FROM DangKyHocPhan WHERE id = ?",
                    (registration_id,),
                )
        except sqlite3.IntegrityError as exc:
            return False, self._integrity_message(exc)

        return True, "Xóa đăng ký học phần thành công"

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------
    def _validate_school_year(
        self,
        data: NamHocData,
    ) -> str:
        data.tenNamHoc = self._clean_text(data.tenNamHoc)

        if not data.tenNamHoc:
            return "Tên năm học không được để trống"

        if data.trangThai not in ACADEMIC_STATUSES:
            return "Trạng thái năm học không hợp lệ"

        return self._validate_date_range(
            data.ngayBatDau,
            data.ngayKetThuc,
            "năm học",
        )

    def _validate_semester(
        self,
        data: HocKyData,
    ) -> str:
        data.tenHocKy = self._clean_text(data.tenHocKy)

        try:
            data.namHocId = int(data.namHocId)
        except (TypeError, ValueError):
            return "Năm học không hợp lệ"

        if data.namHocId <= 0:
            return "Vui lòng chọn năm học"

        if not data.tenHocKy:
            return "Tên học kỳ không được để trống"

        if data.trangThai not in ACADEMIC_STATUSES:
            return "Trạng thái học kỳ không hợp lệ"

        error = self._validate_date_range(
            data.ngayBatDau,
            data.ngayKetThuc,
            "học kỳ",
        )
        if error:
            return error

        with self.db.conn() as connection:
            school_year = connection.execute(
                """
                SELECT ngayBatDau, ngayKetThuc
                FROM NamHoc
                WHERE id = ?
                """,
                (data.namHocId,),
            ).fetchone()

        if not school_year:
            return "Năm học không tồn tại"

        if (
            data.ngayBatDau < school_year["ngayBatDau"]
            or data.ngayKetThuc > school_year["ngayKetThuc"]
        ):
            return "Học kỳ phải nằm trong thời gian của năm học"

        return ""

    @staticmethod
    def _validate_subject(
        data: MonHocData,
    ) -> str:
        data.maMon = (data.maMon or "").strip().upper()
        data.tenMon = " ".join((data.tenMon or "").split())

        if not data.maMon:
            return "Mã môn không được để trống"

        if not re.fullmatch(r"[A-Z0-9._-]+", data.maMon):
            return (
                "Mã môn chỉ được gồm chữ in hoa, số, dấu chấm, "
                "gạch ngang hoặc gạch dưới"
            )

        if not data.tenMon:
            return "Tên môn không được để trống"

        try:
            data.soTiet = int(data.soTiet)
        except (TypeError, ValueError):
            return "Số tiết không hợp lệ"

        if not 1 <= data.soTiet <= 300:
            return "Số tiết phải từ 1 đến 300"

        try:
            data.tiLeToiThieu = int(data.tiLeToiThieu)
        except (TypeError, ValueError):
            return "Tỷ lệ chuyên cần tối thiểu không hợp lệ"

        if not 0 <= data.tiLeToiThieu <= 100:
            return "Tỷ lệ chuyên cần phải từ 0 đến 100"

        return ""

    def _validate_course_section(
        self,
        data: LopHocPhanData,
    ) -> str:
        data.maLopHocPhan = (
            data.maLopHocPhan or ""
        ).strip().upper()
        data.maMon = (data.maMon or "").strip().upper()
        data.tenLopHocPhan = self._clean_text(
            data.tenLopHocPhan
        )
        data.nhom = self._clean_text(data.nhom) or "01"
        data.giangVienUsername = (
            data.giangVienUsername or ""
        ).strip()

        if not data.maLopHocPhan:
            return "Mã lớp học phần không được để trống"

        if not re.fullmatch(
            r"[A-Z0-9._-]+",
            data.maLopHocPhan,
        ):
            return (
                "Mã lớp học phần chỉ được gồm chữ in hoa, số, "
                "dấu chấm, gạch ngang hoặc gạch dưới"
            )

        if not data.tenLopHocPhan:
            return "Tên lớp học phần không được để trống"

        if not data.maMon:
            return "Vui lòng chọn môn học"

        try:
            data.hocKyId = int(data.hocKyId)
        except (TypeError, ValueError):
            return "Học kỳ không hợp lệ"

        if data.hocKyId <= 0:
            return "Vui lòng chọn học kỳ"

        try:
            data.siSoToiDa = int(data.siSoToiDa)
        except (TypeError, ValueError):
            return "Sĩ số tối đa không hợp lệ"

        if not 1 <= data.siSoToiDa <= 1000:
            return "Sĩ số tối đa phải từ 1 đến 1000"

        if data.trangThai not in COURSE_SECTION_STATUSES:
            return "Trạng thái lớp học phần không hợp lệ"

        with self.db.conn() as connection:
            subject = connection.execute(
                "SELECT 1 FROM MonHoc WHERE maMon = ?",
                (data.maMon,),
            ).fetchone()

            semester = connection.execute(
                "SELECT 1 FROM HocKy WHERE id = ?",
                (data.hocKyId,),
            ).fetchone()

            lecturer = None
            if data.giangVienUsername:
                lecturer = self._lecturer_id(
                    connection,
                    data.giangVienUsername,
                )

        if not subject:
            return "Môn học không tồn tại"

        if not semester:
            return "Học kỳ không tồn tại"

        if data.giangVienUsername and not lecturer:
            return "Giảng viên không tồn tại hoặc đã bị khóa"

        return ""

    def _validate_registration(
        self,
        data: DangKyHocPhanData,
    ) -> str:
        data.mssv = (data.mssv or "").strip()

        try:
            data.lopHocPhanId = int(data.lopHocPhanId)
        except (TypeError, ValueError):
            return "Lớp học phần không hợp lệ"

        if not data.mssv:
            return "Vui lòng chọn sinh viên"

        if data.lopHocPhanId <= 0:
            return "Vui lòng chọn lớp học phần"

        try:
            start_date = date.fromisoformat(data.ngayDangKy)
        except (TypeError, ValueError):
            return "Ngày đăng ký không hợp lệ"

        if data.trangThai not in REGISTRATION_STATUSES:
            return "Trạng thái đăng ký không hợp lệ"

        if data.trangThai == "DANG_HOC":
            data.ngayKetThuc = ""
        else:
            if not data.ngayKetThuc:
                return "Vui lòng chọn ngày kết thúc đăng ký"

            try:
                end_date = date.fromisoformat(
                    data.ngayKetThuc
                )
            except (TypeError, ValueError):
                return "Ngày kết thúc đăng ký không hợp lệ"

            if end_date < start_date:
                return (
                    "Ngày kết thúc đăng ký không được trước "
                    "ngày đăng ký"
                )

        with self.db.conn() as connection:
            student = connection.execute(
                "SELECT trangThai FROM SinhVien WHERE mssv = ?",
                (data.mssv,),
            ).fetchone()

            section = connection.execute(
                """
                SELECT trangThai
                FROM LopHocPhan
                WHERE id = ?
                """,
                (data.lopHocPhanId,),
            ).fetchone()

        if not student:
            return "Sinh viên không tồn tại"

        if (
            data.trangThai == "DANG_HOC"
            and student["trangThai"] != "DANG_HOC"
        ):
            return "Không thể đăng ký học phần cho sinh viên đã thôi học"

        if not section:
            return "Lớp học phần không tồn tại"

        if (
            data.trangThai == "DANG_HOC"
            and section["trangThai"] in ("DA_HUY", "DA_KET_THUC")
        ):
            return (
                "Không thể đăng ký đang học vào lớp học phần "
                "đã hủy hoặc đã kết thúc"
            )

        return ""

    @staticmethod
    def _validate_date_range(
        start_text: str,
        end_text: str,
        object_name: str,
    ) -> str:
        try:
            start_date = date.fromisoformat(start_text)
        except (TypeError, ValueError):
            return f"Ngày bắt đầu {object_name} không hợp lệ"

        try:
            end_date = date.fromisoformat(end_text)
        except (TypeError, ValueError):
            return f"Ngày kết thúc {object_name} không hợp lệ"

        if start_date >= end_date:
            return (
                f"Ngày bắt đầu {object_name} phải trước "
                f"ngày kết thúc {object_name}"
            )

        return ""

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join((value or "").split())

    @staticmethod
    def _integrity_message(
        exc: sqlite3.IntegrityError,
    ) -> str:
        error = str(exc).lower()

        if "uq_namhoc_ten_ci" in error:
            return "Tên năm học đã tồn tại"

        if "uq_hocky_ten_ci" in error:
            return "Tên học kỳ đã tồn tại trong năm học này"

        if "uq_monhoc_mamon_ci" in error or (
            "unique constraint failed" in error
            and "monhoc.mamon" in error
        ):
            return "Mã môn học đã tồn tại"

        if "uq_monhoc_tenmon_ci" in error:
            return "Tên môn học đã tồn tại"

        if "uq_lophocphan_ma_ci" in error:
            return "Mã lớp học phần đã tồn tại"

        if (
            "dangkyhocphan.mssv" in error
            and "dangkyhocphan.lophocphanid" in error
        ):
            return "Sinh viên đã được đăng ký vào lớp học phần này"

        if "vuot qua si so toi da" in error:
            return "Lớp học phần đã đủ sĩ số tối đa"

        if "hoc ky phai nam" in error:
            return "Học kỳ phải nằm trong thời gian của năm học"

        if "ngay hoc phai nam" in error:
            return "Ngày học phải nằm trong thời gian của học kỳ"

        if "lam sai lich su" in error:
            return (
                "Không thể thay đổi đăng ký vì sẽ làm sai "
                "lịch sử điểm danh"
            )

        if "xoa dang ky da co lich su" in error:
            return "Không thể xóa đăng ký đã có lịch sử điểm danh"

        if "doi mon hoac hoc ky" in error:
            return (
                "Không thể đổi môn hoặc học kỳ sau khi lớp "
                "đã phát sinh điểm danh"
            )

        if "dang co ca diem danh dang mo" in error:
            return (
                "Không thể đổi hoặc bỏ phân công giảng viên "
                "khi lớp đang có ca điểm danh mở"
            )

        if "trung lich khi phan cong" in error:
            return (
                "Không thể phân công vì giảng viên đang có "
                "ca học trùng thời gian"
            )

        if "foreign key constraint failed" in error:
            return (
                "Không thể thực hiện vì dữ liệu đang được sử dụng "
                "hoặc dữ liệu liên kết không tồn tại"
            )

        if "check constraint failed" in error:
            return "Dữ liệu không đáp ứng ràng buộc của cơ sở dữ liệu"

        return "Không thể lưu dữ liệu do ràng buộc cơ sở dữ liệu"
