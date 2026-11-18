# EnergyX Social (modul "Social Posting")

Publikasi Instagram, Facebook Page, YouTube, dan TikTok langsung dari ERPNext/Frappe v16, tanpa SaaS perantara.

## Instalasi

```bash
bench get-app /path/ke/energyx_social      # atau git URL
bench --site <site> install-app energyx_social
bench --site <site> migrate
bench restart
```

`after_install`/`after_migrate` membuat peran **Social Editor**, **Social Manager**, dan Workflow **Social Post Approval** (hanya bila belum ada).
Berikan **kedua** peran (Editor + Manager) kepada manajer agar bisa membuat draf sekaligus menyetujui. Worker `long` harus berjalan.

## Alur

1. System Manager mengisi **Social Posting Settings** (akun, token, Public Base URL) lalu klik **Test Connection** per baris. `enabled` hanya menyala bila lolos.
2. Social Editor membuat **Social Post** → *Submit for Approval*.
3. Social Manager *Approve*. Kanal dengan jadwal → `Scheduled`, tanpa jadwal → `Queued` (siap **Publish Now**).
4. Cron 5 menit mengklaim maks. 10 kanal jatuh tempo → job `long` (timeout 1200 detik, `enqueue_after_commit`).
5. Gagal → Error Log + kolom `error_log`; rate-limit/transient dijadwalkan ulang (maks. 5 percobaan), selebihnya `Failed` → **Retry Failed**.

## Kredensial per kanal

| Kanal | account_id | Token |
|---|---|---|
| Instagram | IG Business Account ID | Long-lived token (scope `instagram_content_publish`, `pages_read_engagement`); isi App ID/Secret agar bisa diperpanjang harian |
| Facebook Page | Page ID | Page access token (`pages_manage_posts`, `pages_manage_engagement`) |
| YouTube | Channel ID (UC…) | Client ID/Secret + Refresh Token (scope `youtube.upload`, `youtube`); access token diperbarui otomatis |
| TikTok | open_id | Client Key/Secret + Refresh Token (scope `video.publish`, `video.upload`, `user.info.basic`, `video.list`) |

## Catatan operasional penting

- **Public Base URL** harus https dan dapat diakses Meta/TikTok tanpa login. File *private* otomatis disalin sementara ke `/files/` dengan nama acak lalu dihapus setelah publish.
- **TikTok**: `PULL_FROM_URL` (dan semua foto) mensyaratkan domain/URL prefix terverifikasi di TikTok Developer Portal. Aplikasi yang belum diaudit hanya boleh `SELF_ONLY`.
- **YouTube**: `videos.insert` memakan 1600 unit kuota (default 10.000/hari ≈ 6 unggahan). Proyek API yang belum diaudit mengunggah sebagai privat. Kuota habis → dijadwalkan ulang 6 jam.
- **Penghapusan dari platform**: didukung Facebook & YouTube. Instagram dan TikTok tidak punya API hapus (pesan jelas ditampilkan; hapus manual).
- Batas ukuran/format ada di `services/media.py::RULES` (nilai konservatif). Verifikasi ke dokumentasi platform terbaru.
- Insight Meta sering berganti nama metrik; `MetaProvider._first_insight` mencoba beberapa nama dan mengabaikan yang tidak didukung.
- Keamanan: semua rahasia berupa field `Password` (terenkripsi), `Account` memakai `repr=False`, token dikirim lewat header (bukan URL), dan semua teks galat melewati `redact()` sebelum masuk Error Log / `error_log`. Field sistem pada baris kanal (status, remote_id, dll.) dipulihkan server dari DB sehingga tidak bisa dipalsukan dari client.

## Struktur

```
energyx_social/
  hooks.py  jobs.py  api.py
  setup/install.py                 # peran + workflow
  services/{client,media,credentials,errors,publisher}.py
  services/providers/{meta,youtube,tiktok}.py
  social_posting/doctype/{social_posting_settings,social_account,social_post,social_post_channel,social_post_metric}
```
