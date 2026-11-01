"""Prakiraan PM2.5 besok dengan model statistik sederhana.

Pertanyaannya: **berapa rata-rata PM2.5 besok di tiap sel?** Data polusi
Open-Meteo berasal dari grid CAMS global ~0,4°, sehingga 51 titik Jabodetabek
sebenarnya hanya memuat sekitar delapan deret waktu yang berbeda. Model dilatih
pada tingkat **sel**, bukan titik, agar satu kejadian tidak dihitung enam kali.
Hasil per sel lalu dipetakan kembali ke tiap titik.

Bentuk modelnya "persistence + koreksi": yang ditebak bukan kadar besok,
melainkan **perubahan dari hari ini** (``pm2_5 − lag1``). Tebakan paling malas,
besok sama dengan hari ini, sulit dikalahkan pada horizon satu hari; dengan
menebak koreksinya saja, model mulai dari tebakan malas itu dan hanya menambah
bila fitur memberi informasi. Fiturnya adalah apa yang sudah diketahui saat
prakiraan dibuat:

* kadar hari ini dan selisihnya terhadap rata-rata 7 hari (kembali ke rata-rata),
* **prakiraan cuaca untuk besok** dan perubahannya terhadap hari ini (angin,
  hujan, tinggi lapisan batas, suhu, kelembapan),
* hari dalam pekan.

Tiga penaksir dibandingkan secara jujur dengan uji maju (walk-forward):
``persistensi`` (koreksi = 0), ``Ridge`` (koreksi linear teregularisasi), dan
``GradientBoosting`` (koreksi dari pohon keputusan bertingkat). Yang MAE-nya
terendah di antara dua model ML dipakai; MAE persistensi selalu ditampilkan di
sebelahnya. Prakiraan CAMS dari Open-Meteo adalah pembanding: ia model
fisika-kimia penuh, kita hanya statistik dari 60 hari data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src import analisis

CUACA = ["angin", "hujan", "blh", "suhu", "rh"]
FITUR = ["lag1", "rata7_minus_lag1", *CUACA, *[f"d_{k}" for k in CUACA], "dow_sin", "dow_cos", "akhir_pekan"]
HARI_UJI = 21          # panjang jendela uji maju
MIN_JAM_LENGKAP = 20   # hari dianggap lengkap bila ≥ 20 jam pengamatan
MIN_BARIS_LATIH = 40   # di bawah ini model tidak dilatih
LABEL_MODEL = {"persistensi": "Persistence (besok = hari ini)", "ridge": "Ridge regression", "gbr": "Gradient boosting"}


@dataclass
class HasilPrakiraan:
    tanggal: date
    per_titik: pd.DataFrame
    per_sel: pd.DataFrame
    per_jam: pd.DataFrame
    backtest: pd.DataFrame
    model_terpilih: str
    pentingnya_fitur: pd.Series
    n_latih: int


# ---------------------------------------------------------------------------
# Penyusunan tabel harian dan fitur
# ---------------------------------------------------------------------------

def tabel_harian(jam: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per (sel, tanggal) untuk semua hari, termasuk hari prakiraan.

    ``pm2_5`` adalah rata-rata jam pengamatan saja (NaN bila belum ada), sedangkan
    ``pm2_5_cams`` memakai semua jam, sehingga untuk besok berisi prakiraan CAMS.
    Variabel cuaca dirata-rata dari semua titik dalam sel dan memakai semua jam,
    karena untuk besok memang prakiraan cuacalah yang dipakai sebagai fitur.
    """
    d = jam.copy()
    d["tanggal"] = d["waktu"].dt.date
    d["pm2_5_obs"] = d["pm2_5"].where(~d["prakiraan"])
    per_jam_sel = d.groupby(["sel", "lat_sel", "lon_sel", "tanggal", "waktu"], as_index=False).agg(
        pm2_5_obs=("pm2_5_obs", "mean"), pm2_5=("pm2_5", "mean"), angin=("angin", "mean"), hujan=("hujan", "mean"), blh=("blh", "mean"), suhu=("suhu", "mean"), rh=("rh", "mean")
    )
    g = per_jam_sel.groupby(["sel", "lat_sel", "lon_sel", "tanggal"], as_index=False).agg(
        pm2_5=("pm2_5_obs", "mean"),
        n_obs=("pm2_5_obs", "count"),
        pm2_5_cams=("pm2_5", "mean"),
        angin=("angin", "mean"),
        hujan=("hujan", "sum"),
        blh=("blh", "mean"),
        suhu=("suhu", "mean"),
        rh=("rh", "mean"),
    )
    return g.sort_values(["sel", "tanggal"]).reset_index(drop=True)


