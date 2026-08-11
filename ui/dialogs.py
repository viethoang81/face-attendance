# ui/dialogs.py
import cv2
import numpy as np
from PyQt5.QtCore import QDate, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


# ══════════════════════════════════════════════════════
#  Dialog Thêm / Sửa sinh viên
# ══════════════════════════════════════════════════════
class StudentDialog(QDialog):
    def __init__(
        self,
        sv_svc,
        cls_svc,
        existing: dict = None,
        classes: list = None,
        read_only: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.sv_svc = sv_svc
        self.cls_svc = cls_svc
        self.existing = existing
        self._original_mssv = (existing or {}).get("mssv", "")
        self._classes = classes
        self.read_only = bool(read_only)

        if self.read_only:
            self.setWindowTitle("Thông tin sinh viên - Chỉ xem")
        else:
            self.setWindowTitle(
                "Sửa thông tin sinh viên" if existing else "Thêm sinh viên mới"
            )
        self.setMinimumWidth(420)

        self._setup_ui()

        if existing:
            self._populate(existing)
        if self.read_only:
            self._set_read_only()

    def _setup_ui(self):
        form = QFormLayout(self)
        form.setSpacing(10)

        self.txt_mssv = QLineEdit()
        self.txt_hoten = QLineEdit()

        self.txt_ngaysinh = QLineEdit()
        self.txt_ngaysinh.setPlaceholderText("DD/MM/YYYY")

        self.cmb_gioitinh = QComboBox()
        self.cmb_gioitinh.addItems(["Nam", "Nữ"])

        self.cmb_lop = QComboBox()

        self.txt_khoa = QLineEdit()
        self.txt_khoa.setReadOnly(True)
        self.txt_khoa.setStyleSheet("background:#f0f0f0;")

        self.txt_email = QLineEdit()
        self.txt_sdt = QLineEdit()

        self.lbl_err = QLabel()
        self.lbl_err.setStyleSheet("color:#D85A30; font-size:12px;")
        self.lbl_err.setWordWrap(True)

        self._khoa_by_malop = {}

        # classes=None: dùng toàn bộ lớp từ service.
        # classes=[]: không có lớp được phép chọn.
        if self._classes is not None:
            source = self._classes
        elif self.cls_svc:
            source = self.cls_svc.get_all()
        else:
            source = []

        for classroom in source:
            ma_lop = classroom["maLop"]
            self.cmb_lop.addItem(classroom["tenLop"], ma_lop)
            self._khoa_by_malop[ma_lop] = classroom.get("khoa", "")

        form.addRow("MSSV *", self.txt_mssv)
        form.addRow("Họ và tên *", self.txt_hoten)
        form.addRow("Lớp *", self.cmb_lop)
        form.addRow("Khoa", self.txt_khoa)
        form.addRow("Ngày sinh *", self.txt_ngaysinh)
        form.addRow("Giới tính *", self.cmb_gioitinh)
        form.addRow("Email *", self.txt_email)
        form.addRow("Số điện thoại *", self.txt_sdt)
        form.addRow(self.lbl_err)

        self.cmb_lop.currentIndexChanged.connect(self._update_khoa)
        self._update_khoa()

        if self.read_only:
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.button(QDialogButtonBox.Close).setText("Đóng")
            buttons.rejected.connect(self.reject)
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            )
            buttons.button(QDialogButtonBox.Ok).setText("Lưu")
            buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
            buttons.accepted.connect(self._submit)
            buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _set_read_only(self):
        for line_edit in (
            self.txt_mssv,
            self.txt_hoten,
            self.txt_ngaysinh,
            self.txt_email,
            self.txt_sdt,
        ):
            line_edit.setReadOnly(True)
            line_edit.setStyleSheet("background:#f0f0f0;")
        self.cmb_gioitinh.setEnabled(False)
        self.cmb_lop.setEnabled(False)

    def _update_khoa(self):
        ma_lop = self.cmb_lop.currentData()
        self.txt_khoa.setText(self._khoa_by_malop.get(ma_lop, ""))

    def _populate(self, student: dict):
        self.txt_mssv.setText(student.get("mssv", ""))
        self.txt_hoten.setText(student.get("hoTen", ""))
        self.txt_ngaysinh.setText(student.get("ngaySinh", ""))
        self.txt_email.setText(student.get("email", ""))
        self.txt_sdt.setText(student.get("soDienThoai", ""))

        gender_index = self.cmb_gioitinh.findText(
            student.get("gioiTinh", "Nam")
        )
        if gender_index >= 0:
            self.cmb_gioitinh.setCurrentIndex(gender_index)

        class_index = self.cmb_lop.findData(student.get("maLop", ""))
        if class_index >= 0:
            self.cmb_lop.setCurrentIndex(class_index)

        self._update_khoa()

    def _submit(self):
        from services.student_service import Student

        student = Student(
            mssv=self.txt_mssv.text().strip(),
            hoTen=self.txt_hoten.text().strip(),
            maLop=self.cmb_lop.currentData(),
            ngaySinh=self.txt_ngaysinh.text().strip(),
            gioiTinh=self.cmb_gioitinh.currentText(),
            email=self.txt_email.text().strip(),
            soDienThoai=self.txt_sdt.text().strip(),
        )

        if self.existing:
            # Truyền MSSV cũ để service đổi mã an toàn và cascade dữ liệu.
            ok, message = self.sv_svc.update(
                self._original_mssv,
                student,
            )
        else:
            ok, message = self.sv_svc.add(student)

        if ok:
            self.accept()
        else:
            self.lbl_err.setText(message)


