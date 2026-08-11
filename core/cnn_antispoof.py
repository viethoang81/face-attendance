import json
import logging
import time
from collections import deque
from pathlib import Path
import cv2
import numpy as np

try:
    import onnxruntime as ort
    ORT_IMPORT_ERROR = None
except Exception as exc:  # ImportError can wrap Windows DLL load failures.
    ort = None
    ORT_IMPORT_ERROR = exc
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = BASE_DIR / "assets" / "antispoof"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "antispoof_cnn.onnx"
DEFAULT_METADATA_PATH = DEFAULT_MODEL_DIR / "metadata.json"

class CNNPredictor:
    """ONNX Runtime predictor for the exported CNN anti-spoof model."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        metadata_path: str | Path = DEFAULT_METADATA_PATH,
        face_margin: float = 0.20,
        detect_face_if_missing: bool = False,
        require_face_box: bool = True,
        min_face_size: int = 64,
        providers: list[str] | None = None,
    ):
        if ort is None:
            detail = (
                f" ({type(ORT_IMPORT_ERROR).__name__}: {ORT_IMPORT_ERROR})"
                if ORT_IMPORT_ERROR is not None
                else ""
            )
            raise RuntimeError(
                "Khong nap duoc onnxruntime/DLL de chay CNN anti-spoof"
                f"{detail}"
            ) from ORT_IMPORT_ERROR
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Khong tim thay model CNN: {self.model_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Khong tim thay metadata CNN: {self.metadata_path}"
            )

        self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self.image_size = int(self.metadata.get("image_size", 128))
        self.threshold = float(self.metadata.get("threshold", 0.5))
        normalization = self.metadata.get("normalization", {})
        self.mean = np.asarray(
            normalization.get("mean", [0.5, 0.5, 0.5]), dtype=np.float32
        )
        self.std = np.asarray(
            normalization.get("std", [0.5, 0.5, 0.5]), dtype=np.float32
        )
        self.face_margin = float(face_margin)
        self.detect_face_if_missing = bool(detect_face_if_missing)
        self.require_face_box = bool(require_face_box)
        self.min_face_size = int(min_face_size)

        self.session = ort.InferenceSession(
            str(self.model_path),
            providers=providers or ["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.detector = None
        if self.detect_face_if_missing:
            cascade_path = Path(cv2.data.haarcascades) / (
                "haarcascade_frontalface_default.xml"
            )
            self.detector = cv2.CascadeClassifier(str(cascade_path))
            if self.detector.empty():
                raise RuntimeError(
                    f"Khong load duoc OpenCV face detector: {cascade_path}"
                )

        logger.info(
            "[CNNAntiSpoof] Loaded %s, threshold=%.3f",
            self.model_path,
            self.threshold,
        )

    @staticmethod
    def _clip_box(
        box: tuple[int, int, int, int],
        frame_width: int,
        frame_height: int,
        margin: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = (int(value) for value in box)
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        x1 = max(0, x1 - int(width * margin))
        y1 = max(0, y1 - int(height * margin))
        x2 = min(frame_width, x2 + int(width * margin))
        y2 = min(frame_height, y2 + int(height * margin))
        return x1, y1, x2, y2

    def _detect_face(self, frame_bgr: np.ndarray):
        if self.detector is None:
            return None
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(self.min_face_size, self.min_face_size),
        )
        if len(faces) == 0:
            return None
        x, y, width, height = max(faces, key=lambda item: item[2] * item[3])
        return x, y, x + width, y + height

    def _preprocess(self, frame_bgr: np.ndarray, face_box=None) -> np.ndarray:
        if (
            frame_bgr is None
            or not isinstance(frame_bgr, np.ndarray)
            or frame_bgr.size == 0
        ):
            raise ValueError("frame khong hop le")

        if face_box is None and self.detect_face_if_missing:
            face_box = self._detect_face(frame_bgr)
        if face_box is None and self.require_face_box:
            raise ValueError("thieu face_box cho CNN")

        crop = frame_bgr
        if face_box is not None:
            height, width = frame_bgr.shape[:2]
            x1, y1, x2, y2 = self._clip_box(
                face_box, width, height, self.face_margin
            )
            crop = frame_bgr[y1:y2, x1:x2]

        if crop.size == 0:
            raise ValueError("face_box tao crop rong")

        if crop.ndim == 2:
            rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
        elif crop.ndim == 3 and crop.shape[2] == 4:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGRA2RGB)
        elif crop.ndim == 3 and crop.shape[2] == 3:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        else:
            raise ValueError("dinh dang frame khong ho tro")

        rgb = cv2.resize(
            rgb,
            (self.image_size, self.image_size),
            interpolation=cv2.INTER_AREA,
        )
        array = rgb.astype(np.float32) / 255.0
        array = (array - self.mean) / self.std
        return array.transpose(2, 0, 1)[None, ...].astype(np.float32)

    def predict(self, frame_bgr: np.ndarray, face_box=None) -> dict:
        tensor = self._preprocess(frame_bgr, face_box=face_box)
        output = self.session.run([self.output_name], {self.input_name: tensor})[0]
        live_score = float(np.asarray(output, dtype=np.float32).reshape(-1)[0])
        return {
            "is_live": live_score >= self.threshold,
            "live_score": live_score,
            "threshold": self.threshold,
        }
    
class TrainedCNNAntiSpoof:
    """Runtime wrapper for the trained CNN anti-spoof ONNX model."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        metadata_path: str | Path = DEFAULT_METADATA_PATH,
    ):
        self.available = False
        self.error: str | None = None
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        self.threshold = 0.5
        self._last_inference_ms = 0.0
        self.predictor: CNNPredictor | None = None

        try:
            self.predictor = CNNPredictor(
                model_path=self.model_path,
                metadata_path=self.metadata_path,
                require_face_box=True,
            )
            self.threshold = float(self.predictor.threshold)
            self.available = True
        except Exception as exc:
            self.error = str(exc)
            logger.exception("[TrainedCNNAntiSpoof] Khong khoi tao duoc CNN")

    @property
    def last_inference_ms(self) -> float:
        return float(self._last_inference_ms)

    def predict(
        self,
        frame_bgr: np.ndarray,
        face_box: tuple[int, int, int, int],
    ) -> float | None:
        result = self.predict_raw(frame_bgr, face_box)
        return None if result is None else float(result["real_score"])

    def predict_raw(
        self,
        frame_bgr: np.ndarray,
        face_box: tuple[int, int, int, int],
    ) -> dict | None:
        if self.predictor is None:
            return None
        try:
            started = time.perf_counter()
            result = self.predictor.predict(frame_bgr, face_box=face_box)
            inference_ms = (time.perf_counter() - started) * 1000.0
            self._last_inference_ms = inference_ms
            real_score = float(result["live_score"])
            threshold = float(result["threshold"])
            spoof_score = max(0.0, min(1.0, 1.0 - real_score))
            live_score = max(0.0, min(1.0, real_score))
            return {
                "real_score": real_score,
                "is_real": bool(result["is_live"]),
                "threshold": threshold,
                "probabilities": [spoof_score, live_score],
                "logits": [real_score],
                "inference_ms": round(float(inference_ms), 2),
                "crop_shape": tuple(frame_bgr.shape),
            }
        except Exception:
            logger.exception("[TrainedCNNAntiSpoof] Du doan CNN that bai")
            return None

    def close(self):
        self.predictor = None