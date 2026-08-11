# ui/tab_history.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QComboBox, QPushButton, QLabel,
    QDateEdit, QHeaderView, QAbstractItemView, QMessageBox,
    QFileDialog, QGroupBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui  import QColor 

ALL_ALLOWED_CLASSES = "__ALL_ALLOWED__"

class TabHistory(QWidget):
    def __init__(self, att_svc, class_access_svc):
        super().__init__()
        self.att_svc = att_svc
        self.class_access_svc = class_access_svc
        self._setup_ui()
        self._load_class_filter()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Bộ lọc ──
        grp = QGroupBox("Bộ lọc tìm kiếm")
        filter_row = QHBoxLayout(grp)

        self.cmb_lop = QComboBox()
        self.cmb_lop.setMinimumHeight(30)

        self.dte_from = QDateEdit(QDate.currentDate())
        self.dte_from.setCalendarPopup(True)
        self.dte_from.setDisplayFormat("dd/MM/yyyy")
        self.dte_from.setMinimumHeight(30)

        self.dte_to = QDateEdit(QDate.currentDate())
        self.dte_to.setCalendarPopup(True)
        self.dte_to.setDisplayFormat("dd/MM/yyyy")
        self.dte_to.setMinimumHeight(30)

        self.txt_mssv = QComboBox()
        self.txt_mssv.setEditable(True)
        self.txt_mssv.setMinimumHeight(30)
        self.txt_mssv.lineEdit().setPlaceholderText("MSSV (bỏ trống = tất cả)")

        btn_search = QPushButton("Tìm kiếm")
        btn_search.setMinimumHeight(30)
        btn_search.setStyleSheet(
            "background:#185FA5;color:white;border-radius:5px;padding:0 12px;"
        )
        btn_search.clicked.connect(self._search)

        btn_reset = QPushButton("Xóa lọc")
        btn_reset.setMinimumHeight(30)
        btn_reset.clicked.connect(self._reset)

        filter_row.addWidget(QLabel("Lớp:"))
        filter_row.addWidget(self.cmb_lop, 1)
        filter_row.addWidget(QLabel("Từ ngày:"))
        filter_row.addWidget(self.dte_from)
        filter_row.addWidget(QLabel("Đến:"))
        filter_row.addWidget(self.dte_to)
        filter_row.addWidget(QLabel("MSSV:"))
        filter_row.addWidget(self.txt_mssv, 1)
        filter_row.addWidget(btn_search)
        filter_row.addWidget(btn_reset)
        layout.addWidget(grp)

        # ── Bảng kết quả ──
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "MSSV", "Họ tên", "Mã lớp học phần", "Lớp học phần",
            "Môn học", "Ca học", "Ngày học", "Giờ học",
            "Giờ điểm danh", "Trạng thái"
        ])
        header = self.table.horizontalHeader()
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(2, 135)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 115)
        self.table.setColumnWidth(7, 125)
        self.table.setColumnWidth(8, 135)
        self.table.setColumnWidth(9, 115)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # ── Footer ──
        footer = QHBoxLayout()
        self.lbl_count = QLabel("Kết quả: 0 bản ghi")
        self.lbl_count.setStyleSheet("color:gray; font-size:12px;")
        footer.addWidget(self.lbl_count)
        footer.addStretch()

        btn_export = QPushButton("Xuất Excel")
        btn_export.setMinimumHeight(32)
        btn_export.setStyleSheet(
            "background:#3B6D11;color:white;border-radius:5px;padding:0 14px;"
        )
        btn_export.clicked.connect(self._export)
        footer.addWidget(btn_export)
        layout.addLayout(footer)

        # Tải dữ liệu ban đầu
        self._search()

    def _load_class_filter(self):
        current = self.cmb_lop.currentData()
        self.cmb_lop.clear()
        classes = self.class_access_svc.get_visible_classes()
        if self.class_access_svc.is_admin:
            self.cmb_lop.addItem("Tất cả lớp", "")
        else:
            self.cmb_lop.addItem("Tất cả lớp được phân công", ALL_ALLOWED_CLASSES)
        for c in classes:
            self.cmb_lop.addItem(c["tenLop"], c["maLop"])
        if current is not None:
            idx = self.cmb_lop.findData(current)
            if idx >= 0:
                self.cmb_lop.setCurrentIndex(idx)

    def showEvent(self, event):
        """Refresh bộ lọc lớp và tải lại dữ liệu mỗi khi tab hiển thị."""
        super().showEvent(event)
        current = self.cmb_lop.currentData()
        self._load_class_filter()
        if current:
           idx = self.cmb_lop.findData(current)
           if idx >= 0:
               self.cmb_lop.setCurrentIndex(idx)
    # Tải lại dữ liệu lịch sử mới nhất
        self._search()

    def _search(self):
        maLop = self.cmb_lop.currentData() or ""
        mssv = self.txt_mssv.currentText().strip()
        d_from = self.dte_from.date().toString("yyyy-MM-dd")
        d_to = self.dte_to.date().toString("yyyy-MM-dd")
        if maLop == ALL_ALLOWED_CLASSES:
            rows = []
            for code in self.class_access_svc.get_visible_class_codes():
                rows.extend(self.att_svc.get_history(
                    maLop=code,
                    mssv=mssv,
                    ngay_from=d_from,
                    ngay_to=d_to,
                ))
            self._fill_table(rows)
            return

        if maLop and not self.class_access_svc.can_access_class(maLop):
            QMessageBox.warning(
                self,
                "Không có quyền",
                "Bạn không có quyền xem lịch sử lớp này."
            )
            return
        rows = self.att_svc.get_history(
            maLop=maLop,
            mssv=mssv,
            ngay_from=d_from,
            ngay_to=d_to,
        )
        self._fill_table(rows)

    def _reset(self):
        self.cmb_lop.setCurrentIndex(0)
        self.txt_mssv.clearEditText()
        self.dte_from.setDate(QDate.currentDate())
        self.dte_to.setDate(QDate.currentDate())
        self._search()

    def _fill_table(self, rows: list[dict]):
        self.table.setRowCount(0)
        self._data = rows
        STATUS_COLOR = {
            "Co mat":  "#E1F5EE",
            "Vang mat": "#FCEBEB",
            "Tre":     "#FAEEDA",
            
            "PRESENT":   "#E1F5EE",
            "LATE":      "#FAEEDA",
            "EXCUSED":   "#E7F0FA",
            "UNEXCUSED": "#FCEBEB",
            "ABSENT":    "#FCEBEB",
        }
        STATUS_LABEL = {
            "Co mat": "Có mặt",
            "Vang mat": "Vắng mặt",
            "Tre": "Trễ",
            "PRESENT":   "Có mặt",
            "LATE":      "Muộn",
            "EXCUSED":   "Vắng có phép",
            "UNEXCUSED": "Vắng không phép",
            "ABSENT":    "Vắng",
        }
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            status = r.get("trangThai", "")
            ca_hoc_id = r.get("caHocId")
            mssv = str(r.get("mssv", "") or "")
            row_key = (mssv, ca_hoc_id)
            vals = [
                mssv, r.get("hoTen",""),
                r.get("maLopHocPhan", ""), r.get("tenLop", ""),
                r.get("tenMon", ""), r.get("tenCa", ""),
                r.get("ngayHoc", ""), r.get("gioHoc", ""),
                r.get("thoiGian", ""),
                STATUS_LABEL.get(status, status)
            ]
            bg = QColor(STATUS_COLOR.get(status, "#ffffff"))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val or ""))
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(bg)
                if ca_hoc_id is not None:
                    # Khóa ổn định của dòng là (mssv, caHocId); tên ca
                    # chỉ là dữ liệu hiển thị và có thể trùng hoặc đổi tên.
                    item.setData(Qt.UserRole, row_key)
                    item.setData(Qt.UserRole + 1, ca_hoc_id)
                    item.setToolTip(
                        f"MSSV: {mssv} | Mã ca học: {ca_hoc_id}"
                    )
                self.table.setItem(row, col, item)
        self.lbl_count.setText(f"Kết quả: {len(rows)} bản ghi")

    def _export(self):
        if not hasattr(self, "_data") or not self._data:
            QMessageBox.warning(self, "Chú ý", "Không có dữ liệu để xuất.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu báo cáo Excel",
            "lich_su_diem_danh.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        ok = self.att_svc.export_excel_history(self._data, path)
        if ok:
            QMessageBox.information(
                self, "Thành công",
                f"Đã xuất {len(self._data)} bản ghi ra:\n{path}"
            )
        else:
            QMessageBox.critical(self, "Lỗi", "Xuất file thất bại.")
