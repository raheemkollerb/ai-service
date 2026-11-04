# Concept AI --- Arsitektur AI/LLM untuk Platform

**Status:** Dokumen konsep awal\
**Versi:** 1.0\
**Tanggal:** 20 Oktober 2026\
**Bahasa:** Indonesia

------------------------------------------------------------------------

## 1. Ringkasan Eksekutif

Dokumen ini mendefinisikan konsep arsitektur AI/LLM yang dapat
diintegrasikan ke platform digital untuk mendukung analisis data,
penyusunan kesimpulan, asisten berbasis percakapan, pencarian dokumen,
pembuatan laporan, dan integrasi sistem.

Prinsip utama arsitektur:

1.  **Hybrid AI:** menggabungkan LLM lokal dan API LLM eksternal sesuai
    sensitivitas data, kualitas yang diperlukan, biaya, dan kebijakan
    organisasi.
2.  **Security by design:** identitas, otorisasi, klasifikasi data, dan
    kebijakan pemrosesan ditegakkan oleh backend, bukan dipercayakan
    kepada LLM.
3.  **Deterministic analytics first:** angka, agregasi, validasi, dan
    perhitungan bisnis dilakukan oleh database atau layanan analitik;
    LLM membantu memahami permintaan dan menjelaskan hasil.
4.  **RAG untuk pengetahuan internal:** dokumen diambil secara
    kontekstual ketika dibutuhkan, tanpa harus melatih ulang model untuk
    setiap perubahan dokumen.
5.  **AI Gateway sebagai pintu terkontrol:** semua permintaan ke model
    melewati lapisan yang menangani routing, kebijakan, observabilitas,
    pembatasan penggunaan, dan adapter provider.
6.  **Least privilege:** model hanya menerima konteks minimum yang
    dibutuhkan dan hanya dapat memanggil tools yang secara eksplisit
    diizinkan.
7.  **Evaluasi sebelum perluasan:** kualitas, keamanan, latensi, biaya,
    dan ketepatan sumber diukur sebelum fitur AI digunakan secara luas.

Tujuan awal bukan membangun model fondasi sendiri. Tujuan awal adalah
mengintegrasikan model yang tersedia secara aman, menghubungkannya
dengan data internal melalui API dan RAG, lalu mengevaluasi kebutuhan
self-hosted atau fine-tuning berdasarkan hasil nyata.

## 2. Latar Belakang dan Tujuan

Platform modern dapat menggunakan AI untuk:

-   Menjawab pertanyaan pengguna dengan konteks platform.
-   Menganalisis data terstruktur dari database.
-   Menjelaskan tren, perbandingan, anomali, dan indikator.
-   Mencari serta merangkum dokumen.
-   Membuat draf laporan, ringkasan, dan rekomendasi.
-   Membantu pengguna menemukan fitur dan informasi.
-   Mengorkestrasi workflow melalui tools atau integrasi yang
    dikendalikan backend.

Namun, integrasi AI juga menimbulkan risiko: kebocoran data, akses
lintas organisasi, jawaban keliru, prompt injection, pemanggilan tools
yang tidak sah, biaya yang tidak terkendali, dan ketergantungan kepada
provider.

### 2.1 Tujuan

-   Menetapkan arsitektur AI yang modular dan dapat dikembangkan
    bertahap.
-   Memisahkan keamanan, perencanaan tugas, routing model, retrieval,
    dan analitik.
-   Menetapkan pembagian kerja LLM lokal, LLM eksternal, RAG, dan
    layanan analitik.
-   Menetapkan kontrol untuk database, dokumen, storage, dan integrasi
    platform lain.
-   Menjadi dasar implementasi teknis, evaluasi, deployment, dan tata
    kelola AI.

### 2.2 Di luar cakupan awal

Versi awal tidak bertujuan untuk:

-   Melatih foundation model dari nol.
-   Memberikan akses bebas kepada LLM ke seluruh database atau sistem.
-   Mengizinkan agent melakukan tindakan berisiko tinggi tanpa
    persetujuan.
-   Menganggap jawaban AI sebagai keputusan resmi tanpa verifikasi.
-   Menggunakan fine-tuning sebagai pengganti kontrol akses atau RAG.

## 3. Prinsip Desain

### 3.1 Model bukan sumber kebenaran data

Sumber kebenaran tetap berada pada database, dokumen resmi, dan sistem
bisnis yang ditetapkan. LLM bertugas memahami, merangkum, menjelaskan,
dan membantu menyusun hasil berdasarkan sumber tersebut.

### 3.2 Pemisahan tugas

Setiap komponen mempunyai tanggung jawab khusus:

-   **Database / Analytics Service:** query, agregasi, statistik,
    perhitungan, dan validasi.
-   **RAG:** menemukan bagian dokumen yang relevan.
-   **LLM:** memahami bahasa, menyusun rencana, merangkum, menjelaskan,
    dan menghasilkan respons.
-   **Policy Engine:** memutuskan akses serta batas pemrosesan yang
    diizinkan.
-   **Task Planner:** mengubah permintaan menjadi rencana tugas yang
    terstruktur.
-   **AI Router:** memilih jalur eksekusi dan model dari opsi yang
    diizinkan.
-   **AI Gateway:** menjadi pintu terkontrol untuk orkestrasi dan
    koneksi model.

### 3.3 Keamanan tidak diputuskan oleh LLM

LLM dapat mengusulkan intent, tools, atau rencana, tetapi tidak boleh
memberikan otorisasi kepada dirinya sendiri. Policy Engine dan backend
harus memvalidasi setiap sumber data, operasi, dan tujuan pemrosesan.

### 3.4 Data minimum

Kirimkan hanya data yang diperlukan. Bila analisis dapat dilakukan
dengan agregasi, jangan mengirim baris mentah atau identitas personal
yang tidak diperlukan.

