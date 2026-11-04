# RUNBOOK — Operasional AI Service (HPC HP Z8 G4) & Integrasi Platform RCC

Dokumen ini adalah panduan operasional harian: **cara menjalankan LLM lokal di
workstation HPC**, **cara memverifikasinya**, dan **langkah mengintegrasikannya
dengan platform RCC** (monorepo `apps/backend + apps/frontend + docker-compose`).

Referensi teknis lengkap:

| Dokumen | Isi |
|---|---|
| `ai-service.md` | Spesifikasi lengkap arsitektur, kontrak SSE § 7, acceptance § 9, troubleshooting § 11 |
| `workstation-setup.md` | Instalasi level-0 HPC, benchmark aktual § 4, checklist § 8 |
| `integration/README-INTEGRASI.md` | Petunjuk menggabungkan paket snippet ke monorepo platform |
| Repo: `https://github.com/raheemkollerb/ai-service` | Seluruh paket (commit `924322a`) |

---

## 1. Arsitektur & alur trafik

```
Browser (SSO login)
   │  POST /api/ai/chat               (cookie SSO, same-origin)
   ▼
BFF Express — apps/backend :3000           [server platform / Docker]
   │  passthrough SSE + X-Service-Key      (x-no-compression, chatLimiter 30/menit)
   ▼
AI Gateway — FastAPI "ai" :8100            [server platform / Docker]
   │  validate → build_context → stream    (OpenAI-compatible adapter)
   ▼
Ollama — :11434 (0.0.0.0)                  [HPC HP Z8 G4 — mesin ini]
   GPU Quadro P5000 16 GB · qwen3:30b-a3b (±30 tok/s, VRAM ±15.3/16 GiB)
```

- **HPC hanya menjalankan Ollama** — gateway produksi berjalan di Docker server
  platform dan memanggil Ollama lewat `LLM_BASE_URL`.
- Protokol SSE (`delta` / `done` / `error`) bersumber dari gateway
  (`ai-service.md` § 7) — BFF passthrough verbatim, frontend mem-parse.
- Tidak ada fallback provider eksternal pada kondisi apapun.

---

## 2. Menjalankan service di HPC

### 2.1 Komponen yang sudah terpasang (status: 2026-10-31)

| Komponen | Kondisi |
|---|---|
| Ollama **0.40.13** | `C:\Users\FastNeutron\AppData\Local\Programs\Ollama\` **(0.40.6 → auto-update ke 0.40.13 pada 2026-11-04 — cek versi setelah tiap restart)** |
| OLLAMA_HOST | `0.0.0.0` (listen semua interface, port 11434) |
| OLLAMA_KEEP_ALIVE | `-1` (model tidak di-unload dari VRAM) |
| OLLAMA_MAX_LOADED_MODELS | `2` |
| OLLAMA_NUM_PARALLEL | `2` (2 stream paralel — atau 1 jika ingin dedikasi penuh) |
| Model utama | `qwen3:30b-a3b` (Q4, ±19 GB — partial offload GPU) |
| Model cadangan | `qwen2.5-coder:14b` (18 tok/s GPU), `qwen14b-long` |
| Driver GPU | NVIDIA **582.78** (R580 U11) — memecah crash `0xc0000005` |
| Firewall | rule "Ollama LLM (RCC AI Gateway)": TCP 11434, RemoteIP `10.5.14.0/23`, semua profil |
| Autostart | tray "Ollama app" start per login; **+ preload model otomatis** (lihat 2.3) |
| IP LAN | `10.5.14.117/23` (Wi-Fi 2 profil Public) |

### 2.2 Mulai / berhenti / periksa

```powershell
# Status Ollama (harus mengembalikan {"version":"0.40.6"})
curl.exe -s --noproxy '*' http://127.0.0.1:11434/api/version

# Jika Ollama tidak berjalan — mulai via aplikasi tray (user-level, tanpa admin):
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe" -WindowStyle Hidden

