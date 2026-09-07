# ════════════════════════════════════════════════════════════════════════════
# HAL LAIN — setup, koneksi database, helper (tidak terikat template tertentu)
# ════════════════════════════════════════════════════════════════════════════

import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path

import mysql.connector
from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.append(str(Path(__file__).parent))

app = Flask(__name__)
app.secret_key = "saoenk_admin_2026_secret"

NAMA_BULAN = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

KATA_ASPEK = {
    'Makanan': {
        'enak', 'lezat', 'gurih', 'pedas', 'hambar', 'asin', 'manis', 'pahit',
        'makanan', 'menu', 'rasa', 'porsi', 'masakan', 'sambal', 'cobek',
        'bumbu', 'segar', 'basi', 'sajian', 'hidangan', 'nasi', 'ayam',
        'ikan', 'seafood', 'daging', 'sayur', 'kuah', 'sup', 'soto',
        'nikmat', 'sedap', 'crispy', 'fresh', 'minuman', 'jus',
        'lauk', 'gorengan', 'mie', 'bakso', 'sate', 'bakar', 'goreng',
        'rebus', 'kukus', 'matang', 'mentah', 'penyajian', 'disajikan', 'makan',
    },
    'Layanan': {
        'pelayan', 'pelayanan', 'ramah', 'lama', 'cepat', 'lambat',
        'antri', 'antrian', 'tunggu', 'kasir', 'staff', 'karyawan',
        'pramusaji', 'order', 'pesanan', 'salah', 'sigap', 'responsif',
        'melayani', 'layanan', 'servis', 'service', 'waitress', 'waiter',
        'pesan', 'diantar', 'antar', 'layan', 'sopan', 'cuek', 'slow',
        'cekatan', 'tanggap', 'respon', 'minta', 'komplain', 'makasih', 'terimakasih', 'terima',
    },
    'Suasana': {
        'pandang', 'tempat', 'suasana', 'parkir', 'bersih', 'kotor', 'nyaman',
        'ramai', 'sepi', 'meja', 'kursi', 'toilet', 'wc', 'wifi',
        'musik', 'dekorasi', 'instagramable', 'ac', 'panas', 'dingin',
        'lokasi', 'interior', 'eksterior', 'outdoor', 'indoor',
        'gedung', 'ruangan', 'atmosfer', 'ambiance', 'tempatnya',
        'strategis', 'jauh', 'dekat', 'akses', 'jalan', 'lingkungan',
    },
}


def _deteksi_aspek(teks_bersih):
    kata_set = set((teks_bersih or '').lower().split())
    return [asp for asp, kata in KATA_ASPEK.items() if kata_set.intersection(kata)]


def _aspek_sentimen(komentar_list):
    stats = {asp: {'Positif': 0, 'Netral': 0, 'Negatif': 0} for asp in KATA_ASPEK}
    for k in komentar_list:
        aspek = _deteksi_aspek(k['teks_bersih'])
        for asp in aspek:
            stats[asp][k['sentimen']] += 1
    return stats

def _top_kata(komentar_list, sentimen, n=10):
    kata = []
    for k in komentar_list:
        if k['sentimen'] != sentimen:
            continue
        kalimat = k['teks_bersih']
        if not kalimat:
            continue
        kata += kalimat.split()
    return Counter(kata).most_common(n)


# Status job scraping yang sedang berjalan {session_id: {status, pesan, progress}}
scraping_jobs: dict = {}

# Status job analisis semua data {status, pesan, progress}
analisis_job: dict = {}


def get_db():
    from config.db import get_connection
    return get_connection()


def init_db():
    """Buat database dan tabel jika belum ada."""
    schema = Path(__file__).parent / "database" / "schema.sql"
    conn = mysql.connector.connect(host="localhost", user="root", password="")
    cursor = conn.cursor()
    for stmt in schema.read_text(encoding="utf-8").split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                cursor.execute(stmt)
            except Exception:
                pass
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_globals():
    from config.branches import BRANCHES
    now = datetime.now()
    return dict(
        BRANCHES=BRANCHES,
        NAMA_BULAN=NAMA_BULAN,
        bulan_sekarang=now.month,
        tahun_sekarang=now.year,
    )


