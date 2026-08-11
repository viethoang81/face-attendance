from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class RegisterDialog(QDialog):
    """
    Hộp thoại tạo tài khoản quản trị.

    Giảng viên được quản lý riêng trong TabLecturers nên hộp thoại
    quản lý tài khoản chung chỉ tạo thêm Admin.
    """

    def __init__(
        self,
        auth_svc,
        actor_username: str,
        parent=None,
    ):
        super().__init__(parent)

        self.auth_svc = auth_svc
        self.actor_username = actor_username

        self.setWindowTitle("Tạo tài khoản quản trị")
        self.setMinimumWidth(480)

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("TẠO TÀI KHOẢN QUẢN TRỊ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size:17px;"
            "font-weight:700;"
            "color:#2F2A7E;"
        )
        root.addWidget(title)

        note = QLabel(
            "Tài khoản giảng viên được tạo và quản lý trong "
            "mục Quản lý giảng viên."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color:#666;"
            "padding:6px 0 10px 0;"
        )
        root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_username = QLineEdit()
        self.txt_hoten = QLineEdit()
        self.txt_email = QLineEdit()
        self.txt_phone = QLineEdit()
        self.txt_password = QLineEdit()
        self.txt_confirm = QLineEdit()

        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setEchoMode(QLineEdit.Password)

        self.txt_password.setPlaceholderText(
            "Ít nhất 8 ký tự, gồm chữ và số"
        )
        self.txt_confirm.setPlaceholderText(
            "Nhập lại chính xác mật khẩu tạm"
        )

        self.chk_show_password = QCheckBox("Hiện mật khẩu")
        self.chk_show_password.toggled.connect(
            self._toggle_password
        )

        role_label = QLabel("Quản trị viên")
        role_label.setStyleSheet("font-weight:600;")

        form.addRow("Tài khoản *", self.txt_username)
        form.addRow("Họ tên *", self.txt_hoten)
        form.addRow("Email *", self.txt_email)
        form.addRow("Số điện thoại", self.txt_phone)
        form.addRow("Vai trò", role_label)
        form.addRow("Mật khẩu tạm *", self.txt_password)
        form.addRow("Xác nhận *", self.txt_confirm)
        form.addRow("", self.chk_show_password)

        root.addLayout(form)

        button = QPushButton("Tạo tài khoản Admin")
        button.setMinimumHeight(38)
        button.setStyleSheet(
            "background:#1D9E75;"
            "color:white;"
            "border-radius:6px;"
            "font-weight:600;"
        )
        button.clicked.connect(self._create)

        root.addWidget(button)

    def _create(self):
        ok, message = self.auth_svc.create_account(
            self.actor_username,
            self.txt_username.text(),
            self.txt_password.text(),
            self.txt_confirm.text(),
            self.txt_hoten.text(),
            self.txt_email.text(),
            self.txt_phone.text(),
            "Admin",
        )

        if ok:
            QMessageBox.information(
                self,
                "Thành công",
                message,
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Không thể tạo tài khoản",
                message,
            )

    def _toggle_password(
        self,
        checked: bool,
    ):
        mode = (
            QLineEdit.Normal
            if checked
            else QLineEdit.Password
        )

        self.txt_password.setEchoMode(mode)
        self.txt_confirm.setEchoMode(mode)