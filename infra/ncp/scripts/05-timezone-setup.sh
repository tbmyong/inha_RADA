#!/usr/bin/env bash
# 05-timezone-setup.sh
# 시스템 타임존을 UTC 로 고정한다 (저장은 UTC, 표시 변환은 Grafana / Spring 단에서 Asia/Seoul).

set -euo pipefail

sudo timedatectl set-timezone UTC
timedatectl status

echo "DB / 애플리케이션 로그는 UTC 로 기록된다."
echo "Grafana 는 grafana.ini 의 default_timezone=Asia/Seoul 로 사용자에게 KST 로 표시한다."