# ════════════════════════════════════════════════════════════════════════════
# SIGNUP.HTML — pendaftaran admin pertama
# ════════════════════════════════════════════════════════════════════════════

@app.route("/signup", methods=["GET", "POST"])
def signup():
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM admins LIMIT 1")
    has_admin = cursor.fetchone() is not None

    error = None
    if request.method == "POST":
        if has_admin:
            conn.close()
            return redirect(url_for("signup"))
        username   = request.form.get("username", "").strip()
        password   = request.form.get("password", "")
        konfirmasi = request.form.get("konfirmasi", "")
        if not username or not password:
            error = "Username dan password wajib diisi."
        elif len(password) < 6:
            error = "Password minimal 6 karakter."
        elif password != konfirmasi:
            error = "Konfirmasi password tidak cocok."
        else:
            try:
                cursor.execute(
                    "INSERT INTO admins (username, password_hash, role) VALUES (%s, %s, 'admin')",
                    (username, generate_password_hash(password)),
                )
                conn.commit()
                conn.close()
                flash("Akun admin berhasil dibuat. Silakan login.", "success")
                return redirect(url_for("login"))
            except mysql.connector.IntegrityError:
                error = f"Username '{username}' sudah digunakan."

    conn.close()
    return render_template("signup.html", has_admin=has_admin, error=error)


