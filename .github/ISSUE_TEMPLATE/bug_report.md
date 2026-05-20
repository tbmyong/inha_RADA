---
name: Bug report
about: 동작 이상 / 회귀 / 예상치 못한 에러 신고
title: "[BUG] "
labels: bug
assignees: ''
---

## 재현 단계
1.
2.
3.

## 기대 동작
<!-- 무엇이 일어나야 했는가 -->

## 실제 동작
<!-- 무엇이 일어났는가 (에러 메시지, 잘못된 값 등) -->

## 환경
- OS:
- Docker 버전 (`docker --version`):
- 컴포넌트 SHA / 브랜치:
- 실행 방법: [ ] docker compose / [ ] systemd (NCP) / [ ] 로컬 개별 실행

## 영향 범위
- [ ] client (`client.py`, `client_core/`)
- [ ] spring (`server-spring/`)
- [ ] ml (`ml_server/`)
- [ ] grafana (`infra/grafana/`)
- [ ] db (Flyway, 시드, 스키마)
- [ ] ops (compose, NCP, env)

## 로그 발췌
```
<!-- docker compose logs <service> 또는 ./gradlew test 출력 일부 -->
```

## 추가 컨텍스트
<!-- 스크린샷, 관련 PR/Issue 링크 -->
