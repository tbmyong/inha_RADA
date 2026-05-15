# RADA demo seed (DEV ONLY)

Populates 40 PCs (`PC-01` .. `PC-40`) with 1h of metrics, 6 anomalies, 25 AI
judgments so the Grafana main dashboard renders the mockup layout without
running real agents.

**Do not run in production.** The script touches only rows whose `pc_id`
starts with `PC-` and the NCP deployment never invokes it.

Run from repo root:

```powershell
# Windows
./infra/seed/seed_demo.ps1
```

```bash
# Linux / macOS / WSL
./infra/seed/seed_demo.sh
```
