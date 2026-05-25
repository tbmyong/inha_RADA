# PC Provisioning — 운영 가이드

RADA 학생 PC (40대 규모) 첫 배포와 운영 중 발생하는 PC 추가 / 키 회전 /
폐기를 위한 toolkit 사용법. 모든 도구는 `tools/` 아래에 있으며 추가
의존성 없이 Python 표준 라이브러리만 사용한다 — psycopg 가 없으면 자동
으로 `docker compose exec postgres psql` 경로로 폴백한다.

## 인증 계약

- Spring 측 해시: `SHA-256(pepper + ":" + raw_key)` lowercase hex
  (`server-spring/.../security/ApiKeyHasher.java`).
- pepper 환경변수: `API_KEY_PEPPER` — Spring 컨테이너와 본 toolkit 이
  반드시 동일한 값을 봐야 인증이 통과한다.
- DB 컬럼: `pc_info(pc_id, hostname, api_key VARCHAR(64), is_active,
  registered_at)`. `api_key` 는 64자 hex 다이제스트만 저장한다 — raw
  키는 DB 에 절대 들어가지 않는다.

## Quick start — 학생 PC 40대 첫 배포

```bash
ssh ncp-server
cd /opt/rada
export API_KEY_PEPPER='<운영용 강력한 pepper>'        # Spring 과 동일

python tools/provision_pcs.py \
    --count 40 --prefix PC \
    --output /tmp/keys.csv --from-compose

scp /tmp/keys.csv 운영자-PC:~/                        # 안전 채널로
# 각 학생 PC 에 raw_key 한 줄씩 박아 배포 (client/.env 또는 config)

shred -u /tmp/keys.csv                                 # NCP 에서 즉시 삭제
```

출력 CSV 컬럼: `pc_id, raw_key, hashed_key, registered_at`. raw_key 만
클라이언트 측 설정에 박는다. hashed_key 는 검증용 사본일 뿐이다.

## CLI 모드

### A. 자동 생성 (배포용 — 가장 흔함)

```bash
python tools/provision_pcs.py --count 40 --prefix PC \
    --output provisioned_keys.csv --from-compose
```

- pc_id: `PC-01, PC-02, ..., PC-40` (zero-padded; `--count` 자릿수에 맞게)
- raw_key: `secrets.token_urlsafe(24)` — 32자 URL-safe base64
- hostname: pc_id 와 동일하게 채워짐

### B. CSV 입력 (학번 / MAC 매핑이 있을 때)

```bash
python tools/provision_pcs.py --input pcs.csv \
    --output provisioned_keys.csv --from-compose
```

`pcs.csv` 형식:

```csv
pc_id,hostname
LAB-201A-01,lab201a-pc01.example.ac.kr
LAB-201A-02,lab201a-pc02.example.ac.kr
```

raw_key 는 입력 받지 않는다 — 도구가 발급한다.

### C. dry-run (DB 무수정 검증)

```bash
python tools/provision_pcs.py --count 5 --prefix TEST \
    --output /tmp/test_keys.csv --dry-run
```

DB 에 손대지 않고 CSV 만 만든다. 자릿수, 접두사, pepper 가 의도대로
적용됐는지 사전 점검에 사용한다.

### 공통 옵션

| 옵션 | 설명 |
| --- | --- |
| `--pepper <val>` | `API_KEY_PEPPER` env 무시하고 명시 지정 |
| `--db-url postgresql://...` | 컨테이너 외부 DB 에 직접 접속 |
| `--from-compose` | `docker compose exec postgres psql` 경로 사용 (psycopg 미설치 호스트의 기본) |
| `--yes` | 기존 pc_id 갱신 시 확인 prompt 생략 |
| `--dry-run` | DB 변경 없이 CSV 만 출력 |

기존 pc_id 가 발견되면 `ON CONFLICT (pc_id) DO UPDATE` 로 `api_key`,
`hostname`, `is_active=true`, `registered_at` 을 갱신한다. 사실상
"키 회전 + 재활성화" 효과.

## 키 회전 (compromise 의심)

```bash
python tools/rotate_pc_key.py PC-07 --output PC-07.key --from-compose
```

- 해당 PC 의 `api_key` 해시를 새 raw 의 다이제스트로 즉시 교체
- 이전 raw_key 는 그 즉시 무효 (다음 metric POST 부터 401)
- 새 raw_key 1줄짜리 파일을 `--output` 경로에 작성, OS 권한 0600 적용

전체 일괄 회전은 dev 단계에서는 미구현이다. 필요 시 `--count` 모드로
같은 pc_id 들을 다시 provision 하면 ON CONFLICT 경로로 일괄 회전된다.

## PC 폐기 / 비활성화

```bash
# 단일
python tools/revoke_pc.py PC-07 --from-compose

# metric 30일 이상 끊긴 PC 일괄
python tools/revoke_pc.py --all-inactive-since 30d --from-compose

# 사전 점검 (DB 무수정)
python tools/revoke_pc.py PC-07 --dry-run --from-compose
```

행을 삭제하지 않고 `is_active=false` 만 토글한다 — 과거 metric 과
score 데이터는 그대로 보존된다.

## 학기 중 신규 PC 합류

CSV 1줄 모드로 추가만 한다 — 기존 PC 들은 ON CONFLICT 조건을 타지
않으므로 안전하다.

```bash
echo "pc_id,hostname
PC-41,lab201b-pc41.example.ac.kr" > /tmp/new.csv

python tools/provision_pcs.py --input /tmp/new.csv \
    --output /tmp/new_keys.csv --from-compose
```

## pepper 변경 시

- 모든 PC 의 api_key 다이제스트가 새 pepper 기준으로 재계산되어야 함.
  raw_key 자체를 다시 발급하지 않는 한 단순히 pepper 만 바꾸면 전체 PC
  가 즉시 401 이 된다.
- 따라서 pepper 변경은 사실상 **전체 re-provisioning 과 동치**:
  1. 새 pepper 를 정해 Spring 컨테이너 env 에 반영
  2. `provision_pcs.py --count 40 ... --yes` 로 같은 pc_id 들을 다시
     발급 (ON CONFLICT 경로)
  3. 새 CSV 의 raw_key 들을 각 PC 에 재배포
- pepper 는 영구적으로 두는 것을 강력히 권장.

## 배포 점검 체크리스트

- [ ] `API_KEY_PEPPER` 가 dev 와 다른 강력한 랜덤 (32바이트 이상)
- [ ] Spring 컨테이너 env 와 toolkit 실행 환경의 pepper 가 동일
- [ ] 출력 CSV 가 운영 호스트에서 즉시 안전하게 배포되고 `shred`/삭제
- [ ] `SELECT count(*) FROM pc_info WHERE is_active` 가 운영 PC 수와 일치
- [ ] 각 PC client 설정의 raw_key 1자 단위까지 정확히 입력됨
- [ ] `tools/provisioned_keys*.csv` 가 `.gitignore` 에 포함되어 있음

## 트러블슈팅

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `psql failed (rc=...)` | docker 미설치 또는 컨테이너 미가동 | `docker compose ps` 확인, `--db-url` 로 직접 접속 |
| `401 Unauthorized` | pepper 불일치 | Spring `API_KEY_PEPPER` vs `provision_pcs.py` 실행 env 비교 |
| 새 PC만 인증 됨 / 기존은 401 | pepper 바뀜 | "pepper 변경 시" 절차 적용 |
| `internal hash collision` | `secrets.token_urlsafe` 충돌 (사실상 0) | 재실행하면 정상화 |
