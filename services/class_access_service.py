class ClassAccessService:
    def __init__(self, class_svc, lecturer_svc, current_user: dict):
        self.class_svc = class_svc
        self.lecturer_svc = lecturer_svc
        self.current_user = current_user or {}

    @property
    def username(self) -> str:
        return self.current_user.get("username", "").strip()

    @property
    def role(self) -> str:
        return self.current_user.get("vaiTro", "")

    @property
    def is_admin(self) -> bool:
        return self.role == "Admin"

    def get_visible_classes(self) -> list[dict]:
        if self.is_admin:
            return self.class_svc.get_all()
        return self.lecturer_svc.get_homeroom_classes(self.username)

    def get_visible_class_codes(self) -> list[str]:
        return [c["maLop"] for c in self.get_visible_classes()]

    def can_access_class(self, ma_lop: str) -> bool:
        ma_lop = (ma_lop or "").strip()
        if not ma_lop:
            return False
        if self.is_admin:
            return True
        return self.lecturer_svc.is_homeroom_of(self.username, ma_lop)