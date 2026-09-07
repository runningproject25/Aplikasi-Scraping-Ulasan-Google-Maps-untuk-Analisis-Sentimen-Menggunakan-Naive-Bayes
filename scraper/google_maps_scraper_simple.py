import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm
from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).parent.parent))
from config.branches import BRANCHES

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _get_db():
    from config.db import get_connection
    return get_connection()


# ── Browser helpers ───────────────────────────────────────────────────────────

def buka_tab_ulasan(page):
    try:
        page.get_by_role("tab", name=re.compile(r"Ulasan|Reviews", re.I)).click(timeout=8000)
        page.wait_for_timeout(3000)
    except Exception:
        pass
    _set_sort_terbaru(page)


def _set_sort_terbaru(page):
    # Klik tombol "Urutkan"
    try:
        btn = page.locator("button[aria-label*='Urutkan'], button[aria-label*='Sort']").first
        if btn.is_visible(timeout=3000):
            btn.click()
            page.wait_for_timeout(2000)
    except Exception:
        pass

    # Klik opsi "Terbaru" — cari berdasarkan teks, bukan data-index yang bisa berubah
    try:
        page.wait_for_selector(
            "div[role='menuitemradio'], li[role='menuitemradio']",
            state="visible", timeout=4000,
        )
        terpilih = page.evaluate("""() => {
            const items = document.querySelectorAll(
                'div[role="menuitemradio"], li[role="menuitemradio"]'
            );
            for (const el of items) {
                const txt = el.textContent.trim().toLowerCase();
                if (txt.includes('terbaru') || txt.includes('newest') || txt.includes('recent')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if terpilih:
            page.wait_for_timeout(2000)
    except Exception:
        pass


def _parse_bulan_lalu(tanggal_str):
    if not isinstance(tanggal_str, str) or not tanggal_str.strip():
        return None
    t = tanggal_str.lower().strip()
    if any(x in t for x in ["hari", "jam", "menit", "detik", "kemarin",
                              "day", "hour", "minute", "second", "yesterday", "just"]):
        return 0
    if "minggu" in t or "week" in t:
        m = re.search(r"(\d+)\s*(?:minggu|week)", t)
        return 1 if (int(m.group(1)) if m else 1) >= 4 else 0
    if "bulan" in t or "month" in t:
        if "sebulan" in t or "a month" in t:
            return 1
        m = re.search(r"(\d+)\s*(?:bulan|month)", t)
        return int(m.group(1)) if m else 1
    if "tahun" in t or "year" in t:
        if "setahun" in t or "a year" in t:
            return 12
        m = re.search(r"(\d+)\s*(?:tahun|year)", t)
        return int(m.group(1)) * 12 if m else 12
    return None


def _get_last_visible_date(page):
    try:
        teks = page.evaluate("""() => {
            for (const sel of ['span.rsqaWe', 'span.dehysf', 'li.DU9Pgb span']) {
                const els = document.querySelectorAll(sel);
                if (els.length) return els[els.length - 1].innerText;
            }
            return null;
        }""")
        return _parse_bulan_lalu(teks) if teks else None
    except Exception:
        return None


def tutup_dialog(page):
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass


# ── Ekstrak review dari DOM ───────────────────────────────────────────────────

def ambil_review_dari_halaman(page):
    tutup_dialog(page)
    page.wait_for_timeout(4000)

    try:
        for _ in range(5):
            jumlah = page.evaluate("""() => {
                const btns = document.querySelectorAll('button.w8nwRe');
                btns.forEach(b => b.click());
                return btns.length;
            }""")
            if not jumlah:
                break
            page.wait_for_timeout(3000)
    except Exception:
        pass

    page.wait_for_timeout(5000)
    try:
        page.evaluate("""() => {
            document.querySelectorAll('button.w8nwRe').forEach(b => b.click());
        }""")
        page.wait_for_timeout(4000)
    except Exception:
        pass

    try:
        raw = page.evaluate("""() => {
            let els = document.querySelectorAll('div[data-review-id]');
            if (!els.length) els = document.querySelectorAll('div.jJc9Ad');
            if (!els.length) els = document.querySelectorAll('div.GHT2ce');

            var ATTR_MAP = {
                'makanan': 'rating_makanan',
                'layanan': 'rating_layanan',
                'suasana': 'rating_suasana',
            };

            return Array.from(els).map(el => {
                let teks = '';
                const tEl = el.querySelector('span.wiI7pd');
                if (tEl) teks = tEl.innerText.trim();

                let nama = '';
                const nEl = el.querySelector('div.d4r55');
                if (nEl) nama = nEl.innerText.trim();

                let rating = null;
                const rEl = el.querySelector('span[aria-label]');
                if (rEl) {
                    const m = rEl.getAttribute('aria-label').match(/(\\d)/);
                    if (m) rating = parseInt(m[1]);
                }

                let tanggal = '';
                const dEl = el.querySelector('span.rsqaWe');
                if (dEl) tanggal = dEl.innerText.trim();

                var rating_makanan = null, rating_layanan = null, rating_suasana = null;

                try {
                    var firstPBK = el.querySelector('div.PBK6be');
                    var attrEls = [];
                    if (firstPBK) {
                        var pbkParent = firstPBK.parentElement;
                        var prev = firstPBK.previousElementSibling;
                        if (prev && prev.tagName === 'DIV' && prev.querySelector('span.RfDO5c')) {
                            attrEls.push(prev);
                        }
                        var pbks = pbkParent.querySelectorAll(':scope > div.PBK6be');
                        for (var qi = 0; qi < pbks.length; qi++) attrEls.push(pbks[qi]);
                    }
                    for (var pi = 0; pi < attrEls.length; pi++) {
                        var divs = attrEls[pi].querySelectorAll(':scope > div');
                        var lbl = '', val = '';
                        if (divs.length >= 2) {
                            var lSpan = divs[0].querySelector('span.RfDO5c');
                            var vSpan = divs[1].querySelector('span.RfDO5c');
                            if (lSpan) {
                                var bEl = lSpan.querySelector('[style*="font-weight"], b');
                                lbl = (bEl ? bEl : lSpan).innerText.replace(/\xa0/g, ' ').trim().toLowerCase();
                            }
                            if (vSpan) {
                                var vInner = vSpan.querySelector('span');
                                if (vInner) {
                                    var vAria = vInner.getAttribute('aria-label');
                                    val = (vAria || vInner.innerText).replace(/ /g, ' ').trim();
                                } else {
                                    val = vSpan.innerText.replace(/ /g, ' ').trim();
                                }
                            }
                        } else if (divs.length === 1) {
                            var rSpan = divs[0].querySelector('span.RfDO5c');
                            if (rSpan) {
                                var iSpan = rSpan.querySelector('span');
                                if (iSpan) {
                                    var bEl2 = iSpan.querySelector('b');
                                    if (bEl2) {
                                        lbl = bEl2.innerText.replace(':', '').trim().toLowerCase();
                                        val = iSpan.innerText.replace(bEl2.innerText, '').trim();
                                    }
                                }
                            }
                        }
                        if (lbl && val) {
                            var fld = ATTR_MAP[lbl];
                            if (fld === 'rating_makanan') rating_makanan = val;
                            else if (fld === 'rating_layanan') rating_layanan = val;
                            else if (fld === 'rating_suasana') rating_suasana = val;
                        }
                    }
                } catch(e) {}

                return {
                    review_id: el.getAttribute('data-review-id') || '',
                    nama: nama, rating: rating, teks: teks, tanggal: tanggal,
                    rating_makanan: rating_makanan,
                    rating_layanan: rating_layanan,
                    rating_suasana: rating_suasana,
                };
            });
        }""")
    except Exception:
        return []

    hasil = []
    for r in raw:
        hasil.append({
            "review_id":      r.get("review_id", ""),
            "nama_pengguna":  r.get("nama", ""),
            "rating":         r.get("rating"),
            "komentar":       r.get("teks", ""),
            "tanggal":        r.get("tanggal", ""),
            "rating_makanan": r.get("rating_makanan"),
            "rating_layanan": r.get("rating_layanan"),
            "rating_suasana": r.get("rating_suasana"),
        })
    return hasil


# ── Scrape satu cabang ────────────────────────────────────────────────────────

def scrape_reviews(page, maps_url, nama_cabang, months_ago_target=None):
    """
    Ambil review dari halaman Google Maps.

    months_ago_target:
        None  → kumpulkan semua review (mode dataset/semua data)
        0–1   → kumpulkan langsung, stop saat melewati bulan target
        ≥2    → Phase 1 fast-skip, lalu Phase 2 collect (mode per-bulan lama)
    """
    print(f"\n[Google Maps] Scraping: {nama_cabang}")
    page.goto(maps_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    buka_tab_ulasan(page)

    review_muncul = False
    for _ in range(5):
        try:
            n = page.evaluate("""() => {
                var els = document.querySelectorAll('div[data-review-id]');
                if (!els.length) els = document.querySelectorAll('div.jJc9Ad');
                if (!els.length) els = document.querySelectorAll('div.GHT2ce');
                return els.length;
            }""")
            if n and n > 0:
                review_muncul = True
                break
        except Exception:
            pass
        page.wait_for_timeout(3000)

    if not review_muncul:
        print(f"  Review belum muncul, coba buka tab ulasan lagi...")
        buka_tab_ulasan(page)
        page.wait_for_timeout(6000)

    reviews = []
    review_dict = {}
    scroll_kosong = 0

    pbar = tqdm(desc=f"  {nama_cabang}", unit=" ulasan", file=sys.stdout)

    def _scroll_panel(px=None):
        try:
            if px is None:
                scrolled = page.evaluate("""() => {
                    for (const sel of ['div.m6QErb.DxyBCb', 'div[role="feed"]', 'div.m6QErb']) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) {
                            const before = el.scrollTop;
                            el.scrollTop = el.scrollHeight;
                            return el.scrollTop - before;
                        }
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                    return 1;
                }""")
            else:
                scrolled = page.evaluate(f"""() => {{
                    for (const sel of ['div.m6QErb.DxyBCb', 'div[role="feed"]', 'div.m6QErb']) {{
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) {{
                            const before = el.scrollTop;
                            el.scrollTop += {px};
                            return el.scrollTop - before;
                        }}
                    }}
                    window.scrollTo(0, window.scrollY + {px});
                    return {px};
                }}""")
            return scrolled if scrolled else 0
        except Exception:
            return 0

    while True:
        if months_ago_target is not None:
            last = _get_last_visible_date(page)
            dekat_target = last is None or last >= months_ago_target - 1
        else:
            dekat_target = True

        if not dekat_target:
            _scroll_panel(8000)
            page.wait_for_timeout(700)
            continue

        baru = ambil_review_dari_halaman(page)

        if baru:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ditambah = 0
            berhenti = False

            for r in baru:
                rid    = r.get("review_id", "")
                teks_r = r.get("komentar", "")
                key    = rid if rid else (r.get("nama_pengguna", "") + "|" + teks_r)

                bulan_lalu = _parse_bulan_lalu(r.get("tanggal", ""))

                perlu_collect = False
                if months_ago_target is None:
                    perlu_collect = True
                elif bulan_lalu is not None and bulan_lalu > months_ago_target:
                    berhenti = True
                    break
                elif bulan_lalu == months_ago_target:
                    perlu_collect = True
                elif bulan_lalu is None and teks_r.strip():
                    perlu_collect = True

                if not perlu_collect:
                    continue

                r.update({"cabang": nama_cabang, "platform": "Google Maps",
                           "tanggal_scraping": ts})

                if key in review_dict:
                    idx = review_dict[key]
                    if len(teks_r) > len(reviews[idx].get("komentar", "")):
                        reviews[idx]["komentar"] = teks_r
                else:
                    review_dict[key] = len(reviews)
                    reviews.append(r)
                    ditambah += 1

            if ditambah:
                pbar.update(ditambah)
                scroll_kosong = 0
            else:
                scroll_kosong += 1

            if berhenti:
                print(f"  Berhenti: melewati bulan target. Terkumpul: {len(reviews)}")
                break
        else:
            scroll_kosong += 1

        if scroll_kosong >= 10:
            print(f"  Tidak ada review baru setelah 10 iterasi. Total: {len(reviews)}")
            break

        _scroll_panel()
        page.wait_for_timeout(5000 if scroll_kosong > 0 else 4000)

    pbar.close()
    return reviews


# ── Orchestration: scraping → DB (dipanggil dari app.py) ─────────────────────

def _scraping_google_maps(update_status, harus_berhenti=None, bulan=None, tahun=None, cabang=None):
    months_ago_target = None
    if bulan and tahun:
        now = datetime.now()
        months_ago_target = max(0, (now.year - tahun) * 12 + (now.month - bulan))

    cabang_list = list(BRANCHES.items())
    if cabang:
        cabang_list = [(k, v) for k, v in cabang_list if v["nama"] == cabang]
    total = len(cabang_list)

    semua_reviews = []
    update_status("scraping", "Membuka browser Chromium...", 3)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="id-ID", viewport={"width": 1280, "height": 800})
        page = context.new_page()
        context.on("page", lambda new_page: new_page.close())

        update_status("scraping", "Inisialisasi sesi browser...", 4)
        try:
            page.goto("https://www.google.com/maps", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        except Exception:
            pass
        update_status("scraping", "Browser siap. Memulai scraping...", 5)

        for i, (_, info) in enumerate(cabang_list):
            if harus_berhenti and harus_berhenti():
                update_status("dihentikan", "Scraping dihentikan oleh admin.", 0)
                break

            progress = 5 + int((i / total) * 45)
            update_status("scraping", f"Scraping {info['nama']} ({i+1}/{total})...", progress)

            try:
                reviews = scrape_reviews(
                    page, info["google_maps_url"], info["nama"],
                    months_ago_target=months_ago_target,
                )
                semua_reviews.extend(reviews)
                update_status("scraping", f"  ✓ {len(reviews)} ulasan dari {info['nama']}", progress)
            except Exception as exc:
                update_status("scraping", f"  ✗ Gagal {info['nama']}: {exc}", progress)

        browser.close()

    if not semua_reviews:
        return pd.DataFrame()

    # Deduplication — buang review yang review_id-nya sudah ada di DB
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT review_id FROM komentar WHERE review_id IS NOT NULL AND review_id != ''")
        existing_ids = {r[0] for r in cursor.fetchall()}
        conn.close()
        sebelum = len(semua_reviews)
        semua_reviews = [r for r in semua_reviews
                         if not r.get("review_id") or r["review_id"] not in existing_ids]
        update_status("scraping",
                      f"  Deduplication: {sebelum} → {len(semua_reviews)} ulasan baru (belum ada di database)", 50)
    except Exception:
        pass

    return pd.DataFrame(semua_reviews)


def _filter_bulan(df, target_bulan, target_tahun, update_status):
    now = datetime.now()
    months_ago_target = (now.year - target_tahun) * 12 + (now.month - target_bulan)
    sebelum = len(df)

    def cocok(tanggal_str):
        bln = _parse_bulan_lalu(tanggal_str)
        return True if bln is None else bln == months_ago_target

    df_filtered = df[df["tanggal"].apply(cocok)].copy()
    update_status(
        "scraping",
        f"  Filter bulan: {sebelum} → {len(df_filtered)} ulasan "
        f"(perkiraan {months_ago_target} bulan lalu = bulan target).",
        52,
    )
    return df_filtered


def _simpan_mentah_ke_mysql(df, id_sesi_scraping):
    conn = _get_db()
    cursor = conn.cursor()

    def _int(v):
        try: return int(v) if pd.notna(v) else None
        except (TypeError, ValueError): return None

    def _str(v, default=""):
        try: return default if pd.isna(v) else (str(v) if v is not None else default)
        except (TypeError, ValueError): return str(v) if v is not None else default

    rows = [
        (
            id_sesi_scraping,
            _str(row.get("cabang")),
            _str(row.get("nama_pengguna")),
            _int(row.get("rating")),
            _str(row.get("komentar")),
            _str(row.get("tanggal_scraping")) or None,
            _str(row.get("review_id")) or None,
            _int(row.get("rating_makanan")),
            _int(row.get("rating_layanan")),
            _int(row.get("rating_suasana")),
        )
        for _, row in df.iterrows()
    ]

    cursor.executemany("""
        INSERT INTO komentar
            (id_sesi_scraping, cabang, nama_pengguna, rating, komentar, tanggal_scraping,
             review_id, rating_makanan, rating_layanan, rating_suasana)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, rows)

    cursor.execute("SELECT COUNT(*) FROM komentar WHERE id_sesi_scraping=%s", (id_sesi_scraping,))
    total = cursor.fetchone()[0]

    cursor.execute("""
        UPDATE scraping_sessions
        SET status='terkumpul', jumlah_data=%s, selesai_pada=NOW()
        WHERE id=%s
    """, (total, id_sesi_scraping))

    conn.commit()
    conn.close()


