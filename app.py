"""The Air We Breathe — peta langsung kualitas udara Jabodetabek dan prakiraan besok.

Jalankan: ``streamlit run app.py``
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import analisis, grafik, model, peta, sumber

st.set_page_config(page_title="The Air We Breathe", page_icon="🌫️", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .blok-judul h1 {margin-bottom:0; font-size:2.3rem; letter-spacing:-0.02em}
    .blok-judul .tagline {color:#ff9f43; font-size:1.05rem; font-weight:600; margin:0 0 .3rem}
    .blok-judul .sub {color:#a9a79f; margin:0}
    div[data-testid="stMetricValue"] {font-size:1.6rem}
    .catatan {color:#a9a79f; font-size:.85rem}
    .pil {display:inline-block;padding:2px 10px;border-radius:999px;font-weight:600;font-size:.9rem;color:#0e0f12}
    </style>
    """,
    unsafe_allow_html=True,
)

HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner="Mengambil data Open-Meteo untuk 51 titik Jabodetabek ...")
def muat(offline: bool) -> sumber.HasilMuat:
    return sumber.muat_semua(paksa_offline=offline)


@st.cache_data(ttl=1800, show_spinner="Melatih model prakiraan ...")
def prakirakan(_jam: pd.DataFrame, kunci: str) -> model.HasilPrakiraan:
    return model.latih_dan_prakirakan(_jam)


def pil(kategori: str, warna: dict) -> str:
    return f'<span class="pil" style="background:{warna.get(kategori, "#999")}">{kategori}</span>'


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    mode = st.radio("Data source", ["Live (Open-Meteo)", "Offline (sample data)"], index=0)
    offline = mode.startswith("Offline")
    indeks = st.radio("Index", ["ISPU", "US AQI"], index=0, horizontal=True, help="ISPU: indeks resmi Indonesia (Permen LHK 14/2020). US AQI: indeks US EPA.")
    st.markdown("### 🗺️ Map layers")
    tampil_heatmap = st.checkbox("PM2.5 heatmap", False)
    tampil_besok = st.checkbox("Tomorrow forecast layer", True)
    if st.button("🔄 Reload data", width="stretch"):
        muat.clear()
        prakirakan.clear()
        st.rerun()
    st.markdown(
        '<p class="catatan">Data diperbarui tiap 30 menit. Jika jaringan gagal, aplikasi memakai data contoh. '
        "Stasiun sensor OpenAQ tampil bila kunci API tersedia di Secrets.</p>",
        unsafe_allow_html=True,
    )

hasil = muat(offline)
jam = hasil.jam
sekarang = analisis.waktu_sekarang(jam)
kini = analisis.kondisi_terkini(jam, sekarang)
ring = analisis.ringkasan(kini, jam, sekarang)
sel = analisis.per_sel(kini)
prak = prakirakan(jam, hasil.waktu_ambil.isoformat())
label_waktu = f"{HARI_ID[sekarang.day_of_week]}, {sekarang:%d %b %Y %H:%M} WIB"
label_besok = f"{HARI_ID[pd.Timestamp(prak.tanggal).day_of_week]}, {pd.Timestamp(prak.tanggal):%d %b}"


# ---------------------------------------------------------------------------
# Judul dan status
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="blok-judul">
      <h1>🌁 The Air We Breathe</h1>
      <p class="tagline">Every breath is a data point.</p>
      <p class="sub">Peta langsung PM2.5 di 51 titik Jabodetabek dari Open-Meteo (CAMS), indeks ISPU dan US AQI, pola jam dan cuaca, serta prakiraan besok dengan model statistik yang diuji secara jujur.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if hasil.offline:
    rincian = "; ".join(hasil.kesalahan) if hasil.kesalahan else "mode offline dipilih"
    st.warning(f"Data berasal dari **data contoh** ({hasil.sumber['udara']}). {rincian}", icon="📦")
else:
    waktu = hasil.waktu_ambil.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    st.caption(f"Data langsung · diambil {waktu} · " + " · ".join(f"{k}: {v}" for k, v in hasil.sumber.items()))

