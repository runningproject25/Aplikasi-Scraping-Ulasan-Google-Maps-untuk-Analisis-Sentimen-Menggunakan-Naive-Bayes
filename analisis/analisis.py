"""
Runner analisis sentimen untuk Flask.
Dipanggil dari background thread — prediksi Naive Bayes untuk data yang sudah di-scraping,
hasilnya disimpan ke MySQL.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.append(str(Path(__file__).parent.parent))

MODEL_DIR = Path(__file__).parent.parent / "model"


def _get_db():
    from config.db import get_connection
    return get_connection()


# ── Load model tersimpan ──────────────────────────────────────────────────────

def _muat_model(update_status):
    import joblib
    model_path   = MODEL_DIR / "naive_bayes.pkl"
    vec_path     = MODEL_DIR / "vectorizer.pkl"
    akurasi_path = MODEL_DIR / "akurasi.txt"

    if not model_path.exists() or not vec_path.exists():
        raise RuntimeError(
            "Model belum tersedia. Jalankan python naive_bayes.py untuk melatih model dan menyimpannya."
        )

    update_status("loading", "Memuat model tersimpan...", 68)
    model      = joblib.load(model_path)
    vectorizer = joblib.load(vec_path)
    akurasi    = float(akurasi_path.read_text().strip()) if akurasi_path.exists() else None
    return model, vectorizer, akurasi


# ── Helper sentimen dari rating bintang ──────────────────────────────────────

def _sentimen_dari_rating(rating):
    """1-2 → Negatif, 3 → Netral, 4-5 → Positif. None → Netral."""
    try:
        r = round(float(rating))
    except (TypeError, ValueError):
        return "Netral"
    if r <= 2:
        return "Negatif"
    elif r == 3:
        return "Netral"
    else:
        return "Positif"


def _klasifikasi_star_only(id_sesi_scraping, cursor, update_status, pesan=""):
    cursor.execute("""
        SELECT id, rating FROM komentar
        WHERE id_sesi_scraping = %s
          AND (komentar IS NULL OR TRIM(komentar) = '')
    """, (id_sesi_scraping,))
    rows = cursor.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["sentimen_prediksi"] = df["rating"].apply(_sentimen_dari_rating)

    if pesan:
        update_status("saving", pesan, None)

    for _, row in df.iterrows():
        cursor.execute(
            "UPDATE komentar SET sentimen=%s, confidence=NULL WHERE id=%s",
            (row["sentimen_prediksi"], int(row["id"]))
        )
    return df


# ── Analisis satu sesi ────────────────────────────────────────────────────────

def analisis_sesi(id_sesi_scraping: int, update_status):
    from analisis.preprocessing import bersihkan_teks

    conn = _get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE scraping_sessions SET status='sedang_analisis' WHERE id=%s", (id_sesi_scraping,))
    conn.commit()

    df_star = _klasifikasi_star_only(
        id_sesi_scraping, cursor, update_status,
        pesan="Analisis sentimen menggunakan Naive Bayes sedang dilakukan. "
              "Ulasan tanpa komentar dilabeli berdasarkan rating..."
    )
    conn.commit()

    cursor.execute(
        "SELECT id, komentar FROM komentar "
        "WHERE id_sesi_scraping=%s AND komentar IS NOT NULL AND TRIM(komentar) != ''",
        (id_sesi_scraping,)
    )
    rows = cursor.fetchall()
    conn.close()

    akurasi = None

    if rows:
        df = pd.DataFrame(rows)
        update_status("preprocessing", "Stemming teks...", 40)
        df["teks_bersih"] = df["komentar"].apply(bersihkan_teks)

        model, vectorizer, akurasi = _muat_model(update_status)

        update_status("saving", "Menyimpan hasil ke database...", 85)
        X = vectorizer.transform(df["teks_bersih"])
        df["sentimen_prediksi"] = model.predict(X)
        df["confidence"]        = model.predict_proba(X).max(axis=1).round(4)

        conn = _get_db()
        cursor = conn.cursor()
        for _, row in df.iterrows():
            cursor.execute(
                "UPDATE komentar SET teks_bersih=%s, sentimen=%s, confidence=%s WHERE id=%s",
                (row["teks_bersih"], row["sentimen_prediksi"], float(row["confidence"]), int(row["id"]))
            )
        conn.commit()
        conn.close()

    # Agregasi dari DB setelah semua prediksi tersimpan
    conn = _get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            SUM(sentimen = 'Positif') AS j_pos,
            SUM(sentimen = 'Netral')  AS j_net,
            SUM(sentimen = 'Negatif') AS j_neg,
            COUNT(*)                  AS total
        FROM komentar WHERE id_sesi_scraping = %s
    """, (id_sesi_scraping,))
    agg = cursor.fetchone()
    cursor.execute("""
        UPDATE scraping_sessions
        SET status='selesai', jumlah_positif=%s, jumlah_netral=%s,
            jumlah_negatif=%s, akurasi=%s, selesai_pada=NOW()
        WHERE id=%s
    """, (agg["j_pos"] or 0, agg["j_net"] or 0, agg["j_neg"] or 0,
          float(akurasi) if akurasi is not None else None, id_sesi_scraping))
    conn.commit()
    conn.close()

    akurasi_str = f"Akurasi model: {akurasi*100:.1f}%" if akurasi is not None else ""
    update_status("selesai", f"Selesai! {agg['total']} ulasan dianalisis. {akurasi_str}".strip(), 100)
