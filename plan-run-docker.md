# PLAN — Menjalankan AI Gateway via Docker di HPC ("Mode B")

Status dokumen: **Fase 0–3 sudah dieksekusi 2026-11-05** (bukti log di bawah);
Fase 4–5 menyusul. Disusun: 2026-11-04 · repo `raheemkollerb/ai-service`
(branch `main`)

**Update eksekusi Fase 0–3 (2026-11-05) — Mode B HIDUP di HPC:**

- **Fase 0:** penyebab "Docker gagal dibuka" = **Virtualization Technology
  (VT-x) di BIOS HP Z8 G4 OFF** + log `HCS_E_HYPERV_NOT_INSTALLED`
  (`com.docker.backend.exe.log`). VT-x di-enable via BIOS (F10 → Advanced →
  Device Configuration); *Virtual Machine Platform* ternyata sudah terpasang,
  jadi tidak perlu `wsl --install --no-distribution`. Setelah BIOS: WSL Store
  3.0.3.0, distro `docker-desktop` **Running (WSL2)**, engine 29.9.2,
  `docker run --rm hello-world` OK, `AutoStart=true` di settings-store.json.
- **Fase 2:** `.env` dibuat dari `.env.example` dengan SERVICE_KEY dev acak
  (32-byte, tidak di-commit; tertutup `.gitignore`). `docker compose -f
  docker-compose.hpc.yml up -d --build` → `deploy-hpc-ai-1` **healthy**,
  `restart: unless-stopped`. `/health` 200 dari `127.0.0.1` **dan** LAN.
- **Fase 3 tahap 1:** rule `"RCC AI Gateway (:8100)"` TCP 8100,
  `remoteip=10.5.14.0/23`, semua profile (dibuat via UAC 2026-11-05).
- **⚠️ IP HPC berubah 10.5.14.117 → 10.5.15.9** (DHCP Wi-Fi 2, tetap dalam
  subnet /23 sehingga rule firewall tahap 1 tetap valid). Saat server platform
  live gunakan `AI_SERVICE_URL=http://10.5.15.9:8100` (atau reservasi DHCP agar
  stabil) + sinkronisasi SERVICE_KEY.
- Smoke test lulus: kunci salah → **403**; `/ai/health/upstream` →
  `available:true` melalui `host.docker.internal:11434` (NAT Docker → Ollama
  lokal jalan); SSE chat → `delta` progresif + `done {finish_reason:"stop"}`.
- Tersisa manual: firewall **tahap 2** (11434→subnet NAT Docker + 8100→IP
  platform) saat IP platform diketahui; checklist § 7 (reboot → container hidup
  otomatis + preload Ollama); Fase 4 (dokumen) & Fase 5 (integrasi platform).

**Update eksekusi (2026-11-04)** — persiapan kode & dokumen Mode B sudah
dikerjakan dari sisi repo:

- `deploy-hpc/` dibuat: `docker-compose.hpc.yml` + `.env.example` + `README.md` (Fase 1).
- `apps/ai` di-port ke **implementasi platform sebagai acuan tunggal**;
  acceptansi `tools/test_gateway.py` T1–T8 **PASS ulang** (T7 kini memeriksa
  `{"status":"healthy", "service":"ai-gateway", ...}` mengikuti versi platform;
  body 503 `/ai/health/upstream` dirapikan menjadi flat).
- `tools/restrict-firewall.ps1` mendapat mode `-HpcGateway` (11434→NAT Docker,
  8100→IP platform) — eksekusinya tetap oleh admin di HPC (Fase 3).
- Dokumen diperbarui: `README-INTEGRASI.md` § 7 Mode B; `RUNBOOK` § 1/2.5/4.2/
  4.3/4.4 revisi; `ai-service.md` catatan porting (T7 + 503 flat).
- Tersisa manual di HPC: Fase 0 (instal Docker Desktop), build & start compose,
  firewall tahap 1–2, verifikasi checklist § 7 — setelah server platform siap.

Dokumen ini memuat ide: **"platform utama tidak perlu menambah/menempel folder
`apps/ai`"** dengan menjalankan AI Gateway sebagai container Docker **di mesin
HPC ini sendiri** — dikaitkan dengan kondisi aktual per hari ini.