# ════════════════════════════════════════════════════════════════════════════
# LOGIN.HTML — autentikasi admin
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD.HTML — halaman utama setelah login
# ════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    from config.branches import BRANCHES

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # KARTU kecil statistik dan grafik distribusi sentimen
    cursor.execute(
        "SELECT SUM(jumlah_data)    AS total, "
        "       SUM(jumlah_positif) AS positif, "
        "       SUM(jumlah_netral)  AS netral, "
        "       SUM(jumlah_negatif) AS negatif "
        "FROM scraping_sessions WHERE bulan != 0"
    )
    tbl_scraping_session         = cursor.fetchone()
    total_ulasan             = int(tbl_scraping_session["total"]   or 0)
    total_sentimen_positif = int(tbl_scraping_session["positif"] or 0)
    total_sentimen_netral  = int(tbl_scraping_session["netral"]  or 0)
    total_sentimen_negatif = int(tbl_scraping_session["negatif"] or 0)

    # KARTU akurasi
    akurasi_model_path = Path(__file__).parent / "model" / "akurasi.txt"
    try:
        akurasi_model = float(akurasi_model_path.read_text().strip())
    except Exception:
        akurasi_model = None

    # GRAFIK Perbandingan Sentimen per Cabang
    cursor.execute(
        "SELECT cabang, "
        "SUM(jumlah_positif) AS positif, "
        "SUM(jumlah_netral)  AS netral, "
        "SUM(jumlah_negatif) AS negatif "
        "FROM scraping_sessions "
        "WHERE status='selesai' AND bulan != 0 AND cabang IS NOT NULL "
        "GROUP BY cabang"
    )
    data_sentimen_tiap_cabang: dict = {
        r["cabang"]: {
            "Positif": int(r["positif"] or 0),
            "Netral":  int(r["netral"]  or 0),
            "Negatif": int(r["negatif"] or 0),
        }
        for r in cursor.fetchall()
    }

    # GRAFIK ASPEK
    cursor.execute(
        "SELECT k.teks_bersih, k.sentimen, s.bulan "
        "FROM komentar k JOIN scraping_sessions s ON k.id_sesi_scraping = s.id "
        "WHERE s.status='selesai' AND s.bulan != 0 "
        "ORDER BY s.bulan DESC"
    )
    data_teks_bersih_sentimen_bulan = cursor.fetchall()

    # kelompokkan data_teks_bersih_sentimen_bulan berdasarkan bulan untuk analisis aspek dan word cloud per bulan.
    data_tiap_bulan: dict = {}
    for row in data_teks_bersih_sentimen_bulan:
        lbl = NAMA_BULAN[row['bulan']]
        if lbl not in data_tiap_bulan:
            data_tiap_bulan[lbl] = []
        data_tiap_bulan[lbl].append(row)

    daftar_bulan = list(data_tiap_bulan.keys())

    # analisis aspek untuk semua bulan, bulan mei, bulan juni, dst.
    aspek_data: dict = {"Semua Bulan": _aspek_sentimen(data_teks_bersih_sentimen_bulan)}
    for lbl, rows in data_tiap_bulan.items():
        aspek_data[lbl] = _aspek_sentimen(rows)

    # GRAFIK tren bulan ke bulan
    cursor.execute(
        "SELECT bulan, cabang, jumlah_positif AS positif, jumlah_netral AS netral, jumlah_negatif AS negatif "
        "FROM scraping_sessions "
        "WHERE status='selesai' AND bulan != 0 "
        "ORDER BY bulan ASC"
    )
    data_sent_tiap_bln_dari_cab_tertentu: dict = {"Semua Cabang": {}}
    for r in cursor.fetchall():
        cab   = r["cabang"] 
        label = NAMA_BULAN[r['bulan']]
        pos   = int(r["positif"])
        net   = int(r["netral"])
        neg   = int(r["negatif"])
        sc    = data_sent_tiap_bln_dari_cab_tertentu["Semua Cabang"]
        if label not in sc:
            sc[label] = {"positif": 0, "netral": 0, "negatif": 0}
        sc[label]["positif"] += pos
        sc[label]["netral"]  += net
        sc[label]["negatif"] += neg
        if cab not in data_sent_tiap_bln_dari_cab_tertentu:
            data_sent_tiap_bln_dari_cab_tertentu[cab] = {}
        data_sent_tiap_bln_dari_cab_tertentu[cab][label] = {"positif": pos, "netral": net, "negatif": neg}

    # TOP KATA
    def _wc_pair(rows):
        return {"positif": _top_kata(rows, 'Positif'), "negatif": _top_kata(rows, 'Negatif')}

    wordcloud_all: dict = _wc_pair(data_teks_bersih_sentimen_bulan)

    # TABEL hasil analisis
    cursor.execute(
        "SELECT id, bulan, tahun, cabang, status, jumlah_data, "
        "jumlah_positif, jumlah_netral, jumlah_negatif, akurasi "
        "FROM scraping_sessions WHERE bulan != 0 "
        "ORDER BY id DESC LIMIT 4"
    )
    
    riwayat_terakhir = cursor.fetchall()
    for s in riwayat_terakhir:
        s["nama_bulan"] = NAMA_BULAN[s["bulan"]]

    conn.close()

    # Ambil data word cloud untuk bulan yang sedang ditampilkan.
    sesi = {
        "jumlah_data":    total_ulasan,
        "jumlah_positif": total_sentimen_positif,
        "jumlah_netral":  total_sentimen_netral,
        "jumlah_negatif": total_sentimen_negatif,
        "akurasi":        akurasi_model,
    }

    return render_template(
        "dashboard.html",
        sesi=sesi,
        aspek_data=aspek_data,
        data_sentimen_tiap_cabang=data_sentimen_tiap_cabang,
        wordcloud_all=wordcloud_all,
        daftar_bulan=daftar_bulan,
        riwayat_terakhir=riwayat_terakhir,
        data_sent_tiap_bln_dari_cab_tertentu=data_sent_tiap_bln_dari_cab_tertentu,
        active_page="dashboard",
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn     = get_db()
        cursor   = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE username=%s", (username,))
        admin = cursor.fetchone()
        conn.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session["logged_in"]      = True
            session["admin_id"]       = admin["id"]
            session["admin_username"] = admin["username"]
            session["role"]           = admin["role"]
            return redirect(url_for("dashboard"))
        error = "Username atau password salah."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════════════════════
# KELOLA_ADMIN.HTML — lihat, tambah, hapus admin
# ════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
def kelola_admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username FROM admins ORDER BY id")
    admin_list = cursor.fetchall()
    conn.close()
    return render_template(
        "kelola_user.html",
        admin_list=admin_list,
        current_admin_id=session.get("admin_id"),
        active_page="kelola_admin",
    )


@app.route("/admin/tambah", methods=["POST"])
def tambah_admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Username dan password wajib diisi.", "danger")
        return redirect(url_for("kelola_admin"))
    if len(password) < 6:
        flash("Password minimal 6 karakter.", "danger")
        return redirect(url_for("kelola_admin"))
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admins (username, password_hash) VALUES (%s, %s)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
        conn.close()
        flash(f"Admin '{username}' berhasil ditambahkan.", "success")
    except mysql.connector.IntegrityError:
        flash(f"Username '{username}' sudah digunakan.", "danger")
    return redirect(url_for("kelola_admin"))


@app.route("/admin/hapus/<int:admin_id>", methods=["POST"])
def hapus_admin(admin_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    if admin_id == session.get("admin_id"):
        flash("Tidak dapat menghapus akun sendiri.", "danger")
        return redirect(url_for("kelola_admin"))
    conn   = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS total FROM admins")
    if cursor.fetchone()["total"] <= 1:
        flash("Tidak dapat menghapus satu-satunya admin.", "danger")
        conn.close()
        return redirect(url_for("kelola_admin"))
    cursor.execute("SELECT username FROM admins WHERE id=%s", (admin_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM admins WHERE id=%s", (admin_id,))
        conn.commit()
        flash(f"Admin '{row['username']}' berhasil dihapus.", "success")
    conn.close()
    return redirect(url_for("kelola_admin"))


# ════════════════════════════════════════════════════════════════════════════
# SCRAPING — Routes scraping per cabang untuk prediksi
# ════════════════════════════════════════════════════════════════════════════

@app.route("/riwayat")
@login_required
def riwayat_scraping():
    now = datetime.now()
    bulan_ini = now.month
    tahun_ini = now.year

    from config.branches import BRANCHES

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM scraping_sessions WHERE bulan != 0 ORDER BY dibuat_pada DESC"
    )
    sesi_list = cursor.fetchall()

    for s in sesi_list:
        s["nama_bulan"] = NAMA_BULAN[s["bulan"]]

    ada_running = any(
        scraping_jobs.get(s["id"], {}).get("status") == "berjalan"
        or s["status"] == "berjalan"
        for s in sesi_list
    )

    conn.close()

    return render_template(
        "riwayat.html",
        sesi_list=sesi_list,
        ada_running=ada_running,
        bulan_sekarang=bulan_ini,
        tahun_sekarang=tahun_ini,
        nama_bulan=NAMA_BULAN,
        branches=BRANCHES,
        active_page="riwayat",
    )


@app.route("/scraping")
@login_required
def scraping_page():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id FROM scraping_sessions WHERE status='berjalan' ORDER BY id DESC LIMIT 1"
    )
    sesi_aktif = cursor.fetchone()
    conn.close()
    if sesi_aktif:
        return redirect(url_for("monitoring", id_sesi_scraping=sesi_aktif["id"]))
    return render_template("scraping_cabang.html", active_page="scraping")


@app.route("/scraping/mulai", methods=["POST"])
@login_required
def mulai_scraping():
    from config.branches import BRANCHES
    now = datetime.now()
    bulan = now.month
    tahun = now.year

    inputan_cabang = request.form.get("cabang", "").strip()
    nama_cabang = BRANCHES[inputan_cabang]["nama"]

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, status FROM scraping_sessions WHERE bulan=%s AND tahun=%s AND cabang=%s ORDER BY id DESC LIMIT 1",
        (bulan, tahun, nama_cabang),
    )
    existing = cursor.fetchone()

    if existing:
        id_sesi_scraping = existing["id"]
        cursor.execute(
            "UPDATE scraping_sessions SET status='berjalan', dibuat_pada=NOW() WHERE id=%s",
            (id_sesi_scraping,)
        )
        conn.commit()
        conn.close()
        scraping_jobs[id_sesi_scraping] = {"status": "berjalan", "pesan": "Memulai update...", "progress": 0}
    else:
        cursor.execute(
            "INSERT INTO scraping_sessions (bulan, tahun, cabang, status, dibuat_pada) VALUES (%s, %s, %s, 'berjalan', NOW())",
            (bulan, tahun, nama_cabang),
        )
        conn.commit()
        id_sesi_scraping = cursor.lastrowid
        conn.close()
        scraping_jobs[id_sesi_scraping] = {"status": "berjalan", "pesan": "Memulai...", "progress": 0}

    t = threading.Thread(
        target=_background_worker,
        args=(id_sesi_scraping, bulan, tahun),
        kwargs={"cabang": nama_cabang},
        daemon=True,
    )
    t.start()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "id_sesi_scraping": id_sesi_scraping, "nama_cabang": nama_cabang})
    return redirect(url_for("monitoring", id_sesi_scraping=id_sesi_scraping))


