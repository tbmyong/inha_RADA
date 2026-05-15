"""ML 서버 연결 실패 시 페이로드를 임시 보관하는 큐.

기본은 in-memory 동작. ``queue_path`` 인자를 주면 JSONL 파일로
디스크 영속성을 갖는다. 프로세스 재시작 후에도 미전송 페이로드를
복구할 수 있다.

회귀 안전성:
- ``queue_path=None``(기본) → 기존 in-memory 동작 그대로 유지
- 인터페이스(``put``/``pop``/``drain``/``__len__``/``__iter__``/``max_size``)
  는 변경 없음
"""
from __future__ import annotations

import errno
import json
import logging
import os
import threading
from collections import deque
from pathlib import Path
from typing import Iterator, List, Optional, Union

logger = logging.getLogger(__name__)


class LocalQueue:
    def __init__(
        self,
        max_size: int = 200,
        queue_path: Optional[Union[str, Path]] = None,
        max_bytes: Optional[int] = None,
        fsync: bool = False,
    ) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if max_bytes is not None and max_bytes <= 0:
            raise ValueError("max_bytes must be positive when set")

        self._max_size = max_size
        self._max_bytes = max_bytes
        self._fsync = fsync
        self._buf: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()

        self._queue_path: Optional[Path] = (
            Path(queue_path) if queue_path is not None else None
        )

        # 관측 카운터
        self._dropped_count = 0
        self._corrupt_skipped_count = 0
        self._disk_write_failed_count = 0

        if self._queue_path is not None:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    # ------------------------------------------------------------------ public
    def put(self, payload: dict) -> None:
        with self._lock:
            # maxlen 초과 시 deque가 자동으로 popleft 하므로
            # 그 전에 dropped 여부를 판단해야 한다.
            will_overflow = len(self._buf) >= self._max_size
            self._buf.append(payload)
            if will_overflow:
                self._dropped_count += 1

            if self._queue_path is not None:
                if will_overflow:
                    # 디스크 쪽도 oldest 라인 제거 필요 → compact
                    self._compact_disk_locked()
                else:
                    self._append_line_locked(payload)
                self._enforce_max_bytes_locked()

    def pop(self) -> Optional[dict]:
        with self._lock:
            if not self._buf:
                return None
            item = self._buf.popleft()
            if self._queue_path is not None:
                self._compact_disk_locked()
            return item

    def drain(self) -> List[dict]:
        with self._lock:
            items = list(self._buf)
            self._buf.clear()
            if self._queue_path is not None:
                self._compact_disk_locked()
            return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    def __iter__(self) -> Iterator:
        # snapshot 반환 (락 보호하의 list 복사)
        with self._lock:
            snapshot = list(self._buf)
        return iter(snapshot)

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def corrupt_skipped_count(self) -> int:
        return self._corrupt_skipped_count

    @property
    def disk_write_failed_count(self) -> int:
        return self._disk_write_failed_count

    # ----------------------------------------------------------------- helpers
    def _load_from_disk(self) -> None:
        path = self._queue_path
        assert path is not None
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        self._corrupt_skipped_count += 1
                        logger.warning(
                            "LocalQueue: corrupt line skipped during load: %s", e
                        )
                        continue
                    if len(self._buf) >= self._max_size:
                        self._buf.popleft()
                        self._dropped_count += 1
                    self._buf.append(obj)
        except OSError as e:
            logger.warning("LocalQueue: failed to read %s: %s", path, e)
            return

        # 로드 후 디스크와 인메모리 정합성 보장 (손상 라인 제거 + maxlen 적용)
        try:
            self._compact_disk_locked()
        except OSError as e:
            logger.warning("LocalQueue: post-load compact failed: %s", e)

    def _append_line_locked(self, payload: dict) -> None:
        path = self._queue_path
        assert path is not None
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False))
                f.write("\n")
                f.flush()
                if self._fsync:
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        # fsync 실패는 치명적이지 않음. 카운트만 올림.
                        self._disk_write_failed_count += 1
        except OSError as e:
            if getattr(e, "errno", None) == errno.ENOSPC:
                logger.warning("LocalQueue: disk full, keeping payload in-memory only")
            else:
                logger.warning("LocalQueue: append failed (%s); in-memory retained", e)
            self._disk_write_failed_count += 1

    def _compact_disk_locked(self) -> None:
        """현재 인메모리 버퍼를 디스크에 atomic 하게 다시 쓴다."""
        path = self._queue_path
        assert path is not None
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                for item in self._buf:
                    f.write(json.dumps(item, ensure_ascii=False))
                    f.write("\n")
                f.flush()
                if self._fsync:
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        self._disk_write_failed_count += 1
            os.replace(tmp, path)
        except OSError as e:
            self._disk_write_failed_count += 1
            if getattr(e, "errno", None) == errno.ENOSPC:
                logger.warning("LocalQueue: disk full during compact")
            else:
                logger.warning("LocalQueue: compact failed: %s", e)
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def _enforce_max_bytes_locked(self) -> None:
        if self._max_bytes is None or self._queue_path is None:
            return
        try:
            size = self._queue_path.stat().st_size
        except OSError:
            return
        if size <= self._max_bytes:
            return
        # oldest 부터 drop 하면서 max_bytes 이하로 떨어질 때까지 반복
        while self._buf and size > self._max_bytes:
            self._buf.popleft()
            self._dropped_count += 1
            self._compact_disk_locked()
            try:
                size = self._queue_path.stat().st_size
            except OSError:
                return
