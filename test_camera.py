import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from services.face_template_service import (
    FaceTemplateService,
)
import cv2

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.attendance_engine import AttendanceEngine
from core.database import DB_PATH
from core.face_engine import FaceEngine
from core.cnn_antispoof import TrainedCNNAntiSpoof
from services.student_service import StudentService

class ReadOnlyDatabase:
    """Database adapter that allows SELECT queries but cannot write."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @contextmanager
    def conn(self):
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

class CameraTestEngine(AttendanceEngine):
    """
    Production AttendanceEngine with only session validation and DB writes
    replaced for camera testing.
    """

    TEST_SESSION_ID = 0

    def __init__(self, face_engine: FaceEngine, cnn_antispoof: TrainedCNNAntiSpoof):
        super().__init__(
            db=None,
            face_engine=face_engine,
            cnn_antispoof=cnn_antispoof,
        )
        self.test_passed = set()

    def _get_class_status(self, mssv: str, ca_hoc_id: int) -> str:
        return "ok"

    def record(self, mssv: str, ca_hoc_id: int) -> str:
        """Simulate a successful attendance record without touching the DB."""
        with self._record_lock:
            now = time.time()
            if now - self.cooldown.get(mssv, 0) < self.COOLDOWN_SEC:
                return "duplicate"
            self.cooldown[mssv] = now
            self.marked_in_session.add(mssv)
            self.test_passed.add(mssv)
            return "new"

    def reset_session(self):
        super().reset_session()
        self.test_passed.clear()


def put_test_status(frame, engine: CameraTestEngine):
    lines = [
        "CAMERA TEST - CNN + MediaPipe pipeline",
        "No real class session | No attendance DB write",
        (
            f"FRAME_SKIP={engine.FRAME_SKIP} | "
            f"VOTE={engine.VOTE_REQUIRED}/{engine.VOTE_WINDOW} | "
            f"CNN={engine.CNN_REQUIRED_VOTES}/{engine.CNN_WINDOW} | "
            f"Passed={len(engine.test_passed)}"
        ),
        "Keys: R reset/reload | Q or ESC quit",
    ]

    font = cv2.FONT_HERSHEY_SIMPLEX
    y = 26
    for line in lines:
        cv2.putText(frame, line, (12, y), font, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, line, (12, y), font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        y += 24


def load_name_map() -> dict[str, str]:
    try:
        return StudentService(ReadOnlyDatabase(DB_PATH)).get_name_map()
    except Exception as exc:
        print(f"[CameraTest] Cannot read student names: {exc}")
        return {}


def main():
    read_only_db = ReadOnlyDatabase(DB_PATH)
    template_service = FaceTemplateService(read_only_db)
    face_engine = FaceEngine(template_service)
    cnn_antispoof = TrainedCNNAntiSpoof()
    if not cnn_antispoof.available:
        raise SystemExit(
            f"[CameraTest] CNN anti-spoof unavailable: {cnn_antispoof.error}"
        )
    engine = CameraTestEngine(face_engine, cnn_antispoof)
    name_map = load_name_map()

    print("[CameraTest] CNN + MediaPipe recognition pipeline")
    print(
        "[CameraTest] FaceEngine -> voting -> CNN anti-spoof -> MediaPipe challenge -> in-memory result"
    )
    print("[CameraTest] No CaHoc validation and no DiemDanh DB write")
    print(
        f"[CameraTest] CNN: {cnn_antispoof.model_path.name} | "
        f"threshold={cnn_antispoof.threshold:.2f} | "
        f"votes={engine.CNN_REQUIRED_VOTES}/{engine.CNN_WINDOW}"
    )
    print(f"[CameraTest] Encodings: {len(face_engine.known_encs)}")
    print(f"[CameraTest] Students: {len(set(face_engine.known_mssv))}")

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        engine.close()
        raise SystemExit("[CameraTest] Cannot open camera 0")

    window_name = "Camera Recognition Test"
    last_status = {}

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("[CameraTest] Cannot read camera frame")
                break

            results = engine.process_frame(
                frame,
                CameraTestEngine.TEST_SESSION_ID,
                name_map,
            )
            output = engine.draw(frame, results)
            put_test_status(output, engine)

            for result in results:
                mssv = result.get("mssv")
                status = result.get("status", "")
                label = result.get("label", "")
                if not mssv:
                    continue
                current = (status, label)
                if last_status.get(mssv) != current:
                    print(f"[CameraTest] {mssv}: {status} | {label}")
                    last_status[mssv] = current

            cv2.imshow(window_name, output)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            if key in (ord("r"), ord("R")):
                face_engine.load_encodings()
                name_map = load_name_map()
                engine.reset_session()
                last_status.clear()
                print("[CameraTest] Reset and reloaded encodings")
    finally:
        camera.release()
        cv2.destroyAllWindows()
        engine.close()


if __name__ == "__main__":
    main()
