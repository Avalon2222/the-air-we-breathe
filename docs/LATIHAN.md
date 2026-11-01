# 🏋️ Latihan

Diurutkan dari mudah ke menantang. Tiap latihan punya petunjuk dan kunci yang bisa dibuka. Usahakan mencoba
minimal 10 menit sebelum membuka kunci. Setelah tiap latihan, jalankan `python -m pytest tests/` dan
`streamlit run app.py`.

---

### Latihan 1 — Menambah titik pantau (cukup edit CSV) ⭐

Tambahkan **Cibubur** (`-6.360, 106.890`, kota `Jakarta`, wilayah `Jakarta Timur`) ke `data/titik.csv`, lalu
perbarui data contoh dengan `python scripts/perbarui_sample.py`. Di sel mana ia jatuh?

<details><summary>Petunjuk</summary>
Satu baris baru di akhir CSV, urutan kolom: nama, kota, wilayah, lat, lon. Hitung selnya dengan
<code>sumber.sel_grid(-6.36, 106.89)</code> sebelum mengunduh ulang.
</details>

<details><summary>Kunci</summary>

```
Cibubur,Jakarta,Jakarta Timur,-6.360,106.890
```

Selnya `-6.4,106.8`, sama dengan Cibinong dan Kebayoran Baru. Tiga tes akan **gagal** karena mengharapkan 51 titik
(`test_muat_titik_statis_valid`, `test_muat_sample_bentuk_dan_meta`, `test_muat_semua_paksa_offline_tanpa_jaringan`,
dan `test_prakiraan_pada_data_contoh`). Ubah 51 menjadi 52. Tes yang gagal karena asumsi lama adalah tes yang bekerja benar.
</details>

---

### Latihan 2 — Jam terbersih untuk lari pagi ⭐

Di tab Patterns sudah ada kalimat jam terkotor dan terbersih. Tambahkan satu kalimat yang menyebut **jendela 3 jam
berturut-turut** dengan rata-rata PM2.5 terendah, misalnya "Jendela terbersih: 13:00–15:00 WIB (34 µg/m³)".

<details><summary>Petunjuk</summary>
<code>prof["pm2_5"].rolling(3).mean()</code> memberi rata-rata tiga jam yang berakhir di tiap baris. <code>idxmin()</code>
memberi indeks akhir jendela. Awas jam 23→0→1: rolling biasa tidak melingkar, dan untuk latihan ini itu boleh diabaikan.
</details>

<details><summary>Kunci</summary>

```python
gulung = prof["pm2_5"].rolling(3).mean()
akhir = int(gulung.idxmin())
st.caption(f"Jendela 3 jam terbersih: {akhir - 2:02d}:00–{akhir:02d}:00 WIB ({gulung.min():.0f} µg/m³).")
```
</details>

---

### Latihan 3 — Indeks ketiga: AQI Eropa ⭐⭐

Open-Meteo juga menyediakan `european_aqi`, tetapi kita menghitung indeks sendiri dari PM2.5. Tambahkan fungsi
`analisis.aqi_eu_pm25` memakai titik potong EAQI untuk PM2.5 (µg/m³): Good 0–10, Fair 10–20, Moderate 20–25,
Poor 25–50, Very poor 50–75, Extremely poor 75–800, dengan indeks 0–20, 20–40, 40–60, 60–80, 80–100, 100+.
Tambahkan tes parametrize untuk titik potongnya.

<details><summary>Petunjuk</summary>
Tabel `AQI_US_PM25` sudah menunjukkan formatnya; `_interpolasi` dan `_bungkus` bisa dipakai ulang tanpa diubah.
</details>

<details><summary>Kunci</summary>

```python
AQI_EU_PM25 = [(0, 10, 0, 20), (10, 20, 20, 40), (20, 25, 40, 60), (25, 50, 60, 80), (50, 75, 80, 100), (75, 800, 100, 500)]

def aqi_eu_pm25(konsentrasi):
    return _bungkus(konsentrasi, np.round(_interpolasi(konsentrasi, AQI_EU_PM25)))
```

Tes: `(0, 0), (10, 20), (25, 60), (50, 80), (75, 100)`. Lalu bandingkan: PM2.5 40 µg/m³ adalah ISPU 81 "Sedang",
US AQI 112, dan EAQI 72 "Poor". Tiga benua, tiga vonis.
</details>

---

### Latihan 4 — Titik yang paling "melawan" selnya ⭐⭐

Semua titik sesel punya PM2.5 sama, tetapi cuacanya beda. Buat tabel kecil di tab Patterns: untuk setiap sel, titik
dengan rata-rata angin 7 hari **tertinggi** dan **terendah**. Hipotesisnya: kalau CAMS beresolusi lebih halus, titik
berangin itulah yang akan lebih bersih.

