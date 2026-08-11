from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QLineEdit, QComboBox, QPushButton,
    QLabel, QMessageBox, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor


STUDENT_STATUS_LABELS = {
    "DANG_HOC": "Đang học",
    "BAO_LUU": "Bảo lưu",
    "DINH_CHI": "Đình chỉ",
    "THOI_HOC": "Đã thôi học",
    "TOT_NGHIEP": "Tốt nghiệp",
}


class TabMyClassStudents(QWidget):
    def __init__(
        self,
        student_service,
        face_engine,
    ):
        super().__init__()
        self.student_service = student_service
        self.face_engine = face_engine

        self._setup_ui()
        self._load_class_filter()
        self.load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        info = QLabel("Chỉ hiển thị sinh viên thuộc lớp bạn chủ nhiệm.")
        info.setStyleSheet("color:#185FA5; font-size:12px;")
        layout.addWidget(info)

        search_row = QHBoxLayout()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Tìm theo MSSV hoặc họ tên...")
        self.txt_search.setMinimumHeight(32)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._do_search)
        self.txt_search.textChanged.connect(
            lambda: self._timer.start(300)
        )

        self.cmb_lop = QComboBox()
        self.cmb_lop.setMinimumHeight(32)
        self.cmb_lop.currentIndexChanged.connect(self._do_search)

        self.cmb_status = QComboBox()
        self.cmb_status.setMinimumHeight(32)
        self.cmb_status.addItem("Tất cả trạng thái", "")
        self.cmb_status.addItem("Đang học", "DANG_HOC")
        self.cmb_status.addItem("Thôi học", "THOI_HOC")
        self.cmb_status.currentIndexChanged.connect(self._do_search)

        btn_refresh = QPushButton("Làm mới")
        btn_refresh.setMinimumHeight(32)
        btn_refresh.clicked.connect(self._refresh)

        search_row.addWidget(QLabel("Tìm:"))
        search_row.addWidget(self.txt_search, 3)
        search_row.addWidget(QLabel("Lớp:"))
        search_row.addWidget(self.cmb_lop, 1)
        search_row.addWidget(QLabel("Trạng thái:"))
        search_row.addWidget(self.cmb_status, 1)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "MSSV", "Họ và tên", "Lớp",
            "Ngày sinh", "Giới tính", "Email", "Số ĐT", "Trạng thái",
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.Stretch,
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._open_edit)
        layout.addWidget(self.table)

        self.lbl_status = QLabel("Tổng: 0 sinh viên")
        self.lbl_status.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self._make_btn(btn_row, "+ Thêm mới", "#1D9E75", self._open_add)
        self.btn_edit = self._make_btn(
            btn_row, "Sửa / Xem", "#BA7517", self._open_edit
        )
        self.btn_remove = self._make_btn(
            btn_row,
            "Xóa / Cho thôi học",
            "#D85A30",
            self._delete,
        )
        self.btn_face = self._make_btn(
            btn_row,
            "Đăng ký khuôn mặt",
            "#534AB7",
            self._register_face,
        )
        btn_row.addStretch()
        layout.addLayout(btn_row)

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

    def _homeroom_classes(self) -> list[dict]:
        return self.student_service.get_allowed_classes()

    def _load_class_filter(self):
        self.cmb_lop.blockSignals(True)
        self.cmb_lop.clear()
        self.cmb_lop.addItem("Tất cả lớp chủ nhiệm", "")

        for classroom in self._homeroom_classes():
            self.cmb_lop.addItem(
                classroom["tenLop"],
                classroom["maLop"],
            )

        self.cmb_lop.blockSignals(False)

    def load_data(self, rows=None):
        if rows is None:
            rows = self.student_service.get_all()

        registered_set = self.face_engine.get_registered_mssv_set()
        self.table.setRowCount(0)

        for student in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            has_face = student.get("mssv", "").strip() in registered_set
            status = student.get("trangThai", "")
            if status == "THOI_HOC":
                background = QColor("#FCEBEB")
                tooltip = "Đã thôi học - chỉ được xem thông tin"
            else:
                background = (
                    QColor("#E1F5EE") if has_face else QColor("#FFFFFF")
                )
                tooltip = (
                    "Đã đăng ký khuôn mặt"
                    if has_face
                    else "Chưa đăng ký khuôn mặt"
                )

            for col, key in enumerate([
                "mssv",
                "hoTen",
                "tenLop",
                "ngaySinh",
                "gioiTinh",
                "email",
                "soDienThoai",
                "trangThai",
            ]):
                value = student.get(key, "")
                if key == "trangThai":
                    value = STUDENT_STATUS_LABELS.get(value, value)
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(background)
                item.setToolTip(tooltip)
                self.table.setItem(row, col, item)

        self.lbl_status.setText(f"Tổng: {len(rows)} sinh viên")

    def _do_search(self):
        keyword = self.txt_search.text().strip()
        ma_lop = self.cmb_lop.currentData()
        status = self.cmb_status.currentData() or ""

        self.load_data(
            self.student_service.search(
                keyword,
                ma_lop or "",
                status,
            )
        )

    def _refresh(self):
        self.txt_search.clear()
        self._load_class_filter()
        self.cmb_lop.setCurrentIndex(0)
        self.cmb_status.setCurrentIndex(0)
        self.load_data()

    def _selected_mssv(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self,
                "Chú ý",
                "Vui lòng chọn một sinh viên.",
            )
            return None

        return self.table.item(row, 0).text()

    def _guard(self, mssv: str) -> bool:
        """Chặn thao tác lên sinh viên không thuộc lớp mình chủ nhiệm."""

        if self.student_service.can_manage_student(mssv):
            return True

        QMessageBox.warning(
            self,
            "Không có quyền",
            "Sinh viên này không thuộc lớp bạn chủ nhiệm.",
        )
        return False

    def _open_add(self):
        classes = self._homeroom_classes()
        if not classes:
            QMessageBox.information(
                self,
                "Chưa có lớp chủ nhiệm",
                "Bạn chưa được phân công chủ nhiệm lớp nào.",
            )
            return

        from ui.dialogs import StudentDialog

        dlg = StudentDialog(
            self.student_service,
            None,
            classes=classes,
            parent=self,
        )
        if dlg.exec_():
            self._refresh()

    def _open_edit(self):
        mssv = self._selected_mssv()
        if not mssv or not self._guard(mssv):
            return

        student = self.student_service.get_by_mssv(mssv)
        if not student:
            return

        from ui.dialogs import StudentDialog

        dlg = StudentDialog(
            self.student_service,
            None,
            existing=student,
            classes=self._homeroom_classes(),
            read_only=student.get("trangThai") != "DANG_HOC",
            parent=self,
        )
        if dlg.exec_() and student.get("trangThai") == "DANG_HOC":
            # MSSV có thể đã thay đổi; đồng bộ cache nhận diện khuôn mặt.
            self.face_engine.load_encodings()
            self._refresh()

    def _delete(self):
        mssv = self._selected_mssv()
        if not mssv or not self._guard(mssv):
            return

        can_purge, reason = self.student_service.can_hard_delete(mssv)
        if can_purge:
            reply = QMessageBox.warning(
                self,
                "Xóa vĩnh viễn sinh viên",
                "Sinh viên chưa phát sinh dữ liệu học tập. Hồ sơ và mẫu "
                "khuôn mặt sẽ bị xóa vĩnh viễn và không thể khôi phục.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            ok, message = self.student_service.purge_student(mssv)
        else:
            if "quyền" in reason.lower() or "không tìm thấy" in reason.lower():
                QMessageBox.warning(self, "Không thể thao tác", reason)
                return
            student = self.student_service.get_by_mssv(mssv)
            if student and student.get("trangThai") == "THOI_HOC":
                QMessageBox.information(
                    self,
                    "Sinh viên đã thôi học",
                    "Sinh viên đã ở trạng thái thôi học và vẫn có dữ liệu "
                    "học vụ nên không thể xóa vĩnh viễn.",
                )
                return
            from ui.dialogs import StudentWithdrawalDialog

            dialog = StudentWithdrawalDialog(mssv, reason, self)
            if not dialog.exec_():
                return
            ok, message = self.student_service.withdraw_student(
                mssv,
                dialog.effective_date(),
            )
        if ok:
            self.face_engine.load_encodings()

        QMessageBox.information(self, "Kết quả", message)

        if ok:
            self._refresh()

    def _register_face(self):
        mssv = self._selected_mssv()
        if not mssv or not self._guard(mssv):
            return

        student = self.student_service.get_by_mssv(mssv)
        if not student:
            return
        if student.get("trangThai") != "DANG_HOC":
            QMessageBox.warning(
                self,
                "Không thể đăng ký khuôn mặt",
                "Sinh viên không ở trạng thái Đang học; chỉ được xem "
                "thông tin.",
            )
            return

        registered_set = self.face_engine.get_registered_mssv_set()
        if mssv in registered_set:
            reply = QMessageBox.question(
                self,
                "Khuôn mặt đã tồn tại",
                f"Sinh viên '{mssv}' đã được đăng ký khuôn mặt trước đó.\n\n"
                "Bạn có muốn đăng ký lại không?\n\n"
                "Mẫu cũ chỉ bị thay thế sau khi bạn chụp thành công "
                "đủ 10 mẫu mới.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        from ui.dialogs import FaceRegisterDialog

        dlg = FaceRegisterDialog(
            mssv,
            self.face_engine,
            parent=self,
        )
        if dlg.exec_():
            self._refresh()
