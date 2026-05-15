# inha_RADA

RADA is a PC resource monitoring and anomaly detection project for lab PCs.
It collects local machine metrics, stores them through a Spring Boot server,
analyzes anomalies through a FastAPI ML server, and visualizes operational
status with Grafana.

## Components

- `agent.py`, `client_core/`: PC-side metric collection, local detection, and metric sending
- `ml_server/`: FastAPI anomaly analysis server with scoring and model management
- `server-spring/`: Spring Boot API server for ingestion, authentication, persistence, and query APIs
- `infra/`: NCP, PostgreSQL, Grafana, systemd, and deployment support files
- `tests/`: Python unit and integration tests

## Runtime Outline

1. The agent collects CPU, memory, GPU, disk, network, and process metrics.
2. The Spring Boot server authenticates incoming metrics and stores them in PostgreSQL.
3. The ML server analyzes abnormal patterns and returns verdicts.
4. Grafana reads PostgreSQL data for dashboards and alerting.

## Configuration

Sensitive values are provided through environment variables.

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA`
- `DB_USER`, `DB_PASSWORD`
- `API_KEY_PEPPER`
- `ML_SERVER_URL`

See component-level README files and sample config files for local setup details.