warna_kat = analisis.WARNA_ISPU if indeks == "ISPU" else analisis.WARNA_AQI
kat_kini = ring["kategori_ispu"] if indeks == "ISPU" else ring["kategori_aqi"]
nilai_indeks = ring["ispu"] if indeks == "ISPU" else ring["aqi_us"]
besok_rata = float(prak.per_titik["besok_ml"].mean())
besok_kat = analisis.kategori_ispu(analisis.ispu_pm25(besok_rata))

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("PM2.5 Jabodetabek", f"{ring['rata']:.0f} µg/m³", f"{ring['delta_24j']:+.0f} vs 24 jam lalu" if pd.notna(ring["delta_24j"]) else None, delta_color="inverse")
k2.metric(f"{indeks} rata-rata", f"{nilai_indeks:.0f}", kat_kini, delta_color="off")
k3.metric("Sel terkotor", f"{sel.iloc[0]['pm2_5']:.0f} µg/m³", sel.iloc[0]["label"], delta_color="off")
k4.metric("Sel terbersih", f"{sel.iloc[-1]['pm2_5']:.0f} µg/m³", sel.iloc[-1]["label"], delta_color="off")
k5.metric("× pedoman WHO (24 jam)", f"{ring['kali_who']:.1f}×", f"rata 24 jam {ring['rata_24j']:.0f} µg/m³", delta_color="off")
k6.metric(f"Besok ({label_besok[:3]})", f"{besok_rata:.0f} µg/m³", f"{besok_rata - ring['rata_24j']:+.0f} vs 24 jam terakhir", delta_color="inverse")

st.markdown(
    f"{pil(kat_kini, warna_kat)} &nbsp; <span class='catatan'>{label_waktu} · {ring['n_tidak_sehat']} dari {ring['n_titik']} titik di kategori Tidak Sehat ke atas · "
    f"angin {ring['angin']:.0f} km/j dari {ring['arah_angin']} · hujan 24 jam {ring['hujan_24j']:.1f} mm</span>",
    unsafe_allow_html=True,
)

tab_peta, tab_besok, tab_pola, tab_data, tab_cara = st.tabs(["🗺️ Live map", "🔮 Tomorrow", "📈 Patterns", "📋 Data & Sources", "🧭 How it works"])


# ---------------------------------------------------------------------------
# Tab Peta
# ---------------------------------------------------------------------------

