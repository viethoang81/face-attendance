import logging

from PyQt5.QtCore import QDate, Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.ui_helpers import (
    create_action_button,
    create_data_table,
)


logger = logging.getLogger(__name__)


COURSE_STATUS_LABELS = {
    "MO_DANG_KY": "Mở đăng ký",
    "DANG_HOC": "Đang học",
    "DA_KET_THUC": "Đã kết thúc",
    "DA_HUY": "Đã hủy",
}

REGISTRATION_STATUS_LABELS = {
    "DANG_HOC": "Đang học",
    "DA_HUY": "Đã hủy",
    "HOAN_THANH": "Hoàn thành",
    "DINH_CHI": "Đình chỉ",
}

STUDENT_STATUS_LABELS = {
    "DANG_HOC": "Đang học",
    "BAO_LUU": "Bảo lưu",
    "DINH_CHI": "Đình chỉ",
    "THOI_HOC": "Thôi học",
    "TOT_NGHIEP": "Tốt nghiệp",
}

REGISTRATION_ROW_COLORS = {
    "DANG_HOC": "#E1F5EE",
    "DA_HUY": "#F1F3F5",
    "HOAN_THANH": "#E6F4FF",
    "DINH_CHI": "#FAEEDA",
}


class TabMyCourseSections(QWidget):
    def __init__(
        self,
        lecturer_course_service,
    ):
        super().__init__()

        self.service = lecturer_course_service
        self._sections_by_id = {}
        self._has_been_shown = False

        self._build_ui()
        self._connect_signals()
        self._reload_sections()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        note = QLabel(
            "Chỉ hiển thị lớp học phần được phân công "
            "cho tài khoản giảng viên đang đăng nhập. "
            "Tab này chỉ đọc."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color:#185FA5; font-size:12px;"
        )
        layout.addWidget(note)

        filter_group = QGroupBox("Bộ lọc")
        filter_row = QHBoxLayout(filter_group)
        filter_row.setSpacing(8)

        self.cmb_section = QComboBox()
        self.cmb_section.setMinimumWidth(330)
        self.cmb_section.setMinimumHeight(32)

        self.cmb_status = QComboBox()
        self.cmb_status.setMinimumHeight(32)
        self.cmb_status.addItem(
            "Tất cả đăng ký",
            "",
        )
        self.cmb_status.addItem(
            "Đang học",
            "DANG_HOC",
        )
        self.cmb_status.addItem(
            "Hoàn thành",
            "HOAN_THANH",
        )
        self.cmb_status.addItem(
            "Đình chỉ",
            "DINH_CHI",
        )
        self.cmb_status.addItem(
            "Đã hủy",
            "DA_HUY",
        )

        self.txt_search = QLineEdit()
        self.txt_search.setMinimumHeight(32)
        self.txt_search.setPlaceholderText(
            "Tìm theo MSSV hoặc họ tên..."
        )
        self.txt_search.setClearButtonEnabled(True)

        self.btn_reload = create_action_button(
            "Tải lại dữ liệu",
            "reload",
            self._reload_sections,
            self,
        )

        filter_row.addWidget(
            QLabel("Lớp học phần:")
        )
        filter_row.addWidget(
            self.cmb_section,
            3,
        )
        filter_row.addWidget(
            QLabel("Trạng thái:")
        )
        filter_row.addWidget(
            self.cmb_status,
            1,
        )
        filter_row.addWidget(QLabel("Tìm:"))
        filter_row.addWidget(
            self.txt_search,
            2,
        )
        filter_row.addWidget(self.btn_reload)
        layout.addWidget(filter_group)

        self.lbl_section_info = QLabel()
        self.lbl_section_info.setWordWrap(True)
        self.lbl_section_info.setStyleSheet(
            "background:#F7F9FC;"
            "border:1px solid #D8DEE8;"
            "border-radius:6px;"
            "padding:8px;"
            "color:#2F3A4A;"
        )
        layout.addWidget(
            self.lbl_section_info
        )

        self.table = create_data_table(
            [
                "MSSV",
                "Họ và tên",
                "Lớp hành chính",
                "Ngày đăng ký",
                "Ngày kết thúc",
                "Trạng thái đăng ký",
                "Trạng thái sinh viên",
                "Khuôn mặt",
            ],
            stretch_columns=(1, 2),
        )
        layout.addWidget(self.table, 1)

        self.lbl_count = QLabel(
            "Hiển thị: 0 sinh viên"
        )
        self.lbl_count.setStyleSheet(
            "color:#5F6B7A; font-size:12px;"
        )
        layout.addWidget(self.lbl_count)

    def _connect_signals(self):
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(
            self._load_students
        )

        self.cmb_section.currentIndexChanged.connect(
            self._on_section_changed
        )
        self.cmb_status.currentIndexChanged.connect(
            self._load_students
        )
        self.txt_search.textChanged.connect(
            self._schedule_search
        )
        self.txt_search.returnPressed.connect(
            self._search_now
        )

    def _schedule_search(
        self,
        _text="",
    ):
        self._search_timer.start()

    def _search_now(self):
        self._search_timer.stop()
        self._load_students()

    @staticmethod
    def _section_label(
        section: dict,
    ) -> str:
        subject = " - ".join(
            value
            for value in (
                section.get("maMon", ""),
                section.get("tenMon", ""),
            )
            if value
        )

        period = " - ".join(
            value
            for value in (
                section.get("tenHocKy", ""),
                section.get("tenNamHoc", ""),
            )
            if value
        )

        return " | ".join(
            value
            for value in (
                section.get(
                    "maLopHocPhan",
                    "",
                ),
                subject,
                period,
            )
            if value
        )

    def _reload_sections(
        self,
        _checked=False,
    ):
        previous_id = (
            self.cmb_section.currentData()
        )

        try:
            sections = (
                self.service
                .list_assigned_sections()
            )

            sections_by_id = {
                int(
                    section["lopHocPhanId"]
                ): section
                for section in sections
            }
        except Exception:
            logger.exception(
                "Không thể tải lớp học phần "
                "được phân công"
            )
            self._clear_all(
                "Không thể tải danh sách "
                "lớp học phần."
            )
            QMessageBox.critical(
                self,
                "Lỗi dữ liệu",
                "Không thể tải danh sách lớp học "
                "phần. Vui lòng thử lại.",
            )
            return

        self._sections_by_id = (
            sections_by_id
        )

        self.cmb_section.blockSignals(True)

        try:
            self.cmb_section.clear()

            for section in sections:
                self.cmb_section.addItem(
                    self._section_label(
                        section
                    ),
                    int(
                        section[
                            "lopHocPhanId"
                        ]
                    ),
                )

            if sections:
                selected_index = (
                    self.cmb_section.findData(
                        previous_id
                    )
                )
                self.cmb_section.setCurrentIndex(
                    selected_index
                    if selected_index >= 0
                    else 0
                )
            else:
                self.cmb_section.addItem(
                    "Chưa được phân công "
                    "lớp học phần",
                    None,
                )
                self.cmb_section.setCurrentIndex(
                    0
                )
        finally:
            self.cmb_section.blockSignals(
                False
            )

        has_sections = bool(sections)

        self.cmb_section.setEnabled(
            has_sections
        )
        self.cmb_status.setEnabled(
            has_sections
        )
        self.txt_search.setEnabled(
            has_sections
        )

        if has_sections:
            self._on_section_changed()
        else:
            self._clear_table()
            self.lbl_section_info.setText(
                "Bạn chưa được phân công "
                "lớp học phần nào."
            )

    def _clear_all(
        self,
        message: str,
    ):
        self._sections_by_id.clear()

        self.cmb_section.blockSignals(True)

        try:
            self.cmb_section.clear()
            self.cmb_section.addItem(
                message,
                None,
            )
        finally:
            self.cmb_section.blockSignals(
                False
            )

        self.cmb_section.setEnabled(False)
        self.cmb_status.setEnabled(False)
        self.txt_search.setEnabled(False)

        self._clear_table()
        self.lbl_section_info.setText(
            message
        )

    def _current_section(
        self,
    ) -> dict | None:
        section_id = (
            self.cmb_section.currentData()
        )

        try:
            section_id = int(section_id)
        except (TypeError, ValueError):
            return None

        return self._sections_by_id.get(
            section_id
        )

    def _on_section_changed(
        self,
        _index=None,
    ):
        section = self._current_section()

        if section is None:
            self._clear_table()
            self.lbl_section_info.setText(
                "Không có lớp học phần "
                "để hiển thị."
            )
            return

        subject = " - ".join(
            value
            for value in (
                section.get("maMon", ""),
                section.get("tenMon", ""),
            )
            if value
        )

        period = " - ".join(
            value
            for value in (
                section.get(
                    "tenHocKy",
                    "",
                ),
                section.get(
                    "tenNamHoc",
                    "",
                ),
            )
            if value
        )

        course_status = (
            COURSE_STATUS_LABELS.get(
                section.get(
                    "lopHocPhanTrangThai",
                    "",
                ),
                section.get(
                    "lopHocPhanTrangThai",
                    "",
                ),
            )
        )

        current_size = int(
            section.get(
                "siSoHienTai",
                0,
            )
            or 0
        )
        maximum_size = int(
            section.get(
                "siSoToiDa",
                0,
            )
            or 0
        )
        total_registrations = int(
            section.get(
                "tongDangKy",
                0,
            )
            or 0
        )

        self.lbl_section_info.setText(
            f"Lớp: "
            f"{section.get('maLopHocPhan', '')}"
            f" — "
            f"{section.get('tenLopHocPhan', '')}"
            f" | Môn: {subject}"
            f" | Thời gian: {period}"
            f" | Đang học: "
            f"{current_size}/{maximum_size}"
            f" | Tổng đăng ký: "
            f"{total_registrations}"
            f" | Trạng thái: "
            f"{course_status}"
        )

        self._load_students()

    def _load_students(
        self,
        _index=None,
    ):
        section = self._current_section()

        if section is None:
            self._clear_table()
            return

        try:
            rows = (
                self.service
                .list_section_students(
                    section[
                        "lopHocPhanId"
                    ],
                    keyword=(
                        self.txt_search.text()
                    ),
                    registration_status=(
                        self.cmb_status
                        .currentData()
                        or ""
                    ),
                )
            )
        except ValueError as exc:
            logger.warning(
                "Bộ lọc danh sách sinh viên "
                "không hợp lệ: %s",
                exc,
            )
            self._clear_table()
            QMessageBox.warning(
                self,
                "Bộ lọc không hợp lệ",
                str(exc),
            )
            return
        except Exception:
            logger.exception(
                "Không thể tải sinh viên "
                "lớp học phần id=%s",
                section.get(
                    "lopHocPhanId"
                ),
            )
            self._clear_table()
            QMessageBox.critical(
                self,
                "Lỗi dữ liệu",
                "Không thể tải danh sách "
                "sinh viên. Vui lòng thử lại.",
            )
            return

        self._fill_table(rows)

    def _fill_table(
        self,
        rows: list[dict],
    ):
        sorting_enabled = (
            self.table.isSortingEnabled()
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_index, student in enumerate(
            rows
        ):
            registration_status = (
                student.get(
                    "dangKyTrangThai",
                    "",
                )
            )

            values = (
                student.get("mssv", ""),
                student.get("hoTen", ""),
                student.get("tenLop", ""),
                self._display_date(
                    student.get(
                        "ngayDangKy",
                        "",
                    )
                ),
                self._display_date(
                    student.get(
                        "ngayKetThuc",
                        "",
                    )
                ),
                REGISTRATION_STATUS_LABELS.get(
                    registration_status,
                    registration_status,
                ),
                STUDENT_STATUS_LABELS.get(
                    student.get(
                        "sinhVienTrangThai",
                        "",
                    ),
                    student.get(
                        "sinhVienTrangThai",
                        "",
                    ),
                ),
                (
                    "Có mẫu"
                    if student.get(
                        "coKhuonMat"
                    )
                    else "Chưa có mẫu"
                ),
            )

            background = QColor(
                REGISTRATION_ROW_COLORS.get(
                    registration_status,
                    "#FFFFFF",
                )
            )

            for column, value in enumerate(
                values
            ):
                item = QTableWidgetItem(
                    str(value)
                )
                item.setBackground(
                    background
                )

                if column in {1, 2}:
                    item.setTextAlignment(
                        Qt.AlignLeft
                        | Qt.AlignVCenter
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignCenter
                    )

                if column == 7:
                    item.setToolTip(
                        "Chỉ phản ánh việc có "
                        "ít nhất một mẫu khuôn mặt "
                        "đang hoạt động trong "
                        "cơ sở dữ liệu."
                    )

                self.table.setItem(
                    row_index,
                    column,
                    item,
                )

        self.table.setSortingEnabled(
            sorting_enabled
        )
        self.lbl_count.setText(
            f"Hiển thị: {len(rows)} sinh viên"
        )

    def _clear_table(self):
        sorting_enabled = (
            self.table.isSortingEnabled()
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(
            sorting_enabled
        )
        self.lbl_count.setText(
            "Hiển thị: 0 sinh viên"
        )

    @staticmethod
    def _display_date(
        value,
    ) -> str:
        value = str(value or "")

        if not value:
            return ""

        parsed = QDate.fromString(
            value,
            "yyyy-MM-dd",
        )

        if not parsed.isValid():
            return value

        return parsed.toString(
            "dd/MM/yyyy"
        )

    def showEvent(self, event):
        super().showEvent(event)

        # Lần đầu đã tải trong __init__.
        # Những lần quay lại tab sẽ kiểm tra
        # lại việc phân công và quyền truy cập.
        if self._has_been_shown:
            self._reload_sections()
        else:
            self._has_been_shown = True