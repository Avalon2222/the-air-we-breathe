"""Peta Folium: titik pantau berwarna kategori indeks, heatmap, stasiun OpenAQ."""

from __future__ import annotations

import folium
import pandas as pd
from branca.element import MacroElement, Template
from folium.plugins import HeatMap

from src import analisis
from src.sumber import UKURAN_SEL

PUSAT_JABODETABEK = (-6.27, 106.83)

_LEGENDA = """
{% macro html(this, kwargs) %}
<div style="position:fixed;bottom:28px;left:12px;z-index:9999;background:rgba(14,15,18,.88);color:#f2f1ec;
            padding:10px 12px;border-radius:8px;font:12px/1.5 system-ui,sans-serif;border:1px solid #333;max-width:230px">
  <b>{{ this.judul }}</b><br>
  {% for nama, warna in this.item %}
  <span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:{{ warna }};border:1px solid #ddd;margin-right:6px;vertical-align:middle"></span>{{ nama }}<br>
  {% endfor %}
  <span style="color:#a9a79f">Ukuran lingkaran = konsentrasi PM2.5<br>Kotak putus-putus = sel grid model (~40 km)</span>
  {% if this.stasiun %}<br><span style="display:inline-block;width:10px;height:10px;background:#fff;border:1px solid #888;margin-right:6px;vertical-align:middle"></span>Stasiun sensor OpenAQ{% endif %}
</div>
{% endmacro %}
"""


class _Legenda(MacroElement):
    def __init__(self, judul: str, item: list[tuple[str, str]], stasiun: bool):
        super().__init__()
        self._template = Template(_LEGENDA)
        self.judul, self.item, self.stasiun = judul, item, stasiun


def radius(pm: float) -> float:
    """Jari-jari piksel: 6 px pada udara bersih, tumbuh pelan sampai sekitar 22 px."""
    return float(min(22.0, 6.0 + (pm or 0.0) / 7.0))


def _popup(r: pd.Series, indeks: str, label_waktu: str) -> str:
    if indeks == "ISPU":
        baris_indeks = f"ISPU <b>{r['ispu']:.0f}</b> · {r['kategori_ispu']}"
    else:
        baris_indeks = f"US AQI <b>{r['aqi_us']:.0f}</b> · {r['kategori_aqi']}"
    delta = f"{r['delta_24j']:+.0f} vs 24 jam lalu" if "delta_24j" in r and pd.notna(r.get("delta_24j")) else ""
    cuaca = f"angin {r['angin']:.0f} km/j dari {r.get('arah', '-')} · lapisan batas {r['blh']:.0f} m" if pd.notna(r.get("angin")) else ""
    return (
        f"<div style='font:13px system-ui;min-width:190px'><b>{r['titik']}</b><br><span style='color:#888'>{r['wilayah']}</span><br>"
        f"<span style='font-size:20px'><b>{r['pm2_5']:.0f}</b></span> µg/m³ PM2.5 <span style='color:#888'>{delta}</span><br>{baris_indeks}<br>"
        f"<span style='color:#888'>{label_waktu}</span><br><span style='color:#888;font-size:11px'>{cuaca}</span></div>"
    )