<details><summary>Petunjuk</summary>
Mulai dari `analisis.harian_per_titik(jam)`, saring 7 hari terakhir, `groupby(["sel","titik"])["angin"].mean()`,
lalu per sel ambil `idxmax` dan `idxmin`. Kolom `sel` ada di `jam`, jadi tambahkan ke `groupby` di `harian_per_titik`
atau gabungkan ulang.
</details>

<details><summary>Kunci</summary>

```python
h = analisis.harian_per_titik(jam).merge(jam[["titik", "sel"]].drop_duplicates(), on="titik")
h = h[h["tanggal"] >= h["tanggal"].max() - pd.Timedelta(days=7)]
a = h.groupby(["sel", "titik"])["angin"].mean().reset_index()
paling = a.loc[a.groupby("sel")["angin"].idxmax()].merge(a.loc[a.groupby("sel")["angin"].idxmin()], on="sel", suffixes=("_berangin", "_tenang"))
st.dataframe(paling, hide_index=True)
```
</details>

---

### Latihan 5 — Persistence yang lebih pintar ⭐⭐

Tambahkan pembanding keempat di `uji_maju`: **rata-rata 3 hari terakhir** (`lag1`, `lag2`, dan hari ketiga). Apakah ia
mengalahkan persistence biasa? Model sederhana sering kalah dari rata-rata pendek karena rata-rata meredam hari aneh.

<details><summary>Petunjuk</summary>
`tambah_fitur` sudah membuat `lag2`. Tambahkan `lag3 = g["pm2_5"].shift(3)` dan `rata3 = (lag1 + lag2 + lag3) / 3`.
Di `uji_maju`, tambahkan kunci `"rata3"` ke dict `hasil` dan isi dengan `te["rata3"]`. Jangan masukkan `rata3` ke
`FITUR` dulu; ini pembanding, bukan fitur.
</details>

<details><summary>Kunci</summary>

```python
h["lag3"] = g["pm2_5"].shift(3)
h["rata3"] = h[["lag1", "lag2", "lag3"]].mean(axis=1)
...
hasil = {"persistensi": [], "rata3": [], "ridge": [], "gbr": []}
...
hasil["rata3"].append(te["rata3"].to_numpy())
```

Tambahkan `"rata3": "Rata-rata 3 hari"` ke `LABEL_MODEL` di `model.py` dan `grafik.py`, dan pastikan `_bisa_dilatih`
tidak membuang baris karena `lag3` NaN (ia hanya memeriksa `FITUR`). Pada data contoh, rata-rata 3 hari biasanya
sedikit lebih buruk dari persistence saat tren turun tajam, dan lebih baik saat deretnya bergerigi.
</details>

---

### Latihan 6 — Prakiraan lusa ⭐⭐⭐

Open-Meteo mengirim dua hari prakiraan. Perluas `latih_dan_prakirakan` agar juga menghasilkan prakiraan **H+2**.
Kesulitannya: `lag1` untuk lusa adalah prakiraan besok (yang belum terjadi), jadi gunakan hasil model untuk besok
sebagai `lag1` lusa (prakiraan rekursif).

<details><summary>Petunjuk</summary>
Setelah `besok_ml` dihitung, bangun `target2 = h[h["tanggal"] == besok + 1 hari]`, isi `lag1` dengan `besok_ml` per sel,
`rata7_minus_lag1` dari rata7 yang digeser, `d_*` relatif terhadap cuaca besok, lalu panggil `prediksi` lagi.
Galat lusa pasti lebih besar; katakan itu di antarmuka.
</details>

<details><summary>Kunci</summary>

```python
lusa = besok + timedelta(days=1)
t2 = h[h["tanggal"] == lusa].copy()
besok_sel = target.set_index("sel")
t2["lag1"] = t2["sel"].map(besok_sel["besok_ml"])
t2["rata7_minus_lag1"] = t2["sel"].map(besok_sel["rata7"]) - t2["lag1"]
for k in CUACA:
    t2[f"d_{k}"] = t2[k] - t2["sel"].map(besok_sel[k])
for k in FITUR:
    t2[k] = t2[k].fillna(data[k].median())
t2["lusa_ml"] = prediksi(model, t2)
```

Untuk mengukur galat H+2 secara jujur, `uji_maju` perlu diperluas dengan cara yang sama (prediksi besok dipakai
sebagai lag1 untuk lusa), bukan memakai lag1 sebenarnya.
</details>

---

### Latihan 7 — Sensor vs model ⭐⭐⭐

Daftar kunci OpenAQ gratis, simpan di `.streamlit/secrets.toml` sebagai `OPENAQ_API_KEY = "..."`. Stasiun akan muncul
di peta. Buat tabel di tab Data yang memasangkan tiap stasiun dengan sel CAMS tempatnya berada dan menghitung
selisih `sensor − model`. Apakah CAMS meremehkan Jakarta?

<details><summary>Petunjuk</summary>
`sumber.sel_grid(stasiun["lat"], stasiun["lon"])` memberi sel. Gabungkan dengan `kini.groupby("sel")["pm2_5"].mean()`.
Waktu pembacaan sensor bisa berbeda beberapa jam dari jam "sekarang"; tampilkan kolom waktunya.
</details>

