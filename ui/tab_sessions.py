# ui/tab_sessions.py
import re

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel,
    QLineEdit, QSpinBox, QPushButton, QComboBox,
    QDateEdit, QMessageBox, QFormLayout, QDialog,
    QDialogButtonBox, QStyledItemDelegate
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui  import QColor
def _fix_combo_delegate(combo: QComboBox):
    combo.setItemDelegate(QStyledItemDelegate(combo))
from services.session_service import SessionService, MonHoc, CaHoc, KHUNG_GIO, compute_ca_status

_STATUS_COLOR = {
    "ChuaMo":      "#EEF1F7",
    "DangDienRa":  "#E1F5EE",
    "DaKetThuc":   "#F0F0F0",
}
_STATUS_LABEL = {
    "ChuaMo":      "Chưa mở",
    "DangDienRa":  "Đang diễn ra",
    "DaKetThuc":   "Đã kết thúc",
}

def _session_display_name(ca: dict) -> str:
    """Return a compact session name for display-only surfaces."""
    ten_ca = str(ca.get("tenCa", "")).strip()
    match = re.search(r"\bCa\s*\d+\b", ten_ca, flags=re.IGNORECASE)
    context_values = [
        str(ca.get("tenMon", "")).strip(),
        str(ca.get("tenLop", "")).strip(),
        str(ca.get("maLop", "")).strip(),
    ]
    compactable = any(
        value and value.casefold() in ten_ca.casefold()
        for value in context_values
    )
    suffix = ten_ca[match.end():].strip() if match else ""
    if match and (compactable or " - " in ten_ca or suffix.startswith(("-", "–", "—"))):
        return re.sub(r"\s+", " ", match.group(0)).title()
    return ten_ca or "Ca học"

