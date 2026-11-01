"""Indeks kualitas udara, ringkasan kondisi, dan pola waktu.

Dua indeks dihitung dari konsentrasi PM2.5 (µg/m³):

* **ISPU** (Indeks Standar Pencemar Udara) menurut Permen LHK P.14/2020,
  indeks resmi Indonesia. Lima kategori: Baik, Sedang, Tidak Sehat,
  Sangat Tidak Sehat, Berbahaya.
* **US AQI** menurut US EPA (titik potong PM2.5 pembaruan 2024), indeks yang
  paling sering muncul di aplikasi cuaca.

Keduanya interpolasi linear sepotong-sepotong antara titik potong konsentrasi
dan titik potong indeks. Semua fungsi menerima skalar atau ``Series``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WHO_HARIAN_PM25 = 15.0   # pedoman WHO 2021, rata-rata 24 jam
WHO_TAHUNAN_PM25 = 5.0   # pedoman WHO 2021, rata-rata tahunan
BAKU_MUTU_HARIAN_ID = 55.0  # PP 22/2021 Lampiran VII, PM2.5 24 jam

# (konsentrasi_bawah, konsentrasi_atas, indeks_bawah, indeks_atas)
ISPU_PM25 = [
    (0.0, 15.5, 0, 50),
    (15.5, 55.4, 51, 100),
    (55.4, 150.4, 101, 200),
    (150.4, 250.4, 201, 300),
    (250.4, 500.0, 301, 500),
]
AQI_US_PM25 = [
    (0.0, 9.0, 0, 50),
    (9.0, 35.4, 51, 100),
    (35.4, 55.4, 101, 150),
    (55.4, 125.4, 151, 200),
    (125.4, 225.4, 201, 300),
    (225.4, 325.4, 301, 500),
]

KATEGORI_ISPU = ["Baik", "Sedang", "Tidak Sehat", "Sangat Tidak Sehat", "Berbahaya"]
BATAS_ISPU = [50, 100, 200, 300]
WARNA_ISPU = {
    "Baik": "#2ecc71",
    "Sedang": "#3b9ddd",
    "Tidak Sehat": "#f1c40f",
    "Sangat Tidak Sehat": "#e74c3c",
    "Berbahaya": "#1b1b1b",
}
KATEGORI_AQI = ["Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous"]
BATAS_AQI = [50, 100, 150, 200, 300]
WARNA_AQI = {
    "Good": "#00e400",
    "Moderate": "#ffff00",
    "Unhealthy for Sensitive Groups": "#ff7e00",
    "Unhealthy": "#ff0000",
    "Very Unhealthy": "#8f3f97",
    "Hazardous": "#7e0023",
}
SARAN_ISPU = {
    "Baik": "Udara bersih. Aktivitas luar ruang aman untuk semua.",
    "Sedang": "Masih bisa diterima; kelompok sensitif (asma, lansia, anak) sebaiknya kurangi aktivitas berat yang lama di luar.",
    "Tidak Sehat": "Kelompok sensitif hindari aktivitas luar; yang lain kurangi aktivitas berat. Masker N95/KN95 membantu.",
    "Sangat Tidak Sehat": "Semua orang kurangi aktivitas luar ruang. Tutup jendela, nyalakan penyaring udara bila ada.",
    "Berbahaya": "Darurat kesehatan. Tetap di dalam ruangan, hindari aktivitas fisik luar sama sekali.",
}


def _interpolasi(konsentrasi, tabel) -> np.ndarray:
    c = np.asarray(konsentrasi, dtype=float)
    hasil = np.full(c.shape, np.nan)
    for c_lo, c_hi, i_lo, i_hi in tabel:
        topeng = (c >= c_lo) & (c <= c_hi) & np.isnan(hasil)
        hasil[topeng] = (i_hi - i_lo) / (c_hi - c_lo) * (c[topeng] - c_lo) + i_lo
    terlalu_tinggi = c > tabel[-1][1]
    hasil[terlalu_tinggi] = tabel[-1][3]
    hasil[c < 0] = np.nan
    return hasil


def _bungkus(konsentrasi, nilai: np.ndarray):
    if isinstance(konsentrasi, pd.Series):
        return pd.Series(nilai, index=konsentrasi.index)
    if np.ndim(konsentrasi) == 0:
        return float(nilai)
    return nilai


def ispu_pm25(konsentrasi):
    """Nilai ISPU dari konsentrasi PM2.5 (µg/m³). Dibulatkan ke bilangan bulat."""
    return _bungkus(konsentrasi, np.round(_interpolasi(konsentrasi, ISPU_PM25)))


def aqi_us_pm25(konsentrasi):
    """Nilai US AQI dari konsentrasi PM2.5 (µg/m³), konsentrasi dipotong ke 1 desimal seperti EPA."""
    c = np.floor(np.asarray(konsentrasi, dtype=float) * 10) / 10
    return _bungkus(konsentrasi, np.round(_interpolasi(c, AQI_US_PM25)))


def _kategori(indeks, batas: list[int], nama: list[str]):
    nilai = np.atleast_1d(np.asarray(indeks, dtype=float))
    idx = np.digitize(np.nan_to_num(nilai, nan=0.0), batas, right=True)
    hasil = np.array(nama, dtype=object)[idx]
    hasil[np.isnan(nilai)] = None
    if isinstance(indeks, pd.Series):
        return pd.Series(hasil, index=indeks.index)
    if np.ndim(indeks) == 0:
        return hasil.item()
    return hasil


def kategori_ispu(indeks):
    return _kategori(indeks, BATAS_ISPU, KATEGORI_ISPU)


def kategori_aqi_us(indeks):
    return _kategori(indeks, BATAS_AQI, KATEGORI_AQI)


def arah_kompas(derajat) -> str:
    """0–360° menjadi 8 arah mata angin (dari mana angin bertiup)."""
    if derajat is None or pd.isna(derajat):
        return "-"
    arah = ["U", "TL", "T", "TG", "S", "BD", "B", "BL"]
    return arah[int(((float(derajat) % 360) + 22.5) // 45) % 8]


# ---------------------------------------------------------------------------
# Kondisi saat ini
# ---------------------------------------------------------------------------

def waktu_sekarang(jam: pd.DataFrame) -> pd.Timestamp:
    """Jam terakhir yang bukan prakiraan. Dalam mode offline, inilah 'sekarang'."""
    pengamatan = jam.loc[~jam["prakiraan"], "waktu"]
    return pengamatan.max() if not pengamatan.empty else jam["waktu"].min()


def tambah_indeks(df: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan kolom ispu, kategori_ispu, aqi_us, kategori_aqi dari pm2_5."""
    df = df.copy()
    df["ispu"] = ispu_pm25(df["pm2_5"])
    df["kategori_ispu"] = kategori_ispu(df["ispu"])
    df["aqi_us"] = aqi_us_pm25(df["pm2_5"])
    df["kategori_aqi"] = kategori_aqi_us(df["aqi_us"])
    return df


