# Setup LLM Lokal — HP Z8 G4 Workstation (Ollama)

**Status:** Panduan Implementasi
**Versi:** 0.1 (trial — Fase L0)
**Tanggal:** 22 Oktober 2026
**Target hardware:** HP Z8 G4, 2× Xeon Scalable, RAM 256 GB, GPU NVIDIA RTX/Ada 16 GB VRAM, Windows

---

## 1. Ringkasan

Workstation Z8 G4 berperan sebagai **inference server** (runtime LLM) untuk
asisten AI platform RCC. Orkestrasi (policy, routing, tools) tetap di sisi
platform; workstation hanya melayani endpoint OpenAI-compatible yang
dipanggil AI Gateway (`apps/ai`).

Model default trial: **`qwen3:30b-a3b`** — MoE 30B total / 3B aktif,
kualitas kuat untuk Bahasa Indonesia, compute ringan (pas untuk hardware
ini, tidak "over"), dapat di-swap kapan saja via env `LLM_MODEL`.

```
Browser → BFF Express (:3000) → AI Gateway apps/ai (:8100, Docker)
        → http://<IP-Z8G4>:11434/v1  (Ollama di workstation)
```

## 2. Instalasi Ollama (Windows)

1. Unduh installer: <https://ollama.com/download/windows>, lalu instal
   sebagai aplikasi biasa (service Ollama berjalan otomatis).

2. Set variabel environment *machine-level* (PowerShell admin):

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST","0.0.0.0","Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE","-1","Machine")     # model tetap di RAM/VRAM
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS","2","Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL","2","Machine")    # sesuaikan hasil load test
# Opsional: log lebih rinci saat debugging
[Environment]::SetEnvironmentVariable("OLLAMA_DEBUG","1","Machine")
```

3. Restart Ollama lalu verifikasi menerima koneksi di port 11434.

## 3. Model

### 3.1 Model default (trial)

```powershell
ollama pull qwen3:30b-a3b
```

Q4_K_M ≈ 15–18 GB — hampir seluruhnya muat di 16 GB VRAM; beberapa expert
layer otomatis offload ke RAM. Ekspektasi throughput di Z8 G4:
~40–70 tok/s untuk satu stream.

### 3.2 Kandidat upgrade (swap via `LLM_MODEL`, tanpa ubah kode)

| Model | Sumber | Ukuran (Q4) | Catatan |
|---|---|---|---|
| Qwen-SEA-LION-v4.5-27B | GGUF `aisingapore/Qwen-SEA-LION-v4.5-27B-IT-GGUF` + Modelfile | 16.8 GB | Terbaik di Bahasa Indonesia + SEA, 262K ctx, MIT |
| GLM-4.7-Flash 30B-A3B | GGUF `bartowski/zai-org_GLM-4.7-Flash-GGUF` | ≈ 18.5 GB | Reasoning/tool-calling terkuat di kelasnya, MIT |
| Gemma-SEA-LION-v4.5 | GGUF kecil (planner/classifier fase berikutnya) | ~5 GB | Sangat cepat, Indonesian native, MIT |

### 3.3 Modelfile contoh (SEA-LION)

```dockerfile
FROM .\Qwen-SEA-LION-v4.5-27B-IT-Q4_K_M.gguf
PARAMETER temperature 0.7
PARAMETER num_ctx 16384
SYSTEM """Anda adalah asisten AI internal platform Research Control Center (RCC) milik BRIN."""
```

```powershell
ollama create sealion-27b -f .\Modelfile
```

### 3.4 Embedding (fase RAG berikutnya)

```powershell
ollama pull bge-m3
```

## 4. Benchmark singkat (kalibrasi)

```powershell
# Quick test kualitas & latency
ollama run qwen3:30b-a3b "Ringkas kinerja riset Indonesia tahun ini dalam 3 kalimat."

