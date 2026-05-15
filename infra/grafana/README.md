# RADA Grafana 대시보드

본 디렉터리는 RADA 운영 대시보드 (메인 + PC 상세) 를 Grafana provisioning 으로 배포한다.

## 구성

```
infra/grafana/
├── grafana.ini
└── provisioning/
    ├── alerting/severity-high.yaml
    ├── datasources/postgres.yaml       # uid: rada_pg
    └── dashboards/
        ├── dashboards.yaml             # provider (folder: RADA)
        ├── rada-main.json              # 메인 대시보드 (40 PC + 게이지 + 도넛 + 시계열 + Top5)
        └── rada-pc-detail.json         # 드릴다운 상세 대시보드 (PC 단위 6 패널)
```

## 메인 대시보드 (`rada-main`)

- 시간범위: `now-1h ~ now`, refresh: `5s`
- 변수
  - `$pc_id` (query: `SELECT pc_id FROM pc_info WHERE is_active = true`)
  - `$severity` (custom: NORMAL/LOW/MEDIUM/HIGH — V5 정합)
- 패널 (24-col 그리드)
  - 좌측: 40대 PC 단일 Stat 패널 (multi-value, 셀당 1 PC, severity 매핑된 색/라벨). 셀 클릭 시 Data link 로 `rada-pc-detail` 이동.
  - 우측 상단: 전체 정상 비율 Gauge (≥90 green / ≥70 yellow / <70 red), 채굴 의심 Stat(red), 점검 대상 Stat(yellow) — 모두 최근 10분 윈도우.
  - 우측 중단: AI 판단 분포 Donut (`verdict ILIKE` 분류 — Normal/Mining/Heavy Load/HW Error).
  - 좌측 하단: 이상 점수 추이 시계열 (PC별 시리즈, Y축 max=50, `anomaly_history.scores` 의 `score_breakdown.final` → `final` → `total` COALESCE 호환 우선순위).
  - 우측 하단: CPU / GPU / VRAM Top 5 BarGauge (최근 5분 평균).

### 옵션 A (Stat + gridPos honeycomb) 채택 사유

- `grafana-polystat-panel` 같은 honeycomb 전용 플러그인은 **실제 설치하지 않음** (의존 추가 회피).
- 기본 빌트인 Stat 패널 한 개에 multi-value 모드로 40개 PC 를 모두 렌더한다. orientation=auto + 패널 크기 12×16 에서 자동으로 격자형으로 펼쳐진다.
- 단일 패널 = 단일 쿼리 = 단일 Data link 정의로 유지보수가 가장 단순하다.

## 상세 대시보드 (`rada-pc-detail`)

- uid: `rada-pc-detail`, 변수: `$pc_id` (query: `SELECT pc_id FROM pc_info ORDER BY pc_id`)
- 패널 6개
  1. 자원 시계열 (cpu_percent / mem_percent / gpu_percent)
  2. VRAM / Disk I/O 시계열 (vram_mb / disk_read_mb / disk_write_mb)
  3. 네트워크 시계열 (inbound_mb / outbound_mb)
  4. 이상 탐지 이력 테이블 (`anomaly_history WHERE pc_id=$pc_id`)
  5. AI 판단 내역 테이블 (`ai_judgment_history aj JOIN anomaly_history ah`)
  6. Top 프로세스 (`metrics_history.extra->'top_processes'` 가 있을 때만; 부재 시 빈 표)

### Drill-down 링크 구조

메인 Stat 패널 → 상세:
```
/d/rada-pc-detail/rada-pc-detail?var-pc_id=${__data.fields.pc_id}
```
`targetBlank=false` (같은 탭 이동).

## 플러그인 안내

- 본 시안은 빌트인 패널 (`stat`, `gauge`, `piechart`, `timeseries`, `bargauge`, `table`) 만 사용한다.
- honeycomb 시각화를 더 정교하게 다듬고 싶다면 (선택) 다음을 설치:
  ```sh
  # 컨테이너 환경 예시 — 실제 적용 시 운영 담당이 검토 후 활성화
  # grafana-cli plugins install grafana-polystat-panel
  ```
  현재는 설치하지 않는다.

## refresh 부하 주의

- 기본 `5s` refresh 는 40 PC × 9 패널 × 분당 12회 쿼리 ≈ 4,300 query/min 수준.
- Postgres 부하가 보이면 대시보드 우상단에서 `10s` 또는 `30s` 로 완화 가능.

## 수동 검증 (dummy INSERT)

스키마 변경 없이 더미 데이터를 넣어 시각 확인:

```sql
-- 1) PC 등록 (없을 때만)
INSERT INTO pc_info(pc_id, hostname, is_active)
  VALUES ('PC-001', 'lab-001', true)
  ON CONFLICT (pc_id) DO NOTHING;

-- 2) 최근 metrics
INSERT INTO metrics_history
  (pc_id, collected_at, cpu_percent, mem_percent, gpu_percent,
   vram_mb, disk_read_mb, disk_write_mb, inbound_mb, outbound_mb, extra)
VALUES
  ('PC-001', NOW(), 88.0, 65.0, 92.0, 7200, 120, 80, 5, 3,
   '{"top_processes":[{"name":"xmrig.exe","cpu_percent":85.0,"mem_percent":12.3}]}'::jsonb);

-- 3) anomaly + AI 판단
WITH ins AS (
  INSERT INTO anomaly_history(pc_id, detected_at, severity, anomaly_type, scores)
    VALUES ('PC-001', NOW(), 'HIGH', 'gpu_burst',
            '{"total": 42.0, "cpu": 8, "gpu": 30, "net": 4}'::jsonb)
    RETURNING id
)
INSERT INTO ai_judgment_history(anomaly_id, judged_at, verdict, confidence, reason)
SELECT id, NOW(), 'mining_suspected', 0.87, 'sustained GPU + xmrig signature' FROM ins;
```

확인 포인트
- 메인: `PC-001` 셀이 빨간색 (HIGH), 정상 비율 게이지 감소, 채굴 의심 Stat=1, 도넛 Mining 슬라이스, CPU/GPU/VRAM Top5 에 `PC-001` 노출.
- 상세 (`?var-pc_id=PC-001`): 세 시계열 패널에 신규 포인트, 이상 탐지/AI 판단 테이블 1행씩 추가, Top 프로세스 테이블에 `xmrig.exe`.
