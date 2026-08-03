# JAWA — Catur Jawa Multiplayer

Permainan papan tradisional **Catur jawa** untuk dua pemain yang bermain dari
dua komputer (atau dua proses) berbeda, saling terhubung lewat jaringan.

## Requirement
- Python 3.8+
- Tkinter
## Cara Menjalankan

Jalankan dari root repo. Program yang sama dipakai untuk kedua peran.

```bash
python3 main.py
```

Sebuah jendela launcher akan muncul, isinya:

- **Mode** — `Host` (menunggu lawan) atau `Join` (menyambung ke host)
- **Nama** — nama pemain, dipakai untuk log dan rating
- **Port lokal** — port UDP yang dipakai proses ini (default 5000)
- **Host tujuan** — IP dan port host, hanya aktif di mode `Join`

Alurnya:

1. **Pemain 1** pilih `Host`, isi nama, tentukan port lokal (mis. 5000), klik
   *Mulai*. Jendela "Menunggu koneksi" muncul.
2. **Pemain 2** pilih `Join`, isi nama, isi **IP host** dan **Port host**
   sesuai milik pemain 1, lalu klik *Mulai*.
3. Setelah handshake berhasil, papan terbuka di kedua sisi dan permainan
   dimulai. Host selalu memegang pihak `A` dan jalan duluan.
4. Saat permainan selesai, muncul ringkasan pemenang beserta perubahan
   rating, lalu launcher tampil lagi untuk partai berikutnya.

### Mencoba di satu komputer

Buka dua terminal, jalankan `python3 main.py` di masing-masing. Terminal
pertama sebagai host di port `5000`; terminal kedua sebagai join ke
`127.0.0.1:5000` dengan **port lokal berbeda**, misal `5001`.

### Dua komputer berbeda

Pemain 2 mengisi IP LAN host (mis. `192.168.1.10`). 
### Membaca riwayat permainan

Setiap permainan tersimpan di `logs/game_<id>.jsonl`.

```bash
python3 -m game.logger --list                          # daftar log
python3 -m game.logger --replay logs/game_<id>.jsonl   # riwayat terbaca manusia
python3 -m game.logger --list --dir DIR                # log di direktori lain
```

### Papan peringkat

```bash
python3 -m game.rating                  # baca ratings.json
python3 -m game.rating --store FILE     # file rating lain
```

## Tentang Program Ini

### Susunan berkas

```
main.py             program utama: launcher -> handshake -> papan -> ulangi
game/
  board.py          papan sebagai graf node + edge berarah
  state.py          isi papan, giliran, status permainan
  rules.py          langkah legal, makan, promosi, deteksi akhir permainan
  engine.py         GameEngine: satu pintu masuk untuk GUI maupun jaringan
  network.py        protokol andal di atas UDP (TCP-over-UDP)
  launcher.py       dialog setup koneksi, jendela tunggu, popup akhir partai
  gui.py            papan Tkinter
  logger.py         penulis + pembaca log JSONL
  rating.py         Elo non-linear, persisten di ratings.json
tools/              skrip uji keandalan dengan tc-netem
logs/               keluaran runtime (tidak di-commit)
ratings.json        keluaran runtime (tidak di-commit)
```

### Model eksekusi

Tidak ada server pusat. Dua proses berkedudukan setara, masing-masing
menjalankan **salinan engine sendiri**. Yang dikirim lewat jaringan hanya
*langkah*, bukan seluruh papan. Karena kedua engine deterministik dan
menerapkan langkah dalam urutan yang sama, kedua papan dijamin identik —
inilah yang dibuktikan oleh hash papan di skrip uji.

Peran `host` hanya menentukan siapa yang menerbitkan konfigurasi awal
(`game_id`, giliran pertama, nama kedua pemain) saat handshake. Sesudah itu
kedua sisi setara.

### Lapisan jaringan: TCP-over-UDP

`game/network.py` membangun ulang jaminan keandalan TCP di atas soket UDP,
dengan dua modifikasi yang disengaja:

- **Handshake sekaligus membawa data.** `SYN` membawa nama penantang,
  `SYNACK` membawa konfigurasi permainan lengkap, lalu `ACK` menutup
  three-way handshake. Jadi tidak ada ronde negosiasi terpisah.
- **Teardown sekaligus membawa hasil.** `FIN` berisi pemenang, alasan, dan
  langkah terakhir yang mengakhiri permainan.
- Disederhanakan: tidak ada `RST`, `PSH`, sliding window, maupun congestion
  control.

Format paketnya JSON satu datagram:

```json
{"typ": "DATA", "seq": 3, "data": {"move": {...}}}
{"typ": "ACK",  "ack": 3}
```

Yang dijamin lapisan ini:

| Masalah UDP | Penanganan |
| --- | --- |
| Paket hilang | tiap `DATA`/`FIN` disimpan di `pending`, dikirim ulang tiap `RTO` (0.3 s) sampai ter-`ACK`, maksimal 100 kali |
| Paket duplikat | `seq` di bawah `expected` atau sudah ada di buffer langsung dibuang (dihitung di `stats["dup"]`) |
| Paket tidak urut | disimpan di buffer sampai nomor urutnya tiba, baru diserahkan ke aplikasi secara berurutan |
| Lawan hilang | setelah 100 percobaan gagal, status menjadi `lost` dan aplikasi diberi tahu |

Sebuah thread latar menjalankan `loop()`: menerima paket, mengirim `ACK`, dan
memeriksa timer retransmisi tiap 50 ms. Aplikasi cukup memanggil
`send_move()` / `send_end()` dan membaca `read()` dari antrian in-order —
GUI tidak pernah berurusan dengan `seq` atau retransmisi.

### Engine dan papan

`GameEngine` adalah satu-satunya pintu masuk aturan permainan: `legal_moves()`,
`apply_move()`, `call_dam()`, `resign()`. Engine tidak tahu apa pun tentang
jaringan maupun GUI — keduanya memanggil API yang sama, sehingga langkah dari
lawan diproses lewat jalur yang persis sama dengan langkah lokal.

`board.py` menyimpan papan sebagai **graf node + edge berarah**, bukan matriks.
Tiap edge membawa arah `(dx, dy)`, dan arah itulah yang menentukan titik
pendaratan sebuah lompatan. Akibatnya `rules.py` sama sekali tidak tahu bentuk
papannya — mengganti papan cukup dengan mengubah pembangun graf di `board.py`.

### Logging

Setiap kejadian (`game_start`, `move`, `capture`, `promotion`, `dam`,
`game_over`, `rating_update`) ditulis append-only sebagai satu baris JSON ke
`logs/game_<id>.jsonl`, lengkap dengan `seq` naik monoton dan `ts`. Karena
append-only dan berurutan, satu partai bisa diputar ulang persis seperti
terjadinya. Pembaca log tahan terhadap baris rusak: baris yang gagal di-parse
ditandai, bukan menggagalkan seluruh pembacaan.

### Rating

Elo dengan ekspektasi skor **logistik**, jadi perubahan rating tidak linear
terhadap selisih kekuatan:

```
E_A = 1 / (1 + 10^((R_B - R_A) / 400))
R_A' = R_A + K * (S_A - E_A),   S_A in {1, 0.5, 0}
```

Faktor `K` ikut adaptif: 40 untuk pemain dengan <10 partai, 16 untuk rating
>=2000, selain itu 24 — pemain baru bergerak cepat, pemain mapan lambat.
Rating awal 400, disimpan di `ratings.json` dan diperbarui otomatis tiap
partai selesai (penulisan atomik lewat file sementara + `os.replace`).
