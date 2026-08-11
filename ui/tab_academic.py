from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.academic_service import (
    DangKyHocPhanData,
    HocKyData,
    LopHocPhanData,
    MonHocData,
    NamHocData,
)
from ui.ui_helpers import (
    add_form_field,
    create_action_bar,
    create_data_table,
    create_two_column_form,
)


ACADEMIC_STATUS_LABELS = {
    "SAP_DIEN_RA": "Sắp diễn ra",
    "DANG_DIEN_RA": "Đang diễn ra",
    "DA_KET_THUC": "Đã kết thúc",
}

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


def _table_item(
    value,
) -> QTableWidgetItem:
    if value is None:
        value = ""

    item = QTableWidgetItem(str(value))
    item.setTextAlignment(
        Qt.AlignLeft | Qt.AlignVCenter
    )
    return item


def _set_combo_data(
    combo: QComboBox,
    value,
) -> bool:
    index = combo.findData(value)

    if index < 0 and isinstance(value, str):
        for position in range(combo.count()):
            current = combo.itemData(position)
            if (
                isinstance(current, str)
                and current.casefold() == value.casefold()
            ):
                index = position
                break

    if index >= 0:
        combo.setCurrentIndex(index)
        return True

    return False


def _set_date(
    editor: QDateEdit,
    iso_date: str,
):
    value = QDate.fromString(
        iso_date or "",
        "yyyy-MM-dd",
    )

    if value.isValid():
        editor.setDate(value)


def _iso_date(
    editor: QDateEdit,
) -> str:
    return editor.date().toString("yyyy-MM-dd")


def _confirm_delete(
    parent,
    message: str,
) -> bool:
    reply = QMessageBox.question(
        parent,
        "Xác nhận xóa",
        message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return reply == QMessageBox.Yes


def _show_result(
    parent,
    result: tuple[bool, str],
) -> bool:
    ok, message = result

    if ok:
        QMessageBox.information(
            parent,
            "Thành công",
            message,
        )
    else:
        QMessageBox.warning(
            parent,
            "Không thể thực hiện",
            message,
        )

    return ok


def _add_academic_statuses(
    combo: QComboBox,
):
    for value, label in ACADEMIC_STATUS_LABELS.items():
        combo.addItem(label, value)


def _add_course_statuses(
    combo: QComboBox,
):
    for value, label in COURSE_STATUS_LABELS.items():
        combo.addItem(label, value)


def _add_registration_statuses(
    combo: QComboBox,
):
    for value, label in REGISTRATION_STATUS_LABELS.items():
        combo.addItem(label, value)


class SchoolYearPanel(QWidget):
    def __init__(
        self,
        academic_service,
        parent=None,
    ):
        super().__init__(parent)

        self.service = academic_service
        self.selected_id = 0

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QGroupBox("Thông tin năm học")
        form = create_two_column_form(group)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText(
            "Ví dụ: 2026–2027"
        )

        self.date_start = QDateEdit()
        self.date_end = QDateEdit()

        for editor in (
            self.date_start,
            self.date_end,
        ):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")

        today = QDate.currentDate()
        self.date_start.setDate(
            QDate(today.year(), 1, 1)
        )
        self.date_end.setDate(
            QDate(today.year(), 12, 31)
        )

        self.cmb_status = QComboBox()
        _add_academic_statuses(self.cmb_status)

        add_form_field(form, 0, 0, "Tên năm học *", self.txt_name)
        add_form_field(form, 0, 1, "Trạng thái", self.cmb_status)
        add_form_field(form, 1, 0, "Ngày bắt đầu *", self.date_start)
        add_form_field(form, 1, 1, "Ngày kết thúc *", self.date_end)

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Thêm", "create", self.create),
                ("update", "Sửa", "edit", self.update),
                ("delete", "Xóa", "delete", self.delete),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        self.table = create_data_table(
            [
                "ID",
                "Năm học",
                "Bắt đầu",
                "Kết thúc",
                "Trạng thái",
                "Số học kỳ",
            ],
            stretch_columns=(1, 4),
            hidden_columns=(0,),
        )
        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

    def refresh(self):
        rows = self.service.list_school_years()

        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["tenNamHoc"],
                row["ngayBatDau"],
                row["ngayKetThuc"],
                ACADEMIC_STATUS_LABELS.get(
                    row["trangThai"],
                    row["trangThai"],
                ),
                row.get("soHocKy", 0),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _table_item(value),
                )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        item = self.table.item(row, 0)
        if not item:
            return

        self.selected_id = int(item.text())

        selected = next(
            (
                value
                for value in self.service.list_school_years()
                if value["id"] == self.selected_id
            ),
            None,
        )
        if not selected:
            return

        self.txt_name.setText(
            selected["tenNamHoc"]
        )
        _set_date(
            self.date_start,
            selected["ngayBatDau"],
        )
        _set_date(
            self.date_end,
            selected["ngayKetThuc"],
        )
        _set_combo_data(
            self.cmb_status,
            selected["trangThai"],
        )

    def _read_form(self) -> NamHocData:
        return NamHocData(
            id=self.selected_id,
            tenNamHoc=self.txt_name.text(),
            ngayBatDau=_iso_date(self.date_start),
            ngayKetThuc=_iso_date(self.date_end),
            trangThai=self.cmb_status.currentData(),
        )

    def create(self):
        data = self._read_form()
        data.id = 0

        if _show_result(
            self,
            self.service.create_school_year(data),
        ):
            self.clear_form()
            self.refresh()

    def update(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn năm học cần cập nhật.",
            )
            return

        if _show_result(
            self,
            self.service.update_school_year(
                self._read_form()
            ),
        ):
            self.refresh()

    def delete(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn năm học cần xóa.",
            )
            return

        if not _confirm_delete(
            self,
            "Bạn có chắc muốn xóa năm học này?",
        ):
            return

        if _show_result(
            self,
            self.service.delete_school_year(
                self.selected_id
            ),
        ):
            self.clear_form()
            self.refresh()

    def clear_form(self):
        self.selected_id = 0
        self.table.clearSelection()
        self.txt_name.clear()
        self.cmb_status.setCurrentIndex(0)


