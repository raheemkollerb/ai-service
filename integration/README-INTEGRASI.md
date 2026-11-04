# README-INTEGRASI — Menggabungkan Paket AI ke Monorepo Platform

Paket ini adalah **snippet siap tempel** untuk monorepo platform RCC
(`apps/backend`, `apps/frontend`, `docker-compose.yml`, root `.env`).
Referensi kebutuhan lengkap: `ai-service.md` § 4.C–§ 6.E.

## 1. Salinisasi app AI Gateway

```
apps/ai/                            ← salin seluruh isi paket (app/, Dockerfile, requirements.txt, .env.example, .gitignore)
```

File `apps/ai/**` sudah lulus V1 (`python -m compileall`) dan T1–T8 (mock LLM).
Tidak perlu perubahan saat ditempel — hanya `.env` runtime.

## 2. Backend (BFF Express) — `apps/backend`

| Sumber paket | Tujuan monorepo |
|---|---|
| `backend/ai.service.ts` | `src/services/ai.service.ts` (baru) |
| `backend/ai.routes.ts` | `src/routes/ai.routes.ts` (baru) |
| `backend/config-snippet.ts` | gabungkan ke `src/config/index.ts` — tambah `aiConfig` |
| `backend/middleware-snippet.ts` | tambah `chatLimiter` di `src/middleware/rateLimit.middleware.ts` |
| `backend/app-snippet.ts` | `src/app.ts` — letakkan `app.use('/api/ai', aiRoutes)` **di bawah** `app.use('/api', preserveSessionCookie, requireSsoSession)` |

Wajib (§ 4):

- `aiConfig.baseURL` dari env `AI_SERVICE_URL`; `serviceKey` dari `SERVICE_KEY`;
  timeout 120000; max 20 pesan; max 8000 char.
- Streaming: `x-no-compression` (header req) **sebelum** `axios.post(... responseType: 'stream')`,
  header SSE lengkap + `res.flushHeaders()`, lalu **passthrough** `upstream.data.pipe(res)` —
  JANGAN menulis ulang payload.
- `/api/ai/chat` tanpa cookie SSO → tetap 401 `Login required` (middleware global).
- Rate limit chat: 30 permintaan/menit, terpisah dari `apiLimiter`.

Verifikasi: `pnpm --filter backend exec tsc --noEmit` (0 error) + `pnpm --filter backend build`.

## 3. Frontend — `apps/frontend`

| Sumber paket | Tujuan monorepo |
|---|---|
| `frontend/aiService.ts` | `src/services/aiService.ts` (baru) |
| `frontend/useChat.ts` | `src/hooks/useChat.ts` (ganti isi) |
| — | `src/components/features/ai-chat/AIChat.tsx`: indikator `status` (Online/Offline/unknown) + footer **"Asisten AI Internal — LLM Lokal"** |
| — | **HAPUS** `src/services/geminiService.ts`, `VITE_GEMINI_API_KEY` di `src/vite-env.d.ts`, dependency `@google/genai` di `package.json` |

Setelah hapus dependency: `pnpm install --lockfile-only` di root — WAJIB agar
`pnpm-lock.yaml` regen (Dockerfile pakai `pnpm install --frozen-lockfile`).

Perilaku wajib useChat (§ 5): welcome tunggal `role:'model'` skip saat kirim;
draft assistant kosong di ujung list di-update progresif setiap `delta`;
tanpa delta apa pun → pesan offline; status pemetaan hijau/merah/abu.
Chat types tetap `role: 'user' | 'model'`.

Verifikasi: `pnpm --filter frontend build` sukses; `grep -r gemini apps/frontend/src` → 0 hasil.

## 4. compose + env (root monorepo)

1. `integration/docker-compose-ai.yml` → blok `ai:` ditempel di `docker-compose.yml`
   (setelah `analytics`, sebelum `backend`). Jaringan `app-network` sudah ada di monorepo.
   Tanpa `depends_on` ke Ollama (runtime di luar compose).
2. Root `.env` + `.env.example` tambah kunci:

```
SERVICE_KEY=<nilai-sama-semua-service>
LLM_BASE_URL=http://<IP-Z8G4>:11434/v1
LLM_MODEL=qwen3:30b-a3b
AI_SERVICE_URL=http://ai:8100
```

Nilai `.env` **JANGAN di-commit**. `git status` harus bersih dari `.env`.

## 5. Rangkaian verifikasi setelah penggabungan

```
V2  pnpm --filter backend exec tsc --noEmit      → 0 error
V3  pnpm --filter backend build                  → dist/
V4  pnpm --filter frontend build; grep -r gemini → 0 hasil
V5  docker compose config -q                     → valid
V6  git diff pnpm-lock.yaml                      → @google/genai hilang
T1-T8 tools/test_gateway.py (opsi ulang di platform, LLM_BASE_URL → mock atau workstation)
9.3 Docker compose up −d ai backend frontend; curl localhost:3000/api/ai/health/upstream → available:true
    Browser: login SSO → panel Virtual Assistant → streaming berjalan
```

## 6. Status workstation (sudah tuntas 2026-10-26)

- Ollama 0.40.6 listen `0.0.0.0:11434`, env user-level terpasang,
  rule firewall "Ollama LLM (RCC AI Gateway)" aktif (RemoteIP `10.5.14.0/23`,
  Profiles Domain/Private/Public — untuk produksi perketat RemoteAddress ke IP
  container host platform).
- Driver NVIDIA 582.78 (R580 U11) memecahkan crash `0xc0000005`.
- Benchmark: `qwen3:30b-a3b` 30.3 tok/s (1 stream) & ≈30 tok/s per stream
  (2 stream paralel), VRAM ±15.3/16 GiB — rincian di `workstation-setup.md` § 4.

## 7. Mode B — Gateway berjalan di HPC (deployment aktif sejak 2026-11-04)

Alternatif tanpa menambah folder/blok compose di monorepo platform:
**AI Gateway + Ollama keduanya hidup di HPC**, platform hanya mengubah env.

```
Browser (SSO) → BFF Express :3000  [server platform]
                    │  AI_SERVICE_URL = http://<IP-HPC>:8100
                    ▼
     AI Gateway (container Docker di HPC) :8100
                    │  LLM_BASE_URL = host.docker.internal:11434/v1
                    ▼
     Ollama :11434 [HPC] — TIDAK ter-expose ke LAN
```

| Sisi | Perubahan |
|---|---|
| HPC (repo ini) | `deploy-hpc/docker-compose.hpc.yml` + `deploy-hpc/.env` (`SERVICE_KEY` = nilai platform) — build dari `apps/ai` |
| Platform | root `.env`: `AI_SERVICE_URL=http://<IP-HPC>:8100` + `SERVICE_KEY` sama. Compose platform tidak menjalankan service `ai` (dicadangkan di profile `ai-local`) |
| Firewall HPC | `tools/restrict-firewall.ps1 -HpcGateway [-PlatformIP <IP>]` — 11434 dikunci ke subnet NAT Docker/WSL, 8100 terbuka untuk IP/subnet platform |

Detail rencana & risiko: `plan-run-docker.md`. Operasional harian: `RUNBOOK-ai-service.md` § 2.5.