with tab_peta:
    kolom_peta, kolom_daftar = st.columns([3, 1.15])
    with kolom_daftar:
        st.markdown("#### Saat ini, per sel")
        st.markdown(f"<p class='catatan'>{analisis.SARAN_ISPU[ring['kategori_ispu']]}</p>", unsafe_allow_html=True)
        for _, r in sel.iterrows():
            kat = r["kategori_ispu"] if indeks == "ISPU" else r["kategori_aqi"]
            nilai = f"ISPU {r['ispu']:.0f}" if indeks == "ISPU" else f"AQI {r['aqi_us']:.0f}"
            delta = f" · {r['delta_24j']:+.0f} vs 24 j" if pd.notna(r["delta_24j"]) else ""
            st.markdown(
                f"<div style='border-left:3px solid {warna_kat.get(kat, '#999')};padding:2px 8px;margin:4px 0' title='{r['titik']}'>"
                f"<b>{r['pm2_5']:.0f}</b> µg/m³ · {r['label']}<br>"
                f"<span class='catatan'>{int(r['n'])} titik · {nilai} {kat}{delta}</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("<p class='catatan'>Delapan sel grid CAMS menutupi seluruh Jabodetabek; arahkan kursor ke baris untuk melihat titik-titiknya.</p>", unsafe_allow_html=True)
    with kolom_peta:
        m = peta.buat_peta(kini, indeks=indeks, label_waktu=label_waktu, tampil_heatmap=tampil_heatmap, stasiun=hasil.stasiun, besok=prak.per_titik if tampil_besok else None)
        st_folium(m, height=620, use_container_width=True, returned_objects=[])
        st.markdown(
            "<p class='catatan'>Lingkaran: titik pantau, warna mengikuti kategori indeks, ukuran mengikuti PM2.5. Kotak putus-putus: sel grid model CAMS (~0,4° atau ~40 km); semua titik dalam satu sel berbagi nilai yang sama, karena data ini keluaran model global, bukan sensor per kecamatan. "
            "Lapisan <i>Prakiraan ML besok</i> bisa dinyalakan dari kontrol lapisan di kanan atas peta. Klik titik untuk rincian.</p>",
            unsafe_allow_html=True,
        )
    c1, c2 = st.columns([1.3, 1])
    c1.plotly_chart(grafik.batang_sel(sel), width="stretch")
    with c2:
        st.plotly_chart(grafik.batang_kota(analisis.per_kota(kini)), width="stretch")
        st.plotly_chart(grafik.polutan_lain(kini), width="stretch")


# ---------------------------------------------------------------------------
# Tab Besok
# ---------------------------------------------------------------------------

with tab_besok:
    bt = prak.backtest.set_index("model") if not prak.backtest.empty else None
    b1, b2, b3, b4 = st.columns(4)
    b1.metric(f"Prakiraan besok ({label_besok})", f"{besok_rata:.0f} µg/m³", besok_kat, delta_color="off")
    b2.metric("Model terpilih", grafik.LABEL_MODEL[prak.model_terpilih], f"{prak.n_latih:,} baris latih", delta_color="off")
    if bt is not None and prak.model_terpilih in bt.index:
        b3.metric("MAE uji maju", f"{bt.loc[prak.model_terpilih, 'mae']:.1f} µg/m³", f"persistence {bt.loc['persistensi', 'mae']:.1f}", delta_color="off")
    b4.metric("Pembanding CAMS besok", f"{prak.per_titik['besok_cams'].mean():.0f} µg/m³", f"selisih {besok_rata - prak.per_titik['besok_cams'].mean():+.0f}", delta_color="off")

    st.plotly_chart(grafik.garis_riwayat(analisis.rata_wilayah_per_jam(jam), prak.per_jam), width="stretch")
    c1, c2 = st.columns([1.4, 1])
    c1.plotly_chart(grafik.titik_prakiraan(prak.per_titik), width="stretch")
    with c2:
        if not prak.backtest.empty:
            st.plotly_chart(grafik.grafik_backtest(prak.backtest), width="stretch")
        st.plotly_chart(grafik.grafik_fitur(prak.pentingnya_fitur), width="stretch")

    if bt is not None and prak.model_terpilih in bt.index and bt.loc["persistensi", "mae"] <= bt.loc[prak.model_terpilih, "mae"]:
        st.info(
            f"Jujur saja: pada {int(bt['n'].max() / max(prak.per_sel.shape[0], 1))} hari uji terakhir, tebakan paling malas (besok = hari ini, MAE {bt.loc['persistensi', 'mae']:.1f}) "
            f"masih sedikit lebih akurat daripada model terpilih (MAE {bt.loc[prak.model_terpilih, 'mae']:.1f}). Model ini dibangun sebagai 'persistence + koreksi', "
            "jadi prakiraannya tetap dekat dengan hari ini; perbedaannya adalah arah yang disarankan cuaca besok. Anggap angka di atas sebagai arah, bukan kepastian.",
            icon="🧪",
        )
    else:
        st.success(
            f"Model terpilih mengalahkan tebakan malas pada uji maju: MAE {bt.loc[prak.model_terpilih, 'mae']:.1f} vs {bt.loc['persistensi', 'mae']:.1f} µg/m³." if bt is not None else "Uji maju tidak dijalankan: data terlalu pendek.",
            icon="✅",
        )
    naik = prak.per_titik.sort_values("delta", ascending=False).iloc[0]
    turun = prak.per_titik.sort_values("delta").iloc[0]
    st.markdown(
        f"Besok diperkirakan **{'lebih kotor' if besok_rata > ring['rata_24j'] else 'lebih bersih'}** dari 24 jam terakhir di rata-rata wilayah. "
        f"Kenaikan terbesar di **{naik['titik']}** ({naik['delta']:+.0f} µg/m³), penurunan terbesar di **{turun['titik']}** ({turun['delta']:+.0f}). "
        f"Faktor paling berpengaruh menurut model: **{grafik.NAMA_FITUR[prak.pentingnya_fitur.index[0]]}**, lalu **{grafik.NAMA_FITUR[prak.pentingnya_fitur.index[1]]}**."
    )
    with st.expander("Bagaimana prakiraan ini dibuat, dan seberapa bisa dipercaya?"):
        st.markdown(
            """
            **Satu baris = satu sel grid pada satu hari.** Data CAMS beresolusi ~40 km, jadi 51 titik sebenarnya hanya 8 deret waktu;
            melatih per titik berarti menghitung kejadian yang sama berkali-kali.

            **Yang ditebak adalah perubahan, bukan kadar.** Target model = PM2.5 besok − PM2.5 hari ini ("persistence + koreksi").
            Fiturnya hanya hal yang sudah diketahui saat prakiraan dibuat: PM2.5 hari ini dan selisihnya terhadap rata-rata 7 hari,
            **prakiraan cuaca untuk besok** beserta perubahannya dari hari ini (angin, hujan, tinggi lapisan batas, suhu, kelembapan),
            dan hari dalam pekan.

            **Uji maju (walk-forward).** Untuk 21 hari terakhir, model dilatih hanya dengan hari-hari sebelum hari uji, lalu
            ditebak hari itu. Galatnya (MAE) dibandingkan dengan *persistence*, tebakan paling malas: "besok sama dengan hari ini".
            Model statistik baru layak dipercaya bila mengalahkan tebakan malas itu; bila tidak, aplikasi mengatakannya terang-terangan.
            Model ML dengan MAE terendah dipilih otomatis.

            **Kejujuran yang perlu dicatat.** (1) Fitur "PM2.5 hari ini" saat prakiraan dibuat baru mencakup jam yang sudah
            lewat, sedangkan saat latihan ia mencakup 24 jam penuh. (2) Data riwayatnya sendiri keluaran model CAMS, bukan sensor,
            jadi kita sedang belajar meniru model lain, bukan atmosfer. (3) Enam puluh hari data tidak menangkap musim: model ini
            tidak tahu bahwa musim kemarau lebih pekat dari musim hujan. Prakiraan CAMS ditampilkan sebagai pembanding yang
            memakai fisika-kimia penuh; bila keduanya sepakat, kepercayaan naik.
            """
        )


# ---------------------------------------------------------------------------
# Tab Pola
# ---------------------------------------------------------------------------

with tab_pola:
    harian = analisis.harian_per_titik(jam)
    st.markdown("#### Waktu")
    c1, c2 = st.columns([1.3, 1])
    c1.plotly_chart(grafik.heatmap_jam_hari(analisis.matriks_jam_hari(jam)), width="stretch")
    with c2:
        prof = analisis.profil_jam(jam)
        st.plotly_chart(grafik.profil_jam(prof), width="stretch")
        puncak, lembah = prof.loc[prof["pm2_5"].idxmax()], prof.loc[prof["pm2_5"].idxmin()]
        st.markdown(
            f"Jam terkotor rata-rata **{int(puncak['jam']):02d}:00 WIB** ({puncak['pm2_5']:.0f} µg/m³), terbersih **{int(lembah['jam']):02d}:00 WIB** "
            f"({lembah['pm2_5']:.0f} µg/m³). Polusi menumpuk pada malam sampai pagi karena lapisan batas atmosfer rendah dan angin lemah, "
            f"lalu terangkat siang hari saat matahari memanaskan permukaan."
        )
    with st.expander("Mengapa malam dan pagi lebih kotor dari siang?"):
        st.markdown(
            """
            Udara di dekat permukaan bercampur dalam suatu **lapisan batas** (boundary layer). Siang hari matahari memanaskan tanah,
            udara naik, lapisan ini menebal sampai 1–2 km, dan polusi "diencerkan" dalam volume besar. Malam hari permukaan mendingin,
            lapisan menipis sampai beberapa ratus meter atau kurang, dan emisi yang sama terjebak dalam volume kecil, sehingga konsentrasi
            naik. Tambahkan jam sibuk pagi, dan hasilnya puncak PM2.5 sekitar subuh sampai pagi. Angin kencang dan hujan memecah pola ini.
            """
        )

    st.markdown("#### Cuaca")
    w = analisis.angin_vs_pm(harian)
    c3, c4, c5 = st.columns(3)
    c3.plotly_chart(grafik.sebaran_cuaca(w, "angin", "Kecepatan angin (km/j)"), width="stretch")
    c4.plotly_chart(grafik.sebaran_cuaca(w, "blh", "Tinggi lapisan batas (m)"), width="stretch")
    c5.plotly_chart(grafik.sebaran_cuaca(w, "hujan", "Hujan harian (mm)"), width="stretch")
    kor = analisis.korelasi_cuaca(harian)
    st.markdown(
        f"Korelasi harian dengan PM2.5: angin **{kor['angin']:+.2f}**, lapisan batas **{kor['blh']:+.2f}**, hujan **{kor['hujan']:+.2f}**, suhu **{kor['suhu']:+.2f}**. "
        f"Tanda negatif berarti makin besar variabel itu, makin bersih udara. Inilah alasan cuaca besok menjadi fitur model."
    )

    st.markdown("#### Kota dan hari")
    c6, c7 = st.columns([1.4, 1])
    c6.plotly_chart(grafik.hari_kategori(analisis.hari_per_kategori(harian)), width="stretch")
    c7.plotly_chart(grafik.akhir_pekan(analisis.akhir_pekan_vs_kerja(harian)), width="stretch")
    who = analisis.hari_di_atas_who(harian)
    st.markdown(f"**Berapa sering melampaui ambang?** Dari {int(who['hari'].max())} hari pengamatan:")
    st.dataframe(
        who[["titik", "kota", "pm2_5", "pct_who", "pct_baku_mutu"]].rename(columns={"titik": "Titik", "kota": "Kota", "pm2_5": "Rata-rata PM2.5", "pct_who": "% hari > WHO (15)", "pct_baku_mutu": "% hari > baku mutu RI (55)"}),
        hide_index=True,
        width="stretch",
        height=320,
        column_config={"Rata-rata PM2.5": st.column_config.NumberColumn(format="%.0f"), "% hari > WHO (15)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100), "% hari > baku mutu RI (55)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)},
    )