---

## 1. Kondisi saat ini (as-is)

### 1.1 Runtime LLM di HPC — hidup & sehat

| Komponen | Kondisi |
|---|---|
| Ollama | **0.40.13** (semula 0.40.6 → auto-update 2026-11-04), listen `0.0.0.0:11434` + IPv6 |
| Model termuat | `qwen3:30b-a3b` ±19 GB, split `23%/77% CPU/GPU`, `UNTIL: Forever` (KEEP_ALIVE=-1) |
| VRAM | 15.441 / 16.384 MiB (nvidia-smi) |
| Benchmark (2026-10-26) | 1 stream **30.3 tok/s** · 2 stream **30.2/30.3 tok/s per stream** (paralel), 192 token |
| Driver GPU | NVIDIA 582.78 (R580 U11) — crash `0xc0000005` sudah tuntas |
| Preload otomatis | HKCU Run "RCC Ollama Preload" → `tools/ollama-preload.ps1` (log `%LOCALAPPDATA%\Ollama\preload.log`) |
| Model cadangan | `qwen2.5-coder:14b` (18 tok/s GPU), `qwen14b-long`, `qwen3.5:35b(-64k)` |

### 1.2 Komponen repo ini (sumber kebenaran) — sudah lolos acceptance

| Item | Status |
|---|---|
| `apps/ai` (AI Gateway FastAPI, kontrak SSE § 7) | V1 compile OK · **T1–T8 SEMUA PASS** (mock LLM :11999, `tools/test_gateway.py`) |
| `integration/` | snippet BFF + frontend + blok compose + `README-INTEGRASI.md` (Mode A) |
| Dokumen | `ai-service.md` · `workstation-setup.md` · `RUNBOOK-ai-service.md` |
| Tools | `probe.py` · `mock_llm.py` · `test_gateway.py` · `ollama-preload.ps1` · `restrict-firewall.ps1` |
| GitHub | pushed: `924322a` (paket) · `fb72d1d` (runbook) · `c366871` (privasi) · `c308be1` (tanda LLM hidup) |
| Gateway venv di HPC | ya — bisa dihidupkan manual (`apps/ai/.venv`) untuk staging port 8100/8101 |

### 1.3 Jaringan & batasan aktif

- HPC IP **10.5.14.117/23** (Wi-Fi 2, profil Public) — *update 2026-11-05:
  DHCP memberi **10.5.15.9**; masih dalam subnet `10.5.14.0/23`.*
- Firewall rule **"Ollama LLM (RCC AI Gateway)"** — TCP 11434, RemoteIP
  `10.5.14.0/23` (masih subnet luas: seluruh LAN bisa menjangkau 11434).
- **Server platform belum live**; IP server platform **belum diketahui**.
- Windows HPC harus dalam keadaan login agar Ollama hidup (aplikasi user, bukan service).

### 1.4 Yang belum ada (gap menuju Mode B)

- Docker / WSL2 **belum terinstal** di HPC (butuh admin + UAC, mungkin reboot).
- Belum ada folder `deploy-hpc/` (compose + `.env.example`).
- Belum ada rule firewall untuk gateway 8100.
- Belum tahu IP platform server (untuk penyempitan firewall tahap 2).

---

## 2. Ide Mode B — diagram alur

```
Browser (SSO)  →  BFF Express :3000            [server platform / Docker]
                     │  AI_SERVICE_URL = http://10.5.15.9:8100  (IP HPC saat ini; DHCP — cek ipconfig)
                     ▼
     AI Gateway (container Docker di HPC) :8100   ← build dari apps/ai/Dockerfile
                     │  LLM_BASE_URL = host.docker.internal:11434  (tidak lewat LAN)
                     ▼
     Ollama :11434  [HPC]  — tidak lagi ter-expose ke LAN
```

Keputusan inti: **build & jalankan gateway berpindah dari platform ke HPC;
platform hanya menambah 2 kunci env** (`AI_SERVICE_URL`, `SERVICE_KEY`).

## 3. Mode A vs Mode B — perbandingan