class SemesterPanel(QWidget):
    def __init__(
        self,
        academic_service,
        parent=None,
    ):
        super().__init__(parent)

        self.service = academic_service
        self.selected_id = 0

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QGroupBox("Thông tin học kỳ")
        form = create_two_column_form(group)

        self.cmb_school_year = QComboBox()
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText(
            "Ví dụ: Học kỳ 1"
        )

        self.date_start = QDateEdit()
        self.date_end = QDateEdit()

        for editor in (
            self.date_start,
            self.date_end,
        ):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")

        self.date_start.setDate(QDate.currentDate())
        self.date_end.setDate(
            QDate.currentDate().addMonths(4)
        )

        self.cmb_status = QComboBox()
        _add_academic_statuses(self.cmb_status)

        add_form_field(form, 0, 0, "Năm học *", self.cmb_school_year)
        add_form_field(form, 0, 1, "Tên học kỳ *", self.txt_name)
        add_form_field(form, 1, 0, "Ngày bắt đầu *", self.date_start)
        add_form_field(form, 1, 1, "Ngày kết thúc *", self.date_end)
        add_form_field(form, 2, 0, "Trạng thái", self.cmb_status)

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Thêm", "create", self.create),
                ("update", "Sửa", "edit", self.update),
                ("delete", "Xóa", "delete", self.delete),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        self.table = create_data_table(
            [
                "ID",
                "Năm học",
                "Học kỳ",
                "Bắt đầu",
                "Kết thúc",
                "Trạng thái",
                "Số lớp học phần",
            ],
            stretch_columns=(1, 2, 5),
            hidden_columns=(0,),
        )
        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

    def _load_school_years(self):
        current = self.cmb_school_year.currentData()

        self.cmb_school_year.blockSignals(True)
        self.cmb_school_year.clear()

        for row in self.service.list_school_years():
            self.cmb_school_year.addItem(
                row["tenNamHoc"],
                row["id"],
            )

        if current is not None:
            _set_combo_data(
                self.cmb_school_year,
                current,
            )

        self.cmb_school_year.blockSignals(False)

    def refresh(self):
        self._load_school_years()
        rows = self.service.list_semesters()

        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["tenNamHoc"],
                row["tenHocKy"],
                row["ngayBatDau"],
                row["ngayKetThuc"],
                ACADEMIC_STATUS_LABELS.get(
                    row["trangThai"],
                    row["trangThai"],
                ),
                row.get("soLopHocPhan", 0),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _table_item(value),
                )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        id_item = self.table.item(row, 0)
        if not id_item:
            return

        self.selected_id = int(id_item.text())

        selected = next(
            (
                value
                for value in self.service.list_semesters()
                if value["id"] == self.selected_id
            ),
            None,
        )
        if not selected:
            return

        _set_combo_data(
            self.cmb_school_year,
            selected["namHocId"],
        )
        self.txt_name.setText(selected["tenHocKy"])
        _set_date(
            self.date_start,
            selected["ngayBatDau"],
        )
        _set_date(
            self.date_end,
            selected["ngayKetThuc"],
        )
        _set_combo_data(
            self.cmb_status,
            selected["trangThai"],
        )

    def _read_form(self) -> HocKyData:
        return HocKyData(
            id=self.selected_id,
            namHocId=self.cmb_school_year.currentData() or 0,
            tenHocKy=self.txt_name.text(),
            ngayBatDau=_iso_date(self.date_start),
            ngayKetThuc=_iso_date(self.date_end),
            trangThai=self.cmb_status.currentData(),
        )

    def create(self):
        data = self._read_form()
        data.id = 0

        if _show_result(
            self,
            self.service.create_semester(data),
        ):
            self.clear_form()
            self.refresh()

    def update(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn học kỳ cần cập nhật.",
            )
            return

        if _show_result(
            self,
            self.service.update_semester(
                self._read_form()
            ),
        ):
            self.refresh()

    def delete(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn học kỳ cần xóa.",
            )
            return

        if not _confirm_delete(
            self,
            "Bạn có chắc muốn xóa học kỳ này?",
        ):
            return

        if _show_result(
            self,
            self.service.delete_semester(
                self.selected_id
            ),
        ):
            self.clear_form()
            self.refresh()

    def clear_form(self):
        self.selected_id = 0
        self.table.clearSelection()
        self.txt_name.clear()
        self.cmb_status.setCurrentIndex(0)