# ---------------------------------------------------------------------------
# Tab Data & Sumber
# ---------------------------------------------------------------------------

with tab_data:
    tampil = kini[["titik", "kota", "wilayah", "lat", "lon", "pm2_5", "pm2_5_24j", "delta_24j", "ispu", "kategori_ispu", "aqi_us", "kategori_aqi", "pm10", "no2", "o3", "co", "so2", "suhu", "rh", "angin", "arah", "blh"]]
    st.dataframe(
        tampil.rename(
            columns={
                "titik": "Titik", "kota": "Kota", "wilayah": "Wilayah", "lat": "Lintang", "lon": "Bujur", "pm2_5": "PM2.5", "pm2_5_24j": "PM2.5 24 jam", "delta_24j": "Δ 24 jam",
                "ispu": "ISPU", "kategori_ispu": "Kategori ISPU", "aqi_us": "US AQI", "kategori_aqi": "Kategori AQI", "pm10": "PM10", "no2": "NO₂", "o3": "O₃", "co": "CO", "so2": "SO₂",
                "suhu": "Suhu (°C)", "rh": "RH (%)", "angin": "Angin (km/j)", "arah": "Arah", "blh": "Lapisan batas (m)",
            }
        ),
        hide_index=True,
        width="stretch",
        height=420,
        column_config={k: st.column_config.NumberColumn(format="%.0f") for k in ("PM2.5", "PM2.5 24 jam", "Δ 24 jam", "ISPU", "US AQI", "PM10", "NO₂", "O₃", "CO", "SO₂", "RH (%)", "Angin (km/j)", "Lapisan batas (m)")},
    )
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download current conditions (CSV)", tampil.to_csv(index=False).encode("utf-8"), file_name=f"udara_jabodetabek_{sekarang:%Y%m%d_%H}.csv", mime="text/csv")
    d2.download_button("⬇️ Download hourly history (CSV)", jam.to_csv(index=False).encode("utf-8"), file_name=f"udara_jabodetabek_perjam_{sekarang:%Y%m%d}.csv", mime="text/csv")
    if not hasil.stasiun.empty:
        st.markdown("**Stasiun sensor OpenAQ**")
        st.dataframe(hasil.stasiun, hide_index=True, width="stretch")
    st.markdown(
        """
        **Sumber**

        | Sumber | Isi | Tautan |
        |---|---|---|
        | Open-Meteo Air Quality API | PM2.5, PM10, NO₂, O₃, CO, SO₂ per jam dari model CAMS global (Copernicus), 60 hari riwayat + 2 hari prakiraan, resolusi ~0,4° (~40 km, sekitar 8 sel untuk Jabodetabek) | [open-meteo.com](https://open-meteo.com/en/docs/air-quality-api) |
        | Open-Meteo Forecast API | Suhu, kelembapan, hujan, angin, tinggi lapisan batas per jam | [open-meteo.com](https://open-meteo.com/en/docs) |
        | OpenAQ v3 (opsional) | Pembacaan sensor PM2.5 sungguhan dari stasiun di Jabodetabek; perlu kunci API gratis | [openaq.org](https://docs.openaq.org/) |
        | Permen LHK P.14/2020 | Titik potong ISPU untuk PM2.5 | [peraturan.go.id](https://peraturan.go.id/) |
        | US EPA | Titik potong US AQI PM2.5 (pembaruan 2024) | [airnow.gov](https://www.airnow.gov/aqi/aqi-basics/) |
        | WHO Air Quality Guidelines 2021 | Pedoman PM2.5 24 jam 15 µg/m³, tahunan 5 µg/m³ | [who.int](https://www.who.int/publications/i/item/9789240034228) |

        > ⚠️ **Disclaimer.** Aplikasi ini menampilkan ulang data publik untuk tujuan edukasi dan portofolio. Nilai Open-Meteo adalah
        > keluaran **model**, bukan pengukuran, dan bisa meleset puluhan µg/m³ dari sensor di lokasi yang sama. Prakiraan besok adalah
        > model statistik sederhana, bukan prakiraan resmi. Untuk keputusan kesehatan, rujuk [ispu.menlhk.go.id](https://ispu.menlhk.go.id/)
        > dan [udara.jakarta.go.id](https://udara.jakarta.go.id/).
        """
    )
    if hasil.kesalahan:
        st.markdown("**Catatan pengambilan data:** " + " · ".join(hasil.kesalahan))


