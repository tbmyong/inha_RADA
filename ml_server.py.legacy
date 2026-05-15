"""
PC 이상탐지 ML 서버 (v8)

[논문 반영]
- Chen et al. (2023) BS-iForest:
    ① 박스플롯 필터: 이상치 포함 서브샘플에서만 iTree 구성 → IF 무작위성 감소
    ② fitness 기반 트리 선발 개념 → contamination 동적 적용으로 대응
- Lu et al. (2023) Review:
    ① LOF kd_tree: O(n²·d) → O(n·log(n)·d) 복잡도 완화
    ② n_jobs=-1: 병렬처리로 추가 완화
    ③ iForestASD: 슬라이딩 윈도우 + concept drift 탐지

[3계층 탐지 구조]
Layer 1 (agent.py): 규칙 기반 절대값 → 즉각 알람
Layer 2 (IF):       전역 이상 탐지  → 채굴/악성코드 등 극단값
Layer 3 (LOF):      로컬 이상 탐지  → 특정 PC vs 동시간대 타 PC 비교

[전체 PC 노후화 탐지]
- 40대 PC 중 임계값 초과 비율이 일정 이상 → 전체 노후화 신호
- 특정 PC만 높음 → LOF의 로컬 이상탐지가 담당
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from collections import deque
import statistics
import datetime
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

app = FastAPI(title="PC 이상탐지 ML 서버 v8")

# ──────────────────────────────────────────
# 상수
# ──────────────────────────────────────────

WINDOW_SIZE      = 120    # 패턴 분석 단기 히스토리 (10분)
TRAIN_WINDOW     = 720    # 학습용 장기 히스토리 (1시간)
MIN_TRAIN_SIZE   = 60     # 최소 학습 샘플 (5분)
RETRAIN_INTERVAL = 60     # N건마다 재학습
SCORE_WINDOW     = 5      # 이상 점수 누적 가중치 윈도우

# 전체 PC 노후화 판단 임계값
# 전체 PC 중 이 비율 이상이 절대 임계값을 초과하면 전체 노후화 의심
GLOBAL_DEGRADATION_RATIO   = 0.7   # 70% 이상
GLOBAL_DEGRADATION_CPU_THR = 80.0  # %

# LOF 슬라이딩 윈도우 크기 (복잡도 완화)
# Lu et al. (2023): O(n²·d) → O(N²·d), N << n
LOF_WINDOW_SIZE = 240  # 최근 240건 (20분치, 5초 × 240)

# ──────────────────────────────────────────
# 시간표 기반 동적 contamination
# Lu et al. (2023): 동적 임계값 선택이 핵심 미래 연구 방향
# ──────────────────────────────────────────

def get_timetable_slot(dt: datetime.datetime) -> str:
    """수업 있냐 없냐만 구분 (class / free)"""
    weekday = dt.weekday()
    hour    = dt.hour
    # 주말 포함 평일 야간 모두 free
    if weekday >= 5:
        return "free"
    if 9 <= hour < 18:
        return "class"
    return "free"

CONTAMINATION: Dict[str, float] = {
    "class": 0.03,   # 수업 중 이상 비율 낮음 → 엄격
    "free":  0.08,   # 야간/주말 패턴 다양 → 느슨
}

# ──────────────────────────────────────────
# 전역 저장소
# ──────────────────────────────────────────

pc_history:         Dict[str, deque] = {}
pc_train_history:   Dict[str, Dict[str, deque]] = {}
pc_models:          Dict[str, Dict[str, dict]]  = {}
pc_score_history:   Dict[tuple, deque] = {}   # (pc_id, slot) 키
rule_score_history: Dict[tuple, deque] = {}   # (pc_id, slot) 키 — 슬롯 혼용 방지

# 전체 PC 최신 메트릭 (전체 노후화 크로스 비교용)
all_pc_latest: Dict[str, dict] = {}

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

# 채굴 풀 알려진 IP 대역 (도메인 → IP 역조회 불가하므로 IP 직접 등록)
# psutil은 도메인이 아닌 IP만 반환하므로 도메인 비교는 작동하지 않음
# 주요 채굴 풀 IP 대역 등록으로 대체
MINING_POOL_IPS = {
    # Ethermine
    "155.138.", "66.228.", "45.79.",
    # NiceHash
    "64.76.", "209.222.",
    # F2Pool
    "101.251.", "39.104.",
}

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

# GPU를 고점유하는 정상 프로세스 (게임·렌더링)
# 이 프로세스 실행 중이면 GPU 패턴 룰 완화
GAME_RENDER_PROCESSES = {
    # 게임
    "sc2_x64.exe","starcraft ii.exe",
    "gta5.exe","rdr2.exe","cyberpunk2077.exe",
    "league of legends.exe","leagueclient.exe",
    "valorant.exe","overwatch.exe","battlenet.exe",
    "steam.exe","steamwebhelper.exe",
    # 렌더링·인코딩
    "blender.exe","blender",
    "ffmpeg.exe","ffmpeg","handbrake.exe",
    "davinciresolve.exe","premiere pro.exe",
    # jupyter만 유지 (python.exe 제거: 채굴 스크립트도 python으로 실행됨)
    "jupyter.exe","jupyter",
}

# CPU를 고점유하는 정상 프로세스 (컴파일·인코딩)
# 이 프로세스 실행 중이면 CPU 채굴 룰 완화
COMPILE_ENCODE_PROCESSES = {
    "cl.exe","gcc","g++","clang","clang++",    # 컴파일러
    "mspdbsrv.exe","link.exe",                 # MSVC 링커
    "java","javac","gradle","mvn",             # Java 빌드
    "node.exe","node","npm","webpack",         # Node 빌드
    "cmake","ninja","make",                    # 빌드 시스템
    "ffmpeg.exe","ffmpeg","handbrake.exe",     # 인코딩
    "blender.exe","blender",                   # 렌더링
}


# ──────────────────────────────────────────
# 요청 모델
# ──────────────────────────────────────────

class GpuMetrics(BaseModel):
    name:               str
    load_percent:       float
    memory_used_mb:     float
    memory_total_mb:    float
    memory_percent:     float
    temperature:        Optional[float] = None
    sm_utilization:     Optional[float] = None
    tensor_core_active: Optional[int]   = None
    power_draw_w:       Optional[float] = None

class MetricsRequest(BaseModel):
    pc_id:                  str
    timestamp:              str
    cpu_percent:            float
    cpu_core_count:         int   = 1
    memory_percent:         float
    memory_used_gb:         float = 0
    memory_total_gb:        float = 0
    inbound_mb:             float
    outbound_mb:            float
    inbound_total_mb:       float = 0
    outbound_total_mb:      float = 0
    external_packet_count:  int
    external_connections:   List[dict] = Field(default_factory=list)
    active_ports:           List[int]  = Field(default_factory=list)
    disk_read_mb:           float = 0
    disk_write_mb:          float = 0
    gpu:                    Optional[GpuMetrics] = None
    top_processes:          List[dict] = Field(default_factory=list)
    local_alerts:           List[dict] = Field(default_factory=list)
    boxplot_signal:         dict       = Field(default_factory=dict)

# ──────────────────────────────────────────
# 피처 엔지니어링
# ──────────────────────────────────────────

def build_features(
    cpu: float, memory: float,
    gpu_pct: float, vram_mb: float, gpu_total_mb: float,
    disk_r: float, disk_w: float, power: float,
) -> list:
    """
    ML 피처 (네트워크 제외)

    [네트워크 피처 제외 이유]
    - inbound/outbound는 유휴→활성 전환 시 수십 배 변동 → 오탐 주범
    - C2 비콘은 소량+규칙적 패턴 → 볼륨 기반 ML로 탐지 불가
    - 네트워크 이상은 모두 룰 기반으로 전담 (analyze_pattern 참조)
    - ML은 CPU/메모리/GPU/디스크 패턴에 집중
    """
    raw = [cpu, memory, gpu_pct, vram_mb, disk_r, disk_w, power]
    gpu_total_safe = gpu_total_mb if gpu_total_mb > 0 else 8192
    derived = [
        cpu / (gpu_pct + 0.001),                   # CPU-GPU 비율 (채굴: GPU만 높음)
        gpu_pct - cpu,                             # 기형 패턴 지표
        gpu_pct * (1 - vram_mb / gpu_total_safe),  # GPU 고점유 + VRAM 낮음
    ]
    return raw + derived


def extract_features_from_snapshot(snap: dict) -> Optional[list]:
    try:
        return build_features(
            cpu=snap.get("cpu_percent", 0),
            memory=snap.get("memory_percent", 0),
            gpu_pct=snap.get("gpu_percent", 0) or 0,
            vram_mb=snap.get("gpu_vram_mb", 0) or 0,
            gpu_total_mb=snap.get("gpu_total_mb", 8192) or 8192,
            disk_r=snap.get("disk_read_mb", 0),
            disk_w=snap.get("disk_write_mb", 0),
            power=snap.get("gpu_power_w", 0) or 0,
        )
    except Exception:
        return None


def extract_features_from_metrics(metrics: MetricsRequest) -> list:
    gpu_total = metrics.gpu.memory_total_mb if metrics.gpu else 8192
    return build_features(
        cpu=metrics.cpu_percent,
        memory=metrics.memory_percent,
        gpu_pct=metrics.gpu.load_percent if metrics.gpu else 0,
        vram_mb=metrics.gpu.memory_used_mb if metrics.gpu else 0,
        gpu_total_mb=gpu_total,
        disk_r=metrics.disk_read_mb,
        disk_w=metrics.disk_write_mb,
        power=metrics.gpu.power_draw_w if metrics.gpu and metrics.gpu.power_draw_w else 0,
    )

# ──────────────────────────────────────────
# 히스토리 스냅샷
# ──────────────────────────────────────────

def make_snapshot(metrics: MetricsRequest) -> dict:
    return {
        "timestamp":             metrics.timestamp,
        "cpu_percent":           metrics.cpu_percent,
        "memory_percent":        metrics.memory_percent,
        "gpu_percent":           metrics.gpu.load_percent      if metrics.gpu else None,
        "gpu_vram_mb":           metrics.gpu.memory_used_mb    if metrics.gpu else None,
        "gpu_total_mb":          metrics.gpu.memory_total_mb   if metrics.gpu else 8192,
        "gpu_power_w":           metrics.gpu.power_draw_w      if metrics.gpu else None,
        "tensor_core_active":    metrics.gpu.tensor_core_active if metrics.gpu else None,
        "inbound_mb":            metrics.inbound_mb,
        "outbound_mb":           metrics.outbound_mb,
        "external_packet_count": metrics.external_packet_count,
        "disk_read_mb":          metrics.disk_read_mb,
        "disk_write_mb":         metrics.disk_write_mb,
        "top_processes":         metrics.top_processes,
    }

def update_train_history(pc_id: str, slot: str, snapshot: dict) -> None:
    if pc_id not in pc_train_history:
        pc_train_history[pc_id] = {}
    if slot not in pc_train_history[pc_id]:
        pc_train_history[pc_id][slot] = deque(maxlen=TRAIN_WINDOW)
    pc_train_history[pc_id][slot].append(snapshot)

# ──────────────────────────────────────────
# BS-iForest 박스플롯 필터
# Chen et al. (2023): 이상치 포함 서브샘플에서만 iTree 구성
# ──────────────────────────────────────────

def boxplot_has_outlier(arr: np.ndarray) -> bool:
    """
    1D 배열에 IQR 기준 이상치가 존재하는지 확인.
    BS-iForest Algorithm 1의 box-plot-filter() 구현.

    [논문 근거]
    - Chen et al. (2023) Algorithm 1, Line 6: if(box-plot-filter(X'))
    - 이상치 없는 서브샘플로는 iTree 생성 안 함 → 무작위성 감소
    """
    if len(arr) < 4:
        return True  # 데이터 부족 시 일단 통과
    q1, q3  = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr     = q3 - q1
    lower   = q1 - 1.5 * iqr
    upper   = q3 + 1.5 * iqr
    return bool(np.any((arr < lower) | (arr > upper)))


def filter_training_data_by_boxplot(X_raw: np.ndarray) -> np.ndarray:
    """
    학습 데이터에서 박스플롯 기준 이상치를 포함하는 서브셋만 선별.
    각 피처별로 이상치 포함 여부를 확인하여 해당 샘플 행을 표시.

    [논문과의 차이]
    - 원 논문: 서브샘플 단위로 tree 구성 여부 결정
    - 여기서는: 전체 학습셋에서 이상치 포함 샘플 인덱스를 마킹
      → sklearn IF의 subsampling과 결합하여 유사 효과 달성

    [복잡도]
    - O(n·d): 각 피처별 IQR 계산, n=학습샘플수, d=피처수
    """
    n_features  = X_raw.shape[1]
    outlier_mask = np.zeros(len(X_raw), dtype=bool)

    for feature_idx in range(n_features):
        col  = X_raw[:, feature_idx]
        q1   = np.percentile(col, 25)
        q3   = np.percentile(col, 75)
        iqr  = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_mask |= (col < lower) | (col > upper)

    # 이상치 포함 샘플 + 무작위 정상 샘플 혼합
    outlier_idx = np.where(outlier_mask)[0]
    normal_idx  = np.where(~outlier_mask)[0]

    if len(outlier_idx) == 0:
        return X_raw

    max_normal = min(len(normal_idx), len(outlier_idx) * 3)
    rng = np.random.RandomState(42)   # 재현성 확보
    if max_normal > 0:
        selected_normal = rng.choice(normal_idx, max_normal, replace=False)
        selected_idx    = np.concatenate([outlier_idx, selected_normal])
    else:
        selected_idx = outlier_idx

    return X_raw[np.sort(selected_idx)]


# ──────────────────────────────────────────
# Rotated Isolation Forest (RIF)
# Monemizadeh & Kiani (2025) — Data Mining and Knowledge Discovery Vol.39
#
# [기존 IF 한계]
# - IF: 축 평행 분할 → axis-aligned ghost cluster 오탐
# - EIF: 랜덤 방향 분할 → inter-cluster ghost 오탐
#
# [RIF 해결]
# 트리마다 QR 분해로 생성한 직교 회전행렬로 데이터를 회전 후
# 일반 iTree 구성 → 두 종류의 ghost cluster 동시 제거
#
# [우리 환경에서의 이점]
# PC 자원 데이터는 수업/유휴/게임 등 다중 군집 형성
# 군집 간 경계 영역(CPU 35%, GPU 55% 등)이 inter-cluster ghost로 오탐 가능
# → RIF로 해결
#
# [복잡도]
# 학습: O(n·m·log n) + QR 분해 O(d³) × m회
#       d=피처수(10), m=트리수(100) → QR 오버헤드 무시 가능
# 예측: IF와 동일
# ──────────────────────────────────────────

class RotatedIsolationForest:
    """
    Rotated Isolation Forest (RIF) 구현
    Monemizadeh & Kiani (2025)

    sklearn IsolationForest와 동일한 인터페이스 제공:
    - fit(X)
    - decision_function(X) → 낮을수록 이상 (IF와 동일)
    - predict(X)           → -1=이상, 1=정상
    """

    def __init__(
        self,
        n_estimators:  int   = 100,
        contamination: float = 0.05,
        random_state:  int   = 42,
    ):
        self.n_estimators  = n_estimators
        self.contamination = contamination
        self.random_state  = random_state
        self.trees:             list = []
        self.rotation_matrices: list = []
        self._threshold:        float = 0.0

    def fit(self, X: np.ndarray) -> "RotatedIsolationForest":
        d   = X.shape[1]
        rng = np.random.RandomState(self.random_state)

        self.trees             = []
        self.rotation_matrices = []

        for _ in range(self.n_estimators):
            # 랜덤 정규분포 행렬 → QR 분해 → 직교 회전행렬 Q
            A = rng.randn(d, d)
            Q, _ = np.linalg.qr(A)   # Q: 직교행렬(거리·각도 보존)

            X_rot = X @ Q             # 데이터 회전

            # 회전된 공간에서 단일 iTree 학습
            tree = IsolationForest(
                n_estimators=1,
                contamination=self.contamination,
                random_state=int(rng.randint(0, 100000)),
                max_samples=min(256, len(X)),  # 원 논문 subsampling 유지
            )
            tree.fit(X_rot)
            self.trees.append(tree)
            self.rotation_matrices.append(Q)

        # 판정 임계값: 학습 데이터 전체 점수의 contamination 분위수
        train_scores = self.decision_function(X)
        self._threshold = float(
            np.percentile(train_scores, self.contamination * 100)
        )
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """낮을수록 이상 (sklearn IF와 동일한 방향)"""
        scores = np.zeros(len(X))
        for tree, Q in zip(self.trees, self.rotation_matrices):
            X_rot   = X @ Q
            scores += tree.decision_function(X_rot)
        return scores / len(self.trees)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """-1=이상, 1=정상"""
        scores = self.decision_function(X)
        return np.where(scores < self._threshold, -1, 1)


# ──────────────────────────────────────────
# 앙상블 모델 학습 (RIF + LOF + RobustScaler)
# ──────────────────────────────────────────

def train_model(pc_id: str, slot: str) -> bool:
    """
    [적용 논문]
    1. Monemizadeh & Kiani (2025) RIF:
       QR 분해 랜덤 회전으로 ghost cluster 오탐 제거
       → 기존 IF(axis-aligned ghost) + EIF(inter-cluster ghost) 모두 해결
    2. Chen et al. (2023) BS-iForest:
       박스플롯 필터로 이상치 포함 서브셋 선별 (sklearn API 제약으로 근사 구현)
    3. Lu et al. (2023) Review:
       LOF kd_tree(O(n²)→O(n·log n)) + n_jobs=-1 병렬처리 + 슬라이딩 윈도우
    """
    try:
        history = pc_train_history.get(pc_id, {}).get(slot, [])
        if len(history) < MIN_TRAIN_SIZE:
            return False

        X_raw = []
        for snap in history:
            feat = extract_features_from_snapshot(snap)
            if feat:
                X_raw.append(feat)

        if len(X_raw) < MIN_TRAIN_SIZE:
            return False

        X_raw = np.array(X_raw)

        # RobustScaler: 이상치에 강건한 정규화
        scaler   = RobustScaler()
        X_scaled = scaler.fit_transform(X_raw)

        contamination = CONTAMINATION.get(slot, 0.05)

        # ── Rotated Isolation Forest ──
        # Monemizadeh & Kiani (2025): QR 분해 회전으로 ghost cluster 제거
        # BS-iForest 박스플롯 필터 전처리와 결합:
        # 이상치 포함 서브셋 선별(BS-iForest) + 회전(RIF) = 두 논문의 시너지
        X_filtered   = filter_training_data_by_boxplot(X_scaled)
        has_filtered = len(X_filtered) >= MIN_TRAIN_SIZE

        if_model = RotatedIsolationForest(
            contamination=contamination,
            n_estimators=100,
            random_state=42,
        )
        if_model.fit(X_filtered if has_filtered else X_scaled)

        # ── Local Outlier Factor ──
        # [복잡도 완화]
        # algorithm='kd_tree': O(n²·d) → O(n·log(n)·d)
        # Lu et al. (2023): kd_tree가 저차원(d<=20)에서 brute force 대비 효율적
        # n_jobs=-1: 모든 CPU 코어 병렬 사용
        # LOF 슬라이딩 윈도우: 전체 n 대신 최근 LOF_WINDOW_SIZE만 사용
        lof_train = X_scaled[-LOF_WINDOW_SIZE:] if len(X_scaled) > LOF_WINDOW_SIZE else X_scaled

        lof_model = LocalOutlierFactor(
            contamination=contamination,
            novelty=True,
            n_neighbors=min(20, len(lof_train) - 1),
            algorithm='kd_tree',   # ← 핵심 복잡도 완화
            n_jobs=-1,             # ← 병렬 처리
        )
        lof_model.fit(lof_train)

        if pc_id not in pc_models:
            pc_models[pc_id] = {}
        pc_models[pc_id][slot] = {
            "if_model":        if_model,
            "lof_model":       lof_model,
            "scaler":          scaler,
            "sample_count":    len(X_raw),
            "lof_window_size": len(lof_train),
            "contamination":   contamination,
            "boxplot_filtered":has_filtered,
        }
        return True

    except Exception as e:
        print(f"[학습 오류] {pc_id}/{slot}: {e}")
        return False

# ──────────────────────────────────────────
# 앙상블 이상 탐지 + 누적 가중 점수
# ──────────────────────────────────────────

def predict_anomaly(pc_id: str, slot: str, metrics: MetricsRequest) -> dict:
    model_info = pc_models.get(pc_id, {}).get(slot)

    if not model_info:
        sample_count = len(pc_train_history.get(pc_id, {}).get(slot, []))
        return {
            "available":      False,
            "reason":         f"학습 데이터 수집 중 ({sample_count}/{MIN_TRAIN_SIZE}건)",
            "is_anomaly":     None,
            "weighted_score": None,
            "if_score":       None,
            "lof_score":      None,
            "sample_count":   None,
        }

    try:
        features = extract_features_from_metrics(metrics)
        X_raw    = np.array([features])
        X_scaled = model_info["scaler"].transform(X_raw)

        # IF 점수
        if_score = float(model_info["if_model"].decision_function(X_scaled)[0])

        # LOF 점수 (sigmoid 정규화)
        lof_raw  = float(model_info["lof_model"].decision_function(X_scaled)[0])
        lof_score = float(2 / (1 + np.exp(-np.clip(lof_raw, -500, 500))) - 1)

        # 앙상블 가중 점수
        ensemble_score = if_score * 0.6 + lof_score * 0.4

        # 누적 가중 점수 — (pc_id, slot) 키로 슬롯 혼용 방지
        score_key = (pc_id, slot)
        if score_key not in pc_score_history:
            pc_score_history[score_key] = deque(maxlen=SCORE_WINDOW)
        pc_score_history[score_key].append(ensemble_score)

        scores   = list(pc_score_history[score_key])
        n        = len(scores)
        weights  = [max(0.2, 1.0 - 0.2 * (n - 1 - i)) for i in range(n)]
        weighted_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)

        if_anomaly  = int(model_info["if_model"].predict(X_scaled)[0]) == -1
        lof_anomaly = int(model_info["lof_model"].predict(X_scaled)[0]) == -1
        is_anomaly  = if_anomaly and lof_anomaly and weighted_score < 0

        # agent.py의 박스플롯 신호와 결합 (보조 지표)
        bp = metrics.boxplot_signal
        bp_flag = (bp.get("available") and
                   (bp.get("cpu_iqr_outlier") or bp.get("mem_iqr_outlier")))

        return {
            "available":         True,
            "is_anomaly":        bool(is_anomaly),
            "if_score":          round(if_score, 4),
            "lof_score":         round(lof_score, 4),
            "lof_raw":           round(lof_raw, 4),
            "weighted_score":    round(weighted_score, 4),
            "if_anomaly":        bool(if_anomaly),
            "lof_anomaly":       bool(lof_anomaly),
            "boxplot_flag":      bool(bp_flag),    # 로컬 박스플롯 신호
            "sample_count":      int(model_info["sample_count"]),
            "lof_window_size":   int(model_info["lof_window_size"]),
            "contamination":     float(model_info["contamination"]),
            "boxplot_filtered":  bool(model_info.get("boxplot_filtered", False)),
        }

    except Exception as e:
        return {
            "available":      False,
            "reason":         f"예측 오류: {e}",
            "is_anomaly":     None,
            "weighted_score": None,
            "if_score":       None,
            "lof_score":      None,
            "sample_count":   None,
        }

# ──────────────────────────────────────────
# 전체 PC 노후화 탐지 (Cross-PC 비교)
# ──────────────────────────────────────────

def detect_global_hw_degradation() -> dict:
    """
    전체 PC 최신 메트릭 비교 (TTL: 30초 이내 데이터만 유효)
    꺼진 PC나 agent가 죽은 PC의 마지막 값이 계속 포함되는 것을 방지
    """
    import time as _time
    now = _time.time()
    TTL = 30.0  # 30초 이내 데이터만 유효

    fresh = {
        pc_id: snap for pc_id, snap in all_pc_latest.items()
        if now - snap.get("_ts", 0) <= TTL
    }

    if len(fresh) < 3:
        return {"detected": False, "reason": f"유효 PC 부족 ({len(fresh)}대, TTL={TTL}초)"}

    total = len(fresh)
    exceed_cpu = sum(
        1 for snap in fresh.values()
        if snap.get("cpu_percent", 0) >= GLOBAL_DEGRADATION_CPU_THR
    )
    exceed_ratio = exceed_cpu / total

    if exceed_ratio >= GLOBAL_DEGRADATION_RATIO:
        avg_cpu = np.mean([s.get("cpu_percent", 0) for s in fresh.values()])
        return {
            "detected":      True,
            "exceed_count":  exceed_cpu,
            "total_pcs":     total,
            "exceed_ratio":  round(exceed_ratio, 2),
            "avg_cpu":       round(float(avg_cpu), 1),
            "detail":        (f"전체 {total}대 중 {exceed_cpu}대 ({exceed_ratio*100:.0f}%)가 "
                              f"CPU {GLOBAL_DEGRADATION_CPU_THR}% 초과 "
                              f"(평균={avg_cpu:.1f}%) → 전체 노후화 또는 고부하 의심"),
        }

    return {
        "detected":     False,
        "exceed_count": exceed_cpu,
        "total_pcs":    total,
        "exceed_ratio": round(exceed_ratio, 2),
    }

# ──────────────────────────────────────────
# 패턴 분석
# ──────────────────────────────────────────

def analyze_pattern(metrics: MetricsRequest, history: deque, slot: str,
                    ml_weighted_score: float = 0.0) -> dict:
    """
    EDR 스타일 이상 탐지 엔진 (v2)

    [구조]
    Layer 1 - Signal:    원자 단위 신호 수집 (판단 없음)
    Layer 2 - Indicator: 신호 조합 → 카테고리별 점수
    Layer 3 - Scoring:   전체 점수 합산 + ML 앙상블 통합 + 컨텍스트 감점
    Layer 4 - Verdict:   임계값 기반 최종 판단

    [점수 등급 표준화]
    CRITICAL (확정 증거)  = 10  ex) 알려진 채굴 프로세스 이름
    HIGH     (강한 의심)  =  5  ex) 채굴 풀 IP 직접 통신
    MEDIUM   (보조 신호)  =  3  ex) GPU 일직선 + CPU 낮음
    INFO     (참고 신호)  =  1  ex) 외부 연결 건수 높음

    [스텔스 핵심 원칙]
    "점유율은 낮게 속이는데 하드웨어는 갈구는 모순(Mismatch)"이 반드시 있어야 함
    단순 유휴 상태(GPU 0% + 전력 낮음)는 스텔스 점수 0점
    """
    history_list = list(history)
    has_history  = len(history_list) >= 12
    pc_id        = metrics.pc_id   # score_key 생성에 필요

    gpu = metrics.gpu

    # ════════════════════════════════════════
    # LAYER 1: SIGNAL (원자 단위 신호)
    # ════════════════════════════════════════

    running_procs = {p.get("name","").lower() for p in metrics.top_processes}
    is_gaming    = bool(running_procs & {g.lower() for g in GAME_RENDER_PROCESSES})
    is_compiling = bool(running_procs & {c.lower() for c in COMPILE_ENCODE_PROCESSES})

    # ── GPU 기초값 ──
    gpu_pct    = gpu.load_percent      if gpu else 0.0
    vram_mb    = gpu.memory_used_mb    if gpu else 0.0
    vram_total = (gpu.memory_total_mb  if gpu else 0.0) or 8192.0
    tensor     = gpu.tensor_core_active if gpu else None
    power      = gpu.power_draw_w      if gpu else None
    sm         = gpu.sm_utilization    if gpu else None
    vram_ratio = vram_mb / vram_total
    gpu_active = gpu_pct >= 30.0   # GPU가 실제 작동 중인지 (유휴 구분 가드)

    # ── GPU 히스토리 통계 ──
    gpu_stddev = vram_stddev = power_stddev = avg_power = avg_gpu_pct = None

    if has_history and gpu:
        gpu_vals = [h["gpu_percent"] for h in history_list if h.get("gpu_percent") is not None]
        if len(gpu_vals) >= 12:
            gpu_stddev  = statistics.stdev(gpu_vals)
            avg_gpu_pct = statistics.mean(gpu_vals)

        vram_vals = [h["gpu_vram_mb"] for h in history_list if h.get("gpu_vram_mb") is not None]
        if len(vram_vals) >= 12:
            vram_stddev = statistics.stdev(vram_vals)

        power_vals = [h["gpu_power_w"] for h in history_list if h.get("gpu_power_w")]
        if len(power_vals) >= 12:
            avg_power    = statistics.mean(power_vals)
            power_stddev = statistics.stdev(power_vals)

    # ── CPU 히스토리 통계 ──
    cpu_stddev = avg_cpu = None
    if has_history:
        cpu_vals   = [h["cpu_percent"] for h in history_list]
        cpu_stddev = statistics.stdev(cpu_vals)
        avg_cpu    = statistics.mean(cpu_vals)

    # ── 네트워크 히스토리 통계 ──
    avg_inbound = avg_outbound = avg_ext_count = 0.0
    outbound_stddev = None
    if has_history:
        avg_inbound  = statistics.mean([h["inbound_mb"]  for h in history_list])
        avg_outbound = statistics.mean([h["outbound_mb"] for h in history_list])
        avg_ext_count= statistics.mean([h["external_packet_count"] for h in history_list])
        ob_vals = [h["outbound_mb"] for h in history_list]
        if len(ob_vals) >= 2:
            outbound_stddev = statistics.stdev(ob_vals)

    # ── 네트워크 현재값 ──
    mining_pool_hit = any(
        conn.get("ip","").startswith(prefix)
        for conn in metrics.external_connections
        for prefix in MINING_POOL_IPS
    )
    mining_pool_ip_str = next(
        (conn.get("ip","") for conn in metrics.external_connections
         if any(conn.get("ip","").startswith(p) for p in MINING_POOL_IPS)), ""
    )

    # DoS 임계값 (class: 느슨, free: 엄격)
    dos_ratio     = {"class": 30, "free": 15}.get(slot, 15)
    dos_spike_hit = avg_inbound > 0 and metrics.inbound_mb > avg_inbound * dos_ratio

    # Outbound 급증 (데이터 유출 핵심 신호)
    outbound_spike = (avg_outbound > 0.01
                      and metrics.outbound_mb > avg_outbound * 5
                      and metrics.outbound_mb > 1.0)

    # ── 프로세스 ──
    known_miners = [p for p in metrics.top_processes
                    if p.get("name","").lower() in MINING_PROCESSES]
    temp_exec    = [p for p in metrics.top_processes
                    if any(sp in p.get("path","").lower() for sp in SUSPICIOUS_PATHS)
                    and p.get("name","").lower() not in WHITELIST_PROCESSES]

    persistent_miner = has_history and len(known_miners) > 0 and any(
        sum(1 for h in history_list
            if any(p.get("name","").lower() == m.get("name","").lower()
                   for p in h.get("top_processes",[]))) >= 6
        for m in known_miners
    )

    # ── 스텔스 모순(Mismatch) 신호 ──
    # 핵심: "점유율은 낮은데 하드웨어는 갈구는" 모순
    # 시점 통일: avg_power vs avg_gpu_pct (둘 다 히스토리 평균)
    stealth_mismatch_power = (avg_power    is not None
                               and avg_gpu_pct is not None
                               and avg_power    >= 80.0   # 평균 전력 높은데
                               and avg_gpu_pct  < 30.0)   # 평균 GPU%는 낮음
    stealth_mismatch_vram  = (vram_ratio > 0.7            # VRAM은 가득 찼는데
                               and gpu_pct < 20.0)        # GPU%는 거의 0

    # ── 신호 딕셔너리 ──
    signals: Dict[str, Any] = {
        # 컨텍스트
        "is_gaming":        is_gaming,
        "is_compiling":     is_compiling,
        # GPU (gpu_active 가드 적용)
        "gpu_active":       gpu_active,
        "gpu_high":         gpu_pct >= 70,
        "gpu_flat":         (gpu_stddev is not None
                             and gpu_stddev < 5.0
                             and gpu_active),           # ← 유휴(0%) 오탐 방지 가드
        "gpu_cpu_gap":      gpu_pct >= 70 and metrics.cpu_percent < 20,
        "vram_low":         vram_ratio < 0.3 and gpu_active,
        "vram_stable":      (vram_stddev is not None
                             and vram_stddev < 50
                             and gpu_active),           # ← 유휴 오탐 방지 가드
        "power_stable":     (power_stddev is not None
                             and power_stddev < 10.0    # 5→10W로 완화
                             and gpu_active             # GPU 실제 작동 중일 때만
                             and avg_power is not None
                             and avg_power >= 60.0),    # 전력 자체도 어느 정도 있어야
        "tensor_inactive":  tensor is not None and tensor == 0 and gpu_active,
        "sm_high":          sm is not None and sm >= 70,
        # 스텔스 모순 신호 (Mismatch - 핵심)
        "stealth_mismatch_power": stealth_mismatch_power,
        "stealth_mismatch_vram":  stealth_mismatch_vram,
        # CPU (cpu_active 가드 적용)
        "cpu_high":         metrics.cpu_percent >= 80,
        "cpu_flat":         (cpu_stddev is not None
                             and cpu_stddev < 5.0
                             and metrics.cpu_percent >= 60),
        # 메모리
        "mem_critical":     metrics.memory_percent >= 95,   # 절대 임계
        "mem_high":         metrics.memory_percent >= 85,   # 경고 수준  # ← 유휴(낮은 CPU) 오탐 방지
        # 네트워크
        "net_external_high": metrics.external_packet_count >= 8,
        "mining_pool_ip":    mining_pool_hit,
        "outbound_spike":    outbound_spike,
        "dos_spike":         dos_spike_hit,
        # 프로세스
        "known_miner":       len(known_miners) > 0,
        "temp_exec":         len(temp_exec) > 0,
        "persistent_miner":  persistent_miner,
        "persistent_ext":    avg_ext_count >= 8,  # 5→8 상향 (Windows Update 등 오탐 방지)
        # ML 앙상블 통합 신호
        "ml_anomaly":        ml_weighted_score < -0.1,  # IF+LOF가 이상으로 판단
    }

    # ════════════════════════════════════════
    # LAYER 2: INDICATOR (신호 → 카테고리 점수)
    # 점수 단위: CRITICAL=10 / HIGH=5 / MEDIUM=3 / INFO=1
    # ════════════════════════════════════════

    # ── GPU 채굴 점수 ──
    gpu_mining_score = 0
    if signals["gpu_high"]:                          gpu_mining_score += 1  # INFO
    if signals["gpu_flat"]:                          gpu_mining_score += 3  # MEDIUM (핵심)
    if signals["gpu_cpu_gap"]:                       gpu_mining_score += 3  # MEDIUM
    if signals["net_external_high"]:                 gpu_mining_score += 1  # INFO
    if signals["mining_pool_ip"]:                    gpu_mining_score += 5  # HIGH
    if signals["tensor_inactive"] and signals["vram_low"]: gpu_mining_score += 3  # MEDIUM
    if signals["is_gaming"]:                         gpu_mining_score -= 5  # 감점

    # ── CPU 채굴 점수 ──
    cpu_mining_score = 0
    if signals["cpu_high"]:                          cpu_mining_score += 1  # INFO
    if signals["cpu_flat"]:                          cpu_mining_score += 3  # MEDIUM (핵심)
    if not signals["gpu_high"]:                      cpu_mining_score += 1  # INFO
    if signals["mining_pool_ip"]:                    cpu_mining_score += 5  # HIGH
    # KT 클라우드 패턴 1: GPU 0% + CPU 고점유 일직선 → CPU only miner 강력 의심
    # (GPU 없거나 유휴 상태에서 CPU만 풀가동 = 정상 AI 작업 패턴 아님)
    if not signals["gpu_active"] and signals["cpu_high"] and signals["cpu_flat"]:
                                                     cpu_mining_score += 2  # MEDIUM
    if signals["is_compiling"]:                      cpu_mining_score -= 5  # 감점
    if signals["is_gaming"]:                         cpu_mining_score -= 3  # 감점

    # ── 스텔스 채굴 점수 ──
    # 반드시 모순 신호(mismatch) 하나 이상이 있어야 의미 있음
    # 모순 없으면 = 그냥 유휴 상태
    stealth_score = 0
    has_mismatch = signals["stealth_mismatch_power"] or signals["stealth_mismatch_vram"]
    if has_mismatch:
        if signals["stealth_mismatch_power"]:        stealth_score += 5  # HIGH (모순 핵심)
        if signals["stealth_mismatch_vram"]:         stealth_score += 5  # HIGH (모순 핵심)
        # 모순이 있는 상태에서 추가 보조 신호
        if signals["vram_stable"]:                   stealth_score += 1  # INFO
        if signals["gpu_flat"]:                      stealth_score += 1  # INFO
        if signals["power_stable"]:                  stealth_score += 1  # INFO
        if signals["is_gaming"]:                     stealth_score -= 3
        if signals["is_compiling"]:                  stealth_score -= 2
    # 모순 없으면 stealth_score = 0 (유휴 상태 오탐 방지)

    # ── 데이터 유출 점수 ──
    exfil_score = 0
    if signals["outbound_spike"]:                    exfil_score += 5  # HIGH (핵심)
    if signals["net_external_high"]:                 exfil_score += 1  # INFO

    # ── 프로세스 점수 ──
    process_score = 0
    if signals["known_miner"]:                       process_score += 10  # CRITICAL
    if signals["persistent_miner"]:                  process_score +=  3  # MEDIUM
    if signals["temp_exec"]:                         process_score +=  1  # INFO

    # ── DoS 점수 ──
    dos_score = 0
    if signals["dos_spike"]:                         dos_score += 5  # HIGH

    # ── 백도어 점수 ──
    # 비수업 시간(free) 지속적 외부 통신이 핵심
    backdoor_score = 0
    if slot == "free":
        if signals["persistent_ext"]:                backdoor_score += 3  # MEDIUM
        if signals["net_external_high"]:             backdoor_score += 1  # INFO

    # ── 메모리 점수 ──
    # 악성 프로그램과 정상 고사용(IDE + 크롬 다수 탭)이 동일한 수치를 보임
    # → 단독으로는 판단 불가 → INFO 수준(1점)으로 낮게 유지
    # → 다른 의심 신호(채굴, 유출 등)와 겹칠 때만 점수에 기여
    mem_score = 0
    if signals["mem_critical"]:                      mem_score += 1   # INFO
    if signals["mem_high"] and not signals["cpu_high"]:
                                                     mem_score += 1   # INFO
        # outbound_spike가 함께 있으면 데이터 유출로 더 무겁게 처리 (exfil이 담당)

    # ── ML 앙상블 통합 ──
    ml_score = 0
    if signals["ml_anomaly"]:
        # -0.1 ~ -1.0 → 1 ~ 5점 (0이 되는 버그 방지: max(1, ...))
        ml_contribution = min(5, max(1, int(abs(ml_weighted_score) * 5)))
        ml_score += ml_contribution

    # ════════════════════════════════════════
    # LAYER 3: RISK SCORING
    # ════════════════════════════════════════

    raw_score = (
        gpu_mining_score +
        cpu_mining_score +
        stealth_score +
        exfil_score +
        process_score +
        dos_score +
        backdoor_score +
        mem_score +
        ml_score
    )

    # 컨텍스트 감점 (process_score는 확정 증거라 제외)
    context_multiplier = 1.0
    if is_gaming:    context_multiplier *= 0.4
    if is_compiling: context_multiplier *= 0.5
    adjusted_score = process_score + (raw_score - process_score) * context_multiplier

    # 점수 누적 (최근 5건 가중 평균) — (pc_id, slot) 키로 슬롯 혼용 방지
    score_key = (pc_id, slot)
    if score_key not in rule_score_history:
        rule_score_history[score_key] = deque(maxlen=5)
    rule_score_history[score_key].append(adjusted_score)

    score_list = list(rule_score_history[score_key])
    n          = len(score_list)
    weights    = [max(0.2, 1.0 - 0.2 * (n - 1 - i)) for i in range(n)]
    final_score= sum(s * w for s, w in zip(score_list, weights)) / sum(weights)

    # ════════════════════════════════════════
    # LAYER 4: VERDICT
    # ════════════════════════════════════════

    if process_score >= 10:
        verdict  = "CONFIRMED_MINING"
        severity = "HIGH"
    elif final_score >= 12:
        verdict  = "HIGH_RISK"
        severity = "HIGH"
    elif final_score >= 6:
        verdict  = "SUSPICIOUS"
        severity = "MEDIUM"
    elif final_score >= 3:
        verdict  = "LOW_RISK"
        severity = "LOW"
    else:
        verdict  = "NORMAL"
        severity = "NORMAL"

    # ════════════════════════════════════════
    # ALERT 생성
    # ════════════════════════════════════════
    alerts = []

    if verdict == "CONFIRMED_MINING":
        miner_names = [m["name"] for m in known_miners]
        pool_note   = f" + 채굴풀IP({mining_pool_ip_str})" if mining_pool_hit else ""
        alerts.append({"type":"CONFIRMED_MINING","severity":"HIGH",
                        "detail":f"채굴 프로세스: {miner_names}{pool_note}",
                        "score":round(final_score,2)})
        if signals["persistent_miner"]:
            alerts.append({"type":"PROCESS_PERSISTENT","severity":"HIGH",
                            "detail":"채굴 프로세스 히스토리 6회 이상 지속",
                            "score":round(final_score,2)})

    elif verdict in ("HIGH_RISK","SUSPICIOUS","LOW_RISK"):
        top_cat = max([
            ("GPU_MINING",  gpu_mining_score),
            ("CPU_MINING",  cpu_mining_score),
            ("STEALTH",     stealth_score),
            ("EXFIL",       exfil_score),
            ("BACKDOOR",    backdoor_score),
            ("DOS",         dos_score),
            ("MEMORY",      mem_score),
            ("ML",          ml_score),
        ], key=lambda x: x[1])
        active = [k for k, v in signals.items()
                  if v is True and k not in ("is_gaming","is_compiling")]
        ctx = []
        if is_gaming:    ctx.append("게임(-60%)")
        if is_compiling: ctx.append("컴파일(-50%)")
        alerts.append({
            "type":     f"{verdict}_{top_cat[0]}",
            "severity": {"HIGH_RISK":"HIGH","SUSPICIOUS":"MEDIUM","LOW_RISK":"LOW"}[verdict],
            "detail":   (f"점수={final_score:.1f} 주요원인={top_cat[0]}({top_cat[1]}점) "
                         f"활성신호={active}"
                         + (f" 컨텍스트감점={ctx}" if ctx else "")),
            "score":    round(final_score, 2),
        })

    # DoS는 점수와 무관하게 즉시 알람
    if signals["dos_spike"] and avg_inbound > 0:
        threshold = dos_ratio
        alerts.append({"type":"DOS_SUSPECTED","severity":"HIGH",
                        "detail":(f"Inbound 급증 {metrics.inbound_mb:.3f}MB/5s "
                                  f"(평균={avg_inbound:.3f}, {metrics.inbound_mb/avg_inbound:.1f}배, 기준={threshold}배)"),
                        "score":round(dos_score,2)})

    # agent Layer1 경고 통합
    for la in metrics.local_alerts:
        if la.get("severity") in ("HIGH","MEDIUM"):
            alerts.append({"type":f"LOCAL_{la.get('type','UNKNOWN')}",
                           "severity":la["severity"],
                           "detail":f"[에이전트] {la.get('detail','')}",
                           "score":0})

    overall = ("HIGH"   if any(a["severity"]=="HIGH"   for a in alerts) else
               "MEDIUM" if any(a["severity"]=="MEDIUM" for a in alerts) else
               "LOW"    if any(a["severity"]=="LOW"    for a in alerts) else "NORMAL")

    return {
        "timetable_slot":   slot,
        "overall_severity": overall,
        "alerts":           alerts,
        "verdict":          verdict,
        "scores": {
            "final":              round(final_score, 2),
            "adjusted":           round(adjusted_score, 2),
            "raw":                round(raw_score, 2),
            "gpu_mining":         gpu_mining_score,
            "cpu_mining":         cpu_mining_score,
            "stealth":            stealth_score,
            "exfil":              exfil_score,
            "process":            process_score,
            "dos":                dos_score,
            "backdoor":           backdoor_score,
            "mem":                mem_score,
            "ml":                 ml_score,
            "context_multiplier": round(context_multiplier, 2),
        },
        "signals": {k: bool(v) if not isinstance(v, bool) else v
                    for k, v in signals.items()},
    }
ANTHROPIC_API_KEY = None
USE_REAL_CLAUDE   = ANTHROPIC_API_KEY is not None


def build_prompt(metrics: MetricsRequest, pattern_result: dict,
                 global_hw: dict) -> str:
    alerts_text = "\n".join(
        [f"- [{a['severity']}] {a['type']}: {a['detail']}" for a in pattern_result["alerts"]]
    )
    procs_text = "\n".join(
        [f"- {p['name']} (CPU {p['cpu_percent']}%, MEM {p['memory_percent']}%, {p['path']})"
         for p in metrics.top_processes[:5]]
    )
    gpu_text = ""
    if metrics.gpu:
        gpu_text = (f"GPU {metrics.gpu.load_percent}%, VRAM {metrics.gpu.memory_used_mb}MB, "
                    f"SM {metrics.gpu.sm_utilization}%, 텐서코어 {metrics.gpu.tensor_core_active}%, "
                    f"전력 {metrics.gpu.power_draw_w}W")

    global_hw_text = ""
    if global_hw.get("detected"):
        global_hw_text = f"\n[전체 PC 노후화 신호]\n{global_hw.get('detail','')}"

    scores   = pattern_result.get("scores", {})
    verdict  = pattern_result.get("verdict", "NORMAL")
    signals  = pattern_result.get("signals", {})
    active_s = [k for k, v in signals.items() if v and k not in ("is_gaming","is_compiling")]

    return f"""당신은 학교 실습실 PC 보안 및 유지보수 분석 전문가입니다.