class SubjectPanel(QWidget):
    def __init__(
        self,
        academic_service,
        parent=None,
    ):
        super().__init__(parent)

        self.service = academic_service
        self.old_subject_code = ""

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QGroupBox("Thông tin môn học")
        form = create_two_column_form(group)

        self.txt_code = QLineEdit()
        self.txt_name = QLineEdit()

        self.spin_periods = QSpinBox()
        self.spin_periods.setRange(1, 300)
        self.spin_periods.setValue(45)

        self.spin_min_rate = QSpinBox()
        self.spin_min_rate.setRange(0, 100)
        self.spin_min_rate.setSuffix(" %")
        self.spin_min_rate.setValue(75)

        add_form_field(form, 0, 0, "Mã môn *", self.txt_code)
        add_form_field(form, 0, 1, "Tên môn *", self.txt_name)
        add_form_field(form, 1, 0, "Số tiết", self.spin_periods)
        add_form_field(
            form,
            1,
            1,
            "Tỷ lệ chuyên cần tối thiểu",
            self.spin_min_rate,
        )

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Thêm", "create", self.create),
                ("update", "Sửa", "edit", self.update),
                ("delete", "Xóa", "delete", self.delete),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        self.table = create_data_table(
            [
                "Mã môn",
                "Tên môn",
                "Số tiết",
                "Chuyên cần tối thiểu",
                "Số lớp học phần",
            ],
            stretch_columns=(1,),
        )
        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

    def refresh(self):
        rows = self.service.list_subjects()
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["maMon"],
                row["tenMon"],
                row["soTiet"],
                f"{row['tiLeToiThieu']}%",
                row.get("soLopHocPhan", 0),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _table_item(value),
                )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        code_item = self.table.item(row, 0)
        if not code_item:
            return

        self.old_subject_code = code_item.text()

        selected = next(
            (
                value
                for value in self.service.list_subjects()
                if value["maMon"] == self.old_subject_code
            ),
            None,
        )
        if not selected:
            return

        self.txt_code.setText(selected["maMon"])
        self.txt_name.setText(selected["tenMon"])
        self.spin_periods.setValue(
            int(selected["soTiet"])
        )
        self.spin_min_rate.setValue(
            int(selected["tiLeToiThieu"])
        )

    def _read_form(self) -> MonHocData:
        return MonHocData(
            maMon=self.txt_code.text(),
            tenMon=self.txt_name.text(),
            soTiet=self.spin_periods.value(),
            tiLeToiThieu=self.spin_min_rate.value(),
        )

    def create(self):
        if _show_result(
            self,
            self.service.create_subject(
                self._read_form()
            ),
        ):
            self.clear_form()
            self.refresh()

    def update(self):
        if not self.old_subject_code:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn môn học cần cập nhật.",
            )
            return

        if _show_result(
            self,
            self.service.update_subject(
                self.old_subject_code,
                self._read_form(),
            ),
        ):
            self.clear_form()
            self.refresh()

    def delete(self):
        if not self.old_subject_code:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn môn học cần xóa.",
            )
            return

        if not _confirm_delete(
            self,
            f"Bạn có chắc muốn xóa môn "
            f"'{self.old_subject_code}'?",
        ):
            return

        if _show_result(
            self,
            self.service.delete_subject(
                self.old_subject_code
            ),
        ):
            self.clear_form()
            self.refresh()

    def clear_form(self):
        self.old_subject_code = ""
        self.table.clearSelection()
        self.txt_code.clear()
        self.txt_name.clear()
        self.spin_periods.setValue(45)
        self.spin_min_rate.setValue(75)


