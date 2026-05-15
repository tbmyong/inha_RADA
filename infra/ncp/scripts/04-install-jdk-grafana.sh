#!/usr/bin/env bash
# 04-install-jdk-grafana.sh
# JDK 17 + Grafana OSS 설치

set -euo pipefail

echo "[1/4] JDK 17 설치"
sudo apt-get update -y
sudo apt-get install -y openjdk-17-jdk-headless
java -version

echo "[2/4] Grafana OSS APT 저장소 등록"
sudo apt-get install -y apt-transport-https software-properties-common wget gnupg
sudo mkdir -p /etc/apt/keyrings
wget -qO- https://apt.grafana.com/gpg.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
  | sudo tee /etc/apt/sources.list.d/grafana.list

echo "[3/4] Grafana 설치"
sudo apt-get update -y
sudo apt-get install -y grafana

echo "[4/4] provisioning / grafana.ini 배치"
# 본 리포의 infra/grafana/* 를 서버로 rsync/scp 한 뒤 다음 경로로 심볼릭 링크/복사한다.
#   /etc/grafana/grafana.ini
#   /etc/grafana/provisioning/datasources/postgres.yaml
#   /etc/grafana/provisioning/dashboards/dashboards.yaml
#   /etc/grafana/provisioning/dashboards/rada-main.json
#   /etc/grafana/provisioning/alerting/severity-high.yaml
sudo install -d -m 0755 -o grafana -g grafana \
  /etc/grafana/provisioning/datasources \
  /etc/grafana/provisioning/dashboards \
  /etc/grafana/provisioning/alerting

# 환경변수(GRAFANA_READER_PASSWORD)는 systemd override 에서 주입한다 (grafana-server.override.conf 참고)
sudo systemctl daemon-reload
sudo systemctl enable --now grafana-server
sudo systemctl status --no-pager grafana-server || true

echo "DONE. http://<외부IP>:3000 (admin / 초기 비밀번호는 grafana.ini 에 정의)"