# Berhenti total (hati-hati: meng-unload model)
Get-Process "ollama app","ollama" -ErrorAction SilentlyContinue | Stop-Process -Force
```

Penting: Ollama berjalan sebagai **aplikasi user** (bukan Windows service) —
butuh sesi login Windows aktif untuk hidup. Bila env user-level diubah,
restart Ollama agar nilainya berlaku.

### 2.3 Preload model otomatis (sudah aktif)

Saat login Windows, entry `HKCU\...\CurrentVersion\Run` **"RCC Ollama Preload"**
menjalankan `tools/ollama-preload.ps1`: menunggu Ollama up (hingga 60 s) →
mengirim 1 token `keep_alive:-1` ke model utama sehingga **VRAM sudah hangat
sebelum chat pertama platform masuk**.

```powershell
# Log operasi preload, jalankan manual, dan nonaktif:
Get-Content "$env:LOCALAPPDATA\Ollama\preload.log" -Tail 10
powershell -NoProfile -ExecutionPolicy Bypass -File D:\Gust\ai-service\tools\ollama-preload.ps1
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'RCC Ollama Preload'   # nonaktifkan
```

Load penuh pertama biasanya 60–70 s; setelah itu instant (model menetap di VRAM).

### 2.4 Uji cepat & pengukuran

```powershell
# Daftar model
curl.exe -s --noproxy '*' http://127.0.0.1:11434/v1/models

# Smoke test endpoint OpenAI-compatible (yang dipakai gateway)
'{"model":"qwen3:30b-a3b","messages":[{"role":"user","content":"Halo"}],"stream":false,"max_tokens":32}' |
  Set-Content "$env:TEMP\smoke.json" -Encoding ASCII
curl.exe -s --noproxy '*' -X POST http://127.0.0.1:11434/v1/chat/completions -H "Content-Type: application/json" --data-binary "@$env:TEMP\smoke.json"

# Mengukur tok/s (tools di repo ini)
cd D:\Gust\ai-service\apps\ai
.\.venv\Scripts\python.exe ..\..\tools\probe.py --model qwen3:30b-a3b --prompt "Ringkas 3 poin." --num-predict 128

