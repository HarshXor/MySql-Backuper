# MySql-Backuper

Skrip Python kecil untuk melakukan dump MySQL, menyimpan cadangan ke folder lokal, dan mengunggah ke Google Drive dengan rotasi file.

## Persyaratan

1. Python 3
2. `mysqldump` dan `mysql` tersedia di PATH
3. Paket Python:
   ```bash
   pip install requests
   ```
4. Akun Google dengan project API Drive aktif dan kredensial OAuth 2.0

## Langkah-langkah Setup

1. **Buat project di Google Cloud Console**
   - Kunjungi https://console.cloud.google.com/
   - Buat project baru atau gunakan yang sudah ada.
   - Aktifkan Google Drive API di halaman "Library".
   - Pergi ke menu "Credentials" dan klik "Create Credentials" → "OAuth client ID".
   - Pilih "Desktop app" untuk jenis aplikasi.
   - Simpan `Client ID` dan `Client Secret`.

2. **Jalankan setup awal script**
   ```bash
   python backup.py --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> \
     --folder-id <FOLDER_ID> --max-files 3 \
     --local-dir /path/to/local/backup \
     --db-host localhost --db-user root --db-pass secret --db-name mydb
   ```
   - `--folder-id` dapat diperoleh dari URL folder Google Drive (misal `https://drive.google.com/drive/folders/<ID>`).
   - Script akan menyimpan konfigurasi di `google_api.json`.
   - Setelah menjalankan perintah di atas, ikuti instruksi untuk membuka URL dan memasukkan `authorization code`.

3. **Menjalankan backup berkala**
   Cukup panggil:
   ```bash
   python backup.py
   ```
   - Script akan membuat dump MySQL, memeriksa integritas Dump, menyimpan file lokal dengan rotasi, lalu mengunggah ke Drive.

## Fitur

- **Rotasi lokal**: Menjaga hanya `max-files` cadangan di folder lokal.
- **Rotasi Google Drive**: Hapus file tertua jika jumlah file sudah mencapai `max-files`.
- **Cek integritas**: Dump akan diimpor ke database sementara untuk memastikan tidak korup.
- **Konfigurasi otomatis**: Semua pengaturan tersimpan di `google_api.json`.

## Catatan

- Pastikan kredensial database memiliki izin membuat/menghapus database sementara untuk cek integritas.
- Jangan commit `google_api.json` ke Git (ditambahkan ke `.gitignore`).
- Jika `mysqldump` atau `mysql` tidak ditemukan, install paket MySQL client.

## Pengembangan

Kode utama berada di `backup.py`. Anda dapat menambahkan logging atau mendukung enkripsi file jika perlu.

---

Silakan sesuaikan parameter sesuai lingkungan Anda.