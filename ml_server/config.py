"""ml_server 전역 설정 / 상수.

기존 ml_server.py 상단부 상수를 그대로 이전.
"""
from typing import Dict, Optional
import datetime
import os

# ──────────────────────────────────────────
# 윈도우 / 학습 파라미터
# ──────────────────────────────────────────
WINDOW_SIZE      = 120    # 패턴 분석 단기 히스토리 (10분)
TRAIN_WINDOW     = 720    # 학습용 장기 히스토리 (1시간)
MIN_TRAIN_SIZE   = 60     # 최소 학습 샘플 (5분)
RETRAIN_INTERVAL = 60     # N건마다 재학습
SCORE_WINDOW     = 5      # 이상 점수 누적 가중치 윈도우

# 전체 PC 노후화 판단 임계값
GLOBAL_DEGRADATION_RATIO   = 0.7
GLOBAL_DEGRADATION_CPU_THR = 80.0

# LOF 슬라이딩 윈도우 크기
LOF_WINDOW_SIZE = 240

# 시간표 슬롯별 contamination
CONTAMINATION: Dict[str, float] = {
    "class": 0.03,
    "free":  0.08,
}

# Anthropic API
# 호환을 위해 모듈 레벨 상수는 남기되, 런타임 결정은 아래 getter들이 담당.
ANTHROPIC_API_KEY = None
USE_REAL_CLAUDE   = False


def get_anthropic_api_key() -> Optional[str]:
    """ANTHROPIC_API_KEY 환경변수 — 미설정/빈 문자열이면 None."""
    return os.getenv("ANTHROPIC_API_KEY") or None


def use_real_claude() -> bool:
    """USE_REAL_CLAUDE 환경변수 명시 우선, 미설정 시 키 존재 여부."""
    override = os.getenv("USE_REAL_CLAUDE")
    if override is not None:
        return override.lower() in ("1", "true", "yes", "on")
    return get_anthropic_api_key() is not None


def get_claude_model() -> str:
    return os.getenv("CLAUDE_MODEL") or "claude-sonnet-4-5-20250929"


def get_claude_timeout_sec() -> int:
    raw = os.getenv("CLAUDE_TIMEOUT_SEC")
    if raw is None or raw == "":
        return 10
    try:
        return int(raw)
    except ValueError:
        return 10


def get_claude_max_tokens() -> int:
    raw = os.getenv("CLAUDE_MAX_TOKENS")
    if raw is None or raw == "":
        return 500
    try:
        return int(raw)
    except ValueError:
        return 500


# ──────────────────────────────────────────
# 시간표 슬롯
# ──────────────────────────────────────────
def get_timetable_slot(dt: datetime.datetime) -> str:
    """수업 있냐 없냐만 구분 (class / free)."""
    weekday = dt.weekday()
    hour    = dt.hour
    if weekday >= 5:
        return "free"
    if 9 <= hour < 18:
        return "class"
    return "free"


# ──────────────────────────────────────────
# 블랙리스트 / 화이트리스트
# ──────────────────────────────────────────
MINING_PROCESSES = {
    "xmrig","xmrig.exe","nanominer","nanominer.exe",
    "t-rex","t-rex.exe","lolminer","lolminer.exe",
    "gminer","gminer.exe","nbminer","nbminer.exe",
    "phoenixminer","phoenixminer.exe","minerd","cgminer",
    "bfgminer","ethminer","claymore",
}

MINING_POOL_IPS = {
    "155.138.", "66.228.", "45.79.",
    "64.76.", "209.222.",
    "101.251.", "39.104.",
}
# 별칭 (스펙)
POOL_IPS = MINING_POOL_IPS

SUSPICIOUS_PATHS = {
    "/tmp/","/var/tmp/",
    "\\temp\\","\\appdata\\local\\temp\\","\\windows\\temp\\",
}

WHITELIST_PROCESSES = {
    "python.exe","python","java","javaw.exe",
    "chrome.exe","msedge.exe","firefox.exe",
    "pycharm64.exe","idea64.exe","code.exe",
    "slack.exe","zoom.exe","discord.exe",
    "explorer.exe","svchost.exe","system",
    "system idle process","registry","smss.exe",
    "csrss.exe","wininit.exe","services.exe",
    "lsass.exe","winlogon.exe","dwm.exe",
    "runtimebroker.exe","taskhostw.exe",
    "league of legends.exe","leagueclient.exe",
    "leagueclientuxrender.exe",
}
WHITELIST = WHITELIST_PROCESSES

GAME_RENDER_PROCESSES = {
    "sc2_x64.exe","starcraft ii.exe",
    "gta5.exe","rdr2.exe","cyberpunk2077.exe",
    "league of legends.exe","leagueclient.exe",
    "valorant.exe","overwatch.exe","battlenet.exe",
    "steam.exe","steamwebhelper.exe",
    "blender.exe","blender",
    "ffmpeg.exe","ffmpeg","handbrake.exe",
    "davinciresolve.exe","premiere pro.exe",
    "jupyter.exe","jupyter",
}
GAME = GAME_RENDER_PROCESSES

COMPILE_ENCODE_PROCESSES = {
    "cl.exe","gcc","g++","clang","clang++",
    "mspdbsrv.exe","link.exe",
    "java","javac","gradle","mvn",
    "node.exe","node","npm","webpack",
    "cmake","ninja","make",
    "ffmpeg.exe","ffmpeg","handbrake.exe",
    "blender.exe","blender",
}
COMPILE = COMPILE_ENCODE_PROCESSES
