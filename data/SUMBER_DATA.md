# Sumber data dan metodologi

## Titik pantau (`titik.csv`)

51 titik yang mewakili kecamatan atau kawasan di Jabodetabek: 23 di DKI Jakarta (termasuk Pulau Pramuka sebagai
pembanding lepas pantai), 7 Bogor, 3 Depok, 10 Tangerang (kota, selatan, kabupaten, termasuk Bandara Soekarno-Hatta),
8 Bekasi. Koordinat adalah perkiraan pusat kecamatan, dibulatkan tiga desimal; bukan koordinat kantor resmi.
Kolom: `nama, kota, wilayah, lat, lon`. Menambah titik cukup dengan menambah baris.

## Open-Meteo Air Quality API

- URL: `https://air-quality-api.open-meteo.com/v1/air-quality`
- Parameter: `latitude`/`longitude` (daftar dipisah koma, 51 pasang sekaligus), `hourly=pm2_5,pm10,nitrogen_dioxide,
  ozone,carbon_monoxide,sulphur_dioxide`, `past_days=60`, `forecast_days=2`, `timezone=Asia/Jakarta`.
- Sumber hulu: **CAMS global** (Copernicus Atmosphere Monitoring Service, ECMWF), resolusi 0,4° (~40 km), dengan pembaruan
  tiap jam. Di Eropa Open-Meteo memakai CAMS Eropa 0,1°; di Indonesia hanya versi global yang tersedia.
- Konsekuensi: pusat sel grid jatuh di kelipatan 0,4° (lintang −5,6; −6,0; −6,4; −6,8; bujur 106,4; 106,8; 107,2) dan
  **semua titik dalam satu sel menerima deret nilai yang persis sama**. 51 titik Jabodetabek hanya memuat **8 sel**.
  Fungsi `sumber.sel_grid` memberi label sel, dan `tests/test_sumber.py` memastikan asumsi ini masih berlaku pada data contoh.
- Nilai adalah keluaran model (analisis + prakiraan), bukan pengukuran. Di kota besar Asia Tenggara, CAMS cenderung
  **meremehkan** PM2.5 dibanding sensor permukaan, kadang puluhan µg/m³.
- Lisensi: CC BY 4.0 (Open-Meteo), data CAMS berlisensi Copernicus.

## Open-Meteo Forecast API

- URL: `https://api.open-meteo.com/v1/forecast`
- `hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,boundary_layer_height`,
  `past_days=60`, `forecast_days=2`, titik dan zona waktu sama.
- Model cuaca gabungan terbaik per lokasi (di Indonesia umumnya ECMWF IFS 9 km atau GFS), resolusi lebih halus daripada
  CAMS, sehingga angin dan tinggi lapisan batas berbeda antar titik meski PM2.5-nya sama.
- Tinggi lapisan batas (`boundary_layer_height`) adalah tebal lapisan udara yang bercampur dekat permukaan; makin rendah,
  makin terjebak polusi.

## OpenAQ v3 (opsional)

- URL: `https://api.openaq.org/v3/locations?bbox=106.30,-6.85,107.30,-5.60&parameters_id=2&limit=200`, lalu
  `/v3/locations/{id}/latest` per lokasi (maksimum 40 lokasi).
- Perlu kunci API gratis (daftar di explore.openaq.org), dikirim lewat header `X-API-Key`. Kunci dibaca dari variabel
  lingkungan `OPENAQ_API_KEY` atau `st.secrets["OPENAQ_API_KEY"]`.
- Isinya pembacaan **sensor sungguhan** (stasiun pemerintah, kedutaan, sensor berbiaya rendah) yang diagregasi OpenAQ.
  Di peta ditampilkan sebagai belah ketupat agar bisa dibandingkan dengan sel model.
- Parameter id 2 = `pm25` (µg/m³). Lisensi data mengikuti penyedia masing-masing (umumnya CC BY).

## Indeks

### ISPU (Permen LHK P.14/MENLHK/SETJEN/KUM.1/7/2020)

| ISPU | Kategori | PM2.5 24 jam (µg/m³) |
|---|---|---|
| 0–50 | Baik | 0–15,5 |
| 51–100 | Sedang | 15,6–55,4 |
| 101–200 | Tidak Sehat | 55,5–150,4 |
| 201–300 | Sangat Tidak Sehat | 150,5–250,4 |
| ≥ 301 | Berbahaya | 250,5–500 |

Rumus: `I = (Ia − Ib) / (Xa − Xb) × (X − Xb) + Ib`, dengan `(Xb, Xa)` batas konsentrasi dan `(Ib, Ia)` batas indeks
pada rentang yang memuat X. ISPU resmi dihitung dari rata-rata 24 jam; aplikasi ini juga menerapkannya pada nilai per jam
untuk peta "saat ini", yang secara resmi tidak baku, dan menyebutnya apa adanya.

### US AQI (US EPA, pembaruan Februari 2024)

| AQI | Kategori | PM2.5 24 jam (µg/m³) |
|---|---|---|
| 0–50 | Good | 0,0–9,0 |
| 51–100 | Moderate | 9,1–35,4 |
| 101–150 | Unhealthy for Sensitive Groups | 35,5–55,4 |
| 151–200 | Unhealthy | 55,5–125,4 |
| 201–300 | Very Unhealthy | 125,5–225,4 |
| 301–500 | Hazardous | 225,5–325,4 |

Konsentrasi dipotong ke satu desimal sebelum dihitung, mengikuti EPA. Batas bawah kategori Moderate yang hanya 9 µg/m³
membuat US AQI jauh lebih "galak" daripada ISPU pada udara yang sama.

### Pedoman WHO 2021 dan baku mutu nasional

- WHO: PM2.5 rata-rata 24 jam **15 µg/m³**, rata-rata tahunan **5 µg/m³**; PM10 45/15; NO₂ 25 (24 jam); O₃ 100 (8 jam);
  SO₂ 40 (24 jam); CO 4 mg/m³ (24 jam).
- PP 22/2021 Lampiran VII: PM2.5 24 jam **55 µg/m³**, tahunan 15 µg/m³.

## Prakiraan besok (`src/model.py`)

- Unit analisis: **sel grid × hari**, bukan titik × hari, agar deret yang identik tidak dihitung berulang.
- Target: rata-rata PM2.5 hari H. Fitur: PM2.5 H−1 dan H−2, rata-rata 7 hari sebelum H, prakiraan cuaca hari H (angin,
  hujan, tinggi lapisan batas, suhu, kelembapan), hari dalam pekan (sinus/kosinus, akhir pekan), posisi sel.
- Uji maju 14 hari: model dilatih ulang tiap hari uji hanya dengan hari-hari sebelumnya. Metrik: MAE, RMSE, bias.
- Model: persistence (pembanding), Ridge (α = 1, fitur distandarkan), Gradient Boosting (150 pohon, kedalaman 2).
  Yang MAE-nya terendah di antara dua model ML dipakai; MAE persistence selalu ditampilkan di sebelahnya.
- Prakiraan per jam besok: rata-rata harian ML dikalikan profil diurnal 14 hari terakhir per sel.
- Keterbatasan yang disengaja ditampilkan: fitur "hari ini" saat prakiraan hanya mencakup jam yang sudah lewat; data latih
  adalah keluaran model lain; 60 hari tidak memuat siklus musiman.