### 3.5 Modular dan provider-agnostic

Fitur platform tidak boleh bergantung langsung pada format API satu
provider. Gunakan adapter agar provider, model, atau runtime dapat
diganti dengan perubahan minimal.

### 3.6 Human oversight

Tindakan yang berdampak pada data, hak akses, persetujuan, transaksi,
atau komunikasi eksternal memerlukan aturan khusus dan, bila sesuai,
persetujuan manusia.

## 4. Istilah dan Komponen

### 4.1 LLM

Large Language Model adalah model yang memproses bahasa untuk menjawab
pertanyaan, meringkas, menalar, dan menghasilkan teks atau struktur
data. Model tidak otomatis mengetahui isi database internal atau data
terbaru.

### 4.2 LLM lokal / self-hosted

Model dijalankan pada server atau lingkungan yang dikelola organisasi.
Contoh runtime yang dapat dievaluasi adalah Ollama untuk prototipe dan
vLLM untuk serving dengan kebutuhan throughput lebih tinggi. Model dan
lisensinya harus diperiksa sebelum digunakan.

Self-hosted memberikan kontrol lebih besar atas lokasi pemrosesan,
tetapi tidak otomatis aman. Jaringan, log, akses server, model, dan
pipeline tetap harus diamankan.

### 4.3 LLM eksternal

Model diakses melalui API penyedia. Kelebihannya adalah kemudahan
integrasi dan akses ke model yang dikelola penyedia. Sebelum data
dikirim, organisasi harus meninjau ketentuan penggunaan, retensi, lokasi
pemrosesan, kontrol data, kontrak, dan klasifikasi data yang diizinkan.

Tidak digunakan untuk training secara default bukan berarti data pasti
tidak disimpan. Retensi log, state aplikasi, dan pemantauan
penyalahgunaan perlu ditinjau secara terpisah.

### 4.4 RAG

Retrieval-Augmented Generation adalah pipeline yang mencari informasi
relevan dari sumber eksternal terhadap model---misalnya dokumen
internal---dan memberikan hasil pencarian itu sebagai konteks untuk LLM.
RAG bukan model LLM dan bukan jaminan keamanan.

### 4.5 Embedding

Model embedding mengubah teks menjadi representasi vektor agar sistem
dapat melakukan pencarian berdasarkan kemiripan semantik. Embedding dan
indeks vektor tetap dapat membawa informasi sensitif sehingga harus
dilindungi.

### 4.6 Tool calling

Mekanisme agar model meminta aplikasi menjalankan fungsi yang sudah
disediakan, misalnya mengambil statistik, mencari dokumen, atau membuat
draf laporan. Backend tetap memvalidasi nama tool, parameter, izin, dan
dampak tindakan.

### 4.7 Fine-tuning

Pelatihan lanjutan terhadap model menggunakan contoh khusus.
Dipertimbangkan untuk kebutuhan perilaku atau format yang konsisten jika
prompt dan RAG tidak cukup. Fine-tuning bukan metode utama untuk
memasukkan data yang terus berubah atau mengamankan data.

## 5. Arsitektur Tingkat Tinggi

``` mermaid
flowchart TD
    U[Pengguna / Frontend] --> API[Backend API dan autentikasi]
    API --> GW[AI Gateway / Orchestrator]
    GW --> CTX[Request dan Context Resolver]
    CTX --> PLAN[Task Planner]
    PLAN --> POLICY[Policy Engine]
    POLICY -->|Ditolak| DENY[Penolakan / klarifikasi]
    POLICY -->|Diizinkan| ROUTER[AI Router]
    ROUTER --> ANALYTICS[Analytics API / SQL terkontrol]
    ROUTER --> RAG[RAG Pipeline]
    ROUTER --> LOCAL[LLM lokal]
    ROUTER --> EXT[LLM eksternal jika diizinkan]
    ANALYTICS --> VALID[Validasi hasil dan sumber]
    RAG --> LOCAL
    RAG --> EXT
    LOCAL --> VALID
    EXT --> VALID
    VALID --> AUDIT[Audit dan observabilitas aman]
    AUDIT --> RESP[Respons ke pengguna]
```

Diagram tersebut menggambarkan tanggung jawab logis, bukan keharusan
setiap permintaan melewati semua komponen. Jalur aktual dipilih sesuai
kebutuhan tugas dan kebijakan.

### 5.1 Komponen utama

1.  **Frontend:** antarmuka chat, analisis, sumber, status proses,
    persetujuan, dan feedback.
2.  **Backend API:** autentikasi, session, RBAC/ABAC, rate limit, dan
    API platform.
3.  **AI Gateway:** antarmuka tunggal untuk model, routing, konfigurasi,
    kontrol konteks, dan metrik.
4.  **Request & Context Resolver:** mengumpulkan identitas
    terverifikasi, fitur, permintaan, dan sumber yang berpotensi
    dibutuhkan.
5.  **Task Planner:** membuat rencana kerja dari pertanyaan. Dapat
    berupa aturan, kode, atau dibantu LLM lokal.
6.  **Policy Engine:** menentukan apakah pengguna boleh mengakses sumber
    dan apakah konteks boleh diproses pada jalur tertentu.
7.  **AI Router:** memilih analytics, RAG, LLM lokal, atau LLM eksternal
    dari jalur yang telah diizinkan.
8.  **Analytics Service:** menjalankan query dan perhitungan terkontrol.
9.  **RAG Service:** ingest, indeks, retrieval, reranking opsional, dan
    pengelolaan sumber.
10. **Model adapters:** menghubungkan sistem ke provider eksternal atau
    runtime lokal.
11. **Validation & Audit:** memeriksa output, sumber, kebijakan, serta
    mencatat metadata aktivitas yang dibutuhkan.

## 6. Pembagian Tugas: Analytics, RAG, LLM Lokal, dan LLM Eksternal

### 6.1 Database dan Analytics Service