def kondisi_terkini(jam: pd.DataFrame, sekarang: pd.Timestamp | None = None) -> pd.DataFrame:
    """Satu baris per titik pada jam 'sekarang', lengkap dengan indeks dan perubahan 24 jam."""
    sekarang = sekarang or waktu_sekarang(jam)
    kini = jam[jam["waktu"] == sekarang].copy()
    kemarin = jam[jam["waktu"] == sekarang - pd.Timedelta(hours=24)][["titik", "pm2_5"]].rename(columns={"pm2_5": "pm2_5_kemarin"})
    kini = kini.merge(kemarin, on="titik", how="left")
    kini["delta_24j"] = kini["pm2_5"] - kini["pm2_5_kemarin"]
    rata24 = (
        jam[(jam["waktu"] > sekarang - pd.Timedelta(hours=24)) & (jam["waktu"] <= sekarang)]
        .groupby("titik")["pm2_5"].mean().rename("pm2_5_24j")
    )
    kini = kini.merge(rata24, on="titik", how="left")
    kini = tambah_indeks(kini)
    kini["arah"] = kini["arah_angin"].map(arah_kompas)
    return kini.sort_values("pm2_5", ascending=False).reset_index(drop=True)


def ringkasan(kini: pd.DataFrame, jam: pd.DataFrame, sekarang: pd.Timestamp | None = None) -> dict:
    """Angka-angka kartu KPI untuk seluruh wilayah."""
    sekarang = sekarang or waktu_sekarang(jam)
    rata = float(kini["pm2_5"].mean())
    rata_24j = float(kini["pm2_5_24j"].mean())
    rata_kemarin = float(kini["pm2_5_kemarin"].mean()) if kini["pm2_5_kemarin"].notna().any() else float("nan")
    terburuk, terbaik = kini.iloc[0], kini.iloc[-1]
    rata_7h = float(jam[(jam["waktu"] > sekarang - pd.Timedelta(days=7)) & (jam["waktu"] <= sekarang)]["pm2_5"].mean())
    return {
        "waktu": sekarang,
        "rata": rata,
        "rata_24j": rata_24j,
        "rata_7h": rata_7h,
        "delta_24j": rata - rata_kemarin if not np.isnan(rata_kemarin) else float("nan"),
        "ispu": float(ispu_pm25(rata)),
        "kategori_ispu": kategori_ispu(ispu_pm25(rata)),
        "aqi_us": float(aqi_us_pm25(rata)),
        "kategori_aqi": kategori_aqi_us(aqi_us_pm25(rata)),
        "kali_who": rata_24j / WHO_HARIAN_PM25,
        "terburuk": terburuk,
        "terbaik": terbaik,
        "n_tidak_sehat": int((kini["ispu"] > 100).sum()),
        "n_titik": int(len(kini)),
        "angin": float(kini["angin"].mean()),
        "arah_angin": arah_kompas(_rata_arah(kini["arah_angin"])),
        "hujan_24j": float(jam[(jam["waktu"] > sekarang - pd.Timedelta(hours=24)) & (jam["waktu"] <= sekarang)].groupby("titik")["hujan"].sum().mean()),
    }