<details><summary>Kunci</summary>

```python
s = hasil.stasiun.copy()
s["lat_sel"], s["lon_sel"] = sumber.sel_grid(s["lat"], s["lon"])
s["sel"] = s["lat_sel"].map("{:.1f}".format) + "," + s["lon_sel"].map("{:.1f}".format)
m = kini.groupby("sel")["pm2_5"].mean().rename("pm2_5_model")
s = s.merge(m, on="sel", how="left")
s["selisih"] = s["pm2_5"] - s["pm2_5_model"]
st.dataframe(s[["nama", "penyedia", "waktu", "pm2_5", "pm2_5_model", "selisih"]], hide_index=True)
st.caption(f"Rata-rata sensor − model: {s['selisih'].mean():+.0f} µg/m³ dari {len(s)} stasiun.")
```

Secara umum di Jakarta, sensor permukaan membaca lebih tinggi daripada CAMS global. Itulah mengapa lapisan ini ada.
</details>

---

### Latihan 8 — Arsip harian dengan SQLite ⭐⭐⭐

Setiap kali aplikasi mengambil data langsung, simpan rata-rata harian per sel ke `data/arsip.sqlite` (tabel
`harian(sel, tanggal, pm2_5, angin, hujan, blh)`, kunci unik `(sel, tanggal)`). Setelah beberapa bulan, Anda punya
riwayat lebih panjang dari 60 hari Open-Meteo, dan model bisa belajar musim.

<details><summary>Petunjuk</summary>
`sqlite3` ada di pustaka standar. `INSERT OR REPLACE` menangani hari yang diambil berkali-kali. Panggil penyimpanan
dari `muat_semua` hanya bila `not offline`. Di Streamlit Community Cloud berkas lokal **hilang** saat aplikasi
di-deploy ulang; latihan ini untuk dijalankan di mesin sendiri atau diperluas dengan penyimpanan eksternal.
</details>

<details><summary>Kunci</summary>

```python
import sqlite3
def arsipkan(harian: pd.DataFrame, berkas=DIR_DATA / "arsip.sqlite") -> None:
    with sqlite3.connect(berkas) as con:
        con.execute("CREATE TABLE IF NOT EXISTS harian (sel TEXT, tanggal TEXT, pm2_5 REAL, angin REAL, hujan REAL, blh REAL, PRIMARY KEY (sel, tanggal))")
        con.executemany(
            "INSERT OR REPLACE INTO harian VALUES (?, ?, ?, ?, ?, ?)",
            harian.dropna(subset=["pm2_5"]).assign(tanggal=lambda d: d["tanggal"].astype(str))[["sel", "tanggal", "pm2_5", "angin", "hujan", "blh"]].itertuples(index=False),
        )
```

Lalu di `latih_dan_prakirakan`, gabungkan arsip dengan `tabel_harian(jam)` (`concat` + `drop_duplicates(["sel","tanggal"], keep="last")`)
sebelum `tambah_fitur`. Tambahkan fitur `bulan_sin`/`bulan_cos` begitu arsip melewati satu tahun.
</details>

---

### Latihan 9 — Interval kepercayaan prakiraan ⭐⭐⭐⭐

Angka tunggal "besok 62 µg/m³" menyembunyikan ketidakpastian. Tambahkan rentang **P10–P90** untuk tiap sel dengan
salah satu cara: (a) kuantil galat sisa dari uji maju (empiris), atau (b) `GradientBoostingRegressor(loss="quantile",
alpha=0.1)` dan `alpha=0.9` sebagai dua model tambahan. Gambar rentangnya sebagai pita di grafik `garis_riwayat`.

<details><summary>Petunjuk</summary>
Cara (a) paling murah: simpan `err = p − y` dari model terpilih di `uji_maju`, lalu `np.quantile(err, [0.1, 0.9])`.
Rentang besok = `besok_ml + q10` sampai `besok_ml + q90`. Pita per jam: kalikan dengan profil diurnal seperti nilai tengahnya.
</details>

<details><summary>Kunci</summary>

```python
# di uji_maju, kembalikan juga sisa galat per model: sisa[nama] = p - y
q10, q90 = np.quantile(sisa[terpilih], [0.1, 0.9])
per_sel["besok_p10"] = np.clip(per_sel["besok_ml"] + q10, 1, None)
per_sel["besok_p90"] = per_sel["besok_ml"] + q90
```

Di `garis_riwayat`, tambahkan dua `go.Scatter` dengan `fill="tonexty"` dan `fillcolor="rgba(255,159,67,0.15)"` sebelum
garis ML. Lalu periksa kalibrasinya: pada uji maju, apakah sekitar 80% nilai aktual benar-benar jatuh dalam rentang?
Kalau tidak, rentang Anda terlalu percaya diri, dan itu temuan yang layak ditulis di README.
</details>