| Aspek | Mode A (desain lama, spesifikasi) | Mode B (ide ini) |
|---|---|---|
| Perubahan monorepo | tempel `apps/ai/` + blok compose + build Python di CI | **hanya 2 kunci env** (snippet BFF/frontend tetap ditempel) |
| Tempat build image gateway | server platform (CI/CD) | HPC (build dari repo ini) |
| Ollama ter-expose LAN? | ya — 11434 ke subnet (dipersempit ke IP platform) | **tidak** — hanya internal HPC via NAT Docker WSL2 |
| Jalur trafik | BFF → gateway (platform) → Ollama via LAN | BFF → gateway (HPC, via LAN) → Ollama lokal |
| Debug/iterasi cepat | mudah (compose platform biasa) | butuh `docker compose build` tiap perubahan |
| Operasional | 1 stack compose | + Docker Desktop/WSL2 di HPC |
| Lisensi | — | Docker Desktop gratis <250 karyawan / <$10 M; selain itu Engine-in-WSL2 |

Yang **tidak berubah** pada kedua mode: kontrak SSE (`delta`/`done`/`error`
bersumber gateway; BFF passthrough verbatim; tidak ada API key/URL LLM di
frontend) — hasil acceptance T1–T8 tetap diminta identik.

---

## 4. Rencana implementasi per fase

### Fase 0 — Pre-check & instal Docker Desktop (±30 menit + UAC/reboot)

```powershell
wsl --status                                   # pastikan WSL2 aktif; update kernel bila belum
# unduh installer Docker Desktop (amd64) → D:\Down\docker-desktop-install.exe
# jalankan installer (centang "Use WSL 2 instead of Hyper-V"; restart bila diminta)
docker --version                               # verifikasi
docker run --rm hello-world                    # tes pull + jaringan
```
- Settings: **Start Docker Desktop when you log in = ON** (agar gateway hidup pas boot).
- Catatan lisensi & ketergantungan sesi login (sama halnya dengan tray Ollama).

### Fase 1 — Isi `deploy-hpc/` (paket baru di repo)

- `docker-compose.hpc.yml`:
  - `services.ai`: `build: ../apps/ai`, `ports: "8100:8100"`, `restart: unless-stopped`
  - `extra_hosts: ["host.docker.internal:host-gateway"]`
  - env: `SERVICE_KEY=${SERVICE_KEY}` · `ENVIRONMENT=${ENVIRONMENT:-production}`
    · `LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:11434/v1}`
    · `LLM_MODEL=${LLM_MODEL:-qwen3:30b-a3b}` · `LLM_TIMEOUT=${LLM_TIMEOUT:-120}`
   - healthcheck berbasis **python** — image hasil `apps/ai/Dockerfile` sebenarnya
     sudah memuat curl; healthcheck python dipilih agar tidak bergantung tooling image:
    `test: ["CMD","python","-c","import urllib.request;urllib.request.urlopen('http://localhost:8100/health')"]`
- `.env.example` (`SERVICE_KEY=`, `LLM_MODEL=`, `LLM_TIMEOUT=120`) + tangani `.env` di `.gitignore`.

### Fase 2 — Build, jalankan, verifikasi (±45 menit)

```powershell
cd D:\Gust\ai-service\deploy-hpc
Copy-Item .env.example .env    # isi SERVICE_KEY (sinkron dengan nilai platform nanti!)
docker compose -f docker-compose.hpc.yml up -d --build
docker compose ps              # STATUS healthy
curl.exe -s --noproxy '*' http://127.0.0.1:8100/health        # {"status":"ok"}
curl.exe -s --noproxy '*' http://10.5.15.9:8100/health        # dari mesin lain di LAN → OK (IP cek ipconfig)
```
- Smoke: SSE chat + cek 403 kunci salah terhadap container (client `python httpx` kecil).
- Benchmark: tidak perlu ulang penuh — container memakai Ollama yang sama; angka tetap acuan § 1.1.

### Fase 3 — Firewall (tahap 1 sekarang; tahap 2 saat IP platform diketahui)