Gunakan database atau service analitik untuk:

-   Jumlah, total, rata-rata, rasio, dan agregasi.
-   Perbandingan periode dan organisasi.
-   Penghitungan indikator kinerja.
-   Filter berdasarkan rentang tanggal, status, dan kategori.
-   Validasi data, aturan bisnis, serta pemeriksaan konsistensi.
-   Prediksi numerik yang sebaiknya dikerjakan model statistik atau
    machine learning khusus.

LLM boleh mengusulkan fungsi analitik yang diperlukan, tetapi parameter
dan query harus divalidasi backend. Hindari memberi LLM akses bebas
untuk mengeksekusi SQL arbitrer.

### 6.2 RAG internal

Gunakan RAG untuk pengetahuan yang tersimpan dalam dokumen atau sumber
teks, seperti:

-   SOP, pedoman, dan kebijakan.
-   Laporan, proposal, publikasi, dan dokumen teknis.
-   Dokumentasi sistem dan panduan pengguna.
-   Catatan atau knowledge base yang hak aksesnya jelas.
-   Informasi yang berubah dari waktu ke waktu dan tidak cocok ditanam
    permanen dalam bobot model.

RAG sebaiknya menghasilkan referensi sumber dan, jika memungkinkan,
halaman, bagian, atau ID dokumen. Jika bukti yang ditemukan tidak cukup,
sistem harus mengakui keterbatasan atau meminta klarifikasi.

### 6.3 LLM lokal

Jadikan jalur lokal sebagai default untuk konteks yang wajib tetap di
lingkungan internal, sesuai klasifikasi dan kebijakan organisasi.
Kandidat tugas:

-   Tanya jawab atas dokumen rahasia melalui RAG.
-   Ringkasan laporan internal.
-   Klasifikasi dan ekstraksi dokumen.
-   Penyusunan temuan awal dari hasil analitik internal.
-   Pemrosesan batch yang rutin dan telah lulus evaluasi kualitas.
-   Perencanaan tugas internal jika local planner cukup akurat.

Kesesuaian model lokal harus diuji terhadap kualitas Bahasa Indonesia,
ketepatan sumber, konteks panjang, latensi, RAM/VRAM, throughput, dan
lisensi.

### 6.4 LLM eksternal

Gunakan sebagai lapisan kemampuan tambahan untuk tugas yang memberikan
manfaat nyata dan konteksnya diizinkan, misalnya:

-   Sintesis atau penalaran yang lebih kompleks.
-   Penyusunan laporan dengan struktur yang lebih baik.
-   Brainstorming umum tanpa data sensitif.
-   Analisis atas agregat atau data yang telah disetujui untuk diproses
    eksternal.
-   Perbandingan beberapa alternatif atau penyusunan draf berdasarkan
    konteks yang sudah disanitasi.

LLM eksternal bukan tujuan akhir dari routing. Jika model lokal atau
service deterministik cukup, tidak perlu memanggil model eksternal.

### 6.5 Hybrid per tugas

Satu permintaan dapat terdiri dari beberapa subtugas. Misalnya:

1.  Analytics Service menghitung statistik internal.
2.  RAG mencari dokumen pendukung yang boleh diakses.
3.  LLM lokal menyusun temuan dari sumber internal.
4.  Jika kebijakan mengizinkan, ringkasan agregat yang disetujui dapat
    dikirim ke LLM eksternal untuk sintesis tambahan.
5.  Sistem memvalidasi kembali angka, referensi, dan batas pengungkapan.

Tidak semua permintaan perlu melewati kedua LLM. Setiap pemanggilan
eksternal menambah biaya, latensi, dan risiko data.

## 7. RAG Pipeline secara Detail

### 7.1 Ingestion

Sumber dokumen dapat berasal dari object storage, file upload,
repositori internal, atau sistem lain yang secara eksplisit diizinkan.

Tahapan:

1.  Verifikasi sumber dan hak akses.
2.  Validasi tipe file, ukuran, dan keamanan file.
3.  Ekstraksi teks dan metadata.
4.  OCR bila dokumen berupa hasil pemindaian.
5.  Normalisasi teks.
6.  Chunking berdasarkan struktur dokumen.
7.  Simpan metadata sumber, klasifikasi, pemilik, ACL, versi, dan status
    dokumen.
8.  Buat embedding dan indeks pencarian.
9.  Catat status proses serta penanganan kegagalan.

Dokumen yang diperbarui atau dicabut aksesnya harus memperbarui indeks.
Penghapusan atau pencabutan akses perlu mencakup indeks, cache, dan
salinan turunan sesuai kebijakan retensi.

### 7.2 Chunking dan metadata

Hindari chunking hanya berdasarkan jumlah karakter bila struktur dokumen
penting. Pertimbangkan judul, bagian, paragraf, tabel, halaman, dan
hubungan antarbab.

Metadata minimal yang dapat dipertimbangkan:

-   `document_id`
-   `source_id`
-   `title`
-   `page_number` atau penanda bagian
-   `organization_id` atau cakupan tenant
-   `classification`
-   `acl` atau referensi ke sistem izin
-   `version`
-   `updated_at`
-   `ingestion_status`

Jangan menyimpan daftar ACL yang tidak pernah diperbarui lalu
menganggapnya sebagai sumber kebenaran. Untuk akses sensitif, otorisasi
harus divalidasi terhadap sistem izin yang berlaku.

### 7.3 Embedding dan vector store

Pilihan awal yang disarankan:

-   Model embedding lokal yang mendukung bahasa dan jenis dokumen yang
    digunakan.
-   PostgreSQL + pgvector untuk mengurangi kompleksitas infrastruktur
    awal.
-   Full-text search untuk kata kunci, istilah teknis, kode, dan nama
    yang harus dicocokkan persis.
