# core/anti_spoof.py
import cv2
import logging
import time
import random
import numpy as np
from collections import deque
from dataclasses import dataclass
from threading import Lock

try:
    import mediapipe as mp

    MP_OK = True
except ImportError:
    MP_OK = False

logger = logging.getLogger(__name__)

# Landmark index MediaPipe
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
NOSE_TIP = 1
LEFT_EAR = 234
RIGHT_EAR = 454

# Danh sách thử thách
CHALLENGES = ["CHOP_MAT", "QUAY_TRAI", "QUAY_PHAI"]
CHALLENGE_LABELS = {
    "CHOP_MAT": "Chop mat 1 lan!",
    "QUAY_TRAI": "Quay dau sang TRAI!",
    "QUAY_PHAI": "Quay dau sang PHAI!",
}

def _choose_challenge(exclude: str | None = None) -> str:
    choices = [ch for ch in CHALLENGES if ch != exclude]
    return random.choice(choices or CHALLENGES)

def _make_state(challenge: str) -> dict:
    return {
        "verified": False,
        "verified_time": 0.0,
        "frames": 0,
        "challenge": challenge,
        "done": False,
        "rejected": False,
        "reject_reason": "",
        "generation": 0,
        # EAR (chớp mắt)
        "consec_closed": 0,
        "consec_open": 0,
        "blink_phase": "open",
        "blink_ready_frames": 0,
        "blink_closed_frames": 0,
        "blink_pose_anchor": None,
        "ear_raw": deque(maxlen=4),
        "ear_smooth": deque(maxlen=20),
        "static_frames": 0,
        # Adaptive EAR calibration
        "ear_baseline_samples": deque(maxlen=12),
        "ear_baseline": None,
        # Head movement observed during the blink challenge
        "blink_yaw_samples": deque(maxlen=20),
        # Yaw (quay đầu)
        "yaw_turn": deque(maxlen=5),
        "yaw_static": deque(maxlen=20),
        "yaw_raw_history": deque(maxlen=90),
        "yaw_center_samples": deque(maxlen=8),
        "yaw_center_baseline": None,
        "yaw_passed_center": False,
        # Trajectory tracking
        "yaw_history": deque(maxlen=90),
        "turn_phase": "center",
        "turn_phase_frame": 0,
        "peak_yaw": 0.0,
        "teleport_count": 0,
        "teleport_candidate_from": None,
        "teleport_candidate_to": None,
        "teleport_candidate_frames": 0,
        "turn_forward_steps": 0,
        "turn_return_steps": 0,
        "last_turn_yaw": 0.0,
    }

@dataclass(frozen=True)
class _FrameContext:
    state: dict
    challenge: str
    challenge_label: str
    generation: int

