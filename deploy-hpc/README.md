# deploy-hpc — Mode B (AI Gateway + Ollama di HPC)

Semua perintah dijalankan di **HPC**, di folder `deploy-hpc/` hasil clone repo
ini (mis. `D:\Gust\ai-service\deploy-hpc`).

## Ringkasan alur (Mode B)

```
Browser (SSO) → BFF Express :3000 [server platform]
                    │  AI_SERVICE_URL = http://<IP-HPC>:8100
                    ▼
     AI Gateway (container Docker di HPC) :8100
                    │  LLM_BASE_URL = host.docker.internal:11434/v1
                    ▼
     Ollama :11434 [HPC] — TIDAK ter-expose ke LAN
```

## Checklist menjalankan

```powershell
# 1. Docker Desktop hidup (Fase 0 plan-run-docker.md)
docker --version

# 2. Konfigurasi runtime
Copy-Item .env.example .env
notepad .env            # isi SERVICE_KEY (sama dengan platform!)

# 3. Build & start
docker compose -f docker-compose.hpc.yml up -d --build

# 4. Verifikasi
docker compose -f docker-compose.hpc.yml ps        # ai healthy
curl.exe -s --noproxy '*' http://127.0.0.1:8100/health     # {"status":"healthy",...}
curl.exe -s --noproxy '*' http://<IP-HPC>:8100/health      # dari mesin lain

# 5. Firewall (PowerShell Admin) dibatasi subnet/IP platform
netsh advfirewall firewall set rule name="RCC AI Gateway (:8100)" new remoteip=<subnet-atau-IP-platform>
```

## Rujukan

| Dokumen | Isi |
|---|---|
| `../plan-run-docker.md` | Rencana Mode B lengkap (Fase 0–5, risiko, rollback) |
| `../RUNBOOK-ai-service.md` | Operasional harian HPC |
| `../README-INTEGRASI.md` | Sisi platform (env `AI_SERVICE_URL`, `SERVICE_KEY`) |
