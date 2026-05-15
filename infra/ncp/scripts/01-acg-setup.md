# 01. NCP ACG (Access Control Group) 설정

NCP 콘솔 > Server > ACG 에서 다음 규칙을 적용한다.
RADA 서버는 단일 인스턴스(4GB RAM 가정), 외부에 노출하는 포트는 최소화한다.

## Inbound (외부 → 서버)

| Protocol | Source        | Port  | 설명                                     |
|----------|---------------|-------|------------------------------------------|
| TCP      | <관리자 IP/32> | 22    | SSH (특정 IP만, 0.0.0.0/0 사용 금지)       |
| TCP      | 0.0.0.0/0     | 8080  | Spring Boot API (Nginx 미사용 시 직노출)  |
| TCP      | 0.0.0.0/0     | 3000  | Grafana UI                               |

## 내부 전용 (외부 차단 — ACG 에 등록하지 않음)

| Protocol | Port  | 설명                                                          |
|----------|-------|---------------------------------------------------------------|
| TCP      | 8000  | FastAPI (uvicorn 127.0.0.1 바인딩, ACG 에도 등록하지 않음)    |
| TCP      | 5432  | PostgreSQL (listen_addresses='localhost', ACG 비등록)        |

## Outbound

- 기본 정책 All Allow (apt, JDK 다운로드 등에 필요).
- 운영 단계에서 필요 시 443/80/53 만 허용으로 좁힐 것.

## 검증 (외부 머신에서)

```
nc -zv <외부IP> 22     # OK
nc -zv <외부IP> 8080   # OK
nc -zv <외부IP> 3000   # OK
nc -zv <외부IP> 8000   # 반드시 차단(timeout / refused)
nc -zv <외부IP> 5432   # 반드시 차단(timeout / refused)
```

8000/5432 가 외부에서 열리면 즉시 ACG / 바인딩 / 방화벽을 점검한다.
