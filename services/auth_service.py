import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

from core.database import Database
from services.email_service import SmtpEmailService


logger = logging.getLogger(__name__)


class AuthService:
    """Xác thực bằng TaiKhoan, hồ sơ giảng viên bằng GiangVien."""

    PASSWORD_ITERATIONS = 260_000
    FAILED_ATTEMPT_LIMIT = 5
    LOCKOUT_MINUTES = 15
    OTP_EXPIRES_MINUTES = 5
    OTP_MAX_ATTEMPTS = 5
    OTP_REQUEST_COOLDOWN_SECONDS = 60
    VALID_ROLES = {"Admin", "GiangVien"}
    VALID_GENDERS = {"Nam", "Nữ", "Khác"}

    def __init__(self, db: Database, email_service=None):
        self.db = db
        self.email_service = email_service or SmtpEmailService()

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _new_salt() -> str:
        return os.urandom(16).hex()

    @classmethod
    def _hash_value(cls, value, salt, iterations=None) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            value.encode("utf-8"),
            salt.encode("utf-8"),
            iterations or cls.PASSWORD_ITERATIONS,
        ).hex()

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))

    @staticmethod
    def _is_valid_username(username: str) -> bool:
        return (
            3 <= len(username) <= 40
            and any(char.isalnum() for char in username)
            and all(char.isalnum() or char in " ._-" for char in username)
        )

    @staticmethod
    def _normalize_username(username: str) -> str:
        return " ".join((username or "").strip().split())

    @staticmethod
    def _clean_phone(phone: str) -> str:
        return re.sub(r"\s+", "", (phone or "").strip())

    @staticmethod
    def _normalize_person_name(name: str) -> str:
        return " ".join((name or "").strip().split())

    @staticmethod
    def _is_valid_person_name(name: str) -> bool:
        return bool(re.fullmatch(
            r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*",
            name,
            re.UNICODE,
        ))

    @staticmethod
    def _is_valid_ma_gv(ma_gv: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9]+", ma_gv))

    @staticmethod
    def _dob_to_db(value: str) -> str:
        return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")

    @staticmethod
    def _dob_from_db(value: str) -> str:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return value or ""

    @classmethod
    def _validate_password(cls, password: str) -> tuple[bool, str]:
        if password != password.strip():
            return False, "Mật khẩu không được có khoảng trắng ở đầu hoặc cuối"
        if len(password) < 8:
            return False, "Mật khẩu phải có ít nhất 8 ký tự"
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            return False, "Mật khẩu phải có ít nhất một chữ cái và một chữ số"
        return True, ""

    @classmethod
    def _verify_password(cls, password: str, row) -> bool:
        actual = cls._hash_value(
            password,
            row["passwordSalt"],
            int(row["passwordIterations"] or 100_000),
        )
        return hmac.compare_digest(actual, row["passwordHash"])

    @staticmethod
    def _account_id(connection, username: str) -> int | None:
        if not username:
            return None
        row = connection.execute(
            "SELECT id FROM TaiKhoan WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        return int(row["id"]) if row else None

    def _log(
        self,
        event_type,
        success,
        actor="",
        target="",
        message="",
        connection=None,
    ):
        def write(conn):
            conn.execute(
                """
                INSERT INTO AuthLog (
                    actorTaiKhoanId, targetTaiKhoanId,
                    actorUsernameSnapshot, targetUsernameSnapshot,
                    eventType, success, message, createdAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._account_id(conn, actor),
                    self._account_id(conn, target),
                    (actor or "").strip(),
                    (target or "").strip(),
                    event_type,
                    int(bool(success)),
                    (message or "")[:500],
                    self._format_dt(self._now()),
                ),
            )

        if connection is not None:
            write(connection)
            return
        try:
            with self.db.conn() as conn:
                write(conn)
        except Exception:
            logger.exception("[AuthService] Cannot write auth log")

    @staticmethod
    def _is_admin(actor_username: str, connection) -> bool:
        row = connection.execute(
            """
            SELECT vaiTro, isActive
            FROM TaiKhoan
            WHERE username = ?
            """,
            ((actor_username or "").strip(),),
        ).fetchone()
        return bool(row and row["vaiTro"] == "Admin" and row["isActive"] == 1)

    def _send_temporary_password_email(
        self,
        actor_username,
        username,
        display_name,
        email,
        temporary_password,
    ):
        try:
            sent, message = self.email_service.send_temporary_password(
                email, display_name, username, temporary_password
            )
        except Exception:
            logger.exception("[AuthService] Cannot send temporary password")
            sent, message = False, "Dịch vụ email gặp lỗi không xác định."
        self._log(
            "TEMP_PASSWORD_EMAIL",
            sent,
            actor=actor_username,
            target=username,
            message=message,
        )
        return sent, message

    def _send_password_changed_notice(self, username, display_name, email):
        if not email:
            return
        try:
            sent, message = self.email_service.send_password_changed_notice(
                email, display_name
            )
        except Exception:
            logger.exception("[AuthService] Cannot send password notice")
            sent, message = False, "Dịch vụ email gặp lỗi không xác định."
        self._log(
            "PASSWORD_CHANGED_EMAIL",
            sent,
            actor=username,
            target=username,
            message=message,
        )

    def login(self, username, password) -> tuple[bool, str, dict | None]:
        username = self._normalize_username(username)
        if not username or not password:
            return False, "Vui lòng nhập đầy đủ tài khoản và mật khẩu", None

        now = self._now()
        generic_error = "Tài khoản hoặc mật khẩu không đúng"
        with self.db.conn() as connection:
            row = connection.execute(
                "SELECT * FROM TaiKhoan WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                self._log(
                    "LOGIN", False, actor=username,
                    message=generic_error, connection=connection,
                )
                return False, generic_error, None

            username = row["username"]
            if row["isActive"] != 1:
                message = "Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ Admin."
                self._log(
                    "LOGIN", False, actor=username,
                    message=message, connection=connection,
                )
                return False, message, None

            locked_until = self._parse_dt(row["lockedUntil"])
            if locked_until and locked_until > now:
                message = (
                    "Tài khoản đang bị khóa tạm thời đến "
                    f"{locked_until.strftime('%H:%M:%S %d/%m/%Y')}."
                )
                self._log(
                    "LOGIN", False, actor=username,
                    message=message, connection=connection,
                )
                return False, message, None

            if not self._verify_password(password, row):
                attempts = int(row["failedAttempts"] or 0) + 1
                if attempts >= self.FAILED_ATTEMPT_LIMIT:
                    lock_until = now + timedelta(minutes=self.LOCKOUT_MINUTES)
                    connection.execute(
                        """
                        UPDATE TaiKhoan
                        SET failedAttempts = 0, lockedUntil = ?,
                            updatedAt = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (self._format_dt(lock_until), row["id"]),
                    )
                    message = (
                        f"Đăng nhập sai quá {self.FAILED_ATTEMPT_LIMIT} lần. "
                        f"Tài khoản bị khóa {self.LOCKOUT_MINUTES} phút."
                    )
                else:
                    connection.execute(
                        """
                        UPDATE TaiKhoan
                        SET failedAttempts = ?, updatedAt = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (attempts, row["id"]),
                    )
                    message = (
                        f"{generic_error}. Còn "
                        f"{self.FAILED_ATTEMPT_LIMIT - attempts} lần thử."
                    )
                self._log(
                    "LOGIN", False, actor=username,
                    message=message, connection=connection,
                )
                return False, message, None

            login_time = self._format_dt(now)
            connection.execute(
                """
                UPDATE TaiKhoan
                SET failedAttempts = 0, lockedUntil = '',
                    lastLoginAt = ?, updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (login_time, row["id"]),
            )
            self._log(
                "LOGIN", True, actor=username,
                message="Đăng nhập thành công", connection=connection,
            )
            user = dict(row)
            user.update(
                failedAttempts=0,
                lockedUntil="",
                lastLoginAt=login_time,
            )
            return True, "Đăng nhập thành công", user

    def logout(self, username: str):
        self._log("LOGOUT", True, actor=username, message="Đăng xuất")
    @staticmethod
    def _validate_lecturer_fields(phone: str, dob: str) -> str:
        phone = (phone or "").strip()
        if not phone:
            return "Số điện thoại không được để trống"
        if not re.fullmatch(r"(0[2-9])\d{8,9}", phone):
            return (
                "Số điện thoại không hợp lệ "
                "(bắt đầu bằng 0, gồm 10-11 chữ số)"
            )

        dob = (dob or "").strip()
        if not dob:
            return "Ngày sinh không được để trống"
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", dob):
            return "Ngày sinh không đúng định dạng DD/MM/YYYY"
        try:
            parsed = datetime.strptime(dob, "%d/%m/%Y")
        except ValueError:
            return "Ngày sinh không tồn tại"
        if parsed.year < 1900 or parsed > datetime.now():
            return "Ngày sinh phải từ năm 1900 đến hiện tại"
        return ""

    def create_account(
        self,
        actor_username,
        username,
        temporary_password,
        confirm_password,
        ho_ten,
        email,
        so_dien_thoai="",
        role="GiangVien",
        ma_gv="",
        gioi_tinh="",
        ngay_sinh="",
        bo_mon="",
    ) -> tuple[bool, str]:
        username = self._normalize_username(username)
        ho_ten = self._normalize_person_name(ho_ten)
        email = (email or "").strip().lower()
        phone = self._clean_phone(so_dien_thoai)
        role = (role or "").strip()
        ma_gv = (ma_gv or "").strip().upper()
        gioi_tinh = (gioi_tinh or "").strip() or "Nam"
        ngay_sinh = (ngay_sinh or "").strip()
        bo_mon = " ".join((bo_mon or "").split())

        if not self._is_valid_username(username):
            return False, (
                "Tài khoản phải có 3–40 ký tự và chỉ gồm chữ, số, "
                "khoảng trắng, dấu chấm, gạch ngang hoặc gạch dưới"
            )
        if not ho_ten or not self._is_valid_person_name(ho_ten):
            return False, "Họ tên chỉ được chứa chữ cái và khoảng trắng"
        if not self._is_valid_email(email):
            return False, "Email bắt buộc và phải đúng định dạng"
        if role not in self.VALID_ROLES:
            return False, "Vai trò không hợp lệ"
        if temporary_password != confirm_password:
            return False, "Mật khẩu xác nhận không khớp"
        ok, message = self._validate_password(temporary_password)
        if not ok:
            return False, message

        dob_db = ""
        if role == "GiangVien":
            error = self._validate_lecturer_fields(phone, ngay_sinh)
            if error:
                return False, error
            if not ma_gv:
                return False, "Mã giảng viên không được để trống"
            if not self._is_valid_ma_gv(ma_gv):
                return False, "Mã giảng viên chỉ gồm chữ in hoa và số"
            if gioi_tinh not in self.VALID_GENDERS:
                return False, "Giới tính không hợp lệ"
            if not bo_mon:
                return False, "Bộ môn không được để trống"
            dob_db = self._dob_to_db(ngay_sinh)

        salt = self._new_salt()
        password_hash = self._hash_value(temporary_password, salt)
        try:
            with self.db.conn() as connection:
                if not self._is_admin(actor_username, connection):
                    return False, "Chỉ Admin mới được tạo tài khoản"

                duplicate = connection.execute(
                    """
                    SELECT 1 FROM TaiKhoan
                    WHERE username = ? OR lower(email) = lower(?)
                    """,
                    (username, email),
                ).fetchone()
                if duplicate:
                    return False, "Tài khoản hoặc email đã tồn tại"

                if phone and connection.execute(
                    """
                    SELECT 1 FROM TaiKhoan
                    WHERE soDienThoai = ? AND soDienThoai <> ''
                    """,
                    (phone,),
                ).fetchone():
                    return False, "Số điện thoại đã được sử dụng"

                if role == "GiangVien" and connection.execute(
                    "SELECT 1 FROM GiangVien WHERE maGV = ?",
                    (ma_gv,),
                ).fetchone():
                    return False, f"Mã giảng viên '{ma_gv}' đã được sử dụng"

                cursor = connection.execute(
                    """
                    INSERT INTO TaiKhoan (
                        username, passwordHash, passwordSalt, hoTen,
                        email, soDienThoai, vaiTro, isActive,
                        passwordIterations, mustChangePassword,
                        passwordChangedAt
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?)
                    """,
                    (
                        username,
                        password_hash,
                        salt,
                        ho_ten,
                        email,
                        phone,
                        role,
                        self.PASSWORD_ITERATIONS,
                        self._format_dt(self._now()),
                    ),
                )
                if role == "GiangVien":
                    connection.execute(
                        """
                        INSERT INTO GiangVien (
                            taiKhoanId, maGV, gioiTinh, ngaySinh, boMon
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            cursor.lastrowid,
                            ma_gv,
                            gioi_tinh,
                            dob_db,
                            bo_mon,
                        ),
                    )
                self._log(
                    "ACCOUNT_CREATE",
                    True,
                    actor=actor_username,
                    target=username,
                    message=f"Tạo tài khoản vai trò {role}",
                    connection=connection,
                )
        except sqlite3.IntegrityError as exc:
            logger.warning("[AuthService] Account rejected: %s", exc)
            return False, (
                "Tài khoản, email, số điện thoại hoặc mã giảng viên "
                "đã tồn tại"
            )
        except Exception as exc:
            logger.exception("[AuthService] Cannot create account")
            return False, f"Không thể tạo tài khoản: {exc}"

        sent, email_message = self._send_temporary_password_email(
            actor_username,
            username,
            ho_ten,
            email,
            temporary_password,
        )
        result = (
            "Đã tạo tài khoản. Người dùng phải đổi mật khẩu "
            "khi đăng nhập lần đầu."
        )
        if sent:
            return True, f"{result}\nĐã gửi thông tin đăng nhập tới {email}."
        return True, (
            f"{result}\nKhông gửi được email tự động: {email_message}\n"
            "Admin cần chuyển mật khẩu tạm thời cho người dùng."
        )

    def get_accounts(self, actor_username: str) -> list[dict]:
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return []
            rows = connection.execute(
                """
                SELECT username, hoTen, email, soDienThoai, vaiTro,
                       isActive, failedAttempts, lockedUntil,
                       lastLoginAt, mustChangePassword, createdAt
                FROM TaiKhoan
                ORDER BY CASE vaiTro WHEN 'Admin' THEN 0 ELSE 1 END,
                         username
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_lecturers(self, actor_username: str) -> list[dict]:
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return []
            rows = connection.execute(
                """
                SELECT tk.username, gv.maGV, tk.hoTen, gv.gioiTinh,
                       gv.ngaySinh, tk.email, tk.soDienThoai,
                       gv.boMon, tk.vaiTro, tk.isActive, tk.createdAt
                FROM GiangVien gv
                JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                ORDER BY tk.hoTen
                """
            ).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["ngaySinh"] = self._dob_from_db(row["ngaySinh"])
        return result

    def get_lecturer_options(self, actor_username: str) -> list[dict]:
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return []
            rows = connection.execute(
                """
                SELECT tk.username, tk.hoTen
                FROM GiangVien gv
                JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                WHERE tk.isActive = 1
                  AND tk.vaiTro = 'GiangVien'
                ORDER BY tk.hoTen
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_lecturer(
        self,
        actor_username,
        username,
        ho_ten,
        email,
        so_dien_thoai="",
        gioi_tinh="",
        ngay_sinh="",
        bo_mon="",
        ma_gv="",
    ) -> tuple[bool, str]:
        username = self._normalize_username(username)
        ho_ten = self._normalize_person_name(ho_ten)
        email = (email or "").strip().lower()
        phone = self._clean_phone(so_dien_thoai)
        gioi_tinh = (gioi_tinh or "").strip() or "Nam"
        ngay_sinh = (ngay_sinh or "").strip()
        bo_mon = " ".join((bo_mon or "").split())
        ma_gv = (ma_gv or "").strip().upper()

        if not ho_ten or not self._is_valid_person_name(ho_ten):
            return False, (
                "Họ tên giảng viên chỉ được chứa chữ cái và khoảng trắng"
            )
        if not self._is_valid_email(email):
            return False, "Email bắt buộc và phải đúng định dạng"
        error = self._validate_lecturer_fields(phone, ngay_sinh)
        if error:
            return False, error
        if not ma_gv or not self._is_valid_ma_gv(ma_gv):
            return False, "Mã giảng viên chỉ gồm chữ in hoa và số"
        if gioi_tinh not in self.VALID_GENDERS:
            return False, "Giới tính không hợp lệ"
        if not bo_mon:
            return False, "Bộ môn không được để trống"

        try:
            with self.db.conn() as connection:
                if not self._is_admin(actor_username, connection):
                    return False, (
                        "Chỉ Admin mới được sửa thông tin giảng viên"
                    )
                target = connection.execute(
                    """
                    SELECT tk.id AS taiKhoanId, gv.id AS giangVienId
                    FROM TaiKhoan tk
                    JOIN GiangVien gv ON gv.taiKhoanId = tk.id
                    WHERE tk.username = ?
                      AND tk.vaiTro = 'GiangVien'
                    """,
                    (username,),
                ).fetchone()
                if not target:
                    return False, "Không tìm thấy giảng viên"

                duplicate = connection.execute(
                    """
                    SELECT 1 FROM TaiKhoan
                    WHERE id <> ?
                      AND (
                          lower(email) = lower(?)
                          OR soDienThoai = ?
                      )
                    """,
                    (target["taiKhoanId"], email, phone),
                ).fetchone()
                duplicate_code = connection.execute(
                    """
                    SELECT 1 FROM GiangVien
                    WHERE id <> ? AND maGV = ?
                    """,
                    (target["giangVienId"], ma_gv),
                ).fetchone()
                if duplicate or duplicate_code:
                    return False, (
                        "Email, số điện thoại hoặc mã giảng viên "
                        "đã được sử dụng"
                    )

                connection.execute(
                    """
                    UPDATE TaiKhoan
                    SET hoTen = ?, email = ?, soDienThoai = ?,
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (ho_ten, email, phone, target["taiKhoanId"]),
                )
                connection.execute(
                    """
                    UPDATE GiangVien
                    SET maGV = ?, gioiTinh = ?, ngaySinh = ?,
                        boMon = ?, updatedAt = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        ma_gv,
                        gioi_tinh,
                        self._dob_to_db(ngay_sinh),
                        bo_mon,
                        target["giangVienId"],
                    ),
                )
                self._log(
                    "ACCOUNT_UPDATE",
                    True,
                    actor=actor_username,
                    target=username,
                    message="Cập nhật hồ sơ giảng viên",
                    connection=connection,
                )
        except sqlite3.IntegrityError:
            return False, (
                "Email, số điện thoại hoặc mã giảng viên đã được sử dụng"
            )
        return True, "Cập nhật giảng viên thành công"

    def delete_lecturer(
        self,
        actor_username: str,
        target_username: str,
    ) -> tuple[bool, str]:
        """Không xóa vật lý; chỉ ngừng hoạt động tài khoản giảng viên."""
        target_username = self._normalize_username(target_username)
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return False, (
                    "Chỉ Admin mới được ngừng hoạt động giảng viên"
                )
            lecturer = connection.execute(
                """
                SELECT tk.id, tk.hoTen, tk.isActive,
                       gv.id AS giangVienId
                FROM TaiKhoan tk
                JOIN GiangVien gv ON gv.taiKhoanId = tk.id
                WHERE tk.username = ?
                  AND tk.vaiTro = 'GiangVien'
                """,
                (target_username,),
            ).fetchone()
            if not lecturer:
                return False, "Không tìm thấy giảng viên"
            if lecturer["isActive"] == 0:
                return True, "Giảng viên đã ở trạng thái ngừng hoạt động"

            homerooms = connection.execute(
                """
                SELECT COUNT(*) FROM LopHoc
                WHERE giangVienChuNhiemId = ?
                """,
                (lecturer["giangVienId"],),
            ).fetchone()[0]
            sections = connection.execute(
                """
                SELECT COUNT(*) FROM LopHocPhan
                WHERE giangVienId = ?
                  AND trangThai NOT IN ('DA_KET_THUC', 'DA_HUY')
                """,
                (lecturer["giangVienId"],),
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE TaiKhoan
                SET isActive = 0, failedAttempts = 0, lockedUntil = '',
                    updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (lecturer["id"],),
            )
            self._log(
                "LECTURER_DISABLE",
                True,
                actor=actor_username,
                target=target_username,
                message=(
                    f"Ngừng hoạt động; lớp chủ nhiệm={homerooms}, "
                    f"lớp học phần={sections}"
                ),
                connection=connection,
            )

        warning = ""
        if homerooms or sections:
            warning = (
                f" Còn {homerooms} lớp chủ nhiệm và {sections} "
                "lớp học phần cần được phân công lại."
            )
        return True, (
            f"Đã ngừng hoạt động giảng viên "
            f"'{lecturer['hoTen']}'.{warning}"
        )
    def set_account_active(
        self,
        actor_username: str,
        target_username: str,
        active: bool,
    ) -> tuple[bool, str]:
        if (
            actor_username.casefold() == target_username.casefold()
            and not active
        ):
            return False, (
                "Admin không thể tự vô hiệu hóa tài khoản đang đăng nhập"
            )

        try:
            with self.db.conn() as connection:
                if not self._is_admin(actor_username, connection):
                    return False, "Chỉ Admin mới được quản lý tài khoản"
                row = connection.execute(
                    """
                    SELECT id, username, vaiTro, isActive
                    FROM TaiKhoan
                    WHERE username = ?
                    """,
                    (target_username,),
                ).fetchone()
                if not row:
                    return False, "Không tìm thấy tài khoản"

                if (
                    not active
                    and row["vaiTro"] == "Admin"
                    and row["isActive"] == 1
                ):
                    active_admins = connection.execute(
                        """
                        SELECT COUNT(*) FROM TaiKhoan
                        WHERE vaiTro = 'Admin' AND isActive = 1
                        """
                    ).fetchone()[0]
                    if active_admins <= 1:
                        return False, (
                            "Không thể vô hiệu hóa Admin đang hoạt động cuối cùng"
                        )

                connection.execute(
                    """
                    UPDATE TaiKhoan
                    SET isActive = ?, failedAttempts = 0, lockedUntil = '',
                        updatedAt = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (int(bool(active)), row["id"]),
                )
                self._log(
                    "ACCOUNT_ENABLE" if active else "ACCOUNT_DISABLE",
                    True,
                    actor=actor_username,
                    target=row["username"],
                    message=(
                        "Kích hoạt tài khoản"
                        if active
                        else "Vô hiệu hóa tài khoản"
                    ),
                    connection=connection,
                )
        except sqlite3.IntegrityError as exc:
            return False, str(exc)
        return True, "Đã cập nhật trạng thái tài khoản"

    def unlock_account(
        self,
        actor_username: str,
        target_username: str,
    ) -> tuple[bool, str]:
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return False, "Chỉ Admin mới được mở khóa tài khoản"
            cursor = connection.execute(
                """
                UPDATE TaiKhoan
                SET failedAttempts = 0, lockedUntil = '',
                    updatedAt = CURRENT_TIMESTAMP
                WHERE username = ?
                """,
                (target_username,),
            )
            if cursor.rowcount == 0:
                return False, "Không tìm thấy tài khoản"
            self._log(
                "ACCOUNT_UNLOCK",
                True,
                actor=actor_username,
                target=target_username,
                message="Mở khóa đăng nhập",
                connection=connection,
            )
        return True, "Đã mở khóa tài khoản"

    def admin_reset_password(
        self,
        actor_username: str,
        target_username: str,
        temporary_password: str,
        confirm_password: str,
    ) -> tuple[bool, str]:
        if temporary_password != confirm_password:
            return False, "Mật khẩu xác nhận không khớp"
        ok, message = self._validate_password(temporary_password)
        if not ok:
            return False, message

        salt = self._new_salt()
        password_hash = self._hash_value(temporary_password, salt)
        now_text = self._format_dt(self._now())
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return False, "Chỉ Admin mới được cấp lại mật khẩu"
            target = connection.execute(
                """
                SELECT id, username, hoTen, email
                FROM TaiKhoan
                WHERE username = ?
                """,
                (target_username,),
            ).fetchone()
            if not target:
                return False, "Không tìm thấy tài khoản"

            connection.execute(
                """
                UPDATE TaiKhoan
                SET passwordHash = ?, passwordSalt = ?,
                    passwordIterations = ?, mustChangePassword = 1,
                    passwordChangedAt = ?, failedAttempts = 0,
                    lockedUntil = '', updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    password_hash,
                    salt,
                    self.PASSWORD_ITERATIONS,
                    now_text,
                    target["id"],
                ),
            )
            connection.execute(
                """
                UPDATE PasswordResetToken
                SET usedAt = ?
                WHERE taiKhoanId = ? AND usedAt = ''
                """,
                (now_text, target["id"]),
            )
            self._log(
                "PASSWORD_ADMIN_RESET",
                True,
                actor=actor_username,
                target=target["username"],
                message="Admin cấp mật khẩu tạm thời",
                connection=connection,
            )

        sent, email_message = self._send_temporary_password_email(
            actor_username,
            target["username"],
            target["hoTen"],
            target["email"],
            temporary_password,
        )
        result = (
            "Đã cấp mật khẩu tạm thời. Người dùng phải đổi mật khẩu "
            "khi đăng nhập."
        )
        if sent:
            return True, (
                f"{result}\nĐã gửi mật khẩu tạm tới {target['email']}."
            )
        return True, (
            f"{result}\nKhông gửi được email tự động: {email_message}\n"
            "Admin cần chuyển mật khẩu tạm thời cho người dùng."
        )

    def change_password(
        self,
        username: str,
        old_password: str,
        new_password: str,
        confirm_password: str,
    ) -> tuple[bool, str]:
        if not old_password or not new_password:
            return False, "Vui lòng nhập đầy đủ mật khẩu"
        if new_password != confirm_password:
            return False, "Mật khẩu xác nhận không khớp"
        if hmac.compare_digest(old_password, new_password):
            return False, "Mật khẩu mới phải khác mật khẩu hiện tại"
        ok, message = self._validate_password(new_password)
        if not ok:
            return False, message

        with self.db.conn() as connection:
            row = connection.execute(
                "SELECT * FROM TaiKhoan WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or not self._verify_password(old_password, row):
                self._log(
                    "PASSWORD_CHANGE",
                    False,
                    actor=username,
                    target=username,
                    message="Mật khẩu cũ không đúng",
                    connection=connection,
                )
                return False, "Mật khẩu cũ không đúng"

            salt = self._new_salt()
            password_hash = self._hash_value(new_password, salt)
            now_text = self._format_dt(self._now())
            connection.execute(
                """
                UPDATE TaiKhoan
                SET passwordHash = ?, passwordSalt = ?,
                    passwordIterations = ?, mustChangePassword = 0,
                    passwordChangedAt = ?, failedAttempts = 0,
                    lockedUntil = '', updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    password_hash,
                    salt,
                    self.PASSWORD_ITERATIONS,
                    now_text,
                    row["id"],
                ),
            )
            self._log(
                "PASSWORD_CHANGE",
                True,
                actor=row["username"],
                target=row["username"],
                message="Đổi mật khẩu thành công",
                connection=connection,
            )
            display_name, email = row["hoTen"], row["email"]

        self._send_password_changed_notice(
            row["username"],
            display_name,
            email,
        )
        return True, "Đổi mật khẩu thành công"
    def request_password_reset(
        self,
        identifier: str,
    ) -> tuple[bool, str]:
        identifier = (identifier or "").strip()
        if not identifier:
            return False, "Vui lòng nhập tài khoản hoặc email"

        with self.db.conn() as connection:
            account = connection.execute(
                """
                SELECT id, username, hoTen, email, isActive
                FROM TaiKhoan
                WHERE username = ? OR lower(email) = lower(?)
                """,
                (identifier, identifier),
            ).fetchone()
            if not account:
                self._log(
                    "PASSWORD_RESET_REQUEST",
                    False,
                    actor=identifier,
                    message="Không tìm thấy tài khoản/email",
                    connection=connection,
                )
                return False, "Không tìm thấy tài khoản hoặc email"
            if account["isActive"] != 1:
                return False, (
                    "Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ Admin."
                )
            if not account["email"]:
                return False, (
                    "Tài khoản chưa có email. Vui lòng liên hệ Admin."
                )

            latest = connection.execute(
                """
                SELECT createdAt
                FROM PasswordResetToken
                WHERE taiKhoanId = ? AND usedAt = ''
                ORDER BY id DESC
                LIMIT 1
                """,
                (account["id"],),
            ).fetchone()
            if latest:
                created_at = self._parse_dt(latest["createdAt"])
                if created_at:
                    remaining = (
                        self.OTP_REQUEST_COOLDOWN_SECONDS
                        - int((self._now() - created_at).total_seconds())
                    )
                    if remaining > 0:
                        return False, (
                            f"Vui lòng chờ {remaining} giây trước khi "
                            "yêu cầu mã OTP mới."
                        )

        otp = f"{secrets.randbelow(1_000_000):06d}"
        token_salt = self._new_salt()
        token_hash = self._hash_value(otp, token_salt)
        expires = self._now() + timedelta(
            minutes=self.OTP_EXPIRES_MINUTES
        )
        try:
            sent, message = self.email_service.send_password_reset_otp(
                account["email"],
                account["hoTen"],
                otp,
                self.OTP_EXPIRES_MINUTES,
            )
        except Exception:
            logger.exception("[AuthService] Cannot send password reset OTP")
            sent, message = False, (
                "Dịch vụ email gặp lỗi không xác định. "
                "Vui lòng liên hệ Admin."
            )
        if not sent:
            self._log(
                "PASSWORD_RESET_REQUEST",
                False,
                actor=account["username"],
                target=account["username"],
                message=message,
            )
            return False, message

        now_text = self._format_dt(self._now())
        with self.db.conn() as connection:
            connection.execute(
                """
                UPDATE PasswordResetToken
                SET usedAt = ?
                WHERE taiKhoanId = ? AND usedAt = ''
                """,
                (now_text, account["id"]),
            )
            connection.execute(
                """
                INSERT INTO PasswordResetToken (
                    taiKhoanId, tokenHash, tokenSalt, expiresAt, createdAt
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    account["id"],
                    token_hash,
                    token_salt,
                    self._format_dt(expires),
                    now_text,
                ),
            )
            self._log(
                "PASSWORD_RESET_REQUEST",
                True,
                actor=account["username"],
                target=account["username"],
                message="Đã gửi OTP",
                connection=connection,
            )
        return True, message

    def reset_password_with_otp(
        self,
        identifier: str,
        otp: str,
        new_password: str,
        confirm_password: str,
    ) -> tuple[bool, str]:
        identifier = (identifier or "").strip()
        otp = (otp or "").strip()
        if not identifier or not otp or not new_password:
            return False, "Vui lòng nhập đầy đủ thông tin"
        if new_password != confirm_password:
            return False, "Mật khẩu xác nhận không khớp"
        ok, message = self._validate_password(new_password)
        if not ok:
            return False, message

        now = self._now()
        now_text = self._format_dt(now)
        with self.db.conn() as connection:
            account = connection.execute(
                """
                SELECT id, username, hoTen, email
                FROM TaiKhoan
                WHERE username = ? OR lower(email) = lower(?)
                """,
                (identifier, identifier),
            ).fetchone()
            if not account:
                return False, "Mã OTP không hợp lệ hoặc đã hết hạn"

            token = connection.execute(
                """
                SELECT *
                FROM PasswordResetToken
                WHERE taiKhoanId = ? AND usedAt = ''
                ORDER BY id DESC
                LIMIT 1
                """,
                (account["id"],),
            ).fetchone()
            if not token:
                return False, "Mã OTP không hợp lệ hoặc đã hết hạn"

            expires_at = self._parse_dt(token["expiresAt"])
            if not expires_at or expires_at < now:
                connection.execute(
                    """
                    UPDATE PasswordResetToken
                    SET usedAt = ?
                    WHERE id = ?
                    """,
                    (now_text, token["id"]),
                )
                return False, (
                    "Mã OTP đã hết hạn. Vui lòng yêu cầu mã mới."
                )
            if int(token["attempts"] or 0) >= self.OTP_MAX_ATTEMPTS:
                connection.execute(
                    """
                    UPDATE PasswordResetToken
                    SET usedAt = ?
                    WHERE id = ?
                    """,
                    (now_text, token["id"]),
                )
                return False, (
                    "Mã OTP đã bị khóa do nhập sai quá nhiều lần."
                )

            actual_hash = self._hash_value(otp, token["tokenSalt"])
            if not hmac.compare_digest(actual_hash, token["tokenHash"]):
                connection.execute(
                    """
                    UPDATE PasswordResetToken
                    SET attempts = attempts + 1
                    WHERE id = ?
                    """,
                    (token["id"],),
                )
                self._log(
                    "PASSWORD_OTP_RESET",
                    False,
                    actor=account["username"],
                    target=account["username"],
                    message="OTP không đúng",
                    connection=connection,
                )
                return False, "Mã OTP không đúng"

            salt = self._new_salt()
            password_hash = self._hash_value(new_password, salt)
            connection.execute(
                """
                UPDATE TaiKhoan
                SET passwordHash = ?, passwordSalt = ?,
                    passwordIterations = ?, mustChangePassword = 0,
                    passwordChangedAt = ?, failedAttempts = 0,
                    lockedUntil = '', updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    password_hash,
                    salt,
                    self.PASSWORD_ITERATIONS,
                    now_text,
                    account["id"],
                ),
            )
            connection.execute(
                """
                UPDATE PasswordResetToken
                SET usedAt = ?
                WHERE id = ?
                """,
                (now_text, token["id"]),
            )
            self._log(
                "PASSWORD_OTP_RESET",
                True,
                actor=account["username"],
                target=account["username"],
                message="Đặt lại mật khẩu bằng OTP",
                connection=connection,
            )

        self._send_password_changed_notice(
            account["username"],
            account["hoTen"],
            account["email"],
        )
        return True, "Đặt lại mật khẩu thành công"

    def get_auth_logs(
        self,
        actor_username: str,
        limit: int = 300,
    ) -> list[dict]:
        safe_limit = max(1, min(int(limit), 1000))
        with self.db.conn() as connection:
            if not self._is_admin(actor_username, connection):
                return []
            rows = connection.execute(
                """
                SELECT id,
                       actorUsernameSnapshot AS actorUsername,
                       targetUsernameSnapshot AS targetUsername,
                       eventType, success, message, createdAt
                FROM AuthLog
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
