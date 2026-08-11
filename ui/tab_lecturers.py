"""Tab quản lý Giảng viên (Admin)."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class LecturerDialog(QDialog):
    """Dialog thêm hoặc sửa hồ sơ giảng viên."""

    def __init__(
        self,
        auth_svc,
        actor_username: str,
        existing: dict = None,
        parent=None,
    ):
        super().__init__(parent)
        self.auth_svc = auth_svc
        self.actor_username = actor_username
        self.existing = existing

        self.setWindowTitle(
            "Sửa thông tin giảng viên" if existing else "Thêm giảng viên mới"
        )
        self.setMinimumWidth(440)

        self._setup_ui()

        if existing:
            self._populate(existing)

    def _setup_ui(self):
        form = QFormLayout(self)
        form.setSpacing(10)

        self.txt_magv = QLineEdit()
        self.txt_magv.setPlaceholderText("VD: GV001")

        self.txt_username = QLineEdit()
        self.txt_hoten = QLineEdit()
        self.txt_hoten.setPlaceholderText("Chỉ gồm chữ cái và khoảng trắng")

        self.cmb_gioitinh = QComboBox()
        self.cmb_gioitinh.addItems(["Nam", "Nữ"])

        self.txt_ngaysinh = QLineEdit()
        self.txt_ngaysinh.setPlaceholderText("DD/MM/YYYY")

        self.txt_email = QLineEdit()
        self.txt_sdt = QLineEdit()
        self.txt_bomon = QLineEdit()

        self.txt_password = QLineEdit()
        self.txt_confirm = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_confirm.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText(
            "Ít nhất 8 ký tự, gồm chữ và số"
        )

        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet("color:#D85A30; font-size:12px;")
        self.lbl_err.setWordWrap(True)

        form.addRow("Mã giảng viên *", self.txt_magv)
        form.addRow("Tài khoản *", self.txt_username)
        form.addRow("Họ và tên *", self.txt_hoten)
        form.addRow("Giới tính *", self.cmb_gioitinh)
        form.addRow("Ngày sinh *", self.txt_ngaysinh)
        form.addRow("Email *", self.txt_email)
        form.addRow("Số điện thoại *", self.txt_sdt)
        form.addRow("Bộ môn *", self.txt_bomon)

        if not self.existing:
            form.addRow("Mật khẩu tạm *", self.txt_password)
            form.addRow("Xác nhận *", self.txt_confirm)

        form.addRow(self.lbl_err)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Lưu")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if self.existing:
            # Username là tài khoản đăng nhập; không đổi tại màn hình hồ sơ.
            self.txt_username.setReadOnly(True)
            self.txt_username.setStyleSheet("background:#F0F0F0;")

    def _populate(self, lecturer: dict):
        self.txt_magv.setText(lecturer.get("maGV", ""))
        self.txt_username.setText(lecturer.get("username", ""))
        self.txt_hoten.setText(lecturer.get("hoTen", ""))
        self.txt_ngaysinh.setText(lecturer.get("ngaySinh", ""))
        self.txt_email.setText(lecturer.get("email", ""))
        self.txt_sdt.setText(lecturer.get("soDienThoai", ""))
        self.txt_bomon.setText(lecturer.get("boMon", ""))

        gender_index = self.cmb_gioitinh.findText(
            lecturer.get("gioiTinh", "Nam")
        )
        if gender_index >= 0:
            self.cmb_gioitinh.setCurrentIndex(gender_index)

    def _submit(self):
        self.lbl_err.clear()

        ma_gv = self.txt_magv.text().strip().upper()
        username = self.txt_username.text().strip()
        ho_ten = self.txt_hoten.text().strip()
        email = self.txt_email.text().strip()
        phone = self.txt_sdt.text().strip()
        gender = self.cmb_gioitinh.currentText()
        birth_date = self.txt_ngaysinh.text().strip()
        department = self.txt_bomon.text().strip()

        if self.existing:
            ok, message = self.auth_svc.update_lecturer(
                self.actor_username,
                username,
                ho_ten,
                email,
                phone,
                gender,
                birth_date,
                department,
                ma_gv,
            )
        else:
            ok, message = self.auth_svc.create_account(
                self.actor_username,
                username,
                self.txt_password.text(),
                self.txt_confirm.text(),
                ho_ten,
                email,
                phone,
                "GiangVien",
                ma_gv,
                gender,
                birth_date,
                department,
            )

        if not ok:
            self.lbl_err.setText(message)
            return

        QMessageBox.information(self, "Thành công", message)
        self.accept()


class TabLecturers(QWidget):
    def __init__(self, auth_svc, current_user: dict):
        super().__init__()
        self.auth_svc = auth_svc
        self.current_user = current_user or {}
        self._data: list[dict] = []

        self._setup_ui()
        self.load_data()

    @property
    def _actor(self) -> str:
        return self.current_user.get("username", "")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        search_row = QHBoxLayout()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "Tìm theo mã GV, họ tên, email hoặc tài khoản"
        )
        self.txt_search.setMinimumHeight(32)
        self.txt_search.textChanged.connect(self._apply_filter)

        btn_refresh = QPushButton("Làm mới")
        btn_refresh.setMinimumHeight(32)
        btn_refresh.clicked.connect(self._refresh)

        search_row.addWidget(QLabel("Tìm:"))
        search_row.addWidget(self.txt_search, 4)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Mã GV",
            "Tài khoản",
            "Họ và tên",
            "Giới tính",
            "Ngày sinh",
            "Email",
            "Số ĐT",
            "Bộ môn",
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.Stretch,
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._open_edit)
        layout.addWidget(self.table)

        self.lbl_status = QLabel("Tổng: 0 giảng viên")
        self.lbl_status.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        button_row = QHBoxLayout()
        self._make_btn(button_row, "+ Thêm mới", "#1D9E75", self._open_add)
        self._make_btn(button_row, "Sửa", "#BA7517", self._open_edit)
        self._make_btn(
            button_row,
            "Cấp mật khẩu tạm",
            "#534AB7",
            self._reset_password,
        )
        self._make_btn(
            button_row,
            "Bật / tắt",
            "#185FA5",
            self._toggle_active,
        )
        self._make_btn(button_row, "Xóa", "#D85A30", self._delete)
        button_row.addStretch()
        layout.addLayout(button_row)

    def _make_btn(self, layout, text, color, handler):
        button = QPushButton(text)
        button.setMinimumHeight(34)
        button.setStyleSheet(
            f"QPushButton {{ background:{color}; color:white; "
            f"border-radius:6px; padding:0 14px; font-weight:500; }}"
            f"QPushButton:hover {{ opacity:0.85; }}"
        )
        button.clicked.connect(handler)
        layout.addWidget(button)
        return button

    def load_data(self):
        self._data = self.auth_svc.get_lecturers(self._actor)
        self._render(self._data)

    def _render(self, rows: list[dict]):
        self.table.setRowCount(0)

        for lecturer in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            inactive = lecturer.get("isActive") != 1
            values = [
                lecturer.get("maGV", ""),
                lecturer.get("username", ""),
                lecturer.get("hoTen", ""),
                lecturer.get("gioiTinh", ""),
                lecturer.get("ngaySinh", ""),
                lecturer.get("email", ""),
                lecturer.get("soDienThoai", ""),
                lecturer.get("boMon", ""),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                if inactive:
                    item.setToolTip("Tài khoản đang bị vô hiệu hóa")
                    item.setForeground(Qt.gray)

                self.table.setItem(row, col, item)

        self.lbl_status.setText(f"Tổng: {len(rows)} giảng viên")

    def _apply_filter(self):
        keyword = self.txt_search.text().strip().lower()

        if not keyword:
            self._render(self._data)
            return

        filtered = [
            lecturer
            for lecturer in self._data
            if keyword in str(lecturer.get("maGV", "")).lower()
            or keyword in str(lecturer.get("hoTen", "")).lower()
            or keyword in str(lecturer.get("email", "")).lower()
            or keyword in str(lecturer.get("username", "")).lower()
        ]
        self._render(filtered)

    def _refresh(self):
        self.txt_search.clear()
        self.load_data()

    def _selected_username(self) -> str | None:
        row = self.table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Chú ý",
                "Vui lòng chọn một giảng viên.",
            )
            return None

        return self.table.item(row, 1).text()

    def _open_add(self):
        dialog = LecturerDialog(
            self.auth_svc,
            self._actor,
            parent=self,
        )
        if dialog.exec_():
            self._refresh()

    def _open_edit(self):
        username = self._selected_username()
        if not username:
            return

        lecturer = next(
            (
                item
                for item in self._data
                if item.get("username") == username
            ),
            None,
        )
        if not lecturer:
            QMessageBox.warning(
                self,
                "Lỗi",
                "Không tìm thấy giảng viên cần sửa.",
            )
            return

        dialog = LecturerDialog(
            self.auth_svc,
            self._actor,
            existing=lecturer,
            parent=self,
        )
        if dialog.exec_():
            self._refresh()

    def _reset_password(self):
        username = self._selected_username()
        if not username:
            return

        from ui.account_manager_dialog import TemporaryPasswordDialog

        dialog = TemporaryPasswordDialog(username, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        ok, message = self.auth_svc.admin_reset_password(
            self._actor,
            username,
            dialog.txt_password.text(),
            dialog.txt_confirm.text(),
        )

        if ok:
            QMessageBox.information(self, "Kết quả", message)
            self._refresh()
        else:
            QMessageBox.warning(self, "Không thể thực hiện", message)

    def _toggle_active(self):
        username = self._selected_username()
        if not username:
            return

        lecturer = next(
            (
                item
                for item in self._data
                if item.get("username") == username
            ),
            None,
        )
        if not lecturer:
            return

        activate = lecturer.get("isActive") != 1
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
            self._actor,
            username,
            activate,
        )

        if ok:
            QMessageBox.information(self, "Kết quả", message)
            self._refresh()
        else:
            QMessageBox.warning(self, "Không thể thực hiện", message)

    def _delete(self):
        username = self._selected_username()
        if not username:
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận xóa giảng viên",
            (
                f"Bạn có chắc muốn xóa giảng viên '{username}'?\n\n"
                "Các lớp do giảng viên này chủ nhiệm sẽ chuyển sang "
                "'Chưa phân công'.\n"
                "Sinh viên, ca học và lịch sử điểm danh không bị xóa."
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok, message = self.auth_svc.delete_lecturer(
            self._actor,
            username,
        )

        if ok:
            QMessageBox.information(self, "Thành công", message)
            self._refresh()
        else:
            QMessageBox.warning(self, "Không thể xóa", message)