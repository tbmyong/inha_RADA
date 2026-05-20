---
name: Improvement
about: 기능 개선 / 리팩터링 / 성능 / 문서화 제안
title: "[IMPROVE] "
labels: enhancement
assignees: ''
---

## 현재 상태
<!-- 어디가 어떻게 동작 중인가 (파일/경로 명시) -->

## 제안 사항
<!-- 어떻게 바꾸자는 것인가 -->

## 기대 효과
<!-- 성능 / 가독성 / 유지보수 / DX 등 — 측정 가능하면 수치 포함 -->

## 영향 받는 contract (건드리면 팀 합의 필요)
- [ ] DB 스키마 — 기존 Flyway `V*.sql` 파일 수정 (V9+ 신규 추가는 OK)
- [ ] 22-key MetricsRequest payload
- [ ] ML 응답 (`MlResponse` / `analyze_router` 응답 JSON 구조)
- [ ] API 경로 (`/api/metrics`, `/analyze`, `/actuator/*`)
- [ ] 인증 (`ApiKeyHasher`, pepper, API key 알고리즘)
- [ ] `anomaly_history.scores` JSONB nested key 이름
- [ ] 환경변수 이름 / Docker compose service 이름
- [ ] Grafana datasource UID (`rada_pg`, `rada_spring`)

> 위 항목 중 하나라도 체크되면 PR 단계에서 **All-team sync 필요**.

## 작업 추정
- 예상 소요:
- 검증 방법:
- 회귀 위험:

## 참고
<!-- 관련 이슈/PR, 외부 문서 링크 -->
