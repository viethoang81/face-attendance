import logging
import re
from datetime import date, datetime

import cv2
import numpy as np
import winsound
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QGroupBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui  import QImage, QPixmap

from core.database import BASE_DIR
from services.session_service import compute_ca_status

logger = logging.getLogger(__name__)

SOUND_DIR = BASE_DIR / "assets" / "sounds"


def _session_display_name(ca: dict) -> str:
    """Return a compact session name for attendance screens."""
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

_TIME_STATUS_STYLE = {
    "ChuaMo":     ("color:#BA7517; font-size:12px; padding:2px 0;",
                   "⏰ Chưa đến giờ"),
    "DangDienRa": ("color:#1D9E75; font-size:12px; padding:2px 0;",
                   "🟢 Đang trong giờ học"),
    "DaKetThuc":  ("color:#888;    font-size:12px; padding:2px 0;",
                   "⏹ Đã qua giờ học"),
    "unknown":    ("color:gray;    font-size:12px; padding:2px 0;",
                   ""),
}
#  Thread chạy camera
class CameraThread(QThread):
    frame_ready       = pyqtSignal(object)
    student_marked    = pyqtSignal(str, str, str)
    challenge_changed = pyqtSignal(str)
    camera_error      = pyqtSignal(str)

    def __init__(self, engine, ca_hoc_id: int, name_map: dict):
        super().__init__()
        self.engine    = engine
        self.ca_hoc_id = ca_hoc_id
        self.name_map  = name_map
        self._running  = False
        self._emitted  = set()
        self._last_challenge = ""

    def run(self):
        self._running = True
        cap = cv2.VideoCapture(0)
        try:
            if not cap.isOpened():
                self.camera_error.emit("Không mở được camera")
                return

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    break

                results = self.engine.process_frame(
                    frame, self.ca_hoc_id, self.name_map
                )

                for r in results:
                    if r.get("status") == "spoof_check" and r.get("label"):
                        label = r["label"]
                        if label != self._last_challenge:
                            self._last_challenge = label
                            self.challenge_changed.emit(label)

                for r in results:
                    if r.get("status") == "new" and r.get("mssv"):
                        mssv = r["mssv"]
                        if mssv in self._emitted:
                            continue
                        self._emitted.add(mssv)
                        self.student_marked.emit(mssv, r["label"], "new")

                annotated = self.engine.draw(frame, results)
                self.frame_ready.emit(annotated)
        finally:
            cap.release()

    def stop(self):
        self._running = False
        self.wait(3000)

