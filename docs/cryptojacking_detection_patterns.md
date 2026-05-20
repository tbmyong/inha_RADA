# Cryptojacking Detection Patterns — Reference Catalog

본 문서는 RADA 의 카테고리 기반 mining 탐지 신호 설계를 위한 reference. 공신력 있는 학술 논문 + 산업 자료를 인용해 정상 워크로드 (학습/dev/게임/렌더링) 와 cryptojacking 의 행동 차이를 패턴별로 정리.

핵심 설계 원칙:
- **단일 패턴 발화 ≠ mining 판정**. 다수 카테고리가 동시에 + 장시간 만족할 때만 의심.
- **자원 사용량은 mining 의 *결과* 이지 *시그니처* 가 아님** — 패턴의 변화/조합이 시그니처.
- **allowlist/blacklist 대신 행동 패턴**으로 분류 (이름 위장 mining 대비).

---

## 1. 자원 사용 패턴 (Resource Pattern)

| # | 패턴 | 임계값 / 조건 | 정상 발생 가능성 | 출처 |
|---|---|---|---|---|
| R1 | CPU 사용률 **지속 + 평평** | CPU ≥ 90% AND std < 5% sustained 30분+ | 빌드/렌더링은 5~10분 burst | KT cloud, velog |
| R2 | GPU 사용률 **지속 + 평평** | GPU ≥ 90% AND std < 5% sustained 30분+ | 게임/ML 학습은 변동성 큼 | velog ("Drop 구간 없음"), KT cloud |
| R3 | CPU-GPU **동시 풀가동** | CPU ≥ 90% AND GPU ≥ 90% sustained | 거의 없음 (게임도 GPU 위주) | KT cloud |
| R4 | GPU-only **비대칭** (CPU mining 反대) | GPU ≥ 90% AND CPU < 15% sustained | 비디오 인코딩 일부 | velog, Tanana 2024 |
| R5 | **전력 일직선** | GPU 전력 (power_draw_w) std < 5W sustained AND 평균 ≥ TDP의 70% | 정상 작업은 변동 | velog ("최대 전력 일직선") |
| R6 | SM 활성도 vs **Tensor Core 활성도 비대칭** | SM ≥ 90% AND tensor_active < 5% sustained 10초+ | AI 학습은 둘 다 높음 | velog (핵심 시그니처) |
| R7 | **VRAM 작은 일정** | VRAM used < 1 GB AND GPU compute ≥ 90% sustained | ML 학습은 VRAM 풀사용 | Tanana 2024 |
| R8 | **메모리 사용 idle** | mem_used_gb < 4 AND GPU ≥ 90% sustained | 게임/AI 학습은 큰 메모리 | KT cloud ("300MB 이하 고정") |
| R9 | **CPU throttling evasion** | CPU 평균 30~70% 인데 코어 1개만 풀가동 sustained | 일부 단일 스레드 작업 | CryptoGuard 2025 |

**핵심 통찰**: 정상 ML 학습/게임은 변동성이 큼. Mining 은 평평한 부하 + 다른 자원 영역은 idle (메모리/디스크/Tensor) — KT cloud 와 velog 가 공통으로 강조하는 비대칭성.

---

## 2. 네트워크 패턴 (Network Pattern)

| # | 패턴 | 임계값 / 조건 | 정상 발생 가능성 | 출처 |
|---|---|---|---|---|
| N1 | **Stratum 패킷 시그니처** | outbound 작은 패킷 (200~600 B) 일정 간격 (30s±5s) | 거의 없음 (Stratum 특유) | Netflow-Plus, Sysdig Falco |
| N2 | **외부 IP 장기 지속** | 동일 외부 endpoint 와 ≥ 30분 연결 유지 | RDP / VPN / 화상회의 가능 | logpoint/guardsix |
| N3 | **Mining pool 포트** | port 3333, 4444, 7777, 7778, 3335, 3357, 5588, 5730, 6099, 8118, 8333, 8888, 8899, 9332 | 거의 없음 (대중 SW 미사용) | Sysdig Falco, KT cloud |
| N4 | **NAS / 내부망 트래픽 0** | 내부 IP outbound = 0 AND 외부 outbound > 0 sustained | dev 환경은 git/docker registry 사용 | velog |
| N5 | **Outbound 지속 (no burst)** | outbound mean 일정 (CV < 0.3) sustained 30분+ | 정상 streaming 도 가능 | KT cloud |
| N6 | **DNS resolution 새 외부 도메인 high entropy** | 1시간 내 새 외부 도메인 ≥ 20 (유저 idle 시) | 일반 사용 시 발생 | logpoint/guardsix |
| N7 | **User-Agent 의심 패턴** (HTTP proxy log) | UA 가 "XMRig*", "ccminer*", "miner" 포함 | 정상 SW 거의 미발생 | logpoint/guardsix |
| N8 | **CmdLine "stratum+tcp"** | 프로세스 cmdline 에 "stratum+tcp" 포함 | 정상 SW 미발생 | Sysdig Falco |
| N9 | **Mining pool 도메인** | DNS 또는 connection 의 호스트가 ethermine.org, nanopool.org, nicehash.com, minexmr.com, supportxmr.com 등 | 정상 미발생 | KT cloud, COIN_MINER_DOMAIN list |