@app.route("/scraping/hentikan/<int:id_sesi_scraping>", methods=["POST"])
@login_required
def hentikan_scraping(id_sesi_scraping):
    if id_sesi_scraping in scraping_jobs:
        scraping_jobs[id_sesi_scraping]["stop_requested"] = True
    return jsonify({"ok": True})


@app.route("/scraping/status/<int:id_sesi_scraping>")
@login_required
def status_scraping(id_sesi_scraping):
    job = scraping_jobs.get(id_sesi_scraping, {})

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT status, jumlah_data FROM scraping_sessions WHERE id=%s",
        (id_sesi_scraping,),
    )
    row = cursor.fetchone()
    conn.close()

    return jsonify({
        "status":      job.get("status", row["status"] if row else "unknown"),
        "progress":    job.get("progress", 0),
        "pesan":       job.get("pesan", ""),
        "db_status":   row["status"] if row else "unknown",
        "jumlah_data": row["jumlah_data"] if row else 0,
    })


@app.route("/monitoring/<int:id_sesi_scraping>")
@login_required
def monitoring(id_sesi_scraping):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM scraping_sessions WHERE id=%s", (id_sesi_scraping,))
    sesi = cursor.fetchone()
    conn.close()
    if sesi:
        sesi["nama_bulan"] = "Dataset Awal" if sesi["bulan"] == 0 else NAMA_BULAN[sesi["bulan"]]
    return render_template("scraping_cabang.html", sesi=sesi, id_sesi_scraping=id_sesi_scraping,
                           active_page="scraping")



