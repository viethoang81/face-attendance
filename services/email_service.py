import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    use_tls: bool
    use_ssl: bool
    timeout_seconds: int

    @classmethod
    def from_environment(cls):
        return cls(
            host=os.getenv("ATTENDANCE_SMTP_HOST", "").strip(),
            port=_read_int("ATTENDANCE_SMTP_PORT", 587),
            username=os.getenv("ATTENDANCE_SMTP_USERNAME", "").strip(),
            password=os.getenv("ATTENDANCE_SMTP_PASSWORD", ""),
            sender=os.getenv(
                "ATTENDANCE_SMTP_FROM",
                os.getenv("ATTENDANCE_SMTP_USERNAME", ""),
            ).strip(),
            use_tls=_read_bool("ATTENDANCE_SMTP_USE_TLS", True),
            use_ssl=_read_bool("ATTENDANCE_SMTP_USE_SSL", False),
            timeout_seconds=_read_int("ATTENDANCE_SMTP_TIMEOUT", 15),
        )

    @property
    def missing_fields(self) -> list[str]:
        required = {
            "ATTENDANCE_SMTP_HOST": self.host,
            "ATTENDANCE_SMTP_USERNAME": self.username,
            "ATTENDANCE_SMTP_PASSWORD": self.password,
            "ATTENDANCE_SMTP_FROM": self.sender,
        }
        return [name for name, value in required.items() if not value]


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _read_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("[EmailService] Invalid %s; using %d", name, default)
        return default


class SmtpEmailService:
    """Send transactional emails using optional SMTP environment settings.

    Email is deliberately optional: authentication and Admin password reset
    continue to work when SMTP is not configured.
    """

    def __init__(self, settings: SmtpSettings | None = None):
        self.settings = settings or SmtpSettings.from_environment()

    @property
    def available(self) -> bool:
        return not self.settings.missing_fields

    @property
    def configuration_message(self) -> str:
        if self.available:
            return "Email SMTP đã được cấu hình."
        missing = ", ".join(self.settings.missing_fields)
        return f"Chưa cấu hình email SMTP ({missing})."

    def _send(self, recipient: str, subject: str, body: str) -> tuple[bool, str]:
        if not recipient.strip():
            return False, "Tài khoản chưa có địa chỉ email."
        if not self.available:
            return False, (
                "Chưa cấu hình Gmail gửi thư. "
                "Vui lòng liên hệ Admin để được cấp mật khẩu tạm thời."
            )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.sender
        message["To"] = recipient
        message.set_content(body)

        try:
            context = ssl.create_default_context()
            if self.settings.use_ssl:
                smtp_factory = smtplib.SMTP_SSL
                smtp = smtp_factory(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.settings.timeout_seconds,
                    context=context,
                )
            else:
                smtp = smtplib.SMTP(
                    self.settings.host,
                    self.settings.port,
                    timeout=self.settings.timeout_seconds,
                )

            with smtp:
                if self.settings.use_tls and not self.settings.use_ssl:
                    smtp.starttls(context=context)
                smtp.login(self.settings.username, self.settings.password)
                smtp.send_message(message)
            return True, "Đã gửi email thành công."
        except smtplib.SMTPAuthenticationError:
            logger.exception("[EmailService] SMTP authentication failed")
            return False, (
                "Gmail từ chối đăng nhập. Hãy kiểm tra địa chỉ Gmail và "
                "App Password trong cấu hình."
            )
        except (OSError, smtplib.SMTPException):
            logger.exception("[EmailService] Cannot send email to %s", recipient)
            return False, (
                "Không thể gửi email. Vui lòng kiểm tra kết nối mạng và "
                "cấu hình Gmail, hoặc liên hệ Admin."
            )
        except Exception:
            logger.exception("[EmailService] Unexpected email error")
            return False, "Không thể tạo hoặc gửi email do lỗi không xác định."

    def send_password_reset_otp(
        self, recipient: str, display_name: str, otp: str, expires_minutes: int
    ) -> tuple[bool, str]:
        sent, message = self._send(
            recipient,
            "Mã khôi phục mật khẩu hệ thống điểm danh",
            f"Xin chào {display_name},\n\n"
            f"Mã OTP khôi phục mật khẩu của bạn là: {otp}\n"
            f"Mã có hiệu lực trong {expires_minutes} phút và chỉ sử dụng một lần.\n\n"
            "Nếu bạn không yêu cầu mã này, hãy bỏ qua email.\n\n"
            "Hệ thống điểm danh",
        )
        if sent:
            return True, "Đã gửi mã OTP tới email của tài khoản."
        return False, message

    def send_temporary_password(
        self,
        recipient: str,
        display_name: str,
        username: str,
        temporary_password: str,
    ) -> tuple[bool, str]:
        return self._send(
            recipient,
            "Tài khoản hệ thống điểm danh",
            f"Xin chào {display_name},\n\n"
            "Admin đã tạo hoặc cấp lại tài khoản hệ thống điểm danh cho bạn.\n\n"
            f"Tài khoản: {username}\n"
            f"Mật khẩu tạm thời: {temporary_password}\n\n"
            "Bạn phải đổi mật khẩu ngay trong lần đăng nhập tiếp theo. "
            "Không chia sẻ mật khẩu này với người khác.\n\n"
            "Hệ thống điểm danh",
        )

    def send_password_changed_notice(
        self, recipient: str, display_name: str
    ) -> tuple[bool, str]:
        return self._send(
            recipient,
            "Mật khẩu hệ thống điểm danh đã được thay đổi",
            f"Xin chào {display_name},\n\n"
            "Mật khẩu tài khoản hệ thống điểm danh của bạn vừa được thay đổi.\n"
            "Nếu bạn không thực hiện thao tác này, hãy liên hệ Admin ngay.\n\n"
            "Hệ thống điểm danh",
        )