# ---------------------------------------------------------------------------
# Tab Cara Kerja
# ---------------------------------------------------------------------------

with tab_cara:
    st.markdown(
        """
        #### Alur data

        ```
        data/titik.csv (51 titik)
            ├─► Open-Meteo Air Quality ─┐
            └─► Open-Meteo Forecast ────┤
        OPENAQ_API_KEY (opsional) ──► OpenAQ v3 ─┤
        data/sample/jam.csv.gz ──── fallback ────┤
                                                 ▼
                      src/sumber.py  (parse, gabung, sel grid, tandai prakiraan)
                                                 │  tabel per jam (75 ribu baris)
                       ┌─────────────────────────┴──────────────────┐
                       ▼                                            ▼
            src/analisis.py (ISPU, AQI, pola)         src/model.py (fitur, uji maju, prakiraan)
                       │                                            │
                       └────────────► src/grafik.py (Plotly) ◄──────┘
                                      src/peta.py (Folium)
                                                 │
                                                 ▼
                                      app.py (Streamlit)
        ```

        1. **Ambil.** Dua permintaan HTTP ke Open-Meteo, masing-masing membawa 51 pasang koordinat sekaligus. Balasannya daftar JSON per lokasi
           dengan larik per jam. Tidak ada kunci API.
        2. **Normalisasi.** Setiap lokasi dipetakan ke baris `titik, waktu, pm2_5, ..., angin, blh`, lalu udara dan cuaca digabung per `(titik, waktu)`.
           Jam setelah waktu pengambilan ditandai `prakiraan = True`.
        3. **Fallback.** Jika permintaan gagal, tabel yang sama dibaca dari `data/sample/jam.csv.gz` dan spanduk peringatan muncul. "Sekarang"
           dalam mode offline adalah jam pengamatan terakhir di berkas itu.
        4. **Indeks.** PM2.5 diubah ke ISPU (Permen LHK 14/2020) dan US AQI (EPA 2024) dengan interpolasi linear sepotong-sepotong antar titik potong.
        5. **Pola.** Profil per jam, matriks jam × hari, rata-rata harian per titik, korelasi dengan angin, hujan, dan tinggi lapisan batas.
        6. **Prakiraan.** Tabel harian per sel grid (bukan per titik, karena titik-titik sesel bernilai sama) → fitur lag + prakiraan cuaca besok → target = perubahan dari hari ini → uji maju 21 hari untuk Ridge dan Gradient Boosting melawan
           persistence → model terbaik dilatih ulang dengan semua data → prakiraan rata-rata besok per sel, dipetakan ke tiap titik dan dipecah per jam dengan profil diurnal.
        7. **Tampil.** Folium menggambar peta di atas tile gelap Esri, Plotly menggambar grafik, Streamlit menyusun semuanya dan menyimpan hasil
           pengambilan serta model selama 30 menit.

        Penjelasan panjang ada di `docs/BELAJAR.md`, latihannya di `docs/LATIHAN.md`.
        """
    )
