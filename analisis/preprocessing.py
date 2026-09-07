import re
import html
import csv
from pathlib import Path

from Sastrawi.Stemmer.StemmerFactory import StemmerFactory

# ── Path setup ────────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent.parent
KAMUS_DIR = BASE_DIR / 'kamus'

# ── Helpers baca kamus ────────────────────────────────────────────────────────

def _baca_csv_dict(nama_file, kolom_kunci, kolom_nilai):
    path = KAMUS_DIR / nama_file
    result = {}
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get(kolom_kunci):
                result[row[kolom_kunci].strip()] = row[kolom_nilai].strip()
    return result

def _baca_csv_set(nama_file, kolom):
    path = KAMUS_DIR / nama_file
    result = set()
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get(kolom):
                result.add(row[kolom].strip())
    return result

# ── Load semua kamus ──────────────────────────────────────────────────────────

EMOJI_DICT         = _baca_csv_dict('emoji_dict.csv', 'emoji', 'kata')
SLANG_DICT         = _baca_csv_dict('slang_typo_singkatan_inggris.csv', 'slang', 'formal')
KATA_TIDAK_PENTING = _baca_csv_set('kata_tidak_penting_untuk_sentimen.csv', 'kata')

# ── Stemmer ───────────────────────────────────────────────────────────────────

_base_stemmer = StemmerFactory().create_stemmer()
_stem_cache   = {}

def _stem(word):
    if word not in _stem_cache:
        _stem_cache[word] = _base_stemmer.stem(word)
    return _stem_cache[word]

KATA_NEGASI = {'tidak', 'bukan', 'belum', 'jangan', 'tanpa', 'kurang', 'tak'}

STEM_EXCEPTION = {
    'perbaiki', 'diperbaiki', 'memperbaiki',
    'ketidakpuasan', 'ketidaknyamanan', 'ketidaksesuaian',
    'terbaik', 'pengalaman', 'pertahankan',
}

# ── Step 1 — Case Folding ─────────────────────────────────────────────────────

def case_folding(text):
    return text.lower()

# ── Step 2 — Emoji ke Kata Sentimen ──────────────────────────────────────────

def emoji_ke_kata(text):
    for emoji, kata in EMOJI_DICT.items():
        text = text.replace(emoji, f' {kata} ')
    return text

# ── Step 3 — Cleaning ─────────────────────────────────────────────────────────

