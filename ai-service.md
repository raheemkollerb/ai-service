# Panduan Implementasi — AI Service & LLM Lokal Platform RCC

**Status:** Panduan implementasi (untuk vibe-coding / implementasi manual)
**Versi:** 1.0
**Tanggal:** 27 Oktober 2026
**Basis konsep:** `docs/pengembangan/concept-llm-plan-1.md` (arsitektur Hybrid AI — trial ini hanya jalur **lokal**, tanpa API eksternal)
**Referensi operasional:** `docs/ai/workstation-setup.md` (checklist L0 di workstation)

---

## 0. Cara Pakai Dokumen Ini

Dokumen ini adalah **spec implementasi lengkap** agar AI service (AI Gateway + asisten chat) dapat dibangun dari nol pada monorepo RCC dengan bantuan coding agent (opencode) atau manual.

Panduan untuk agent/developer:

1. Kerjakan fase demi fase secara berurutan: **A → E**, lalu lakukan **Acceptance Tests** (§ 9) sebelum menyatakan selesai.
2. Setiap fase memiliki daftar file, perilaku yang wajib, dan kriteria lolos.
3. Jika repo sudah berisi `apps/ai/` (mis. commit `feat: add local LLM AI gateway`), jangan tulis ulang — gunakan § 3–§ 6 dan § 9 sebagai **verifikasi** terhadap kode yang ada.
4. Konteks repositori RCC dirangkum di § 1 — pastikan implementasi ikut konvensi repositori, bukan konvensi pilihan sendiri.

---

## 1. Konteks Monorepo RCC (WAJIB DIBACA DULU)

Ringkasan repositori dan tata letaknya:

