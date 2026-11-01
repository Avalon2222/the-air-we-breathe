"""Pengujian indeks dan ringkasan dengan nilai yang diketahui."""

import numpy as np
import pandas as pd
import pytest

from src import analisis


def buat_jam(n_hari: int = 3, titik: tuple[str, ...] = ("A", "B"), seed: int = 1) -> pd.DataFrame:
    """Tabel per jam buatan: dua titik di sel berbeda, pola harian sinus, 6 jam terakhir prakiraan."""
    rng = np.random.default_rng(seed)
    waktu = pd.date_range("2026-10-01 00:00", periods=24 * n_hari, freq="h", tz="Asia/Jakarta")
    potongan = []
    for i, t in enumerate(titik):
        dasar = 30 + 10 * i
        pm = dasar + 15 * np.sin((waktu.hour - 5) / 24 * 2 * np.pi) + rng.normal(0, 1, len(waktu))
        potongan.append(
            pd.DataFrame(
                {
                    "titik": t, "kota": "Jakarta" if i == 0 else "Bogor", "wilayah": "W", "lat": -6.2 - 0.4 * i, "lon": 106.8,
                    "sel": f"{-6.2 - 0.4 * i:.1f},106.8", "lat_sel": -6.2 - 0.4 * i, "lon_sel": 106.8, "waktu": waktu,
                    "pm2_5": pm, "pm10": pm * 1.2, "no2": 10.0, "o3": 50.0, "co": 400.0, "so2": 5.0,
                    "suhu": 28.0, "rh": 80.0, "hujan": 0.0, "angin": 8.0 + i, "arah_angin": 90.0 + 180 * i, "blh": 500.0,
                    "prakiraan": waktu > waktu[-7],
                }
            )
        )
    return pd.concat(potongan, ignore_index=True)


@pytest.mark.parametrize("c,ispu", [(0, 0), (15.5, 50), (35.45, 76), (55.4, 100), (100.0, 147), (150.4, 200), (250.4, 300), (500, 500), (900, 500)])
def test_ispu_titik_potong(c, ispu):
    assert analisis.ispu_pm25(c) == ispu


@pytest.mark.parametrize("c,aqi", [(0, 0), (9.0, 50), (12.0, 57), (35.4, 100), (55.4, 150), (125.4, 200), (225.4, 300), (325.4, 500)])
def test_aqi_us_titik_potong(c, aqi):
    assert analisis.aqi_us_pm25(c) == aqi


def test_indeks_menerima_series_dan_nan():
    s = pd.Series([10.0, np.nan, 60.0])
    i = analisis.ispu_pm25(s)
    assert isinstance(i, pd.Series) and i.isna().sum() == 1 and i.iloc[2] == 106
    kat = analisis.kategori_ispu(i)
    assert kat.iloc[0] == "Baik" and pd.isna(kat.iloc[1]) and kat.iloc[2] == "Tidak Sehat"
    assert analisis.kategori_ispu(50) == "Baik" and analisis.kategori_ispu(51) == "Sedang" and analisis.kategori_ispu(301) == "Berbahaya"


def test_kategori_aqi_us():
    assert analisis.kategori_aqi_us(50) == "Good"
    assert analisis.kategori_aqi_us(151) == "Unhealthy"
    assert analisis.kategori_aqi_us(pd.Series([10, 120])).tolist() == ["Good", "Unhealthy for Sensitive Groups"]


def test_indeks_monoton_naik():
    c = np.linspace(0, 400, 801)
    assert np.all(np.diff(analisis.ispu_pm25(c)) >= 0)
    assert np.all(np.diff(analisis.aqi_us_pm25(c)) >= 0)


@pytest.mark.parametrize("d,arah", [(0, "U"), (45, "TL"), (90, "T"), (180, "S"), (270, "B"), (359, "U"), (202.5, "BD")])
def test_arah_kompas(d, arah):
    assert analisis.arah_kompas(d) == arah


def test_rata_arah_vektor_melewati_utara():
    assert abs(analisis._rata_arah(pd.Series([350.0, 10.0])) - 0) < 1e-6


def test_waktu_sekarang_jam_pengamatan_terakhir():
    jam = buat_jam()
    assert analisis.waktu_sekarang(jam) == jam.loc[~jam["prakiraan"], "waktu"].max()


def test_kondisi_terkini_dan_ringkasan():
    jam = buat_jam()
    kini = analisis.kondisi_terkini(jam)
    assert len(kini) == 2 and kini["pm2_5"].is_monotonic_decreasing
    assert {"ispu", "kategori_ispu", "aqi_us", "kategori_aqi", "delta_24j", "pm2_5_24j", "arah"} <= set(kini.columns)
    assert kini["delta_24j"].notna().all()
    r = analisis.ringkasan(kini, jam)
    assert r["terburuk"]["titik"] == "B" and r["terbaik"]["titik"] == "A"
    assert r["n_titik"] == 2 and 0 < r["kali_who"] < 10
    assert r["kategori_ispu"] in analisis.KATEGORI_ISPU


def test_harian_per_titik_hanya_pengamatan():
    jam = buat_jam(n_hari=3)
    h = analisis.harian_per_titik(jam)
    assert h["tanggal"].nunique() == 3
    hari_terakhir = h[h["tanggal"] == h["tanggal"].max()]
    assert (hari_terakhir["n_jam"] == 18).all()  # 6 jam terakhir prakiraan dibuang


def test_profil_jam_dan_matriks():
    jam = buat_jam(n_hari=4)
    prof = analisis.profil_jam(jam)
    assert list(prof["jam"]) == list(range(24))
    assert prof.loc[prof["pm2_5"].idxmax(), "jam"] == 11  # puncak sinus di jam 11
    piv = analisis.matriks_jam_hari(jam, hari=2)
    assert piv.shape == (24, 2)


def test_per_kota_dan_hari_per_kategori():
    jam = buat_jam()
    kini = analisis.kondisi_terkini(jam)
    kota = analisis.per_kota(kini)
    assert set(kota["kota"]) == {"Jakarta", "Bogor"} and kota["n"].sum() == 2
    tabel = analisis.hari_per_kategori(analisis.harian_per_titik(jam))
    assert list(tabel.columns) == analisis.KATEGORI_ISPU
    assert tabel.loc["Jakarta"].sum() == 3


def test_hari_di_atas_who():
    jam = buat_jam()
    who = analisis.hari_di_atas_who(analisis.harian_per_titik(jam))
    assert (who["pct_who"] == 100).all()  # dasar 30–40 µg/m³ selalu di atas 15
    assert (who["pct_baku_mutu"] == 0).all()


def test_korelasi_cuaca_mengembalikan_empat_variabel():
    jam = buat_jam(n_hari=6)
    kor = analisis.korelasi_cuaca(analisis.harian_per_titik(jam))
    assert set(kor.index) == {"angin", "hujan", "blh", "suhu"}


def test_akhir_pekan_vs_kerja():
    jam = buat_jam(n_hari=7)  # 1 Okt 2026 Kamis → ada Sabtu dan Minggu
    d = analisis.akhir_pekan_vs_kerja(analisis.harian_per_titik(jam))
    assert set(d["jenis"]) == {"Hari kerja", "Akhir pekan"}
