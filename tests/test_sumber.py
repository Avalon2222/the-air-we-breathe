"""Pengujian parser dan pemuat data, tanpa jaringan."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src import sumber


def titik_uji() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nama": ["Menteng", "Bogor Tengah"],
            "kota": ["Jakarta", "Bogor"],
            "wilayah": ["Jakarta Pusat", "Kota Bogor"],
            "lat": [-6.195, -6.597],
            "lon": [106.832, 106.800],
        }
    )


def payload_open_meteo(n_jam: int = 30, var: dict | None = None, n_lokasi: int = 2) -> list:
    """Tiruan balasan Open-Meteo untuk ``n_lokasi`` lokasi dengan ``n_jam`` jam mulai 2026-10-01 00:00."""
    var = var or sumber.VAR_UDARA
    waktu = pd.date_range("2026-10-01 00:00", periods=n_jam, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    blok = []
    for i in range(n_lokasi):
        hourly = {"time": waktu}
        for j, nama in enumerate(var):
            hourly[nama] = [round(10 + i * 5 + j + (k % 24) * 0.5, 1) for k in range(n_jam)]
        blok.append({"latitude": -6.2 - 0.4 * i, "longitude": 106.8, "hourly_units": {}, "hourly": hourly})
    return blok


def test_muat_titik_statis_valid():
    t = sumber.muat_titik()
    assert list(t.columns) == sumber.KOLOM_TITIK
    assert len(t) == 51
    assert t["nama"].is_unique
    assert t["lat"].between(-7.0, -5.5).all() and t["lon"].between(106.2, 107.4).all()
    assert set(t["kota"]) == {"Jakarta", "Bogor", "Depok", "Tangerang", "Bekasi"}


def test_parse_open_meteo_banyak_lokasi():
    df = sumber.parse_open_meteo(payload_open_meteo(), titik_uji(), sumber.VAR_UDARA)
    assert len(df) == 60
    assert set(df["titik"]) == {"Menteng", "Bogor Tengah"}
    assert str(df["waktu"].dt.tz) == "Asia/Jakarta"
    assert list(sumber.VAR_UDARA.values()) == [c for c in df.columns if c in sumber.VAR_UDARA.values()]
    menteng = df[df["titik"] == "Menteng"].iloc[0]
    assert menteng["pm2_5"] == 10.0 and menteng["pm10"] == 11.0 and menteng["lat"] == -6.195


def test_parse_open_meteo_satu_lokasi_dict():
    satu = payload_open_meteo(n_lokasi=1)[0]
    df = sumber.parse_open_meteo(satu, titik_uji().head(1), sumber.VAR_UDARA)
    assert len(df) == 30 and df["titik"].iloc[0] == "Menteng"


def test_parse_open_meteo_jumlah_lokasi_salah():
    with pytest.raises(ValueError):
        sumber.parse_open_meteo(payload_open_meteo(n_lokasi=3), titik_uji(), sumber.VAR_UDARA)


def test_parse_open_meteo_nilai_null_jadi_nan():
    p = payload_open_meteo(n_jam=3, n_lokasi=1)
    p[0]["hourly"]["pm2_5"] = [1.0, None, 3.0]
    df = sumber.parse_open_meteo(p, titik_uji().head(1), sumber.VAR_UDARA)
    assert df["pm2_5"].isna().sum() == 1


def test_gabung_menandai_prakiraan_dan_sel():
    t = titik_uji()
    udara = sumber.parse_open_meteo(payload_open_meteo(n_jam=48), t, sumber.VAR_UDARA)
    cuaca = sumber.parse_open_meteo(payload_open_meteo(n_jam=48, var=sumber.VAR_CUACA), t, sumber.VAR_CUACA)
    # "Diambil" pada 2026-10-01 10:30 WIB = 03:30 UTC → jam 11:00 WIB ke atas adalah prakiraan.
    jam = sumber.gabung(udara, cuaca, datetime(2026, 10, 1, 3, 30, tzinfo=timezone.utc))
    assert list(jam.columns) == sumber.KOLOM_JAM
    assert jam["prakiraan"].sum() == 2 * 37
    hari_pertama = jam["waktu"].dt.day == 1
    assert not jam.loc[hari_pertama & (jam["waktu"].dt.hour == 10), "prakiraan"].any()
    assert jam.loc[hari_pertama & (jam["waktu"].dt.hour == 11), "prakiraan"].all()
    assert jam["angin"].notna().all()
    assert set(jam["sel"]) == {"-6.0,106.8", "-6.4,106.8"}


def test_gabung_membuang_baris_tanpa_pm25():
    t = titik_uji().head(1)
    p = payload_open_meteo(n_jam=3, n_lokasi=1)
    p[0]["hourly"]["pm2_5"] = [1.0, None, 3.0]
    udara = sumber.parse_open_meteo(p, t, sumber.VAR_UDARA)
    cuaca = sumber.parse_open_meteo(payload_open_meteo(n_jam=3, var=sumber.VAR_CUACA, n_lokasi=1), t, sumber.VAR_CUACA)
    jam = sumber.gabung(udara, cuaca, datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert len(jam) == 2


@pytest.mark.parametrize(
    "lat,lon,lat_sel,lon_sel",
    [(-6.195, 106.832, -6.0, 106.8), (-6.597, 106.800, -6.4, 106.8), (-6.2, 106.45, -6.0, 106.4), (-6.26, 106.56, -6.4, 106.4), (-5.745, 106.613, -5.6, 106.8), (-6.245, 107.01, -6.4, 107.2)],
)
def test_sel_grid_mengikuti_kisi_open_meteo(lat, lon, lat_sel, lon_sel):
    # Pusat sel CAMS global di kelipatan 0,4°, batas sel di pusat ± 0,2°; pasangan ini dicocokkan dengan pengelompokan nilai nyata.
    a, b = sumber.sel_grid(lat, lon)
    assert (float(a), float(b)) == (lat_sel, lon_sel)


def test_sample_titik_sesel_berbagi_deret_pm25():
    """Memastikan asumsi grid 0,4°: semua titik dalam satu sel punya deret PM2.5 yang identik di data contoh."""
    jam, _ = sumber.muat_sample()
    piv = jam.pivot(index="waktu", columns="titik", values="pm2_5")
    for sel, g in jam.drop_duplicates("titik").groupby("sel"):
        kolom = g["titik"].tolist()
        assert (piv[kolom].nunique(axis=1) == 1).all(), f"sel {sel} berisi deret yang berbeda: {kolom}"
    assert 5 <= jam["sel"].nunique() <= 12


def test_muat_sample_bentuk_dan_meta():
    jam, meta = sumber.muat_sample()
    assert list(jam.columns) == sumber.KOLOM_JAM
    assert jam["titik"].nunique() == 51
    assert str(jam["waktu"].dt.tz) == "Asia/Jakarta"
    assert jam["prakiraan"].dtype == bool and jam["prakiraan"].any() and (~jam["prakiraan"]).any()
    assert jam["pm2_5"].notna().all() and (jam["pm2_5"] >= 0).all()
    assert meta["jumlah_titik"] == 51 and "diambil" in meta
    # Riwayat cukup panjang untuk melatih model.
    assert (jam["waktu"].max() - jam["waktu"].min()).days >= 30


def test_muat_semua_paksa_offline_tanpa_jaringan():
    h = sumber.muat_semua(paksa_offline=True, dengan_openaq=False)
    assert h.offline and not h.jam.empty and len(h.titik) == 51
    assert h.stasiun.empty
    assert "data contoh" in h.sumber["udara"]


def test_parse_openaq_lokasi_memilih_sensor_pm25():
    payload = {
        "results": [
            {"id": 1, "name": "Kemayoran", "coordinates": {"latitude": -6.16, "longitude": 106.85}, "provider": {"name": "AirNow"}, "sensors": [{"id": 11, "parameter": {"id": 1, "name": "pm10"}}, {"id": 12, "parameter": {"id": 2, "name": "pm25"}}]},
            {"id": 2, "name": "Tanpa PM2.5", "coordinates": {"latitude": -6.2, "longitude": 106.8}, "sensors": [{"id": 21, "parameter": {"id": 1, "name": "pm10"}}]},
            {"id": 3, "name": "Tanpa koordinat", "coordinates": None, "sensors": [{"id": 31, "parameter": {"id": 2, "name": "pm25"}}]},
        ]
    }
    df = sumber.parse_openaq_lokasi(payload)
    assert len(df) == 1 and df.iloc[0]["id_sensor"] == 12 and df.iloc[0]["penyedia"] == "AirNow"


def test_parse_openaq_terbaru():
    payload = {"results": [{"sensorsId": 11, "value": 80.0, "datetime": {"utc": "2026-10-01T03:00:00Z"}}, {"sensorsId": 12, "value": 42.5, "datetime": {"utc": "2026-10-01T03:00:00Z"}}]}
    nilai, waktu = sumber.parse_openaq_terbaru(payload, 12)
    assert nilai == 42.5 and waktu.hour == 10 and str(waktu.tz) == "Asia/Jakarta"
    assert sumber.parse_openaq_terbaru(payload, 99) == (None, None)


def test_simpan_dan_muat_sample_bolak_balik(tmp_path, monkeypatch):
    jam, meta = sumber.muat_sample()
    kecil = jam[jam["titik"].isin(["Menteng", "Cibinong"])].head(200)
    monkeypatch.setattr(sumber, "DIR_SAMPLE", tmp_path)
    sumber.simpan_sample(kecil, {"diambil": "2026-10-01 00:00 UTC", "jumlah_titik": 2})
    ulang, meta2 = sumber.muat_sample()
    assert len(ulang) == len(kecil) and meta2["jumlah_titik"] == 2
    assert np.allclose(ulang["pm2_5"].to_numpy(), kecil["pm2_5"].round(2).to_numpy())
    assert (ulang["waktu"].to_numpy() == kecil["waktu"].to_numpy()).all()