def cleaning(text):
    text = html.unescape(text)
    text = re.sub(r'http\S+|www\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ── Step 4 — Normalisasi Berulang ─────────────────────────────────────────────

def normalisasi_berulang(text):
    return re.sub(r'(.)\1{1,}', r'\1', text)

# ── Step 5 — Normalisasi Slang ────────────────────────────────────────────────

def normalisasi_slang(text):
    return ' '.join(SLANG_DICT.get(token, token) for token in text.split())

# ── Step 6 — Tokenisasi ───────────────────────────────────────────────────────

def tokenisasi(text):
    return text.split()

# ── Step 7 — Buang Kata Tidak Penting ────────────────────────────────────────

def buang_kata_tidak_penting(tokens):
    return [token for token in tokens if token not in KATA_TIDAK_PENTING and len(token) > 1]

# ── Step 8 — Stemming ────────────────────────────────────────────────────────

def stemming(tokens):
    return [t if t in STEM_EXCEPTION else _stem(t) for t in tokens]

# ── Step 9 — Negation Handling ───────────────────────────────────────────────

def negation_handling(tokens):
    hasil = []
    i = 0
    while i < len(tokens):
        if tokens[i] in KATA_NEGASI and i + 1 < len(tokens):
            hasil.append(tokens[i] + '_' + tokens[i + 1])
            i += 2
        else:
            hasil.append(tokens[i])
            i += 1
    return hasil

# ── Pipeline utama ────────────────────────────────────────────────────────────

def preprocess(text):
    text   = case_folding(text)
    text   = emoji_ke_kata(text)
    text   = cleaning(text)
    text   = normalisasi_berulang(text)
    text   = normalisasi_slang(text)
    tokens = tokenisasi(text)
    tokens = buang_kata_tidak_penting(tokens)
    tokens = stemming(tokens)
    tokens = negation_handling(tokens)
    return tokens


def bersihkan_teks(text):
    return ' '.join(preprocess(str(text)))


def tahapan_preprocessing(text):
    """Jalankan tiap tahap secara terpisah dan kembalikan detail perubahan."""
    text = str(text)

    s1 = case_folding(text)
    s2 = emoji_ke_kata(s1)
    s3 = cleaning(s2)
    s4 = normalisasi_berulang(s3)

    tanda_baca_dihapus = sorted(set(re.findall(r'[^\w\s]', s2)))

    normalisasi_changes = []
    tokens_s5 = []
    for token in s4.split():
        formal = SLANG_DICT.get(token, token)
        if formal != token:
            normalisasi_changes.append((token, formal))
        tokens_s5.append(formal)
    s5 = ' '.join(tokens_s5)

    tokens6 = tokenisasi(s5)
    stopword_dibuang = [t for t in tokens6 if t in KATA_TIDAK_PENTING or len(t) <= 1]
    tokens7 = buang_kata_tidak_penting(tokens6)

    stemming_changes = []
    tokens7_stem = []
    for t in tokens7:
        hasil = t if t in STEM_EXCEPTION else _stem(t)
        if hasil != t:
            stemming_changes.append((t, hasil))
        tokens7_stem.append(hasil)

    tokens8 = negation_handling(tokens7_stem)

    return {
        'asli'               : text,
        'case_folding'       : s1,
        'cleaning'           : s3,
        'tanda_baca_dihapus' : tanda_baca_dihapus,
        'normalisasi_changes': normalisasi_changes,
        'stopword_dibuang'   : stopword_dibuang,
        'stemming_changes'   : stemming_changes,
        'akhir'              : ' '.join(tokens8),
    }


if __name__ == "__main__":
    import sys, pandas as pd
    from collections import Counter
    from datetime import datetime

    SEP  = "=" * 60
    SEP2 = "-" * 60

    ROOT = Path(__file__).parent.parent
    PROC_DIR = ROOT / "data" / "processed"
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(
        (ROOT / "data" / "raw").rglob("google_maps*.csv"),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    if not raw_files:
        sys.exit("ERROR: Tidak ada file google_maps*.csv di data/raw/")

    df = pd.read_csv(raw_files[0], encoding="utf-8-sig")
    total_awal = len(df)
    df = df.dropna(subset=["komentar"]).copy()
    df = df[df["komentar"].astype(str).str.strip().str.len() > 0].copy()
    jumlah_tanpa_komentar = total_awal - len(df)
    print(f"\n{SEP}")
    print(f"  PREPROCESSING TEKS - SAOENK COBEK")
    print(SEP)
    print(f"  File           : {raw_files[0].name}")
    print(f"  Total awal     : {total_awal} baris")
    print(f"  Tanpa komentar : {jumlah_tanpa_komentar} baris dihapus (hanya rating)")
    print(f"  Tersisa        : {len(df)} baris")

    def _tampilkan_baris(df_s, label):
        print(f"\n  {label} (baris 1-10 + terakhir):")
        print(f"  {SEP2}")
        sampel_idx = list(range(min(10, len(df_s))))
        if len(df_s) > 10:
            sampel_idx.append(len(df_s) - 1)
        for pos in sampel_idx:
            row    = df_s.iloc[pos]
            nama   = str(row['nama_pengguna'])[:25] if 'nama_pengguna' in df_s.columns else '?'
            komen  = str(row['komentar'])[:65]      if 'komentar'      in df_s.columns else ''
            marker = "  <-- terakhir" if (pos == len(df_s) - 1 and len(df_s) > 10) else ""
            print(f"      [{pos+1:>4}] {nama:<26}| {komen}{marker}")

    def _norm(s):
        return s.astype(str).str.lower().str.replace(r'\s+', ' ', regex=True).str.strip()

    df["_nama_norm"]     = _norm(df["nama_pengguna"]) if "nama_pengguna" in df.columns else ""
    df["_komentar_norm"] = _norm(df["komentar"])

    # Hapus duplikat: nama + komentar sama
    df_ri        = df.reset_index(drop=True)
    mask_semua   = df_ri.duplicated(subset=["_nama_norm", "_komentar_norm"], keep=False)
    df_semua_dup = df_ri[mask_semua].sort_values(["_nama_norm", "_komentar_norm"])

    print(f"\n{SEP}")
    print(f"  STEP Hapus Duplikat Nama + Komentar Sama")
    print(SEP)

    if not df_semua_dup.empty:
        grp_key = None
        grp_num = 0
        for idx, row in df_semua_dup.iterrows():
            key = (row["_nama_norm"], row["_komentar_norm"])
            if key != grp_key:
                grp_num += 1
                grp_key = key
                print(f"\n    [Grup {grp_num}]")
            nama  = str(row.get('nama_pengguna', '?'))[:25]
            komen = str(row.get('komentar', ''))[:65]
            print(f"      Baris {idx+1:>4} : {nama:<26}| {komen}")
    else:
        print(f"  Tidak ada duplikat ditemukan.")

    mask_dup1  = df.duplicated(subset=["_nama_norm", "_komentar_norm"], keep="first")
    df_dup1_ex = df[mask_dup1].copy()
    df         = df[~mask_dup1].copy()
    print(f"\n  Dihapus: {len(df_dup1_ex)} baris -> tersisa {len(df)} baris")
    _tampilkan_baris(df, "Setelah hapus duplikat nama+komentar")

    # Hapus duplikat: komentar sama, nama beda
    mask_dup2  = df.duplicated(subset=["_komentar_norm"], keep="first")
    df_dup2_ex = df[mask_dup2].copy()
    df         = df[~mask_dup2].copy()

    print(f"\n{SEP}")
    print(f"  STEP: Hapus Duplikat Komentar Sama (Nama Beda)")
    print(SEP)
    print(f"  Dihapus: {len(df_dup2_ex)} baris")
    if len(df_dup2_ex) > 0:
        print(f"  Contoh baris dihapus (maks 10):")
        for _, row in df_dup2_ex.head(10).iterrows():
            nama  = str(row.get('nama_pengguna', '?'))[:25]
            komen = str(row.get('komentar', ''))[:65]
            print(f"      - {nama:<26}| {komen}")

    df = df.drop(columns=["_nama_norm", "_komentar_norm"]).copy()
    _tampilkan_baris(df, "Setelah hapus duplikat komentar")
    print(f"\n  Total akhir : {len(df)} baris (dari {total_awal} awal)")

    # ── Contoh tahapan (10 pertama + terakhir) ───────────────────────────────
    print(f"\n{SEP}")
    print("  CONTOH TAHAPAN TEXT PREPROCESSING (baris 1-10 + terakhir)")
    print(SEP)
    seri = df["komentar"].dropna().reset_index(drop=True)
    idx_contoh = list(range(min(10, len(seri))))
    if len(seri) > 10:
        idx_contoh.append(len(seri) - 1)
    for i in idx_contoh:
        teks  = seri.iloc[i]
        label = f"{i+1}" if i < 10 else f"{i+1} (terakhir)"
        h = tahapan_preprocessing(teks)
        print(f"\n  [{label}] Teks asli   : {h['asli']}")
        print(f"      Case folding : {h['case_folding']}")
        print(f"      Cleaning     : {h['cleaning']}")
        if h['tanda_baca_dihapus']:
            print(f"      Tanda baca dihapus: {' '.join(h['tanda_baca_dihapus'])}")
        if h['normalisasi_changes']:
            ubah = ', '.join(f"{a}->{b}" for a, b in h['normalisasi_changes'])
            print(f"      Slang diubah : {ubah}")
        if h['stopword_dibuang']:
            print(f"      Stopword dihapus: {', '.join(h['stopword_dibuang'])}")
        if h['stemming_changes']:
            stem = ', '.join(f"{a}->{b}" for a, b in h['stemming_changes'])
            print(f"      Stemming     : {stem}")
        print(f"      Hasil akhir  : {h['akhir']}")

    # ── Proses semua data + kumpulkan statistik ───────────────────────────────
    print(f"\n{SEP}")
    print("  MEMPROSES SEMUA DATA...")
    print(SEP)

    stopword_counter    = Counter()
    tanda_baca_counter  = Counter()
    slang_counter       = Counter()
    stemming_counter    = Counter()

    teks_bersih_list = []
    for teks in df["komentar"]:
        h = tahapan_preprocessing(str(teks))
        teks_bersih_list.append(h["akhir"])
        stopword_counter.update(h["stopword_dibuang"])
        tanda_baca_counter.update(h["tanda_baca_dihapus"])
        for a, b in h["normalisasi_changes"]:
            slang_counter[(a, b)] += 1
        for a, b in h["stemming_changes"]:
            stemming_counter[(a, b)] += 1

    df["teks_bersih"] = teks_bersih_list
    df = df[df["teks_bersih"].str.strip().str.len() > 0]

    # ── Laporan statistik ─────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  LAPORAN TIAP TAHAP PREPROCESSING")
    print(SEP)

    print(f"\n  [1] CLEANING - Tanda Baca & Simbol yang Dihapus")
    print(f"  {SEP2}")
    if tanda_baca_counter:
        for karakter, jumlah in tanda_baca_counter.most_common():
            print(f"      '{karakter}'  ->  {jumlah}x")
    else:
        print("      (tidak ada)")

    print(f"\n  [2] STOPWORD REMOVAL - Kata Tidak Penting (Top 20)")
    print(f"  {SEP2}")
    if stopword_counter:
        for kata, jumlah in stopword_counter.most_common(20):
            print(f"      {kata:<20} {jumlah}x")
    else:
        print("      (tidak ada)")

    print(f"\n  [3] NORMALISASI SLANG (Top 20)")
    print(f"  {SEP2}")
    if slang_counter:
        for (slang, formal), jumlah in slang_counter.most_common(20):
            print(f"      {slang:<20} -> {formal:<20} ({jumlah}x)")
    else:
        print("      (tidak ada)")

    print(f"\n  [4] STEMMING - Perubahan Kata (Top 20)")
    print(f"  {SEP2}")
    if stemming_counter:
        for (asal, stem), jumlah in stemming_counter.most_common(20):
            print(f"      {asal:<20} -> {stem:<20} ({jumlah}x)")
    else:
        print("      (tidak ada)")

    # ── Simpan hasil ──────────────────────────────────────────────────────────
    cols = list(df.columns)
    cols.remove("teks_bersih")
    idx = cols.index("komentar") + 1
    cols.insert(idx, "teks_bersih")
    df = df[cols]

    out = PROC_DIR / f"hasil_preprocessing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(out, index=False)
    print(f"\n{SEP}")
    print(f"  Selesai! {len(df)} baris -> data/processed/{out.name}")
    print(SEP)
