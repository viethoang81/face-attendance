class CourseSectionAccessService:

    def __init__(
        self,
        academic_service,
        current_user: dict,
    ):
        self.academic_service = academic_service
        self.current_user = current_user or {}

    @property
    def username(self) -> str:
        return (
            self.current_user.get("username", "")
            or ""
        ).strip()

    @property
    def role(self) -> str:
        return self.current_user.get("vaiTro", "")

    @property
    def is_admin(self) -> bool:
        return self.role == "Admin"

    def get_visible_classes(self) -> list[dict]:
        if self.is_admin:
            sections = self.academic_service.list_course_sections(
                include_cancelled=False,
            )
        elif self.role == "GiangVien":
            sections = self.academic_service.list_course_sections(
                lecturer_username=self.username,
                include_cancelled=False,
            )
        else:
            return []

        result = []

        for section in sections:
            section_code = section["maLopHocPhan"]
            subject_name = section.get("tenMon", "")
            semester_name = section.get("tenHocKy", "")
            school_year_name = section.get("tenNamHoc", "")

            label_parts = [
                section_code,
                subject_name,
            ]

            period_text = " - ".join(
                value
                for value in (
                    semester_name,
                    school_year_name,
                )
                if value
            )

            if period_text:
                label_parts.append(period_text)

            result.append(
                {
                    **section,
                    # Tên trường tương thích giao diện cũ.
                    "maLop": section_code,
                    "tenLop": " - ".join(
                        value
                        for value in label_parts
                        if value
                    ),
                }
            )

        return result

    def get_visible_class_codes(self) -> list[str]:
        return [
            section["maLop"]
            for section in self.get_visible_classes()
        ]

    def can_access_class(
        self,
        ma_lop: str,
    ) -> bool:
        ma_lop = (ma_lop or "").strip()
        if not ma_lop:
            return False

        if self.is_admin:
            section = (
                self.academic_service
                .get_course_section_by_code(ma_lop)
            )
            return (
                section is not None
                and section.get("trangThai") != "DA_HUY"
            )

        if self.role != "GiangVien":
            return False

        return self.academic_service.can_lecturer_access(
            self.username,
            ma_lop,
        )