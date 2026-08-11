from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.course_session_service import (
    CaHoc,
    KHUNG_GIO,
)
from ui.ui_helpers import (
    add_form_field,
    create_action_bar,
    create_data_table,
    create_two_column_form,
)


STATUS_LABELS = {
    "ChuaMo": "Chưa mở",
    "DangDienRa": "Đang diễn ra",
    "DaKetThuc": "Đã kết thúc",
}


def _item(value) -> QTableWidgetItem:
    return QTableWidgetItem(
        "" if value is None else str(value)
    )


def _set_combo_data(
    combo: QComboBox,
    value,
) -> bool:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
        return True
    return False


class TabCourseSessions(QWidget):
    def __init__(
        self,
        session_service,
        academic_service,
        current_user: dict,
        parent=None,
    ):
        super().__init__(parent)

        self.session_service = session_service
        self.academic_service = academic_service
        self.current_user = current_user or {}
        self.selected_id = 0
        self.loading = False

        self._build_ui()
        self.refresh()

    @property
    def username(self) -> str:
        return (
            self.current_user.get("username", "")
            or ""
        ).strip()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("QUẢN LÝ CA HỌC THEO LỚP HỌC PHẦN")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size:18px;"
            "font-weight:700;"
            "color:#2F2A7E;"
            "padding:4px;"
        )
        root.addWidget(title)

        group = QGroupBox("Thông tin ca học")
        form = create_two_column_form(group)

        self.cmb_section = QComboBox()

        self.txt_session_name = QLineEdit()
        self.txt_session_name.setPlaceholderText(
            "Ví dụ: Ca 1"
        )

        self.date_session = QDateEdit()
        self.date_session.setCalendarPopup(True)
        self.date_session.setDisplayFormat("dd/MM/yyyy")
        self.date_session.setDate(QDate.currentDate())

        self.cmb_time = QComboBox()

        for (
            display_text,
            session_name,
            start_time,
            end_time,
        ) in KHUNG_GIO:
            self.cmb_time.addItem(
                display_text,
                (
                    session_name,
                    start_time,
                    end_time,
                ),
            )

        self.txt_room = QLineEdit()
        self.txt_room.setPlaceholderText(
            "Ví dụ: P101"
        )

        add_form_field(form, 0, 0, "Lớp học phần *", self.cmb_section)
        add_form_field(form, 0, 1, "Tên ca *", self.txt_session_name)
        add_form_field(form, 1, 0, "Ngày học *", self.date_session)
        add_form_field(form, 1, 1, "Khung giờ *", self.cmb_time)
        add_form_field(form, 2, 0, "Phòng học *", self.txt_room)

        root.addWidget(group)

        action_bar, _ = create_action_bar(
            [
                ("create", "Thêm ca", "create", self.create_session),
                ("update", "Sửa ca", "edit", self.update_session),
                ("delete", "Xóa ca", "delete", self.delete_session),
                ("open", "Mở điểm danh", "reload", self.open_session),
                ("finish", "Kết thúc ca", "special", self.finish_session),
                ("reset", "Đặt lại", "reset", self.clear_form),
                ("reload", "Tải lại dữ liệu", "reload", self.refresh),
            ]
        )
        root.addLayout(action_bar)

        note = QLabel(
            "Hệ thống sẽ chặn trùng giờ của lớp học phần, phòng học "
            "và giảng viên. Ca đã từng mở điểm danh sẽ không được "
            "xóa để bảo toàn lịch sử vắng mặt."
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
                "Mã lớp học phần",
                "Môn học",
                "Học kỳ",
                "Tên ca",
                "Ngày học",
                "Thời gian",
                "Phòng",
                "Trạng thái",
            ],
            stretch_columns=(2, 3, 4),
            hidden_columns=(0,),
        )

        self.table.itemSelectionChanged.connect(
            self._on_selected
        )

        root.addWidget(self.table, 1)

        self.cmb_time.currentIndexChanged.connect(
            self._on_time_changed
        )

    def _load_sections(self):
        current_section = self.cmb_section.currentData()

        self.loading = True
        self.cmb_section.clear()

        sections = self.academic_service.list_course_sections(
            include_cancelled=False
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

        if current_section is not None:
            _set_combo_data(
                self.cmb_section,
                current_section,
            )

        self.loading = False

    def refresh(self):
        self._load_sections()

        rows = self.session_service.get_all_ca()
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            time_text = (
                f"{row['gioBatDau']}–{row['gioKetThuc']}"
            )

            values = [
                row["id"],
                row["maLop"],
                f"{row['maMon']} — {row['tenMon']}",
                (
                    f"{row['tenHocKy']} — "
                    f"{row['tenNamHoc']}"
                ),
                row["tenCa"],
                row["ngayHoc"],
                time_text,
                row["phongHoc"],
                STATUS_LABELS.get(
                    row["trangThai"],
                    row["trangThai"],
                ),
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column,
                    _item(value),
                )

    def _on_time_changed(self):
        value = self.cmb_time.currentData()
        if not value:
            return

        session_name = value[0]
        current_name = self.txt_session_name.text().strip()

        if (
            not current_name
            or current_name.startswith("Ca ")
        ):
            self.txt_session_name.setText(
                session_name
            )

    def _on_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return

        id_item = self.table.item(row, 0)
        if not id_item:
            return

        self.selected_id = int(id_item.text())
        session = self.session_service.get_ca_by_id(
            self.selected_id
        )

        if not session:
            return

        _set_combo_data(
            self.cmb_section,
            session["lopHocPhanId"],
        )

        self.txt_session_name.setText(
            session["tenCa"]
        )
        self.txt_room.setText(
            session["phongHoc"]
        )

        session_date = QDate.fromString(
            session["ngayHoc"],
            "yyyy-MM-dd",
        )
        if session_date.isValid():
            self.date_session.setDate(session_date)

        for index in range(self.cmb_time.count()):
            value = self.cmb_time.itemData(index)
            if not value:
                continue

            _, start_time, end_time = value

            if (
                start_time == session["gioBatDau"]
                and end_time == session["gioKetThuc"]
            ):
                self.cmb_time.setCurrentIndex(index)
                break

    def _read_form(self) -> CaHoc:
        time_data = self.cmb_time.currentData()

        if time_data:
            _, start_time, end_time = time_data
        else:
            start_time = ""
            end_time = ""

        return CaHoc(
            id=self.selected_id,
            lopHocPhanId=(
                self.cmb_section.currentData() or 0
            ),
            tenCa=self.txt_session_name.text(),
            ngayHoc=self.date_session.date().toString(
                "yyyy-MM-dd"
            ),
            phongHoc=self.txt_room.text(),
            gioBatDau=start_time,
            gioKetThuc=end_time,
            nguoiTao=self.username,
        )

    def create_session(self):
        data = self._read_form()
        data.id = 0

        new_id, message = (
            self.session_service.create_ca(data)
        )

        if new_id > 0:
            QMessageBox.information(
                self,
                "Thành công",
                message,
            )
            self.clear_form()
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Không thể tạo ca",
                message,
            )

    def update_session(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn ca",
                "Vui lòng chọn ca học cần cập nhật.",
            )
            return

        ok, message = self.session_service.update_ca(
            self._read_form()
        )

        if ok:
            QMessageBox.information(
                self,
                "Thành công",
                message,
            )
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Không thể cập nhật",
                message,
            )

    def delete_session(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn ca",
                "Vui lòng chọn ca học cần xóa.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "Bạn có chắc muốn xóa ca học này?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        ok, message = self.session_service.delete_ca(
            self.selected_id
        )

        if ok:
            QMessageBox.information(
                self,
                "Thành công",
                message,
            )
            self.clear_form()
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Không thể xóa",
                message,
            )

    def open_session(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn ca",
                "Vui lòng chọn ca cần mở điểm danh.",
            )
            return

        session = self.session_service.get_ca_by_id(
            self.selected_id
        )

        if not session:
            QMessageBox.warning(
                self,
                "Không tìm thấy",
                "Không tìm thấy ca học.",
            )
            return

        if session["trangThai"] == "DaKetThuc":
            QMessageBox.warning(
                self,
                "Không thể mở",
                "Ca học đã kết thúc.",
            )
            return

        ok, message = self.session_service.set_status(
            self.selected_id,
            "DangDienRa",
        )

        if ok:
            QMessageBox.information(
                self,
                "Đã mở điểm danh",
                message,
            )
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Không thể mở",
                message,
            )

    def finish_session(self):
        if self.selected_id <= 0:
            QMessageBox.warning(
                self,
                "Chưa chọn ca",
                "Vui lòng chọn ca học cần kết thúc.",
            )
            return

        ok, message = self.session_service.set_status(
            self.selected_id,
            "DaKetThuc",
        )

        if ok:
            QMessageBox.information(
                self,
                "Đã kết thúc",
                message,
            )
            self.refresh()
        else:
            QMessageBox.warning(
                self,
                "Không thể kết thúc",
                message,
            )

    def clear_form(self):
        self.selected_id = 0
        self.table.clearSelection()
        self.txt_session_name.clear()
        self.txt_room.clear()
        self.date_session.setDate(QDate.currentDate())
        self.cmb_time.setCurrentIndex(0)
        self._on_time_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()