-   Hybrid search yang menggabungkan pencarian kata kunci dan vektor.
-   Reranker lokal bila evaluasi menunjukkan peningkatan relevansi yang
    berarti.

BGE-M3 dapat menjadi kandidat uji untuk kebutuhan multilingual, tetapi
tidak boleh dipilih tanpa evaluasi pada korpus nyata. Model embedding
harus konsisten antara proses indexing dan query.

### 7.4 Retrieval dan pembentukan konteks

1.  Autentikasi pengguna.
2.  Tentukan sumber yang mungkin dibutuhkan.
3.  Terapkan filter akses sebelum hasil dikirim ke model.
4.  Cari kandidat dokumen.
5.  Rerank jika diperlukan.
6.  Batasi jumlah dan ukuran potongan.
7.  Validasi kembali hak akses dokumen.
8.  Susun konteks beserta metadata sumber.
9.  Kirim konteks hanya ke model yang diizinkan.
10. Validasi sumber pada respons akhir.

Jangan mengambil dokumen tanpa filter lalu berharap LLM mengabaikan
bagian yang tidak boleh dibaca pengguna.

### 7.5 Jawaban berbasis sumber

Respons RAG sebaiknya:

-   Menyertakan nama dokumen dan halaman atau bagian jika tersedia.
-   Membedakan fakta sumber dengan interpretasi model.
-   Tidak mengarang kutipan atau referensi.
-   Menyatakan jika sumber tidak cukup atau bertentangan.
-   Menghindari pengungkapan bagian sumber yang tidak boleh ditampilkan.

### 7.6 Keamanan RAG

-   Dokumen dianggap sebagai data tidak tepercaya, bukan instruksi
    sistem.
-   Uji prompt injection yang tertanam dalam dokumen.
-   Pisahkan indeks atau terapkan filter tenant/organisasi secara
    konsisten.
-   Lindungi embedding, metadata, cache, dan log.
-   Batasi akses service account ke sumber dokumen.
-   Validasi ulang izin saat dokumen diperbarui atau pengguna kehilangan
    akses.
-   Jangan mengirim dokumen sensitif ke layanan embedding eksternal
    tanpa persetujuan kebijakan.

## 8. Policy Engine, Task Planner, dan AI Router

Ketiga komponen ini harus dipisahkan secara konseptual, meskipun dapat
diimplementasikan dalam satu service pada tahap awal.

### 8.1 Policy Engine

Tanggung jawab:

-   Memastikan identitas berasal dari sesi atau token yang
    terverifikasi.
-   Memeriksa role, organisasi, tenant, dan hak akses spesifik.
-   Memeriksa klasifikasi sumber data.
-   Menentukan apakah data boleh diproses lokal, eksternal, atau tidak
    boleh diproses oleh AI.
-   Menentukan tujuan pemrosesan yang diperbolehkan.
-   Menegakkan batas data yang dapat dikirim.
-   Menolak permintaan yang melanggar kebijakan.
-   Menentukan kebutuhan persetujuan untuk tindakan tertentu.

Policy Engine harus bersifat deterministik, dapat diuji, dan dapat
diaudit. LLM tidak boleh mengubah atau mengesampingkan hasil kebijakan.

### 8.2 Task Planner

Tanggung jawab:

-   Mengidentifikasi intent pengguna.
-   Memecah pertanyaan kompleks menjadi subtugas.
-   Mengusulkan jenis sumber yang dibutuhkan.
-   Memilih kandidat tools dari daftar yang diizinkan.
-   Meminta klarifikasi bila permintaan ambigu.
-   Menghasilkan rencana terstruktur yang dapat divalidasi.

Pendekatan awal:

1.  Gunakan aturan untuk intent yang sederhana dan umum.
2.  Tambahkan local LLM planner untuk pertanyaan bebas atau
    multi-langkah.
3.  Validasi output dengan schema yang ketat.
4.  Batasi tools melalui allowlist.
5.  Jangan menganggap rencana dari LLM sebagai izin untuk mengakses
    data.

LLM eksternal tidak diperlukan hanya untuk melakukan klasifikasi intent.

### 8.3 AI Router

Tanggung jawab:

-   Memilih analytics API, RAG, local LLM, atau external LLM.
-   Memilih model dari daftar yang telah disetujui.
-   Mempertimbangkan klasifikasi data, tugas, kualitas, latensi,
    ketersediaan, dan biaya.
-   Menggunakan fallback hanya jika jalur fallback juga diizinkan.
-   Mencatat alasan routing dalam bentuk metadata yang aman.

Router tidak boleh mengirim data ke model eksternal hanya karena model
lokal gagal. Kegagalan harus berakhir pada retry yang aman, jalur
alternatif yang diizinkan, atau pesan keterbatasan.

### 8.4 Pemeriksaan kebijakan berlapis

Lakukan pemeriksaan pada beberapa titik:

1.  Sebelum retrieval atau pemanggilan tools.
2.  Saat mengambil setiap sumber data.
3.  Setelah konteks aktual terbentuk, sebelum dikirim ke LLM eksternal.
4.  Sebelum tindakan eksternal atau perubahan data dilakukan.
5.  Sebelum respons yang berpotensi sensitif ditampilkan.

Klasifikasi data hasil gabungan harus mempertimbangkan semua sumber yang
berkontribusi. Data agregat pun dapat sensitif jika memungkinkan
identifikasi ulang.

## 9. Alur Pemrosesan Permintaan

``` mermaid
flowchart TD
    A[Pertanyaan pengguna] --> B[Autentikasi dan identitas terverifikasi]
    B --> C[Intent rules / Task Planner]
    C --> D[Validasi rencana dan tools]
    D --> E[Policy check untuk sumber dan operasi]
    E -->|Tidak diizinkan| X[Tolak atau minta klarifikasi]
    E -->|Diizinkan| F[Analytics / Retrieval / Tools]
    F --> G[Klasifikasi konteks aktual]
    G --> H{Jalur pemrosesan diizinkan?}
    H -->|Internal saja| I[LLM lokal]
    H -->|Eksternal diizinkan dan bermanfaat| J[Redaksi dan minimisasi konteks]
    J --> K[LLM eksternal]
    H -->|Perhitungan deterministik| L[Analytics API]
    I --> M[Validasi output dan sumber]
    K --> M
    L --> M
    M --> N[Audit aman dan respons]
```

