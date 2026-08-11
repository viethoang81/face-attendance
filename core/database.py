from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
BASE_DIR = (
    MODULE_DIR.parent if MODULE_DIR.name.lower() == "core" else MODULE_DIR
)
DB_PATH = BASE_DIR / "data" / "students.db"
SCHEMA_VERSION = 3
MIN_MIGRATABLE_SCHEMA_VERSION = 2

class Database:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def conn(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self):
        self._assert_database_is_compatible()

        with self.conn() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS SchemaVersion (
                    version     INTEGER PRIMARY KEY,
                    appliedAt   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS TaiKhoan (
                    id                  INTEGER PRIMARY KEY,
                    username            TEXT NOT NULL
                                            COLLATE NOCASE
                                            UNIQUE
                                            CHECK (
                                                username = trim(username)
                                                AND length(username)
                                                    BETWEEN 3 AND 40
                                            ),
                    passwordHash        TEXT NOT NULL
                                            CHECK (
                                                length(trim(passwordHash)) > 0
                                            ),
                    passwordSalt        TEXT NOT NULL
                                            CHECK (
                                                length(trim(passwordSalt)) > 0
                                            ),
                    hoTen               TEXT NOT NULL
                                            CHECK (
                                                length(trim(hoTen)) >= 3
                                            ),
                    email               TEXT NOT NULL DEFAULT '',
                    soDienThoai         TEXT NOT NULL DEFAULT '',
                    vaiTro              TEXT NOT NULL
                                            CHECK (
                                                vaiTro IN (
                                                    'Admin',
                                                    'GiangVien'
                                                )
                                            ),
                    isActive            INTEGER NOT NULL DEFAULT 1
                                            CHECK (isActive IN (0, 1)),
                    failedAttempts      INTEGER NOT NULL DEFAULT 0
                                            CHECK (failedAttempts >= 0),
                    lockedUntil         TEXT NOT NULL DEFAULT '',
                    lastLoginAt         TEXT NOT NULL DEFAULT '',
                    mustChangePassword  INTEGER NOT NULL DEFAULT 1
                                            CHECK (
                                                mustChangePassword IN (0, 1)
                                            ),
                    passwordIterations  INTEGER NOT NULL DEFAULT 260000
                                            CHECK (
                                                passwordIterations >= 100000
                                            ),
                    passwordChangedAt   TEXT NOT NULL DEFAULT '',
                    createdAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,
                    updatedAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,

                    CHECK (
                        email = ''
                        OR (
                            email = trim(email)
                            AND instr(email, '@') > 1
                        )
                    ),
                    CHECK (
                        soDienThoai = ''
                        OR soDienThoai NOT GLOB '*[^0-9]*'
                    )
                );

                CREATE TABLE IF NOT EXISTS GiangVien (
                    id              INTEGER PRIMARY KEY,
                    taiKhoanId      INTEGER NOT NULL UNIQUE,
                    maGV            TEXT NOT NULL
                                        COLLATE NOCASE
                                        UNIQUE
                                        CHECK (
                                            maGV = trim(maGV)
                                            AND length(maGV) > 0
                                        ),
                    gioiTinh        TEXT NOT NULL
                                        CHECK (
                                            gioiTinh IN ('Nam', 'Nữ', 'Khác')
                                        ),
                    ngaySinh        TEXT NOT NULL
                                        CHECK (
                                            length(ngaySinh) = 10
                                            AND date(
                                                ngaySinh,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngaySinh,
                                                '+0 days'
                                            ) = ngaySinh
                                        ),
                    boMon           TEXT NOT NULL
                                        CHECK (
                                            length(trim(boMon)) > 0
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (taiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS LopHoc (
                    maLop                   TEXT NOT NULL
                                                COLLATE NOCASE
                                                PRIMARY KEY
                                                CHECK (
                                                    maLop = trim(maLop)
                                                    AND length(maLop) > 0
                                                ),
                    tenLop                  TEXT NOT NULL
                                                COLLATE NOCASE
                                                UNIQUE
                                                CHECK (
                                                    length(trim(tenLop)) > 0
                                                ),
                    khoaHoc                 TEXT NOT NULL
                                                CHECK (
                                                    khoaHoc
                                                        GLOB '[0-9][0-9][0-9][0-9]'
                                                ),
                    khoa                    TEXT NOT NULL
                                                CHECK (
                                                    length(trim(khoa)) > 0
                                                ),
                    giangVienChuNhiemId     INTEGER,
                    createdAt               TEXT NOT NULL
                                                DEFAULT CURRENT_TIMESTAMP,
                    updatedAt               TEXT NOT NULL
                                                DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (giangVienChuNhiemId)
                        REFERENCES GiangVien(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS SinhVien (
                    mssv            TEXT NOT NULL
                                        COLLATE NOCASE
                                        PRIMARY KEY
                                        CHECK (
                                            mssv = trim(mssv)
                                            AND length(mssv)
                                                BETWEEN 1 AND 30
                                        ),
                    hoTen           TEXT NOT NULL
                                        CHECK (
                                            length(trim(hoTen)) >= 3
                                        ),
                    ngaySinh        TEXT NOT NULL
                                        CHECK (
                                            length(ngaySinh) = 10
                                            AND date(
                                                ngaySinh,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngaySinh,
                                                '+0 days'
                                            ) = ngaySinh
                                        ),
                    gioiTinh        TEXT NOT NULL
                                        CHECK (
                                            gioiTinh IN ('Nam', 'Nữ', 'Khác')
                                        ),
                    maLop           TEXT NOT NULL COLLATE NOCASE,
                    email           TEXT NOT NULL
                                        COLLATE NOCASE
                                        UNIQUE
                                        CHECK (
                                            email = trim(email)
                                            AND instr(email, '@') > 1
                                        ),
                    soDienThoai     TEXT NOT NULL UNIQUE
                                        CHECK (
                                            length(soDienThoai)
                                                BETWEEN 10 AND 11
                                            AND soDienThoai
                                                NOT GLOB '*[^0-9]*'
                                        ),
                    trangThai       TEXT NOT NULL DEFAULT 'DANG_HOC'
                                        CHECK (
                                            trangThai IN (
                                                'DANG_HOC',
                                                'BAO_LUU',
                                                'DINH_CHI',
                                                'THOI_HOC',
                                                'TOT_NGHIEP'
                                            )
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (maLop)
                        REFERENCES LopHoc(maLop)
                        ON UPDATE CASCADE
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS MonHoc (
                    maMon           TEXT NOT NULL
                                        COLLATE NOCASE
                                        PRIMARY KEY
                                        CHECK (
                                            maMon = trim(maMon)
                                            AND length(maMon) > 0
                                        ),
                    tenMon          TEXT NOT NULL
                                        COLLATE NOCASE
                                        UNIQUE
                                        CHECK (
                                            length(trim(tenMon)) > 0
                                        ),
                    soTiet          INTEGER NOT NULL DEFAULT 45
                                        CHECK (soTiet BETWEEN 1 AND 300),
                    tiLeToiThieu    INTEGER NOT NULL DEFAULT 75
                                        CHECK (
                                            tiLeToiThieu BETWEEN 0 AND 100
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS NamHoc (
                    id              INTEGER PRIMARY KEY,
                    tenNamHoc       TEXT NOT NULL
                                        COLLATE NOCASE
                                        UNIQUE
                                        CHECK (
                                            length(trim(tenNamHoc)) > 0
                                        ),
                    ngayBatDau      TEXT NOT NULL
                                        CHECK (
                                            length(ngayBatDau) = 10
                                            AND date(
                                                ngayBatDau,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngayBatDau,
                                                '+0 days'
                                            ) = ngayBatDau
                                        ),
                    ngayKetThuc     TEXT NOT NULL
                                        CHECK (
                                            length(ngayKetThuc) = 10
                                            AND date(
                                                ngayKetThuc,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngayKetThuc,
                                                '+0 days'
                                            ) = ngayKetThuc
                                        ),
                    trangThai       TEXT NOT NULL
                                        DEFAULT 'SAP_DIEN_RA'
                                        CHECK (
                                            trangThai IN (
                                                'SAP_DIEN_RA',
                                                'DANG_DIEN_RA',
                                                'DA_KET_THUC'
                                            )
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    CHECK (ngayBatDau < ngayKetThuc)
                );

                CREATE TABLE IF NOT EXISTS HocKy (
                    id              INTEGER PRIMARY KEY,
                    namHocId        INTEGER NOT NULL,
                    tenHocKy        TEXT NOT NULL COLLATE NOCASE
                                        CHECK (
                                            length(trim(tenHocKy)) > 0
                                        ),
                    ngayBatDau      TEXT NOT NULL
                                        CHECK (
                                            length(ngayBatDau) = 10
                                            AND date(
                                                ngayBatDau,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngayBatDau,
                                                '+0 days'
                                            ) = ngayBatDau
                                        ),
                    ngayKetThuc     TEXT NOT NULL
                                        CHECK (
                                            length(ngayKetThuc) = 10
                                            AND date(
                                                ngayKetThuc,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngayKetThuc,
                                                '+0 days'
                                            ) = ngayKetThuc
                                        ),
                    trangThai       TEXT NOT NULL
                                        DEFAULT 'SAP_DIEN_RA'
                                        CHECK (
                                            trangThai IN (
                                                'SAP_DIEN_RA',
                                                'DANG_DIEN_RA',
                                                'DA_KET_THUC'
                                            )
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (namHocId)
                        REFERENCES NamHoc(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,

                    UNIQUE (namHocId, tenHocKy),
                    CHECK (ngayBatDau < ngayKetThuc)
                );

                CREATE TABLE IF NOT EXISTS LopHocPhan (
                    id                  INTEGER PRIMARY KEY,
                    maLopHocPhan        TEXT NOT NULL
                                            COLLATE NOCASE
                                            UNIQUE
                                            CHECK (
                                                maLopHocPhan
                                                    = trim(maLopHocPhan)
                                                AND length(maLopHocPhan) > 0
                                            ),
                    maMon               TEXT NOT NULL COLLATE NOCASE,
                    hocKyId             INTEGER NOT NULL,
                    tenLopHocPhan       TEXT NOT NULL
                                            CHECK (
                                                length(
                                                    trim(tenLopHocPhan)
                                                ) > 0
                                            ),
                    nhom                TEXT NOT NULL DEFAULT '01'
                                            CHECK (
                                                length(trim(nhom)) > 0
                                            ),
                    siSoToiDa           INTEGER NOT NULL DEFAULT 60
                                            CHECK (
                                                siSoToiDa
                                                    BETWEEN 1 AND 1000
                                            ),
                    giangVienId         INTEGER,
                    trangThai           TEXT NOT NULL
                                            DEFAULT 'MO_DANG_KY'
                                            CHECK (
                                                trangThai IN (
                                                    'MO_DANG_KY',
                                                    'DANG_HOC',
                                                    'DA_KET_THUC',
                                                    'DA_HUY'
                                                )
                                            ),
                    createdAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,
                    updatedAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (maMon)
                        REFERENCES MonHoc(maMon)
                        ON UPDATE CASCADE
                        ON DELETE RESTRICT,
                    FOREIGN KEY (hocKyId)
                        REFERENCES HocKy(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,
                    FOREIGN KEY (giangVienId)
                        REFERENCES GiangVien(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS DangKyHocPhan (
                    id              INTEGER PRIMARY KEY,
                    mssv            TEXT NOT NULL COLLATE NOCASE,
                    lopHocPhanId    INTEGER NOT NULL,
                    ngayDangKy      TEXT NOT NULL
                                        CHECK (
                                            length(ngayDangKy) = 10
                                            AND date(
                                                ngayDangKy,
                                                '+0 days'
                                            ) IS NOT NULL
                                            AND date(
                                                ngayDangKy,
                                                '+0 days'
                                            ) = ngayDangKy
                                        ),
                    ngayKetThuc     TEXT NOT NULL DEFAULT ''
                                        CHECK (
                                            ngayKetThuc = ''
                                            OR (
                                                length(ngayKetThuc) = 10
                                                AND date(
                                                    ngayKetThuc,
                                                    '+0 days'
                                                ) IS NOT NULL
                                                AND date(
                                                    ngayKetThuc,
                                                    '+0 days'
                                                ) = ngayKetThuc
                                            )
                                        ),
                    trangThai       TEXT NOT NULL DEFAULT 'DANG_HOC'
                                        CHECK (
                                            trangThai IN (
                                                'DANG_HOC',
                                                'DA_HUY',
                                                'HOAN_THANH',
                                                'DINH_CHI'
                                            )
                                        ),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,
                    updatedAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (mssv)
                        REFERENCES SinhVien(mssv)
                        ON UPDATE CASCADE
                        ON DELETE RESTRICT,
                    FOREIGN KEY (lopHocPhanId)
                        REFERENCES LopHocPhan(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,

                    UNIQUE (mssv, lopHocPhanId),

                    CHECK (
                        ngayKetThuc = ''
                        OR ngayKetThuc >= ngayDangKy
                    ),
                    CHECK (
                        (
                            trangThai = 'DANG_HOC'
                            AND ngayKetThuc = ''
                        )
                        OR (
                            trangThai <> 'DANG_HOC'
                            AND ngayKetThuc <> ''
                        )
                    )
                );

                CREATE TABLE IF NOT EXISTS CaHoc (
                    id                      INTEGER PRIMARY KEY,
                    lopHocPhanId            INTEGER NOT NULL,
                    tenCa                   TEXT NOT NULL
                                                CHECK (
                                                    length(trim(tenCa)) > 0
                                                ),
                    ngayHoc                 TEXT NOT NULL
                                                CHECK (
                                                    length(ngayHoc) = 10
                                                    AND date(
                                                        ngayHoc,
                                                        '+0 days'
                                                    ) IS NOT NULL
                                                    AND date(
                                                        ngayHoc,
                                                        '+0 days'
                                                    ) = ngayHoc
                                                ),
                    phongHoc                TEXT NOT NULL
                                                COLLATE NOCASE
                                                CHECK (
                                                    length(trim(phongHoc)) > 0
                                                ),
                    gioBatDau               TEXT NOT NULL
                                                CHECK (
                                                    length(gioBatDau) = 5
                                                    AND time(
                                                        gioBatDau,
                                                        '+0 minutes'
                                                    ) IS NOT NULL
                                                    AND time(
                                                        gioBatDau,
                                                        '+0 minutes'
                                                    ) = gioBatDau || ':00'
                                                ),
                    gioKetThuc              TEXT NOT NULL
                                                CHECK (
                                                    length(gioKetThuc) = 5
                                                    AND time(
                                                        gioKetThuc,
                                                        '+0 minutes'
                                                    ) IS NOT NULL
                                                    AND time(
                                                        gioKetThuc,
                                                        '+0 minutes'
                                                    ) = gioKetThuc || ':00'
                                                ),
                    trangThai               TEXT NOT NULL DEFAULT 'ChuaMo'
                                                CHECK (
                                                    trangThai IN (
                                                        'ChuaMo',
                                                        'DangDienRa',
                                                        'DaKetThuc'
                                                    )
                                                ),
                    nguoiTaoTaiKhoanId      INTEGER,
                    daMoDiemDanh            INTEGER NOT NULL DEFAULT 0
                                                CHECK (
                                                    daMoDiemDanh IN (0, 1)
                                                ),
                    createdAt               TEXT NOT NULL
                                                DEFAULT CURRENT_TIMESTAMP,
                    updatedAt               TEXT NOT NULL
                                                DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (lopHocPhanId)
                        REFERENCES LopHocPhan(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,
                    FOREIGN KEY (nguoiTaoTaiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,

                    CHECK (gioBatDau < gioKetThuc)
                );

                CREATE TABLE IF NOT EXISTS DiemDanh (
                    id                  INTEGER PRIMARY KEY,
                    mssv                TEXT NOT NULL COLLATE NOCASE,
                    caHocId             INTEGER NOT NULL,
                    thoiGian            TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP
                                            CHECK (
                                                length(thoiGian) = 19
                                                AND datetime(
                                                    thoiGian,
                                                    '+0 seconds'
                                                ) IS NOT NULL
                                                AND datetime(
                                                    thoiGian,
                                                    '+0 seconds'
                                                ) = thoiGian
                                            ),
                    trangThai           TEXT NOT NULL DEFAULT 'PRESENT'
                                            CHECK (
                                                trangThai IN (
                                                    'PRESENT',
                                                    'LATE',
                                                    'EXCUSED',
                                                    'UNEXCUSED',
                                                    'ABSENT'
                                                )
                                            ),
                    ghiChu              TEXT NOT NULL DEFAULT '',
                    nguon               TEXT NOT NULL DEFAULT 'FACE'
                                            CHECK (
                                                nguon IN (
                                                    'FACE',
                                                    'MANUAL',
                                                    'IMPORT'
                                                )
                                            ),
                    isVoided            INTEGER NOT NULL DEFAULT 0
                                            CHECK (isVoided IN (0, 1)),
                    voidReason          TEXT NOT NULL DEFAULT '',
                    voidedAt            TEXT NOT NULL DEFAULT ''
                                            CHECK (
                                                voidedAt = ''
                                                OR (
                                                    length(voidedAt) = 19
                                                    AND datetime(
                                                        voidedAt,
                                                        '+0 seconds'
                                                    ) IS NOT NULL
                                                    AND datetime(
                                                        voidedAt,
                                                        '+0 seconds'
                                                    ) = voidedAt
                                                )
                                            ),
                    voidedByTaiKhoanId  INTEGER,
                    createdAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,
                    updatedAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (mssv)
                        REFERENCES SinhVien(mssv)
                        ON UPDATE CASCADE
                        ON DELETE RESTRICT,
                    FOREIGN KEY (caHocId)
                        REFERENCES CaHoc(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,
                    FOREIGN KEY (voidedByTaiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE RESTRICT,

                    UNIQUE (mssv, caHocId),
                    CHECK (
                        (
                            isVoided = 0
                            AND voidReason = ''
                            AND voidedAt = ''
                            AND voidedByTaiKhoanId IS NULL
                        )
                        OR (
                            isVoided = 1
                            AND length(trim(voidReason)) > 0
                            AND voidedAt <> ''
                            AND voidedByTaiKhoanId IS NOT NULL
                        )
                    )
                );

                CREATE TABLE IF NOT EXISTS MauKhuonMat (
                    id                  INTEGER PRIMARY KEY,
                    mssv                TEXT NOT NULL COLLATE NOCASE,
                    embedding           BLOB NOT NULL,
                    embeddingDimension  INTEGER NOT NULL DEFAULT 128
                                            CHECK (
                                                embeddingDimension = 128
                                            ),
                    embeddingDtype      TEXT NOT NULL DEFAULT 'float64'
                                            CHECK (
                                                embeddingDtype IN (
                                                    'float32',
                                                    'float64'
                                                )
                                            ),
                    sampleIndex         INTEGER NOT NULL
                                            CHECK (
                                                sampleIndex
                                                    BETWEEN 1 AND 10
                                            ),
                    modelName           TEXT NOT NULL
                                            DEFAULT
                                            'dlib_face_recognition_resnet_model_v1',
                    modelVersion        TEXT NOT NULL DEFAULT '1',
                    brightness          REAL,
                    blurVariance        REAL,
                    faceWidth           INTEGER,
                    faceHeight          INTEGER,
                    createdAt           TEXT NOT NULL
                                            DEFAULT CURRENT_TIMESTAMP,
                    isActive            INTEGER NOT NULL DEFAULT 1
                                            CHECK (isActive IN (0, 1)),

                    FOREIGN KEY (mssv)
                        REFERENCES SinhVien(mssv)
                        ON UPDATE CASCADE
                        ON DELETE RESTRICT,

                    CHECK (
                        (
                            embeddingDtype = 'float64'
                            AND length(embedding)
                                = embeddingDimension * 8
                        )
                        OR (
                            embeddingDtype = 'float32'
                            AND length(embedding)
                                = embeddingDimension * 4
                        )
                    ),
                    CHECK (
                        faceWidth IS NULL OR faceWidth > 0
                    ),
                    CHECK (
                        faceHeight IS NULL OR faceHeight > 0
                    ),

                    UNIQUE (mssv, sampleIndex)
                );

                CREATE TABLE IF NOT EXISTS AuthLog (
                    id                      INTEGER PRIMARY KEY,
                    actorTaiKhoanId         INTEGER,
                    targetTaiKhoanId        INTEGER,
                    actorUsernameSnapshot   TEXT NOT NULL DEFAULT '',
                    targetUsernameSnapshot  TEXT NOT NULL DEFAULT '',
                    eventType               TEXT NOT NULL
                                                CHECK (
                                                    length(trim(eventType)) > 0
                                                ),
                    success                 INTEGER NOT NULL DEFAULT 1
                                                CHECK (success IN (0, 1)),
                    message                 TEXT NOT NULL DEFAULT '',
                    ipAddress               TEXT NOT NULL DEFAULT '',
                    createdAt               TEXT NOT NULL
                                                DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (actorTaiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE SET NULL,
                    FOREIGN KEY (targetTaiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS PasswordResetToken (
                    id              INTEGER PRIMARY KEY,
                    taiKhoanId      INTEGER NOT NULL,
                    tokenHash       TEXT NOT NULL UNIQUE
                                        CHECK (
                                            length(trim(tokenHash)) > 0
                                        ),
                    tokenSalt       TEXT NOT NULL
                                        CHECK (
                                            length(trim(tokenSalt)) > 0
                                        ),
                    expiresAt       TEXT NOT NULL
                                        CHECK (
                                            length(expiresAt) = 19
                                            AND datetime(
                                                expiresAt,
                                                '+0 seconds'
                                            ) IS NOT NULL
                                            AND datetime(
                                                expiresAt,
                                                '+0 seconds'
                                            ) = expiresAt
                                        ),
                    usedAt          TEXT NOT NULL DEFAULT ''
                                        CHECK (
                                            usedAt = ''
                                            OR (
                                                length(usedAt) = 19
                                                AND datetime(
                                                    usedAt,
                                                    '+0 seconds'
                                                ) IS NOT NULL
                                                AND datetime(
                                                    usedAt,
                                                    '+0 seconds'
                                                ) = usedAt
                                            )
                                        ),
                    attempts        INTEGER NOT NULL DEFAULT 0
                                        CHECK (attempts >= 0),
                    createdAt       TEXT NOT NULL
                                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (taiKhoanId)
                        REFERENCES TaiKhoan(id)
                        ON UPDATE RESTRICT
                        ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_taikhoan_email
                    ON TaiKhoan(email COLLATE NOCASE)
                    WHERE email <> '';

                CREATE UNIQUE INDEX IF NOT EXISTS uq_taikhoan_phone
                    ON TaiKhoan(soDienThoai)
                    WHERE soDienThoai <> '';

                CREATE INDEX IF NOT EXISTS idx_giangvien_taikhoan
                    ON GiangVien(taiKhoanId);

                CREATE INDEX IF NOT EXISTS idx_lophoc_gvcn
                    ON LopHoc(giangVienChuNhiemId);

                CREATE INDEX IF NOT EXISTS idx_sinhvien_lop_status
                    ON SinhVien(maLop, trangThai);

                CREATE INDEX IF NOT EXISTS idx_hocky_namhoc
                    ON HocKy(namHocId, ngayBatDau, ngayKetThuc);

                CREATE INDEX IF NOT EXISTS idx_lhp_hocky
                    ON LopHocPhan(hocKyId, maMon);

                CREATE INDEX IF NOT EXISTS idx_lhp_mamon
                    ON LopHocPhan(maMon);

                CREATE INDEX IF NOT EXISTS idx_lhp_giangvien
                    ON LopHocPhan(giangVienId, trangThai);

                CREATE INDEX IF NOT EXISTS idx_dangky_lhp_status
                    ON DangKyHocPhan(
                        lopHocPhanId,
                        trangThai,
                        ngayDangKy,
                        ngayKetThuc
                    );

                CREATE INDEX IF NOT EXISTS idx_dangky_mssv
                    ON DangKyHocPhan(mssv);

                CREATE INDEX IF NOT EXISTS idx_cahoc_lhp_ngay
                    ON CaHoc(
                        lopHocPhanId,
                        ngayHoc,
                        gioBatDau,
                        gioKetThuc
                    );

                CREATE INDEX IF NOT EXISTS idx_cahoc_phong_ngay
                    ON CaHoc(
                        phongHoc,
                        ngayHoc,
                        gioBatDau,
                        gioKetThuc
                    );

                CREATE INDEX IF NOT EXISTS idx_cahoc_creator
                    ON CaHoc(nguoiTaoTaiKhoanId);

                CREATE INDEX IF NOT EXISTS idx_diemdanh_cahoc
                    ON DiemDanh(caHocId);

                CREATE INDEX IF NOT EXISTS idx_diemdanh_voider
                    ON DiemDanh(voidedByTaiKhoanId);

                CREATE INDEX IF NOT EXISTS idx_maukhonmat_active
                    ON MauKhuonMat(mssv, isActive, sampleIndex);

                CREATE INDEX IF NOT EXISTS idx_authlog_actor
                    ON AuthLog(actorTaiKhoanId, createdAt DESC);

                CREATE INDEX IF NOT EXISTS idx_authlog_target
                    ON AuthLog(targetTaiKhoanId, createdAt DESC);

                CREATE INDEX IF NOT EXISTS idx_authlog_created
                    ON AuthLog(createdAt DESC);

                CREATE INDEX IF NOT EXISTS idx_reset_account
                    ON PasswordResetToken(taiKhoanId, createdAt DESC);

                CREATE TRIGGER IF NOT EXISTS trg_giangvien_role_insert
                BEFORE INSERT ON GiangVien
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM TaiKhoan tk
                    WHERE tk.id = NEW.taiKhoanId
                      AND tk.vaiTro = 'GiangVien'
                      AND length(trim(tk.email)) > 0
                      AND length(trim(tk.soDienThoai)) > 0
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ho so giang vien phai gan voi tai khoan GiangVien'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_giangvien_role_update
                BEFORE UPDATE OF taiKhoanId ON GiangVien
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM TaiKhoan tk
                    WHERE tk.id = NEW.taiKhoanId
                      AND tk.vaiTro = 'GiangVien'
                      AND length(trim(tk.email)) > 0
                      AND length(trim(tk.soDienThoai)) > 0
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ho so giang vien phai gan voi tai khoan GiangVien'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_taikhoan_role_guard
                BEFORE UPDATE OF vaiTro ON TaiKhoan
                FOR EACH ROW
                WHEN NEW.vaiTro <> 'GiangVien'
                 AND EXISTS (
                    SELECT 1
                    FROM GiangVien gv
                    WHERE gv.taiKhoanId = OLD.id
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Tai khoan dang co ho so giang vien'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_preserve_last_admin
                BEFORE UPDATE OF vaiTro, isActive ON TaiKhoan
                FOR EACH ROW
                WHEN OLD.vaiTro = 'Admin'
                 AND OLD.isActive = 1
                 AND (
                    NEW.vaiTro <> 'Admin'
                    OR NEW.isActive <> 1
                 )
                 AND (
                    SELECT COUNT(*)
                    FROM TaiKhoan
                    WHERE vaiTro = 'Admin' AND isActive = 1
                 ) <= 1
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'He thong phai con it nhat mot Admin dang hoat dong'
                    );
                END;
                CREATE TRIGGER IF NOT EXISTS trg_lophoc_gvcn_insert
                BEFORE INSERT ON LopHoc
                FOR EACH ROW
                WHEN NEW.giangVienChuNhiemId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM GiangVien gv
                    JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                    WHERE gv.id = NEW.giangVienChuNhiemId
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien chu nhiem khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_lophoc_gvcn_update
                BEFORE UPDATE OF giangVienChuNhiemId ON LopHoc
                FOR EACH ROW
                WHEN NEW.giangVienChuNhiemId
                        IS NOT OLD.giangVienChuNhiemId
                 AND NEW.giangVienChuNhiemId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM GiangVien gv
                    JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                    WHERE gv.id = NEW.giangVienChuNhiemId
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien chu nhiem khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_lhp_giangvien_insert
                BEFORE INSERT ON LopHocPhan
                FOR EACH ROW
                WHEN NEW.giangVienId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM GiangVien gv
                    JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                    WHERE gv.id = NEW.giangVienId
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien lop hoc phan khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_lhp_giangvien_update
                BEFORE UPDATE OF giangVienId ON LopHocPhan
                FOR EACH ROW
                WHEN NEW.giangVienId IS NOT OLD.giangVienId
                 AND NEW.giangVienId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM GiangVien gv
                    JOIN TaiKhoan tk ON tk.id = gv.taiKhoanId
                    WHERE gv.id = NEW.giangVienId
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien lop hoc phan khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_lhp_lock_lecturer_during_open_session
                BEFORE UPDATE OF giangVienId ON LopHocPhan
                FOR EACH ROW
                WHEN NEW.giangVienId IS NOT OLD.giangVienId
                 AND OLD.giangVienId IS NOT NULL
                 AND EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    WHERE ca.lopHocPhanId = OLD.id
                      AND ca.trangThai = 'DangDienRa'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan dang co ca diem danh dang mo'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_lhp_lecturer_overlap_assignment
                BEFORE UPDATE OF giangVienId ON LopHocPhan
                FOR EACH ROW
                WHEN NEW.giangVienId IS NOT OLD.giangVienId
                 AND NEW.giangVienId IS NOT NULL
                 AND EXISTS (
                    SELECT 1
                    FROM CaHoc selectedCa
                    JOIN LopHocPhan otherSection
                      ON otherSection.giangVienId = NEW.giangVienId
                     AND otherSection.id <> OLD.id
                    JOIN CaHoc otherCa
                      ON otherCa.lopHocPhanId = otherSection.id
                    WHERE selectedCa.lopHocPhanId = OLD.id
                      AND otherCa.ngayHoc = selectedCa.ngayHoc
                      AND otherCa.gioBatDau < selectedCa.gioKetThuc
                      AND otherCa.gioKetThuc > selectedCa.gioBatDau
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien bi trung lich khi phan cong lop hoc phan'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_creator_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN NEW.nguoiTaoTaiKhoanId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM TaiKhoan tk
                    WHERE tk.id = NEW.nguoiTaoTaiKhoanId
                      AND tk.vaiTro IN ('Admin', 'GiangVien')
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Tai khoan tao ca hoc khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_creator_update
                BEFORE UPDATE OF nguoiTaoTaiKhoanId ON CaHoc
                FOR EACH ROW
                WHEN NEW.nguoiTaoTaiKhoanId
                        IS NOT OLD.nguoiTaoTaiKhoanId
                 AND NEW.nguoiTaoTaiKhoanId IS NOT NULL
                 AND NOT EXISTS (
                    SELECT 1
                    FROM TaiKhoan tk
                    WHERE tk.id = NEW.nguoiTaoTaiKhoanId
                      AND tk.vaiTro IN ('Admin', 'GiangVien')
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Tai khoan tao ca hoc khong hop le hoac da bi khoa'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_cahoc_ready_for_open_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN (
                        NEW.trangThai = 'DangDienRa'
                        OR NEW.daMoDiemDanh = 1
                     )
                 AND NOT EXISTS (
                    SELECT 1
                    FROM LopHocPhan lhp
                    JOIN GiangVien gv
                      ON gv.id = lhp.giangVienId
                    JOIN TaiKhoan tk
                      ON tk.id = gv.taiKhoanId
                    WHERE lhp.id = NEW.lopHocPhanId
                      AND lhp.trangThai NOT IN (
                          'DA_HUY',
                          'DA_KET_THUC'
                      )
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan chua san sang de mo diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_cahoc_ready_for_open_update
                BEFORE UPDATE OF
                    trangThai,
                    daMoDiemDanh,
                    lopHocPhanId
                ON CaHoc
                FOR EACH ROW
                WHEN (
                        NEW.trangThai = 'DangDienRa'
                        OR (
                            NEW.daMoDiemDanh = 1
                            AND OLD.daMoDiemDanh = 0
                        )
                        OR (
                            NEW.lopHocPhanId
                                IS NOT OLD.lopHocPhanId
                            AND NEW.daMoDiemDanh = 1
                        )
                     )
                 AND NOT EXISTS (
                    SELECT 1
                    FROM LopHocPhan lhp
                    JOIN GiangVien gv
                      ON gv.id = lhp.giangVienId
                    JOIN TaiKhoan tk
                      ON tk.id = gv.taiKhoanId
                    WHERE lhp.id = NEW.lopHocPhanId
                      AND lhp.trangThai NOT IN (
                          'DA_HUY',
                          'DA_KET_THUC'
                      )
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan chua san sang de mo diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_hocky_within_year_insert
                BEFORE INSERT ON HocKy
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM NamHoc nh
                    WHERE nh.id = NEW.namHocId
                      AND NEW.ngayBatDau >= nh.ngayBatDau
                      AND NEW.ngayKetThuc <= nh.ngayKetThuc
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Hoc ky phai nam trong khoang thoi gian cua nam hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_hocky_within_year_update
                BEFORE UPDATE OF namHocId, ngayBatDau, ngayKetThuc ON HocKy
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM NamHoc nh
                    WHERE nh.id = NEW.namHocId
                      AND NEW.ngayBatDau >= nh.ngayBatDau
                      AND NEW.ngayKetThuc <= nh.ngayKetThuc
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Hoc ky phai nam trong khoang thoi gian cua nam hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_within_semester_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM LopHocPhan lhp
                    JOIN HocKy hk ON hk.id = lhp.hocKyId
                    WHERE lhp.id = NEW.lopHocPhanId
                      AND NEW.ngayHoc >= hk.ngayBatDau
                      AND NEW.ngayHoc <= hk.ngayKetThuc
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ngay hoc phai nam trong thoi gian cua hoc ky'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_within_semester_update
                BEFORE UPDATE OF lopHocPhanId, ngayHoc ON CaHoc
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM LopHocPhan lhp
                    JOIN HocKy hk ON hk.id = lhp.hocKyId
                    WHERE lhp.id = NEW.lopHocPhanId
                      AND NEW.ngayHoc >= hk.ngayBatDau
                      AND NEW.ngayHoc <= hk.ngayKetThuc
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ngay hoc phai nam trong thoi gian cua hoc ky'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_capacity_insert
                BEFORE INSERT ON DangKyHocPhan
                FOR EACH ROW
                WHEN NEW.trangThai = 'DANG_HOC'
                 AND (
                    SELECT COUNT(*)
                    FROM DangKyHocPhan dk
                    WHERE dk.lopHocPhanId = NEW.lopHocPhanId
                      AND dk.trangThai = 'DANG_HOC'
                 ) >= (
                    SELECT lhp.siSoToiDa
                    FROM LopHocPhan lhp
                    WHERE lhp.id = NEW.lopHocPhanId
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan da vuot qua si so toi da'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_capacity_update
                BEFORE UPDATE OF lopHocPhanId, trangThai ON DangKyHocPhan
                FOR EACH ROW
                WHEN NEW.trangThai = 'DANG_HOC'
                 AND (
                    SELECT COUNT(*)
                    FROM DangKyHocPhan dk
                    WHERE dk.lopHocPhanId = NEW.lopHocPhanId
                      AND dk.trangThai = 'DANG_HOC'
                      AND dk.id <> OLD.id
                 ) >= (
                    SELECT lhp.siSoToiDa
                    FROM LopHocPhan lhp
                    WHERE lhp.id = NEW.lopHocPhanId
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan da vuot qua si so toi da'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_active_student_insert
                BEFORE INSERT ON DangKyHocPhan
                FOR EACH ROW
                WHEN NEW.trangThai = 'DANG_HOC'
                 AND NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Sinh vien khong o trang thai dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_active_student_update
                BEFORE UPDATE OF mssv, trangThai ON DangKyHocPhan
                FOR EACH ROW
                WHEN NEW.trangThai = 'DANG_HOC'
                 AND NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Sinh vien khong o trang thai dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_diemdanh_registration_insert
                BEFORE INSERT ON DiemDanh
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    JOIN DangKyHocPhan dk
                      ON dk.lopHocPhanId = ca.lopHocPhanId
                    WHERE ca.id = NEW.caHocId
                      AND dk.mssv = NEW.mssv
                      AND dk.ngayDangKy <= ca.ngayHoc
                      AND (
                          dk.ngayKetThuc = ''
                          OR dk.ngayKetThuc >= ca.ngayHoc
                      )
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Sinh vien khong co dang ky hop le trong lop hoc phan'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_diemdanh_registration_update
                BEFORE UPDATE OF mssv, caHocId ON DiemDanh
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    JOIN DangKyHocPhan dk
                      ON dk.lopHocPhanId = ca.lopHocPhanId
                    WHERE ca.id = NEW.caHocId
                      AND dk.mssv = NEW.mssv
                      AND dk.ngayDangKy <= ca.ngayHoc
                      AND (
                          dk.ngayKetThuc = ''
                          OR dk.ngayKetThuc >= ca.ngayHoc
                      )
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Dang ky hoc phan khong hop le cho ban ghi diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_diemdanh_active_student_insert
                BEFORE INSERT ON DiemDanh
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Sinh vien khong con o trang thai dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_diemdanh_active_student_update
                BEFORE UPDATE OF mssv ON DiemDanh
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Sinh vien khong con o trang thai dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_maukhuonmat_active_student_insert
                BEFORE INSERT ON MauKhuonMat
                FOR EACH ROW
                WHEN NEW.isActive = 1
                 AND NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong kich hoat khuon mat cho sinh vien khong dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_maukhuonmat_active_student_update
                BEFORE UPDATE OF mssv, isActive ON MauKhuonMat
                FOR EACH ROW
                WHEN NEW.isActive = 1
                 AND NOT EXISTS (
                    SELECT 1
                    FROM SinhVien sv
                    WHERE sv.mssv = NEW.mssv
                      AND sv.trangThai = 'DANG_HOC'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong kich hoat khuon mat cho sinh vien khong dang hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_diemdanh_face_ready_insert
                BEFORE INSERT ON DiemDanh
                FOR EACH ROW
                WHEN NEW.nguon = 'FACE'
                 AND NOT EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    JOIN LopHocPhan lhp
                      ON lhp.id = ca.lopHocPhanId
                    JOIN GiangVien gv
                      ON gv.id = lhp.giangVienId
                    JOIN TaiKhoan tk
                      ON tk.id = gv.taiKhoanId
                    WHERE ca.id = NEW.caHocId
                      AND ca.trangThai = 'DangDienRa'
                      AND ca.daMoDiemDanh = 1
                      AND lhp.trangThai NOT IN (
                          'DA_HUY',
                          'DA_KET_THUC'
                      )
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ca hoc chua du dieu kien ghi diem danh khuon mat'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_diemdanh_face_ready_update
                BEFORE UPDATE OF
                    mssv,
                    caHocId,
                    nguon
                ON DiemDanh
                FOR EACH ROW
                WHEN NEW.nguon = 'FACE'
                 AND NOT EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    JOIN LopHocPhan lhp
                      ON lhp.id = ca.lopHocPhanId
                    JOIN GiangVien gv
                      ON gv.id = lhp.giangVienId
                    JOIN TaiKhoan tk
                      ON tk.id = gv.taiKhoanId
                    WHERE ca.id = NEW.caHocId
                      AND ca.trangThai = 'DangDienRa'
                      AND ca.daMoDiemDanh = 1
                      AND lhp.trangThai NOT IN (
                          'DA_HUY',
                          'DA_KET_THUC'
                      )
                      AND tk.vaiTro = 'GiangVien'
                      AND tk.isActive = 1
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Ca hoc chua du dieu kien ghi diem danh khuon mat'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_preserve_history_update
                BEFORE UPDATE OF
                    mssv,
                    lopHocPhanId,
                    ngayDangKy,
                    ngayKetThuc
                ON DangKyHocPhan
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    WHERE ca.lopHocPhanId = OLD.lopHocPhanId
                      AND OLD.ngayDangKy <= ca.ngayHoc
                      AND (
                          OLD.ngayKetThuc = ''
                          OR OLD.ngayKetThuc >= ca.ngayHoc
                      )
                      AND (
                          COALESCE(ca.daMoDiemDanh, 0) = 1
                          OR EXISTS (
                              SELECT 1
                              FROM DiemDanh history_dd
                              WHERE history_dd.caHocId = ca.id
                          )
                      )
                      AND (
                          NEW.mssv <> OLD.mssv
                          OR NEW.lopHocPhanId <> OLD.lopHocPhanId
                          OR NEW.ngayDangKy > ca.ngayHoc
                          OR (
                              NEW.ngayKetThuc <> ''
                              AND NEW.ngayKetThuc < ca.ngayHoc
                          )
                      )
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong the thay doi dang ky lam sai lich su diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_dangky_preserve_history_delete
                BEFORE DELETE ON DangKyHocPhan
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    WHERE ca.lopHocPhanId = OLD.lopHocPhanId
                      AND OLD.ngayDangKy <= ca.ngayHoc
                      AND (
                          OLD.ngayKetThuc = ''
                          OR OLD.ngayKetThuc >= ca.ngayHoc
                      )
                      AND (
                          COALESCE(ca.daMoDiemDanh, 0) = 1
                          OR EXISTS (
                              SELECT 1
                              FROM DiemDanh history_dd
                              WHERE history_dd.caHocId = ca.id
                          )
                      )
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong the xoa dang ky da co lich su diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_lhp_preserve_context
                BEFORE UPDATE OF maMon, hocKyId ON LopHocPhan
                FOR EACH ROW
                WHEN (
                    NEW.maMon <> OLD.maMon
                    OR NEW.hocKyId <> OLD.hocKyId
                )
                 AND EXISTS (
                    SELECT 1
                    FROM CaHoc ca
                    WHERE ca.lopHocPhanId = OLD.id
                      AND (
                          ca.daMoDiemDanh = 1
                          OR EXISTS (
                              SELECT 1
                              FROM DiemDanh dd
                              WHERE dd.caHocId = ca.id
                          )
                      )
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong the doi mon hoac hoc ky sau khi co diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_section_overlap_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc existing
                    WHERE existing.lopHocPhanId = NEW.lopHocPhanId
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan bi trung khung gio'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_section_overlap_update
                BEFORE UPDATE OF
                    lopHocPhanId,
                    ngayHoc,
                    gioBatDau,
                    gioKetThuc
                ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc existing
                    WHERE existing.id <> NEW.id
                      AND existing.lopHocPhanId = NEW.lopHocPhanId
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Lop hoc phan bi trung khung gio'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_room_overlap_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc existing
                    WHERE existing.phongHoc = NEW.phongHoc
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Phong hoc bi trung khung gio'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_room_overlap_update
                BEFORE UPDATE OF
                    phongHoc,
                    ngayHoc,
                    gioBatDau,
                    gioKetThuc
                ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM CaHoc existing
                    WHERE existing.id <> NEW.id
                      AND existing.phongHoc = NEW.phongHoc
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Phong hoc bi trung khung gio'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_lecturer_overlap_insert
                BEFORE INSERT ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM LopHocPhan selected
                    JOIN LopHocPhan existingSection
                      ON existingSection.giangVienId
                            = selected.giangVienId
                    JOIN CaHoc existing
                      ON existing.lopHocPhanId = existingSection.id
                    WHERE selected.id = NEW.lopHocPhanId
                      AND selected.giangVienId IS NOT NULL
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien bi trung lich giang day'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_cahoc_lecturer_overlap_update
                BEFORE UPDATE OF
                    lopHocPhanId,
                    ngayHoc,
                    gioBatDau,
                    gioKetThuc
                ON CaHoc
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM LopHocPhan selected
                    JOIN LopHocPhan existingSection
                      ON existingSection.giangVienId
                            = selected.giangVienId
                    JOIN CaHoc existing
                      ON existing.lopHocPhanId = existingSection.id
                    WHERE selected.id = NEW.lopHocPhanId
                      AND selected.giangVienId IS NOT NULL
                      AND existing.id <> NEW.id
                      AND existing.ngayHoc = NEW.ngayHoc
                      AND existing.gioBatDau < NEW.gioKetThuc
                      AND existing.gioKetThuc > NEW.gioBatDau
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Giang vien bi trung lich giang day'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_no_delete_taikhoan
                BEFORE DELETE ON TaiKhoan
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong xoa vat ly tai khoan; hay dat isActive = 0'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_no_delete_giangvien
                BEFORE DELETE ON GiangVien
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong xoa vat ly giang vien; hay khoa tai khoan'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_no_delete_sinhvien
                BEFORE DELETE ON SinhVien
                FOR EACH ROW
                WHEN EXISTS (
                    SELECT 1
                    FROM DangKyHocPhan dk
                    WHERE dk.mssv = OLD.mssv
                )
                OR EXISTS (
                    SELECT 1
                    FROM DiemDanh dd
                    WHERE dd.mssv = OLD.mssv
                )
                OR EXISTS (
                    SELECT 1
                    FROM AuthLog al
                    WHERE al.targetUsernameSnapshot = OLD.mssv
                      AND al.eventType = 'STUDENT_WITHDRAW'
                      AND al.success = 1
                )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong the xoa sinh vien da co du lieu hoc vu'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS
                trg_sinhvien_withdraw_requires_closed_registrations
                BEFORE UPDATE OF trangThai ON SinhVien
                FOR EACH ROW
                WHEN NEW.trangThai = 'THOI_HOC'
                 AND EXISTS (
                    SELECT 1
                    FROM DangKyHocPhan dk
                    WHERE dk.mssv = OLD.mssv
                      AND dk.trangThai = 'DANG_HOC'
                 )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Phai ket thuc dang ky truoc khi cho sinh vien thoi hoc'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_no_delete_cahoc_history
                BEFORE DELETE ON CaHoc
                FOR EACH ROW
                WHEN COALESCE(OLD.daMoDiemDanh, 0) = 1
                  OR EXISTS (
                    SELECT 1
                    FROM DiemDanh dd
                    WHERE dd.caHocId = OLD.id
                  )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong the xoa ca hoc da mo diem danh'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS trg_no_delete_diemdanh
                BEFORE DELETE ON DiemDanh
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Khong xoa diem danh; hay danh dau isVoided = 1'
                    );
                END;
                """
            )

            version_row = connection.execute(
                "SELECT MAX(version) AS version FROM SchemaVersion"
            ).fetchone()
            current_version = version_row["version"]

            if current_version is None:
                connection.execute(
                    "INSERT INTO SchemaVersion(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif current_version != SCHEMA_VERSION:
                raise RuntimeError(
                    "Phiên bản CSDL không tương thích: "
                    f"đang có {current_version}, cần {SCHEMA_VERSION}"
                )

            self._seed_admin(connection)

    def _assert_database_is_compatible(self):
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return

        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
        finally:
            connection.close()

        if not tables:
            return

        if "CanBo" in tables:
            raise RuntimeError(
                "Phát hiện CSDL cũ còn bảng CanBo. "
                "Hãy migration hoặc tạo CSDL mới trước khi dùng schema v3."
            )

        if "SchemaVersion" not in tables:
            raise RuntimeError(
                "CSDL đã có dữ liệu nhưng không có SchemaVersion; "
                "không thể tự động xác định cấu trúc an toàn."
            )

        with sqlite3.connect(self.db_path) as version_connection:
            row = version_connection.execute(
                "SELECT MAX(version) FROM SchemaVersion"
            ).fetchone()
        version = row[0] if row else None
        if version == MIN_MIGRATABLE_SCHEMA_VERSION:
            self._backup_before_schema_v3()
            self._migrate_schema_v2_to_v3()
            return

        if version != SCHEMA_VERSION:
            raise RuntimeError(
                "Phiên bản CSDL không tương thích: "
                f"đang có {version}, cần {SCHEMA_VERSION}"
            )

    def _backup_before_schema_v3(self) -> Path:
        """Tạo bản sao nhất quán trước khi thay đổi trigger của schema v2."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.db_path.with_name(
            f"{self.db_path.stem}.before_v3_{timestamp}{self.db_path.suffix}"
        )

        counter = 1
        while backup_path.exists():
            backup_path = self.db_path.with_name(
                f"{self.db_path.stem}.before_v3_{timestamp}_{counter}"
                f"{self.db_path.suffix}"
            )
            counter += 1

        source = sqlite3.connect(self.db_path)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return backup_path

    def _migrate_schema_v2_to_v3(self):
        """Nâng v2 lên v3 trong một transaction có khóa ghi."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")

        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT MAX(version) AS version FROM SchemaVersion"
            ).fetchone()
            current_version = row["version"] if row else None

            # Một tiến trình khác có thể đã migration trong lúc tạo backup.
            if current_version == SCHEMA_VERSION:
                connection.rollback()
                return

            if current_version != MIN_MIGRATABLE_SCHEMA_VERSION:
                raise RuntimeError(
                    "Không thể migration CSDL: "
                    f"đang có phiên bản {current_version}"
                )

            for trigger_name in (
                "trg_no_delete_sinhvien",
                "trg_dangky_preserve_history_update",
                "trg_dangky_preserve_history_delete",
                "trg_dangky_active_student_insert",
                "trg_dangky_active_student_update",
                "trg_sinhvien_withdraw_requires_closed_registrations",
                "trg_no_delete_cahoc_history",
                "trg_diemdanh_active_student_insert",
                "trg_diemdanh_active_student_update",
                "trg_maukhuonmat_active_student_insert",
                "trg_maukhuonmat_active_student_update",
            ):
                connection.execute(
                    f"DROP TRIGGER IF EXISTS {trigger_name}"
                )

            self._install_schema_v3_student_history_triggers(connection)

            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise RuntimeError(
                    "Migration phát hiện dữ liệu vi phạm khóa ngoại"
                )

            connection.execute(
                "INSERT INTO SchemaVersion(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError("Migration CSDL v2 lên v3 thất bại") from exc
        finally:
            connection.close()

    @staticmethod
    def _install_schema_v3_student_history_triggers(connection):
        connection.execute(
            """
            CREATE TRIGGER trg_dangky_preserve_history_update
            BEFORE UPDATE OF
                mssv,
                lopHocPhanId,
                ngayDangKy,
                ngayKetThuc
            ON DangKyHocPhan
            FOR EACH ROW
            WHEN EXISTS (
                SELECT 1
                FROM CaHoc ca
                WHERE ca.lopHocPhanId = OLD.lopHocPhanId
                  AND OLD.ngayDangKy <= ca.ngayHoc
                  AND (
                      OLD.ngayKetThuc = ''
                      OR OLD.ngayKetThuc >= ca.ngayHoc
                  )
                  AND (
                      COALESCE(ca.daMoDiemDanh, 0) = 1
                      OR EXISTS (
                          SELECT 1
                          FROM DiemDanh history_dd
                          WHERE history_dd.caHocId = ca.id
                      )
                  )
                  AND (
                      NEW.mssv <> OLD.mssv
                      OR NEW.lopHocPhanId <> OLD.lopHocPhanId
                      OR NEW.ngayDangKy > ca.ngayHoc
                      OR (
                          NEW.ngayKetThuc <> ''
                          AND NEW.ngayKetThuc < ca.ngayHoc
                      )
                  )
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong the thay doi dang ky lam sai lich su diem danh'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_dangky_preserve_history_delete
            BEFORE DELETE ON DangKyHocPhan
            FOR EACH ROW
            WHEN EXISTS (
                SELECT 1
                FROM CaHoc ca
                WHERE ca.lopHocPhanId = OLD.lopHocPhanId
                  AND OLD.ngayDangKy <= ca.ngayHoc
                  AND (
                      OLD.ngayKetThuc = ''
                      OR OLD.ngayKetThuc >= ca.ngayHoc
                  )
                  AND (
                      COALESCE(ca.daMoDiemDanh, 0) = 1
                      OR EXISTS (
                          SELECT 1
                          FROM DiemDanh history_dd
                          WHERE history_dd.caHocId = ca.id
                      )
                  )
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong the xoa dang ky da co lich su diem danh'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_no_delete_sinhvien
            BEFORE DELETE ON SinhVien
            FOR EACH ROW
            WHEN EXISTS (
                SELECT 1
                FROM DangKyHocPhan dk
                WHERE dk.mssv = OLD.mssv
            )
            OR EXISTS (
                SELECT 1
                FROM DiemDanh dd
                WHERE dd.mssv = OLD.mssv
            )
            OR EXISTS (
                SELECT 1
                FROM AuthLog al
                WHERE al.targetUsernameSnapshot = OLD.mssv
                  AND al.eventType = 'STUDENT_WITHDRAW'
                  AND al.success = 1
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong the xoa sinh vien da co du lieu hoc vu'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_dangky_active_student_insert
            BEFORE INSERT ON DangKyHocPhan
            FOR EACH ROW
            WHEN NEW.trangThai = 'DANG_HOC'
             AND NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Sinh vien khong o trang thai dang hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_dangky_active_student_update
            BEFORE UPDATE OF mssv, trangThai ON DangKyHocPhan
            FOR EACH ROW
            WHEN NEW.trangThai = 'DANG_HOC'
             AND NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Sinh vien khong o trang thai dang hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_sinhvien_withdraw_requires_closed_registrations
            BEFORE UPDATE OF trangThai ON SinhVien
            FOR EACH ROW
            WHEN NEW.trangThai = 'THOI_HOC'
             AND EXISTS (
                SELECT 1
                FROM DangKyHocPhan dk
                WHERE dk.mssv = OLD.mssv
                  AND dk.trangThai = 'DANG_HOC'
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Phai ket thuc dang ky truoc khi cho sinh vien thoi hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_no_delete_cahoc_history
            BEFORE DELETE ON CaHoc
            FOR EACH ROW
            WHEN COALESCE(OLD.daMoDiemDanh, 0) = 1
              OR EXISTS (
                SELECT 1
                FROM DiemDanh dd
                WHERE dd.caHocId = OLD.id
              )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong the xoa ca hoc da mo diem danh'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_diemdanh_active_student_insert
            BEFORE INSERT ON DiemDanh
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Sinh vien khong con o trang thai dang hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_diemdanh_active_student_update
            BEFORE UPDATE OF mssv ON DiemDanh
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
            )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Sinh vien khong con o trang thai dang hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_maukhuonmat_active_student_insert
            BEFORE INSERT ON MauKhuonMat
            FOR EACH ROW
            WHEN NEW.isActive = 1
             AND NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong kich hoat khuon mat cho sinh vien khong dang hoc'
                );
            END
            """
        )
        connection.execute(
            """
            CREATE TRIGGER trg_maukhuonmat_active_student_update
            BEFORE UPDATE OF mssv, isActive ON MauKhuonMat
            FOR EACH ROW
            WHEN NEW.isActive = 1
             AND NOT EXISTS (
                SELECT 1
                FROM SinhVien sv
                WHERE sv.mssv = NEW.mssv
                  AND sv.trangThai = 'DANG_HOC'
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Khong kich hoat khuon mat cho sinh vien khong dang hoc'
                );
            END
            """
        )

    @staticmethod
    def _seed_admin(connection: sqlite3.Connection):
        default_salt = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
        default_password_hash = (
            "447699188107b8d71af481d4d87f123c7"
            "a7ab686b235bc23c5dcaac8cd797ff8"
        )

        row = connection.execute(
            """
            SELECT id, passwordHash, passwordSalt, mustChangePassword
            FROM TaiKhoan
            WHERE username = 'admin'
            """
        ).fetchone()

        if row is None:
            connection.execute(
                """
                INSERT INTO TaiKhoan (
                    username,
                    passwordHash,
                    passwordSalt,
                    hoTen,
                    vaiTro,
                    isActive,
                    passwordIterations,
                    mustChangePassword
                )
                VALUES (?, ?, ?, ?, 'Admin', 1, 100000, 1)
                """,
                (
                    "admin",
                    default_password_hash,
                    default_salt,
                    "Quản trị viên",
                ),
            )
            return

        if not row["passwordSalt"] or not row["passwordHash"]:
            connection.execute(
                """
                UPDATE TaiKhoan
                SET passwordHash = ?,
                    passwordSalt = ?,
                    vaiTro = 'Admin',
                    isActive = 1,
                    passwordIterations = 100000,
                    mustChangePassword = 1,
                    updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    default_password_hash,
                    default_salt,
                    row["id"],
                ),
            )
