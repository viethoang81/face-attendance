import sys

from core.cnn_antispoof import TrainedCNNAntiSpoof
from core.course_attendance_engine import (
    CourseAttendanceEngine,
)
from core.database import Database
from core.face_engine import FaceEngine

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox,
    QTabWidget,
)

from services.academic_service import AcademicService
from services.class_service import ClassService
from services.course_attendance_service import (
    CourseAttendanceService,
)
from services.course_section_access_service import (
    CourseSectionAccessService,
)
from services.course_session_service import (
    CourseSessionService,
)
from services.face_template_service import (
    FaceTemplateService,
)
from services.homeroom_face_engine import HomeroomFaceEngine
from services.homeroom_student_service import HomeroomStudentService
from services.lecturer_course_service import (
    LecturerCourseService,
)
from services.restricted_auth_service import AuthService
from services.student_service import StudentService

from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow
from ui.tab_academic import TabAcademic
from ui.tab_attendance import TabAttendance
from ui.tab_classes import TabClasses
from ui.tab_course_sessions import TabCourseSessions
from ui.tab_history import TabHistory
from ui.tab_lecturers import TabLecturers
from ui.tab_my_class_students import TabMyClassStudents
from ui.tab_my_course_sections import (
    TabMyCourseSections,
)
from ui.tab_report import TabReport
from ui.tab_students import TabStudents


def build_main_window(
    db: Database,
    auth_svc: AuthService,
    current_user: dict,
):
    # NHẬN DIỆN KHUÔN MẶT
    face_template_service = FaceTemplateService(db)
    face_engine = FaceEngine(face_template_service)
    cnn_antispoof = TrainedCNNAntiSpoof()

    attendance_engine = CourseAttendanceEngine(
        db,
        face_engine,
        cnn_antispoof,
    )

    student_service = StudentService(db, current_user)
    class_service = ClassService(db)

    # SERVICE HỌC VỤ VÀ ĐIỂM DANH
    academic_service = AcademicService(db)
    session_service = CourseSessionService(db)
    attendance_service = CourseAttendanceService(db)

    course_access_service = CourseSectionAccessService(
        academic_service,
        current_user,
    )

    # GIAO DIỆN
    tabs = QTabWidget()
    tabs.setTabPosition(QTabWidget.North)
    tabs.setMovable(False)

    role = current_user.get(
        "vaiTro",
        "GiangVien",
    )

    if role == "Admin":
        tab_students = TabStudents(
            student_service,
            class_service,
            face_engine,
            current_user,
        )
        tabs.addTab(
            tab_students,
            "👤  Quản lý sinh viên",
        )

        tab_lecturers = TabLecturers(
            auth_svc,
            current_user,
        )
        tabs.addTab(
            tab_lecturers,
            "👨‍🏫  Quản lý giảng viên",
        )

        tab_classes = TabClasses(
            class_service,
            auth_svc,
            current_user,
        )
        tabs.addTab(
            tab_classes,
            "🏫  Lớp hành chính",
        )

        tab_academic = TabAcademic(
            academic_service,
            auth_svc,
            current_user,
        )
        tabs.addTab(
            tab_academic,
            "🎓  Quản lý học vụ",
        )

        tab_sessions = TabCourseSessions(
            session_service,
            academic_service,
            current_user,
        )
        tabs.addTab(
            tab_sessions,
            "📅  Quản lý ca học",
        )

    elif role == "GiangVien":
        # Quản lý sinh viên lớp chủ nhiệm
        homeroom_student_service = HomeroomStudentService(
            db,
            current_user,
        )

        homeroom_face_engine = HomeroomFaceEngine(
            face_engine,
            homeroom_student_service,
        )

        tab_my_class_students = TabMyClassStudents(
            homeroom_student_service,
            homeroom_face_engine,
        )

        tabs.addTab(
            tab_my_class_students,
            "👥  Sinh viên lớp chủ nhiệm",
        )

        # Danh sách lớp học phần được phân công hiện tại
        lecturer_course_service = LecturerCourseService(
            db,
            current_user,
        )

        tab_my_sections = TabMyCourseSections(
            lecturer_course_service,
        )

        tabs.addTab(
            tab_my_sections,
            "📚  Lớp học phần của tôi",
        )

    tab_attendance = TabAttendance(
        attendance_engine,
        attendance_service,
        student_service,
        course_access_service,
        session_service,
    )

    tab_history = TabHistory(
        attendance_service,
        course_access_service,
    )

    tab_report = TabReport(
        attendance_service,
        course_access_service,
        session_service,
    )

    tabs.addTab(
        tab_attendance,
        "📷  Điểm danh",
    )
    tabs.addTab(
        tab_history,
        "📋  Lịch sử & Báo cáo",
    )
    tabs.addTab(
        tab_report,
        "📊  Chuyên cần",
    )

    return MainWindow(
        tabs,
        auth_svc=auth_svc,
        current_user=current_user,
    )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    try:
        db = Database()
    except RuntimeError as exc:
        QMessageBox.critical(
            None,
            "Không thể khởi tạo cơ sở dữ liệu",
            str(exc),
        )
        sys.exit(1)
        return

    auth_svc = AuthService(db)

    while True:
        login = LoginDialog(auth_svc)

        if login.exec_() != LoginDialog.Accepted:
            break

        current_user = login.current_user or {}

        if current_user.get("vaiTro") not in {
            "Admin",
            "GiangVien",
        }:
            QMessageBox.warning(
                None,
                "Vai trò không hợp lệ",
                "Chương trình chỉ hỗ trợ tài khoản "
                "Admin và Giảng viên.",
            )
            continue

        window = build_main_window(
            db,
            auth_svc,
            current_user,
        )
        window.show()

        app.exec_()

        if not window.logged_out:
            break

    sys.exit()


if __name__ == "__main__":
    main()