### 9.1 Contoh: pertanyaan statistik

Pertanyaan: "Berapa jumlah proyek aktif tiap organisasi tahun ini?"

-   Planner mengenali kebutuhan analitik.
-   Policy Engine memeriksa akses organisasi dan periode.
-   Analytics API menjalankan query terkontrol.
-   Hasil numerik dikembalikan.
-   LLM lokal atau eksternal hanya digunakan jika pengguna meminta
    penjelasan atau interpretasi tambahan.
-   Respons menyebut periode, definisi proyek aktif, dan waktu data
    diperbarui bila tersedia.

### 9.2 Contoh: pertanyaan dokumen rahasia

Pertanyaan: "Ringkas laporan evaluasi internal ini."

-   Backend memeriksa akses terhadap laporan.
-   RAG mencari bagian relevan dari dokumen.
-   Policy Engine menetapkan jalur internal.
-   LLM lokal menyusun ringkasan dan referensi.
-   Tidak ada fallback ke eksternal tanpa izin kebijakan.
-   Respons diperiksa sebelum ditampilkan.

### 9.3 Contoh: analisis kompleks hybrid

Pertanyaan: "Bandingkan produktivitas tiga organisasi dan susun
rekomendasi."

-   Analytics API menghitung indikator yang terdefinisi.
-   RAG mencari dokumen pendukung yang boleh diakses.
-   LLM lokal menyusun temuan awal jika sumber bersifat internal.
-   Sistem menilai apakah ringkasan agregat dapat dikirim ke eksternal.
-   Jika diizinkan, LLM eksternal membantu sintesis; jika tidak, seluruh
    proses tetap internal.
-   Hasil akhir divalidasi terhadap angka dan sumber.

## 10. Kebijakan Klasifikasi Data

Klasifikasi final harus mengikuti kebijakan organisasi. Contoh kategori
konseptual:

  -----------------------------------------------------------------------
  Kategori                Contoh                  Jalur default
  ----------------------- ----------------------- -----------------------
  Publik                  Informasi yang memang   Eksternal atau lokal
                          telah dipublikasikan    sesuai kebutuhan

  Internal                Informasi operasional   Internal-first;
                          nonpublik               eksternal hanya jika
                                                  kebijakan mengizinkan

  Rahasia                 Laporan atau data       Lokal-only secara
                          terbatas                default

  Sangat sensitif /       Data yang dilarang      Hanya jalur yang secara
  restricted              keluar atau memiliki    eksplisit diizinkan;
                          persyaratan khusus      jika tidak ada, tolak
  -----------------------------------------------------------------------

Kategori di atas bukan pengganti klasifikasi resmi organisasi.

Kontrol penting:

-   Jangan mengandalkan label yang diberikan pengguna tanpa validasi.
-   Gunakan metadata sumber yang dikelola sistem.
-   Terapkan aturan untuk data gabungan dan hasil turunan.
-   Redaksi atau anonimisasi bukan jaminan data aman; risiko
    identifikasi ulang harus dinilai.
-   Jika klasifikasi tidak diketahui, gunakan jalur konservatif sampai
    klasifikasi ditentukan.
-   Simpan aturan provider yang disetujui dan tanggal peninjauannya.

## 11. Keamanan dan Privasi

### 11.1 Kontrol aplikasi

-   API key hanya di backend atau secret manager.
-   Autentikasi dan otorisasi server-side.
-   RBAC dan, jika diperlukan, ABAC berbasis organisasi, tenant, dan
    atribut data.
-   Rate limit dan kuota per pengguna atau organisasi.
-   Validasi skema untuk output planner dan tool calling.
-   Parameterized query serta service account dengan izin minimum.
-   Pembatasan ukuran input, konteks, dan output.
-   Proteksi terhadap akses lintas tenant.

### 11.2 Kontrol model dan provider

-   Tinjau ketentuan penggunaan data, retensi, lokasi pemrosesan,
    subprocessor, dan kontrol organisasi.
-   Gunakan layanan atau kontrak yang disetujui untuk klasifikasi data
    terkait.
-   Jangan menyertakan informasi identitas atau rahasia yang tidak
    diperlukan.
-   Jangan menganggap "tidak digunakan untuk training" berarti "tidak
    pernah disimpan".
-   Tetapkan timeout, batas biaya, dan kebijakan retry.
-   Pisahkan kredensial setiap lingkungan.

### 11.3 Prompt injection dan output tidak aman

-   Perlakukan dokumen, hasil retrieval, web content, dan output tools
    sebagai data tidak tepercaya.
-   Instruksi dari dokumen tidak boleh mengubah kebijakan sistem.
-   Jangan memasukkan secret ke prompt.
-   Batasi tool allowlist dan parameter yang diterima.
-   Validasi output sebelum digunakan dalam query, HTML, kode, atau
    tindakan.
-   Untuk tindakan yang berdampak, gunakan persetujuan eksplisit dan
    audit.
-   Jangan izinkan model memanggil tools berulang tanpa batas.

### 11.4 Logging dan audit

Catat seperlunya:

-   ID permintaan dan waktu.
-   ID pengguna atau pseudonim audit yang sesuai kebijakan.
-   Model/provider dan versi.
-   Jenis tugas dan jalur routing.
-   Tools yang dipanggil dan statusnya.
-   Referensi sumber yang digunakan.
-   Token, latensi, biaya, dan status error.
-   Hasil pemeriksaan kebijakan dan alasan penolakan dalam bentuk yang
    aman.

