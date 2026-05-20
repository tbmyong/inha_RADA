"""ML 서버 / Spring Boot 메인 서버 HTTP 전송기.

mode 별 정상 응답 코드:
- ``mlserver``  : 200 OK (JSON body 포함)
- ``springboot``: 202 Accepted (빈 body 가능)

따라서 ``status_code in (200, 202)`` 를 정상 응답으로 간주하며,
Spring Boot 의 빈 body 에 대비해 ``resp.json()`` 호출은 가드한다.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .local_queue import LocalQueue
from .sanitizer import sanitize_for_json

log = logging.getLogger(__name__)


# Retry 정책:
# - 200/202        : 성공
# - 401/403/422    : drop — 인증/payload 문제, 재시도 무의미
# - 그 외 4xx/5xx  : 재시도 (큐에 적재)
# - ConnectionError: 재시도 (큐에 적재)
NON_RETRYABLE_STATUS = frozenset({401, 403, 422})


class MetricsSender:
    def __init__(
        self,
        url: Optional[str] = None,
        *,
        config: "Optional[object]" = None,
        mode: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 3.0,
        queue: Optional[LocalQueue] = None,
    ) -> None:
        # config 우선 적용
        if config is not None:
            cfg_mode = getattr(config, "mode", None)
            cfg_api_key = getattr(config, "api_key", None)
            cfg_url = None
            target_url_fn = getattr(config, "target_url", None)
            if callable(target_url_fn):
                cfg_url = target_url_fn()
            self.mode = mode or cfg_mode or "mlserver"
            self.api_key = api_key if api_key is not None else cfg_api_key
            self.url = url or cfg_url
        else:
            self.mode = mode or "mlserver"
            self.api_key = api_key
            self.url = url

        if not self.url:
            raise ValueError("MetricsSender requires url or config with target_url()")

        self.timeout = timeout
        self.queue = queue
        # 4xx drop 카운터 — 관측용 (F1 metric 패턴과 일관, 단순 print 로 가시화).
        self.dropped_4xx_count: int = 0

    def _build_headers(self) -> dict:
        if self.mode == "springboot":
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            else:
                log.warning(
                    "MetricsSender mode=springboot 인데 api_key 가 없습니다. 헤더 없이 전송."
                )
            return headers
        # mlserver: 헤더 없음 (기존 동작 유지)
        return {}

    def send(
        self,
        metrics: dict,
        local_alerts: list,
        boxplot_signal: dict,
    ) -> Optional[dict]:
        payload = dict(metrics)
        payload["local_alerts"] = local_alerts
        payload["boxplot_signal"] = boxplot_signal
        payload = sanitize_for_json(payload)
        headers = self._build_headers()
        try:
            if headers:
                resp = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            else:
                resp = requests.post(self.url, json=payload, timeout=self.timeout)
            # mlserver=200, springboot=202 모두 정상으로 처리.
            if resp.status_code in (200, 202):
                # Spring Boot 202 는 빈 body 일 수 있으므로 JSON 파싱 가드.
                log.debug("sent mode=%s status=%s", self.mode, resp.status_code)
                try:
                    return resp.json()
                except (ValueError, json.JSONDecodeError):
                    return {}
            # 401/403/422 → drop (재시도 무의미). 큐에 쌓지 않는다.
            if resp.status_code in NON_RETRYABLE_STATUS:
                self.dropped_4xx_count += 1
                print(
                    f"  [전송 drop] mode={self.mode} status={resp.status_code} "
                    f"(non-retryable; total_dropped={self.dropped_4xx_count})"
                )
                log.error(
                    "send dropped mode=%s status=%s reason=non_retryable",
                    self.mode,
                    resp.status_code,
                )
                return None
            print(
                f"  [전송 오류] mode={self.mode} status={resp.status_code}"
            )
            log.warning(
                "send failed mode=%s status=%s", self.mode, resp.status_code
            )
            if self.queue is not None:
                self.queue.put(payload)
            return None
        except requests.exceptions.ConnectionError:
            print("  [전송 실패] 서버 연결 불가 (로컬 판단만 동작)")
            if self.queue is not None:
                self.queue.put(payload)
            return None
        except Exception as e:
            print(f"  [전송 실패] mode={self.mode} {e}")
            if self.queue is not None:
                self.queue.put(payload)
            return None

    def replay(self, payload: dict) -> bool:
        """이미 sanitize 된 payload 를 그대로 POST 재전송.

        send() 와 달리 payload 를 가공하지 않고, 실패 시 큐에 적재하지도 않는다
        (호출 측에서 재적재 여부를 결정한다). 200/202 면 True, 그 외 False.
        """
        headers = self._build_headers()
        try:
            if headers:
                resp = requests.post(
                    self.url, json=payload, headers=headers, timeout=self.timeout
                )
            else:
                resp = requests.post(
                    self.url, json=payload, timeout=self.timeout
                )
            if resp.status_code in (200, 202):
                log.debug(
                    "replay ok mode=%s status=%s", self.mode, resp.status_code
                )
                return True
            if resp.status_code in NON_RETRYABLE_STATUS:
                self.dropped_4xx_count += 1
                log.error(
                    "replay dropped mode=%s status=%s reason=non_retryable",
                    self.mode,
                    resp.status_code,
                )
                # True 반환: 호출 측이 재적재하지 않도록 (drop).
                return True
            log.warning(
                "replay failed mode=%s status=%s", self.mode, resp.status_code
            )
            return False
        except requests.exceptions.ConnectionError:
            log.warning("replay connection error mode=%s", self.mode)
            return False
        except Exception as e:
            log.warning("replay error mode=%s: %s", self.mode, e)
            return False
