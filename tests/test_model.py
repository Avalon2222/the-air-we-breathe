"""Pengujian alur prakiraan dengan data sintetis yang polanya diketahui."""

import numpy as np
import pandas as pd
import pytest

from src import analisis, model


def buat_jam_sintetis(n_hari: int = 40, n_sel: int = 3, seed: int = 3) -> pd.DataFrame:
    """PM2.5 harian = 60 − 3·angin − 0,8·hujan + sisa AR(1); dua titik per sel berbagi deret yang sama."""
    rng = np.random.default_rng(seed)
    waktu = pd.date_range("2026-09-01 00:00", periods=24 * n_hari, freq="h", tz="Asia/Jakarta")
    hari = np.arange(n_hari)
    potongan = []
    for s in range(n_sel):
        angin = rng.uniform(3, 15, n_hari)
        hujan = rng.exponential(2, n_hari) * (rng.random(n_hari) < 0.4)
        sisa = np.zeros(n_hari)
        for d in range(1, n_hari):
            sisa[d] = 0.6 * sisa[d - 1] + rng.normal(0, 3)
        harian = np.clip(60 + 5 * s - 3 * angin - 0.8 * hujan + sisa, 5, None)
        profil = 1 + 0.3 * np.sin((waktu.hour - 5) / 24 * 2 * np.pi)
        pm = np.repeat(harian, 24) * profil
        for k in range(2):
            potongan.append(
                pd.DataFrame(
                    {
                        "titik": f"S{s}T{k}", "kota": "Jakarta", "wilayah": "W", "lat": -6.0 - 0.4 * s + 0.05 * k, "lon": 106.8, "sel": f"{-6.0 - 0.4 * s:.1f},106.8",
                        "lat_sel": -6.0 - 0.4 * s, "lon_sel": 106.8, "waktu": waktu, "pm2_5": pm, "pm10": pm * 1.3, "no2": 10.0, "o3": 40.0, "co": 300.0, "so2": 4.0,
                        "suhu": 28.0 + rng.normal(0, 0.5, len(waktu)), "rh": 80.0, "hujan": np.repeat(hujan / 24, 24), "angin": np.repeat(angin, 24) + 0.3 * k,
                        "arah_angin": 90.0, "blh": 600.0, "prakiraan": waktu >= waktu[-30],  # 6 jam sisa hari ini + besok 24 jam
                    }
                )
            )
    return pd.concat(potongan, ignore_index=True)


def test_tabel_harian_per_sel_dan_fitur():
    jam = buat_jam_sintetis(n_hari=10, n_sel=2)
    h = model.tambah_fitur(model.tabel_harian(jam))
    assert h["sel"].nunique() == 2 and len(h) == 20
    hari_ini = h[h["tanggal"] == analisis.waktu_sekarang(jam).date()]
    assert (hari_ini["n_obs"] == 18).all()
    besok = h[h["tanggal"] > analisis.waktu_sekarang(jam).date()]
    assert besok["pm2_5"].isna().all() and besok["pm2_5_cams"].notna().all()
    satu = h[h["sel"] == h["sel"].iloc[0]].reset_index(drop=True)
    assert np.isclose(satu.loc[1, "lag1"], satu.loc[0, "pm2_5"])
    assert np.isnan(satu.loc[0, "lag1"]) and np.isnan(satu.loc[2, "rata7"]) and not np.isnan(satu.loc[3, "rata7"])
    assert np.isclose(satu.loc[1, "d_angin"], satu.loc[1, "angin"] - satu.loc[0, "angin"])
    assert set(model.FITUR) <= set(h.columns)


def test_uji_maju_tidak_bocor_dan_ml_mengalahkan_persistensi():
    jam = buat_jam_sintetis(n_hari=45, n_sel=4)
    h = model.tambah_fitur(model.tabel_harian(jam))
    latih = model._bisa_dilatih(h[h["tanggal"] < analisis.waktu_sekarang(jam).date()])
    bt = model.uji_maju(latih, hari_uji=10).set_index("model")
    assert {"persistensi", "ridge", "gbr"} == set(bt.index)
    assert (bt["n"] == 40).all()
    # Target bergantung kuat pada angin & hujan hari itu, yang tidak diketahui persistensi.
    assert bt.loc["ridge", "mae"] < bt.loc["persistensi", "mae"]
    assert (bt["mae"] > 0).all() and (bt["rmse"] >= bt["mae"]).all()


def test_latih_dan_prakirakan_bentuk_hasil():
    jam = buat_jam_sintetis(n_hari=40, n_sel=3)
    p = model.latih_dan_prakirakan(jam)
    assert p.tanggal == analisis.waktu_sekarang(jam).date() + pd.Timedelta(days=1)
    assert len(p.per_sel) == 3 and len(p.per_titik) == 6
    assert p.model_terpilih in ("ridge", "gbr")
    assert (p.per_titik["besok_ml"] > 0).all() and p.per_titik["besok_cams"].notna().all()
    assert p.per_titik["kategori_besok"].isin(analisis.KATEGORI_ISPU).all()
    assert (p.per_titik["n_jam_hari_ini"] == 18).all()
    assert len(p.per_jam) == 24 and np.isclose(p.per_jam["pm2_5_ml"].mean(), p.per_titik["besok_ml"].mean(), rtol=0.02)
    assert np.isclose(p.pentingnya_fitur.sum(), 1.0) and p.pentingnya_fitur.index[0] in model.FITUR
    assert p.n_latih > 0


def test_prakiraan_mengikuti_cuaca_besok():
    """Bila besok anginnya kencang, prakiraan harus lebih rendah daripada bila besok tenang."""
    jam = buat_jam_sintetis(n_hari=40, n_sel=3)
    besok = jam["waktu"].dt.date == analisis.waktu_sekarang(jam).date() + pd.Timedelta(days=1)
    tenang, kencang = jam.copy(), jam.copy()
    tenang.loc[besok, "angin"] = 3.0
    kencang.loc[besok, "angin"] = 15.0
    p_tenang = model.latih_dan_prakirakan(tenang)
    p_kencang = model.latih_dan_prakirakan(kencang)
    assert p_kencang.per_sel["besok_ml"].mean() < p_tenang.per_sel["besok_ml"].mean() - 5


def test_profil_diurnal_rata_rata_satu():
    jam = buat_jam_sintetis(n_hari=20, n_sel=2)
    prof = model.profil_diurnal(jam)
    assert np.allclose(prof.groupby("sel")["rasio"].mean(), 1.0)
    assert prof.loc[prof["rasio"].idxmax(), "jam"] == 11


def test_data_terlalu_sedikit_melempar():
    with pytest.raises(ValueError):
        model.latih_dan_prakirakan(buat_jam_sintetis(n_hari=6, n_sel=1))


def test_prakiraan_pada_data_contoh():
    """Alur penuh pada data contoh nyata: berjalan, pilih model, dan galat masuk akal."""
    from src import sumber

    jam, _ = sumber.muat_sample()
    p = model.latih_dan_prakirakan(jam)
    assert len(p.per_titik) == 51 and p.per_sel["sel"].is_unique
    assert not p.backtest.empty and p.backtest["mae"].between(1, 40).all()
    assert p.per_titik["besok_ml"].between(1, 300).all()
