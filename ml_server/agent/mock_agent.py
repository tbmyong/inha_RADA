"""Mock agent — Claude API와 동일 출력 스키마."""
from typing import Dict, Any
from ..model.requests import MetricsRequest


def mock_agent_judgment(metrics: MetricsRequest, pattern_result: dict,
                        global_hw: dict) -> dict:
    verdict   = pattern_result.get("verdict", "NORMAL")
    scores    = pattern_result.get("scores", {})
    signals   = pattern_result.get("signals", {})
    alerts    = pattern_result["alerts"]
    hw_status = "CONFIRMED" if global_hw.get("detected") else "NONE"

    layer1_highs = [a for a in alerts
                    if a.get("type","").startswith("LOCAL_") and a.get("severity") == "HIGH"]
    if layer1_highs:
        types_str = ", ".join(a["type"].replace("LOCAL_","") for a in layer1_highs)
        if any("MEM" in a["type"] for a in layer1_highs):
            mem_pct = metrics.memory_percent
            cpu_pct = metrics.cpu_percent
            if mem_pct >= 95 and cpu_pct < 30:
                return {"judgment":"SUSPICIOUS","severity":"HIGH","hw_degradation":hw_status,
                        "reason":(f"메모리 {mem_pct}% 임계 초과인데 CPU는 {cpu_pct}%로 낮음. "
                                  f"메모리 누수, 좀비 프로세스, 또는 비인가 고부하 작업 가능성."),
                        "action":"작업 관리자에서 메모리 점유 프로세스 확인 및 불필요한 프로세스 종료."}
            return {"judgment":"SUSPICIOUS","severity":"HIGH","hw_degradation":hw_status,
                    "reason":f"에이전트 감지 HIGH 알람: {types_str}.",
                    "action":"해당 지표 현장 확인 필요."}

    # CONFIRMED_MINING은 HIGH_RISK로 통합 — alerts[0].type=CONFIRMED_MINING으로 표현.
    is_confirmed_mining = any(a.get("type") == "CONFIRMED_MINING" for a in alerts)
    if is_confirmed_mining:
        pool_note = " 채굴 풀 IP 통신 가능성." if signals.get("mining_pool_ip") else ""
        return {"judgment":"DANGEROUS","severity":"HIGH","hw_degradation":hw_status,
                "reason":f"채굴 의심 — 확인이 필요합니다.{pool_note} 프로세스 점수={scores.get('process',0)}.",
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
        if scores.get("mem", 0) >= 5:
            return {"judgment":"SUSPICIOUS","severity":"MEDIUM","hw_degradation":hw_status,
                    "reason":f"메모리 {metrics.memory_percent}% 고점유 지속. CPU {metrics.cpu_percent}%와 불균형.",
                    "action":"메모리 점유 상위 프로세스 확인. 크롬 탭 정리 또는 재시작 권장."}
        return {"judgment":"SUSPICIOUS","severity":"MEDIUM","hw_degradation":hw_status,
                "reason":f"의심 점수 {scores.get('final',0):.1f}점. 지속 모니터링 필요.",
                "action":"실행 중인 프로세스 및 네트워크 연결 상태 점검."}

    if verdict == "OBSERVE":
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


class MockAgent:
    def judge(self, metrics: MetricsRequest, pattern_result: Dict[str, Any],
              global_hw: Dict[str, Any]) -> Dict[str, Any]:
        return mock_agent_judgment(metrics, pattern_result, global_hw)
