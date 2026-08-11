import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock         
from core.attendance_status import PRESENT, LATE   

import cv2
import numpy as np

from core.anti_spoof import AntiSpoof
from core.database import Database
from core.face_engine import FaceEngine
from core.cnn_antispoof import TrainedCNNAntiSpoof

logger = logging.getLogger(__name__)

@dataclass
class _IdentityLock:
    """Temporarily bind one verified identity to the liveness challenge."""

    mssv: str
    name_ascii: str
    box: tuple[int, int, int, int]
    distance: float
    acquired_at: float
    last_confirmed_at: float

class AttendanceEngine:
    SHOW_FPS = False
    FRAME_SKIP = 2
    COOLDOWN_SEC = 60
    VOTE_WINDOW = 9
    VOTE_REQUIRED = 3
    CNN_ENABLED = True
    CNN_REQUIRED = True
    CNN_WINDOW = 5
    CNN_REQUIRED_VOTES = 3
    IDENTITY_LOCK_GRACE_SEC = 2.0
    IDENTITY_LOCK_MAX_SEC = 25.0
    IDENTITY_LOCK_MIN_IOU = 0.12
    IDENTITY_LOCK_MAX_CENTER_RATIO = 0.75
    IDENTITY_LOCK_MIN_AREA_RATIO = 0.35
    IDENTITY_LOCK_MAX_AREA_RATIO = 2.80
    LATE_GRACE_MINUTES = 15

    def __init__(
        self,
        db: Database,
        face_engine: FaceEngine,
        cnn_antispoof: TrainedCNNAntiSpoof | None = None,
    ):
        self.db = db
        self.fe = face_engine
        self.cnn_antispoof = cnn_antispoof
        self.anti_spoof = AntiSpoof()
        self.cooldown = {}
        self.marked_in_session = set()
        self._results = []
        self._frame_cnt = 0
        self._skip_cnt = 0
        self._fps_time = time.time()
        self._fps = 0
        self._record_lock = Lock()
        self._class_check_cache = {}
        self._wrong_class_logged = set()
        self._vote_buf: dict[str, deque] = {}
        self._cnn_scores: dict[str, deque] = {}
        self._cnn_passed: dict[str, bool] = {}
        self._identity_lock: _IdentityLock | None = None

        if self.CNN_ENABLED and (self.cnn_antispoof is None or not self.cnn_antispoof.available):
            logger.error(
                "[AttendanceEngine] CNN unavailable: %s",
                getattr(self.cnn_antispoof, "error", "not initialized"),
            )

    def reset_session(self):
        with self._record_lock:
            self.cooldown.clear()
            self.marked_in_session.clear()
            self._class_check_cache.clear()
            self._wrong_class_logged.clear()
        self.anti_spoof.reset_all()
        self._frame_cnt = 0
        self._skip_cnt = 0
        self._results = []
        self._vote_buf.clear()
        self._cnn_scores.clear()
        self._cnn_passed.clear()
        self._identity_lock = None

    def _get_class_status(self, mssv: str, ca_hoc_id: int) -> str:
        """Kiểm tra sinh viên có đăng ký học phần hợp lệ tại ngày học."""
        key = (mssv, ca_hoc_id)
        with self._record_lock:
            cached = self._class_check_cache.get(key)
            if cached is not None:
                return cached

        try:
            with self.db.conn() as connection:
                row = connection.execute(
                    """
                    SELECT EXISTS (
                               SELECT 1
                               FROM DangKyHocPhan dk
                               WHERE dk.mssv = sv.mssv
                                 AND dk.lopHocPhanId = ca.lopHocPhanId
                                 AND dk.ngayDangKy <= ca.ngayHoc
                                 AND (
                                     dk.ngayKetThuc = ''
                                     OR dk.ngayKetThuc >= ca.ngayHoc
                                 )
                           ) AS coDangKyHopLe
                    FROM SinhVien sv
                    CROSS JOIN CaHoc ca
                    WHERE sv.mssv = ?
                      AND sv.trangThai = 'DANG_HOC'
                      AND ca.id = ?
                    """,
                    (mssv, ca_hoc_id),
                ).fetchone()

            if not row:
                result = "error"
            elif row["coDangKyHopLe"] != 1:
                result = "wrong_class"
            else:
                result = "ok"
        except Exception as exc:
            logger.error(
                "[AttendanceEngine] Registration check error: %s",
                exc,
            )
            result = "error"

        with self._record_lock:
            self._class_check_cache[key] = result
            if result == "wrong_class" and key not in self._wrong_class_logged:
                logger.warning(
                    "[AttendanceEngine] Student has no valid registration: "
                    "MSSV=%s, session=%s",
                    mssv,
                    ca_hoc_id,
                )
                self._wrong_class_logged.add(key)
        return result

    def record(self, mssv: str, ca_hoc_id: int) -> str:
        class_status = self._get_class_status(mssv, ca_hoc_id)
        if class_status != "ok":
            return class_status

        with self._record_lock:
            now = time.time()
            # Luôn đối chiếu database: bản ghi có thể vừa bị hủy hoặc
            # khôi phục từ màn hình quản lý trong khi camera vẫn đang chạy.
            try:
                with self.db.conn() as c:
                    exists = c.execute(
                        "SELECT id, isVoided FROM DiemDanh WHERE mssv=? AND caHocId=?",
                        (mssv, ca_hoc_id),
                    ).fetchone()
                    if exists:
                        self.cooldown[mssv] = now
                        if exists["isVoided"] == 1:
                            self.marked_in_session.discard(mssv)
                            return "voided"
                        self.marked_in_session.add(mssv)
                        return "duplicate"
                    trang_thai = self._resolve_attendance_status(c, ca_hoc_id)
                    c.execute(
                        """
                        INSERT OR IGNORE INTO DiemDanh
                            (mssv, caHocId, thoiGian, trangThai)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            mssv,
                            ca_hoc_id,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            trang_thai,
                        ),
                    )
                    affected = c.execute("SELECT changes()").fetchone()[0]
                self.cooldown[mssv] = now
                if affected:
                    self.marked_in_session.add(mssv)
                    logger.info("[AttendanceEngine] New attendance: %s", mssv)
                    return "new"
                return "duplicate"
            except Exception as exc:
                logger.error("[AttendanceEngine] DB write error: %s", exc)
                return "error"
            
    def _resolve_attendance_status(self, c, ca_hoc_id: int) -> str:
        """PRESENT nếu điểm danh đúng giờ, LATE nếu qua giờ bắt đầu + ân hạn."""
        try:
            row = c.execute(
                "SELECT ngayHoc, gioBatDau FROM CaHoc WHERE id=?",
                (ca_hoc_id,),
            ).fetchone()
            if not row or not row["gioBatDau"]:
                return PRESENT
            start = datetime.strptime(
                f"{row['ngayHoc']} {row['gioBatDau']}", "%Y-%m-%d %H:%M"
            )
            deadline = start + timedelta(minutes=self.LATE_GRACE_MINUTES)
            return LATE if datetime.now() > deadline else PRESENT
        except Exception:
            logger.exception("[AttendanceEngine] Cannot resolve attendance status")
            return PRESENT

    @staticmethod
    def _box_key(box: tuple[int, int, int, int]) -> str:
        x1, y1, x2, y2 = box
        cx = (x1 + x2) // 2 // 40
        cy = (y1 + y2) // 2 // 40
        return f"{cx}_{cy}"

    def _vote(self, box: tuple[int, int, int, int], mssv: str | None) -> str | None:
        key = self._box_key(box)
        if mssv is None:
            self._vote_buf.pop(key, None)
            return None
        buf = self._vote_buf.setdefault(key, deque(maxlen=self.VOTE_WINDOW))
        buf.append(mssv)
        if len(buf) < self.VOTE_REQUIRED:
            return None
        return (
            mssv if sum(1 for sid in buf if sid == mssv) >= self.VOTE_REQUIRED else None
        )

    def _cleanup_vote_buf(self, active_keys: set[str]):
        for key in list(self._vote_buf):
            if key not in active_keys:
                del self._vote_buf[key]

    @staticmethod
    def _box_iou(
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> float:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0

    def _box_matches_identity_lock(
        self,
        box: tuple[int, int, int, int],
    ) -> bool:
        """Reject abrupt face handoffs while allowing normal head-turn jitter."""
        lock = self._identity_lock
        if lock is None:
            return False

        if self._box_iou(lock.box, box) >= self.IDENTITY_LOCK_MIN_IOU:
            return True

        x1, y1, x2, y2 = lock.box
        nx1, ny1, nx2, ny2 = box
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        new_width = max(1, nx2 - nx1)
        new_height = max(1, ny2 - ny1)
        area_ratio = (new_width * new_height) / (width * height)
        if not (
            self.IDENTITY_LOCK_MIN_AREA_RATIO
            <= area_ratio
            <= self.IDENTITY_LOCK_MAX_AREA_RATIO
        ):
            return False

        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        new_center_x = (nx1 + nx2) / 2.0
        new_center_y = (ny1 + ny2) / 2.0
        center_distance = float(
            np.hypot(
                new_center_x - center_x,
                new_center_y - center_y,
            )
        )
        reference_size = max(width, height, new_width, new_height)
        return center_distance <= reference_size * self.IDENTITY_LOCK_MAX_CENTER_RATIO

    def _identity_lock_is_usable(self, now: float) -> bool:
        lock = self._identity_lock
        if lock is None:
            return False
        return (
            now - lock.last_confirmed_at <= self.IDENTITY_LOCK_GRACE_SEC
            and now - lock.acquired_at <= self.IDENTITY_LOCK_MAX_SEC
        )

    def _acquire_identity_lock(
        self,
        mssv: str,
        name_ascii: str,
        box: tuple[int, int, int, int],
        distance: float,
        now: float,
    ):
        self._identity_lock = _IdentityLock(
            mssv=mssv,
            name_ascii=name_ascii,
            box=box,
            distance=float(distance),
            acquired_at=now,
            last_confirmed_at=now,
        )
        logger.info("[AttendanceEngine] Identity locked for liveness: %s", mssv)

    def _release_identity_lock(self, reason: str, *, reset_liveness: bool = True):
        lock = self._identity_lock
        if lock is None:
            return
        self._identity_lock = None
        self._vote_buf.clear()
        if reset_liveness:
            self._cnn_scores.pop(lock.mssv, None)
            self._cnn_passed.pop(lock.mssv, None)
            self.anti_spoof.reset(lock.mssv)
        logger.info(
            "[AttendanceEngine] Identity lock released: %s (%s)",
            lock.mssv,
            reason,
        )

    def _resolve_locked_identity(
        self,
        observed_mssv: str | None,
        box: tuple[int, int, int, int],
        distance: float,
        now: float,
    ) -> _IdentityLock | None:
        """
        Resolve phase-two identity without trusting an Unknown face indefinitely.

        Unknown frames may continue the current challenge only while the box is
        spatially continuous and the same MSSV was confirmed recently.
        """
        lock = self._identity_lock
        if lock is None:
            return None

        if not self._identity_lock_is_usable(now):
            self._release_identity_lock("expired")
            return None

        if observed_mssv is not None and observed_mssv != lock.mssv:
            self._release_identity_lock("different identity")
            return None

        if observed_mssv == lock.mssv:
            lock.box = box
            lock.distance = float(distance)
            lock.last_confirmed_at = now
            return lock

        if not self._box_matches_identity_lock(box):
            self._release_identity_lock("face box changed")
            return None

        # Keep tracking the current face box, but Unknown never extends the
        # grace timer. The original MSSV must be recognized again promptly.
        lock.box = box
        return lock

    def _check_cnn(
        self,
        mssv: str,
        frame: np.ndarray,
        box: tuple[int, int, int, int],
    ) -> dict:
        """Run rolling CNN voting before the single-action challenge."""
        if not self.CNN_ENABLED:
            return {
                "passed": True,
                "state": "disabled",
                "score": 1.0,
                "votes": self.CNN_REQUIRED_VOTES,
                "samples": self.CNN_WINDOW,
            }

        if self.cnn_antispoof is None or not self.cnn_antispoof.available:
            return {
                "passed": not self.CNN_REQUIRED,
                "state": "error",
                "score": 0.0,
                "votes": 0,
                "samples": 0,
            }

        result = self.cnn_antispoof.predict_raw(frame, box)
        if result is None:
            if self._identity_lock is None:
                self.anti_spoof.reset(mssv)
            return {
                "passed": not self.CNN_REQUIRED,
                "state": "error",
                "score": 0.0,
                "votes": 0,
                "samples": 0,
            }

        score = float(result["real_score"])
        threshold = float(result["threshold"])
        scores = self._cnn_scores.setdefault(
            mssv,
            deque(maxlen=self.CNN_WINDOW),
        )
        scores.append(score)

        samples = len(scores)
        votes = sum(value >= threshold for value in scores)
        passed = samples == self.CNN_WINDOW and votes >= self.CNN_REQUIRED_VOTES
        was_passed = self._cnn_passed.get(mssv, False)

        if was_passed and not passed and self._identity_lock is None:
            self.anti_spoof.reset(mssv)
        self._cnn_passed[mssv] = passed

        if samples < self.CNN_WINDOW:
            state = "pending"
        elif passed:
            state = "passed"
        else:
            state = "spoof"

        return {
            "passed": passed,
            "state": state,
            "score": score,
            "votes": votes,
            "samples": samples,
        }

    def _cleanup_cnn(self, active_mssv: set[str]):
        """Drop liveness state when the recognized person leaves the frame."""
        stale = [mssv for mssv in self._cnn_scores if mssv not in active_mssv]
        for mssv in stale:
            self._cnn_scores.pop(mssv, None)
            self._cnn_passed.pop(mssv, None)
            self.anti_spoof.reset(mssv)

    def _reset_all_liveness(self):
        self._identity_lock = None
        self._cnn_scores.clear()
        self._cnn_passed.clear()
        self.anti_spoof.reset_all()

    def process_frame(
        self, frame: np.ndarray, ca_hoc_id: int, name_map: dict
    ) -> list[dict]:
        self._skip_cnt += 1
        self._frame_cnt += 1
        wall_now = time.time()
        if wall_now - self._fps_time >= 1.0:
            elapsed = wall_now - self._fps_time
            self._fps = round(self._frame_cnt / elapsed, 1)
            self._frame_cnt = 0
            self._fps_time = wall_now

        if self._skip_cnt % self.FRAME_SKIP != 0:
            return self._results

        raw = self.fe.recognize(frame)
        out = []
        active_keys: set[str] = set()
        active_mssv: set[str] = set()
        now = time.monotonic()

        if len(raw) > 1:
            self._vote_buf.clear()
            self._reset_all_liveness()
            for r in raw:
                box = r["box"]
                active_keys.add(self._box_key(box))
                out.append(
                    {
                        "box": box,
                        "label": "CHI 1 SV/LAN",
                        "color": (0, 140, 255),
                        "status": "multi_face",
                        "mssv": r.get("mssv"),
                    }
                )
            self._cleanup_vote_buf(active_keys)
            self._results = out
            return out

        if not raw:
            if self._identity_lock_is_usable(now):
                active_mssv.add(self._identity_lock.mssv)
            elif self._identity_lock is not None:
                self._release_identity_lock("face lost")
            self._cleanup_vote_buf(active_keys)
            self._cleanup_cnn(active_mssv)
            self._results = out
            return out

        for r in raw:
            observed_mssv = r["mssv"]
            dist = r["distance"]
            box = r["box"]
            active_keys.add(self._box_key(box))

            locked_identity = self._resolve_locked_identity(
                observed_mssv,
                box,
                dist,
                now,
            )
            if locked_identity is not None:
                mssv = locked_identity.mssv
                name_ascii = locked_identity.name_ascii
                dist = locked_identity.distance
            else:
                mssv = observed_mssv

            if not mssv:
                self._vote(box, None)
                out.append(
                    {
                        "box": box,
                        "label": "Unknown",
                        "color": (60, 60, 200),
                        "status": "unknown",
                        "mssv": None,
                    }
                )
                continue

            if locked_identity is None:
                name = name_map.get(mssv, mssv)
                name_ascii = self._ascii(name)
                class_status = self._get_class_status(mssv, ca_hoc_id)
                if class_status == "wrong_class":
                    self._vote(box, None)
                    out.append(
                        {
                            "box": box,
                            "label": f"{name_ascii} [SAI LOP]",
                            "color": (0, 140, 255),
                            "status": "wrong_class",
                            "mssv": mssv,
                        }
                    )
                    continue
                if class_status != "ok":
                    self._vote(box, None)
                    out.append(
                        {
                            "box": box,
                            "label": f"{name_ascii} [LOI LOP]",
                            "color": (60, 60, 200),
                            "status": "error",
                            "mssv": mssv,
                        }
                    )
                    continue
                if mssv in self.marked_in_session:
                    self._vote(box, None)
                    out.append(
                        {
                            "box": box,
                            "label": f"{name_ascii} [DA DD]",
                            "color": (200, 160, 30),
                            "status": "duplicate",
                            "mssv": mssv,
                        }
                    )
                    continue

                active_mssv.add(mssv)
                stable_mssv = self._vote(box, mssv)
                if stable_mssv is None:
                    out.append(
                        {
                            "box": box,
                            "label": f"{name_ascii} ...",
                            "color": (100, 100, 200),
                            "status": "voting",
                            "mssv": mssv,
                        }
                    )
                    continue
            else:
                active_mssv.add(mssv)
                stable_mssv = locked_identity.mssv

            cnn = self._check_cnn(stable_mssv, frame, box)
            if not cnn["passed"]:
                if locked_identity is not None:
                    self._release_identity_lock(f"CNN {cnn['state']}")
                if cnn["state"] == "error":
                    label = f"{name_ascii} - LOI CNN"
                    color = (60, 60, 200)
                    status = "cnn_error"
                elif cnn["state"] == "spoof":
                    label = (
                        f"{name_ascii} - NGHI GIA MAO "
                        f"({cnn['votes']}/{self.CNN_WINDOW})"
                    )
                    color = (0, 0, 220)
                    status = "cnn_spoof"
                else:
                    label = f"{name_ascii} - CNN " f"{cnn['samples']}/{self.CNN_WINDOW}"
                    color = (80, 160, 220)
                    status = "cnn_check"
                out.append(
                    {
                        "box": box,
                        "label": label,
                        "color": color,
                        "status": status,
                        "mssv": stable_mssv,
                    }
                )
                continue

            if self._identity_lock is None:
                self._acquire_identity_lock(
                    stable_mssv,
                    name_ascii,
                    box,
                    dist,
                    now,
                )


            spoof = self.anti_spoof.process(stable_mssv, frame, face_box=box)
            if not spoof["verified"]:
                challenge_label = spoof.get("status", "Xac thuc...")
                out.append(
                    {
                        "box": box,
                        "label": f"{name_ascii} - {challenge_label}",
                        "color": (30, 140, 220),
                        "status": "spoof_check",
                        "mssv": stable_mssv,
                    }
                )
                continue
            status = self.record(stable_mssv, ca_hoc_id)
            if status == "new":
                label = f"{name_ascii}  ({dist:.2f})"
                color = (30, 200, 100)
            elif status == "duplicate":
                label = f"{name_ascii} [DA DD]"
                color = (200, 160, 30)
            elif status == "wrong_class":
                label = f"{name_ascii} [SAI LOP]"
                color = (0, 140, 255)
            elif status == "voided":
                label = f"{name_ascii} [DA HUY]"
                color = (0, 100, 220)
            else:
                label = name_ascii
                color = (60, 60, 200)
            out.append(
                {
                    "box": box,
                    "label": label,
                    "color": color,
                    "status": status,
                    "mssv": stable_mssv,
                }
            )
            self._release_identity_lock(f"record result: {status}")

        self._cleanup_vote_buf(active_keys)
        self._cleanup_cnn(active_mssv)
        self._results = out
        return out

    def draw(self, frame: np.ndarray, results: list[dict]) -> np.ndarray:
        out = frame.copy()
        for r in results:
            x1, y1, x2, y2 = r["box"]
            color = r["color"]
            label = r["label"]
            status = r.get("status", "")
            thick = 3 if status == "new" else 2
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thick)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
            cv2.rectangle(out, (x1, y1 - th - 12), (x1 + tw + 8, y1), color, -1)
            cv2.putText(
                out,
                label,
                (x1 + 4, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (255, 255, 255),
                2,
            )
            if status == "new":
                cv2.putText(
                    out,
                    "OK!",
                    (x2 - 36, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (30, 220, 100),
                    2,
                )
            elif status == "duplicate":
                cv2.putText(
                    out,
                    "DA DD",
                    (x2 - 60, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (200, 160, 30),
                    2,
                )
            elif status == "wrong_class":
                cv2.putText(
                    out,
                    "SAI LOP",
                    (x2 - 76, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 140, 255),
                    2,
                )
            elif status == "voided":
                cv2.putText(
                    out,
                    "DA HUY",
                    (x2 - 68, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 100, 220),
                    2,
                )
            elif status == "multi_face":
                cv2.putText(
                    out,
                    "1 SV/LAN",
                    (x2 - 74, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 140, 255),
                    2,
                )
            elif status == "voting":
                cv2.putText(
                    out,
                    "...",
                    (x2 - 28, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (150, 150, 220),
                    2,
                )
            elif status == "cnn_check":
                cv2.putText(
                    out,
                    "CNN",
                    (x2 - 38, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (80, 160, 220),
                    2,
                )
            elif status == "cnn_spoof":
                cv2.putText(
                    out,
                    "SPOOF",
                    (x2 - 60, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 220),
                    2,
                )
            elif status == "cnn_error":
                cv2.putText(
                    out,
                    "CNN ERR",
                    (x2 - 70, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (60, 60, 200),
                    2,
                )

        ts = datetime.now().strftime("%H:%M:%S  %d/%m/%Y")
        cv2.putText(
            out, ts, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2
        )
        cv2.putText(
            out,
            f"FPS:{self._fps}",
            (out.shape[1] - 90, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 100),
            2,
        )
        return out

    @staticmethod
    def _ascii(text: str) -> str:
        import unicodedata

        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    def close(self):
        self.anti_spoof.close()
        if self.cnn_antispoof is not None:
            self.cnn_antispoof.close()