class StudentWithdrawalDialog(QDialog):
    """Chọn ngày đầu tiên sinh viên không còn thuộc danh sách học."""

    def __init__(self, mssv: str, reason: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cho sinh viên thôi học")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        message = QLabel(
            "Sinh viên đã phát sinh dữ liệu chuyên cần nên không thể "
            "xóa vĩnh viễn. Hệ thống sẽ chuyển sang trạng thái Thôi học, "
            "ngừng các đăng ký học phần tương lai và giữ nguyên lịch sử. "
            "Thay đổi có hiệu lực ngay khi xác nhận."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        if reason:
            detail = QLabel(reason)
            detail.setWordWrap(True)
            detail.setStyleSheet("color:#666; font-size:12px;")
            layout.addWidget(detail)

        form = QFormLayout()
        self.dte_effective = QDateEdit(QDate.currentDate())
        self.dte_effective.setCalendarPopup(True)
        self.dte_effective.setDisplayFormat("dd/MM/yyyy")
        self.dte_effective.setMinimumDate(QDate.currentDate())
        self.dte_effective.setMaximumDate(QDate.currentDate())
        form.addRow("Có hiệu lực từ ngày (áp dụng ngay):", self.dte_effective)
        layout.addLayout(form)

        note = QLabel(
            "Phiên bản hiện tại không lên lịch thôi học cho ngày tương lai. "
            "Nếu hôm nay đã có ca từng mở, hệ thống sẽ từ chối để bảo toàn "
            "lịch sử; hãy thực hiện lại vào ngày mai."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9A6700; font-size:12px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Xác nhận thôi học")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def effective_date(self) -> str:
        return self.dte_effective.date().toString("yyyy-MM-dd")


# ══════════════════════════════════════════════════════
#  Dialog Đăng ký khuôn mặt
# ══════════════════════════════════════════════════════
class _CaptureThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self._running = False
        self.cap = None

    def run(self):
        self._running = True
        self.cap = cv2.VideoCapture(0)

        while self._running:
            ret, frame = self.cap.read()
            if ret:
                self.frame_ready.emit(frame)

        self.cap.release()
        self.cap = None

    def stop(self):
        self._running = False
        self.wait(3000)


class FaceRegisterDialog(QDialog):
    def __init__(self, mssv: str, face_engine, parent=None):
        super().__init__(parent)
        self.mssv = mssv
        self.face_engine = face_engine

        self.setWindowTitle(f"Đăng ký khuôn mặt — {mssv}")
        self.setMinimumSize(560, 480)

        self._captured = 0
        self._TARGET = 10
        self._last_frame = None
        self._pending_samples: list[dict] = []

        self._setup_ui()
        self._start_camera()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        lbl_guide = QLabel(
            f"Hãy nhìn thẳng vào camera và nhấn 'Chụp' {self._TARGET} lần.\n"
            "Mỗi lần có thể thay đổi góc mặt một chút để tăng độ chính xác."
        )
        lbl_guide.setAlignment(Qt.AlignCenter)
        lbl_guide.setStyleSheet("color:#534AB7; font-size:13px;")
        layout.addWidget(lbl_guide)

        self.lbl_cam = QLabel()
        self.lbl_cam.setMinimumSize(520, 360)
        self.lbl_cam.setAlignment(Qt.AlignCenter)
        self.lbl_cam.setStyleSheet("background:#111; border-radius:8px;")
        layout.addWidget(self.lbl_cam)

        self.lbl_status = QLabel(f"Đã chụp: 0 / {self._TARGET}")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-size:14px; font-weight:500;")
        layout.addWidget(self.lbl_status)

        button_row = QHBoxLayout()

        self.btn_capture = QPushButton(f"Chụp ảnh (0/{self._TARGET})")
        self.btn_capture.setMinimumHeight(38)
        self.btn_capture.setStyleSheet(
            "background:#534AB7;color:white;border-radius:6px;"
            "font-size:14px;font-weight:500;"
        )
        self.btn_capture.clicked.connect(self._capture)

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setMinimumHeight(38)
        btn_cancel.clicked.connect(self._cancel)

        button_row.addWidget(self.btn_capture, 2)
        button_row.addWidget(btn_cancel, 1)
        layout.addLayout(button_row)

    def _start_camera(self):
        self._thread = _CaptureThread()
        self._thread.frame_ready.connect(self._show_frame)
        self._thread.start()

    def _show_frame(self, frame: np.ndarray):
        self._last_frame = frame.copy()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape

        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format_RGB888,
        )
        self.lbl_cam.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.lbl_cam.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _capture(self):
        if self._captured >= self._TARGET:
            self._commit_registration()
            return

        if self._last_frame is None:
            QMessageBox.warning(
                self,
                "Lỗi",
                "Chưa nhận được frame từ camera.",
            )
            return

        ok, message, sample = self.face_engine.extract_registration_sample(
            self.mssv,
            self._last_frame,
        )
        if not ok:
            QMessageBox.warning(self, "Không thể chụp mẫu", message)
            return

        self._pending_samples.append(sample)
        self._captured = len(self._pending_samples)

        self.lbl_status.setText(
            f"Đã chụp: {self._captured} / {self._TARGET}"
        )

        if self._captured < self._TARGET:
            self.btn_capture.setText(
                f"Chụp ảnh ({self._captured}/{self._TARGET})"
            )
            return

        self.btn_capture.setText("Lưu 10 mẫu")
        self._commit_registration()

    def _commit_registration(self):
        self.btn_capture.setEnabled(False)

        ok, message = self.face_engine.replace_registration(
            self.mssv,
            self._pending_samples,
        )
        if not ok:
            self.btn_capture.setEnabled(True)
            self.btn_capture.setText("Thử lưu lại")
            QMessageBox.warning(self, "Không thể lưu", message)
            return

        self._thread.stop()

        QMessageBox.information(
            self,
            "Hoàn tất",
            f"Đã đăng ký thành công {len(self._pending_samples)} mẫu "
            f"khuôn mặt cho {self.mssv}.",
        )
        self.accept()

    def _cancel(self):
        self._thread.stop()
        self.reject()

    def closeEvent(self, event):
        if hasattr(self, "_thread"):
            self._thread.stop()
        super().closeEvent(event)
