import logging
from threading import Lock

import cv2
import face_recognition
import numpy as np

from services.face_template_service import FaceTemplateService


logger = logging.getLogger(__name__)

MIN_FACE_SIZE = 80
MIN_FACE_RATIO = 0.16
MIN_BRIGHTNESS = 40
MAX_BRIGHTNESS = 230
MIN_BLUR_VAR = 45.0
SINGLE_IDENTITY_TOLERANCE = 0.40
DUPLICATE_FACE_TOLERANCE = 0.38


class FaceEngine:
    """Trích xuất, nhận diện và quản lý cache embedding khuôn mặt."""

    REGISTRATION_SAMPLE_COUNT = 10

    def __init__(self, template_service: FaceTemplateService):
        self.template_service = template_service
        self.known_mssv: list[str] = []
        self.known_encs: list[np.ndarray] = []
        self._encs_np: np.ndarray | None = None
        self._enc_lock = Lock()
        self.load_encodings()

    def load_encodings(self):
        """Nạp toàn bộ mẫu đang hoạt động từ SQLite vào cache NumPy."""
        try:
            templates = self.template_service.load_active_templates()
        except Exception as exc:
            logger.error("[FaceEngine] Cannot load templates from SQLite: %s", exc)
            templates = []

        with self._enc_lock:
            self.known_mssv = [template.mssv for template in templates]
            self.known_encs = [template.embedding for template in templates]
            self._rebuild_np_locked()

        logger.info(
            "[FaceEngine] Loaded %d encodings for %d students from SQLite",
            len(self.known_encs),
            len(set(self.known_mssv)),
        )

    def _rebuild_np_locked(self):
        self._encs_np = (
            np.asarray(self.known_encs, dtype=np.float64)
            if self.known_encs
            else None
        )

    def _check_duplicate_face(
        self,
        enc: np.ndarray,
        exclude_mssv: str,
    ) -> tuple[bool, str]:
        """Chặn việc dùng một khuôn mặt cho hai sinh viên khác nhau."""
        if self._encs_np is None or not self.known_mssv:
            return False, ""

        distances = np.linalg.norm(self._encs_np - enc, axis=1)

        for distance, mssv in zip(distances.tolist(), self.known_mssv):
            if mssv == exclude_mssv:
                continue
            if distance < DUPLICATE_FACE_TOLERANCE:
                return True, (
                    f"Khuôn mặt này đã được đăng ký cho MSSV {mssv} "
                    f"(độ tương đồng: {distance:.3f})."
                )
        return False, ""

    def check_register_quality(
        self,
        frame_bgr: np.ndarray,
        locs: list,
    ) -> tuple[bool, str]:
        if len(locs) == 0:
            return False, "Không phát hiện khuôn mặt trong khung hình"
        if len(locs) > 1:
            return False, "Chỉ được có đúng một khuôn mặt khi đăng ký"

        top, right, bottom, left = locs[0]
        face_w = right - left
        face_h = bottom - top
        frame_h, frame_w = frame_bgr.shape[:2]

        if face_w < MIN_FACE_SIZE or face_h < MIN_FACE_SIZE:
            return False, "Khuôn mặt quá nhỏ, hãy đứng gần camera hơn"

        min_required = min(frame_w, frame_h) * MIN_FACE_RATIO
        if face_w < min_required or face_h < min_required:
            return False, "Khuôn mặt chiếm quá ít khung hình, hãy đứng gần hơn"

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        face_gray = gray[
            max(top, 0):min(bottom, frame_h),
            max(left, 0):min(right, frame_w),
        ]
        if face_gray.size == 0:
            return False, "Vùng khuôn mặt không hợp lệ"

        brightness = float(np.mean(face_gray))
        if brightness < MIN_BRIGHTNESS:
            return False, "Ảnh quá tối, hãy thêm ánh sáng"
        if brightness > MAX_BRIGHTNESS:
            return False, "Ảnh quá sáng hoặc bị chói"

        blur_var = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
        if blur_var < MIN_BLUR_VAR:
            return False, "Ảnh bị mờ, hãy giữ yên và thử lại"

        return True, "OK"

    def extract_registration_sample(
        self,
        mssv: str,
        frame_bgr: np.ndarray,
    ) -> tuple[bool, str, dict | None]:
        """Trích xuất một mẫu hợp lệ nhưng chưa ghi xuống CSDL."""
        rgb = self._to_rgb(frame_bgr)
        if rgb is None:
            return False, "Frame không hợp lệ", None

        locs = face_recognition.face_locations(rgb, model="hog")
        ok, message = self.check_register_quality(frame_bgr, locs)
        if not ok:
            return False, message, None

        encodings = face_recognition.face_encodings(rgb, locs)
        if not encodings:
            return False, "Không trích xuất được đặc trưng khuôn mặt", None

        embedding = np.asarray(encodings[0], dtype=np.float64)
        if embedding.shape != (128,) or not np.isfinite(embedding).all():
            return False, "Embedding khuôn mặt không hợp lệ", None

        with self._enc_lock:
            is_duplicate, duplicate_message = self._check_duplicate_face(
                embedding,
                str(mssv),
            )
        if is_duplicate:
            return False, duplicate_message, None

        top, right, bottom, left = locs[0]
        frame_h, frame_w = frame_bgr.shape[:2]
        top = max(top, 0)
        right = min(right, frame_w)
        bottom = min(bottom, frame_h)
        left = max(left, 0)

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        face_gray = gray[top:bottom, left:right]

        return True, "OK", {
            "embedding": embedding,
            "brightness": float(np.mean(face_gray)),
            "blurVariance": float(
                cv2.Laplacian(face_gray, cv2.CV_64F).var()
            ),
            "faceWidth": int(right - left),
            "faceHeight": int(bottom - top),
        }

    def replace_registration(
        self,
        mssv: str,
        samples: list[dict],
        actor_username: str = "",
    ) -> tuple[bool, str]:
        """Lưu trọn bộ 10 mẫu trong một transaction duy nhất."""
        if len(samples) != self.REGISTRATION_SAMPLE_COUNT:
            return (
                False,
                f"Cần đúng {self.REGISTRATION_SAMPLE_COUNT} mẫu khuôn mặt",
            )

        try:
            sample_count = self.template_service.replace_samples(
                mssv,
                samples,
                actor_username=actor_username,
            )
        except Exception as exc:
            logger.exception("[FaceEngine] Cannot replace face templates")
            return False, f"Lỗi lưu dữ liệu khuôn mặt: {exc}"

        self.load_encodings()
        return True, f"Đã lưu {sample_count} mẫu khuôn mặt"

    def remove_encoding(self, mssv: str):
        """Xóa mẫu thủ công và đồng bộ lại cache.

        FK mẫu khuôn mặt dùng ON DELETE RESTRICT. Nghiệp vụ purge phải xóa mẫu
        trong cùng transaction, sau đó giao diện gọi load_encodings().
        """
        try:
            self.template_service.delete_samples(mssv)
        except Exception as exc:
            logger.error("[FaceEngine] Cannot remove face templates: %s", exc)
        finally:
            self.load_encodings()

    def get_registered_mssv_set(self) -> set[str]:
        with self._enc_lock:
            return set(self.known_mssv)

    @staticmethod
    def _rank_candidates(
        enc: np.ndarray,
        known_mssv: list[str],
        encs_np: np.ndarray,
    ) -> list[tuple[str, float]]:
        person_encs: dict[str, list[np.ndarray]] = {}
        for mssv, known_enc in zip(known_mssv, encs_np):
            person_encs.setdefault(mssv, []).append(known_enc)

        if len(person_encs) == 1:
            mssv, samples = next(iter(person_encs.items()))
            centroid = np.mean(np.asarray(samples), axis=0)
            return [(mssv, float(np.linalg.norm(centroid - enc)))]

        distances = np.linalg.norm(encs_np - enc, axis=1)
        person_best: dict[str, float] = {}
        for mssv, distance in zip(known_mssv, distances.tolist()):
            if mssv not in person_best or distance < person_best[mssv]:
                person_best[mssv] = float(distance)
        return sorted(person_best.items(), key=lambda item: item[1])

    def recognize(
        self,
        frame_bgr: np.ndarray,
        tolerance: float = 0.45,
        margin: float = 0.06,
    ) -> list[dict]:
        """Nhận diện khuôn mặt và loại các kết quả không chắc chắn."""
        if (
            frame_bgr is None
            or not isinstance(frame_bgr, np.ndarray)
            or frame_bgr.size == 0
        ):
            return []

        small = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
        rgb = self._to_rgb(small)
        if rgb is None:
            return []

        locs = face_recognition.face_locations(rgb, model="hog")
        encodings = face_recognition.face_encodings(rgb, locs)

        with self._enc_lock:
            known_mssv = list(self.known_mssv)
            encs_np = self._encs_np.copy() if self._encs_np is not None else None

        results = []
        for enc, (top, right, bottom, left) in zip(encodings, locs):
            box = (left * 2, top * 2, right * 2, bottom * 2)

            if encs_np is None or not known_mssv:
                results.append({"box": box, "mssv": None, "distance": 1.0})
                continue

            ranked = self._rank_candidates(enc, known_mssv, encs_np)
            best_mssv, best_distance = ranked[0]
            effective_tolerance = (
                min(tolerance, SINGLE_IDENTITY_TOLERANCE)
                if len(ranked) == 1
                else tolerance
            )

            if best_distance >= effective_tolerance:
                results.append(
                    {"box": box, "mssv": None, "distance": best_distance}
                )
                continue

            if len(ranked) > 1 and ranked[1][1] - best_distance < margin:
                results.append(
                    {"box": box, "mssv": None, "distance": best_distance}
                )
                continue

            results.append(
                {
                    "box": box,
                    "mssv": best_mssv,
                    "distance": best_distance,
                }
            )

        return results

    @staticmethod
    def _to_rgb(frame_bgr: np.ndarray) -> np.ndarray | None:
        if (
            frame_bgr is None
            or not isinstance(frame_bgr, np.ndarray)
            or frame_bgr.size == 0
        ):
            return None
        if frame_bgr.dtype != np.uint8:
            frame_bgr = np.clip(frame_bgr, 0, 255).astype(np.uint8)
        if frame_bgr.ndim == 2:
            return frame_bgr
        if frame_bgr.ndim != 3:
            return None
        if frame_bgr.shape[2] == 3:
            return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if frame_bgr.shape[2] == 4:
            return cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2RGB)
        return None