class CourseSectionPanel(QWidget):
    def __init__(
        self,
        academic_service,
        auth_service,
        current_user: dict,
        parent=None,
    ):
        super().__init__(parent)

        self.service = academic_service
        self.auth_service = auth_service
        self.current_user = current_user or {}
        self.selected_id = 0

        self._build_ui()
        self.refresh()

    @property
    def actor_username(self) -> str:
        return (
            self.current_user.get("username", "")
            or ""
        ).strip()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QGroupBox("Thông tin lớp học phần")
        form = create_two_column_form(group)

        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText(
            "Ví dụ: AI_2026_01"
        )

        self.txt_name = QLineEdit()
        self.txt_group = QLineEdit("01")

        self.cmb_subject = QComboBox()
        self.cmb_semester = QComboBox()
        self.cmb_lecturer = QComboBox()

        self.spin_capacity = QSpinBox()
        self.spin_capacity.setRange(1, 1000)
        self.spin_capacity.setValue(60)

        self.cmb_status = QComboBox()
        _add_course_statuses(self.cmb_status)

        add_form_field(form, 0, 0, "Mã lớp học phần *", self.txt_code)
        add_form_field(form, 0, 1, "Tên lớp học phần *", self.txt_name)
        add_form_field(form, 1, 0, "Môn học *", self.cmb_subject)
        add_form_field(form, 1, 1, "Học kỳ *", self.cmb_semester)
        group_label = add_form_field(form,2,0,"Nhóm",self.txt_group)
        group_label.hide()
        self.txt_group.hide()
        add_form_field(form, 2, 1, "Sĩ số tối đa", self.spin_capacity)
        add_form_field(form, 3, 0, "Giảng viên", self.cmb_lecturer)
        add_form_field(form, 3, 1, "Trạng thái", self.cmb_status)

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Thêm", "create", self.create),
                ("update", "Sửa", "edit", self.update),
                ("delete", "Xóa", "delete", self.delete),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        self.table = create_data_table(
            [
                "ID",
                "Mã lớp học phần",
                "Tên lớp học phần",
                "Môn học",
                "Học kỳ",
                "Năm học",
                "Nhóm",
                "Sĩ số",
                "Tối đa",
                "Giảng viên",
                "Trạng thái",
            ],
            stretch_columns=(2, 3, 9),
            hidden_columns=(0,6),
        )
        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

    def _load_options(self):
        old_subject = self.cmb_subject.currentData()
        old_semester = self.cmb_semester.currentData()
        old_lecturer = self.cmb_lecturer.currentData()

        self.cmb_subject.clear()
        for subject in self.service.list_subjects():
            self.cmb_subject.addItem(
                f"{subject['maMon']} — {subject['tenMon']}",
                subject["maMon"],
            )

        self.cmb_semester.clear()
        for semester in self.service.list_semesters():
            self.cmb_semester.addItem(
                (
                    f"{semester['tenHocKy']} — "
                    f"{semester['tenNamHoc']}"
                ),
                semester["id"],
            )

        self.cmb_lecturer.clear()
        self.cmb_lecturer.addItem(
            "-- Chưa phân công --",
            "",
        )

        lecturers = self.auth_service.get_lecturer_options(
            self.actor_username
        )

        for lecturer in lecturers:
            username = lecturer.get("username", "")
            name = lecturer.get("hoTen", username)
            lecturer_code = lecturer.get("maGV", "")

            text = (
                f"{lecturer_code} — {name}"
                if lecturer_code
                else f"{name} ({username})"
            )
            self.cmb_lecturer.addItem(text, username)

        if old_subject:
            _set_combo_data(
                self.cmb_subject,
                old_subject,
            )

        if old_semester:
            _set_combo_data(
                self.cmb_semester,
                old_semester,
            )

        _set_combo_data(
            self.cmb_lecturer,
            old_lecturer or "",
        )

    def refresh(self):
        self._load_options()
        rows = self.service.list_course_sections()

        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            current_size = int(
                row.get("siSoHienTai", 0)
            )

            values = [
                row["id"],
                row["maLopHocPhan"],
                row["tenLopHocPhan"],
                f"{row['maMon']} — {row['tenMon']}",
                row["tenHocKy"],
                row["tenNamHoc"],
                row["nhom"],
                current_size,
                row["siSoToiDa"],
                (
                    row.get("giangVienHoTen")
                    or "Chưa phân công"
                ),
                COURSE_STATUS_LABELS.get(
                    row["trangThai"],
                    row["trangThai"],
                ),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _table_item(value),
                )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        id_item = self.table.item(row, 0)
        if not id_item:
            return

        self.selected_id = int(id_item.text())
        selected = self.service.get_course_section(
            self.selected_id
        )

        if not selected:
            return

        self.txt_code.setText(
            selected["maLopHocPhan"]
        )
        self.txt_name.setText(
            selected["tenLopHocPhan"]
        )
        self.txt_group.setText(selected["nhom"])

        self.spin_capacity.setValue(
            int(selected["siSoToiDa"])
        )

        _set_combo_data(
            self.cmb_subject,
            selected["maMon"],
        )
        _set_combo_data(
            self.cmb_semester,
            selected["hocKyId"],
        )
        _set_combo_data(
            self.cmb_lecturer,
            selected.get("giangVienUsername") or "",
        )
        _set_combo_data(
            self.cmb_status,
            selected["trangThai"],
        )

    def _read_form(self) -> LopHocPhanData:
        return LopHocPhanData(
            id=self.selected_id,
            maLopHocPhan=self.txt_code.text(),
            maMon=self.cmb_subject.currentData() or "",
            hocKyId=self.cmb_semester.currentData() or 0,
            tenLopHocPhan=self.txt_name.text(),
            nhom=self.txt_group.text(),
            siSoToiDa=self.spin_capacity.value(),
            giangVienUsername=(
                self.cmb_lecturer.currentData() or ""
            ),
            trangThai=self.cmb_status.currentData(),
        )

    def create(self):
        data = self._read_form()
        data.id = 0

        if _show_result(
            self,
            self.service.create_course_section(data),
        ):
            self.clear_form()
            self.refresh()

    def update(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn lớp học phần cần cập nhật.",
            )
            return

        if _show_result(
            self,
            self.service.update_course_section(
                self._read_form()
            ),
        ):
            self.refresh()

    def delete(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn lớp học phần cần xóa.",
            )
            return

        if not _confirm_delete(
            self,
            "Bạn có chắc muốn xóa lớp học phần này?\n\n"
            "Các đăng ký chưa có lịch sử có thể bị xóa theo.",
        ):
            return

        if _show_result(
            self,
            self.service.delete_course_section(
                self.selected_id
            ),
        ):
            self.clear_form()
            self.refresh()

    def clear_form(self):
        self.selected_id = 0
        self.table.clearSelection()
        self.txt_code.clear()
        self.txt_name.clear()
        self.txt_group.setText("01")
        self.spin_capacity.setValue(60)
        self.cmb_status.setCurrentIndex(0)
        _set_combo_data(self.cmb_lecturer, "")