@app.route("/sesi/<int:id_sesi_scraping>/analisis", methods=["POST"])
@login_required
def mulai_analisis_sesi(id_sesi_scraping):
    if analisis_job.get("status") == "berjalan":
        return jsonify({"ok": False, "pesan": "Analisis sedang berjalan."})

    analisis_job.clear()
    analisis_job.update({"status": "berjalan", "pesan": "Memulai...", "progress": 0})

    def update_status(status, pesan, progress=None):
        analisis_job.update({
            "status": status,
            "pesan": pesan,
            "progress": progress if progress is not None else analisis_job.get("progress", 0),
        })

    def worker():
        try:
            from analisis.analisis import analisis_sesi
            analisis_sesi(id_sesi_scraping, update_status)
        except Exception as exc:
            update_status("gagal", str(exc), 0)
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE scraping_sessions SET status='terkumpul' WHERE id=%s AND status='sedang_analisis'",
                    (id_sesi_scraping,)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True})




@app.route("/analisis/monitoring")
@login_required
def monitoring_analisis():
    id_sesi_scraping = request.args.get("session_id", type=int)
    cabang           = request.args.get("cabang", "")
    periode          = request.args.get("periode", "")
    return render_template("monitoring_analisis.html", id_sesi_scraping=id_sesi_scraping,
                           cabang=cabang, periode=periode,
                           active_page="riwayat")


@app.route("/analisis/status")
@login_required
def status_analisis():
    return jsonify({
        "status":   analisis_job.get("status", "idle"),
        "pesan":    analisis_job.get("pesan", ""),
        "progress": analisis_job.get("progress", 0),
    })