def buat_peta(
    kini: pd.DataFrame,
    indeks: str = "ISPU",
    label_waktu: str = "",
    tampil_heatmap: bool = False,
    stasiun: pd.DataFrame | None = None,
    besok: pd.DataFrame | None = None,
    zoom: int = 10,
) -> folium.Map:
    m = folium.Map(location=PUSAT_JABODETABEK, zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ", name="Gelap (Esri)", max_zoom=16,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics", name="Citra satelit (Esri)", show=False,
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)

    kolom_kat = "kategori_ispu" if indeks == "ISPU" else "kategori_aqi"
    warna = analisis.WARNA_ISPU if indeks == "ISPU" else analisis.WARNA_AQI

    # Sel grid model: kotak ~0,4° yang nilainya dibagi oleh semua titik di dalamnya.
    if "sel" in kini.columns and not kini.empty:
        fgsel = folium.FeatureGroup(name="Sel grid CAMS (~0,4°)", show=True)
        sel = kini.groupby(["sel", "lat_sel", "lon_sel"], as_index=False).agg(pm2_5=("pm2_5", "mean"), kat=(kolom_kat, "first"), n=("titik", "size"), titik=("titik", lambda s: ", ".join(s)))
        for _, r in sel.iterrows():
            d = UKURAN_SEL / 2
            folium.Rectangle(
                bounds=[(r["lat_sel"] - d, r["lon_sel"] - d), (r["lat_sel"] + d, r["lon_sel"] + d)], color=warna.get(r["kat"], "#999"), weight=1, opacity=0.6,
                fill=True, fill_color=warna.get(r["kat"], "#999"), fill_opacity=0.12, dash_array="4 4",
                tooltip=f"Sel {r['sel']}: {r['pm2_5']:.0f} µg/m³ · {r['n']} titik",
                popup=folium.Popup(f"<b>Sel grid CAMS</b> {r['sel']}<br>{r['pm2_5']:.0f} µg/m³ PM2.5<br><span style='color:#888;font-size:11px'>{r['titik']}</span>", max_width=260),
            ).add_to(fgsel)
        fgsel.add_to(m)

    if tampil_heatmap and not kini.empty:
        HeatMap(kini[["lat", "lon", "pm2_5"]].values.tolist(), name="Heatmap PM2.5", radius=38, blur=30, min_opacity=0.25, show=True).add_to(m)

    fg = folium.FeatureGroup(name="PM2.5 saat ini", show=True)
    for _, r in kini.iterrows():
        folium.CircleMarker(
            location=(r["lat"], r["lon"]), radius=radius(r["pm2_5"]), color="#ffffff", weight=0.8, fill=True, fill_color=warna.get(r[kolom_kat], "#999"), fill_opacity=0.85,
            tooltip=f"{r['titik']}: {r['pm2_5']:.0f} µg/m³", popup=folium.Popup(_popup(r, indeks, label_waktu), max_width=260),
        ).add_to(fg)
    fg.add_to(m)

    if besok is not None and not besok.empty:
        fgb = folium.FeatureGroup(name="Prakiraan ML besok", show=False)
        for _, r in besok.iterrows():
            folium.CircleMarker(
                location=(r["lat"], r["lon"]), radius=radius(r["besok_ml"]), color="#ff9f43", weight=1.2, fill=True, fill_color=analisis.WARNA_ISPU.get(r["kategori_besok"], "#999"), fill_opacity=0.8,
                tooltip=f"{r['titik']} besok: {r['besok_ml']:.0f} µg/m³ ({r['delta']:+.0f})",
                popup=folium.Popup(f"<b>{r['titik']}</b><br>Besok (ML): <b>{r['besok_ml']:.0f}</b> µg/m³ · ISPU {r['ispu_besok']:.0f} {r['kategori_besok']}<br><span style='color:#888'>hari ini {r['hari_ini']:.0f} · CAMS {r['besok_cams']:.0f}</span>", max_width=240),
            ).add_to(fgb)
        fgb.add_to(m)

    ada_stasiun = stasiun is not None and not stasiun.empty
    if ada_stasiun:
        fgs = folium.FeatureGroup(name="Stasiun OpenAQ (sensor)", show=True)
        for _, s in stasiun.iterrows():
            kat = analisis.kategori_ispu(analisis.ispu_pm25(s["pm2_5"]))
            waktu = s["waktu"].strftime("%d %b %H:%M WIB") if pd.notna(s.get("waktu")) else ""
            folium.RegularPolygonMarker(
                location=(s["lat"], s["lon"]), number_of_sides=4, rotation=45, radius=7, color="#ffffff", weight=1, fill=True, fill_color=analisis.WARNA_ISPU.get(kat, "#999"), fill_opacity=0.95,
                tooltip=f"Sensor {s['nama']}: {s['pm2_5']:.0f} µg/m³", popup=folium.Popup(f"<b>{s['nama']}</b><br>{s['pm2_5']:.0f} µg/m³ PM2.5 (sensor)<br><span style='color:#888'>{waktu} · {s['penyedia']} via OpenAQ</span>", max_width=240),
            ).add_to(fgs)
        fgs.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    item = list(warna.items())
    m.get_root().add_child(_Legenda(f"PM2.5 · kategori {indeks}", item, ada_stasiun))
    return m
