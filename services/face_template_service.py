from __future__ import annotations

from dataclasses import dataclass
import logging
import sqlite3

import numpy as np

from core.database import Database


logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 128
EMBEDDING_DTYPE = np.float64
EMBEDDING_DTYPE_NAME = "float64"
MODEL_NAME = "dlib_face_recognition_resnet_model_v1"
MODEL_VERSION = "1"


@dataclass(frozen=True)
class FaceTemplate:
    id: int
    mssv: str
    embedding: np.ndarray
    sample_index: int


class FaceTemplateService:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def serialize_embedding(embedding: np.ndarray) -> bytes:
        arr = np.asarray(embedding, dtype=EMBEDDING_DTYPE)

        if arr.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                f"Embedding phải có {EMBEDDING_DIMENSION} phần tử"
            )

        if not np.isfinite(arr).all():
            raise ValueError("Embedding chứa NaN hoặc vô hạn")

        return arr.tobytes(order="C")

    @staticmethod
    def deserialize_embedding(
        blob: bytes,
        dimension: int,
        dtype_name: str,
    ) -> np.ndarray:
        if dimension != EMBEDDING_DIMENSION:
            raise ValueError("Embedding không đúng số chiều")

        dtype_map = {
            "float64": np.float64,
            "float32": np.float32,
        }
        dtype = dtype_map.get(dtype_name)

        if dtype is None:
            raise ValueError("Kiểu embedding không hợp lệ")

        arr = np.frombuffer(bytes(blob), dtype=dtype)

        if arr.size != dimension or not np.isfinite(arr).all():
            raise ValueError("BLOB embedding không hợp lệ")

        return arr.astype(np.float64, copy=True)

    def load_active_templates(self) -> list[FaceTemplate]:
        with self.db.conn() as c:
            rows = c.execute("""
                SELECT mkm.id,
                       mkm.mssv,
                       mkm.embedding,
                       mkm.embeddingDimension,
                       mkm.embeddingDtype,
                       mkm.sampleIndex
                FROM MauKhuonMat mkm
                JOIN SinhVien sv ON sv.mssv = mkm.mssv
                WHERE mkm.isActive = 1
                  AND sv.trangThai = 'DANG_HOC'
                ORDER BY mkm.mssv, mkm.sampleIndex
            """).fetchall()

        result = []

        for row in rows:
            try:
                embedding = self.deserialize_embedding(
                    row["embedding"],
                    row["embeddingDimension"],
                    row["embeddingDtype"],
                )
            except ValueError as exc:
                logger.error(
                    "Bỏ qua mẫu khuôn mặt id=%s: %s",
                    row["id"],
                    exc,
                )
                continue

            result.append(
                FaceTemplate(
                    id=row["id"],
                    mssv=str(row["mssv"]),
                    embedding=embedding,
                    sample_index=row["sampleIndex"],
                )
            )

        return result

    def replace_samples(
        self,
        mssv: str,
        samples: list[dict],
        actor_username: str = "",
    ) -> int:
        mssv = str(mssv).strip()

        if not mssv:
            raise ValueError("MSSV không được để trống")

        if not samples:
            raise ValueError("Danh sách mẫu khuôn mặt không được rỗng")

        rows = []

        for sample_index, sample in enumerate(samples, start=1):
            rows.append((
                mssv,
                sqlite3.Binary(
                    self.serialize_embedding(sample["embedding"])
                ),
                EMBEDDING_DIMENSION,
                EMBEDDING_DTYPE_NAME,
                sample_index,
                MODEL_NAME,
                MODEL_VERSION,
                sample.get("brightness"),
                sample.get("blurVariance"),
                sample.get("faceWidth"),
                sample.get("faceHeight"),
            ))

        with self.db.conn() as c:
            # Khóa ghi trước khi kiểm tra quyền/trạng thái để phân công lớp
            # hoặc nghiệp vụ thôi học không thể chen giữa kiểm tra và INSERT.
            c.execute("BEGIN IMMEDIATE")
            actor_username = str(actor_username or "").strip()
            if actor_username:
                student = c.execute(
                    """
                    SELECT sv.trangThai
                    FROM SinhVien sv
                    JOIN LopHoc lh ON lh.maLop = sv.maLop
                    JOIN GiangVien gv
                      ON gv.id = lh.giangVienChuNhiemId
                    JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                    WHERE sv.mssv = ?
                      AND lower(tk.username) = lower(?)
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                    """,
                    (mssv, actor_username),
                ).fetchone()
                if student is None:
                    raise PermissionError(
                        "Bạn không có quyền đăng ký khuôn mặt cho "
                        "sinh viên này"
                    )
            else:
                student = c.execute(
                    "SELECT trangThai FROM SinhVien WHERE mssv = ?",
                    (mssv,),
                ).fetchone()

            if student is None:
                raise ValueError(f"Không tìm thấy sinh viên '{mssv}'")
            if student["trangThai"] != "DANG_HOC":
                raise ValueError(
                    "Không thể đăng ký khuôn mặt cho sinh viên không ở "
                    "trạng thái Đang học"
                )

            # DELETE + INSERT cùng một transaction.
            c.execute("DELETE FROM MauKhuonMat WHERE mssv = ?", (mssv,))

            c.executemany("""
                INSERT INTO MauKhuonMat (
                    mssv, embedding, embeddingDimension, embeddingDtype,
                    sampleIndex, modelName, modelVersion,
                    brightness, blurVariance, faceWidth, faceHeight
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

        return len(rows)

    def delete_samples(self, mssv: str) -> int:
        with self.db.conn() as c:
            cursor = c.execute(
                "DELETE FROM MauKhuonMat WHERE mssv = ?",
                (str(mssv),),
            )

        return cursor.rowcount
