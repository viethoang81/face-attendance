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


class ClassDialog(QDialog):
    def __init__(
        self,
        cls_svc,
        lecturer_options: list[dict],
        existing: dict = None,
        parent=None,
    ):
        super().__init__(parent)
        self.cls_svc = cls_svc
        self.existing = existing
        self._original_ma_lop = (existing or {}).get("maLop", "")

        self.setWindowTitle(
            "Sửa lớp học" if existing else "Thêm lớp học mới"
        )
        self.setMinimumWidth(430)

        self._setup_ui(lecturer_options)

        if existing:
            self._populate(existing)

    def _setup_ui(self, lecturer_options: list[dict]):
        form = QFormLayout(self)
        form.setSpacing(10)

        self.txt_ma = QLineEdit()
        self.txt_ma.setPlaceholderText("VD: 21CNTT1")

        self.txt_ten = QLineEdit()
        self.txt_ten.setPlaceholderText("VD: CNTT21A")

        self.txt_khoahoc = QLineEdit()
        self.txt_khoahoc.setPlaceholderText("VD: 2021")

        self.txt_khoa = QLineEdit()
        self.txt_khoa.setPlaceholderText("VD: Công nghệ Thông tin")

        self.cmb_gvcn = QComboBox()
        self.cmb_gvcn.addItem("— Chưa phân công —", "")

        for lecturer in lecturer_options:
            display_name = lecturer.get("hoTen") or lecturer.get(
                "username",
                "",
            )
            username = lecturer.get("username", "")
            self.cmb_gvcn.addItem(
                f"{display_name} ({username})",
                username,
            )

        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet("color:#D85A30; font-size:12px;")
        self.lbl_err.setWordWrap(True)

        form.addRow("Mã lớp *", self.txt_ma)
        form.addRow("Tên lớp *", self.txt_ten)
        form.addRow("Khóa *", self.txt_khoahoc)
        form.addRow("Khoa *", self.txt_khoa)
        form.addRow("GV chủ nhiệm", self.cmb_gvcn)
        form.addRow(self.lbl_err)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Lưu")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _populate(self, classroom: dict):
        self.txt_ma.setText(classroom.get("maLop", ""))
        self.txt_ten.setText(classroom.get("tenLop", ""))
        self.txt_khoahoc.setText(classroom.get("khoaHoc", ""))
        self.txt_khoa.setText(classroom.get("khoa", ""))

        lecturer_index = self.cmb_gvcn.findData(
            classroom.get("gvChuNhiem", "")
        )
        if lecturer_index >= 0:
            self.cmb_gvcn.setCurrentIndex(lecturer_index)

    def _submit(self):
        ma_lop = self.txt_ma.text().strip()
        ten_lop = self.txt_ten.text().strip()
        khoa_hoc = self.txt_khoahoc.text().strip()
        khoa = self.txt_khoa.text().strip()
        gv_chu_nhiem = self.cmb_gvcn.currentData() or ""

        if self.existing:
            ok, message = self.cls_svc.update(
                self._original_ma_lop,
                ma_lop,
                ten_lop,
                khoa_hoc,
                khoa,
                gv_chu_nhiem,
            )
        else:
            ok, message = self.cls_svc.add(
                ma_lop,
                ten_lop,
                khoa_hoc,
                khoa,
                gv_chu_nhiem,
            )

        if ok:
            self.accept()
        else:
            self.lbl_err.setText(message)


class TabClasses(QWidget):
    def __init__(self, cls_svc, auth_svc, current_user: dict):
        super().__init__()
        self.cls_svc = cls_svc
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
            "Tìm theo mã lớp, tên lớp hoặc khoa..."
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Mã lớp",
            "Tên lớp",
            "Khóa",
            "Khoa",
            "GV chủ nhiệm",
            "Sĩ số",
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4,
            QHeaderView.Stretch,
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._open_edit)
        layout.addWidget(self.table)

        self.lbl_status = QLabel("Tổng: 0 lớp")
        self.lbl_status.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self._make_btn(btn_row, "+ Thêm mới", "#1D9E75", self._open_add)
        self._make_btn(btn_row, "Sửa", "#BA7517", self._open_edit)
        self._make_btn(btn_row, "Xóa", "#D85A30", self._delete)
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

    def load_data(self):
        self._data = self.cls_svc.get_all()
        self._render(self._data)

    def _render(self, rows: list[dict]):
        self.table.setRowCount(0)

        for classroom in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                classroom.get("maLop", ""),
                classroom.get("tenLop", ""),
                classroom.get("khoaHoc", ""),
                classroom.get("khoa", ""),
                classroom.get("gvChuNhiemTen", "") or "—",
                classroom.get("siSo", 0),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

        self.lbl_status.setText(f"Tổng: {len(rows)} lớp")

    def _apply_filter(self):
        keyword = self.txt_search.text().strip().lower()

        if not keyword:
            self._render(self._data)
            return

        filtered = [
            classroom
            for classroom in self._data
            if keyword in str(classroom.get("maLop", "")).lower()
            or keyword in str(classroom.get("tenLop", "")).lower()
            or keyword in str(classroom.get("khoa", "")).lower()
        ]
        self._render(filtered)

    def _refresh(self):
        self.txt_search.clear()
        self.load_data()

    def _selected_malop(self) -> str | None:
        row = self.table.currentRow()

        if row < 0:
            QMessageBox.warning(
                self,
                "Chú ý",
                "Vui lòng chọn một lớp.",
            )
            return None

        return self.table.item(row, 0).text()

    def _lecturer_options(self) -> list[dict]:
        return self.auth_svc.get_lecturer_options(self._actor)

    def _open_add(self):
        dialog = ClassDialog(
            self.cls_svc,
            self._lecturer_options(),
            parent=self,
        )
        if dialog.exec_():
            self._refresh()

    def _open_edit(self):
        ma_lop = self._selected_malop()
        if not ma_lop:
            return

        classroom = self.cls_svc.get_one(ma_lop)
        if not classroom:
            QMessageBox.warning(
                self,
                "Lỗi",
                "Không tìm thấy lớp học cần sửa.",
            )
            return

        dialog = ClassDialog(
            self.cls_svc,
            self._lecturer_options(),
            existing=classroom,
            parent=self,
        )
        if dialog.exec_():
            self._refresh()

    def _delete(self):
        ma_lop = self._selected_malop()
        if not ma_lop:
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa lớp '{ma_lop}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok, message = self.cls_svc.delete(ma_lop)

        if ok:
            QMessageBox.information(self, "Kết quả", message)
            self._refresh()
        else:
            QMessageBox.warning(self, "Không thể xóa", message)