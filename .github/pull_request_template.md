<!-- PR 제목은 Conventional Commits 권장: feat(scope): ..., fix(scope): ..., docs(scope): ... -->

## 변경 요약
<!-- 1~2줄로 "왜" + "무엇" -->

## 동기 / 배경
<!-- 어떤 문제를 풀기 위한 변경인가, 관련 Issue 번호 (#123) -->

## 변경 분류
- [ ] feat — 신규 기능
- [ ] fix — 버그 수정
- [ ] docs — 문서만
- [ ] refactor — 동작 변경 없는 구조 개선
- [ ] chore — 빌드/CI/도구
- [ ] test — 테스트만 추가/수정

## Contract 영향 (체크하면 All-team sync 필요)
**아래 8개 중 하나라도 체크되면 머지 전에 팀 전원 합의 필요. 모듈 담당자뿐 아니라 클라이언트/Grafana/Spring/ML 모두 확인.**

- [ ] Flyway `V*.sql` 기존 파일 수정 (V9+ 신규는 OK)
- [ ] MetricsRequest 22키 변경 (필드 추가/제거/이름 변경/타입)
- [ ] `MlResponse` / `analyze_router` 응답 형식 변경
- [ ] API 경로 (`/api/metrics`, `/analyze`, `/actuator/*`)
- [ ] `ApiKeyHasher` / 인증 알고리즘 / pepper 처리
- [ ] `anomaly_history.scores` JSONB nested key 이름
- [ ] 환경변수 / Docker compose service 이름
- [ ] Grafana datasource UID (`rada_pg`, `rada_spring`)

## 테스트 수행
- [ ] `pytest` 통과 (목표: 282+)
- [ ] `cd server-spring && ./gradlew test --tests "*Test"` 통과 (목표: 77+)
- [ ] (해당 시) Testcontainers IT 6건 로컬 통과
- [ ] (해당 시) `docker compose up -d --build` + smoke 라이브 검증

```
<!-- 테스트 출력 요약 -->
```

## 스크린샷 / 로그
<!-- Grafana 패널 변경 시 캡처 권장. ML 응답 변경 시 before/after JSON. -->

## 체크리스트
- [ ] 신규 코드에 테스트 추가 (또는 사유 명시)
- [ ] `.env` / 시크릿 / `claude_desktop_config.json` commit 없음
- [ ] CI (`python-tests`, `java-tests`) 통과 확인
