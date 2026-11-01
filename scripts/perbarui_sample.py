"""Unduh ulang data contoh ke ``data/sample``.

Dipakai agar aplikasi tetap berjalan tanpa internet dan agar pengujian
tidak bergantung pada jaringan. Jalankan dari akar proyek:

    python scripts/perbarui_sample.py

Hasilnya satu berkas ``jam.csv.gz`` (tabel per jam semua titik, sekitar 60
hari riwayat + 2 hari prakiraan) dan ``meta.json``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from src import sumber  # noqa: E402


def utama(hari_riwayat: int = sumber.HARI_RIWAYAT) -> None:
    print("Mengunduh data contoh dari Open-Meteo ...")
    titik = sumber.muat_titik()
    waktu_ambil = datetime.now(timezone.utc)
    udara = sumber.ambil_udara(titik, hari_riwayat)
    print(f"  udara: {len(udara):,} baris")
    cuaca = sumber.ambil_cuaca(titik, hari_riwayat)
    print(f"  cuaca: {len(cuaca):,} baris")
    jam = sumber.gabung(udara, cuaca, waktu_ambil)
    meta = {
        "diambil": waktu_ambil.strftime("%Y-%m-%d %H:%M UTC"),
        "hari_riwayat": hari_riwayat,
        "hari_prakiraan": sumber.HARI_PRAKIRAAN,
        "jumlah_titik": int(titik.shape[0]),
        "jumlah_baris": int(len(jam)),
        "sumber": "Open-Meteo Air Quality (CAMS) + Open-Meteo Forecast",
        "catatan": "Data contoh untuk mode offline dan pengujian. Perbarui dengan scripts/perbarui_sample.py.",
    }
    sumber.simpan_sample(jam, meta)
    ukuran = (sumber.DIR_SAMPLE / "jam.csv.gz").stat().st_size // 1024
    print(f"  jam.csv.gz: {len(jam):,} baris, {ukuran} KB")
    print("Selesai.")


if __name__ == "__main__":
    utama()
