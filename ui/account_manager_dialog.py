from datetime import datetime
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
)

class TemporaryPasswordDialog(QDialog):
    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Cấp mật khẩu tạm thời - {username}")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        note = QLabel("Người dùng sẽ phải đổi mật khẩu ở lần đăng nhập tiếp theo.")
        note.setWordWrap(True)
        self.txt_password = QLineEdit()
        self.txt_confirm = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("Ít nhất 8 ký tự, gồm chữ và số")
        form.addRow(note)
        form.addRow("Mật khẩu tạm", self.txt_password)
        form.addRow("Xác nhận", self.txt_confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Cập nhật")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

class AuthLogDialog(QDialog):
    def __init__(self, auth_svc, actor_username: str, parent=None):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self.actor_username = actor_username
        self.setWindowTitle("Nhật ký xác thực và tài khoản")
        self.resize(1000, 600)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Thời gian", "Người thực hiện", "Tài khoản", "Sự kiện", "Kết quả", "Chi tiết"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        for column in range(5):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        layout.addWidget(self.table)
        self._load()

    def _load(self):
        rows = self.auth_svc.get_auth_logs(self.actor_username)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.get("createdAt", ""),
                row.get("actorUsername", ""),
                row.get("targetUsername", ""),
                row.get("eventType", ""),
                "Thành công" if row.get("success") else "Thất bại",
                row.get("message", ""),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value)))

class AccountManagerDialog(QDialog):
    def __init__(self, auth_svc, current_user: dict, parent=None):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self.current_user = current_user
        self.setWindowTitle("Quản lý tài khoản cán bộ")
        self.resize(1100, 620)
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title = QLabel("TÀI KHOẢN NỘI BỘ")
        title.setStyleSheet("font-size:17px;font-weight:700;color:#2F2A7E;")
        title_row.addWidget(title)
        title_row.addStretch()
        btn_logs = QPushButton("Xem nhật ký")
        btn_logs.clicked.connect(self._open_logs)
        title_row.addWidget(btn_logs)
        layout.addLayout(title_row)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Tài khoản",
                "Họ tên",
                "Email",
                "Vai trò",
                "Trạng thái",
                "Sai",
                "Khóa đến",
                "Đăng nhập cuối",
                "Đổi MK",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (0, 3, 4, 5, 6, 7, 8):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        actions = [
            ("Tạo tài khoản", self._create),
            ("Cấp mật khẩu tạm", self._reset_password),
            ("Mở khóa", self._unlock),
            ("Bật / tắt tài khoản", self._toggle_active),
            ("Làm mới", self._load),
        ]
        for text, slot in actions:
            button = QPushButton(text)
            button.setMinimumHeight(34)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _load(self):
        accounts = self.auth_svc.get_accounts(
            self.current_user.get("username", "")
        )
        self.table.setRowCount(len(accounts))
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row_index, account in enumerate(accounts):
            locked = bool(account.get("lockedUntil") and account["lockedUntil"] > now_text)
            if account.get("isActive") != 1:
                status = "Vô hiệu hóa"
            elif locked:
                status = "Khóa tạm thời"
            else:
                status = "Hoạt động"
            values = [
                account.get("username", ""),
                account.get("hoTen", ""),
                account.get("email", ""),
                account.get("vaiTro", ""),
                status,
                account.get("failedAttempts", 0),
                account.get("lockedUntil", ""),
                account.get("lastLoginAt", ""),
                "Bắt buộc" if account.get("mustChangePassword") else "Không",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (3, 4, 5, 8):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_index, column, item)
        if accounts:
            self.table.selectRow(0)

    def _selected_username(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Chọn tài khoản", "Vui lòng chọn một tài khoản.")
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _create(self):
        from ui.register_dialog import RegisterDialog

        dialog = RegisterDialog(
            self.auth_svc, self.current_user.get("username", ""), parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            self._load()

    def _reset_password(self):
        username = self._selected_username()
        if not username:
            return
        dialog = TemporaryPasswordDialog(username, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        ok, message = self.auth_svc.admin_reset_password(
            self.current_user.get("username", ""),
            username,
            dialog.txt_password.text(),
            dialog.txt_confirm.text(),
        )
        self._show_result(ok, message)

    def _unlock(self):
        username = self._selected_username()
        if not username:
            return
        ok, message = self.auth_svc.unlock_account(
            self.current_user.get("username", ""), username
        )
        self._show_result(ok, message)

    def _toggle_active(self):
        username = self._selected_username()
        if not username:
            return
        row = self.table.currentRow()
        status = self.table.item(row, 4).text()
        activate = status == "Vô hiệu hóa"
        action = "kích hoạt" if activate else "vô hiệu hóa"
        reply = QMessageBox.question(
            self,
            "Xác nhận",
            f"Bạn có chắc muốn {action} tài khoản '{username}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok, message = self.auth_svc.set_account_active(
            self.current_user.get("username", ""), username, activate
        )
        self._show_result(ok, message)

    def _open_logs(self):
        AuthLogDialog(
            self.auth_svc, self.current_user.get("username", ""), self
        ).exec_()

    def _show_result(self, ok: bool, message: str):
        if ok:
            QMessageBox.information(self, "Thành công", message)
            self._load()
        else:
            QMessageBox.warning(self, "Không thể thực hiện", message)