| Item | Nilai | Sumber |
|---|---|---|
| Monorepo | pnpm workspace (root package.json + pnpm-lock.yaml) | `pnpm-workspace.yaml` |
| Aplikasi | React 19 + Vite 6 + TS (`apps/frontend`), Express 4 BFF (`apps/backend`), FastAPI Analytics (`apps/analytics`), shared (`packages/shared-types`) | apps/* |
| Node / Python | Node ≥ 20, Python **3.11** (image: `python:3.11-slim`, `node:20-alpine`) | Dockerfile |
| pnpm | `pnpm@10.28.2` dipin di Docker/CI — **lockfile harus regen sebelum `--frozen-lockfile` build** | `.gitlab-ci.yml` |
| Port utama | frontend nginx `8080` (dev vite `5173`), BFF `3000`, analytics `8000`, AI gateway `8100` (baru), Ollama `11434` (workstation) | docker-compose.yml |
| Auth pengguna | BRIN SSO session (cookie `rcc_session`), login di analytics via `/auth/sso`; BFF mem-validasi tiap request via middleware `requireSsoSession` | apps/analytics/app/api/auth.py |
| Auth antar-service | header statis `X-Service-Key`, dibanding dengan env `SERVICE_KEY` | apps/analytics/app/core/security.py |
| Streaming | BFF → frontend: passthrough SSE; backend→backend: axios `responseType: 'stream'` → pipe | apps/backend/src/services/ai.service.ts |
| DB | PostgreSQL datamart **read-only** via SSH tunnel (`db-tunnel` container) — hanya analytics yang memegang DATABASE_URL; AI Gateway TIDAK memegang akses DB di versi ini | docker-compose.yml |

Prinsip keamanan yang wajib dipertahankan di sepanjang implementasi (dari dokumen konsep):

- **Internal-only:** Tidak ada fallback/kode ke API LLM eksternal. Data tetap di jaringan internal.
- **Semua rahasia & keputusan di backend:** Service key, model whitelist, limit token — semuanya disimpan di server; browser tidak pernah tahu alamat runtime LLM.
- **Minimum data:** Batas ukuran input, riwayat, dan output ditegakkan di gateway.
- **LLM tidak mengesampingkan otorisasi:** LLM hanya menghasilkan teks; tidak diberikan tools/DB/akses apa pun di tahap ini.

---

### 1.1 Gambaran Arsitektur

```
[Browser] AIChat panel
   │  fetch POST /api/ai/chat (same-origin, cookie SSO)
   ▼
[BFF Express :3000] ai.routes.ts
   │  requireSsoSession + chatLimiter + validasi body
   │  X-Service-Key → AI gateway (SSE passthrough, responseType stream)
   ▼
[AI Gateway apps/ai :8100] (FastAPI, Docker)
   │  verify_service_key + sanitasi pesan + system prompt server-side
   │  POST {LLM_BASE_URL}/chat/completions (OpenAI-compatible, stream)
   ▼
[Ollama di Workstation Z8 G4 :11434] — inferensi 100% lokal
```

Satu arah data: Browser → BFF → Gateway → Ollama. **Tidak ada jalur keluar ke internet dari gateway.** Runtime LLM di-workstation hanya menerima konteks chat yang sudah divalidasi.

---

## 2. Fase A — Workstation / HPC (Z8 G4): Runtime LLM

**Target:** HP Z8 G4 (dual Xeon, RAM 256 GB, GPU NVIDIA RTX/Ada 16 GB, Windows).
Pilihan model menyesuaikan perangkat: **MoE 30B-class** adalah sweet spot (memori CPU/GPU hybrid; 40–70 tok/s); dense 70B hanya untuk batch.

### A.1 Instalasi Ollama

1. Unduh installer Windows dari <https://ollama.com/download/windows>, pasang sebagai aplikasi (service berjalan otomatis).
2. Set environment *machine-level* (PowerShell admin):

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST","0.0.0.0","Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE","-1","Machine")     # model tetap di RAM/VRAM
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS","2","Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL","2","Machine")    # sesuaikan hasil load test
[Environment]::SetEnvironmentVariable("OLLAMA_DEBUG","1","Machine")           # hanya saat debugging
```

3. Restart Ollama, pastikan listen di `0.0.0.0:11434`.

### A.2 Model

Model default trial: **`qwen3:30b-a3b`** — MoE 30B total / 3B aktif, Bahasa Indonesia bagus, compute ringan (tidak "over" untuk Z8 G4), hampir seluruhnya muat di 16 GB VRAM dengan beberapa layer expert offload ke RAM.

```powershell
ollama pull qwen3:30b-a3b
```

Kandidat upgrade (swap via env `LLM_MODEL` tanpa mengubah kode):

| Model | Sumber | Ukuran (Q4) | Catatan |
|---|---|---|---|
| Qwen-SEA-LION-v4.5-27B | GGUF `aisingapore/Qwen-SEA-LION-v4.5-27B-IT-GGUF` + Modelfile `ollama create` | 16.8 GB | Terbaik di Bahasa Indonesia + SEA, 262K ctx, MIT |
| GLM-4.7-Flash 30B-A3B | GGUF `bartowski/zai-org_GLM-4.7-Flash-GGUF` | ≈ 18.5 GB | Reasoning/tool-calling terkuat di kelasnya, MIT |
| Gemma-SEA-LION-v4.5 (E2B/4B) | GGUF kecil | ~5 GB | Untuk planner/classifier fase RAG, sangat cepat, MIT |
| bge-m3 | `ollama pull bge-m3` | ~2.3 GB | Embedding multilingual untuk fase RAG (bukan trial ini) |

Modelfile contoh (SEA-LION):

```dockerfile
FROM .\Qwen-SEA-LION-v4.5-27B-IT-Q4_K_M.gguf
PARAMETER temperature 0.7
PARAMETER num_ctx 16384
SYSTEM """Anda adalah asisten AI internal platform Research Control Center (RCC) milik BRIN."""
```

**Kriteria lolos A:** `ollama run qwen3:30b-a3b "halo"` menjawab; `GET http://<IP-Z8G4>:11434/v1/models` memuat model.

### A.3 Keamanan jaringan workstation

- Windows Firewall: port TCP `11434` **hanya** diizinkan dari IP server platform (yang menjalankan Docker) + subnet admin:

```powershell
New-NetFirewallRule -DisplayName "Ollama - RCC Dev Only" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 11434 `
  -RemoteAddress "<IP-server-platform>,<subnet-LAN-workstation>"
```

- Opsi hardening *fully air-gapped*: blok outbound internet di workstation (kecuali subnet LAN) dan nonaktifkan fitur update check Ollama di app settings.
- Akses adalah *service-to-service*; user/browser tidak memerlukan akses langsung ke 11434.

### A.4 Benchmark (catat hasil)

| Konfigurasi | tok/s (1 stream) | tok/s (2 stream) | VRAM puncak |
|---|---|---|---|
| qwen3:30b-a3b Q4 | … | … | … |

---

## 3. Fase B — AI Gateway `apps/ai` (FastAPI)

### B.1 Struktur file yang dibuat

```
apps/ai/
├── Dockerfile                       # python:3.11-slim, multi-stage meniru apps/analytics
├── requirements.txt                 # fastapi==0.115.0, uvicorn[standard]==0.32.0,
│                                    # httpx==0.28.1, pydantic==2.10.3, pydantic-settings==2.6.1
├── .env.example
└── app/
    ├── __init__.py
    ├── main.py                      # FastAPI app + CORS + lifespan (tutup httpx client)
    ├── core/
    │   ├── config.py                # pydantic-settings
    │   └── security.py              # verify_service_key (X-Service-Key)
    ├── api/
    │   └── chat.py                  # router /ai: POST /ai/chat (SSE), GET /ai/health/upstream
    ├── providers/
    │   └── ollama_client.py         # adapter OpenAI-compatible + httpx streaming
    ├── services/
    │   └── chat_service.py          # validasi + susun konteks + formatter SSE
    └── models/
        ├── __init__.py              # re-export HealthResponse
        └── base.py
```

### B.2 Konfigurasi (`app/core/config.py`)

Field `Settings` (semuanya bisa dioverride env, case-insensitive):

| Field | Env | Default | Fungsi |
|---|---|---|---|
| `host`,`port` | `HOST`,`PORT` | `0.0.0.0`,`8100` | server |
| `environment` | `ENVIRONMENT` | `development` | OpenAPI docs hanya di dev |
| `service_key` | `SERVICE_KEY` | *(wajib, tanpa default)* | auth BFF→gateway |
| `llm_base_url` | `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | runtime OpenAI-compatible |
| `llm_api_key` | `LLM_API_KEY` | `ollama` | header Bearer (Ollama tidak memvalidasinya, tetap isi) |
| `llm_model` | `LLM_MODEL` | `qwen3:30b-a3b` | whitelist satu-satunya model |
| `llm_temperature` | `LLM_TEMPERATURE` | `0.7` | sampling |
| `llm_max_tokens` | `LLM_MAX_TOKENS` | `2048` | batas output |
| `llm_timeout` | `LLM_TIMEOUT` | `120.0` | detik; koneksi & baca |
| `llm_system_prompt` | `LLM_SYSTEM_PROMPT` | *(persona asisten internal, lihat di bawah)* | dikunci server-side |
| `llm_max_history_messages` | `LLM_MAX_HISTORY_MESSAGES` | `20` | limit riwayat |
| `llm_max_message_chars` | `LLM_MAX_MESSAGE_CHARS` | `8000` | limit per pesan |
| `cors_origins` | `CORS_ORIGINS` | origin BFF | format koma-terpisah |

Default system prompt (boleh diganti via env, jangan diubah tanpa review — ini mengunci perilaku asisten):

```
Anda adalah asisten AI internal platform Research Control Center (RCC) milik BRIN.
Bantu administrator riset menganalisis data, tren, dan kinerja periset. Jawab dengan
bahasa Indonesia yang profesional, ringkas, dan berbasis data yang diberikan. Jika suatu
pertanyaan membutuhkan data platform yang belum tersedia dalam percakapan ini, sampaikan
batasan tersebut dan sarankan pengguna membuka halaman atau filter terkait. Jangan
mengarang angka, nama, atau referensi.
```

### B.3 Perilaku wajib

**`app/core/security.py`**
- `APIKeyHeader(name="X-Service-Key")`; jika header ≠ `settings.service_key` → 403.
- Pola *identik* dengan `apps/analytics/app/core/security.py` — jangan ciptakan skema baru.

**`app/services/chat_service.py`**
- `validate_messages(raw)`:
  - Hanya terima role `user` | `assistant`; **role `system` dari klien dibuang** (system prompt milik gateway saja).
  - Maks `llm_max_history_messages` pesan (lebih → `ChatValidationError` berbahasa Indonesia), maks `llm_max_message_chars` karakter/pesan.
  - Pesan kosong/whitespace di-skip; jika semua tak valid → validasi error.
- `build_context(messages)`: `[system prompt] + messages`.
- `stream_chat(...)`: memanggil provider streaming, bungkus tiap event menjadi frame SSE `data: {json}\n\n` (`ensure_ascii=False`).

**`app/providers/ollama_client.py`**
- Konfigurasi httpx: `base_url=LLM_BASE_URL`, header `Bearer`, timeout (LLM_TIMEOUT, connect 10s), satu `AsyncClient` shared.
- `list_models()` → `GET /models` (untuk health-upstream); gagal → `UpstreamUnavailable`.
- `stream_chat_completions(messages, model)` — `POST /chat/completions` `stream:true`:
  - Request body: `{"model", "messages": [...system+history...], "stream": true, "temperature", "max_tokens"}`.
  - Baca SSE: `aiter_lines()`, ambil baris `data:`; `data: [DONE]` → break; parse JSON.
  - **GOTCHA (bug yang pernah ditemukan):** `finish_reason` DAPAT **di dalam `choices[0]`** — bukan top-level chunk. Event:
    - `delta` bila `choices[0].delta.content` tidak kosong;
    - `done` bila `choices[0].finish_reason` tidak `None`, kirim `usage` dari chunk kalau ada.
  - Penanganan gagal: HTTP ≥ 400 → event `error`; `httpx.HTTPError` → event `error` `LLM runtime tidak dapat dihubungi: ...`; **TIDAK ADA fallback ke path lain.**
- `close_client()` dipanggil `lifespan` saat shutdown.

**`app/api/chat.py` (router prefix `/ai`, dependency `verify_service_key`)**
- `POST /ai/chat`:
  - Request body (Pydantic): `messages: [{role, content}]` opsional `model: str | None`.
  - Whitelist model: jika request `model` ≠ settings `llm_model` → set `None` (pakai default).
  - Response: `StreamingResponse` `media_type="text/event-stream"` dengan header **`Cache-Control: no-cache`, `X-Accel-Buffering: no`** (anti-buffering nginx!). Error validasi → 400.
- `GET /ai/health/upstream` → `200 {llm_base_url, model, available:true, models:[...]}`; runtime gagal → **503** berisi detail.
- Bocor informasi: hanya metadata config, jangan pernah masukkan isi prompt.

**`app/main.py`**
- FastAPI (metadata: `RCC - AI Gateway`), `openapi_url` hanya di development, `CORSMiddleware` (allow `X-Service-Key` header), mount `chat.router`, `GET /health` (ringan, cepat, tanpa probe LLM), `GET /` (metadata service).
- **Catatan:** `/health` tetap hidup walau LLM mati — cek kesehatan LLM gunakan `/ai/health/upstream`.

### B.4 Dockerfile — meniru `apps/analytics/Dockerfile`

- Multi-stage: builder `python:3.11-slim` (`pip install -r requirements.txt`), produksi `python:3.11-slim` + `curl`.
- `COPY app ./app`, user non-root, `EXPOSE 8100`, HEALTHCHECK curl `/health`, CMD `uvicorn app.main:app --host 0.0.0.0 --port 8100`.
- **Jangan** copy file `.env` asli; cukup `.env.example` disalin sebagai `.env` (meniru pola analytics).

### B.5 `.env.example` apps/ai

```
HOST=0.0.0.0
PORT=8100
ENVIRONMENT=development
SERVICE_KEY=your-service-key-here
# Utamakan IP LAN workstation, contoh: http://192.168.1.50:11434/v1
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3:30b-a3b
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048
LLM_TIMEOUT=120
LLM_MAX_HISTORY_MESSAGES=20
LLM_MAX_MESSAGE_CHARS=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

**Kriteria lolos B:** (a) `python -m compileall apps/ai/app` sukses; (b) container/uvicorn hidup, `GET /health` 200; (c) `POST /ai/chat` dengan key salah → 403; dengan `messages` kosong → 400; role `system` dari klien dibuang.

---

## 4. Fase C — BFF Express (`apps/backend`)

### C.1 File yang diubah/dibuat

| File | Perubahan |
|---|---|
| `src/config/index.ts` | Tambah `aiConfig`: `baseURL` (env `AI_SERVICE_URL`), `serviceKey` (`SERVICE_KEY`), `timeout: 120000`, `maxHistoryMessages: 20`, `maxMessageChars: 8000` |
| `src/services/ai.service.ts` | *(new)* klien gateway + proxy streaming |
| `src/routes/ai.routes.ts` | *(new)* `POST /chat`, `GET /health/upstream` |
| `src/middleware/rateLimit.middleware.ts` | Tambah `chatLimiter` — **30 req / menit** |
| `src/app.ts` | `app.use('/api/ai', aiRoutes);` **di bawah** `app.use('/api', preserveSessionCookie, requireSsoSession)` |
| `.env.example` | Tambah `AI_SERVICE_URL=http://localhost:8100` |

### C.2 Perilaku wajib `ai.service.ts`

- `validateAiMessages(body)`: cleaning identik dengan gateway (role user/assistant, ≤20 pesan, ≤8000 char); lempar custom `AiValidationError`.
- `streamChat(messages, req, res)`:
  - `axios.post(`${aiConfig.baseURL}/ai/chat`, { messages }, { responseType: 'stream', headers: { 'X-Service-Key', 'Content-Type' }, timeout })`.
  - Sebelum itu: **`req.headers['x-no-compression'] = 'true'`** — WAJIB, karena middleware `compression()` default akan mengompresi/mem-buffer `text/event-stream`.
  - Set header browser: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`; lalu `res.flushHeaders()`.
  - `upstream.data.pipe(res)`; pada `error`/`close` hancurkan stream keduanya — **JANGAN rewrite payload**, passthrough saja.
  - Error sebelum header: 400 (validasi) / 503 (gateway tidak hidup) — **jangan** konversi jadi pemanggilan path eksternal.
- `healthUpstream()` → `GET /ai/health/upstream` passthrough JSON.

### C.3 Perilaku wajib `ai.routes.ts`

- `POST /chat` + `chatLimiter` + `validateAiMessages(req.body)` → `aiService.streamChat(...)`, catch `AiValidationError` → 400.
- `GET /health/upstream` → passthrough; 503 bila gateway/runtime mati (dengan JSON `available:false`).
- Auth SSO **tidak di-cek ulang** di sini (middleware global sudah menahan); rate limit spesifik chat sebaiknya di-`chatLimiter`.

**Kriteria lolos C:** `pnpm --filter backend exec tsc --noEmit` sukses (0 error); `pnpm --filter backend build` sukses; `/api/ai/*` tanpa cookie SSO → 401 `Login required`.

---

## 5. Fase D — Frontend (`apps/frontend`)

### D.1 File yang diubah/dibuat

| File | Perubahan |
|---|---|
| `src/services/aiService.ts` | *(new)* klien SSE, parse protocol gateway |
| `src/hooks/useChat.ts` | streaming riil, progressive update, status koneksi |
| `src/components/features/ai-chat/AIChat.tsx` | indicator status Online/Offline + footer **"Asisten AI Internal — LLM Lokal"** (bukan "Powered by Gemini") |
| `src/services/geminiService.ts` | **HAPUS** — tidak perlu dibuat backward compat |
| `package.json` | **Hapus** dependency `@google/genai`, lalu **`pnpm install --lockfile-only`** (root) untuk regen lockfile — WAJIB, karena Dockerfile memakai `pnpm install --frozen-lockfile` |
| `src/vite-env.d.ts` | **Hapus** `VITE_GEMINI_API_KEY` dari `ImportMetaEnv` |
| `src/types/chat.types.ts` | tidak berubah (`role: 'user' | 'model'`) |

### D.2 Perilaku wajib `aiService.ts` (klien SSE)

- **Wajib fetch stream** (bukan `EventSource`, karena POST):

```ts
fetch('/api/ai/chat', { method: 'POST', credentials: 'include', headers: {...}, body: JSON.stringify({ messages }) });
```

- Baca `response.body.getReader()`; decoder TextDecoder; **buffer pecahan frame**: split `"\n\n"`; parse line `data:` → JSON:
  - `{"type":"delta","text"}` kumpulkan (kembalikan full text pada akhir stream);
  - `{"type":"done","finish_reason"}` → batalkan reader, selesai;
  - `{"type":"error","message"}` → lempar ke handlers.
- Pemetaan status: HTTP 401 → pesan "Sesi berakhir, silakan login kembali"; non-OK → ambil `detail` dari JSON bila tersedia; gagal `fetch` → "Tidak dapat menghubungi layanan AI platform."
- **Tidak ada** URL LLM/API key di file ini — akses tetap same-origin melalui BFF (dev vite: `/api` diproxy ke `localhost:3000` via `vite.config.ts`; prod Docker: nginx proxy `location /api/` menuju `backend:3000`).

### D.3 Perilaku wajib `useChat.ts`

- State: `messages` (welcome tunggal role `model`), `input`, `isLoading`, `status: 'online' | 'offline' | 'unknown'`, scrollRef.
- `handleSend`:
  1. push pesan user lalu **draft assistant kosong** di akhir list.
  2. Siapkan history di kirim: **skip welcome pertama** (hemat token) & konversi role `model` → `assistant`.
  3. `aiService.streamChat(history, handlers)`: `onDelta` → upsert draft secara progressive (jika draft masih kosong, isi langsung dengan delta pertama); `onError` → isi draft dengan pesan error + set `status:'offline'`.
  4. Bila **tidak ada delta apa pun** sampai stream selesai → draft diisi pesan offline: *"Asisten AI belum terhubung ke LLM lokal…"* + `status:'offline'`.
- Petakan `status`: `online` (dot hijau + "Online — LLM Lokal"), `offline` (dot merah "Offline"), `unknown` (abu "Menghubungkan…").

**Kriteria lolos D:** `pnpm --filter frontend build` (vite) sukses; `grep -r gemini` di `apps/frontend/src` → **0 hasil**; UI chat streaming token muncul progresif.

---

## 6. Fase E — Runtime & Env (docker compose + root env)

### E.1 docker-compose.yml — service `ai`

Tambah blok (letakkan setelah service `analytics`, sebelum `backend`):

```yaml
  ai:
    build:
      context: ./apps/ai
      dockerfile: Dockerfile
    ports:
      - "8100:8100"
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-development}
      - SERVICE_KEY=${SERVICE_KEY:-dev-service-key}
      - LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:11434/v1}
      - LLM_MODEL=${LLM_MODEL:-qwen3:30b-a3b}
      - LLM_TEMPERATURE=${LLM_TEMPERATURE:-0.7}
      - LLM_MAX_TOKENS=${LLM_MAX_TOKENS:-2048}
      - LLM_TIMEOUT=${LLM_TIMEOUT:-120}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
```

Catatan:
- **Tidak ada `depends_on` ke LLM** — Ollama tidak berada di dalam compose (berjalan di mesin fisik/VM terpisah). Gateway harus tetap healthy walau LLM mati; status LLM hanya dicek lewat `/ai/health/upstream`.
- `extra_hosts host.docker.internal:host-gateway` dibutuhkan untuk default `LLM_BASE_URL` (Ollama di host Docker yang sama). Di produksi gunakan IP LAN runtime terpisah.

### E.2 root `.env` + `.env.example` (kunci baru)

```
SERVICE_KEY=...                                  # nilai sama di semua service; ganti di produksi
LLM_BASE_URL=http://<IP-Z8G4>:11434/v1           # IP LAN workstation, bukan localhost
LLM_MODEL=qwen3:30b-a3b
AI_SERVICE_URL=http://ai:8100                     # dari dalam jaringan Docker
```

- **`.env` tidak boleh di-commit;** `.env.example` mendokumentasikan formatnya.
- Parameter yang **wajib** diset operator: `SERVICE_KEY` (sama semua service), `LLM_BASE_URL` (IP workstation), sesuaikan `LLM_MODEL` bila ganti model.
- Bila menambah kunci env baru: perbarui `.env.example` di commit yang sama dengan kode.

---

## 7. Protokol SSE (kontrak lintas-lapis, JANGAN diubah tanpa sinkron semua sisi)

Setiap event berbentuk frame `data: {JSON}\n\n`. Gateway adalah **sumber kebenaran** protokol; BFF melewatkan (passthrough) verbatim; frontend yang mem-parsing:

| Event | Payload | Pengirim |
|---|---|---|
| `delta` | `{"type":"delta","text":"..."}` | gateway (dari model) |
| `done` | `{"type":"done","finish_reason":"stop"|"length"|..., "usage":{...?}}` | gateway (dari chunk terakhir) |
| `error` | `{"type":"error","message":"..."}` | gateway — upstream mati / 4xx / 5xx |
| (HTTP) | 400 detail invalid input · 401 tidak login (BFF) · 403 service key salah · 503 gateway/runtime tidak hidup | BFF/gateway |

Aturan:
- Jangan menciptakan event baru di BFF/frontend; jika perlu, tambahkan di gateway lalu update dokumen ini.
- Error event **selalu menutup stream** setelahnya.
- Tidak ada fallback provider eksternal pada kondisi apapun.
- Client boleh membatalkan (AbortController): reader menghentikan koneksi sehingga BFF `destroy` stream upstream.

---

## 8. Roadmap setelah trial (JANGAN dikerjakan dalam trial ini)

Sesuai docs konsep § 17 dan SDD:

| Fase | Isi | Titik integrasi yang sudah disiapkan |
|---|---|---|
| Tahap 2 | Tools analitik (`get_publication_statistics`, dsb.) — perlu intent + tool calling schema + validasi backend | tambah di `apps/ai` services; whitelist tool di konfig; perluasan protokol SSE: event `tool_call`/`tool_result` |
| Tahap 3 | RAG: ingest + `bge-m3` + pgvector + sitasi | komponen baru di `apps/ai`; `.env` `RAG_*`; dmart tetap read-only |
| Tahap 4 | Policy engine + routing matang + klasifikasi data | struktur modul baru; gateway tetap satu-satunya pintu |
| Opsional | vLLM (WSL2/Linux di workstation) | hanya ganti `LLM_BASE_URL` — adapter OpenAI-compatible sudah memungkinkan |

---

## 9. Acceptance Tests (jalankan semua sebelum dinyatakan selesai)

### 9.1 Unit/verifikasi cepat

| Kode | Perintah | Ekspektasi |
|---|---|---|
| V1 | `python -m compileall apps/ai/app` | exit 0 |
| V2 | `pnpm --filter backend exec tsc --noEmit` | 0 error |
| V3 | `pnpm --filter backend build` | dist terbentuk |
| V4 | `pnpm --filter frontend build` | sukses; **grep gemini di src → 0** |
| V5 | `docker compose config -q` | valid (warning DB_USER/SSH_* wajar bila env belum di-set) |
| V6 | lockfile: `git diff pnpm-lock.yaml` berisi penghapusan `@google/genai` | ✓ (pastikan `pnpm install --lockfile-only` sudah dijalankan) |

### 9.2 Integration (mock LLM OpenAI-compatible di port lokal)

Untuk mesin tanpa akses ke workstation, buat mock server SSE OpenAI-compatible sesuai format § 7 (modul test `fastapi` kecil yang menyediakan `POST /v1/chat/completions`; jalankan di `:11999`, set `LLM_BASE_URL=http://127.0.0.1:11999/v1`, `SERVICE_KEY=dev-test`, jalankan uvicorn gateway `:8101` lalu uji):

| ID | Skenario | Ekspektasi |
|---|---|---|
| T1 | `POST /ai/chat` `X-Service-Key` salah | 403 |
| T2 | `messages: []` | 400 dengan detail valid |
| T3 | `messages` mengandung `role:"system"` | 200, stream delta; system dibuang |
| T4 | 21 messages | 400 (maks 20) |
| T5 | multi-turn user/assistant 2× | 200, SSE delta + **done** (`finish_reason` + `usage` ada) |
| T6 | runtime LLM mati (base URL salah) | stream `error` event, stream ditutup; tidak ada 5xx server |
| T7 | `GET /health` | 200 `ai-gateway` selamat walau LLM mati |
| T8 | `GET /ai/health/upstream` runtime hidup | 200 `available:true` + daftar models |

> Catatan gotcha verifikasi: PowerShell salah parse `curl.exe -d '{"..."}'`. Gunakan client `python + httpx` kecil untuk payload JSON (bukti: smoke test nyata memakai httpx pada repo ini).

**Hasil run aktual (2026-10-26, `tools/test_gateway.py` — mock `:11999`, gateway `:8101`,
dead-upstream `:8102`): SEMUA 8 TES PASS.**
Detail: T1 403/403; T2 400 detail "Tidak ada pesan yang valid..."; T3 system dibuang
(tepat 1 system tersisa `build_context`, tidak ada leak payload user); T4 400; T5
`text/event-stream` + delta×4 + `done{finish_reason:"stop",usage}`; T6 status 200
(tanpa 5xx) bermuara frame `error`; T7 `{"status":"ok"}`; T8 `available:true` +
daftar model. Catatan perbaikan saat tes: `ChatMessage.role` awalnya `Literal["user",
"assistant"]` menolak `system` dengan 422 → diperluas ke `["user","assistant","system"]`
(bermaka `validate_messages` yang membuang system sesuai spesimen § 7).

### 9.3 Runtime penuh (workstation nyata)

```
1. curl http://<IP-Z8G4>:11434/v1/models                       → daftar model dari workstation
2. docker compose up -d redis ai backend analytics frontend    → `ai` healthy
3. curl localhost:3000/api/ai/health/upstream                  → available:true (via BFF)
4. Browser: login SSO → buka panel Virtual Assistant → kirim chat → token streaming
5. Firewall: jaringan yang TIDAK di-whitelist tidak dapat akses 11434
```

---

## 10. Checklist Keamanan (PENTING — jangan lewati)

- [x] `.env` tidak pernah masuk git (`apps/ai/.gitignore` memuat `.env`; repo lokal belum git — verifikasi `git status` saat sudah push).
- [ ] `SERVICE_KEY` di semua service sama; nilai dev tidak dipakai di produksi.
- [ ] Tidak ada string API key/URL runtime di bundle frontend; grep `VITE_` hanya menyisakan `VITE_API_URL`, `VITE_WS_URL`, `VITE_ENABLE_DEV_LOGIN`. (Snippet di `integration/frontend/` bersih — grep `gemini|VITE_|@google` → 0.)
- [x] Gateway & BFF tidak punya kode pemanggil URL eksternal (grep `http` di `apps/ai/app` → hanya `LLM_BASE_URL` env/default internal + CORS localhost; sisi BFF menunggu penggabungan).
- [x] Firewall workstation: rule "Ollama LLM (RCC AI Gateway)" aktif — RemoteIP `10.5.14.0/23`, TCP 11434, semua profil. Saat deploy platform, pertajam `RemoteAddress` ke IP container host.
- [ ] Rate limit aktif: apiLimiter global (BFF) + chatLimiter 30/menit (`/api/ai/chat`). (Snippet `chatLimiter` siap di `integration/backend/middleware-snippet.ts`.)
- [x] Log jangan menyimpan isi percakapan utuh (grep `logging|print` di `apps/ai/app` → 0; Ollama pun hanya menyimpan metadata).
- [x] Semua prompt masuk ke model melewati validasi panjang & role sanitize (terbukti T2/T3/T4; system dari klien dibuang, hingga 1 system bawaan gateway).

---

## 11. Troubleshooting

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| `/v1/models` 404 di workstation | Ollama versi lama | update Ollama |
| Load model OOM/gagal di workstation | VRAM terlalu mepet dengan file besar | pastikan quant Q4_K_M; update driver GPU |
| Token tidak muncul (muncul blok sekali) | kompresi/buffer menahan SSE | pastikan `x-no-compression` di BFF & header `X-Accel-Buffering: no` di chain proxy |
| 401 saat `POST /api/ai/chat` | cookie SSO tidak terkirim | login ulang; cek `credentials:'include'` + CORS |
| 503 health-upstream | LLM runtime mati / firewall / IP salah | cek `OLLAMA_HOST`, firewall rule, `LLM_BASE_URL` dari dalam container (`docker compose exec ai sh` → curl) |
| Python 3.14 gagal install pydantic | wheel `cp314` tidak tersedia untuk `pydantic-core` 2.10.x | gunakan Python 3.11 (image Docker) atau pip versi lain di venv dev |
| `--frozen-lockfile` gagal di Docker build | lockfile tidak sinkron dengan package.json | jalankan `pnpm install --lockfile-only` di root sebelum build |
| `finish_reason`/`usage` tidak sampai frontend | parsing di top-level chunk (bug nyata ditemukan saat smoke test) | parse `choices[0].finish_reason` di ollama_client.py |