class AntiSpoof:
    # Ngưỡng EAR
    EAR_THRESH = 0.18
    EAR_OPEN_THRESH = 0.22
    EAR_CONSEC = 1
    EAR_OPEN_CONSEC = 2
    EAR_READY_CONSEC = 1
    BLINK_MAX_CLOSED_FRAMES = 14
    BLINK_MAX_POSE_DELTA = 0.25
    EAR_VAR_THRESH = 0.0004

    # A valid blink must include a small amount of natural head movement.
    BLINK_MIN_YAW_VAR = 0.08
    BLINK_MIN_YAW_SAMPLES = 3

    # Personal EAR calibration avoids rejecting users with naturally small eyes.
    EAR_BASELINE_FRAMES = 8  # số mẫu cần cho calibration
    EAR_THRESH_RATIO = 0.78  # personal_thresh = baseline × ratio
    EAR_OPEN_RATIO = 0.92  # personal_open = baseline × ratio
    EAR_MIN_BASELINE = 0.16  # EAR tối thiểu để coi là mắt mở
    EAR_BASELINE_MAX_STD = 0.04  # mẫu phải ổn định
    EAR_FLOOR_THRESH = 0.12  # sàn tuyệt đối cho thresh
    EAR_FLOOR_OPEN = 0.15  # sàn tuyệt đối cho open_thresh

    # Ngưỡng Yaw
    YAW_THRESH = 12.0
    YAW_CENTER_THRESH = 12.0
    YAW_CENTER_SAMPLES = 3
    YAW_CENTER_STABLE_SPAN = 10.0
    YAW_START_THRESH = 3.0
    YAW_RETURN_THRESH = 7.0
    YAW_RETURN_LIMIT = 90
    YAW_VAR_THRESH = 3.0

    # Trajectory
    YAW_TELEPORT_THRESH = 42.0
    YAW_TELEPORT_STABLE_SPAN = 20.0
    YAW_TELEPORT_CONFIRM_FRAMES = 3
    YAW_STEP_EPS = 0.20
    YAW_MIN_FORWARD_STEPS = 2
    YAW_MIN_RETURN_STEPS = 2
    YAW_MIN_PHASE_FRAMES = 4
    YAW_MAX_PHASE_FRAMES = 100
    YAW_MAX_BACKTRACK = 22.0

    # Static check
    STATIC_LIMIT = 45
    STATIC_CHECK_DELAY = 25

    # Timeout & TTL
    MAX_FRAMES = 300
    VERIFIED_TTL = 10.0

    # Baseline fallback
    BASELINE_FALLBACK_FRAME = 30

    def __init__(self):
        self._state: dict[str, dict] = {}
        self._detector = None
        self._mode = "none"
        self._state_lock = Lock()
        self._gen_counter = 0

        if not MP_OK:
            logger.warning("[AntiSpoof] Chua cai mediapipe")
            return
        try:
            mp_face = mp.solutions.face_mesh
            self._detector = mp_face.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._mode = "mediapipe"
            logger.info("[AntiSpoof] OK - v4-hardened, max_faces=1")
        except Exception:
            logger.exception("[AntiSpoof] Khong khoi tao duoc MediaPipe FaceMesh")

    def _new_state(self, challenge: str) -> dict:
        """Create a session state with a unique generation."""
        self._gen_counter += 1
        state = _make_state(challenge)
        state["generation"] = self._gen_counter
        return state

    def reset(self, mssv: str):
        challenge = _choose_challenge()
        with self._state_lock:
            self._state[mssv] = self._new_state(challenge)
        logger.info(
            "[AntiSpoof] %s: thu thach = %s",
            mssv,
            CHALLENGE_LABELS[challenge],
        )

    def reset_all(self):
        with self._state_lock:
            self._state.clear()

    def process(self, mssv: str, frame_bgr: np.ndarray, face_box: tuple = None) -> dict:
        if self._mode != "mediapipe" or self._detector is None:
            return {
                "verified": False,
                "status": "Can MediaPipe de xac thuc chong gia mao",
                "challenge": "",
            }

        context, early_result = self._begin_frame(mssv)
        if early_result is not None:
            return early_result

        if frame_bgr is None:
            return self._pending_result(context, status="Loi frame")

        detected = self._detect_landmarks(frame_bgr, face_box)
        if detected is None:
            return self._pending_result(context)

        if not self._is_current_context(mssv, context):
            return self._pending_result(context)

        face_lm, width, height = detected
        ear, raw_ear, avg_yaw, raw_yaw, pose_signature = self._update_observation(
            mssv,
            context.state,
            face_lm,
            width,
            height,
        )

        static_result = self._apply_static_guard(mssv, context.state)
        if static_result is not None:
            return static_result

        done = self._run_challenge(
            context.state,
            context.challenge,
            ear,
            avg_yaw,
            raw_yaw,
            pose_signature,
        )
        if done:
            verified = self._commit_verified(mssv, context, raw_ear, avg_yaw)
            if verified is not None:
                return verified
        return self._pending_result(context, raw_ear, avg_yaw)

    def _begin_frame(self, mssv: str) -> tuple[_FrameContext | None, dict | None]:
        """Prepare one frame and handle session lifecycle transitions."""
        with self._state_lock:
            if mssv not in self._state:
                challenge = _choose_challenge()
                self._state[mssv] = self._new_state(challenge)
                logger.info(
                    "[AntiSpoof] %s: thu thach = %s",
                    mssv,
                    CHALLENGE_LABELS[challenge],
                )
            state = self._state[mssv]

            if state.get("rejected"):
                reason = state.get("reject_reason", "Thu lai")
                old_challenge = state["challenge"]
                challenge = _choose_challenge(old_challenge)
                self._state[mssv] = self._new_state(challenge)
                logger.warning("[AntiSpoof] %s: reset sau nghi ngo gia mao", mssv)
                return None, {
                    "verified": False,
                    "status": reason,
                    "challenge": CHALLENGE_LABELS[challenge],
                }

            if state["verified"]:
                if time.time() - state["verified_time"] < self.VERIFIED_TTL:
                    return None, {
                        "verified": True,
                        "status": "THAT",
                        "challenge": state["challenge"],
                    }
                logger.info("[AntiSpoof] %s: het han - thu thach moi", mssv)
                challenge = _choose_challenge(state["challenge"])
                self._state[mssv] = self._new_state(challenge)
                state = self._state[mssv]
                logger.info(
                    "[AntiSpoof] %s: thu thach = %s",
                    mssv,
                    CHALLENGE_LABELS[challenge],
                )

            state["frames"] += 1
            if state["frames"] > self.MAX_FRAMES:
                challenge = _choose_challenge(state["challenge"])
                self._state[mssv] = self._new_state(challenge)
                new_ch = self._state[mssv]["challenge"]
                logger.info(
                    "[AntiSpoof] %s: thu thach = %s",
                    mssv,
                    CHALLENGE_LABELS[new_ch],
                )
                return None, {
                    "verified": False,
                    "status": "HET GIO - Thu lai",
                    "challenge": CHALLENGE_LABELS[new_ch],
                }

            challenge = state["challenge"]
            return (
                _FrameContext(
                    state=state,
                    challenge=challenge,
                    challenge_label=CHALLENGE_LABELS[challenge],
                    generation=state["generation"],
                ),
                None,
            )

    def _detect_landmarks(self, frame_bgr: np.ndarray, face_box: tuple):
        """Run MediaPipe and return the selected face landmarks."""
        rgb = self._to_rgb(frame_bgr)
        scale = 0.5
        small = cv2.resize(rgb, (0, 0), fx=scale, fy=scale)
        h, w = small.shape[:2]

        small.flags.writeable = False
        try:
            results = self._detector.process(small)
        except Exception:
            logger.exception("[AntiSpoof] MediaPipe process failed")
            return None
        finally:
            small.flags.writeable = True

        if not results.multi_face_landmarks:
            return None

        face_lm = self._select_face(results.multi_face_landmarks, face_box, scale, w, h)
        return face_lm, w, h

    def _is_current_context(self, mssv: str, context: _FrameContext) -> bool:
        """Return whether the session survived work performed outside the lock."""
        with self._state_lock:
            current = self._state.get(mssv)
            return (
                current is context.state
                and current.get("generation", 0) == context.generation
            )

    def _update_observation(
        self, mssv: str, state: dict, face_lm, width: int, height: int
    ) -> tuple:
        """Update EAR/yaw histories and return metrics for challenge checks."""
        ear = (
            self._ear(face_lm, LEFT_EYE, width, height)
            + self._ear(face_lm, RIGHT_EYE, width, height)
        ) / 2.0
        state["ear_raw"].append(ear)
        state["ear_smooth"].append(ear)
        raw_ear = float(np.mean(state["ear_raw"]))
        pose_signature = self._pose_signature(face_lm)
        self._calibrate_ear(mssv, state, ear)

        yaw = self._calc_yaw(face_lm, width, height)
        state["yaw_turn"].append(yaw)
        state["yaw_static"].append(yaw)
        avg_yaw_abs = float(np.mean(state["yaw_turn"]))
        self._calibrate_yaw_center(mssv, state, avg_yaw_abs)

        baseline = state["yaw_center_baseline"] or 0.0
        avg_yaw = avg_yaw_abs - baseline
        raw_yaw = yaw - baseline
        state["yaw_history"].append(avg_yaw)
        state["yaw_raw_history"].append(raw_yaw)

        if (
            state["yaw_center_baseline"] is not None
            and not state["yaw_passed_center"]
            and abs(avg_yaw) < self.YAW_CENTER_THRESH
        ):
            state["yaw_passed_center"] = True
            logger.info(
                "[AntiSpoof] %s: passed_center (avg_yaw=%.1f)",
                mssv,
                avg_yaw,
            )

        return ear, raw_ear, avg_yaw, raw_yaw, pose_signature

    def _calibrate_ear(self, mssv: str, state: dict, ear: float):
        if state["ear_baseline"] is not None or ear <= self.EAR_MIN_BASELINE:
            return

        state["ear_baseline_samples"].append(ear)
        samples = list(state["ear_baseline_samples"])
        if (
            len(samples) >= self.EAR_BASELINE_FRAMES
            and float(np.std(samples)) < self.EAR_BASELINE_MAX_STD
        ):
            state["ear_baseline"] = float(np.median(samples))
            logger.info(
                "[AntiSpoof] %s: EAR baseline = %.3f",
                mssv,
                state["ear_baseline"],
            )

    def _calibrate_yaw_center(self, mssv: str, state: dict, avg_yaw_abs: float):
        if (
            state["yaw_center_baseline"] is None
            and abs(avg_yaw_abs) < self.YAW_CENTER_THRESH
        ):
            state["yaw_center_samples"].append(avg_yaw_abs)
            samples = list(state["yaw_center_samples"])[-self.YAW_CENTER_SAMPLES :]
            if (
                len(samples) >= self.YAW_CENTER_SAMPLES
                and max(samples) - min(samples) <= self.YAW_CENTER_STABLE_SPAN
            ):
                state["yaw_center_baseline"] = float(np.median(samples))
                state["yaw_passed_center"] = True
                logger.info(
                    "[AntiSpoof] %s: passed_center (baseline=%.1f)",
                    mssv,
                    state["yaw_center_baseline"],
                )

        if (
            state["yaw_center_baseline"] is None
            and state["frames"] > self.BASELINE_FALLBACK_FRAME
        ):
            state["yaw_center_baseline"] = 0.0
            state["yaw_passed_center"] = True
            logger.info(
                "[AntiSpoof] %s: baseline fallback = 0 (frame %d)",
                mssv,
                state["frames"],
            )

    def _apply_static_guard(self, mssv: str, state: dict) -> dict | None:
        if len(state["ear_smooth"]) < 10 or state["frames"] <= self.STATIC_CHECK_DELAY:
            return None

        is_static, ear_var, yaw_var = self._static_metrics(state)
        if not is_static:
            state["static_frames"] = 0
            return None

        state["static_frames"] += 1
        if state["static_frames"] <= self.STATIC_LIMIT:
            return None

        logger.warning(
            "[AntiSpoof] %s: anh tinh (ear_var=%.5f, yaw_var=%.2f)",
            mssv,
            ear_var,
            yaw_var,
        )

        with self._state_lock:
            challenge = _choose_challenge(state["challenge"])
            self._state[mssv] = self._new_state(challenge)
        logger.info(
            "[AntiSpoof] %s: thu thach = %s",
            mssv,
            CHALLENGE_LABELS[challenge],
        )
        return {
            "verified": False,
            "status": "ANH GIA! Thu lai!",
            "challenge": challenge,
        }

    def _run_challenge(
        self,
        state: dict,
        challenge: str,
        ear: float,
        avg_yaw: float,
        raw_yaw: float,
        pose_signature,
    ) -> bool:
        if challenge == "CHOP_MAT":
            state["blink_yaw_samples"].append(raw_yaw)
            if not self._check_teleport(state, state["yaw_raw_history"]):
                return self._check_blink(state, ear, pose_signature)
            return False
        if challenge == "QUAY_TRAI":
            return self._check_turn(state, avg_yaw, direction="left")
        if challenge == "QUAY_PHAI":
            return self._check_turn(state, avg_yaw, direction="right")
        return False

    def _commit_verified(
        self, mssv: str, context: _FrameContext, raw_ear: float, avg_yaw: float
    ) -> dict | None:
        """Atomically verify the same session that produced this frame."""
        with self._state_lock:
            current = self._state.get(mssv)
            if (
                current is not context.state
                or current.get("generation", 0) != context.generation
            ):
                return None
            current["verified"] = True
            current["verified_time"] = time.time()

        logger.info(
            "[AntiSpoof] %s: THAT - challenge=%s",
            mssv,
            context.challenge,
        )
        return {
            "verified": True,
            "status": "THAT",
            "challenge": context.challenge,
            "ear": raw_ear,
            "yaw": avg_yaw,
        }

    @staticmethod
    def _pending_result(
        context: _FrameContext,
        raw_ear: float | None = None,
        avg_yaw: float | None = None,
        status: str | None = None,
    ) -> dict:
        result = {
            "verified": False,
            "status": status or context.challenge_label,
            "challenge": context.challenge,
        }
        if raw_ear is not None:
            result["ear"] = raw_ear
        if avg_yaw is not None:
            result["yaw"] = avg_yaw
        return result

    # Kiểm tra chớp mắt
    def _check_blink(self, state: dict, raw_ear: float, pose_signature=None) -> bool:
        if state.get("rejected"):
            return False

        # Prefer personal thresholds after enough stable open-eye samples.
        ear_baseline = state.get("ear_baseline")
        if ear_baseline is not None:
            thresh = max(
                self.EAR_FLOOR_THRESH,
                min(self.EAR_THRESH, ear_baseline * self.EAR_THRESH_RATIO),
            )
            open_thresh = max(
                self.EAR_FLOOR_OPEN,
                min(self.EAR_OPEN_THRESH, ear_baseline * self.EAR_OPEN_RATIO),
            )
        else:
            thresh = self.EAR_THRESH
            open_thresh = self.EAR_OPEN_THRESH

        phase = state["blink_phase"]

        if phase == "open":
            if raw_ear >= open_thresh:
                state["blink_ready_frames"] += 1
                state["consec_closed"] = 0
                if pose_signature is not None:
                    state["blink_pose_anchor"] = np.asarray(
                        pose_signature, dtype=float
                    ).copy()
                return False

            if raw_ear < thresh:
                if state["blink_ready_frames"] < self.EAR_READY_CONSEC:
                    state["consec_closed"] = 0
                    return False

                if self._blink_pose_jumped(state, pose_signature):
                    self._reset_blink(state)
                    logger.warning("[AntiSpoof] blink pose jump - nghi doi anh")
                    return False

                state["consec_closed"] += 1
                if state["consec_closed"] >= self.EAR_CONSEC:
                    state["blink_phase"] = "closed"
                    state["consec_open"] = 0
                    state["blink_closed_frames"] = 0
                    logger.debug(
                        "[AntiSpoof] blink: mat nham (EAR=%.3f, thresh=%.3f)",
                        raw_ear,
                        thresh,
                    )
            else:
                state["consec_closed"] = 0

        elif phase == "closed":
            state["blink_closed_frames"] += 1
            if state["blink_closed_frames"] > self.BLINK_MAX_CLOSED_FRAMES:
                self._reset_blink(state)
                logger.info("[AntiSpoof] blink giu mat nham qua lau - reset")
                return False

            if self._blink_pose_jumped(state, pose_signature):
                self._reset_blink(state)
                logger.warning("[AntiSpoof] blink pose jump - nghi doi anh")
                return False

            if raw_ear > open_thresh:
                state["consec_open"] += 1
                if state["consec_open"] >= self.EAR_OPEN_CONSEC:
                    yaw_samples = list(state.get("blink_yaw_samples", []))
                    if len(yaw_samples) >= self.BLINK_MIN_YAW_SAMPLES:
                        yaw_var = float(np.var(yaw_samples))
                        if yaw_var < self.BLINK_MIN_YAW_VAR:
                            self._reset_blink(state)
                            logger.warning(
                                "[AntiSpoof] blink yaw qua tinh "
                                "(var=%.4f) - nghi anh",
                                yaw_var,
                            )
                            return False

                    state["blink_phase"] = "open"
                    state["done"] = True
                    logger.debug(
                        "[AntiSpoof] blink: mat mo (EAR=%.3f) - DONE",
                        raw_ear,
                    )
                    return True
            else:
                state["consec_open"] = 0

        return state["done"]

    def _static_metrics(self, state: dict) -> tuple[bool, float, float]:
        ear_var = float(np.var(list(state["ear_smooth"])))
        yaw_var = (
            float(np.var(list(state["yaw_static"])))
            if len(state["yaw_static"]) >= 10
            else float("inf")
        )
        is_static = ear_var < self.EAR_VAR_THRESH and yaw_var < self.YAW_VAR_THRESH
        return is_static, ear_var, yaw_var

    def _blink_pose_jumped(self, state: dict, pose_signature) -> bool:
        anchor = state.get("blink_pose_anchor")
        if anchor is None or pose_signature is None:
            return False
        delta = float(np.linalg.norm(np.asarray(pose_signature, dtype=float) - anchor))
        return delta > self.BLINK_MAX_POSE_DELTA

    @staticmethod
    def _reset_blink(state: dict):
        state["blink_phase"] = "open"
        state["consec_closed"] = 0
        state["consec_open"] = 0
        state["blink_ready_frames"] = 0
        state["blink_closed_frames"] = 0
        state["blink_pose_anchor"] = None
        state["blink_yaw_samples"].clear()

    # Kiểm tra quay đầu
    def _check_turn(self, state: dict, avg_yaw: float, direction: str) -> bool:
        if state.get("rejected"):
            return False

        sign = -1 if direction == "left" else 1
        history = state["yaw_history"]
        raw_history = state["yaw_raw_history"]
        phase = state["turn_phase"]
        signed_yaw = sign * avg_yaw
        signed_raw_yaw = sign * float(raw_history[-1]) if raw_history else signed_yaw

        if self._check_teleport(state, raw_history):
            return False

        if phase == "center":
            if (
                state["yaw_center_baseline"] is not None
                and abs(avg_yaw) < self.YAW_CENTER_THRESH
            ):
                state["yaw_passed_center"] = True

            moving = state["yaw_passed_center"] and signed_yaw > self.YAW_START_THRESH

            if moving:
                state["turn_phase"] = "moving"
                state["turn_phase_frame"] = state["frames"]
                state["peak_yaw"] = signed_yaw
                state["turn_forward_steps"] = 0
                state["turn_return_steps"] = 0
                state["last_turn_yaw"] = signed_raw_yaw
                logger.debug(
                    "[AntiSpoof] phase center -> moving (yaw=%.1f)",
                    signed_yaw,
                )
            return False

        elif phase == "moving":
            frames_in = state["frames"] - state["turn_phase_frame"]

            step_delta = signed_raw_yaw - state["last_turn_yaw"]
            if step_delta >= self.YAW_STEP_EPS:
                state["turn_forward_steps"] += 1
            state["last_turn_yaw"] = signed_raw_yaw

            if signed_yaw > state["peak_yaw"]:
                state["peak_yaw"] = signed_yaw

            if frames_in < self.YAW_MIN_PHASE_FRAMES:
                return False

            if frames_in > self.YAW_MAX_PHASE_FRAMES:
                logger.info("[AntiSpoof] moving timeout (%df) - reset", frames_in)
                self._reset_turn_phase(state)
                return False

            if len(history) >= 5:
                recent = [float(y) for y in list(history)[-5:]]
                signed = [sign * y for y in recent]
                backtrack = max(signed) - min(signed)
                if backtrack > self.YAW_MAX_BACKTRACK and signed_yaw < self.YAW_THRESH:
                    logger.warning(
                        "[AntiSpoof] backtrack=%.1f - dao dong bat thuong",
                        backtrack,
                    )
                    self._reset_turn_phase(state)
                    return False

            if signed_yaw >= self.YAW_THRESH:
                if state["turn_forward_steps"] < self.YAW_MIN_FORWARD_STEPS:
                    logger.info(
                        "[AntiSpoof] forward_steps=%d qua it - reset",
                        state["turn_forward_steps"],
                    )
                    self._reset_turn_phase(state)
                    return False

                state["turn_phase"] = "peak"
                state["turn_phase_frame"] = state["frames"]
                state["turn_return_steps"] = 0
                state["last_turn_yaw"] = signed_raw_yaw
                logger.debug(
                    "[AntiSpoof] phase moving -> peak (peak=%.1f)",
                    state["peak_yaw"],
                )
            return False

        elif phase == "peak":
            frames_in = state["frames"] - state["turn_phase_frame"]

            if frames_in > self.YAW_RETURN_LIMIT:
                logger.info("[AntiSpoof] peak timeout - reset")
                self._reset_turn_phase(state)
                return False

            step_delta = signed_raw_yaw - state["last_turn_yaw"]
            if step_delta <= -self.YAW_STEP_EPS:
                state["turn_return_steps"] += 1
            state["last_turn_yaw"] = signed_raw_yaw

            if signed_yaw > state["peak_yaw"] + self.YAW_MAX_BACKTRACK:
                logger.warning("[AntiSpoof] quay sai huong khi ve - reset")
                self._reset_turn_phase(state)
                return False

            if abs(avg_yaw) < self.YAW_RETURN_THRESH:
                if state["turn_return_steps"] < self.YAW_MIN_RETURN_STEPS:
                    logger.warning(
                        "[AntiSpoof] return_steps=%d qua it - nghi doi anh",
                        state["turn_return_steps"],
                    )
                    self._reset_turn_phase(state)
                    return False
                state["turn_phase"] = "done"
                logger.debug("[AntiSpoof] quay ve trung tam - PASS")
                return True

        return False

    def _check_teleport(self, state: dict, raw_history: deque) -> bool:
        if len(raw_history) < 4:
            return False

        values = [float(y) for y in raw_history]
        current = float(np.median(values[-3:]))
        previous = float(np.median(values[-4:-1]))
        origin = state["teleport_candidate_from"]
        target = state["teleport_candidate_to"]

        if origin is not None and target is not None:
            near_target = abs(current - target) <= self.YAW_TELEPORT_STABLE_SPAN
            far_from_origin = abs(current - origin) > self.YAW_TELEPORT_THRESH

            if near_target and far_from_origin:
                state["teleport_candidate_frames"] += 1
                if (
                    state["teleport_candidate_frames"]
                    >= self.YAW_TELEPORT_CONFIRM_FRAMES
                ):
                    delta = abs(target - origin)
                    state["teleport_count"] += 1
                    self._clear_teleport_candidate(state)
                    logger.warning(
                        "[AntiSpoof] TELEPORT confirmed delta=%.1f count=%d",
                        delta,
                        state["teleport_count"],
                    )
                    self._reset_turn_phase(state)
                    if state["teleport_count"] >= 2:
                        state["rejected"] = True
                        state["reject_reason"] = "NGHI NGO GIA MAO - Thu lai"
                        logger.warning("[AntiSpoof] 2x teleport - tu choi session nay")
                return True

            logger.debug("[AntiSpoof] yaw spike ignored")
            self._clear_teleport_candidate(state)
            return True

        delta = abs(current - previous)
        if delta > self.YAW_TELEPORT_THRESH:
            state["teleport_candidate_from"] = previous
            state["teleport_candidate_to"] = current
            state["teleport_candidate_frames"] = 1
            logger.debug("[AntiSpoof] teleport candidate delta=%.1f", delta)
            return True
        return False

    @staticmethod
    def _clear_teleport_candidate(state: dict):
        state["teleport_candidate_from"] = None
        state["teleport_candidate_to"] = None
        state["teleport_candidate_frames"] = 0

    @staticmethod
    def _reset_turn_phase(state: dict):
        state["turn_phase"] = "center"
        state["turn_phase_frame"] = state["frames"]
        state["peak_yaw"] = 0.0
        state["turn_forward_steps"] = 0
        state["turn_return_steps"] = 0
        state["last_turn_yaw"] = 0.0

    #Tính Yaw 
    @staticmethod
    def _calc_yaw(lm, w: int, h: int) -> float:
        nose = np.array([lm[NOSE_TIP].x * w, lm[NOSE_TIP].y * h])
        l_ear = np.array([lm[LEFT_EAR].x * w, lm[LEFT_EAR].y * h])
        r_ear = np.array([lm[RIGHT_EAR].x * w, lm[RIGHT_EAR].y * h])

        dist_l = np.linalg.norm(nose - l_ear)
        dist_r = np.linalg.norm(nose - r_ear)
        total = dist_l + dist_r
        if total < 1e-6:
            return 0.0
        return float((dist_r - dist_l) / total * 90)

    @staticmethod
    def _pose_signature(lm) -> np.ndarray:
        indices = (NOSE_TIP, LEFT_EAR, RIGHT_EAR, 10, 152)
        return np.asarray(
            [(lm[i].x, lm[i].y) for i in indices],
            dtype=float,
        ).reshape(-1)

    #EAR
    @staticmethod
    def _ear(lm, indices: list, w: int, h: int) -> float:
        pts = [np.array([lm[i].x * w, lm[i].y * h]) for i in indices]
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        hh = np.linalg.norm(pts[0] - pts[3])
        return (v1 + v2) / (2 * hh) if hh > 1e-6 else 0.3

    @staticmethod
    def _to_rgb(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 3 and frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _select_face(face_landmarks_list, face_box, scale, w, h):
        if len(face_landmarks_list) == 1 or face_box is None:
            return face_landmarks_list[0].landmark
        x1, y1, x2, y2 = face_box
        cx = ((x1 + x2) / 2) * scale
        cy = ((y1 + y2) / 2) * scale
        best_lm, best_d = face_landmarks_list[0].landmark, float("inf")
        for fl in face_landmarks_list:
            lm = fl.landmark
            d = (lm[1].x * w - cx) ** 2 + (lm[1].y * h - cy) ** 2
            if d < best_d:
                best_d, best_lm = d, lm
        return best_lm

    def close(self):
        if self._detector:
            self._detector.close()