Hindari menyimpan isi prompt, jawaban, atau dokumen sensitif secara utuh
tanpa kebutuhan yang sah, kontrol akses, dan retensi yang jelas. Log
juga harus dilindungi dari akses tidak sah.

### 11.5 Infrastruktur lokal

Untuk model lokal:

-   Pisahkan jaringan model dari akses langsung ke database utama.
-   Sediakan endpoint internal dan autentikasi service-to-service.
-   Batasi egress jaringan sesuai kebutuhan.
-   Amankan runtime, model artifacts, container, dan host.
-   Monitor resource, antrean, dan error.
-   Lindungi cache dan vector store.
-   Uji bahwa data tidak dikirim ke layanan eksternal yang tidak
    disetujui.

## 12. Rekomendasi Stack Teknologi Awal

Pilihan ini merupakan baseline yang dapat disesuaikan, bukan keharusan
memakai semua komponen sekaligus.

  -----------------------------------------------------------------------
  Lapisan                 Kandidat                Peran
  ----------------------- ----------------------- -----------------------
  Frontend                React + TypeScript      Chat, analisis, sumber,
                                                  persetujuan, feedback

  Backend / AI Gateway    Node.js + Express       Auth, routing, policy
                                                  integration, provider
                                                  adapter, rate limit

  Analytics Service       Python + FastAPI        Statistik, perhitungan,
                                                  query analitik, data
                                                  processing

  Database                PostgreSQL              Data platform dan
                                                  metadata

  Vector search           pgvector + PostgreSQL   Retrieval semantik dan
                          full-text search        kata kunci

  Document processing     Python + PyMuPDF, OCR   Ekstraksi dan
                          bila perlu              normalisasi dokumen

  Embedding               Model multilingual      Indeks semantik tanpa
                          lokal                   pengiriman teks ke
                                                  layanan embedding
                                                  eksternal

  Local inference         Ollama untuk prototipe; Menjalankan LLM lokal
                          vLLM untuk serving yang 
                          sesuai                  

  Cache / queue           Redis bila dibutuhkan   Cache aman, rate
                                                  limiting, antrean atau
                                                  status pekerjaan

  Observability           Logging, metrics,       Latensi, error, biaya,
                          tracing yang sesuai     dan health
                          stack                   

  Secret management       Secret manager atau     Melindungi API key dan
                          mekanisme secret        kredensial
                          deployment              
  -----------------------------------------------------------------------

### 12.1 Catatan pemilihan teknologi

-   Mulai dengan satu provider eksternal, bukan banyak provider
    sekaligus.
-   Pilih satu model lokal untuk proof of concept berdasarkan hardware
    dan evaluasi.
-   Jangan menambahkan vector database terpisah sebelum PostgreSQL +
    pgvector terbukti tidak cukup.
-   Pilih embedding berdasarkan benchmark Bahasa Indonesia dan karakter
    dokumen.
-   Fine-tuning bukan prioritas sebelum ada baseline evaluasi yang
    menunjukkan kebutuhan.
-   Hindari ketergantungan pada satu provider melalui adapter internal
    yang konsisten.

## 13. Pemilihan Model dan Evaluasi

Jangan menentukan model hanya berdasarkan benchmark umum atau harga.
Buat kumpulan kasus uji dari tugas nyata yang telah disanitasi.

### 13.1 Dimensi evaluasi

-   Akurasi jawaban.
-   Ketepatan sumber dan sitasi.
-   Kemampuan Bahasa Indonesia.
-   Kepatuhan terhadap instruksi dan format.
-   Kualitas tool calling.
-   Ketahanan terhadap prompt injection.
-   Tingkat penolakan yang tepat.
-   Latensi p50/p95.
-   Token atau biaya per tugas.
-   Kebutuhan RAM/VRAM dan throughput untuk model lokal.
-   Konsistensi hasil dan tingkat kegagalan.

### 13.2 Evaluasi RAG

Uji secara terpisah:

-   Apakah dokumen yang benar ditemukan?
-   Apakah bagian yang relevan muncul di peringkat atas?
-   Apakah jawaban didukung oleh sumber yang diambil?
-   Apakah sitasi tepat?
-   Apakah sistem menolak menjawab saat bukti tidak cukup?
-   Apakah filter izin bekerja untuk setiap organisasi dan pengguna?
-   Apakah dokumen yang dicabut aksesnya tidak lagi dapat ditemukan?

### 13.3 Evaluasi routing

-   Apakah tugas analitik diarahkan ke Analytics Service?
-   Apakah dokumen rahasia tetap pada jalur internal?
-   Apakah provider eksternal hanya dipakai saat diizinkan?
-   Apakah fallback tetap mematuhi kebijakan?
-   Apakah planner mengusulkan tools yang benar?
-   Apakah kebijakan tetap ditegakkan ketika prompt meminta untuk
    mengabaikannya?

Tetapkan ambang penerimaan sebelum produksi dan lakukan regression
testing setiap kali model, prompt, embedding, retrieval, atau policy
berubah.

## 14. Biaya, Performa, dan Skalabilitas

Total biaya bukan hanya biaya token. Hitung:

-   Input dan output token API.
-   Embedding dan reranking.
-   Infrastruktur inferensi lokal.
-   CPU, RAM, GPU/VRAM, listrik, dan storage.
-   Pemrosesan dokumen.
-   Database, cache, dan backup.
-   Monitoring, keamanan, serta waktu pemeliharaan.
-   Retry, permintaan gagal, dan penggunaan yang tidak efisien.

Kontrol biaya:

-   Batas token input/output.
-   Maksimum dokumen dan chunk yang diambil.
-   Rate limit dan kuota per pengguna.
-   Cache hanya untuk data yang aman dan masih valid.
-   Batasi retry dan timeout.
-   Gunakan model lebih ringan untuk tugas sederhana jika kualitasnya
    memadai.