def tambah_fitur(harian: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan lag, perubahan cuaca, dan fitur kalender. Lag dihitung per sel dari ``pm2_5`` pengamatan."""
    h = harian.copy()
    g = h.groupby("sel")
    h["lag1"] = g["pm2_5"].shift(1)
    h["lag2"] = g["pm2_5"].shift(2)
    h["rata7"] = g["pm2_5"].transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    h["rata7_minus_lag1"] = h["rata7"] - h["lag1"]
    for k in CUACA:
        h[f"d_{k}"] = h[k] - g[k].shift(1)
    dow = pd.to_datetime(h["tanggal"]).dt.day_of_week
    h["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    h["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    h["akhir_pekan"] = (dow >= 5).astype(float)
    return h


def _bisa_dilatih(h: pd.DataFrame) -> pd.DataFrame:
    return h[(h["n_obs"] >= MIN_JAM_LENGKAP) & h[FITUR].notna().all(axis=1) & h["pm2_5"].notna()]


def buat_model(nama: str):
    if nama == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if nama == "gbr":
        return GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, min_samples_leaf=5, random_state=42)
    raise ValueError(nama)


def latih(nama: str, data: pd.DataFrame):
    """Latih model koreksi: target = pm2_5 − lag1."""
    return buat_model(nama).fit(data[FITUR], data["pm2_5"] - data["lag1"])


def prediksi(model, data: pd.DataFrame) -> np.ndarray:
    """Kadar besok = hari ini + koreksi model, tidak boleh di bawah 1 µg/m³."""
    return np.clip(data["lag1"].to_numpy() + model.predict(data[FITUR]), 1.0, None)


# ---------------------------------------------------------------------------
# Uji maju dan prakiraan
# ---------------------------------------------------------------------------

def uji_maju(data: pd.DataFrame, hari_uji: int = HARI_UJI) -> pd.DataFrame:
    """Walk-forward: untuk tiap hari uji, latih hanya dengan hari-hari sebelumnya.

    Mengembalikan tabel per model: mae, rmse, bias (rata-rata prediksi − aktual), n.
    """
    tanggal = sorted(data["tanggal"].unique())
    hari_uji = min(hari_uji, max(len(tanggal) - 7, 0))
    if hari_uji == 0:
        return pd.DataFrame(columns=["model", "mae", "rmse", "bias", "n"])
    uji_tgl = tanggal[-hari_uji:]
    hasil: dict[str, list[np.ndarray]] = {"persistensi": [], "ridge": [], "gbr": []}
    aktual: list[np.ndarray] = []
    for t in uji_tgl:
        tr = data[data["tanggal"] < t]
        te = data[data["tanggal"] == t]
        if te.empty or len(tr) < MIN_BARIS_LATIH:
            continue
        aktual.append(te["pm2_5"].to_numpy())
        hasil["persistensi"].append(te["lag1"].to_numpy())
        for nama in ("ridge", "gbr"):
            hasil[nama].append(prediksi(latih(nama, tr), te))
    y = np.concatenate(aktual) if aktual else np.array([])
    baris = []
    for nama, daftar in hasil.items():
        p = np.concatenate(daftar) if daftar else np.array([])
        if p.size == 0:
            continue
        err = p - y
        baris.append({"model": nama, "mae": float(np.abs(err).mean()), "rmse": float(np.sqrt((err**2).mean())), "bias": float(err.mean()), "n": int(p.size)})
    return pd.DataFrame(baris)


def profil_diurnal(jam: pd.DataFrame, hari: int = 14) -> pd.DataFrame:
    """Faktor per (sel, jam-dalam-hari): rasio PM2.5 jam itu terhadap rata-rata harinya, dinormalkan ke rata-rata 1."""
    p = jam[~jam["prakiraan"]].copy()
    batas = p["waktu"].max().normalize() - pd.Timedelta(days=hari)
    p = p[p["waktu"] >= batas]
    p["tanggal"] = p["waktu"].dt.date
    p["jam"] = p["waktu"].dt.hour
    rata_hari = p.groupby(["sel", "tanggal"])["pm2_5"].transform("mean")
    p["rasio"] = p["pm2_5"] / rata_hari.where(rata_hari > 0)
    prof = p.groupby(["sel", "jam"], as_index=False)["rasio"].mean()
    prof["rasio"] = prof["rasio"] / prof.groupby("sel")["rasio"].transform("mean")
    return prof


def latih_dan_prakirakan(jam: pd.DataFrame, sekarang: pd.Timestamp | None = None) -> HasilPrakiraan:
    """Jalankan seluruh alur: tabel harian → fitur → uji maju → pilih model → prakiraan besok."""
    sekarang = sekarang or analisis.waktu_sekarang(jam)
    hari_ini, besok = sekarang.date(), sekarang.date() + timedelta(days=1)
    h = tambah_fitur(tabel_harian(jam))
    data = _bisa_dilatih(h[h["tanggal"] < hari_ini])
    if len(data) < MIN_BARIS_LATIH:
        raise ValueError(f"data latih terlalu sedikit ({len(data)} baris)")
    backtest = uji_maju(data)

    # Pilih model ML dengan MAE terendah; persistensi hanya pembanding.
    ml = backtest[backtest["model"].isin(["ridge", "gbr"])]
    terpilih = str(ml.sort_values("mae").iloc[0]["model"]) if not ml.empty else "ridge"
    model = latih(terpilih, data)

    # Baris besok per sel. "Hari ini" = rata-rata jam yang sudah lewat (hari belum lengkap, lihat dokumentasi).
    kini = h[h["tanggal"] == hari_ini].set_index("sel")
    target = h[h["tanggal"] == besok].copy()
    if target.empty:
        raise ValueError("tidak ada baris prakiraan untuk besok dalam data")
    target["hari_ini"] = target["sel"].map(kini["pm2_5"])
    target["n_jam_hari_ini"] = target["sel"].map(kini["n_obs"]).fillna(0).astype(int)
    target["lag1"] = target["hari_ini"]
    target["rata7"] = target["rata7"].fillna(target["sel"].map(kini["rata7"]))
    target["rata7_minus_lag1"] = target["rata7"] - target["lag1"]
    for k in CUACA:
        target[f"d_{k}"] = target[k] - target["sel"].map(kini[k])
    for k in FITUR + ["hari_ini"]:
        target[k] = target[k].fillna(data[k].median() if k in data.columns else data["pm2_5"].median())
    target["besok_ml"] = prediksi(model, target)
    target["besok_persistensi"] = target["hari_ini"]
    target["besok_cams"] = target["pm2_5_cams"]
    target["ispu_besok"] = analisis.ispu_pm25(target["besok_ml"])
    target["kategori_besok"] = analisis.kategori_ispu(target["ispu_besok"])
    target["delta"] = target["besok_ml"] - target["hari_ini"]
    kolom_sel = ["sel", "lat_sel", "lon_sel", "hari_ini", "n_jam_hari_ini", "besok_ml", "besok_persistensi", "besok_cams", "ispu_besok", "kategori_besok", "delta", "angin", "hujan", "blh"]
    per_sel = target[kolom_sel].reset_index(drop=True)

    titik = jam[["titik", "kota", "wilayah", "lat", "lon", "sel"]].drop_duplicates("titik")
    per_titik = titik.merge(per_sel, on="sel", how="inner").sort_values(["besok_ml", "titik"], ascending=[False, True]).reset_index(drop=True)

    # Profil per jam besok: rata-rata harian ML × faktor diurnal per sel, dirata-rata se-wilayah (berbobot jumlah titik per sel).
    prof = profil_diurnal(jam)
    pj = prof.merge(per_titik[["titik", "sel", "besok_ml"]], on="sel")
    pj["pm2_5_ml"] = pj["besok_ml"] * pj["rasio"]
    per_jam = pj.groupby("jam", as_index=False)["pm2_5_ml"].mean()
    cams_besok = jam[jam["waktu"].dt.date == besok].groupby(jam["waktu"].dt.hour)["pm2_5"].mean().rename("pm2_5_cams")
    per_jam = per_jam.merge(cams_besok, left_on="jam", right_index=True, how="left")
    per_jam["waktu"] = pd.Timestamp(besok).tz_localize(jam["waktu"].dt.tz) + pd.to_timedelta(per_jam["jam"], unit="h")

    if terpilih == "gbr":
        penting = pd.Series(model.feature_importances_, index=FITUR)
    else:
        penting = pd.Series(np.abs(model[-1].coef_), index=FITUR)
    penting = (penting / penting.sum()).sort_values(ascending=False)

    return HasilPrakiraan(
        tanggal=besok, per_titik=per_titik, per_sel=per_sel, per_jam=per_jam[["waktu", "jam", "pm2_5_ml", "pm2_5_cams"]],
        backtest=backtest, model_terpilih=terpilih, pentingnya_fitur=penting, n_latih=int(len(data)),
    )
