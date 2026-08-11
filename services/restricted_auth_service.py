from services.auth_service import AuthService as BaseAuthService


class AuthService(BaseAuthService):
    VALID_ROLES = {
        "Admin",
        "GiangVien",
    }