-   Monitor biaya per fitur dan per organisasi.
-   Hindari mengirim seluruh riwayat percakapan atau dokumen tanpa
    kebutuhan.

Untuk deployment lokal, lakukan load test dengan concurrency yang
realistis. Satu model yang baik untuk satu pengguna belum tentu memenuhi
kebutuhan banyak pengguna bersamaan.

## 15. Fallback dan Penanganan Kegagalan

-   **Model lokal tidak tersedia:** gunakan antrean atau pesan
    sementara; jangan otomatis mengirim data ke eksternal jika kebijakan
    tidak mengizinkan.
-   **Provider eksternal gagal:** retry terbatas, gunakan provider
    alternatif hanya jika sudah disetujui, atau kembalikan respons yang
    aman.
-   **RAG tidak menemukan bukti:** minta klarifikasi atau nyatakan bahwa
    sumber tidak cukup.
-   **Analytics API gagal:** jangan mengarang angka; jelaskan bahwa data
    tidak dapat diambil.
-   **Policy Engine gagal atau tidak dapat menentukan izin:** fail
    closed untuk data sensitif.
-   **Output tidak valid:** validasi ulang secara terbatas atau tolak
    output.
-   **Tindakan berisiko:** hentikan sampai persetujuan dan validasi yang
    diperlukan tersedia.

## 16. Agent dan Integrasi Eksternal

Mulai dari assistant dengan tools terbatas. Agent yang mampu menjalankan
banyak langkah baru ditambahkan setelah kontrol dan evaluasi tersedia.

Setiap tool harus memiliki:

-   Nama dan deskripsi yang jelas.
-   Skema parameter yang tervalidasi.
-   Pemeriksaan otorisasi di backend.
-   Batas timeout dan penggunaan.
-   Kebijakan idempotensi untuk operasi yang dapat diulang.
-   Logging dan hasil yang dapat diaudit.
-   Klasifikasi input dan output.
-   Persyaratan persetujuan manusia untuk operasi berisiko.

Contoh tools yang relatif aman untuk tahap awal:

-   `get_publication_statistics`
-   `search_authorized_documents`
-   `get_project_summary`
-   `draft_report`

Contoh operasi yang memerlukan kontrol lebih tinggi:

-   Mengubah data master.
-   Menghapus dokumen.
-   Mengubah role atau izin.
-   Menyetujui transaksi atau permohonan.
-   Mengirim email atau dokumen ke pihak eksternal.

Nama di atas merupakan contoh konseptual, bukan API yang sudah tersedia.

## 17. Tahapan Implementasi

### Tahap 0 --- Discovery dan klasifikasi

-   Tentukan platform dan pengguna sasaran.
-   Petakan database, storage, API, dan integrasi.
-   Klasifikasikan data dan tentukan sumber kebenaran.
-   Tetapkan kebijakan penggunaan provider eksternal.
-   Pilih use case awal dan kriteria keberhasilan.

**Output:** inventaris data, matriks sensitivitas, use case, dan aturan
pemrosesan.

### Tahap 1 --- AI Assistant dasar

-   Integrasikan satu provider eksternal melalui backend.
-   Bangun AI Gateway dan adapter model.
-   Terapkan autentikasi, rate limit, secret management, dan logging
    aman.
-   Gunakan data sintetis atau publik saat pengembangan.
-   Siapkan test set awal.

**Output:** assistant dasar dengan batas penggunaan yang jelas.

### Tahap 2 --- Analytics tools

-   Definisikan katalog fungsi analitik.
-   Terapkan query parameterized dan hak akses per organisasi.
-   Pisahkan perhitungan dari narasi LLM.
-   Tampilkan periode, definisi indikator, dan sumber angka.

**Output:** AI yang dapat menjelaskan data platform secara terukur.

### Tahap 3 --- RAG internal

-   Implementasikan ingestion dan ekstraksi dokumen.
-   Uji embedding multilingual.
-   Bangun vector search dan full-text search.
-   Tambahkan filter ACL, sitasi, dan evaluasi retrieval.
-   Gunakan LLM lokal untuk dokumen yang harus tetap internal.

**Output:** pencarian dan tanya jawab dokumen berbasis sumber.

### Tahap 4 --- Policy Engine dan routing matang

-   Pisahkan Policy Engine, Task Planner, dan AI Router.
-   Tambahkan klasifikasi konteks aktual.
-   Terapkan pemeriksaan sebelum dan setelah retrieval serta sebelum
    pengiriman eksternal.
-   Uji fallback, penolakan, dan kebocoran lintas organisasi.

**Output:** routing hybrid yang dapat diaudit.

### Tahap 5 --- Evaluasi produksi dan optimasi

-   Lakukan pengujian keamanan dan beban.
-   Ukur kualitas model lokal dan eksternal.
-   Optimalkan biaya, latensi, retrieval, dan prompt.
-   Tentukan SLO dan prosedur insiden.

**Output:** kesiapan produksi berdasarkan kriteria yang terukur.

### Tahap 6 --- Agent terbatas dan perluasan

-   Tambahkan workflow multi-langkah.
-   Batasi tools berdasarkan izin.
-   Terapkan persetujuan untuk tindakan penting.
-   Tambahkan provider atau model baru hanya jika ada manfaat yang
    terbukti.

**Output:** automasi AI yang terkendali.

## 18. Matriks Keputusan Routing

