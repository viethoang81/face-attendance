from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ForgotPasswordDialog(QDialog):
    """Two-step password recovery: request OTP first, then enter a new password."""

    def __init__(self, auth_svc, parent=None):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self._otp_identifier = ""
        self.setWindowTitle("Khôi phục mật khẩu")
        self.resize(500, 320)
        self.setMinimumWidth(500)
        self.setStyleSheet(self._style())
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)

        title = QLabel("KHÔI PHỤC MẬT KHẨU")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("title")
        root.addWidget(title)

        desc = QLabel(
            "Bước 1: nhập tài khoản hoặc email đã đăng ký để nhận mã OTP.\n"
            "Hãy liên hệ Admin để được cấp mật khẩu tạm thời."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setObjectName("subtitle")
        root.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        identifier_form = QFormLayout()
        identifier_form.setSpacing(10)
        self.txt_identifier = QLineEdit()
        self.txt_identifier.setPlaceholderText("Tài khoản hoặc email đã đăng ký")
        self.txt_identifier.textChanged.connect(self._on_identifier_changed)
        identifier_form.addRow("Tài khoản/email", self.txt_identifier)
        layout.addLayout(identifier_form)

        self.btn_send = QPushButton("Gửi mã OTP")
        self.btn_send.setObjectName("secondaryBtn")
        self.btn_send.setMinimumHeight(36)
        self.btn_send.setEnabled(False)
        self.btn_send.clicked.connect(self._send_otp)
        layout.addWidget(self.btn_send)

        self.lbl_status = QLabel(
            "Chưa có mã OTP. Hãy nhập tài khoản/email và nhấn “Gửi mã OTP”."
        )
        self.lbl_status.setObjectName("status")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        self.recovery_panel = QFrame()
        recovery_form = QFormLayout(self.recovery_panel)
        recovery_form.setContentsMargins(0, 8, 0, 0)
        recovery_form.setSpacing(10)
        self.txt_otp = QLineEdit()
        self.txt_new_password = QLineEdit()
        self.txt_confirm = QLineEdit()

        self.txt_otp.setPlaceholderText("Mã OTP 6 số đã nhận")
        self.txt_otp.setMaxLength(6)
        self.txt_new_password.setPlaceholderText("Ít nhất 8 ký tự, gồm chữ và số")
        self.txt_new_password.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setEchoMode(QLineEdit.Password)
        recovery_form.addRow("Mã OTP", self.txt_otp)
        recovery_form.addRow("Mật khẩu mới", self.txt_new_password)
        recovery_form.addRow("Xác nhận", self.txt_confirm)
        self.recovery_panel.setVisible(False)
        layout.addWidget(self.recovery_panel)

        self.btn_reset = QPushButton("Đặt lại mật khẩu")
        self.btn_reset.setObjectName("primaryBtn")
        self.btn_reset.setMinimumHeight(38)
        self.btn_reset.setVisible(False)
        self.btn_reset.clicked.connect(self._reset_password)
        layout.addWidget(self.btn_reset)

        root.addWidget(card)
        self.txt_identifier.setFocus()

    def _on_identifier_changed(self, text: str):
        identifier = text.strip()
        self.btn_send.setEnabled(bool(identifier))
        if self._otp_identifier and identifier != self._otp_identifier:
            self._hide_recovery_step()

    def _show_recovery_step(self, identifier: str):
        self._otp_identifier = identifier
        self.lbl_status.setText(
            "Đã gửi OTP. Bước 2: nhập mã nhận được và đặt mật khẩu mới."
        )
        self.lbl_status.setProperty("success", True)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.recovery_panel.setVisible(True)
        self.btn_reset.setVisible(True)
        self.btn_send.setText("Gửi lại mã OTP")
        self.resize(500, 470)

    def _hide_recovery_step(self):
        self._otp_identifier = ""
        self.txt_otp.clear()
        self.txt_new_password.clear()
        self.txt_confirm.clear()
        self.recovery_panel.setVisible(False)
        self.btn_reset.setVisible(False)
        self.btn_send.setText("Gửi mã OTP")
        self.lbl_status.setText(
            "Tài khoản/email đã thay đổi. Hãy gửi một mã OTP mới."
        )
        self.lbl_status.setProperty("success", False)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.resize(500, 320)

    def _send_otp(self):
        identifier = self.txt_identifier.text().strip()
        if not identifier:
            QMessageBox.warning(
                self, "Thiếu thông tin", "Vui lòng nhập tài khoản hoặc email."
            )
            return

        ok, message = self.auth_svc.request_password_reset(identifier)
        if ok:
            self._show_recovery_step(identifier)
            QMessageBox.information(self, "Đã gửi OTP", message)
            self.txt_otp.setFocus()
        else:
            QMessageBox.warning(self, "Không thể gửi OTP", message)

    def _reset_password(self):
        if not self._otp_identifier:
            QMessageBox.warning(
                self, "Chưa có OTP", "Vui lòng gửi mã OTP trước khi đặt lại mật khẩu."
            )
            return

        ok, message = self.auth_svc.reset_password_with_otp(
            self._otp_identifier,
            self.txt_otp.text(),
            self.txt_new_password.text(),
            self.txt_confirm.text(),
        )
        if ok:
            QMessageBox.information(self, "Thành công", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Thất bại", message)

    @staticmethod
    def _style():
        return """
        QDialog { background:#EEF1F7; font-family:Segoe UI; font-size:13px; }
        QLabel#title { color:#2F2A7E; font-size:18px; font-weight:700; }
        QLabel#subtitle { color:#666; }
        QLabel#status {
            color:#666; background:#F4F6FA; border:1px solid #DDE1EA;
            border-radius:6px; padding:7px;
        }
        QLabel#status[success="true"] {
            color:#176B4D; background:#E8F7F0; border-color:#9BD8BF;
        }
        QFrame#card { background:white; border:1px solid #DDE1EA; border-radius:8px; }
        QLineEdit {
            border:1px solid #CCD2DD; border-radius:6px; padding:6px 9px;
            background:#FAFAFC; min-height:28px;
        }
        QLineEdit:focus { border:1px solid #534AB7; background:white; }
        QPushButton#secondaryBtn {
            background:#185FA5; color:white; border-radius:6px; font-weight:600;
        }
        QPushButton#secondaryBtn:disabled { background:#AAB4C3; }
        QPushButton#primaryBtn {
            background:#534AB7; color:white; border-radius:6px; font-weight:600;
        }
        """