**핵심 통찰**: Stratum 프로토콜의 **고정 패킷 길이 + 일정 주기** 가 가장 강력한 mining 시그니처 (Netflow-Plus 논문). Mining 의 외부 통신은 의도적으로 가벼움 — 적발 회피용.

---

## 3. 시스템 / 사용자 패턴 (System Pattern)

| # | 패턴 | 임계값 / 조건 | 정상 발생 가능성 | 출처 |
|---|---|---|---|---|
| S1 | **사용자 idle 중 자원 풀가동** | last_input ≥ 30분 AND CPU/GPU ≥ 90% sustained | 정상 일괄 작업 (overnight build) 가능 | INESC-ID NCA 2020, PMC11623100 |
| S2 | **잠금 화면 중 자원 풀가동** | screen_locked = true AND CPU/GPU ≥ 90% sustained | 정상 overnight 작업 (드물지만 있음) | PMC11623100 ("idle 상태에서도 high CPU 지속") |
| S3 | **자원 high + 디스크 I/O idle** | CPU/GPU ≥ 90% AND disk_io_mb_per_s < 1 sustained | 인메모리 작업 가능 (DB cache 등) | KT cloud ("디스크 read/write 거의 없음") |
| S4 | **자원 high + 메모리 idle** | CPU/GPU ≥ 90% AND mem_used_gb < 4 sustained | 거의 없음 — 큰 작업은 메모리 같이 사용 | KT cloud, velog |
| S5 | **Process recreation persistence** | 종료된 mining 프로세스가 60초 내 재생성 (같은 PPID 또는 cron) | 정상 워치독 도구 (systemd, monit) | KT cloud (사례: "강제 종료 후 자동 재설치") |
| S6 | **/tmp, /var/tmp, %APPDATA% 실행 + 외부 통신** | exec_path 가 임시 디렉터리 AND outbound > 0 | dev 도구 (npx, pip 임시 캐시) 가능 | KT cloud |
| S7 | **CPU load_avg vs running process count 부조화** | load_min5 ≥ logical_cpu_count AND processcount_running ≤ 3 | thrashing 상태 | PMC11623100 |

**핵심 통찰**: KT cloud + INESC-ID 가 공통으로 강조 — **"사용자 inactive 인데 자원만 풀가동"** 이 mining 의 거의 확정적 시그니처. RADA 현재 user idle 정보 미수집 — 도입 필요 (GetLastInputInfo).

---

## 4. 프로세스 패턴 (Process Pattern) — fast-path 유지

| # | 패턴 | 임계값 / 조건 | 출처 |
|---|---|---|---|
| P1 | **알려진 miner 프로세스명** | 프로세스명 ∈ {xmrig, nanominer, t-rex, lolminer, ccminer, ethminer, claymore, phoenixminer, gminer, nbminer, teamredminer} | KT cloud, Sysdig Falco |
| P2 | **cmdline 의 mining pool 주소** | cmdline 에 "stratum+tcp://" 포함 | Sysdig Falco |
| P3 | **임시 경로 실행 + miner like 동작** | exec_path 가 `/tmp`, `/var/tmp`, `%TEMP%`, `%APPDATA%\Local\Temp` AND R1-R8 중 하나 | KT cloud |
| P4 | **PID manipulation evasion** | 프로세스가 자기 PID 를 자주 변경 (PPID 동일, PID 새로 발생) | CryptoGuard 2025 |
| P5 | **Entry point poisoning** | LD_PRELOAD / DLL injection 흔적 + 미상 외부 통신 | CryptoGuard 2025 |

→ 이 카테고리는 본 RADA 의 **기존 fast-path** (`mining_known = 10` 점수) 와 동일. 유지.

---

## 5. 지속성 / 시간 패턴 (Persistence / Time Pattern) — 게이팅 조건