class RegistrationPanel(QWidget):
    def __init__(
        self,
        academic_service,
        parent=None,
    ):
        super().__init__(parent)

        self.service = academic_service
        self.selected_id = 0
        self.loading = False

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        group = QGroupBox("Đăng ký sinh viên vào lớp học phần")
        form = create_two_column_form(group)

        self.cmb_section = QComboBox()
        self.cmb_student = QComboBox()

        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("dd/MM/yyyy")
        self.date_start.setDate(QDate.currentDate())

        self.cmb_status = QComboBox()
        _add_registration_statuses(self.cmb_status)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("dd/MM/yyyy")
        self.date_end.setDate(QDate.currentDate())

        add_form_field(form, 0, 0, "Lớp học phần *", self.cmb_section)
        add_form_field(form, 0, 1, "Sinh viên *", self.cmb_student)
        add_form_field(form, 1, 0, "Ngày đăng ký *", self.date_start)
        add_form_field(form, 1, 1, "Trạng thái", self.cmb_status)
        add_form_field(form, 2, 0, "Ngày kết thúc", self.date_end)

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Đăng ký", "create", self.create),
                ("update", "Sửa đăng ký", "edit", self.update),
                ("delete", "Xóa", "delete", self.delete),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        note = QLabel(
            "Một sinh viên chỉ có một bản ghi đăng ký trong mỗi "
            "lớp học phần. "
            
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color:#666;"
            "padding:4px 0;"
        )
        root.addWidget(note)

        self.table = create_data_table(
            [
                "ID",
                "MSSV",
                "Họ tên",
                "Lớp hành chính",
                "Mã lớp học phần",
                "Môn học",
                "Ngày đăng ký",
                "Ngày kết thúc",
                "Trạng thái",
            ],
            stretch_columns=(2, 3, 5),
            hidden_columns=(0,),
        )
        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

        self.cmb_section.currentIndexChanged.connect(
            self.refresh_table
        )
        self.cmb_status.currentIndexChanged.connect(
            self._sync_end_date_state
        )
        self._sync_end_date_state()
    def _load_options(self):
        old_section = self.cmb_section.currentData()
        old_student = self.cmb_student.currentData()

        self.loading = True

        self.cmb_section.clear()
        sections = self.service.list_course_sections(
            include_cancelled=True
        )

        for section in sections:
            self.cmb_section.addItem(
                (
                    f"{section['maLopHocPhan']} — "
                    f"{section['tenMon']} — "
                    f"{section['tenHocKy']} "
                    f"{section['tenNamHoc']}"
                ),
                section["id"],
            )

        self.cmb_student.clear()

        for student in self.service.list_students():
            self.cmb_student.addItem(
                (
                    f"{student['mssv']} — "
                    f"{student['hoTen']} — "
                    f"{student['maLop']}"
                ),
                student["mssv"],
            )

        if old_section is not None:
            _set_combo_data(
                self.cmb_section,
                old_section,
            )

        if old_student:
            _set_combo_data(
                self.cmb_student,
                old_student,
            )

        self.loading = False

    def refresh(self):
        self._load_options()
        self.refresh_table()

    def refresh_table(self):
        if self.loading:
            return

        section_id = self.cmb_section.currentData() or 0
        rows = self.service.list_registrations(
            section_id
        )

        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["mssv"],
                row["hoTen"],
                (
                    f"{row['maLop']} — "
                    f"{row['tenLop']}"
                ),
                row["maLopHocPhan"],
                f"{row['maMon']} — {row['tenMon']}",
                row["ngayDangKy"],
                row["ngayKetThuc"],
                REGISTRATION_STATUS_LABELS.get(
                    row["trangThai"],
                    row["trangThai"],
                ),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _table_item(value),
                )

    def _sync_end_date_state(self, _index=None):
        status = self.cmb_status.currentData()
        has_ended = status in {
            "DA_HUY",
            "HOAN_THANH",
            "DINH_CHI",
        }

        self.date_end.setEnabled(has_ended)

        if not has_ended:
            self.date_end.setToolTip(
                "Đăng ký đang học không có ngày kết thúc."
            )
        else:
            self.date_end.setToolTip(
                "Chọn ngày sinh viên kết thúc đăng ký học phần."
            )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        id_item = self.table.item(row, 0)
        if not id_item:
            return

        self.selected_id = int(id_item.text())

        selected = next(
            (
                registration
                for registration
                in self.service.list_registrations()
                if registration["id"] == self.selected_id
            ),
            None,
        )
        if not selected:
            return

        _set_combo_data(
            self.cmb_section,
            selected["lopHocPhanId"],
        )
        _set_combo_data(
            self.cmb_student,
            selected["mssv"],
        )
        _set_date(
            self.date_start,
            selected["ngayDangKy"],
        )
        _set_combo_data(
            self.cmb_status,
            selected["trangThai"],
        )

        end_date = selected["ngayKetThuc"] or ""

        if end_date:
            _set_date(self.date_end, end_date)
        else:
            self.date_end.setDate(QDate.currentDate())

        self._sync_end_date_state()

    def _read_form(self) -> DangKyHocPhanData:
        status = self.cmb_status.currentData()
        end_date = (
            ""
            if status == "DANG_HOC"
            else _iso_date(self.date_end)
        )

        return DangKyHocPhanData(
            id=self.selected_id,
            mssv=self.cmb_student.currentData() or "",
            lopHocPhanId=(
                self.cmb_section.currentData() or 0
            ),
            ngayDangKy=_iso_date(self.date_start),
            ngayKetThuc=end_date,
            trangThai=status,
        )

    def create(self):
        data = self._read_form()
        data.id = 0

        if _show_result(
            self,
            self.service.create_registration(data),
        ):
            self.clear_form()
            self.refresh()

    def update(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn đăng ký cần cập nhật.",
            )
            return

        if _show_result(
            self,
            self.service.update_registration(
                self._read_form()
            ),
        ):
            self.clear_form()
            self.refresh()

    def delete(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn dữ liệu",
                "Vui lòng chọn đăng ký cần xóa.",
            )
            return

        if not _confirm_delete(
            self,
            "Bạn có chắc muốn xóa đăng ký này?\n\n"
            "Đăng ký đã có lịch sử điểm danh sẽ không thể xóa.",
        ):
            return

        if _show_result(
            self,
            self.service.delete_registration(
                self.selected_id
            ),
        ):
            self.clear_form()
            self.refresh()

    def clear_form(self):
        self.selected_id = 0
        self.table.clearSelection()
        self.date_start.setDate(QDate.currentDate())
        self.date_end.setDate(QDate.currentDate())
        self.cmb_status.setCurrentIndex(0)
        self._sync_end_date_state()


