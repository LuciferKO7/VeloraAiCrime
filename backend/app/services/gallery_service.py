import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from backend.app.core.config import settings
from backend.app.db.session import get_engine

logger = logging.getLogger("velora.gallery_service")


def save_gallery_image(face_id: str, image_bytes: bytes) -> str:
    """
    Saves gallery face image to local storage under backend/storage/gallery/{face_id}.png.
    Returns relative storage path.
    """
    storage = Path(settings.STORAGE_DIR)
    gallery_dir = storage / "gallery"
    gallery_dir.mkdir(parents=True, exist_ok=True)
    file_path = gallery_dir / f"{face_id}.png"
    file_path.write_bytes(image_bytes)
    return f"gallery/{face_id}.png"


class GalleryIndex:
    """
    In-memory embedding matrix for gallery matching (§8.7).
    Loads valid stored gallery embeddings at startup or on demand,
    maps rows deterministically to gallery face IDs, and supports cosine similarity search.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._face_ids: list[str] = []
        self._matrix: np.ndarray | None = None
        self._initialized: bool = False

    def __len__(self) -> int:
        with self._lock:
            return len(self._face_ids)

    def load_from_db(self, engine_or_conn: Engine | Connection | None = None) -> None:
        """
        Loads all gallery face embeddings from the database into the in-memory matrix.
        Rejects malformed or invalid embeddings safely.
        """
        with self._lock:
            face_ids: list[str] = []
            vectors: list[np.ndarray] = []

            query = text("SELECT id, embedding FROM gallery_faces ORDER BY added_at ASC, id ASC")

            def process_rows(rows):
                for row in rows:
                    face_id = row[0]
                    raw_blob = row[1]
                    if not isinstance(raw_blob, (bytes, bytearray)):
                        logger.warning("Skipping gallery face %s: embedding is not bytes", face_id)
                        continue
                    if len(raw_blob) != 512 * 4:
                        logger.warning(
                            "Skipping gallery face %s: invalid blob length %d (expected 2048)",
                            face_id,
                            len(raw_blob),
                        )
                        continue
                    try:
                        vec = np.frombuffer(raw_blob, dtype=np.float32).copy()
                        if not np.all(np.isfinite(vec)):
                            logger.warning("Skipping gallery face %s: non-finite embedding floats", face_id)
                            continue
                        norm = float(np.linalg.norm(vec))
                        if norm <= 1e-12:
                            logger.warning("Skipping gallery face %s: zero-norm embedding", face_id)
                            continue
                        vec = vec / norm
                        vectors.append(vec)
                        face_ids.append(face_id)
                    except Exception as err:
                        logger.warning("Skipping gallery face %s: failed parsing embedding: %s", face_id, err)

            if isinstance(engine_or_conn, Connection):
                rows = engine_or_conn.execute(query).fetchall()
                process_rows(rows)
            else:
                eng = engine_or_conn or get_engine()
                with eng.connect() as conn:
                    rows = conn.execute(query).fetchall()
                    process_rows(rows)

            if vectors:
                self._matrix = np.vstack(vectors).astype(np.float32)
            else:
                self._matrix = np.empty((0, 512), dtype=np.float32)
            self._face_ids = face_ids
            self._initialized = True
            logger.info("Gallery index initialized with %d faces", len(self._face_ids))

    def add_face(self, face_id: str, embedding: np.ndarray | list[float] | bytes) -> None:
        """
        Dynamically adds a single face embedding to the in-memory matrix.
        """
        with self._lock:
            if not self._initialized:
                self.load_from_db()

            if isinstance(embedding, (bytes, bytearray)):
                vec = np.frombuffer(embedding, dtype=np.float32).copy()
            else:
                vec = np.array(embedding, dtype=np.float32)

            vec = vec.reshape(512)
            norm = float(np.linalg.norm(vec))
            if norm > 1e-12:
                vec = vec / norm

            if self._matrix is None or len(self._face_ids) == 0:
                self._matrix = vec.reshape(1, 512).astype(np.float32)
            else:
                self._matrix = np.vstack([self._matrix, vec.reshape(1, 512)]).astype(np.float32)

            self._face_ids.append(face_id)
            logger.info("Added face %s to gallery index (total %d)", face_id, len(self._face_ids))

    def search(
        self,
        query_embedding: list[float] | np.ndarray,
        top_k: int = 5,
        engine_or_conn: Engine | Connection | None = None,
    ) -> list[dict[str, Any]]:
        """
        Performs cosine similarity search against the in-memory matrix.
        Returns sorted list of matches:
        [{"rank": int, "gallery_face_id": str, "similarity": float}]
        """
        with self._lock:
            if not self._initialized:
                self.load_from_db(engine_or_conn)

            if self._matrix is None or len(self._face_ids) == 0:
                return []

            q = np.array(query_embedding, dtype=np.float32).reshape(512)
            norm = float(np.linalg.norm(q))
            if norm > 1e-12:
                q = q / norm

            sims = np.dot(self._matrix, q)
            k = min(top_k, len(self._face_ids))
            if k <= 0:
                return []

            sorted_indices = np.argsort(-sims)[:k]
            results: list[dict[str, Any]] = []
            for rank, idx in enumerate(sorted_indices, start=1):
                results.append(
                    {
                        "rank": rank,
                        "gallery_face_id": self._face_ids[idx],
                        "similarity": float(round(float(sims[idx]), 6)),
                    }
                )
            return results

    def reset(self) -> None:
        """
        Resets in-memory state.
        """
        with self._lock:
            self._face_ids = []
            self._matrix = None
            self._initialized = False


gallery_index = GalleryIndex()
