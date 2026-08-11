# ui/change_password_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFormLayout, QFrame
)
from PyQt5.QtCore import Qt


class ChangePasswordDialog(QDialog):
    def __init__(self, auth_svc, current_user: dict, force_change=False, parent=None):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self.current_user = current_user
        self.force_change = force_change

        self.setWindowTitle(
            "Đổi mật khẩu tạm thời" if force_change else "Đổi mật khẩu"
        )
        self.setFixedSize(440, 360 if force_change else 320)
        self.setStyleSheet(self._style())
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)

        title = QLabel("ĐỔI MẬT KHẨU")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("title")
        root.addWidget(title)

        user = QLabel(
            f"Tài khoản: {self.current_user.get('username', '')}"
        )
        user.setAlignment(Qt.AlignCenter)
        user.setObjectName("subtitle")
        root.addWidget(user)

        if self.force_change:
            note = QLabel(
                "Đây là mật khẩu tạm thời. Bạn phải đặt mật khẩu mới "
                "trước khi sử dụng hệ thống."
            )
            note.setWordWrap(True)
            note.setObjectName("warning")
            root.addWidget(note)

        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_old = QLineEdit()
        self.txt_new = QLineEdit()
        self.txt_confirm = QLineEdit()

        self.txt_old.setEchoMode(QLineEdit.Password)
        self.txt_new.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setEchoMode(QLineEdit.Password)

        form.addRow("Mật khẩu cũ", self.txt_old)
        form.addRow("Mật khẩu mới", self.txt_new)
        form.addRow("Xác nhận", self.txt_confirm)

        layout.addLayout(form)

        btn = QPushButton("Cập nhật mật khẩu")
        btn.setObjectName("primaryBtn")
        btn.setMinimumHeight(38)
        btn.clicked.connect(self._change)
        layout.addWidget(btn)

        root.addWidget(card)

    def _change(self):
        ok, msg = self.auth_svc.change_password(
            self.current_user["username"],
            self.txt_old.text(),
            self.txt_new.text(),
            self.txt_confirm.text()
        )

        if ok:
            self.current_user["mustChangePassword"] = 0
            QMessageBox.information(self, "Thành công", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Thất bại", msg)

    @staticmethod
    def _style():
        return """
        QDialog {
            background: #EEF1F7;
            font-family: Segoe UI;
            font-size: 13px;
        }

        QLabel#title {
            color: #2F2A7E;
            font-size: 18px;
            font-weight: 700;
        }

        QLabel#subtitle {
            color: #666;
        }

        QLabel#warning {
            color: #9A3412;
            background: #FFF7ED;
            border: 1px solid #FDBA74;
            border-radius: 6px;
            padding: 8px;
        }

        QFrame#card {
            background: white;
            border-radius: 14px;
            border: 1px solid #DDE1EA;
        }

        QLineEdit {
            border: 1px solid #CCD2DD;
            border-radius: 7px;
            padding: 6px 9px;
            background: #FAFAFC;
            min-height: 28px;
        }

        QLineEdit:focus {
            border: 1px solid #534AB7;
            background: white;
        }

        QPushButton#primaryBtn {
            background: #534AB7;
            color: white;
            border-radius: 8px;
            font-weight: 600;
        }

        QPushButton#primaryBtn:hover {
            background: #443AA5;
        }
        """