아래 데이터를 분석해 이상 여부를 판단하고 JSON으로만 응답하세요.

[현재 메트릭]
PC={metrics.pc_id}, 시각={metrics.timestamp}, 시간표={pattern_result['timetable_slot']}
CPU={metrics.cpu_percent}%, 메모리={metrics.memory_percent}%
{gpu_text}
외부연결={metrics.external_packet_count}건, Net ↑{metrics.outbound_mb}MB/5s ↓{metrics.inbound_mb}MB/5s
{global_hw_text}

[EDR 분석 결과]
verdict={verdict}, 최종점수={scores.get('final',0):.1f}
(GPU채굴:{scores.get('gpu_mining',0)} CPU채굴:{scores.get('cpu_mining',0)} 스텔스:{scores.get('stealth',0)} 유출:{scores.get('exfil',0)} 프로세스:{scores.get('process',0)})
컨텍스트배율={scores.get('context_multiplier',1.0)} (게임={signals.get('is_gaming',False)}, 컴파일={signals.get('is_compiling',False)})
활성신호={active_s}

[탐지 알람]
{alerts_text if alerts_text else "- 이상 없음"}

[프로세스]
{procs_text}

JSON 형식으로만 응답:
{{"judgment":"NORMAL|SUSPICIOUS|DANGEROUS","severity":"LOW|MEDIUM|HIGH",
  "reason":"판단근거(2~3문장)","action":"추천조치",
  "hw_degradation":"NONE|SUSPECTED|CONFIRMED"}}""".strip()


def call_claude_api(prompt: str) -> dict:
    import requests as req, json
    response = req.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-20250514", "max_tokens": 500,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=10,
    )
    return json.loads(response.json()["content"][0]["text"])


def mock_agent_judgment(metrics: MetricsRequest, pattern_result: dict,
                        global_hw: dict) -> dict:
    verdict   = pattern_result.get("verdict", "NORMAL")
    scores    = pattern_result.get("scores", {})
    signals   = pattern_result.get("signals", {})
    alerts    = pattern_result["alerts"]
    alert_types = {a["type"] for a in alerts}
    hw_status = "CONFIRMED" if global_hw.get("detected") else "NONE"

    # ── Layer1 HIGH 알람 우선 처리 ──
    # EDR 점수와 무관하게 Layer1이 HIGH면 AI Agent도 반응해야 함
    layer1_highs = [a for a in alerts
                    if a.get("type","").startswith("LOCAL_") and a.get("severity") == "HIGH"]
    if layer1_highs:
        types_str = ", ".join(a["type"].replace("LOCAL_","") for a in layer1_highs)
        # 메모리 절대 임계 초과 케이스
        if any("MEM" in a["type"] for a in layer1_highs):
            mem_pct = metrics.memory_percent
            cpu_pct = metrics.cpu_percent
            if mem_pct >= 95 and cpu_pct < 30:
                return {"judgment":"SUSPICIOUS","severity":"HIGH","hw_degradation":hw_status,
                        "reason":(f"메모리 {mem_pct}% 임계 초과인데 CPU는 {cpu_pct}%로 낮음. "
                                  f"메모리 누수, 좀비 프로세스, 또는 백그라운드 악성코드 의심."),
                        "action":"작업 관리자에서 메모리 점유 프로세스 확인 및 불필요한 프로세스 종료."}
            return {"judgment":"SUSPICIOUS","severity":"HIGH","hw_degradation":hw_status,
                    "reason":f"에이전트 감지 HIGH 알람: {types_str}.",
                    "action":"해당 지표 현장 확인 필요."}

    # verdict 기반 판단 (EDR 점수 체계 반영)
    if verdict == "CONFIRMED_MINING":
        pool_note = " 채굴 풀 IP 통신 확인." if signals.get("mining_pool_ip") else ""
        return {"judgment":"DANGEROUS","severity":"HIGH","hw_degradation":hw_status,
                "reason":f"채굴 프로세스가 확인되었습니다.{pool_note} 프로세스 점수={scores.get('process',0)}.",
                "action":"해당 프로세스 즉시 강제 종료 및 관리자 현장 확인."}

    if verdict == "HIGH_RISK":
        top = max([
            ("GPU 채굴", scores.get("gpu_mining", 0)),
            ("CPU 채굴", scores.get("cpu_mining", 0)),
            ("스텔스",   scores.get("stealth", 0)),
            ("데이터 유출", scores.get("exfil", 0)),
            ("DoS",      scores.get("dos", 0)),
            ("메모리",   scores.get("mem", 0)),
        ], key=lambda x: x[1])
        ctx = ""
        if signals.get("is_gaming"):    ctx = " (게임 실행 중 감점 적용)"
        if signals.get("is_compiling"): ctx = " (컴파일 중 감점 적용)"
        return {"judgment":"DANGEROUS","severity":"HIGH","hw_degradation":hw_status,
                "reason":f"위험 점수 {scores.get('final',0):.1f}점. 주요 원인: {top[0]}({top[1]}점).{ctx}",
                "action":"즉시 현장 확인 및 의심 프로세스 강제 종료."}

    if verdict == "SUSPICIOUS":
        # 메모리 주원인인 경우 특화 메시지
        if scores.get("mem", 0) >= 5:
            return {"judgment":"SUSPICIOUS","severity":"MEDIUM","hw_degradation":hw_status,
                    "reason":f"메모리 {metrics.memory_percent}% 고점유 지속. CPU {metrics.cpu_percent}%와 불균형.",
                    "action":"메모리 점유 상위 프로세스 확인. 크롬 탭 정리 또는 재시작 권장."}
        return {"judgment":"SUSPICIOUS","severity":"MEDIUM","hw_degradation":hw_status,
                "reason":f"의심 점수 {scores.get('final',0):.1f}점. 지속 모니터링 필요.",
                "action":"실행 중인 프로세스 및 네트워크 연결 상태 점검."}

    if verdict == "LOW_RISK":
        return {"judgment":"SUSPICIOUS","severity":"LOW","hw_degradation":hw_status,
                "reason":f"낮은 위험 점수 {scores.get('final',0):.1f}점. 경미한 이상 신호.",
                "action":"지속 관찰 후 패턴 지속 시 현장 확인."}

    if global_hw.get("detected"):
        return {"judgment":"SUSPICIOUS","severity":"MEDIUM","hw_degradation":"SUSPECTED",
                "reason":f"하드웨어 노후화 징후: {global_hw.get('detail','')}",
                "action":"해당 PC 점검 예약. 발열 상태 및 디스크 상태 확인 권장."}

    return {"judgment":"NORMAL","severity":"LOW","hw_degradation":hw_status,
            "reason":f"정상 범위. 최종점수={scores.get('final',0):.1f}. CPU {metrics.cpu_percent}%, 메모리 {metrics.memory_percent}%.",
            "action":"조치 불필요."}


def run_ai_agent(metrics: MetricsRequest, pattern_result: dict, global_hw: dict) -> dict:
    if USE_REAL_CLAUDE:
        try:
            return call_claude_api(build_prompt(metrics, pattern_result, global_hw))
        except Exception as e:
            print(f"  [Claude API 오류] {e} → Mock으로 대체")
    return mock_agent_judgment(metrics, pattern_result, global_hw)

# ──────────────────────────────────────────
# numpy 직렬화 변환
# ──────────────────────────────────────────

def sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(i) for i in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    return obj

# ──────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────

@app.post("/analyze")
def analyze(metrics: MetricsRequest):
    pc_id = metrics.pc_id
    dt    = datetime.datetime.fromisoformat(metrics.timestamp)
    slot  = get_timetable_slot(dt)

    if pc_id not in pc_history:
        pc_history[pc_id] = deque(maxlen=WINDOW_SIZE)

    snapshot = make_snapshot(metrics)
    pc_history[pc_id].append(snapshot)
    update_train_history(pc_id, slot, snapshot)

    # 전체 PC 최신 메트릭 업데이트 (TTL 기반 신선도 검사용 _ts 포함)
    import time as _time
    all_pc_latest[pc_id] = {
        "cpu_percent":    metrics.cpu_percent,
        "memory_percent": metrics.memory_percent,
        "timestamp":      metrics.timestamp,
        "_ts":            _time.time(),  # TTL 계산용 실수 타임스탬프
    }

    # 재학습 — last_train_count 방식 (modulo 버그 수정)
    # train_size % RETRAIN_INTERVAL == 0 방식은 오류 시 다음 배수까지 기다려야 함
    train_size = len(pc_train_history.get(pc_id, {}).get(slot, []))
    last_count = pc_models.get(pc_id, {}).get(slot, {}).get("sample_count", 0)
    if train_size >= MIN_TRAIN_SIZE and train_size - last_count >= RETRAIN_INTERVAL:
        if train_model(pc_id, slot):
            model_info = pc_models[pc_id][slot]
            print(f"[학습 완료] PC={pc_id}, 슬롯={slot}, 샘플={train_size}건, "
                  f"contamination={model_info['contamination']}, "
                  f"LOF윈도우={model_info['lof_window_size']}건, "
                  f"박스플롯필터={'✅' if model_info['boxplot_filtered'] else '❌'}")

    # 앙상블 예측 (IF + LOF) - 패턴 분석보다 먼저 실행해서 ML 점수를 EDR에 통합
    if_result = predict_anomaly(pc_id, slot, metrics)
    ml_weighted = if_result.get("weighted_score") or 0.0

    # 패턴 분석 (ML 점수를 Signal로 통합)
    pattern_result = analyze_pattern(metrics, pc_history[pc_id], slot,
                                     ml_weighted_score=ml_weighted)

    # 전체 PC 노후화 탐지
    global_hw = detect_global_hw_degradation()
    if global_hw.get("detected"):
        pattern_result["alerts"].append({
            "type":     "GLOBAL_HW_DEGRADATION",
            "severity": "MEDIUM",
            "detail":   global_hw["detail"],
        })
        if pattern_result["overall_severity"] == "NORMAL":
            pattern_result["overall_severity"] = "MEDIUM"

    # AI Agent (이상 또는 노후화 의심 시 실행)
    agent_result = None
    if pattern_result["overall_severity"] != "NORMAL":
        agent_result = run_ai_agent(metrics, pattern_result, global_hw)

    return sanitize({
        "pc_id":               pc_id,
        "timestamp":           metrics.timestamp,
        "timetable_slot":      slot,
        "overall_severity":    pattern_result["overall_severity"],
        "verdict":             pattern_result.get("verdict", "NORMAL"),
        "alerts":              pattern_result["alerts"],
        "scores":              pattern_result.get("scores", {}),
        "signals":             pattern_result.get("signals", {}),
        "history_size":        len(pc_history[pc_id]),
        "isolation_forest":    if_result,
        "global_hw_degradation": global_hw,
        "agent":               agent_result,
    })


@app.get("/status")
def status():
    return {
        "status":           "running",
        "monitored_pcs":    list(pc_history.keys()),
        "total_pcs":        len(all_pc_latest),
        "pc_history_sizes": {pc_id: len(h) for pc_id, h in pc_history.items()},
        "trained_models":   {
            pc_id: list(slots.keys()) for pc_id, slots in pc_models.items()
        },
        "global_hw_latest": detect_global_hw_degradation(),
    }


@app.delete("/history/{pc_id}")
def clear_history(pc_id: str):
    if pc_id in pc_history:
        pc_history[pc_id].clear()
        pc_score_history.pop(pc_id, None)
        all_pc_latest.pop(pc_id, None)
        return {"message": f"{pc_id} 히스토리 초기화 완료"}
    return {"message": f"{pc_id} 없음"}
