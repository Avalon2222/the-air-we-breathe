"""Grafik Plotly dengan tema gelap yang seragam."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import analisis
from src.analisis import KATEGORI_ISPU, WARNA_ISPU, WHO_HARIAN_PM25

WARNA_OBS = "#8ec5ff"
WARNA_CAMS = "#b39cff"
WARNA_ML = "#ff9f43"
WARNA_SAMAR = "#8a877f"
TATA = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(size=12))
LABEL_MODEL = {"persistensi": "Persistence", "ridge": "Ridge", "gbr": "Gradient boosting"}


LEGENDA_ATAS = dict(orientation="h", y=1.0, yanchor="bottom", x=0, xanchor="left")


def _tata(fig: go.Figure, judul: str, tinggi: int = 340, **kw) -> go.Figure:
    """Tata letak seragam. Bila ada legenda horizontal di atas, judul digeser ke atas agar tidak bertumpuk."""
    legenda_atas = kw.get("legend", {}).get("orientation") == "h"
    kw.setdefault("margin", dict(l=10, r=10, t=75 if legenda_atas else 40, b=10))
    judul_kw = dict(text=judul, font=dict(size=15), y=0.98, yanchor="top") if legenda_atas else dict(text=judul, font=dict(size=15))
    fig.update_layout(title=judul_kw, height=tinggi, **TATA, **kw)
    return fig


def _pita_ispu(fig: go.Figure, maks: float) -> None:
    """Latar berwarna kategori ISPU di sumbu y (konsentrasi PM2.5)."""
    batas = [0, 15.5, 55.4, 150.4, 250.4, max(500.0, maks)]
    for i, kat in enumerate(KATEGORI_ISPU):
        if batas[i] > maks * 1.1:
            break
        fig.add_hrect(y0=batas[i], y1=min(batas[i + 1], maks * 1.1), fillcolor=WARNA_ISPU[kat], opacity=0.07, line_width=0, layer="below")
    fig.add_hline(y=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5, annotation_text="WHO 24 jam (15)", annotation_position="top left", annotation_font_size=10)


def garis_riwayat(wilayah: pd.DataFrame, per_jam_besok: pd.DataFrame | None, hari: int = 7) -> go.Figure:
    """Rata-rata wilayah per jam: pengamatan, prakiraan CAMS, dan prakiraan ML besok."""
    batas = wilayah["waktu"].max() - pd.Timedelta(days=hari + 2)
    w = wilayah[wilayah["waktu"] >= batas]
    obs = w[~w["prakiraan"]]
    cams = w[w["prakiraan"] | (w["waktu"] == obs["waktu"].max())]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=obs["waktu"], y=obs["pm2_5"], mode="lines", name="PM2.5 (CAMS, analisis)", line=dict(color=WARNA_OBS, width=2), hovertemplate="%{x|%a %d %b %H:%M}<br>%{y:.0f} µg/m³<extra></extra>"))
    fig.add_trace(go.Scatter(x=cams["waktu"], y=cams["pm2_5"], mode="lines", name="Prakiraan CAMS", line=dict(color=WARNA_CAMS, width=2, dash="dot"), hovertemplate="%{x|%a %d %b %H:%M}<br>%{y:.0f} µg/m³<extra></extra>"))
    if per_jam_besok is not None and not per_jam_besok.empty:
        fig.add_trace(go.Scatter(x=per_jam_besok["waktu"], y=per_jam_besok["pm2_5_ml"], mode="lines", name="Prakiraan ML besok", line=dict(color=WARNA_ML, width=3), hovertemplate="%{x|%a %d %b %H:%M}<br>%{y:.0f} µg/m³<extra></extra>"))
    maks = float(max(w["pm2_5"].max(), (per_jam_besok["pm2_5_ml"].max() if per_jam_besok is not None and not per_jam_besok.empty else 0)))
    _pita_ispu(fig, maks)
    fig.add_vline(x=obs["waktu"].max(), line_color="#ffffff", opacity=0.3, line_dash="dash")
    return _tata(fig, "PM2.5 rata-rata Jabodetabek: 7 hari terakhir dan prakiraan", 380, yaxis_title="µg/m³", xaxis_title=None, legend=LEGENDA_ATAS, hovermode="x unified")


def heatmap_jam_hari(matriks: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=matriks.values, x=[pd.Timestamp(c).strftime("%d %b") for c in matriks.columns], y=[f"{h:02d}:00" for h in matriks.index],
            colorscale=[[0, "#1d3b2a"], [0.12, "#2ecc71"], [0.3, "#3b9ddd"], [0.55, "#f1c40f"], [0.8, "#e74c3c"], [1, "#4a0a0a"]],
            zmin=0, zmax=max(120, float(np.nanmax(matriks.values))), colorbar=dict(title="µg/m³", thickness=12), hovertemplate="%{x} %{y}<br>%{z:.0f} µg/m³<extra></extra>",
        )
    )
    return _tata(fig, "Jam × hari: kapan udara paling kotor?", 420, yaxis=dict(autorange="reversed", dtick=3), xaxis_title=None)


def profil_jam(prof: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prof["jam"], y=prof["p75"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prof["jam"], y=prof["p25"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(142,197,255,0.15)", name="Rentang P25–P75", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prof["jam"], y=prof["pm2_5"], mode="lines+markers", name="Rata-rata", line=dict(color=WARNA_OBS, width=3), hovertemplate="%{x:02d}:00 WIB<br>%{y:.0f} µg/m³<extra></extra>"))
    fig.add_hline(y=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5)
    return _tata(fig, "Profil harian: PM2.5 per jam (WIB)", 340, xaxis=dict(dtick=3, title=None), yaxis_title="µg/m³", legend=LEGENDA_ATAS)


def batang_titik(kini: pd.DataFrame, n: int = 15) -> go.Figure:
    d = kini.head(n).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=d["pm2_5"], y=d["titik"], orientation="h", marker_color=[WARNA_ISPU[k] for k in d["kategori_ispu"]], marker_line=dict(color="#ffffff", width=0.5),
            text=[f"{v:.0f}" for v in d["pm2_5"]], textposition="outside", customdata=np.stack([d["kota"], d["ispu"], d["kategori_ispu"]], axis=-1),
            hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>%{x:.1f} µg/m³ · ISPU %{customdata[1]:.0f} %{customdata[2]}<extra></extra>",
        )
    )
    fig.add_vline(x=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5)
    return _tata(fig, f"{n} titik paling kotor saat ini", 460, xaxis_title="PM2.5 (µg/m³)", yaxis_title=None)


def batang_sel(sel: pd.DataFrame) -> go.Figure:
    """Satu batang per sel grid CAMS; label = wilayah dominan di dalamnya."""
    d = sel.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=d["pm2_5"], y=[f"{l} ({n} titik)" for l, n in zip(d["label"], d["n"])], orientation="h", marker_color=[WARNA_ISPU[k] for k in d["kategori_ispu"]], marker_line=dict(color="#ffffff", width=0.5),
            text=[f"{v:.0f}" for v in d["pm2_5"]], textposition="outside", customdata=np.stack([d["titik"], d["ispu"], d["kategori_ispu"], d["delta_24j"]], axis=-1),
            hovertemplate="<b>%{y}</b><br>%{x:.1f} µg/m³ · ISPU %{customdata[1]:.0f} %{customdata[2]} · %{customdata[3]:+.0f} vs 24 jam lalu<br><span style='font-size:11px'>%{customdata[0]}</span><extra></extra>",
        )
    )
    fig.add_vline(x=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5)
    return _tata(fig, f"PM2.5 saat ini per sel grid CAMS ({len(sel)} sel, {int(sel['n'].sum())} titik)", 420, xaxis=dict(title="PM2.5 (µg/m³)", range=[0, float(sel["pm2_5"].max()) * 1.15]), yaxis_title=None)


def batang_kota(kota: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=kota["kota"], y=kota["pm2_5"], marker_color=[WARNA_ISPU[k] for k in kota["kategori_ispu"]], marker_line=dict(color="#ffffff", width=0.5),
            text=[f"{v:.0f}" for v in kota["pm2_5"]], textposition="outside", customdata=kota[["ispu", "kategori_ispu", "n"]],
            hovertemplate="<b>%{x}</b><br>%{y:.1f} µg/m³ · ISPU %{customdata[0]:.0f} %{customdata[1]}<br>%{customdata[2]} titik<extra></extra>",
        )
    )
    fig.add_hline(y=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5)
    return _tata(fig, "Per kota saat ini", 340, yaxis=dict(title="PM2.5 (µg/m³)", range=[0, float(kota["pm2_5"].max()) * 1.2]), xaxis_title=None)


def hari_kategori(tabel: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for kat in KATEGORI_ISPU:
        fig.add_trace(go.Bar(name=kat, x=tabel.index, y=tabel[kat], marker_color=WARNA_ISPU[kat], marker_line=dict(color="#ffffff", width=0.3), hovertemplate="%{x}<br>" + kat + ": %{y} hari<extra></extra>"))
    return _tata(fig, "Jumlah hari per kategori ISPU (rata-rata harian kota)", 340, barmode="stack", yaxis_title="hari", xaxis_title=None, legend=LEGENDA_ATAS)


def sebaran_cuaca(w: pd.DataFrame, x: str, label_x: str) -> go.Figure:
    d = w.dropna(subset=[x, "pm2_5"])
    fig = go.Figure(go.Scatter(x=d[x], y=d["pm2_5"], mode="markers", name="hari", marker=dict(color=WARNA_OBS, size=8, opacity=0.8, line=dict(color="#ffffff", width=0.5)), customdata=[str(t) for t in d["tanggal"]], hovertemplate="%{customdata}<br>" + label_x + ": %{x:.1f}<br>PM2.5: %{y:.0f} µg/m³<extra></extra>"))
    r = float("nan")
    if len(d) >= 5 and d[x].nunique() > 1:
        r = float(d[x].corr(d["pm2_5"]))
        m, b = np.polyfit(d[x], d["pm2_5"], 1)
        xs = np.linspace(float(d[x].min()), float(d[x].max()), 50)
        fig.add_trace(go.Scatter(x=xs, y=m * xs + b, mode="lines", name="garis tren", line=dict(color=WARNA_ML, width=2), hoverinfo="skip"))
    fig.update_layout(showlegend=False)
    return _tata(fig, f"{label_x} vs PM2.5 harian (r = {r:.2f})", 320, xaxis_title=label_x, yaxis_title="PM2.5 (µg/m³)")


def grafik_backtest(bt: pd.DataFrame) -> go.Figure:
    d = bt.copy()
    d["label"] = d["model"].map(LABEL_MODEL)
    warna = {"persistensi": WARNA_SAMAR, "ridge": WARNA_OBS, "gbr": WARNA_ML}
    fig = go.Figure(
        go.Bar(x=d["label"], y=d["mae"], marker_color=[warna[m] for m in d["model"]], text=[f"{v:.1f}" for v in d["mae"]], textposition="outside", customdata=d[["rmse", "bias", "n"]], hovertemplate="<b>%{x}</b><br>MAE %{y:.2f} · RMSE %{customdata[0]:.2f}<br>bias %{customdata[1]:+.2f} · n=%{customdata[2]}<extra></extra>")
    )
    return _tata(fig, "Galat uji maju 21 hari (MAE, µg/m³; makin rendah makin baik)", 320, yaxis=dict(title="MAE", range=[0, float(d["mae"].max()) * 1.2]), xaxis_title=None)


NAMA_FITUR = {
    "lag1": "PM2.5 hari ini", "rata7_minus_lag1": "Rata-rata 7 hari − hari ini", "angin": "Angin besok", "hujan": "Hujan besok", "blh": "Lapisan batas besok",
    "suhu": "Suhu besok", "rh": "Kelembapan besok", "d_angin": "Perubahan angin", "d_hujan": "Perubahan hujan", "d_blh": "Perubahan lapisan batas",
    "d_suhu": "Perubahan suhu", "d_rh": "Perubahan kelembapan", "dow_sin": "Hari (sin)", "dow_cos": "Hari (cos)", "akhir_pekan": "Akhir pekan",
}


def grafik_fitur(penting: pd.Series) -> go.Figure:
    d = penting.sort_values()
    fig = go.Figure(go.Bar(x=d.values, y=[NAMA_FITUR.get(k, k) for k in d.index], orientation="h", marker_color=WARNA_ML, text=[f"{v:.0%}" for v in d.values], textposition="outside"))
    return _tata(fig, "Fitur yang paling menentukan", 380, xaxis=dict(title=None, tickformat=".0%", range=[0, float(d.max()) * 1.3]), yaxis_title=None)


def titik_prakiraan(pt: pd.DataFrame, n: int = 20) -> go.Figure:
    d = pt.head(n).iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["hari_ini"], y=d["titik"], mode="markers", name="Hari ini", marker=dict(color=WARNA_SAMAR, size=9, symbol="circle-open", line=dict(width=2))))
    fig.add_trace(go.Scatter(x=d["besok_cams"], y=d["titik"], mode="markers", name="Besok (CAMS)", marker=dict(color=WARNA_CAMS, size=9, symbol="diamond")))
    fig.add_trace(go.Scatter(x=d["besok_ml"], y=d["titik"], mode="markers", name="Besok (ML)", marker=dict(color=WARNA_ML, size=11, line=dict(color="#ffffff", width=0.8))))
    fig.add_vline(x=WHO_HARIAN_PM25, line_dash="dot", line_color="#ffffff", opacity=0.5)
    fig.add_vline(x=55.4, line_dash="dot", line_color=WARNA_ISPU["Tidak Sehat"], opacity=0.6)
    return _tata(fig, f"Prakiraan besok, {n} titik tertinggi", 560, xaxis_title="PM2.5 rata-rata harian (µg/m³)", yaxis_title=None, legend=LEGENDA_ATAS)


def akhir_pekan(d: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(x=d["jenis"], y=d["pm2_5"], marker_color=[WARNA_OBS, WARNA_ML], text=[f"{v:.1f}" for v in d["pm2_5"]], textposition="outside"))
    return _tata(fig, "Hari kerja vs akhir pekan", 300, yaxis_title="PM2.5 (µg/m³)", xaxis_title=None)


def polutan_lain(kini: pd.DataFrame) -> go.Figure:
    """Rata-rata wilayah polutan selain PM2.5, dinormalkan terhadap pedoman WHO 24 jam / 8 jam."""
    pedoman = {"pm10": 45.0, "no2": 25.0, "o3": 100.0, "so2": 40.0, "co": 4000.0}
    label = {"pm10": "PM10 (45)", "no2": "NO₂ (25)", "o3": "O₃ (100)", "so2": "SO₂ (40)", "co": "CO (4000)"}
    nilai = {k: float(kini[k].mean()) for k in pedoman if k in kini.columns}
    rasio = [nilai[k] / pedoman[k] for k in nilai]
    fig = go.Figure(go.Bar(x=[label[k] for k in nilai], y=rasio, marker_color=[WARNA_ISPU["Sangat Tidak Sehat"] if r > 1 else WARNA_OBS for r in rasio], text=[f"{nilai[k]:.0f} µg/m³" for k in nilai], textposition="outside"))
    fig.add_hline(y=1, line_dash="dot", line_color="#ffffff", opacity=0.6, annotation_text="pedoman WHO", annotation_font_size=10)
    return _tata(fig, "Polutan lain saat ini, relatif terhadap pedoman WHO (= 1)", 320, yaxis_title="× pedoman", xaxis_title=None)
