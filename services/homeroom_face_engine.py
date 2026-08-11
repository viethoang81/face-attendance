from __future__ import annotations


class HomeroomFaceEngine:
    """Giới hạn đăng ký khuôn mặt vào sinh viên thuộc lớp chủ nhiệm."""

    _DENIED = (
        "Bạn không có quyền đăng ký khuôn mặt cho sinh viên "
        "ngoài lớp chủ nhiệm được phân công."
    )

    def __init__(self, delegate, student_service):
        self._delegate = delegate
        self._student_service = student_service

    @property
    def REGISTRATION_SAMPLE_COUNT(self) -> int:
        return int(
            getattr(
                self._delegate,
                "REGISTRATION_SAMPLE_COUNT",
                10,
            )
        )

    def _can_manage(self, mssv: str) -> bool:
        try:
            return bool(
                self._student_service.can_modify_student(mssv)
            )
        except Exception:
            # Phân quyền phải fail-closed nếu việc kiểm tra gặp lỗi.
            return False

    def extract_registration_sample(
        self,
        mssv: str,
        frame_bgr,
    ) -> tuple[bool, str, dict | None]:
        if not self._can_manage(mssv):
            return False, self._DENIED, None

        return self._delegate.extract_registration_sample(
            mssv,
            frame_bgr,
        )

    def replace_registration(
        self,
        mssv: str,
        samples: list[dict],
    ) -> tuple[bool, str]:
        # Không dựa vào lần kiểm tra lúc chụp: phân công chủ nhiệm có thể
        # đã thay đổi trong thời gian người dùng thu thập đủ các mẫu.
        if not self._can_manage(mssv):
            return False, self._DENIED

        return self._delegate.replace_registration(
            mssv,
            samples,
            actor_username=self._student_service.username,
        )

    def load_encodings(self):
        return self._delegate.load_encodings()

    def get_registered_mssv_set(self) -> set[str]:
        return self._delegate.get_registered_mssv_set()