#  Dialog thêm / sửa Ca học
class CaHocDialog(QDialog):
    def __init__(self, session_svc: SessionService,
                 cls_svc,
                 existing: dict = None,
                 nguoi_tao: str = "",
                 parent=None):
        super().__init__(parent)
        self.session_svc = session_svc
        self.cls_svc     = cls_svc
        self.existing    = existing
        self.nguoi_tao   = nguoi_tao
        self.result_ca: CaHoc | None = None
        self._auto_name  = True  # flag: tự động cập nhật tên ca
        self.setWindowTitle(
            "Sửa ca học" if existing else "Thêm ca học mới"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(self._style())
        self._setup_ui()
        if existing:
            self._populate(existing)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # ── Lớp ──
        self.cmb_lop = QComboBox()
        _fix_combo_delegate(self.cmb_lop) 
        for c in self.cls_svc.get_all():
            self.cmb_lop.addItem(c["tenLop"], c["maLop"])
        form.addRow("Lớp *", self.cmb_lop)

        # ── Môn học (bắt buộc) ──
        self.cmb_mon = QComboBox()
        _fix_combo_delegate(self.cmb_mon)
        mon_list = self.session_svc.get_all_mon()
        if not mon_list:
            self.cmb_mon.addItem("— Chưa có môn học nào —", "__EMPTY__")
        else:
            for m in mon_list:
                self.cmb_mon.addItem(
                    f"{m['maMon']} - {m['tenMon']}", m["maMon"]
                )
        form.addRow("Môn học *", self.cmb_mon)

        # ── Khung giờ ──
        self.cmb_khung_gio = QComboBox()
        _fix_combo_delegate(self.cmb_khung_gio) 
        for _, _, gbd, gkt in KHUNG_GIO:
            self.cmb_khung_gio.addItem(f"{gbd} – {gkt}", (gbd, gkt))
        self.cmb_khung_gio.currentIndexChanged.connect(
            self._on_khung_gio_changed
        )
        form.addRow("Khung giờ *", self.cmb_khung_gio)

        # ── Tên ca ──
        self.txt_ten_ca = QLineEdit()
        self.txt_ten_ca.setPlaceholderText(
            "Tự động điền theo khung giờ, có thể chỉnh"
        )
        self.txt_ten_ca.textEdited.connect(self._on_ten_ca_edited)
        form.addRow("Tên ca *", self.txt_ten_ca)

        # ── Ngày học ──
        self.dte_ngay = QDateEdit(QDate.currentDate())
        self.dte_ngay.setCalendarPopup(True)
        self.dte_ngay.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Ngày học *", self.dte_ngay)

        # ── Phòng học ──
        self.txt_phong = QLineEdit()
        self.txt_phong.setPlaceholderText("Ví dụ: A201, B305") 
        form.addRow("Phòng học *", self.txt_phong)

        root.addLayout(form)

        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet(
            "color:#D85A30; font-size:12px; padding:2px 0;"
        )
        self.lbl_err.setWordWrap(True)
        root.addWidget(self.lbl_err)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.button(QDialogButtonBox.Ok).setText("Lưu")
        btns.button(QDialogButtonBox.Cancel).setText("Hủy")
        btns.accepted.connect(self._submit)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # Khởi tạo tên ca theo lớp + khung giờ mặc định
        self._sync_ten_ca_from_khung()

    # ── Slots auto-fill tên ca ───────────────────────────────────────────────
    def _on_khung_gio_changed(self):
        """
        Gọi khi đổi khung giờ.
        Cập nhật tên ca tự động nếu _auto_name còn True.
        """
        if self._auto_name:
            self._sync_ten_ca_from_khung()

    def _on_ten_ca_edited(self):
        """Người dùng đã tự sửa tên ca → tắt auto-fill."""
        self._auto_name = False

    def _sync_ten_ca_from_khung(self):
        """
        Điền tên ca mặc định theo khung giờ.
        Ví dụ: "Ca 2"
        """
        idx = self.cmb_khung_gio.currentIndex()
        if 0 <= idx < len(KHUNG_GIO):
            _, ten_ca_mac_dinh, _, _ = KHUNG_GIO[idx]
            self.txt_ten_ca.setText(ten_ca_mac_dinh)

    # ── Populate khi sửa ────────────────────────────────────────────────────
    def _populate(self, d: dict):
        # Lớp (không cho đổi khi sửa)
        idx = self.cmb_lop.findData(d.get("maLop", ""))
        if idx >= 0:
            self.cmb_lop.setCurrentIndex(idx)
        self.cmb_lop.setEnabled(False)

        # Môn học
        idx = self.cmb_mon.findData(d.get("maMon", ""))
        if idx >= 0:
            self.cmb_mon.setCurrentIndex(idx)

        # Khung giờ
        gbd = d.get("gioBatDau", "")
        gkt = d.get("gioKetThuc", "")
        matched = False
        for i in range(self.cmb_khung_gio.count()):
            if self.cmb_khung_gio.itemData(i) == (gbd, gkt):
                self.cmb_khung_gio.setCurrentIndex(i)
                matched = True
                break
        if not matched and gbd and gkt:
            custom_label = f"{gbd} – {gkt}"
            self.cmb_khung_gio.insertItem(0, custom_label, (gbd, gkt))
            self.cmb_khung_gio.setCurrentIndex(0)

        # Tên ca (đã đặt sẵn → tắt auto-fill)
        self._auto_name = False
        self.txt_ten_ca.setText(d.get("tenCa", ""))

        # Ngày học
        ngay = d.get("ngayHoc", "")
        if ngay:
            self.dte_ngay.setDate(QDate.fromString(ngay, "yyyy-MM-dd"))

        # Phòng học
        self.txt_phong.setText(d.get("phongHoc", ""))

    # ── Submit ───────────────────────────────────────────────────────────────
    def _submit(self):
        ma_mon = self.cmb_mon.currentData()
        if not ma_mon or ma_mon == "__EMPTY__":
            self.lbl_err.setText(
                "Chưa có môn học nào. Vui lòng thêm môn học trước."
            )
            return

        gbd, gkt = self.cmb_khung_gio.currentData()

        ca = CaHoc(
            maLop      = self.cmb_lop.currentData(),
            maMon      = ma_mon,
            tenCa      = self.txt_ten_ca.text(),
            ngayHoc    = self.dte_ngay.date().toString("yyyy-MM-dd"),
            gioBatDau  = gbd,
            gioKetThuc = gkt,
            phongHoc   = self.txt_phong.text(),
            nguoiTao   = self.nguoi_tao,
        )
        if self.existing:
            ca.id = self.existing["id"]

        err = self.session_svc._validate_ca(ca)
        if err:
            self.lbl_err.setText(err)
            return

        self.result_ca = ca
        self.accept()

    @staticmethod
    def _style():
        return """
        QDialog {
            background: #EEF1F7;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QLineEdit, QComboBox, QDateEdit {
            border: 1px solid #CCD2DD;
            border-radius: 6px;
            padding: 6px 9px;
            background: #FAFAFC;
            min-height: 28px;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
            border: 1px solid #534AB7;
            background: white;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #CCD2DD;
            background: #FAFAFC;
            outline: 0;
        }
        QComboBox QAbstractItemView::item {
            min-height: 26px;
            padding: 4px 8px;
        }
        """
    
#  Tab chính
class TabSessions(QWidget):
    """Tab quản lý môn học và ca học — chỉ dành cho Admin."""

    def __init__(self, session_svc: SessionService,
                 cls_svc,
                 current_user: dict = None):
        super().__init__()
        self.session_svc  = session_svc
        self.cls_svc      = cls_svc
        self.current_user = current_user or {}
        self._ca_data:  list[dict] = []
        self._mon_data: list[dict] = []
        self._setup_ui()

    # ── Xây dựng giao diện ──────────────────────────────────────────────────
    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_mon_panel())
        splitter.addWidget(self._build_ca_panel())
        splitter.setSizes([340, 860])
        root.addWidget(splitter)

    # ── Panel Môn học ────────────────────────────────────────────────────────
    def _build_mon_panel(self) -> QGroupBox:
        grp = QGroupBox("📚  Môn học")
        layout = QVBoxLayout(grp)

        self.tbl_mon = QTableWidget()
        self.tbl_mon.setColumnCount(3)
        self.tbl_mon.setHorizontalHeaderLabels(
            ["Mã môn", "Tên môn", "Số tiết"]
        )
        self.tbl_mon.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.tbl_mon.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_mon.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_mon.verticalHeader().setVisible(False)
        self.tbl_mon.setAlternatingRowColors(True)
        layout.addWidget(self.tbl_mon)

        form_grp = QGroupBox("Thêm môn học")
        form = QFormLayout(form_grp)
        form.setSpacing(8)

        self.txt_ma_mon  = QLineEdit()
        self.txt_ten_mon = QLineEdit()
        self.spn_so_tiet = QSpinBox()
        self.spn_so_tiet.setRange(1, 300)
        self.spn_so_tiet.setValue(45)

        self.txt_ma_mon.setPlaceholderText("VD: CNTT101")
        self.txt_ten_mon.setPlaceholderText("VD: Lập trình Python")

        form.addRow("Mã môn *",  self.txt_ma_mon)
        form.addRow("Tên môn *", self.txt_ten_mon)
        form.addRow("Số tiết",   self.spn_so_tiet)

        self.lbl_mon_err = QLabel()
        self.lbl_mon_err.setStyleSheet(
            "color:#D85A30; font-size:12px;"
        )
        form.addRow(self.lbl_mon_err)
        layout.addWidget(form_grp)

        btn_row = QHBoxLayout()
        self._btn(btn_row, "+ Thêm",  "#1D9E75", self._add_mon)
        self._btn(btn_row, "Sửa",     "#BA7517", self._edit_mon)
        self._btn(btn_row, "Xoá",     "#D85A30", self._del_mon)
        layout.addLayout(btn_row)

        return grp

    # ── Panel Ca học ─────────────────────────────────────────────────────────
    def _build_ca_panel(self) -> QGroupBox:
        grp = QGroupBox("📅  Ca học")
        layout = QVBoxLayout(grp)

        filter_row = QHBoxLayout()

        self.cmb_filter_lop = QComboBox()
        self.cmb_filter_lop.setMinimumHeight(30)

        self.dte_filter_from = QDateEdit(QDate.currentDate())
        self.dte_filter_from.setCalendarPopup(True)
        self.dte_filter_from.setDisplayFormat("dd/MM/yyyy")
        self.dte_filter_from.setMinimumHeight(30)

        self.dte_filter_to = QDateEdit(QDate.currentDate())
        self.dte_filter_to.setCalendarPopup(True)
        self.dte_filter_to.setDisplayFormat("dd/MM/yyyy")
        self.dte_filter_to.setMinimumHeight(30)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.setMinimumHeight(30)
        self.cmb_filter_status.addItem("Tất cả trạng thái", "")
        for k, v in _STATUS_LABEL.items():
            self.cmb_filter_status.addItem(v, k)

        btn_filter = QPushButton("Lọc")
        btn_filter.setMinimumHeight(30)
        btn_filter.setStyleSheet(
            "background:#185FA5;color:white;border-radius:5px;padding:0 12px;"
        )
        btn_filter.clicked.connect(self._load_ca)

        btn_today = QPushButton("Hôm nay")
        btn_today.setMinimumHeight(30)
        btn_today.clicked.connect(self._filter_today)

        filter_row.addWidget(QLabel("Lớp:"))
        filter_row.addWidget(self.cmb_filter_lop, 2)
        filter_row.addWidget(QLabel("Từ:"))
        filter_row.addWidget(self.dte_filter_from)
        filter_row.addWidget(QLabel("Đến:"))
        filter_row.addWidget(self.dte_filter_to)
        filter_row.addWidget(QLabel("Trạng thái:"))
        filter_row.addWidget(self.cmb_filter_status, 2)
        filter_row.addWidget(btn_filter)
        filter_row.addWidget(btn_today)
        layout.addLayout(filter_row)

        self.tbl_ca = QTableWidget()
        self.tbl_ca.setColumnCount(8)
        self.tbl_ca.setHorizontalHeaderLabels([
            "ID", "Lớp", "Môn học", "Tên ca",
            "Ngày học", "Giờ học", "Phòng", "Trạng thái"
        ])
        self.tbl_ca.setColumnWidth(0, 45)
        self.tbl_ca.setColumnWidth(1, 120)
        self.tbl_ca.setColumnWidth(3, 110)
        self.tbl_ca.setColumnWidth(4, 130)
        self.tbl_ca.setColumnWidth(5, 150)
        self.tbl_ca.setColumnWidth(6, 80)
        self.tbl_ca.setColumnWidth(7, 120)
        self.tbl_ca.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.tbl_ca.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_ca.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_ca.verticalHeader().setVisible(False)
        self.tbl_ca.setAlternatingRowColors(True)
        layout.addWidget(self.tbl_ca)

        footer = QHBoxLayout()
        self.lbl_ca_count = QLabel("0 ca học")
        self.lbl_ca_count.setStyleSheet("color:gray; font-size:12px;")
        footer.addWidget(self.lbl_ca_count)
        footer.addStretch()

        self._btn(footer, "+ Thêm ca",  "#1D9E75", self._add_ca)
        self._btn(footer, "Sửa ca",     "#BA7517", self._edit_ca)
        self._btn(footer, "Xoá ca",     "#D85A30", self._del_ca)
        footer.addSpacing(12)
        self._btn(footer, "▶ Mở ca",    "#185FA5", self._open_ca)
        self._btn(footer, "⏹ Kết thúc", "#534AB7", self._close_ca)
        layout.addLayout(footer)

        return grp

    # ── Tiện ích nút ────────────────────────────────────────────────────────
    @staticmethod
    def _btn(layout, text, color, handler):
        b = QPushButton(text)
        b.setMinimumHeight(32)
        b.setStyleSheet(
            f"QPushButton{{background:{color};color:white;"
            f"border-radius:5px;padding:0 12px;font-weight:500;}}"
            f"QPushButton:hover{{opacity:0.85;}}"
        )
        b.clicked.connect(handler)
        layout.addWidget(b)
        return b

    # ── Load dữ liệu ────────────────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_filters()
        self._load_mon()
        self._load_ca()

    def _refresh_filters(self):
        current = self.cmb_filter_lop.currentData()
        self.cmb_filter_lop.clear()
        self.cmb_filter_lop.addItem("Tất cả lớp", "")
        for c in self.cls_svc.get_all():
            self.cmb_filter_lop.addItem(c["tenLop"], c["maLop"])
        if current:
            idx = self.cmb_filter_lop.findData(current)
            if idx >= 0:
                self.cmb_filter_lop.setCurrentIndex(idx)

    def _load_mon(self):
        self._mon_data = self.session_svc.get_all_mon()
        self.tbl_mon.setRowCount(0)
        for m in self._mon_data:
            r = self.tbl_mon.rowCount()
            self.tbl_mon.insertRow(r)
            for col, key in enumerate(["maMon", "tenMon", "soTiet"]):
                item = QTableWidgetItem(str(m.get(key, "")))
                item.setTextAlignment(Qt.AlignCenter)
                self.tbl_mon.setItem(r, col, item)

    def _load_ca(self):
        ma_lop     = self.cmb_filter_lop.currentData() or ""
        ngay_from  = self.dte_filter_from.date().toString("yyyy-MM-dd")
        ngay_to    = self.dte_filter_to.date().toString("yyyy-MM-dd")
        trang_thai = self.cmb_filter_status.currentData() or ""

        self._ca_data = self.session_svc.get_all_ca(
            ma_lop=ma_lop,
            ngay_from=ngay_from,
            ngay_to=ngay_to,
            trang_thai=trang_thai
        )
        need_reload = False
        for ca in self._ca_data:
            if ca.get("trangThai") in ("ChuaMo", "DangDienRa"):
                before = ca.get("trangThai")
                after = self.session_svc.sync_status(ca["id"])
                if after != before:
                    need_reload = True
        if need_reload:
            self._ca_data = self.session_svc.get_all_ca(
                ma_lop=ma_lop,
                ngay_from=ngay_from,
                ngay_to=ngay_to,
                trang_thai=trang_thai
            )
        self._fill_ca_table(self._ca_data)

    def _fill_ca_table(self, rows: list[dict]):
        self.tbl_ca.setRowCount(0)
        for d in rows:
            r = self.tbl_ca.rowCount()
            self.tbl_ca.insertRow(r)

            gio = ""
            if d.get("gioBatDau") and d.get("gioKetThuc"):
                gio = f"{d['gioBatDau']} – {d['gioKetThuc']}"
            elif d.get("gioBatDau"):
                gio = d["gioBatDau"]

            status_key = d.get("trangThai", "ChuaMo")
            vals = [
                str(d.get("id", "")),
                d.get("tenLop", ""),
                d.get("tenMon", ""),
                _session_display_name(d),
                d.get("ngayHoc", ""),
                gio,
                d.get("phongHoc", ""),
                _STATUS_LABEL.get(status_key, status_key),
            ]
            bg = QColor(_STATUS_COLOR.get(status_key, "#FFFFFF"))
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(bg)
                self.tbl_ca.setItem(r, col, item)

        self.lbl_ca_count.setText(f"{len(rows)} ca học")

    def _filter_today(self):
        today = QDate.currentDate()
        self.dte_filter_from.setDate(today)
        self.dte_filter_to.setDate(today)
        self._load_ca()

    # ── CRUD Môn học ─────────────────────────────────────────────────────────
    def _add_mon(self):
        ma  = self.txt_ma_mon.text().strip()
        ten = self.txt_ten_mon.text().strip()
        ok, msg = self.session_svc.add_mon(
            MonHoc(maMon=ma, tenMon=ten,
                   soTiet=self.spn_so_tiet.value())
        )
        if ok:
            self.lbl_mon_err.setText("")
            self.txt_ma_mon.clear()
            self.txt_ten_mon.clear()
            self.spn_so_tiet.setValue(45)
            self._load_mon()
        else:
            self.lbl_mon_err.setText(msg)

    def _edit_mon(self):
        row = self.tbl_mon.currentRow()
        if row < 0:
            QMessageBox.warning(
                self,
                "Chú ý",
                "Vui lòng chọn môn học.",
            )
            return

        mon = self._mon_data[row]
        dlg = _MonHocEditDialog(mon, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return

        ok, msg = self.session_svc.update_mon(
            mon["maMon"],
            MonHoc(
                maMon=dlg.txt_ma.text().strip(),
                tenMon=dlg.txt_ten.text().strip(),
                soTiet=dlg.spn_tiet.value(),
            ),
        )
        if ok:
            self._load_mon()
        else:
            QMessageBox.warning(self, "Lỗi", msg)

    def _del_mon(self):
        row = self.tbl_mon.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Chú ý", "Vui lòng chọn môn học.")
            return
        m = self._mon_data[row]
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Xoá môn học '{m['tenMon']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = self.session_svc.delete_mon(m["maMon"])
            if ok:
                self._load_mon()
            else:
                QMessageBox.warning(self, "Không thể xoá", msg)

    # ── CRUD Ca học ──────────────────────────────────────────────────────────
    def _add_ca(self):
        if not self.session_svc.get_all_mon():
            QMessageBox.warning(
                self, "Chưa có môn học",
                "Vui lòng thêm ít nhất một môn học trước khi tạo ca."
            )
            return
        username = self.current_user.get("username", "")
        dlg = CaHocDialog(
            self.session_svc, self.cls_svc,
            nguoi_tao=username, parent=self
        )
        if dlg.exec_() and dlg.result_ca:
            ca_id, msg = self.session_svc.create_ca(dlg.result_ca)
            if ca_id > 0:
                self._load_ca()
            else:
                QMessageBox.warning(self, "Không thể tạo ca", msg)

    def _edit_ca(self):
        _, d = self._selected_ca()
        if d is None:
            return
        if d.get("trangThai") != "ChuaMo":
            QMessageBox.warning(
                self, "Không thể sửa",
                "Chỉ có thể sửa ca học ở trạng thái 'Chưa mở'."
            )
            return
        username = self.current_user.get("username", "")
        dlg = CaHocDialog(
            self.session_svc, self.cls_svc,
            existing=d, nguoi_tao=username, parent=self
        )
        if dlg.exec_() and dlg.result_ca:
            ok, msg = self.session_svc.update_ca(dlg.result_ca)
            if ok:
                self._load_ca()
            else:
                QMessageBox.warning(self, "Không thể cập nhật", msg)

    def _del_ca(self):
        _, d = self._selected_ca()
        if d is None:
            return
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Xoá ca học '{d['tenCa']}'?\n"
            "Ca chỉ xoá được nếu chưa có điểm danh.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = self.session_svc.delete_ca(d["id"])
            if ok:
                self._load_ca()
            else:
                QMessageBox.warning(self, "Không thể xoá", msg)

    def _open_ca(self):
        """Open a session only inside the official time window."""
        _, d = self._selected_ca()
        if d is None:
            return
        if d.get("trangThai") != "ChuaMo":
            QMessageBox.warning(self, "Không hợp lệ", "Chỉ có thể mở ca ở trạng thái 'Chưa mở'.")
            return

        time_status = compute_ca_status(
            d.get("ngayHoc", ""),
            d.get("gioBatDau", ""),
            d.get("gioKetThuc", "")
        )
        if time_status != "DangDienRa":
            if time_status == "ChuaMo":
                msg = f"Ca hoc chua toi gio bat dau ({d.get('gioBatDau', '')})."
            elif time_status == "DaKetThuc":
                msg = f"Ca hoc da ket thuc luc {d.get('gioKetThuc', '')}."
            else:
                msg = "Khong xac dinh duoc khung gio cua ca hoc."
            QMessageBox.warning(
                self, "Khong the mo ca ngoai gio",
                msg + "\n\nChi duoc mo ca khi dang trong khung gio chinh thuc."
            )
            return

        ok, msg = self.session_svc.set_status(d["id"], "DangDienRa")
        if ok:
            self._load_ca()
        else:
            QMessageBox.warning(self, "Loi", msg)

    def _close_ca(self):
        """Đóng ca thủ công — Admin kết thúc."""
        _, d = self._selected_ca()
        if d is None:
            return
        if d.get("trangThai") == "DaKetThuc":
            QMessageBox.information(
                self, "Thông báo", "Ca học này đã kết thúc rồi."
            )
            return
        reply = QMessageBox.question(
            self, "Xác nhận kết thúc ca",
            f"Kết thúc ca học '{d['tenCa']}'?\n"
            "Thao tác này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = self.session_svc.set_status(d["id"], "DaKetThuc")
            if ok:
                self._load_ca()
            else:
                QMessageBox.warning(self, "Lỗi", msg)

    # ── Helper chọn dòng ─────────────────────────────────────────────────────
    def _selected_ca(self) -> tuple[int, dict | None]:
        row = self.tbl_ca.currentRow()
        if row < 0 or row >= len(self._ca_data):
            QMessageBox.warning(
                self, "Chú ý", "Vui lòng chọn một ca học."
            )
            return -1, None
        return row, self._ca_data[row]


# ══════════════════════════════════════════════════════════
#  Dialog nhỏ: sửa tên + số tiết môn học
# ══════════════════════════════════════════════════════════
class _MonHocEditDialog(QDialog):
    """Dialog sửa mã môn, tên môn và số tiết."""

    def __init__(self, mon: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sửa môn - {mon['maMon']}")
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.txt_ma = QLineEdit(mon.get("maMon", ""))
        self.txt_ma.setPlaceholderText("VD: CNTT101")

        self.txt_ten = QLineEdit(mon.get("tenMon", ""))

        self.spn_tiet = QSpinBox()
        self.spn_tiet.setRange(1, 300)
        self.spn_tiet.setValue(mon.get("soTiet", 45))

        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet("color:#D85A30; font-size:12px;")
        self.lbl_err.setWordWrap(True)

        form.addRow("Mã môn *", self.txt_ma)
        form.addRow("Tên môn *", self.txt_ten)
        form.addRow("Số tiết", self.spn_tiet)
        form.addRow(self.lbl_err)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Lưu")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        ma_mon = self.txt_ma.text().strip()
        ten_mon = self.txt_ten.text().strip()

        if not ma_mon:
            self.lbl_err.setText("Mã môn không được để trống")
            return
        if not ten_mon:
            self.lbl_err.setText("Tên môn không được để trống")
            return

        self.accept()
