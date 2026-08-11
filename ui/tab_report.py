from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class _StatCard(QFrame):
    """Thẻ thống kê nhỏ ở đầu trang."""

    def __init__(self, title: str, accent: str = "#185FA5"):
        super().__init__()

        self.setStyleSheet(
            "QFrame{background:white;border:1px solid #DDE1EA;border-radius:8px;}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_value = QLabel("—")
        self.lbl_value.setStyleSheet(
            f"font-size:22px;font-weight:700;color:{accent};border:none;"
        )

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(
            "color:#666;font-size:12px;border:none;"
        )

        layout.addWidget(self.lbl_value)
        layout.addWidget(lbl_title)

    def set_value(self, text: str):
        self.lbl_value.setText(text)


class TabReport(QWidget):
    def __init__(self, att_svc, class_access_svc, session_svc):
        super().__init__()

        self.att_svc = att_svc
        self.class_access_svc = class_access_svc
        self.session_svc = session_svc

        self._data: list[dict] = []
        self._threshold = 75
        self._has_report = False

        self._setup_ui()
        self._load_filters()

        # Giao diện ban đầu luôn trống.
        self._clear_report("Chọn lớp và môn học để xem thống kê.")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        filter_group = QGroupBox("Bộ lọc chuyên cần")
        filter_row = QHBoxLayout(filter_group)

        self.cmb_lop = QComboBox()
        self.cmb_lop.setMinimumHeight(30)

        self.cmb_mon = QComboBox()
        self.cmb_mon.setMinimumHeight(30)
        self.cmb_mon.setEnabled(False)

        self.cmb_scope = QComboBox()
        self.cmb_scope.setMinimumHeight(30)
        self.cmb_scope.addItem(
            "Toàn bộ học phần",
            "course",
        )
        self.cmb_scope.addItem(
            "Theo khoảng ngày",
            "period",
        )

        self.dte_from = QDateEdit(QDate.currentDate().addMonths(-3))
        self.dte_from.setCalendarPopup(True)
        self.dte_from.setDisplayFormat("dd/MM/yyyy")
        self.dte_from.setMinimumHeight(30)

        self.dte_to = QDateEdit(QDate.currentDate())
        self.dte_to.setCalendarPopup(True)
        self.dte_to.setDisplayFormat("dd/MM/yyyy")
        self.dte_to.setMinimumHeight(30)

        self.btn_search = QPushButton("Xem báo cáo")
        self.btn_search.setMinimumHeight(30)
        self.btn_search.setStyleSheet(
            "background:#185FA5;color:white;border-radius:5px;padding:0 12px;"
        )
        self.btn_search.clicked.connect(self._search)
        self.btn_search.setEnabled(False)

        filter_row.addWidget(QLabel("Lớp:"))
        filter_row.addWidget(self.cmb_lop, 1)
        filter_row.addWidget(QLabel("Môn:"))
        filter_row.addWidget(self.cmb_mon, 1)
        filter_row.addWidget(QLabel("Phạm vi:"))
        filter_row.addWidget(self.cmb_scope, 1)
        filter_row.addWidget(QLabel("Từ:"))
        filter_row.addWidget(self.dte_from)
        filter_row.addWidget(QLabel("Đến:"))
        filter_row.addWidget(self.dte_to)
        filter_row.addWidget(self.btn_search)
        layout.addWidget(filter_group)

        cards = QHBoxLayout()

        self.card_total = _StatCard("Tổng sinh viên", "#185FA5")
        self.card_avg = _StatCard("Tỷ lệ chuyên cần TB", "#1D9E75")
        self.card_warn = _StatCard(
            "SV cần chú ý (cấm thi)",
            "#C0392B",
        )

        for card in (
            self.card_total,
            self.card_avg,
            self.card_warn,
        ):
            cards.addWidget(card, 1)

        layout.addLayout(cards)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "MSSV",
            "Họ tên",
            "Số buổi",
            "Có mặt",
            "Vắng",
            "Tỷ lệ (%)",
            "Điều kiện dự thi",
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)

        for column in (0, 2, 3, 4, 5, 6):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeToContents,
            )

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        footer = QHBoxLayout()

        self.lbl_count = QLabel("Kết quả: 0 sinh viên")
        self.lbl_count.setStyleSheet("color:gray;font-size:12px;")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.btn_export = QPushButton("Xuất Excel")
        self.btn_export.setMinimumHeight(32)
        self.btn_export.setStyleSheet(
            "background:#3B6D11;color:white;border-radius:5px;padding:0 14px;"
        )
        self.btn_export.clicked.connect(self._export)
        self.btn_export.setEnabled(False)
        footer.addWidget(self.btn_export)

        layout.addLayout(footer)

        self.cmb_lop.currentIndexChanged.connect(self._on_class_changed)
        self.cmb_mon.currentIndexChanged.connect(self._update_search_state)
        self.cmb_scope.currentIndexChanged.connect(self._sync_scope)
        self._sync_scope()

    # ── NẠP BỘ LỌC ────────────────────────────────────────────────────────
    def _load_filters(self):
        selected_lop = self.cmb_lop.currentData()
        selected_mon = self.cmb_mon.currentData()

        self.cmb_lop.blockSignals(True)
        self.cmb_lop.clear()

        self.cmb_lop.addItem("-Chọn lớp-", None)

        for classroom in self.class_access_svc.get_visible_classes():
            self.cmb_lop.addItem(
                classroom["tenLop"],
                classroom["maLop"],
            )

        class_index = self.cmb_lop.findData(selected_lop)
        self.cmb_lop.setCurrentIndex(
            class_index if class_index >= 0 else 0
        )
        self.cmb_lop.blockSignals(False)

        self._load_subjects_for_class(
            self.cmb_lop.currentData(),
            selected_mon,
        )
        self._update_search_state()

    def _load_subjects_for_class(
        self,
        ma_lop: str | None,
        selected_mon: str | None = None,
    ):
        """
        Chỉ nạp các môn đã có ca học thuộc lớp được chọn.
        Không hiển thị toàn bộ môn học của hệ thống.
        """

        self.cmb_mon.blockSignals(True)
        self.cmb_mon.clear()
        self.cmb_mon.addItem("-Chọn môn-", None)

        if ma_lop:
            subjects = self.session_svc.get_subjects_for_class(ma_lop)

            for subject in subjects:
                self.cmb_mon.addItem(
                    subject["tenMon"],
                    subject["maMon"],
                )

        subject_index = self.cmb_mon.findData(selected_mon)
        self.cmb_mon.setCurrentIndex(
            subject_index if subject_index >= 0 else 0
        )

        # Chỉ bật khi lớp có ít nhất một môn tương ứng.
        self.cmb_mon.setEnabled(self.cmb_mon.count() > 1)
        self.cmb_mon.blockSignals(False)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_filters()

    def _on_class_changed(self):
        ma_lop = self.cmb_lop.currentData()

        self._load_subjects_for_class(ma_lop)

        if ma_lop:
            message = "Chọn môn học để xem thống kê."
        else:
            message = "Chọn lớp và môn học để xem thống kê."

        self._clear_report(message)
        self._update_search_state()

    def _update_search_state(self):
        ready = bool(
            self.cmb_lop.currentData()
            and self.cmb_mon.currentData()
        )
        self.btn_search.setEnabled(ready)

    def _sync_scope(self, _index=None):
        is_period = (
            self.cmb_scope.currentData() == "period"
        )

        self.dte_from.setEnabled(is_period)
        self.dte_to.setEnabled(is_period)
        if self._has_report:
            self._clear_report(
                "Phạm vi đã thay đổi. "
                "Nhấn Xem báo cáo để cập nhật."
            )

    # ── HIỂN THỊ BÁO CÁO ──────────────────────────────────────────────────
    def _clear_report(self, message: str):
        self._has_report = False
        self._data = []

        self.table.setRowCount(0)

        self.card_total.set_value("—")
        self.card_avg.set_value("—")
        self.card_warn.set_value("—")

        self.lbl_count.setText(message)
        self.btn_export.setEnabled(False)

    def _search(self):
        ma_lop = self.cmb_lop.currentData()
        ma_mon = self.cmb_mon.currentData()

        if not ma_lop or not ma_mon:
            self._clear_report(
                "Vui lòng chọn đầy đủ lớp và môn học."
            )
            return

        if not self.class_access_svc.can_access_class(ma_lop):
            self._clear_report(
                "Bạn không có quyền xem báo cáo lớp này."
            )
            return

            QMessageBox.warning(
                self,
                "Không có quyền",
                "Bạn không có quyền xem báo cáo lớp này.",
            )
            return

        scope = (
            self.cmb_scope.currentData()
            or "course"
        )

        if scope == "period":
            date_from = self.dte_from.date().toString(
                "yyyy-MM-dd"
            )
            date_to = self.dte_to.date().toString(
                "yyyy-MM-dd"
            )

            if date_from > date_to:
                self._clear_report(
                    "Khoảng ngày lọc không hợp lệ."
                )
                QMessageBox.warning(
                    self,
                    "Chú ý",
                    (
                        "Ngày bắt đầu phải không sau "
                        "ngày kết thúc."
                    ),
                )
                return
        else:
            date_from = ""
            date_to = ""
        report = self.att_svc.get_attendance_report(
            maLop=ma_lop,
            maMon=ma_mon,
            ngay_from=date_from,
            ngay_to=date_to,
            scope=scope,
        )

        self._fill(report)
        self._has_report = True
        self.lbl_count.setText(
            f"Kết quả: {len(self._data)} sinh viên"
        )
        self.btn_export.setEnabled(bool(self._data))

    def _fill(self, report: dict):
        students = report.get("students", [])
        self._data = students
        self._threshold = report.get("threshold", 75)
        scope = report.get("scope", "course")

        total = len(students)
        average = (
            round(
                sum(student["ty_le"] for student in students) / total,
                1,
            )
            if total
            else 0.0
        )
        warning_count = sum(
            1
            for student in students
            if student.get("trang_thai_thi") == "CẤM THI"
        )

        self.card_total.set_value(str(total))
        self.card_avg.set_value(f"{average}%")
        if scope == "period":
            self.card_warn.set_value("—")
        else:
            self.card_warn.set_value(str(warning_count))

        self.table.setRowCount(0)

        green_background = QColor("#E8F6EF")
        red_background = QColor("#FCEBEB")
        normal_background = QColor("#FFFFFF")

        for student in students:
            row = self.table.rowCount()
            self.table.insertRow(row)

            status = student.get("trang_thai_thi", "")

            values = [
                student["mssv"],
                student["hoTen"],
                str(student["tong_buoi"]),
                str(student["so_co_mat"]),
                str(student["so_vang"]),
                str(student["ty_le"]),
                status,
            ]

            if status == "CẤM THI":
                background = red_background
            elif status == "ĐỦ ĐIỀU KIỆN":
                background = green_background
            else:
                background = normal_background

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(background)
                self.table.setItem(row, column, item)

    def _export(self):
        if not self._has_report or not self._data:
            QMessageBox.warning(
                self,
                "Chú ý",
                "Chưa có báo cáo để xuất.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu báo cáo chuyên cần",
            "bao_cao_chuyen_can.xlsx",
            "Excel (*.xlsx)",
        )
        if not path:
            return

        ok = self.att_svc.export_excel_report(
            self._data,
            path,
            self._threshold,
        )

        if ok:
            QMessageBox.information(
                self,
                "Thành công",
                f"Đã xuất {len(self._data)} sinh viên ra:\n{path}",
            )
        else:
            QMessageBox.critical(
                self,
                "Lỗi",
                "Xuất file thất bại.",
            )