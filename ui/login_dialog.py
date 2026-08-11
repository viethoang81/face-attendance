# ui/login_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame, QCheckBox, QSizePolicy
)
from PyQt5.QtCore import Qt


class LoginDialog(QDialog):
    def __init__(self, auth_svc, parent=None):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self.current_user = None

        self.setWindowTitle("Đăng nhập cán bộ")
        self.setMinimumSize(600, 570)
        self.resize(600, 590)
        self.setStyleSheet(self._style())
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(46, 34, 46, 36)
        root.setSpacing(10)

        title = QLabel("HỆ THỐNG ĐIỂM DANH")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("title")
        title.setMinimumHeight(42)
        root.addWidget(title)

        subtitle = QLabel("Đăng nhập tài khoản cán bộ / quản trị viên")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setObjectName("subtitle")
        subtitle.setMinimumHeight(24)
        root.addWidget(subtitle)
        root.addSpacing(8)

        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(350)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 26, 34, 26)
        card_layout.setSpacing(8)

        lbl_user = QLabel("Tài khoản")
        lbl_user.setObjectName("fieldLabel")
        lbl_user.setMinimumHeight(22)
        card_layout.addWidget(lbl_user)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Nhập tài khoản")
        self.txt_username.setFixedHeight(44)
        card_layout.addWidget(self.txt_username)
        card_layout.addSpacing(8)

        lbl_pass = QLabel("Mật khẩu")
        lbl_pass.setObjectName("fieldLabel")
        lbl_pass.setMinimumHeight(22)
        card_layout.addWidget(lbl_pass)

        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Nhập mật khẩu")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setFixedHeight(44)
        card_layout.addWidget(self.txt_password)

        option_row = QHBoxLayout()
        option_row.setContentsMargins(0, 2, 0, 2)
        option_row.setSpacing(12)

        self.chk_show = QCheckBox("Hiện mật khẩu")
        self.chk_show.stateChanged.connect(self._toggle_password)
        option_row.addWidget(self.chk_show)
        option_row.addStretch()

        self.btn_forgot = QPushButton("Quên mật khẩu?")
        self.btn_forgot.setObjectName("linkBtn")
        self.btn_forgot.setFixedHeight(30)
        self.btn_forgot.clicked.connect(self._open_forgot)
        option_row.addWidget(self.btn_forgot)

        card_layout.addLayout(option_row)
        card_layout.addSpacing(6)

        self.btn_login = QPushButton("Đăng nhập")
        self.btn_login.setObjectName("primaryBtn")
        self.btn_login.setFixedHeight(46)
        self.btn_login.clicked.connect(self._login)
        card_layout.addWidget(self.btn_login)

        root.addWidget(card)
        root.addStretch()

        self.txt_password.returnPressed.connect(self._login)

    def _toggle_password(self):
        if self.chk_show.isChecked():
            self.txt_password.setEchoMode(QLineEdit.Normal)
        else:
            self.txt_password.setEchoMode(QLineEdit.Password)

    def _login(self):
        ok, msg, user = self.auth_svc.login(
            self.txt_username.text(),
            self.txt_password.text()
        )

        if ok:
            if user.get("mustChangePassword") == 1:
                from ui.change_password_dialog import ChangePasswordDialog
                dlg = ChangePasswordDialog(
                    self.auth_svc, user, force_change=True, parent=self
                )
                if dlg.exec_() != QDialog.Accepted:
                    QMessageBox.information(
                        self,
                        "Yêu cầu đổi mật khẩu",
                        "Bạn phải đổi mật khẩu tạm thời trước khi vào hệ thống.",
                    )
                    return
                user["mustChangePassword"] = 0
            self.current_user = user
            self.accept()
        else:
            QMessageBox.warning(self, "Đăng nhập thất bại", msg)

    def _open_forgot(self):
        from ui.forgot_password_dialog import ForgotPasswordDialog
        dlg = ForgotPasswordDialog(self.auth_svc, parent=self)
        dlg.exec_()

    @staticmethod
    def _style():
        return """
        QDialog {
            background: #EEF1F7;
            font-family: Segoe UI;
            font-size: 14px;
        }

        QLabel#title {
            color: #2F2A7E;
            font-size: 25px;
            font-weight: 800;
        }

        QLabel#subtitle {
            color: #666666;
            font-size: 14px;
        }

        QFrame#card {
            background: white;
            border-radius: 12px;
            border: 1px solid #DDE1EA;
        }

        QLabel#fieldLabel {
            color: #333333;
            font-size: 15px;
            font-weight: 700;
        }

        QLineEdit {
            border: 1px solid #CCD2DD;
            border-radius: 9px;
            padding: 8px 12px;
            background: #FAFAFC;
            font-size: 14px;
        }

        QLineEdit:focus {
            border: 1px solid #534AB7;
            background: white;
        }

        QCheckBox {
            color: #555555;
            font-size: 13px;
        }

        QPushButton#primaryBtn {
            background: #534AB7;
            color: white;
            border-radius: 9px;
            font-size: 15px;
            font-weight: 700;
        }

        QPushButton#primaryBtn:hover {
            background: #443AA5;
        }

        QPushButton#linkBtn {
            background: transparent;
            border: none;
            color: #185FA5;
            font-size: 13px;
            font-weight: 600;
            padding: 2px 0;
        }

        QPushButton#linkBtn:hover {
            color: #0F477E;
            text-decoration: underline;
        }
        """