Tahap 1 (dijalankan sekali oleh Anda di PowerShell **Admin**):
```powershell
netsh advfirewall firewall add rule name="RCC AI Gateway (:8100)" dir=in action=allow protocol=TCP localport=8100 remoteip=10.5.14.0/23
```
Tahap 2 (menyusul, saat IP platform sudah ada):
```powershell
netsh advfirewall firewall set rule name="RCC AI Gateway (:8100)" new remoteip=<IP-platform>
# 11434 → kunci ke subnet NAT Docker (WSL2) saja, sehingga Ollama tak terlihat LAN:
#   (cek subnet dulu) Get-NetIPConfiguration | Where-Object { $_.InterfaceAlias -like '*WSL*' }
netsh advfirewall firewall set rule name="Ollama LLM (RCC AI Gateway)" new remoteip=<subnet-NAT-Docker>
```

### Fase 4 — Dokumentasi & tooling

- `README-INTEGRASI.md`: tambah seksi **"Mode B — Gateway di HPC"** (platform
  hanya set `AI_SERVICE_URL=http://<IP-HPC>:8100` + `SERVICE_KEY`).
- `RUNBOOK-ai-service.md`: tambah pedoman Mode B (start/stop, `docker logs -f ai`,
  update image, healthcheck, auto-start, troubleshooting Docker/WSL).
- `tools/restrict-firewall.ps1`: tambah mode `-HpcGateway` (set 8100 & 11434 sekaligus).
- Commit + push.

### Fase 5 — Checklist 9.3 (runtime penuh, saat platform hidup)

1. Server platform: `curl http://10.5.15.9:8100/health` → 200 (IP HPC cek ipconfig).
2. BFF env: `AI_SERVICE_URL=http://10.5.15.9:8100`, `SERVICE_KEY` = nilai `.env` HPC.
3. `docker compose up -d backend frontend` (platform **tanpa** service `ai`).
4. Browser → panel Virtual Assistant → chat streaming progresif.
5. Mesin non-whitelist → 8100 & 11434 ditolak.

---

## 5. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Instal WSL2/Docker butuh admin + kemungkinan reboot | jadwalkan jendela waktu; siapkan cadangan waktu 30 menit |
| Lisensi Docker Desktop ( organisasi besar) | gunakan Engine-in-WSL2 gratis; pola Mode B sama |
| Port 8100 baru terbuka | hanya subnet/IP platform; auth `X-Service-Key` tetap wajib |
| Auto-update Ollama (kejadian 0.40.13) | setelah update cek `ollama ps`; container tak bergantung versi (adapter OpenAI-compatible) |
| Subnet NAT Docker bisa berubah | verifikasi via `Get-NetIPConfiguration` sebelum mengetatkan 11434 |
| Single-point di HPC (bertambah) | gateway venv tetap sebagai staging; kembali ke Mode A kapan pun |
| Dua runtime (Ollama + Docker) | pedoman restart di RUNBOOK + healthcheck compose |

## 6. Rollback (bersih)

```powershell
cd D:\Gust\ai-service\deploy-hpc
docker compose -f docker-compose.hpc.yml down
netsh advfirewall firewall delete rule name="RCC AI Gateway (:8100)"
```
- Ollama (11434) & model hangat tetap hidup; Mode A tetap siap ditempel ke
  monorepo bila dipilih; gateway venv tetap tersedia untuk staging.

## 7. Kriteria sukses Mode B

- [ ] `docker compose ps` → `ai` **healthy**
- [ ] `/health` 200 dari: 127.0.0.1 · IP LAN HPC — 2026-11-05 `10.5.15.9` (DHCP) · server platform
- [ ] Chat SSE via container: delta progresif + `done {finish_reason}` + tanpa 5xx
- [ ] `X-Service-Key` salah → 403
- [ ] 11434 tidak terjangkau dari mesin non-whitelist (tahap 2 firewall)
- [ ] Reboot → login → container hidup otomatis + model hangat (preload)
- [ ] Dokumen Mode B tergabung & repo ter-push

## 8. Pra-flight saat eksekusi nanti

- Sesi login HPC aktif (tray Ollama + preload otomatis jalan).
- Disk: D: tersisa ±1,6 TB — cukup (Docker ±2 GB + image ±0,4 GB).
- Ketersediaan UAC (Anda menyetujui installer; netsh tahap 1 dijalankan manual).
- Nilai `SERVICE_KEY` platform yang akan dipakai (atau pakai dev-test dulu).
- Konfirmasi final: Docker Desktop disetujui (kriteria lisensi terpenuhi).