| # | 패턴 | 임계값 / 조건 | 출처 |
|---|---|---|---|
| T1 | **장시간 sustained** | 위 패턴들이 동시 발화 + ≥ 3시간 지속 | velog, KT cloud (각각 "수 시간", "장시간") |
| T2 | **자정~새벽 시간대** | UTC+9 기준 00:00~06:00 시간대 + 자원 high | 일반적 mining 운영 시간 (학생 PC 가 자리에 없을 때) |
| T3 | **재부팅 후 자동 시작** | 부팅 후 5분 내 자원 high + 외부 통신 | KT cloud (자동 재설치 사례) |
| T4 | **요일 패턴 (주말 야간)** | 주말 + 야간 시간대에 자원 high | (RADA 의 timeslot 변수 활용 가능) |

---

## 6. 카테고리 게이팅 결정 표 (제안)

```
INPUT:
  resource_abnormal = (R1 OR R2 OR R3 OR R4 OR R5 OR R6 OR R7 OR R8 OR R9)
  network_abnormal  = (N1 OR N2 OR N4 OR N5 OR N6)
                      [N3/N7/N8/N9 는 process fast-path 로 분리 — 즉시 HIGH_RISK]
  system_abnormal   = (S1 OR S2 OR S3 OR S4 OR S5 OR S6 OR S7)
  
  sustained_minutes = (위 boolean 들이 동시 만족된 연속 시간)

OUTPUT verdict:
  fast-path 우선:
    if 알려진 miner 프로세스/cmdline/pool 도메인 매치 (P1 OR P2 OR N9):
      return HIGH_RISK  ("mining_known")
  
  category gating:
    cats_count = sum([resource_abnormal, network_abnormal, system_abnormal])
    
    if cats_count >= 3 AND sustained_minutes >= 180:
      return HIGH_RISK  ("MINING_CONFIRMED_BY_BEHAVIOR")
    elif cats_count >= 2 AND sustained_minutes >= 30:
      return SUSPICIOUS
    elif cats_count >= 1:
      return OBSERVE  (로그만, 알람 없음)
    else:
      return NORMAL
```

---

## 7. 정상 워크로드 vs Mining 통계 비교 (참고)

INESC-ID NCA 2020 ("Cryptojacking Detection with CPU Usage Metrics") 가 비교한 5 워크로드:

| Workload | CPU 평균 | CPU std | 지속 시간 | 시그니처 |
|---|---|---|---|---|
| Interactive (사용자 입력) | 변동 큼 | 큼 | 짧음 | 사용자 active |
| Bulk Data Transfer | high | 중간 | 분 단위 | I/O bound |
| Web Browsing | low-mid | 큼 | 변동 | burst |
| Video Playback | mid | 작음 | 길게 | GPU 중심 |
| **Idle** | low | 0 | 길게 | 자원 low |
| **Cryptojacking (CPU)** | **high (95%+)** | **매우 작음** | **수 시간** | **자원 high + std 작음 + 다른 자원 idle** |

→ **Mining 의 통계적 차이**: CPU/GPU 평균이 높고 std 가 매우 작음. 정상 워크로드는 둘 중 하나만 만족.

---

## 8. RADA 적용 시 매핑 (다음 세션 작업용)

각 패턴을 RADA 의 client_core 수집 / ML server 평가 단계로 매핑:

### 8.1 추가 수집 필요 (client_core)

| 패턴 | 필요 데이터 | 현재 상태 |
|---|---|---|
| S1, S2 | 사용자 last_input_ms | ❌ 미수집 |
| R5 | gpu_power_w | ✓ derived_features 에 일부 있음 (gpu.power_draw_w) |
| R6 | tensor_core_active vs SM | ⚠ tensor_core_active 키는 있으나 항상 None (NVML 한계) |
| R9 | per-core CPU breakdown | ❌ 현재 평균만 수집 |
| N1 | per-packet 크기 + 주기 | ❌ 현재 총량만 수집 |
| T2, T4 | 시간대 / 요일 | ✓ timeslot 변수 존재 |

### 8.2 ML server 평가 (signal_extractor 확장)

| 카테고리 | 새 evaluator | 필요 입력 시계열 길이 |
|---|---|---|
| Resource Pattern | `evaluate_resource_pattern()` → boolean + 어떤 패턴 발화 | 30분 ~ 3시간 (pc_history_store 확장) |
| Network Pattern | `evaluate_network_pattern()` | 30분+ |
| System Pattern | `evaluate_system_pattern()` | 30분+ |
| Persistence | `evaluate_persistence()` — 카테고리 boolean 들의 동시 지속 시간 | 3시간 |

