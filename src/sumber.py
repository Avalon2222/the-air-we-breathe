"""Pengambilan dan normalisasi data kualitas udara dan cuaca Jabodetabek.

Dua sumber utama, keduanya gratis dan tanpa kunci API:

* **Open-Meteo Air Quality API**: PM2.5, PM10, NO2, O3, CO, SO2 per jam untuk
  setiap titik di ``data/titik.csv``, mencakup riwayat beberapa pekan ke belakang
  dan prakiraan dua hari ke depan. Nilainya berasal dari model atmosfer CAMS
  (Copernicus) global beresolusi sekitar 0,4° (~40 km), bukan dari sensor, sehingga
  seluruh Jabodetabek hanya ditutupi sekitar delapan sel; titik-titik dalam satu
  sel bernilai sama. Kolom ``sel``/``lat_sel``/``lon_sel`` menandai sel itu.
* **Open-Meteo Forecast API**: suhu, kelembapan, hujan, angin, dan tinggi lapisan
  batas atmosfer per jam untuk titik yang sama. Dipakai sebagai fitur model.

Satu sumber opsional, **OpenAQ v3**, memberi pembacaan sensor sungguhan di
lapangan. API-nya gratis tetapi perlu kunci; bila ``OPENAQ_API_KEY`` tersedia
(variabel lingkungan atau ``st.secrets``), stasiun ditampilkan di peta.

Semua fungsi ``parse_*`` murni (tanpa jaringan) agar mudah diuji. Jika jaringan
gagal, ``muat_semua`` jatuh ke berkas contoh di ``data/sample``.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
DIR_SAMPLE = DIR_DATA / "sample"
BERKAS_TITIK = DIR_DATA / "titik.csv"

URL_UDARA = "https://air-quality-api.open-meteo.com/v1/air-quality"
URL_CUACA = "https://api.open-meteo.com/v1/forecast"
URL_OPENAQ = "https://api.openaq.org/v3"

ZONA = "Asia/Jakarta"
UKURAN_SEL = 0.4       # derajat; jarak grid CAMS global yang dipakai Open-Meteo di luar Eropa
HARI_RIWAYAT = 60      # riwayat untuk melatih model (maks. 92 di Open-Meteo)
HARI_PRAKIRAAN = 2     # hari ini sisa jam + besok (+ lusa sebagai cadangan)

# Nama variabel di Open-Meteo -> nama kolom kita.
VAR_UDARA = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "ozone": "o3",
    "carbon_monoxide": "co",
    "sulphur_dioxide": "so2",
}
VAR_CUACA = {
    "temperature_2m": "suhu",
    "relative_humidity_2m": "rh",
    "precipitation": "hujan",
    "wind_speed_10m": "angin",
    "wind_direction_10m": "arah_angin",
    "boundary_layer_height": "blh",
}

KOLOM_TITIK = ["nama", "kota", "wilayah", "lat", "lon"]
KOLOM_JAM = ["titik", "kota", "wilayah", "lat", "lon", "sel", "lat_sel", "lon_sel", "waktu", *VAR_UDARA.values(), *VAR_CUACA.values(), "prakiraan"]

# Kotak Jabodetabek untuk pencarian stasiun OpenAQ: lon_min, lat_min, lon_maks, lat_maks.
KOTAK_JABODETABEK = (106.30, -6.85, 107.30, -5.60)
ID_PARAMETER_PM25 = 2  # id parameter "pm25" di OpenAQ

TIMEOUT = 40
HEADERS = {"User-Agent": "the-air-we-breathe/1.0 (proyek edukasi; data publik)"}


@dataclass
class HasilMuat:
    """Hasil ``muat_semua``: tabel per jam plus catatan asal datanya."""

    jam: pd.DataFrame
    titik: pd.DataFrame
    stasiun: pd.DataFrame
    waktu_ambil: datetime
    offline: bool = False
    sumber: dict[str, str] = field(default_factory=dict)
    kesalahan: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Titik pantau
# ---------------------------------------------------------------------------

def muat_titik(berkas: Path = BERKAS_TITIK) -> pd.DataFrame:
    """Baca daftar titik pantau (kecamatan/kawasan) Jabodetabek."""
    df = pd.read_csv(berkas)
    df = df[KOLOM_TITIK].copy()
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Parser murni Open-Meteo
# ---------------------------------------------------------------------------

def _bingkai_kosong() -> pd.DataFrame:
    df = pd.DataFrame({k: pd.Series(dtype="float64") for k in KOLOM_JAM})
    for k in ("titik", "kota", "wilayah", "sel"):
        df[k] = df[k].astype("object")
    df["waktu"] = pd.to_datetime(df["waktu"]).dt.tz_localize(ZONA)
    df["prakiraan"] = df["prakiraan"].astype(bool)
    return df


def parse_open_meteo(payload: dict | list, titik: pd.DataFrame, peta_var: dict[str, str]) -> pd.DataFrame:
    """Ubah balasan Open-Meteo (satu atau banyak lokasi) menjadi tabel panjang.

    Open-Meteo mengembalikan ``dict`` untuk satu lokasi dan ``list`` untuk banyak
    lokasi, dengan urutan yang sama seperti koordinat yang diminta. Koordinat
    di balasan sudah "ditempelkan" ke grid model, jadi kita memakai urutan,
    bukan koordinat, untuk mencocokkan dengan ``titik``.
    """
    blok = payload if isinstance(payload, list) else [payload]
    if len(blok) != len(titik):
        raise ValueError(f"Open-Meteo mengembalikan {len(blok)} lokasi, diminta {len(titik)}")
    potongan = []
    for (_, t), b in zip(titik.iterrows(), blok):
        h = b.get("hourly", {})
        if not h.get("time"):
            continue
        df = pd.DataFrame({"waktu": pd.to_datetime(h["time"])})
        for var_api, kolom in peta_var.items():
            df[kolom] = pd.to_numeric(pd.Series(h.get(var_api, [None] * len(df))), errors="coerce")
        df.insert(0, "titik", t["nama"])
        df.insert(1, "kota", t["kota"])
        df.insert(2, "wilayah", t["wilayah"])
        df.insert(3, "lat", float(t["lat"]))
        df.insert(4, "lon", float(t["lon"]))
        potongan.append(df)
    if not potongan:
        return pd.DataFrame(columns=["titik", "kota", "wilayah", "lat", "lon", "waktu", *peta_var.values()])
    hasil = pd.concat(potongan, ignore_index=True)
    hasil["waktu"] = hasil["waktu"].dt.tz_localize(ZONA)
    return hasil


def sel_grid(lat, lon, ukuran: float = UKURAN_SEL):
    """Pusat sel grid CAMS global tempat koordinat itu jatuh.

    Grid CAMS global berjarak 0,4° dengan pusat sel di kelipatan 0,4° (…, -6.4, -6.0, …;
    …, 106.8, 107.2, …), sehingga batas sel ada di pusat ± 0,2°. Semua titik dalam satu
    sel menerima deret PM2.5 yang persis sama dari Open-Meteo; itulah yang membuat
    label ini penting untuk peta dan model. Lihat ``tests/test_sumber.py``.
    """
    lat_sel = np.floor((np.asarray(lat, dtype=float) + ukuran / 2) / ukuran) * ukuran
    lon_sel = np.floor((np.asarray(lon, dtype=float) + ukuran / 2) / ukuran) * ukuran
    return np.round(lat_sel, 1), np.round(lon_sel, 1)


def gabung(udara: pd.DataFrame, cuaca: pd.DataFrame, waktu_ambil: datetime) -> pd.DataFrame:
    """Gabungkan tabel udara dan cuaca per (titik, waktu) lalu tandai jam prakiraan."""
    kunci = ["titik", "waktu"]
    kolom_cuaca = kunci + [k for k in VAR_CUACA.values() if k in cuaca.columns]
    df = udara.merge(cuaca[kolom_cuaca], on=kunci, how="left")
    for k in VAR_CUACA.values():
        if k not in df.columns:
            df[k] = float("nan")
    batas = pd.Timestamp(waktu_ambil).tz_convert(ZONA).floor("h")
    df["prakiraan"] = df["waktu"] > batas
    df["lat_sel"], df["lon_sel"] = sel_grid(df["lat"], df["lon"])
    df["sel"] = df["lat_sel"].map(lambda v: f"{v:.1f}") + "," + df["lon_sel"].map(lambda v: f"{v:.1f}")
    df = df.dropna(subset=["pm2_5"]).sort_values(kunci).reset_index(drop=True)
    return df[KOLOM_JAM]


# ---------------------------------------------------------------------------
# Parser murni OpenAQ
# ---------------------------------------------------------------------------

def parse_openaq_lokasi(payload: dict) -> pd.DataFrame:
    """Daftar lokasi OpenAQ v3 (``/v3/locations``) -> id, nama, koordinat, id sensor PM2.5."""
    baris = []
    for r in payload.get("results", []):
        koord = r.get("coordinates") or {}
        sensor_pm25 = [s.get("id") for s in r.get("sensors", []) if (s.get("parameter") or {}).get("id") == ID_PARAMETER_PM25]
        if not sensor_pm25 or koord.get("latitude") is None:
            continue
        baris.append(
            {
                "id_lokasi": r.get("id"),
                "nama": str(r.get("name") or f"Lokasi {r.get('id')}"),
                "lat": float(koord["latitude"]),
                "lon": float(koord["longitude"]),
                "id_sensor": sensor_pm25[0],
                "penyedia": str((r.get("provider") or {}).get("name") or ""),
            }
        )
    return pd.DataFrame(baris, columns=["id_lokasi", "nama", "lat", "lon", "id_sensor", "penyedia"])


def parse_openaq_terbaru(payload: dict, id_sensor: int) -> tuple[float | None, pd.Timestamp | None]:
    """Nilai PM2.5 terbaru dari ``/v3/locations/{id}/latest`` untuk satu sensor."""
    for r in payload.get("results", []):
        if r.get("sensorsId") == id_sensor and r.get("value") is not None:
            waktu = (r.get("datetime") or {}).get("utc")
            ts = pd.to_datetime(waktu, utc=True).tz_convert(ZONA) if waktu else None
            return float(r["value"]), ts
    return None, None


# ---------------------------------------------------------------------------
# Pengambilan dari jaringan
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list:
    r = requests.get(url, params=params, timeout=TIMEOUT, headers={**HEADERS, **(headers or {})})
    r.raise_for_status()
    return r.json()


def _params_dasar(titik: pd.DataFrame, hari_riwayat: int, hari_prakiraan: int) -> dict:
    return {
        "latitude": ",".join(f"{v:.4f}" for v in titik["lat"]),
        "longitude": ",".join(f"{v:.4f}" for v in titik["lon"]),
        "timezone": ZONA,
        "past_days": hari_riwayat,
        "forecast_days": hari_prakiraan,
    }


def ambil_udara(titik: pd.DataFrame, hari_riwayat: int = HARI_RIWAYAT, hari_prakiraan: int = HARI_PRAKIRAAN) -> pd.DataFrame:
    params = {**_params_dasar(titik, hari_riwayat, hari_prakiraan), "hourly": ",".join(VAR_UDARA)}
    return parse_open_meteo(_get_json(URL_UDARA, params), titik, VAR_UDARA)


def ambil_cuaca(titik: pd.DataFrame, hari_riwayat: int = HARI_RIWAYAT, hari_prakiraan: int = HARI_PRAKIRAAN) -> pd.DataFrame:
    params = {**_params_dasar(titik, hari_riwayat, hari_prakiraan), "hourly": ",".join(VAR_CUACA)}
    return parse_open_meteo(_get_json(URL_CUACA, params), titik, VAR_CUACA)


def kunci_openaq() -> str | None:
    """Kunci OpenAQ dari variabel lingkungan atau ``st.secrets`` (jika Streamlit aktif)."""
    kunci = os.environ.get("OPENAQ_API_KEY")
    if kunci:
        return kunci
    try:
        import streamlit as st

        return st.secrets.get("OPENAQ_API_KEY")  # type: ignore[return-value]
    except Exception:
        return None


def ambil_openaq(api_key: str, maks_lokasi: int = 40) -> pd.DataFrame:
    """Pembacaan PM2.5 terbaru dari stasiun OpenAQ di dalam kotak Jabodetabek."""
    h = {"X-API-Key": api_key}
    lokasi = parse_openaq_lokasi(
        _get_json(f"{URL_OPENAQ}/locations", {"bbox": ",".join(str(v) for v in KOTAK_JABODETABEK), "parameters_id": ID_PARAMETER_PM25, "limit": 200}, h)
    )
    baris = []
    for _, l in lokasi.head(maks_lokasi).iterrows():
        try:
            nilai, waktu = parse_openaq_terbaru(_get_json(f"{URL_OPENAQ}/locations/{l['id_lokasi']}/latest", {"limit": 100}, h), l["id_sensor"])
        except requests.RequestException:
            continue
        if nilai is None:
            continue
        baris.append({"nama": l["nama"], "lat": l["lat"], "lon": l["lon"], "pm2_5": nilai, "waktu": waktu, "penyedia": l["penyedia"]})
    return pd.DataFrame(baris, columns=["nama", "lat", "lon", "pm2_5", "waktu", "penyedia"])


# ---------------------------------------------------------------------------
# Data contoh (offline) dan pemuat utama
# ---------------------------------------------------------------------------

def muat_sample() -> tuple[pd.DataFrame, dict]:
    """Tabel per jam dari ``data/sample/jam.csv.gz`` beserta metadatanya."""
    meta = json.loads((DIR_SAMPLE / "meta.json").read_text(encoding="utf-8"))
    with gzip.open(DIR_SAMPLE / "jam.csv.gz", "rt", encoding="utf-8") as f:
        df = pd.read_csv(f)
    df["waktu"] = pd.to_datetime(df["waktu"], utc=True).dt.tz_convert(ZONA)
    df["prakiraan"] = df["prakiraan"].astype(bool)
    return df[KOLOM_JAM], meta


def simpan_sample(jam: pd.DataFrame, meta: dict) -> None:
    DIR_SAMPLE.mkdir(parents=True, exist_ok=True)
    keluar = jam.copy()
    keluar["waktu"] = keluar["waktu"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    with gzip.open(DIR_SAMPLE / "jam.csv.gz", "wt", encoding="utf-8", newline="") as f:
        keluar.to_csv(f, index=False, float_format="%.2f")
    (DIR_SAMPLE / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def muat_semua(paksa_offline: bool = False, dengan_openaq: bool = True, hari_riwayat: int = HARI_RIWAYAT) -> HasilMuat:
    """Ambil semua data; bila gagal, pakai data contoh. Tidak pernah melempar karena jaringan."""
    titik = muat_titik()
    kesalahan: list[str] = []
    stasiun = pd.DataFrame(columns=["nama", "lat", "lon", "pm2_5", "waktu", "penyedia"])
    sumber: dict[str, str] = {}
    waktu_ambil = datetime.now(timezone.utc)

    jam: pd.DataFrame | None = None
    if not paksa_offline:
        try:
            udara = ambil_udara(titik, hari_riwayat)
            cuaca = ambil_cuaca(titik, hari_riwayat)
            jam = gabung(udara, cuaca, waktu_ambil)
            if jam.empty:
                raise ValueError("balasan kosong")
            sumber["udara"] = f"Open-Meteo CAMS · {titik.shape[0]} titik · {hari_riwayat} hari riwayat"
            sumber["cuaca"] = "Open-Meteo Forecast"
        except (requests.RequestException, ValueError, KeyError) as e:
            kesalahan.append(f"Open-Meteo gagal: {type(e).__name__}: {str(e)[:80]}")
            jam = None

    offline = jam is None
    if offline:
        jam, meta = muat_sample()
        waktu_ambil = datetime.strptime(meta["diambil"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        sumber["udara"] = f"data contoh ({meta['diambil']})"
        sumber["cuaca"] = "data contoh"

    if dengan_openaq and not paksa_offline:
        kunci = kunci_openaq()
        if kunci:
            try:
                stasiun = ambil_openaq(kunci)
                sumber["stasiun"] = f"OpenAQ · {len(stasiun)} stasiun"
            except (requests.RequestException, ValueError, KeyError) as e:
                kesalahan.append(f"OpenAQ gagal: {type(e).__name__}")
        else:
            sumber["stasiun"] = "OpenAQ tidak aktif (tanpa kunci)"

    return HasilMuat(jam=jam, titik=titik, stasiun=stasiun, waktu_ambil=waktu_ambil, offline=offline, sumber=sumber, kesalahan=kesalahan)