# Lihat tok/s dari log server Ollama
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 50 -Wait
```

Ukur tok/s pada 1 stream; ulangi dengan 2 sesi paralel untuk memastikan
`OLLAMA_NUM_PARALLEL` belum oversubscribe. Catat di tabel berikut:

| Konfigurasi | tok/s (1 stream) | tok/s (2 stream) | VRAM puncak |
|---|---|---|---|
| qwen3:30b-a3b Q4 | 30.3 (192 tok, model warm) | 30.2 / 30.3 per stream (192 tok × 2, bentrok benar-benar paralel) | ≈ 15.3 / 16 GiB (offload parsial; sisanya CPU — masih di atas target 10 tok/s) |

Hasil pengukuran aktual (2026-10-26): driver 582.78 (R580 U11), `OLLAMA_NUM_PARALLEL=2`,
`qwen2.5-coder:14b` ikut diuji: 18.4 tok/s di GPU (dense — lebih lambat dari 30B MoE yang
hanya mengaktifkan ±3 miliar parameter per token). 1-stream flagship 6.8 dtk wall untuk
192 token, 2-stream bertahan ~30 tok/s per stream — `OLLAMA_NUM_PARALLEL=2` tidak
oversubscribe.

## 5. Keamanan & jaringan

1. Port 11434 dibuka **hanya untuk IP server platform** yang menjalankan
   Docker (dan kebutuhan admin lokal). Buat Windows Firewall rule berikut:

```powershell
New-NetFirewallRule -DisplayName "Ollama - RCC Dev Only" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 11434 `
  -RemoteAddress "<IP-server-platform>,<subnet-LAN-workstation>"
```

2. Akses dianggap *service-to-service*: hanya AI Gateway dari platform yang
   diperkenankan; user browser tidak perlu akses langsung ke 11434.
3. `OLLAMA_DEBUG` hanya aktif saat debugging, tidak untuk operasi rutin.
4. Jangan expose port ini lewat NAT/router bila belum dibutuhkan.

## 6. Konfigurasi sisi platform (env; isi nilai aslinya di `.env`, jangan commit)

| Env | Di mana | Contoh nilai |
|---|---|---|
| `LLM_BASE_URL` | root `.env` (docker compose) | `http://<IP-Z8G4>:11434/v1` |
| `LLM_MODEL` | root `.env` | `qwen3:30b-a3b` |
| `AI_SERVICE_URL` | root `.env` | `http://ai:8100` |
| `SERVICE_KEY` | root `.env` | sama di platform & gateway |

## 7. Verifikasi end-to-end

```powershell
# 1. Di workstation — Ollama hidup dan model tersedia:
Invoke-RestMethod http://<IP-Z8G4>:11434/api/tags

# 2. Dari server platform (host Docker):
curl http://<IP-Z8G4>:11434/v1/models

# 3. AI Gateway (dalam jaringan Docker) dan health lewat BFF:
docker compose exec backend wget -qO- http://ai:8100/health
curl http://localhost:3000/api/ai/health/upstream

# 4. Chat streaming end-to-end (browser):
# Buka dashboard RCC → panel Virtual Assistant → kirim pesan → token muncul progresif.
```

## 8. Checklist "beres"

- [x] Ollama terinstal, `OLLAMA_HOST` di-set, restart selesai
- [x] `qwen3:30b-a3b` berhasil di-pull dan menjawab lewat `ollama run`
- [x] Benchmark 1 & 2 stream tercatat di Tabel § 4
- [x] Firewall 11434 hanya mengizinkan IP platform (rule "Ollama LLM (RCC AI Gateway)", RemoteIP 10.5.14.0/23 — untuk RFC1918/endpoint spesifik platform nanti tinggal diganti/ditambah)
- [ ] `docker compose up` — service `ai` healthy
- [ ] `/api/ai/health/upstream` dari BFF → `"available": true`
- [ ] Chat UI streaming token berjalan mulus di browser

## 9. Masalah umum dan penanganan

| Gejala | Penyebab umum | Perbaikan |
|---|---|---|
| `llama-server ... exit status 0xc0000005` / kernel immediate crash saat load model GPU | Driver NVIDIA terlalu tua memuat runtime llama.cpp CUDA (kasus nyata: 536.96/R535) | Perbarui driver minimal R550+; mesin ini lolos setelah **582.78 (R580 U11)** |
| `/v1/models` 404 | Versi Ollama terlalu lama | Perbarui Ollama ke versi terbaru |
| Load model gagal/OOM | VRAM terlalu mepet dengan file besar | Gunakan quant Q4_K_M atau update driver GPU |
| Respon lambat saat 2 chat paralel | `OLLAMA_NUM_PARALLEL` oversubscribe | Turunkan menjadi 1; antrean ditangani BFF |
| Upstream unreachable dari container | IP workstation berubah / firewall | Perbarui `LLM_BASE_URL`, cek firewall rule |