### 8.3 점수 정책 (scoring_policy.yaml v0.6 제안 골격)

```yaml
version: "scoring-v0.6.0"

# === 기존 유지 (flat 신호 입력으로 활용) =====
process: { known_miner: 10, persistent_miner: 3, temp_exec: 1, appdata_exec: 1 }
episode: { dos_spike: 5, persistent_ext: 2 }
resource_flat:
  cpu_high: 1
  cpu_flat: 1
  mem_high: 1
  mem_critical: 1
  gpu_high: 1
  top_cpu_norm_high: 2
  top_cpu_norm_mid: 1
network_flat:
  net_out_sustained: 2
  outbound_spike: 2
  unique_remote_ip_high: 2
  unique_remote_ip_mid: 1
  new_remote_ip_burst: 1
  spike_with_companion: 1

# === 약화 (FP 주범, 추후 0 으로 삭제 검토) ===
correlation_legacy:
  mining_known: 10              # 유지 (fast-path)
  cpu_plus_net: 2               # 유지 (이미 작음)
  mining_pool_only: 5           # 8 → 5
  disk_write_net_out: 2         # 5 → 2
  unknown_proc_net: 2           # 5 → 2
  appdata_net: 2                # 6 → 2

# === 신규: 카테고리 패턴 (boolean evaluator) ===
category_patterns:
  resource:
    R1_cpu_flat_sustained:        { threshold: { cpu_pct: 90, std: 5, window_min: 30 } }
    R2_gpu_flat_sustained:        { threshold: { gpu_pct: 90, std: 5, window_min: 30 } }
    R3_cpu_gpu_both_high:         { threshold: { cpu_pct: 90, gpu_pct: 90, window_min: 30 } }
    R4_gpu_only_asymmetric:       { threshold: { gpu_pct: 90, cpu_pct_max: 15, window_min: 30 } }
    R5_power_flatline:            { threshold: { power_std_w: 5, power_pct_of_tdp: 70, window_min: 30 } }
    R6_sm_no_tensor:              { threshold: { sm_pct: 90, tensor_pct_max: 5, window_sec: 10 } }
    R7_vram_low_compute_high:     { threshold: { vram_used_mb_max: 1024, gpu_pct: 90, window_min: 30 } }
    R8_mem_idle_compute_high:     { threshold: { mem_used_gb_max: 4, gpu_pct: 90, window_min: 30 } }
    R9_single_core_full:          { threshold: { single_core_pct: 95, total_cpu_max: 40, window_min: 30 } }
  network:
    N1_stratum_periodicity:       { threshold: { packet_size_max: 600, period_sec: 30, window_min: 10 } }
    N2_external_ip_persistent:    { threshold: { same_endpoint_minutes: 30 } }
    N4_internal_zero_external_high: { threshold: { internal_kb: 0, external_mb_min: 1, window_min: 30 } }
    N5_outbound_low_cv:           { threshold: { cv_max: 0.3, window_min: 30 } }
    N6_dns_burst_during_idle:     { threshold: { new_domain_count: 20, user_idle_min: 30, window_min: 60 } }
  system:
    S1_user_idle_high_load:       { threshold: { user_idle_min: 30, cpu_or_gpu_pct: 90, window_min: 30 } }
    S2_locked_high_load:          { threshold: { screen_locked: true, cpu_or_gpu_pct: 90, window_min: 30 } }
    S3_high_load_disk_idle:       { threshold: { cpu_or_gpu_pct: 90, disk_mb_per_s_max: 1, window_min: 30 } }
    S4_high_load_mem_idle:        { threshold: { cpu_or_gpu_pct: 90, mem_used_gb_max: 4, window_min: 30 } }
    S5_process_recreation:        { threshold: { recreation_count: 3, window_sec: 300 } }

gating:
  mining_confirmed:
    categories_required: 3
    sustained_minutes: 180
    verdict: HIGH_RISK
  suspicious:
    categories_required: 2
    sustained_minutes: 30
    verdict: SUSPICIOUS
  observe:
    categories_required: 1
    sustained_minutes: 5
    verdict: OBSERVE

context_discounts:
  startup: -1
  security_scan: -2
  maintenance_update: -2
  lab_agent: -1
  class_or_free: -1
```

---

## 9. 한계 + 결정 사항

### 본 catalog 에서 RADA 가 즉시 구현 가능한 것 (다음 세션)

