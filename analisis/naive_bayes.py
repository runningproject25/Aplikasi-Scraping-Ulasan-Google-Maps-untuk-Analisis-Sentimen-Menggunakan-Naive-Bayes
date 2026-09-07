import sys
import warnings
from pathlib import Path
from datetime import datetime
import joblib

import pandas as pd
import numpy as np
from sklearn.naive_bayes import ComplementNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import classification_report, accuracy_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).parent.parent))

OUTPUT_DIR = Path(__file__).parent.parent / "output"
MODEL_DIR  = Path(__file__).parent.parent / "model"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    """Pilih file berlabel dari data/processed/labeling/."""
    ROOT = Path(__file__).parent.parent
    LABELING_DIR = ROOT / "data" / "processed" / "labeling"
    semua = sorted(
        [f for f in LABELING_DIR.glob("*")
         if f.suffix in (".csv", ".xlsx") and not f.name.startswith("~$")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not semua:
        print(f"ERROR: Tidak ada file ditemukan di folder {LABELING_DIR}")
        sys.exit(1)

    f = semua[0]
    df = pd.read_excel(f) if f.suffix == ".xlsx" else pd.read_csv(f, encoding="utf-8-sig")
    print(f"Dimuat: {f.name} ({len(df)} baris)")
    return df


def siapkan_data(df):
    print("\n[1] Menyiapkan data...")
    print(f"  Data siap: {len(df)} baris")
    print("\n  Distribusi label:")
    print(df["label"].value_counts().to_string())
    return df


def latih_model(df):
    """Latih model Naive Bayes."""
    print("\n[2] Melatih model Naive Bayes...")

    X = df["teks_bersih"]
    y = df["label"]

    # Split data train/test (80:20) DULU 
    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # TF-IDF vectorizer — fit hanya pada train set
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    X_train = vectorizer.fit_transform(X_train_raw)
    X_test  = vectorizer.transform(X_test_raw)

    print(f"  Data latih: {X_train.shape[0]} | Data uji: {X_test.shape[0]}")

    # Distribusi kelas
    dist = y_train.value_counts()
    print(f"  Distribusi train: {dist.to_dict()}")

    bobot = compute_sample_weight("balanced", y_train)

    # Tuning alpha — cross-validation di train set saja, test set tidak disentuh
    kandidat_alpha = [0.01, 0.05, 0.1, 0.3, 0.5, 1.0]
    print("  Tuning alpha ComplementNB (cross-validation 5-fold di train set)...")
    alpha_terbaik = 0.1
    akurasi_terbaik = 0.0
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    for a in kandidat_alpha:
        skor_fold = []
        for fold_train, fold_val in cv.split(X_train, y_train):
            m = ComplementNB(alpha=a)
            bobot_fold = compute_sample_weight("balanced", y_train.iloc[fold_train])
            m.fit(X_train[fold_train], y_train.iloc[fold_train], sample_weight=bobot_fold)
            skor_fold.append(accuracy_score(y_train.iloc[fold_val], m.predict(X_train[fold_val])))
        rata = np.mean(skor_fold)
        print(f"    alpha={a:.2f}  →  CV akurasi={rata*100:.2f}%")
        if rata > akurasi_terbaik:
            akurasi_terbaik = rata
            alpha_terbaik = a

    print(f"  Alpha terbaik: {alpha_terbaik} (CV akurasi={akurasi_terbaik*100:.2f}%)")
    model = ComplementNB(alpha=alpha_terbaik)
    model.fit(X_train, y_train, sample_weight=bobot)

    # Prediksi
    y_pred = model.predict(X_test)

    return model, vectorizer, y_test, y_pred


def evaluasi_model(y_test, y_pred):
    """Evaluasi dan tampilkan hasil model."""
    print("\n[3] Evaluasi Model")
    print("=" * 50)

    akurasi = accuracy_score(y_test, y_pred)
    print(f"  Akurasi: {akurasi:.4f} ({akurasi*100:.2f}%)")

    print("\n  Classification Report:")
    print(classification_report(y_test, y_pred))

    return akurasi


def buat_visualisasi(y_test, y_pred, akurasi):
    """Buat confusion matrix."""
    print("\n[4] Membuat visualisasi...")
    from sklearn.metrics import confusion_matrix
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    fig, ax = plt.subplots(figsize=(7, 6))
    labels_unik = sorted(y_test.unique())
    cm = confusion_matrix(y_test, y_pred, labels=labels_unik)
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=labels_unik, yticklabels=labels_unik, ax=ax,
    )
    ax.set_title(f"Confusion Matrix\nAkurasi: {akurasi*100:.2f}%", fontsize=13, fontweight="bold")
    ax.set_xlabel("Prediksi")
    ax.set_ylabel("Aktual")
    plt.tight_layout()
    path = OUTPUT_DIR / f"confusion_matrix_{timestamp}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Disimpan: {path.name}")


def simpan_hasil(df, model, vectorizer, akurasi):
    """Simpan hasil prediksi dan model."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Prediksi semua data
    X_all = vectorizer.transform(df["teks_bersih"])
    df["sentimen_prediksi"] = model.predict(X_all)
    proba = model.predict_proba(X_all)
    df["confidence"] = proba.max(axis=1).round(4)

    # Simpan CSV hasil
    output_csv = OUTPUT_DIR / f"hasil_sentimen_{timestamp}.csv"
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    df.to_excel(OUTPUT_DIR / f"hasil_sentimen_{timestamp}.xlsx", index=False)

    # Ringkasan per cabang
    ringkasan = df.groupby(["cabang", "sentimen_prediksi"]).size().unstack(fill_value=0)
    ringkasan["Total"] = ringkasan.sum(axis=1)
    ringkasan_path = OUTPUT_DIR / f"ringkasan_cabang_{timestamp}.csv"
    ringkasan.to_csv(ringkasan_path, encoding="utf-8-sig")

    print(f"\n  Hasil disimpan: {output_csv.name}")
    print(f"  Ringkasan cabang: {ringkasan_path.name}")

    print("\n=== RINGKASAN HASIL ===")
    print(ringkasan.to_string())
    print(f"\nAkurasi Model: {akurasi*100:.2f}%")


def simpan_model(model, vectorizer, akurasi):
    """Simpan model, vectorizer, dan akurasi ke folder model/ untuk dipakai web app."""
    joblib.dump(model,      MODEL_DIR / "naive_bayes.pkl")
    joblib.dump(vectorizer, MODEL_DIR / "vectorizer.pkl")
    (MODEL_DIR / "akurasi.txt").write_text(str(akurasi))
    print(f"\n[5] Model tersimpan di folder model/")
    print(f"    naive_bayes.pkl, vectorizer.pkl, akurasi.txt")


def main():
    print("=" * 55)
    print("  ANALISIS SENTIMEN - NAIVE BAYES CLASSIFIER")
    print("  Saoenk Cobek Makassar")
    print("=" * 55)

    df = load_data()
    df = siapkan_data(df)
    model, vectorizer, y_test, y_pred = latih_model(df)
    akurasi = evaluasi_model(y_test, y_pred)
    buat_visualisasi(y_test, y_pred, akurasi)
    simpan_hasil(df, model, vectorizer, akurasi)
    simpan_model(model, vectorizer, akurasi)

    print("\nSelesai! Cek folder output/ untuk hasil dan grafik.")


if __name__ == "__main__":
    main()