def _rata_arah(derajat: pd.Series) -> float:
    """Rata-rata arah angin secara vektor (rata-rata biasa 350° dan 10° memberi 180°, salah)."""
    rad = np.deg2rad(derajat.dropna().to_numpy(dtype=float))
    if rad.size == 0:
        return float("nan")
    return float(np.round(np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())), 6) % 360)


# ---------------------------------------------------------------------------
# Pola
# ---------------------------------------------------------------------------

def pengamatan(jam: pd.DataFrame) -> pd.DataFrame:
    return jam[~jam["prakiraan"]]


def rata_wilayah_per_jam(jam: pd.DataFrame) -> pd.DataFrame:
    """Rata-rata seluruh titik per jam: kolom waktu, pm2_5, pm10, angin, hujan, prakiraan."""
    g = jam.groupby("waktu", as_index=False).agg(pm2_5=("pm2_5", "mean"), pm10=("pm10", "mean"), angin=("angin", "mean"), hujan=("hujan", "mean"), blh=("blh", "mean"), prakiraan=("prakiraan", "all"))
    return g.sort_values("waktu").reset_index(drop=True)


def harian_per_titik(jam: pd.DataFrame) -> pd.DataFrame:
    """Rata-rata harian per titik dari jam pengamatan saja. Kolom tanggal bertipe date."""
    p = pengamatan(jam).copy()
    p["tanggal"] = p["waktu"].dt.date
    h = p.groupby(["titik", "kota", "wilayah", "lat", "lon", "tanggal"], as_index=False).agg(
        pm2_5=("pm2_5", "mean"), pm10=("pm10", "mean"), suhu=("suhu", "mean"), rh=("rh", "mean"),
        hujan=("hujan", "sum"), angin=("angin", "mean"), blh=("blh", "mean"), n_jam=("pm2_5", "size"),
    )
    return h


def profil_jam(jam: pd.DataFrame) -> pd.DataFrame:
    """Rata-rata PM2.5 per jam dalam sehari (0–23) di seluruh titik: kolom jam, pm2_5, p25, p75."""
    p = pengamatan(jam)
    g = p.groupby(p["waktu"].dt.hour)["pm2_5"]
    hasil = pd.DataFrame({"pm2_5": g.mean(), "p25": g.quantile(0.25), "p75": g.quantile(0.75)})
    hasil.index.name = "jam"
    return hasil.reset_index()


def matriks_jam_hari(jam: pd.DataFrame, hari: int = 14) -> pd.DataFrame:
    """Pivot rata-rata wilayah: baris = jam 0–23, kolom = tanggal (``hari`` terakhir)."""
    p = pengamatan(jam)
    batas = p["waktu"].max().normalize() - pd.Timedelta(days=hari - 1)
    p = p[p["waktu"] >= batas]
    piv = p.pivot_table(index=p["waktu"].dt.hour, columns=p["waktu"].dt.date, values="pm2_5", aggfunc="mean")
    piv.index.name, piv.columns.name = "jam", "tanggal"
    return piv