@app.route("/sesi/<int:session_id>")
@login_required
def detail_sesi(session_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Ambil data sesi berdasarkan ID yang dikirim dari URL.
    cursor.execute("SELECT * FROM scraping_sessions WHERE id=%s", (session_id,))
    sesi = cursor.fetchone()

    if not sesi:
        conn.close()
        flash("Sesi tidak ditemukan.", "danger")
        return redirect(url_for("dashboard"))

    sesi["nama_bulan"] = "Dataset Awal" if sesi["bulan"] == 0 else NAMA_BULAN[sesi["bulan"]]

    # Ambil semua komentar milik sesi ini.
    cursor.execute(
        "SELECT cabang, rating, komentar, teks_bersih, sentimen, confidence "
        "FROM komentar WHERE id_sesi_scraping=%s ORDER BY cabang",
        (session_id,)
    )
    komentar_list = cursor.fetchall()
    conn.close()

    # Deteksi aspek (Makanan/Layanan/Suasana) pada setiap komentar.
    if sesi["status"] == "selesai":
        for k in komentar_list:
            k["aspek_list"] = _deteksi_aspek(k["teks_bersih"])

    return render_template(
        "detail.html",
        sesi=sesi,
        komentar_list=komentar_list,
        aspek_sentimen=_aspek_sentimen(komentar_list) if sesi["status"] == "selesai" else {},
        active_page="riwayat",
    )


@app.route("/sesi/<int:session_id>/download")
@login_required
def download_excel(session_id):
    import io
    import pandas as pd
    from flask import send_file

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM scraping_sessions WHERE id=%s", (session_id,))
    sesi = cursor.fetchone()
    if not sesi:
        conn.close()
        flash("Sesi tidak ditemukan.", "danger")
        return redirect(url_for("dashboard"))

    cursor.execute(
        "SELECT cabang, rating, komentar, teks_bersih, sentimen, confidence "
        "FROM komentar WHERE id_sesi_scraping=%s ORDER BY cabang",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        r["aspek"] = ", ".join(_deteksi_aspek(r)) or "—"

    df = pd.DataFrame(rows)
    if not df.empty:
        df.drop(columns=["teks_bersih"], inplace=True, errors="ignore")
        df.rename(columns={
            "cabang":     "Cabang",
            "rating":     "Rating",
            "komentar":   "Komentar",
            "aspek":      "Aspek",
            "sentimen":   "Sentimen",
            "confidence": "Confidence",
        }, inplace=True)
        cols = [c for c in ["Cabang","Rating","Komentar","Aspek","Sentimen","Confidence"] if c in df.columns]
        df = df[cols]
        if "Confidence" in df.columns:
            df["Confidence"] = df["Confidence"].apply(
                lambda x: f"{x*100:.1f}%" if x is not None else ""
            )

    bulan_nama  = NAMA_BULAN[sesi["bulan"]]
    cabang_slug = (sesi.get("cabang") or "semua").replace("Saoenk Cobek ", "").replace(" ", "_").lower()
    nama_file   = f"sentimen_{cabang_slug}_{bulan_nama}_{sesi['tahun']}.xlsx"

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Ulasan")
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nama_file,
    )


@app.route("/sesi/<int:id_sesi_scraping>/hapus", methods=["POST"])
@login_required
def hapus_sesi(id_sesi_scraping):
    if id_sesi_scraping in scraping_jobs:
        scraping_jobs[id_sesi_scraping]["stop_requested"] = True

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM komentar WHERE id_sesi_scraping=%s", (id_sesi_scraping,))
        cursor.execute("DELETE FROM scraping_sessions WHERE id=%s", (id_sesi_scraping,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    scraping_jobs[id_sesi_scraping] = {"stop_requested": True, "deleted": True}

    flash("Sesi berhasil dihapus.", "success")
    return redirect(url_for("dashboard"))


# ════════════════════════════════════════════════════════════════════════════
# Background worker scraping
# ════════════════════════════════════════════════════════════════════════════

def _background_worker(id_sesi_scraping: int, bulan: int, tahun: int, cabang: str = None):
    def update_status(status, pesan, progress=None):
        current = scraping_jobs.get(id_sesi_scraping, {})
        scraping_jobs[id_sesi_scraping] = {
            **current,
            "status": status,
            "pesan": pesan,
            "progress": progress if progress is not None else current.get("progress", 0),
        }

    def harus_berhenti():
        job = scraping_jobs.get(id_sesi_scraping, {})
        return job.get("stop_requested", False) or job.get("deleted", False)

    try:
        from scraper.google_maps_scraper_simple import hanya_scraping
        hanya_scraping(id_sesi_scraping, update_status, bulan=bulan, tahun=tahun,
                       harus_berhenti=harus_berhenti, cabang=cabang)

    except Exception as exc:
        update_status("gagal", str(exc), 0)
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scraping_sessions SET status='gagal', selesai_pada=NOW() WHERE id=%s",
                (id_sesi_scraping,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# HAL LAIN — jalankan aplikasi
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True)
