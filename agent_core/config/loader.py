"""YAML/dict 기반 설정 로더. PyYAML 미설치 환경에서도 dict 직접 주입 가능."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

from . import defaults


@dataclass
class AgentConfig:
    interval: int = defaults.INTERVAL
    ml_server_url: str = defaults.ML_SERVER_URL
    spring_boot_url: str = defaults.SPRING_BOOT_URL
    mode: str = defaults.MODE
    api_key: Optional[str] = defaults.API_KEY
    local_window_size: int = defaults.LOCAL_WINDOW_SIZE
    hw_baseline_window: int = defaults.HW_BASELINE_WINDOW
    normal_ports: Set[int] = field(default_factory=lambda: set(defaults.NORMAL_PORTS))
    thresholds: Dict[str, dict] = field(
        default_factory=lambda: {k: dict(v) for k, v in defaults.THRESHOLDS.items()}
    )
    absolute_thresholds: dict = field(
        default_factory=lambda: dict(defaults.ABSOLUTE_THRESHOLDS)
    )
    hw_degradation_ratio: float = defaults.HW_DEGRADATION_RATIO

    local_queue_path: Optional[str] = defaults.LOCAL_QUEUE_PATH
    local_queue_max_size: int = defaults.LOCAL_QUEUE_MAX_SIZE
    local_queue_max_bytes: int = defaults.LOCAL_QUEUE_MAX_BYTES
    local_queue_fsync: bool = defaults.LOCAL_QUEUE_FSYNC

    def __post_init__(self) -> None:
        if self.mode not in defaults.VALID_MODES:
            raise ValueError(
                f"invalid mode: {self.mode!r} (expected one of {sorted(defaults.VALID_MODES)})"
            )

    def target_url(self) -> str:
        """현재 mode 에 해당하는 전송 대상 URL 반환."""
        if self.mode == "springboot":
            return self.spring_boot_url
        return self.ml_server_url


def _from_dict(data: dict) -> AgentConfig:
    if not data:
        return AgentConfig()
    kwargs: dict = {}
    if "interval" in data:
        kwargs["interval"] = int(data["interval"])
    if "ml_server_url" in data:
        kwargs["ml_server_url"] = str(data["ml_server_url"])
    if "spring_boot_url" in data:
        kwargs["spring_boot_url"] = str(data["spring_boot_url"])
    if "mode" in data:
        kwargs["mode"] = str(data["mode"])
    if "api_key" in data:
        v = data["api_key"]
        kwargs["api_key"] = None if v is None else str(v)
    if "local_window_size" in data:
        kwargs["local_window_size"] = int(data["local_window_size"])
    if "hw_baseline_window" in data:
        kwargs["hw_baseline_window"] = int(data["hw_baseline_window"])
    if "normal_ports" in data:
        kwargs["normal_ports"] = set(int(p) for p in data["normal_ports"])
    if "thresholds" in data:
        kwargs["thresholds"] = {k: dict(v) for k, v in data["thresholds"].items()}
    if "absolute_thresholds" in data:
        kwargs["absolute_thresholds"] = dict(data["absolute_thresholds"])
    if "hw_degradation_ratio" in data:
        kwargs["hw_degradation_ratio"] = float(data["hw_degradation_ratio"])
    if "local_queue_path" in data:
        v = data["local_queue_path"]
        kwargs["local_queue_path"] = None if v is None else str(v)
    if "local_queue_max_size" in data:
        kwargs["local_queue_max_size"] = int(data["local_queue_max_size"])
    if "local_queue_max_bytes" in data:
        kwargs["local_queue_max_bytes"] = int(data["local_queue_max_bytes"])
    if "local_queue_fsync" in data:
        kwargs["local_queue_fsync"] = bool(data["local_queue_fsync"])
    return AgentConfig(**kwargs)


def _apply_env_overrides(cfg: AgentConfig) -> AgentConfig:
    """환경변수 RADA_* 가 존재하면 cfg 위에 override."""
    mode = os.environ.get("RADA_MODE")
    ml_url = os.environ.get("RADA_ML_SERVER_URL")
    sb_url = os.environ.get("RADA_SPRING_BOOT_URL")
    api_key = os.environ.get("RADA_API_KEY")

    if mode is not None:
        if mode not in defaults.VALID_MODES:
            raise ValueError(
                f"invalid RADA_MODE: {mode!r} (expected one of {sorted(defaults.VALID_MODES)})"
            )
        cfg.mode = mode
    if ml_url is not None:
        cfg.ml_server_url = ml_url
    if sb_url is not None:
        cfg.spring_boot_url = sb_url
    if api_key is not None:
        cfg.api_key = api_key
    return cfg


def _discover_config_path() -> Optional[str]:
    """config 파일 경로 자동 탐색.

    우선순위:
      1. RADA_CONFIG 환경변수
      2. ./config.yaml (CWD)
      3. %APPDATA%/rada/config.yaml (Windows)
    """
    env_path = os.environ.get("RADA_CONFIG")
    if env_path and Path(env_path).exists():
        return env_path

    cwd_path = Path.cwd() / "config.yaml"
    if cwd_path.exists():
        return str(cwd_path)

    appdata = os.environ.get("APPDATA")
    if appdata:
        appdata_path = Path(appdata) / "rada" / "config.yaml"
        if appdata_path.exists():
            return str(appdata_path)

    return None


def load_config(path: Optional[str] = None, autodiscover: bool = False) -> AgentConfig:
    """YAML 파일 경로가 주어지면 파일에서 로드. 환경변수 override 적용.

    autodiscover=True 이면 path 인자가 비어있을 때 자동 탐색 (RADA_CONFIG →
    ./config.yaml → %APPDATA%/rada/config.yaml). path 인자가 있으면 항상 우선.
    회귀 안전: 기본값 autodiscover=False — 기존 호출 영향 0.
    """
    if not path and autodiscover:
        path = _discover_config_path()

    cfg: AgentConfig
    if not path:
        cfg = AgentConfig()
    else:
        p = Path(path)
        if not p.exists():
            cfg = AgentConfig()
        else:
            try:
                import yaml  # type: ignore
            except ImportError:
                cfg = AgentConfig()
            else:
                with p.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                cfg = _from_dict(data)
    return _apply_env_overrides(cfg)