def hanya_scraping(id_sesi_scraping: int, update_status, bulan: int = None, tahun: int = None,
                   harus_berhenti=None, cabang: str = None):
    try:
        df_raw = _scraping_google_maps(update_status, harus_berhenti=harus_berhenti,
                                       bulan=bulan, tahun=tahun, cabang=cabang)

        if bulan and tahun and not df_raw.empty:
            df_raw = _filter_bulan(df_raw, bulan, tahun, update_status)

        if harus_berhenti and harus_berhenti():
            conn = _get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scraping_sessions SET status='gagal', selesai_pada=NOW() WHERE id=%s",
                (id_sesi_scraping,)
            )
            conn.commit()
            conn.close()
            return

        if df_raw.empty:
            conn = _get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scraping_sessions SET status='tidak_tersedia', selesai_pada=NOW() WHERE id=%s",
                (id_sesi_scraping,)
            )
            conn.commit()
            conn.close()
            update_status("tidak_tersedia", "Tidak ada ulasan baru ditemukan untuk periode ini.", 100)
            return

        update_status("scraping", f"Scraping selesai: {len(df_raw)} ulasan baru ditemukan.", 50)
        update_status("saving", f"Menyimpan {len(df_raw)} komentar ke database...", 80)
        _simpan_mentah_ke_mysql(df_raw, id_sesi_scraping)
        update_status(
            "terkumpul",
            f"Selesai! {len(df_raw)} komentar baru tersimpan. Lakukan Analisis Sentimen dari Dashboard.",
            100,
        )

    except Exception as exc:
        update_status("gagal", str(exc), 0)
        try:
            conn = _get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scraping_sessions SET status='gagal', selesai_pada=NOW() WHERE id=%s",
                (id_sesi_scraping,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        raise


# ── Simpan ke file (CLI) ──────────────────────────────────────────────────────

def simpan_data(reviews, prefix):
    if not reviews:
        print(f"  Tidak ada data ({prefix})")
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df = pd.DataFrame(reviews)
    df.to_csv(OUTPUT_DIR / f"{prefix}_{timestamp}.csv", index=False, encoding="utf-8-sig")
    df.to_excel(OUTPUT_DIR / f"{prefix}_{timestamp}.xlsx", index=False)
    print(f"  Tersimpan: {len(reviews)} review → data/raw/{prefix}_{timestamp}.csv")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    """Scraping semua cabang, semua data (untuk dataset/labeling)."""
    semua_reviews = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="id-ID", viewport={"width": 1280, "height": 800})
        page = context.new_page()
        context.on("page", lambda p: p.close())

        print("[Warm-up] Inisialisasi sesi browser Google Maps...")
        try:
            page.goto("https://www.google.com/maps", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        except Exception:
            pass

        for kode_cabang, info in BRANCHES.items():
            reviews = scrape_reviews(page, info["google_maps_url"], info["nama"],
                                     months_ago_target=None)
            semua_reviews.extend(reviews)
            simpan_data(reviews, f"google_maps_{kode_cabang}")

        browser.close()

    simpan_data(semua_reviews, "google_maps_all")
    print(f"\nSelesai! Total: {len(semua_reviews)} review dari semua cabang")


if __name__ == "__main__":
    main()
