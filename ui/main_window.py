# ui/main_window.py
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QAction, QMessageBox
)

class MainWindow(QMainWindow):
    """Cửa sổ chính — chỉ chứa layout, logic chính ở main.py."""

    def __init__(self, tabs: QTabWidget,
                 auth_svc=None,
                 current_user: dict | None = None):
        super().__init__()
        self.auth_svc = auth_svc
        self.current_user = current_user or {}
        self.logged_out = False

        self.setWindowTitle(
            "Hệ thống Điểm danh Nhận diện Khuôn mặt"
        )
        self.setMinimumSize(1200, 720)
        self.setCentralWidget(tabs)
        self._build_menu()

    def _build_menu(self):
        mb = self.menuBar()

        # Menu Hệ thống
        m_sys = mb.addMenu("Hệ thống")

        act_accounts = QAction("Quản lý tài khoản", self)
        act_accounts.triggered.connect(self._open_account_mgr)
        if self.current_user.get("vaiTro") != "Admin":
            act_accounts.setVisible(False)
        m_sys.addAction(act_accounts)

        m_sys.addSeparator()

        act_quit = QAction("Thoát", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        m_sys.addAction(act_quit)

        # Menu Tài khoản
        m_acc = mb.addMenu("Tài khoản")

        user_text = self.current_user.get("hoTen", "Chưa đăng nhập")
        role_text = self.current_user.get("vaiTro", "")
        act_user = QAction(f"{user_text} ({role_text})", self)
        act_user.setEnabled(False)
        m_acc.addAction(act_user)

        m_acc.addSeparator()

        act_change_pw = QAction("Đổi mật khẩu", self)
        act_change_pw.triggered.connect(self._change_password)
        m_acc.addAction(act_change_pw)

        act_logout = QAction("Đăng xuất", self)
        act_logout.triggered.connect(self._logout)
        m_acc.addAction(act_logout)

        # Menu Trợ giúp
        m_help = mb.addMenu("Trợ giúp")
        act_about = QAction("Về phần mềm", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    def _change_password(self):
        if not self.auth_svc or not self.current_user:
            return

        from ui.change_password_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(
            self.auth_svc,
            self.current_user,
            parent=self
        )
        dlg.exec_()

    def _open_account_mgr(self):
        if self.current_user.get("vaiTro") != "Admin":
            QMessageBox.warning(
                self, "Không có quyền", "Chỉ Admin mới được quản lý tài khoản."
            )
            return
        from ui.account_manager_dialog import AccountManagerDialog

        AccountManagerDialog(self.auth_svc, self.current_user, parent=self).exec_()

    def _logout(self):
        reply = QMessageBox.question(
            self,
            "Đăng xuất",
            "Bạn có chắc muốn đăng xuất khỏi hệ thống?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.auth_svc and self.current_user:
                self.auth_svc.logout(self.current_user.get("username", ""))
            self.logged_out = True
            self.close()

    def _show_about(self):
        QMessageBox.information(
            self,
            "Về phần mềm",
            "Hệ thống Điểm danh Nhận diện Khuôn mặt\n"
            "Phiên bản: 1.0\n\n"
            "Công nghệ sử dụng:\n"
            "  • Python 3.10.11\n"
            "  • face_recognition (HOG + deep metric learning)\n"
            "  • MediaPipe FaceMesh Anti-spoofing\n"
            "  • OpenCV 4.x\n"
            "  • PyQt5\n"
            "  • SQLite\n\n"
            "Đồ án tốt nghiệp — Khoa Công nghệ Thông tin"
        )