Matriks awal berikut harus disesuaikan dengan kebijakan resmi dan hasil
evaluasi.

  -----------------------------------------------------------------------
  Jenis permintaan  Komponen utama    Model default     Eksternal?
  ----------------- ----------------- ----------------- -----------------
  Hitung jumlah     Analytics API /   Tidak wajib LLM   Tidak diperlukan
  atau agregasi     SQL                                 

  Jelaskan          Analytics +       Lokal jika        Opsional jika
  statistik         narasi            sensitif          konteks diizinkan
  internal                                              

  Tanya jawab SOP   RAG               LLM lokal         Tidak
  rahasia                                               

  Ringkasan laporan Retrieval /       LLM lokal         Tidak
  rahasia           ekstraksi                           

  Klasifikasi       Parser atau       Lokal             Tidak
  dokumen internal  classifier                          

  Brainstorming     LLM Gateway       Eksternal atau    Diizinkan sesuai
  umum                                lokal             kebijakan

  Sintesis kompleks Tools + LLM       Model yang lulus  Ya, bila
  dari data publik                    evaluasi          bermanfaat

  Sintesis dari     Analytics + RAG   Lokal             Tidak, kecuali
  data internal                                         kebijakan secara
  sensitif                                              eksplisit
                                                        mengizinkan
                                                        konteks tertentu

  Prediksi numerik  Model             Model khusus      Tidak otomatis
                    statistik/ML                        

  Mengubah atau     Backend tool +    LLM hanya         Bukan keputusan
  menghapus data    approval          membantu rencana  otomatis
  -----------------------------------------------------------------------

## 19. Tata Kelola dan Operasional

Sebelum produksi, tentukan:

-   Pemilik sistem AI dan pemilik data.
-   Penanggung jawab kebijakan provider.
-   Prosedur penambahan atau penggantian model.
-   Jadwal evaluasi dan regression testing.
-   Prosedur pencabutan akses dan penghapusan data.
-   Retensi log dan percakapan.
-   Penanganan insiden dan kebocoran.
-   Prosedur review output yang berdampak tinggi.
-   Mekanisme feedback pengguna.
-   Inventaris model, versi, prompt, embedding, dan konfigurasi.
-   Dokumentasi perubahan kebijakan serta alasan perubahan.

Gunakan kerangka manajemen risiko seperti NIST AI RMF dan panduan
keamanan aplikasi LLM dari OWASP sebagai referensi, bukan sebagai
pengganti kebijakan organisasi atau penilaian risiko spesifik.

## 20. Keputusan Awal yang Direkomendasikan

Untuk proof of concept, gunakan konfigurasi berikut:

1.  **Frontend:** React + TypeScript.
2.  **AI Gateway:** Node.js + Express.
3.  **Analytics:** Python + FastAPI dengan fungsi terdefinisi.
4.  **Data utama:** PostgreSQL.
5.  **RAG:** ingestion Python, embedding lokal, PostgreSQL + pgvector,
    dan full-text search.
6.  **LLM lokal:** satu model yang dipilih berdasarkan hardware serta
    evaluasi Bahasa Indonesia.
7.  **LLM eksternal:** satu provider API yang telah ditinjau kebijakan
    data dan kontraknya.
8.  **Routing:** rules-first; local LLM planner hanya jika diperlukan.
9.  **Policy Engine:** deterministik dan terpisah secara logis dari
    planner/router.
10. **Keamanan:** akses minimum, klasifikasi data, redaksi, validasi
    tool, audit aman, rate limit, dan pengujian prompt injection.
11. **Fine-tuning:** ditunda sampai evaluasi membuktikan kebutuhan.
12. **Agent:** ditambahkan setelah assistant dan tool calling dasar
    terbukti aman.

### Prinsip keputusan final

-   Jika tugas hanya memerlukan perhitungan, gunakan Analytics Service.
-   Jika tugas memerlukan pengetahuan dokumen, gunakan RAG.
-   Jika konteks wajib tetap internal, gunakan jalur lokal yang telah
    disetujui.
-   Jika tugas memerlukan kemampuan model eksternal dan konteksnya boleh
    dikirim, gunakan API eksternal.
-   Jika izin atau klasifikasi tidak jelas, jangan mengirim data keluar.
-   Jika model gagal, jangan mengarang hasil atau melewati kebijakan.
-   Jika tindakan memiliki dampak nyata, gunakan kontrol backend dan
    persetujuan yang sesuai.

## 21. Referensi Teknis

Dokumentasi berikut dapat digunakan saat tahap desain dan implementasi.
Tinjau kembali versi, lisensi, dan ketentuan terbaru sebelum menetapkan
pilihan produksi.

-   OpenAI API documentation: https://developers.openai.com/api/docs
-   Anthropic documentation: https://docs.anthropic.com/
-   Gemini API documentation: https://ai.google.dev/gemini-api/docs
-   DeepSeek API documentation: https://api-docs.deepseek.com/
-   Ollama: https://ollama.com/
-   vLLM: https://docs.vllm.ai/
-   PostgreSQL: https://www.postgresql.org/docs/
-   pgvector: https://github.com/pgvector/pgvector
-   OWASP Top 10 for LLM Applications:
    https://owasp.org/www-project-top-10-for-large-language-model-applications/
-   NIST AI Risk Management Framework:
    https://www.nist.gov/itl/ai-risk-management-framework

------------------------------------------------------------------------

## 22. Penutup

Arsitektur yang disarankan adalah **Hybrid AI dengan AI Gateway**, yang
menggabungkan analitik deterministik, RAG internal, LLM lokal, dan LLM
eksternal sesuai kebijakan.

Pemisahan terpenting adalah:

-   **Policy Engine:** menentukan apa yang diizinkan.
-   **Task Planner:** menentukan pekerjaan yang perlu dilakukan.
-   **AI Router:** memilih jalur eksekusi yang diizinkan.
-   **Analytics dan RAG:** menyediakan data serta bukti yang relevan.
-   **LLM:** membantu memahami, merangkum, dan menjelaskan hasil.

Dengan fondasi ini, AI dapat berkembang dari assistant sederhana menjadi
sistem analitik dan automasi yang lebih canggih tanpa memberikan kendali
keamanan platform kepada model.