- R1, R2, R3, R4, R5, R7, R8 (R6/R9 는 추가 수집 필요)
- N1, N2, N4, N5 (N6 는 DNS 수집 추가 필요)
- S1, S3, S4 (S2/S5 는 추가 데이터 필요)
- T1 (기본 sustained), T2 (시간대)
- 게이팅 로직

### 구현 보류 (추가 데이터 수집 또는 학교 환경 미지원)

| 패턴 | 보류 이유 |
|---|---|
| R6 (Tensor Core 활성도) | NVML 의 `gpu_tensor_core_active` 가 대다수 드라이버에서 None 반환 |
| R9 (per-core CPU) | client_core 가 평균만 수집 — 코어별 수집 추가 필요 |
| N1 (Stratum 패킷 시그니처) | per-packet 시계열 수집 부담 큼. 향후 검토 |
| N6 (DNS) | DNS 수집 자체 미구현. OS 권한 이슈 가능 |
| N7 (User-Agent) | HTTP proxy 가 학교 환경에 없을 수 있음 |
| P4 (PID manipulation) | OS 수준 모니터링 필요 |
| S2 (screen_locked) | Windows API SystemParametersInfo 추가 호출 가능, 다음 라운드 |

### 운영 정책 결정 사항 (다음 세션)

- 본 catalog 의 `category_patterns.*.threshold` 값들은 일단 보수적 (90%/15%/30min/3h) 으로 시작
- 본인 PC 4시간 데이터 + 학생 PC 들에서 며칠 수집 후 정밀 튜닝
- FP > 1% 면 임계값 강화, FP < 0.5% 면 임계값 완화 (놓치는 mining 확인 후)

---

## 10. 출처

### 학술 / 산업 reference

| 출처 | 주요 기여 |
|---|---|
| Tanana, D. (2024). *Behavior-Based Detection of GPU Cryptojacking*. arXiv:2408.14554 (IEEE 2024) | GPU load + VRAM 기반 decision tree (80% recall, 20% FP) |
| Khalaf, M. et al. (2025). *CryptoGuard: Lightweight Hybrid Detection and Response to Host-based Cryptojackers in Linux Cloud Environments*. ACM ASIACCS 2025 (arXiv:2510.18324) | syscall pattern + sliding window + eBPF remediation. F1 96.12%, 0.06% overhead |
| Gomes, F., Correia, M. (2020). *Cryptojacking Detection with CPU Usage Metrics*. NCA 2020 (INESC-ID) | 5 워크로드 vs mining 의 CPU 통계 차이 (Idle / Web / Video / Bulk / Interactive) |
| Hong, G. et al. (2024). *Real-Time Symbolic Reasoning Framework for Cryptojacking Detection Based on Netflow-Plus Analysis*. Springer LNCS | Stratum 고정 패킷 길이 → linear diophantine equations. "Stratum 탐지 = cryptojacking 탐지" |
| *Detecting and forecasting cryptojacking attack trends in IoT and WSN devices*. PMC11623100 (2024) | host-based feature 셋 (cpu_total, load_min1/5/15, mem_cached, memswap_free, processcount, fs_/_free), idle 중 high CPU 지속 |

### 산업 / 보안 블로그 reference

| 출처 | 주요 기여 |
|---|---|
| KT Cloud Tech (2025-09). *GPU 서버 보안위협 탐지* | 95%+ 다중 시간, mem < 300MB, disk I/O 최소. xmrig/nanominer/t-rex/lolminer. port 3333/4444/8080/9999/14444. ethermine/nanopool/nicehash 도메인. 자동 재설치 사례 |
| velog @jaeyunim. *GPU 부정 사용(Burn/채굴) 색출 방안* | SM 90%+ AND Tensor 5% 미만 10초+ 의 핵심 시그니처. 전력 일직선, NAS I/O 0, GPU 만 독식 |
| Sysdig Blog. *Detecting cryptojacking with Falco* | cmdline "stratum+tcp" rule, miner port 14개 list (3333/4444/8333/7777/7778/3357/3335/8899/8888/5730/5588/8118/6099/9332) |
| Logpoint / Guardsix. *Uncovering illegitimate Crypto-Mining Activity* | DNS to mining pool domains, User-Agent "XMRig*"/"ccminer*", COIN_MINER_IPS/DOMAIN/DNS sigma rules |

---

**다음 세션 작업**: 본 catalog 의 8.3 yaml 골격 기반으로 `signal_extractor.py` + `pc_history_store` (3h 윈도우) + 카테고리 evaluator 구현 → 본인 PC 4h 데이터 + mining 시뮬레이션 으로 측정.