# Bila suatu saat perlu model lain:
# ollama pull <model-tag>   (pastikan quant Q4_K_M agar muat scheme partial-offload)
```

---

## 3. Benchmark referensi (terukur aktual — 2026-10-26)

| Konfigurasi | tok/s (1 stream) | tok/s (2 stream) | VRAM puncak |
|---|---|---|---|
| qwen3:30b-a3b Q4 | **30.3** (192 tok, hang) | **30.2 / 30.3 per stream** (192 tok × 2) | ± 15.3 / 16 GiB |
| qwen2.5-coder:14b (dense) | 18.4 GPU | — | 9.5 / 16 GiB |

- `30b-a3b` = MoE ~3 miliar parameter aktif/token → decode lebih murah daripada dense 14b.
- 2 stream paralel **tidak** oversubscribe (NUM_PARALLEL=2) — throughput per stream tidak turun.
- 1 stream hang mencapai 6.8 s untuk 192 token.

---

## 4. Integrasi platform RCC (server platform)

Ringkasan; detail per-file di `integration/README-INTEGRASI.md`.

### 4.1 Salin paket ke monorepo

1. Salin seluruh `apps/ai/` + `tools/` + dokumen (`ai-service.md`,
   `workstation-setup.md`, `RUNBOOK-ai-service.md`) ke root monorepo.
2. Backend: tempel `integration/backend/*` (ai.service.ts, ai.routes.ts,
   aiConfig, chatLimiter, app.use) — § 4 spec.
3. Frontend: tempel `integration/frontend/*`, hapus `geminiService.ts`
   + `@google/genai` + regen lockfile (`pnpm install --lockfile-only`).
4. `integration/docker-compose-ai.yml` → blok service `ai:` ke root
   `docker-compose.yml` (setelah `analytics`, sebelum `backend`).

### 4.2 Kunci env wajib (server platform)

```
SERVICE_KEY=<nilai-sama-semua-service>            # gateway + BFF HARUS sama
LLM_BASE_URL=http://10.5.14.117:11434/v1          # IP LAN HPC ini (bukan localhost)
LLM_MODEL=qwen3:30b-a3b
AI_SERVICE_URL=http://ai:8100                     # internal jaringan Docker
```

Gateway memakai default `host.docker.internal:11434` bila `LLM_BASE_URL` tidak
diset — karena Ollama ada di mesin BERBEDA, `LLM_BASE_URL` ke IP LAN **wajib**.

### 4.3 Perketat firewall HPC (hanya IP server platform)

Rule saat ini berjalan dengan subnet luas `10.5.14.0/23` — setelah platform
hidup, gunakan script:

```powershell
# Jalankan dari user HPC (script meminta UAC sendiri):
powershell -NoProfile -ExecutionPolicy Bypass -File D:\Gust\ai-service\tools\restrict-firewall.ps1 -PlatformIP <IP-server-platform>

# Transisi (belum semua IP platform tahu) — pertahankan subnet LAN juga:
powershell -NoProfile -ExecutionPolicy Bypass -File D:\Gust\ai-service\tools\restrict-firewall.ps1 -PlatformIP <IP-server-platform> -KeepLanSubnet
```

`restrict-firewall.ps1` mengganti RemoteIP rule `Ollama LLM (RCC AI Gateway)`
menjadi IP platform saja (atau + subnet LAN bila flag `-KeepLanSubnet`), tanpa
mengubah nama rule agar compose/pane docker tidak tersentuh.

### 4.4 Rangkaian verifikasi end-to-end (acceptance § 9.3)

```bash
# 1. Dari server platform — runtime HPC bisa dijangkau
curl http://10.5.14.117:11434/v1/models

# 2. Hidupkan compose (gateway + BFF + frontend)
docker compose up -d redis ai backend analytics frontend
docker compose ps ai            # status healthy

# 3. Health upstream via BFF (harap 200 + available:true)
curl localhost:3000/api/ai/health/upstream -H "X-Service-Key: <SERVICE_KEY>"

# 4. Browser: login SSO → panel Virtual Assistant → kirim chat
#    → token streaming progresif + badge "Online — LLM Lokal"

# 5. Firewall: dari mesin di luar subnet 10.5.14.0/23 → curl 11434 harus ditolak
```

---

## 5. Checklist langsung (diprint / diikuti)

- [ ] HPC login (Ollama tray + preload otomatis jalan)
- [ ] `curl http://10.5.14.117:11434/api/version` dari server platform → 200
- [ ] `docker compose up -d redis ai backend analytics frontend` → `ai` healthy
- [ ] `curl localhost:3000/api/ai/health/upstream` → `available:true` + model terdaftar
- [ ] Chat streaming browser berjalan progresif (token mengalir, bukan blok teks sekaligus)
- [ ] 2 chat paralel masih lancar (±30 tok/s per stream)
- [ ] `X-Service-Key` salah → 403; tanpa cookie SSO → 401 `Login required`
- [ ] Log `preload.log` berisi OK (model hangat)
- [ ] (Produksi) ganti SERVICE_KEY dari nilai dev-test + jalankan `tools/restrict-firewall.ps1 -PlatformIP <IP>` sekali

---

## 6. Troubleshooting

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| `503` di `/api/ai/health/upstream` | Ollama mati / salah IP / firewall | `curl` versi dari platform→HPC; cek Ollama tray & rule firewall |
| `403` BFF→gateway / gateway→LLM | `SERVICE_KEY` tidak sama | samakan nilai di env BFF & `ai` |
| `401 `Login required`` | cookie SSO tidak terkirim | login ulang; cek `credentials:'include'` |
| Token muncul sekali (bukan streaming) | SSE di-buffer | pastikan `x-no-compression` di BFF + `X-Accel-Buffering: no` chain proxy |
| Kernel crash `0xc0000005` saat load model GPU | driver NVIDIA tua (< R550) | perbarui minimal ke **582.78** (branch R580) |
| Load model OOM / gagal | VRAM penuh (file besar) | pastikan quant Q4_K_M; tutup model lain (HPC hot-load 2 model) |
| 2 chat paralel berurutan (antre) | `OLLAMA_NUM_PARALLEL` bukan 2 | set 2 (atau 1 dengan antrean, ditangani BFF) |
| `finish_reason`/`usage` hilang | parsing top-level chunk | gunakan `choices[0]` di `ollama_client.py` |
| Ollama tidak listen `0.0.0.0` | env tidak ter-apply saat restart | cek `[Environment]::GetEnvironmentVariable('OLLAMA_HOST','User')`, restart Ollama |

---

## 7. Catatan operasional berkelanjutan

- **Reboot HPC**: login → Ollama auto-start → preload otomatis hangatkan model (60–70 s) — tidak ada langkah manual.
- **Update driver**: pantau NVIDIA RTX/Quadro (R580) — unduh, instal (-s -noreboot), jalankan `nvidia-smi` untuk verifikasi.
- **Upgrade model**: `ollama pull <model>` → ubah `LLM_MODEL` di `.env` platform → `docker compose up -d ai` (recreate) → benchmark ulang 1/2 stream.
- **Retensi disk**: model di `C:\Users\FastNeutron\.ollama\models` — hapus model tak terpakai (`ollama rm <tag>`) bila penuh.
- **Keamanan**: SERVICE_KEY prod ≠ dev-test; log gateway tidak menyimpan isi chat; remoteip firewall dibatasi ke IP server platform saat produksi.
- Backup konfigurasi penting: env user-level Ollama (`Get-ChildItem env:OLLAMA*`), rule firewall, `HKCU Run` entry — semuanya dapat dibaca ulang dari repo ini.

---

## 8. Jaminan privasi: data tidak keluar ke platform lain

Prinsip: model berjalan **sepenuhnya lokal** di HPC; satu-satunya jalur masuk
adalah TCP 11434 yang dijaga firewall Windows. Isi percakapan hanya berpindah
HPC ⇄ platform yang di-whitelist.

### 8.1 Knob keamanan yang sudah dipasang

| Lapisan | Status |
|---|---|
| Firewall inbound TCP 11434 | hanya IP di `RemoteIP` rule "Ollama LLM (RCC AI Gateway)" yang diterima; default Windows menolak sisanya. **Saat integrasi**: `tools/restrict-firewall.ps1 -PlatformIP <IP>` — kunci ke server platform, hapus subnet luas |
| Gateway (`apps/ai`) | semua URL statis dari env (`LLM_BASE_URL`); grep `http` → tidak ada endpoint eksternal; tanpa fallback provider |
| BFF & frontend | BFF memanggil `AI_SERVICE_URL` internal saja (passthrough SSE); bundle frontend `grep VITE_` bersih, no Gemini |
| `OLLAMA_DEBUG` | 0 pada operasi normal (log hanya metadata, bukan isi prompt) |
| Log gateway BFF/FE | tidak menyimpan isi chat |
| Ollama update check | hanya metadata versi (bukan konten percakapan); pull model hanya saat diperintahkan eksplisit |

### 8.2 Audit rutin (mencari tahu siapa yang menyentuh 11434)

```powershell
# Siapa terhubung SAAT INI ke port 11434:
Get-NetTCPConnection -LocalPort 11434 -State Established |
  Select-Object RemoteAddress, RemotePort, OwningProcess, CreationTime

# Terlihat dari log Ollama (metadata request):
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 50 -Wait

# Ringkasan rule firewall aktif:
Get-NetFirewallRule -DisplayName "Ollama LLM (RCC AI Gateway)" | Get-NetFirewallAddressFilter
```

Bila `RemoteAddress` menampilkan IP yang bukan server platform (atau bukan
`127.0.0.1` dari gateway lokal), jalankan `restrict-firewall.ps1` + catat IP
itu untuk dicari sumbernya di switching/ARP.

### 8.3 Perilaku Ollama dapat auto-update

Perhatian: pada 2026-11-04, versi 0.40.6 berubah sendiri menjadi 0.40.13
(oleh update checker tray). Implikasi:
- Setelah update, Ollama restart dengan env user yang sama — `OLLAMA_HOST=0.0.0.0`
  dan firewall rule tetap berlaku; model ter-unload saat restart, jalankan ulang
  `tools/ollama-preload.ps1` untuk hangatkan manual.
- Bila kebijakan menuntut versi pin, matikan auto-update pada tray Ollama →
  Settings → **Automatic Updates** OFF, atau unduh versi resmi terpisah.