def label_sel(wilayah: pd.Series, maks: int = 2) -> str:
    """Nama pendek sebuah sel dari wilayah-wilayah di dalamnya, mis. "Jakarta Selatan, Kab. Bogor +6"."""
    urut = wilayah.value_counts()
    nama = ", ".join(urut.index[:maks])
    sisa = len(urut) - maks
    return f"{nama} +{sisa}" if sisa > 0 else nama


def per_sel(kini: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per sel grid CAMS: nilai, jumlah titik, label wilayah, daftar titik, dan indeks."""
    g = kini.groupby(["sel", "lat_sel", "lon_sel"], as_index=False).agg(
        pm2_5=("pm2_5", "mean"), pm2_5_24j=("pm2_5_24j", "mean"), delta_24j=("delta_24j", "mean"), n=("titik", "size"),
        label=("wilayah", label_sel), titik=("titik", lambda s: ", ".join(sorted(s))), angin=("angin", "mean"), blh=("blh", "mean"),
    )
    # Sel kecil disebut dengan nama titiknya langsung agar dua sel "Kab. Tangerang" tidak tertukar.
    g["label"] = np.where(g["n"] <= 3, g["titik"], g["label"])
    g = tambah_indeks(g)
    return g.sort_values("pm2_5", ascending=False).reset_index(drop=True)


def per_kota(kini: pd.DataFrame) -> pd.DataFrame:
    g = kini.groupby("kota", as_index=False).agg(pm2_5=("pm2_5", "mean"), pm2_5_24j=("pm2_5_24j", "mean"), n=("titik", "size"))
    g["ispu"] = ispu_pm25(g["pm2_5"])
    g["kategori_ispu"] = kategori_ispu(g["ispu"])
    return g.sort_values("pm2_5", ascending=False).reset_index(drop=True)


def hari_per_kategori(harian: pd.DataFrame) -> pd.DataFrame:
    """Jumlah hari per kategori ISPU per kota (rata-rata harian kota)."""
    k = harian.groupby(["kota", "tanggal"], as_index=False)["pm2_5"].mean()
    k["kategori_ispu"] = kategori_ispu(ispu_pm25(k["pm2_5"]))
    tabel = k.groupby(["kota", "kategori_ispu"]).size().unstack(fill_value=0)
    for kat in KATEGORI_ISPU:
        if kat not in tabel.columns:
            tabel[kat] = 0
    return tabel[KATEGORI_ISPU]


def hari_di_atas_who(harian: pd.DataFrame) -> pd.DataFrame:
    """Per titik: berapa persen hari yang rata-ratanya melampaui pedoman WHO dan baku mutu nasional."""
    g = harian.groupby(["titik", "kota"], as_index=False).agg(
        hari=("tanggal", "nunique"),
        di_atas_who=("pm2_5", lambda s: int((s > WHO_HARIAN_PM25).sum())),
        di_atas_baku_mutu=("pm2_5", lambda s: int((s > BAKU_MUTU_HARIAN_ID).sum())),
        pm2_5=("pm2_5", "mean"),
    )
    g["pct_who"] = 100 * g["di_atas_who"] / g["hari"]
    g["pct_baku_mutu"] = 100 * g["di_atas_baku_mutu"] / g["hari"]
    return g.sort_values("pm2_5", ascending=False).reset_index(drop=True)


def angin_vs_pm(harian: pd.DataFrame) -> pd.DataFrame:
    """Rata-rata harian wilayah: angin, hujan, blh vs PM2.5, untuk melihat peran cuaca."""
    w = harian.groupby("tanggal", as_index=False).agg(pm2_5=("pm2_5", "mean"), angin=("angin", "mean"), hujan=("hujan", "mean"), blh=("blh", "mean"), suhu=("suhu", "mean"))
    return w


def korelasi_cuaca(harian: pd.DataFrame) -> pd.Series:
    """Korelasi Pearson rata-rata harian wilayah antara PM2.5 dan tiap variabel cuaca."""
    w = angin_vs_pm(harian)
    return w[["angin", "hujan", "blh", "suhu"]].corrwith(w["pm2_5"]).round(2)


def akhir_pekan_vs_kerja(harian: pd.DataFrame) -> pd.DataFrame:
    h = harian.copy()
    h["hari"] = pd.to_datetime(h["tanggal"]).dt.day_of_week
    h["jenis"] = np.where(h["hari"] >= 5, "Akhir pekan", "Hari kerja")
    return h.groupby("jenis", as_index=False)["pm2_5"].mean()