#  Tab điểm danh chính
class TabAttendance(QWidget):
    _STATUS_TICK_MS = 30_000   # 30 giây

    def __init__(self, att_engine, att_svc, sv_svc, class_access_svc, session_svc):
        super().__init__()
        self.engine      = att_engine
        self.att_svc     = att_svc
        self.sv_svc      = sv_svc
        self.class_access_svc = class_access_svc
        self.session_svc = session_svc

        self.thread          = None
        self.ca_hoc_id       = None
        self._ma_lop         = None
        self._ca_info: dict | None = None
        self._last_sound_key = ""

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(self._STATUS_TICK_MS)
        self._status_timer.timeout.connect(self._tick_status)

        self._setup_ui()
        self._load_classes()

    #  Xây dựng giao diện
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(10)

        left = QVBoxLayout()

        self.lbl_cam = QLabel("Camera chưa được bật")
        self.lbl_cam.setMinimumSize(760, 430)
        self.lbl_cam.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        self.lbl_cam.setAlignment(Qt.AlignCenter)
        self.lbl_cam.setStyleSheet(
            "background:#1a1a1a; color:#888; "
            "border-radius:8px; font-size:14px;"
        )
        left.addWidget(self.lbl_cam, 1)

        grp_ca = QGroupBox("Chọn ca học")
        grp_ca.setMaximumHeight(145)
        grp_ca.setStyleSheet(
            "QGroupBox{font-weight:600;font-size:13px;"
            "border:1px solid #CCD2DD;border-radius:8px;"
            "margin-top:6px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;"
            "left:10px;padding:0 4px;}"
        )
        ca_layout = QVBoxLayout(grp_ca)
        ca_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Lớp:"))
        self.cmb_lop = QComboBox()
        self.cmb_lop.setMinimumHeight(34)
        self.cmb_lop.currentIndexChanged.connect(self._on_lop_changed)
        row1.addWidget(self.cmb_lop, 2)

        btn_refresh_ca = QPushButton("↺ Làm mới")
        btn_refresh_ca.setMinimumHeight(34)
        btn_refresh_ca.setStyleSheet(
            "background:#185FA5;color:white;"
            "border-radius:6px;padding:0 10px;"
        )
        btn_refresh_ca.clicked.connect(self._load_ca_list)
        row1.addWidget(btn_refresh_ca)
        ca_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Môn học:"))
        self.lbl_mon_value = QLabel("Chưa chọn môn học")
        self.lbl_mon_value.setMinimumHeight(34)
        self.lbl_mon_value.setStyleSheet(
            "background:white;border:1px solid #CCD2DD;"
            "border-radius:4px;padding:0 8px;color:#222;"
        )
        self.lbl_mon_value.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        row2.addWidget(self.lbl_mon_value, 1)

        row2.addWidget(QLabel("Ca học:"))
        self.cmb_ca = QComboBox()
        self.cmb_ca.setMinimumHeight(34)
        self.cmb_ca.setMinimumWidth(380)
        self.cmb_ca.currentIndexChanged.connect(self._on_ca_changed)
        row2.addWidget(self.cmb_ca, 2)
        ca_layout.addLayout(row2)

        info_row = QHBoxLayout()
        self.lbl_ca_info = QLabel("Chưa chọn ca học")
        self.lbl_ca_info.setStyleSheet(
            "color:#534AB7; font-size:12px; padding:2px 4px;"
        )
        self.lbl_time_badge = QLabel("")
        self.lbl_time_badge.setStyleSheet(
            "font-size:12px; font-weight:600; padding:2px 4px;"
        )
        info_row.addWidget(self.lbl_ca_info, 1)
        info_row.addWidget(self.lbl_time_badge)
        ca_layout.addLayout(info_row)

        left.addWidget(grp_ca)

        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("▶  Bắt đầu điểm danh")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.setStyleSheet(
            "QPushButton{background:#1D9E75;color:white;"
            "border-radius:6px;font-size:13px;"
            "font-weight:600;padding:0 16px;}"
            "QPushButton:disabled{background:#888;}"
        )
        self.btn_start.clicked.connect(self._start)

        self.btn_stop = QPushButton("⏹  Dừng")
        self.btn_stop.setMinimumHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton{background:#D85A30;color:white;"
            "border-radius:6px;font-size:13px;"
            "font-weight:600;padding:0 16px;}"
            "QPushButton:disabled{background:#888;}"
        )
        self.btn_stop.clicked.connect(self._stop)

        ctrl.addWidget(self.btn_start, 1)
        ctrl.addWidget(self.btn_stop, 1)
        left.addLayout(ctrl)

        self.lbl_session = QLabel("Chưa có ca học nào đang diễn ra")
        self.lbl_session.setStyleSheet(
            "color:gray; font-size:12px; padding:2px 0;"
        )
        left.addWidget(self.lbl_session)

        layout.addLayout(left, 1)

        right_panel = QWidget()
        right_panel.setMinimumWidth(560)
        right_panel.setMaximumWidth(720)
        right = QVBoxLayout(right_panel)
        right.setSpacing(8)

        lbl_log = QLabel("Điểm danh trong ca này")
        lbl_log.setStyleSheet(
            "font-size:14px; font-weight:500; padding:4px 0;"
        )
        right.addWidget(lbl_log)
        self.tbl_log = QTableWidget(0, 3)
        self.tbl_log.setHorizontalHeaderLabels(
            ["MSSV", "Họ tên", "Giờ vào"]
        )
        self.tbl_log.setColumnWidth(0, 90)
        self.tbl_log.setColumnWidth(2, 90)
        self.tbl_log.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Fixed
        )
        self.tbl_log.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.tbl_log.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Fixed
        )
        self.tbl_log.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_log.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_log.verticalHeader().setVisible(False)
        self.tbl_log.setAlternatingRowColors(True)
        right.addWidget(self.tbl_log, 1)

        self.lbl_count = QLabel("Đã điểm danh: 0 sinh viên")
        self.lbl_count.setStyleSheet(
            "color:#1D9E75; font-size:13px; font-weight:500;"
        )
        right.addWidget(self.lbl_count)

        btn_end = QPushButton("Kết thúc ca & xuất Excel")
        btn_end.setMinimumHeight(34)
        btn_end.setStyleSheet(
            "background:#3B6D11;color:white;"
            "border-radius:6px;padding:0 12px;"
        )
        btn_end.clicked.connect(self._end_session)
        right.addWidget(btn_end)

        layout.addWidget(right_panel, 0)

    #  Load dữ liệu lớp + ca học
    def _load_classes(self):
        self.cmb_lop.blockSignals(True)
        self.cmb_lop.clear()
        for c in self.class_access_svc.get_visible_classes():
            self.cmb_lop.addItem(c["tenLop"], c["maLop"])
        self.cmb_lop.blockSignals(False)
        self._load_ca_list()

    def _on_lop_changed(self):
        self._load_ca_list()

    def _load_ca_list(self):
        """Load opened sessions and sync expired status before showing them."""
        ma_lop = self.cmb_lop.currentData()
        if not ma_lop:
            self.cmb_ca.clear()
            self.cmb_ca.addItem("-- Chưa có ca học --", None)
            self.lbl_mon_value.setText("Chưa chọn môn học")
            return

        today = date.today().strftime("%Y-%m-%d")
        all_ca = self.session_svc.get_ca_by_lop(ma_lop, ngay=today)
        for ca in all_ca:
            if ca.get("trangThai") in ("ChuaMo", "DangDienRa"):
                self.session_svc.sync_status(ca["id"])

        all_ca = self.session_svc.get_ca_by_lop(ma_lop, ngay=today)
        ca_list = [c for c in all_ca if c.get("trangThai") == "DangDienRa"]

        self.cmb_ca.blockSignals(True)
        self.cmb_ca.clear()
        if not ca_list:
            self.cmb_ca.addItem("-- Không có ca nào đang mở hôm nay --", None)
        else:
            for ca in ca_list:
                gio = ""
                if ca.get("gioBatDau") and ca.get("gioKetThuc"):
                    gio = f" ({ca['gioBatDau']}-{ca['gioKetThuc']})"
                self.cmb_ca.addItem(f"{_session_display_name(ca)}{gio}", ca["id"])
        self.cmb_ca.blockSignals(False)
        self._on_ca_changed()

    def _on_ca_changed(self):
        ca_id = self.cmb_ca.currentData()
        if not ca_id:
            self.lbl_ca_info.setText("Chưa chọn ca học")
            self.lbl_mon_value.setText("Chưa chọn môn học")
            self.lbl_time_badge.setText("")
            self._ca_info = None
            return

        ca = self.session_svc.get_ca_by_id(ca_id)
        if not ca:
            self.lbl_ca_info.setText("Không tìm thấy thông tin ca")
            self.lbl_mon_value.setText("Không tìm thấy môn học")
            self.lbl_time_badge.setText("")
            self._ca_info = None
            return

        self._ca_info = ca
        self.lbl_mon_value.setText(ca.get("tenMon") or "Chưa có môn học")
        self._refresh_time_badge(ca)

        parts = []
        if ca.get("phongHoc"):
            parts.append(f"Phòng: {ca['phongHoc']}")
        if ca.get("gioBatDau") and ca.get("gioKetThuc"):
            parts.append(f"Giờ: {ca['gioBatDau']} – {ca['gioKetThuc']}")
        if ca.get("nguoiTao"):
            parts.append(f"Tạo bởi: {ca['nguoiTao']}")
        self.lbl_ca_info.setText(
            "  |  ".join(parts) if parts else "Ca học không có thêm thông tin"
        )

    def _refresh_time_badge(self, ca: dict | None = None):
        if ca is None:
            ca = self._ca_info
        if not ca:
            self.lbl_time_badge.setText("")
            return

        status = compute_ca_status(
            ca.get("ngayHoc", ""),
            ca.get("gioBatDau", ""),
            ca.get("gioKetThuc", "")
        )
        style, text = _TIME_STATUS_STYLE.get(
            status, _TIME_STATUS_STYLE["unknown"]
        )
        self.lbl_time_badge.setStyleSheet(style)
        self.lbl_time_badge.setText(text)
        return status

    def showEvent(self, event):
        super().showEvent(event)
        if not self.thread:
            current_lop = self.cmb_lop.currentData()
            self._load_classes()
            if current_lop:
                idx = self.cmb_lop.findData(current_lop)
                if idx >= 0:
                    self.cmb_lop.setCurrentIndex(idx)

    #  Timer tick — cập nhật trạng thái giờ học
    def _tick_status(self):
        if not self._ca_info:
            return

        status = compute_ca_status(
            self._ca_info.get("ngayHoc", ""),
            self._ca_info.get("gioBatDau", ""),
            self._ca_info.get("gioKetThuc", "")
        )

        style, text = _TIME_STATUS_STYLE.get(
            status, _TIME_STATUS_STYLE["unknown"]
        )
        self.lbl_time_badge.setStyleSheet(style)
        self.lbl_time_badge.setText(text)

        if status == "DaKetThuc" and self.thread is not None:
            self._auto_end_session()

    def _auto_end_session(self):
        self._stop()

        if self.ca_hoc_id:
            self.session_svc.set_status(self.ca_hoc_id, "DaKetThuc")

        count = self.tbl_log.rowCount()

        # Hỏi xuất Excel ngay tại đây, khi ca_hoc_id vẫn còn
        reply = QMessageBox.question(
            self, "Ca học kết thúc tự động",
            f"Ca học đã hết giờ và được kết thúc tự động.\n"
            f"Đã ghi nhận {count} sinh viên điểm danh.\n\n"
            "Bạn có muốn xuất báo cáo Excel ngay không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self._export_excel()

        # Clear state SAU khi đã xử lý xuất Excel
        self._clear_session_state()
        self._load_ca_list()

        self.lbl_session.setText(
            "Ca học đã kết thúc tự động (hết giờ). "
            "Chọn ca mới và nhấn 'Bắt đầu'."
        )
        self.lbl_session.setStyleSheet("color:#D85A30; font-size:12px;")

    def _clear_session_state(self):
        """Xoá sạch state ca hiện tại sau khi đã xử lý xong."""
        self.ca_hoc_id = None
        self._ma_lop   = None
        self._ca_info  = None
        self.engine.reset_session()

    # ════════════════════════════════════════════════
    #  Âm thanh
    # ════════════════════════════════════════════════
    def _play_sound(self, filename: str):
        path = SOUND_DIR / filename
        if not path.exists():
            return
        try:
            winsound.PlaySound(
                str(path),
                winsound.SND_FILENAME | winsound.SND_ASYNC
            )
        except Exception:
            logger.exception("[TabAttendance] Cannot play sound: %s", path)

    def _play_challenge_sound(self, label: str):
        label_lower = label.lower()
        if "chop" in label_lower or "chớp" in label_lower:
            sound_key, filename = "blink", "blink.wav"
        elif "trai" in label_lower or "trái" in label_lower:
            sound_key, filename = "turn_left", "turn_left.wav"
        elif "phai" in label_lower or "phải" in label_lower:
            sound_key, filename = "turn_right", "turn_right.wav"
        else:
            return
        if self._last_sound_key == sound_key:
            return
        self._last_sound_key = sound_key
        self._play_sound(filename)

    # ════════════════════════════════════════════════
    #  Bắt đầu điểm danh
    # ════════════════════════════════════════════════
    def _start(self):
        # Kiểm tra có lớp chưa
        if self.cmb_lop.count() == 0:
            QMessageBox.warning(
                self, "Chưa có lớp học",
                "Vui lòng vào menu Hệ thống → Quản lý lớp học\n"
                "để thêm lớp trước khi điểm danh."
            )
            return

        # Kiểm tra đã chọn ca chưa
        ca_id = self.cmb_ca.currentData()
        if not ca_id:
            QMessageBox.warning(
                self, "Chưa có ca học nào đang mở",
                "Không có ca học nào đang mở.\n\n"
                "Yêu cầu Admin vào tab 'Quản lý ca học'\n"
                "chọn ca cần điểm danh → nhấn '▶ Mở ca' trước."
            )
            return

        # Lấy thông tin ca từ DB
        ca = self.session_svc.get_ca_by_id(ca_id)
        if not ca:
            QMessageBox.critical(
                self, "Lỗi", "Không tìm thấy ca học trong CSDL."
            )
            return

        if not self.class_access_svc.can_access_class(ca.get("maLop", "")):
            QMessageBox.warning(
                self,
                "Không có quyền",
                "Bạn không có quyền điểm danh lớp này."
            )
            return

        ready, ready_message = (
            self.session_svc.validate_attendance_session(
                ca_id,
                require_open=True,
            )
        )
        if not ready:
            QMessageBox.warning(
                self,
                "Không thể điểm danh",
                ready_message,
            )
            return

        # Kiểm tra khuôn mặt
        if not self.engine.fe.known_encs:
            QMessageBox.warning(
                self, "Chưa có dữ liệu khuôn mặt",
                "Chưa có sinh viên nào đăng ký khuôn mặt.\n"
                "Vào tab 'Quản lý sinh viên' → chọn SV → "
                "'Đăng ký khuôn mặt'."
            )
            return

        if ca.get("trangThai") != "DangDienRa":
            QMessageBox.warning(
                self, "Ca học chưa được mở",
                f"Ca học này đang ở trạng thái '{ca.get('trangThai', 'N/A')}'.\n\n"
                "Vui lòng yêu cầu Admin vào tab 'Quản lý ca học'\n"
                "và nhấn '▶ Mở ca' trước khi điểm danh."
            )
            return

        # Only allow attendance inside the official class time window.
        time_status = compute_ca_status(
            ca["ngayHoc"],
            ca.get("gioBatDau", ""),
            ca.get("gioKetThuc", "")
        )
        if time_status != "DangDienRa":
            if time_status == "ChuaMo":
                msg = f"Ca hoc chua toi gio bat dau ({ca.get('gioBatDau', '')})."
            elif time_status == "DaKetThuc":
                msg = f"Ca hoc da ket thuc luc {ca.get('gioKetThuc', '')}."
            else:
                msg = "Khong xac dinh duoc khung gio cua ca hoc."
            QMessageBox.warning(
                self, "Khong the diem danh ngoai gio",
                msg + "\n\nChi duoc diem danh khi ca dang trong thoi gian chinh thuc."
            )
            return

        # Valid session: DangDienRa and currently inside the official time window.
        self.ca_hoc_id = ca_id
        self._ma_lop   = ca["maLop"]
        self._ca_info  = ca

        self.engine.reset_session()
        self._load_existing_log()
        self._last_sound_key = ""

        name_map   = self.sv_svc.get_name_map()
        self.thread = CameraThread(self.engine, ca_id, name_map)
        self.thread.frame_ready.connect(self._show_frame)
        self.thread.student_marked.connect(self._log_student)
        self.thread.challenge_changed.connect(self._play_challenge_sound)
        self.thread.camera_error.connect(self._on_camera_error)
        self.thread.start()

        # Không gọi set_status("DangDienRa") ở đây nữa —
        # Admin đã set từ tab quản lý ca học.

        self._status_timer.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.cmb_lop.setEnabled(False)
        self.cmb_ca.setEnabled(False)

        info_parts = [f"Ca: {_session_display_name(ca)}"]
        if ca.get("gioBatDau") and ca.get("gioKetThuc"):
            info_parts.append(f"{ca['gioBatDau']} – {ca['gioKetThuc']}")
        self.lbl_session.setText("  |  ".join(info_parts))
        self.lbl_session.setStyleSheet("color:#1D9E75; font-size:12px;")

    # ════════════════════════════════════════════════
    #  Xử lý lỗi camera
    # ════════════════════════════════════════════════
    def _on_camera_error(self, error_msg: str):
        if self.ca_hoc_id:
            # Trả ca về DangDienRa để Admin có thể thử lại
            self.session_svc.set_status(self.ca_hoc_id, "DangDienRa")

        self._status_timer.stop()
        self.thread    = None
        self.ca_hoc_id = None
        self._ma_lop   = None
        self._ca_info  = None

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.cmb_lop.setEnabled(True)
        self.cmb_ca.setEnabled(True)
        self.lbl_session.setText("Chưa có ca học nào đang diễn ra")
        self.lbl_session.setStyleSheet("color:gray; font-size:12px;")

        QMessageBox.critical(
            self, "Lỗi camera",
            f"{error_msg}\n\nVui lòng kiểm tra kết nối camera và thử lại."
        )

    # ════════════════════════════════════════════════
    #  Dừng camera
    # ════════════════════════════════════════════════
    def _stop(self):
        self._status_timer.stop()
        if self.thread:
            self.thread.stop()
            self.thread = None
        self.lbl_cam.setText(
            "Camera đã dừng.\nNhấn 'Bắt đầu' để điểm danh tiếp."
        )
        self.lbl_cam.setStyleSheet(
            "background:#1a1a1a; color:#888; "
            "border-radius:8px; font-size:14px;"
        )
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.cmb_lop.setEnabled(True)
        self.cmb_ca.setEnabled(True)

    # ════════════════════════════════════════════════
    #  Hiển thị frame
    # ════════════════════════════════════════════════
    def _show_frame(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.lbl_cam.setPixmap(
            QPixmap.fromImage(img).scaled(
                self.lbl_cam.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    # ════════════════════════════════════════════════
    #  Log sinh viên điểm danh
    # ════════════════════════════════════════════════
    def _load_existing_log(self):
        if not self.ca_hoc_id:
            return
        records = self.att_svc.get_session_summary(self.ca_hoc_id)
        self.tbl_log.setRowCount(0)
        for rec in records:
            mssv = str(rec.get("mssv", ""))
            if mssv:
                self.engine.marked_in_session.add(mssv)
            row = self.tbl_log.rowCount()
            self.tbl_log.insertRow(row)
            items = [
                QTableWidgetItem(mssv),
                QTableWidgetItem(str(rec.get("hoTen", ""))),
                QTableWidgetItem(str(rec.get("thoiGian", ""))[-8:]),
            ]
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.tbl_log.setItem(row, col, item)
        self.lbl_count.setText(
            f"Đã điểm danh: {self.tbl_log.rowCount()} sinh viên"
        )

    def _log_student(self, mssv: str, label: str, status: str):
        if status != "new":
            return
        for r in range(self.tbl_log.rowCount()):
            item = self.tbl_log.item(r, 0)
            if item and item.text() == mssv:
                return
        row = self.tbl_log.rowCount()
        self.tbl_log.insertRow(row)
        ten = label.split("(")[0].strip()
        items = [
            QTableWidgetItem(mssv),
            QTableWidgetItem(ten),
            QTableWidgetItem(datetime.now().strftime("%H:%M:%S")),
        ]
        for col, item in enumerate(items):
            item.setTextAlignment(Qt.AlignCenter)
            self.tbl_log.setItem(row, col, item)
        self.tbl_log.scrollToBottom()
        self.lbl_count.setText(
            f"Đã điểm danh: {self.tbl_log.rowCount()} sinh viên"
        )
        self._last_sound_key = ""
        self._play_sound("success.wav")

    #  Xuất Excel (tái sử dụng ở cả _end_session & _auto_end_session)
    def _export_excel(self):
        """Mở dialog lưu file và xuất báo cáo Excel cho ca hiện tại."""
        if not self.ca_hoc_id:
            return
        from PyQt5.QtWidgets import QFileDialog
        ten_ca = (self._ca_info or {}).get("tenCa", "ca_hoc")
        safe_name = "".join(
            c for c in ten_ca if c.isalnum() or c in " _-"
        ).strip()
        default_name = (
            f"diem_danh_{safe_name}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu báo cáo", default_name, "Excel (*.xlsx)"
        )
        if not path:
            return
        records = self.att_svc.get_session_full_report(
            self.ca_hoc_id, self._ma_lop
        )
        ok = self.att_svc.export_excel_session(
            records, path,
            ten_ca=(self._ca_info or {}).get("tenCa", "")
        )
        if ok:
            QMessageBox.information(
                self, "Thành công",
                f"Đã xuất báo cáo ra:\n{path}"
            )

    # ════════════════════════════════════════════════
    #  Kết thúc ca học (thủ công)
    # ════════════════════════════════════════════════
    def _end_session(self):
        if not self.ca_hoc_id:
            QMessageBox.information(
                self, "Thông báo",
                "Chưa có ca học nào đang diễn ra."
            )
            return

        self._stop()

        count = self.tbl_log.rowCount()
        reply = QMessageBox.question(
            self, "Kết thúc ca học",
            f"Ca học đã ghi nhận {count} sinh viên điểm danh.\n"
            "Bạn có muốn xuất báo cáo Excel không?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._export_excel()

        self.session_svc.set_status(self.ca_hoc_id, "DaKetThuc")
        self._load_ca_list()
        self._clear_session_state()

        self.lbl_session.setText(
            "Ca học đã kết thúc. Chọn ca mới và nhấn 'Bắt đầu'."
        )
        self.lbl_session.setStyleSheet("color:gray; font-size:12px;")

    #  Dọn dẹp khi đóng app
    def closeEvent(self, event):
        self._status_timer.stop()
        if self.thread:
            self.thread.stop()
        self.engine.close()
        super().closeEvent(event)