class TabAcademic(QWidget):
    """
    Tab quản lý học vụ:

    - Môn học
    - Năm học
    - Học kỳ
    - Lớp học phần
    - Đăng ký học phần
    """

    def __init__(
        self,
        academic_service,
        auth_service,
        current_user: dict,
        parent=None,
    ):
        super().__init__(parent)

        self.tabs = QTabWidget()

        self.subject_panel = SubjectPanel(
            academic_service
        )
        self.school_year_panel = SchoolYearPanel(
            academic_service
        )
        self.semester_panel = SemesterPanel(
            academic_service
        )
        self.section_panel = CourseSectionPanel(
            academic_service,
            auth_service,
            current_user,
        )
        self.registration_panel = RegistrationPanel(
            academic_service
        )

        self.panels = [
            self.subject_panel,
            self.school_year_panel,
            self.semester_panel,
            self.section_panel,
            self.registration_panel,
        ]

        self.tabs.addTab(
            self.subject_panel,
            "Môn học",
        )
        self.tabs.addTab(
            self.school_year_panel,
            "Năm học",
        )
        self.tabs.addTab(
            self.semester_panel,
            "Học kỳ",
        )
        self.tabs.addTab(
            self.section_panel,
            "Lớp học phần",
        )
        self.tabs.addTab(
            self.registration_panel,
            "Đăng ký học phần",
        )

        self.tabs.currentChanged.connect(
            self._refresh_current_panel
        )

        root = QVBoxLayout(self)

        title = QLabel("QUẢN LÝ HỌC VỤ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size:18px;"
            "font-weight:700;"
            "color:#2F2A7E;"
            "padding:4px;"
        )

        root.addWidget(title)
        root.addWidget(self.tabs, 1)

    def _refresh_current_panel(
        self,
        index: int,
    ):
        if 0 <= index < len(self.panels):
            self.panels[index].refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_current_panel(
            self.tabs.currentIndex()
        )