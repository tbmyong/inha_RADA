# client_core — RADA 클라이언트 에이전트

PC 자원(CPU/메모리/GPU/네트워크/디스크/프로세스)을 5초 주기로 수집하고
로컬 1차 탐지 후 ML 서버 또는 Spring Boot 메인 서버로 전송하는 모니터링
에이전트.

## 진입점

- **실제 진입점:** `client_core.runtime.ClientRuntime`
  - `ClientRuntime().run_forever()` 가 메인 루프
  - `ClientRuntime().step()` 은 1회 수집/탐지/전송 사이클
- **`client.py`** (저장소 루트) 는 v9 모듈화 이전 호환을 위한 **얇은 shim**.
  - 레거시 함수/상수(`collect_metrics`, `THRESHOLDS`, …)를 그대로 재노출만 하며,
    새 코드는 `ClientRuntime` 을 직접 사용 권장.
  - 학생 PC 배포 시에는 본 파일을 PyInstaller 로 단일 exe 로 빌드한다
    (절차: [`docs/guides/client_deployment.md`](../docs/guides/client_deployment.md)).

```python
from client_core.runtime import ClientRuntime

ClientRuntime().run_forever()
```

## 의존성 설치

```powershell
pip install -r client_core/requirements.txt
```

- `pynvml` / `GPUtil` 미설치 또는 NVIDIA 드라이버 없는 환경이면 GPU 메트릭은
  자동으로 `null` 처리되어 다른 수집 항목에는 영향이 없다.

## 설정 파일

기본 위치: `client_core/config/sample_config.yaml` (샘플).

`ClientRuntime` 은 `load_config(autodiscover=True)` 로 다음 순서로 자동 탐색한다.

1. 명시 경로 (`load_config(path=...)`)
2. `RADA_CONFIG` 환경변수
3. `./config.yaml` (CWD)
4. `%APPDATA%/rada/config.yaml` (Windows)
5. 미발견 시 `client_core/config/defaults.py` 기본값

환경변수 override (항상 최종 적용):

| 환경변수                | 효과                              |
|------------------------|----------------------------------|
| `RADA_MODE`            | `mlserver` 또는 `springboot`     |
| `RADA_ML_SERVER_URL`   | ML 서버 URL 덮어쓰기              |
| `RADA_SPRING_BOOT_URL` | Spring Boot URL 덮어쓰기          |
| `RADA_API_KEY`         | Spring Boot API Key 덮어쓰기      |

## 실행 모드

### mode=mlserver (FastAPI 직접 호출)

```powershell
$env:RADA_MODE = "mlserver"
$env:RADA_ML_SERVER_URL = "http://localhost:8000/analyze"
python client.py
```

응답: `200 OK` + JSON body.

### mode=springboot (Spring Boot 경유)

```powershell
$env:RADA_MODE = "springboot"
$env:RADA_SPRING_BOOT_URL = "http://localhost:8080/api/metrics"
$env:RADA_API_KEY = "your-api-key"
python client.py
```

응답: `202 Accepted` (빈 body 허용). `X-API-Key` 헤더 자동 첨부.

## 전송 실패 복구 (자동 drain)

전송 실패 시 페이로드는 `LocalQueue` 에 적재되며, 다음 사이클부터
`ClientRuntime.step()` 이 사이클당 최대 5건 (`RETRY_PER_CYCLE`) 까지
자동 재전송한다. 단일 실패가 발생하면 즉시 break 하여 정상 전송 흐름을
방해하지 않는다.

`LocalQueue` 에 `queue_path` 를 지정하면 JSONL 디스크 영속이 활성화되어
프로세스 재시작 후에도 미전송 페이로드가 복구된다.

## Windows 권장 사항

- `psutil.net_connections()` 는 외부 연결 카운트에 사용되며, **관리자 권한
  PowerShell** 에서 실행해야 모든 프로세스의 소켓을 열람할 수 있다. 일반
  권한이면 자기 프로세스 소켓만 보이며 외부 연결 통계가 0 으로 떨어질 수 있다.
- PyInstaller `--noconsole` 빌드 + 학생 PC Task Scheduler 운영 시,
  `client_core/__init__.py` 가 자식 프로세스 (GPUtil 의 nvidia-smi 등) 에
  `CREATE_NO_WINDOW` 를 자동 주입한다 — 5초마다 cmd 창 깜빡임 방지.

## PyInstaller 빌드 / 학생 PC 배포

학생 PC 40대에 백그라운드로 깔려면 PyInstaller 단일 exe + Task Scheduler 사용:

```powershell
pyinstaller --onefile --noconsole `
  --name rada_client `
  --hidden-import pynvml `
  --hidden-import GPUtil `
  --collect-all client_core `
  client.py
```

결과: `dist\rada_client.exe`. 자세한 패키징 + install.bat + 마에스트로 baseline
저장 절차는 [`docs/guides/client_deployment.md`](../docs/guides/client_deployment.md) 와
[`docs/guides/deployment_checklist.md`](../docs/guides/deployment_checklist.md) 참조.

## 절대 불변 규약 (변경 금지)

- DB 스키마, ML 페이로드의 22개 키, `ml_server` / `server-spring` 코드, 그리고
  `MetricsSender.send()` 시그니처는 회귀 0 원칙으로 변경하지 않는다.
