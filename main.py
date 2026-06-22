from flask import Flask, render_template, request, redirect, \
    url_for, flash, session, send_file, abort, jsonify, Response
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client
import fitz
import os
import qrcode
import threading
import time
from io import BytesIO, StringIO
import csv
import re
import logging
import sys

from werkzeug.middleware.proxy_fix import ProxyFix

# ===================== LOGGING =====================
sys.dont_write_bytecode = True
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ===================== ZONA HORARIA =====================
TZ_CDMX = ZoneInfo("America/Mexico_City")

def now_cdmx() -> datetime:
    return datetime.now(TZ_CDMX)

def today_cdmx() -> date:
    return now_cdmx().date()

def parse_date_any(value) -> date:
    if not value:
        raise ValueError("Fecha vacía")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ_CDMX)
        else:
            value = value.astimezone(TZ_CDMX)
        return value.date()
    s = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_CDMX)
    else:
        dt = dt.astimezone(TZ_CDMX)
    return dt.date()

# ===================== FLASK CONFIG =====================
app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=2, x_host=2, x_prefix=1)
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    SEND_FILE_MAX_AGE_DEFAULT=0,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24)
)

# ===================== SUPABASE =====================
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== CONFIG GENERAL =====================
OUTPUT_DIR           = "documentos"
PLANTILLA_PRINCIPAL  = "cdmxdigital2025ppp.pdf"
PLANTILLA_SECUNDARIA = "elbueno.pdf"
URL_CONSULTA_BASE    = "https://semovidigitalgob.onrender.com"
ENTIDAD              = "cdmx"
PRECIO_PERMISO       = 374
DIAS_PERMISO         = 30
HORAS_LIMITE_PAGO    = 48
PAGE_SIZE            = 100
BUCKET_NAME          = "permisos-cdmx"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── LOCK GLOBAL PDF ───────────────────────────────────────────────────────────
# PyMuPDF (fitz) NO es thread-safe. Con gunicorn multi-worker/thread, dos
# generaciones simultáneas sin este Lock corrompen los PDFs entre sí.
_pdf_generation_lock = threading.Lock()

# ===================== TABLAS DISPONIBLES =====================
TABLAS_DISPONIBLES = {
    'folios_registrados': {
        'nombre':      'Folios Registrados',
        'pk_col':      'folio',
        'search_cols': ['folio', 'marca', 'linea', 'numero_serie',
                        'numero_motor', 'nombre', 'estado', 'entidad', 'creado_por'],
        'columnas':    ['folio', 'marca', 'linea', 'anio', 'numero_serie',
                        'numero_motor', 'nombre', 'fecha_expedicion',
                        'fecha_vencimiento', 'entidad', 'estado', 'creado_por'],
    },
    'verificaciondigitalcdmx': {
        'nombre':      'Usuarios del Sistema',
        'pk_col':      'id',
        'search_cols': ['username', 'password'],
        'columnas':    ['id', 'username', 'password', 'folios_asignac', 'folios_usados'],
    },
}

# ===================== FOLIOS CDMX =====================
PREFIJO_CDMX = "412"

def generar_folio_automatico_cdmx() -> str:
    """
    FIX: antes descargaba TODOS los folios y luego checaba uno por uno con
    una consulta individual por candidato — extremadamente lento y bloqueante.
    Ahora usa bloques de 500 con UNA sola consulta .in_() y resuelve el
    primer hueco libre en memoria con Python puro.
    """
    # Leer watermark para arrancar desde donde quedamos
    try:
        wm = supabase.table("folio_watermark") \
            .select("ultimo_asignado").eq("prefijo", PREFIJO_CDMX).execute()
        inicio = (wm.data[0]["ultimo_asignado"] + 1) if wm.data else 1
    except Exception:
        inicio = 1

    BLOQUE = 500
    for _ in range(0, 10_000_000, BLOQUE):
        candidatos = [f"{PREFIJO_CDMX}{inicio + i}" for i in range(BLOQUE)]

        try:
            resp = supabase.table("folios_registrados") \
                .select("folio").in_("folio", candidatos).execute()
            ocupados = {r["folio"] for r in (resp.data or [])}
        except Exception as e:
            logger.error(f"[FOLIO] Error bloque: {e}")
            ocupados = set()

        logger.info(f"[FOLIO] bloque {inicio}–{inicio+BLOQUE-1}, ocupados={len(ocupados)}")

        for i, folio in enumerate(candidatos):
            if folio not in ocupados:
                numero_final = inicio + i
                # Guardar watermark
                try:
                    supabase.table("folio_watermark").upsert({
                        "prefijo": PREFIJO_CDMX,
                        "ultimo_asignado": numero_final
                    }).execute()
                except Exception as e:
                    logger.error(f"[WATERMARK] {e}")
                logger.info(f"[FOLIO] ✅ Asignado: {folio}")
                return folio

        inicio += BLOQUE

    raise Exception("Sin folio disponible tras 10,000,000 intentos")


def guardar_folio_con_reintento(datos, username):
    fexp_date = parse_date_any(datos["fecha_exp"])
    fven_date = parse_date_any(datos["fecha_ven"])

    def _row(folio):
        return {
            "folio":             folio,
            "marca":             str(datos["marca"]),
            "linea":             str(datos["linea"]),
            "anio":              str(datos["anio"]),
            "numero_serie":      str(datos["numero_serie"]),
            "numero_motor":      str(datos["numero_motor"]),
            "nombre":            str(datos.get("nombre", "SIN NOMBRE")),
            "fecha_expedicion":  fexp_date.isoformat(),
            "fecha_vencimiento": fven_date.isoformat(),
            "entidad":           ENTIDAD,
            "estado":            "ACTIVO",
            "creado_por":        username,
            "estado_pago":       datos.get("estado_pago", "VALIDADO"),
            "folio_origen":      datos.get("folio_origen", None),
            "user_id":           datos.get("user_id", None),
        }

    # MANUAL
    if datos.get("folio") and str(datos["folio"]).strip():
        fm = str(datos["folio"]).strip()
        try:
            supabase.table("folios_registrados").insert(_row(fm)).execute()
            datos["folio"] = fm
            logger.info(f"[DB] ✅ Folio MANUAL {fm}")
            return True
        except Exception as e:
            em = str(e).lower()
            if any(k in em for k in ("duplicate", "unique", "23505")):
                logger.error(f"[ERROR] Folio {fm} YA EXISTE")
            else:
                logger.error(f"[ERROR BD] {e}")
            return False

    # AUTO con bloque
    for intento in range(10_000_000):
        try:
            c = generar_folio_automatico_cdmx()
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            return False
        try:
            supabase.table("folios_registrados").insert(_row(c)).execute()
            datos["folio"] = c
            logger.info(f"[DB] ✅ Folio AUTO {c} (intento {intento+1})")
            return True
        except Exception as e:
            em = str(e).lower()
            if any(k in em for k in ("duplicate", "unique", "23505")):
                continue
            logger.error(f"[ERROR BD] {e}")
            return False

    logger.error("[ERROR] Sin folio tras 10,000,000 intentos")
    return False

# ===================== SUPABASE STORAGE =====================

def subir_pdf_a_storage(ruta_local: str, folio: str) -> str:
    """
    Sube el PDF al bucket de Supabase Storage.
    Devuelve URL pública o "" si falla.
    """
    try:
        with open(ruta_local, "rb") as f:
            contenido = f.read()

        nombre_archivo = f"{folio}.pdf"
        supabase.storage.from_(BUCKET_NAME).upload(
            path=nombre_archivo,
            file=contenido,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(nombre_archivo)
        logger.info(f"[STORAGE] Subido: {url}")
        return url
    except Exception as e:
        logger.error(f"[STORAGE] Error {folio}: {e}")
        return ""

# ===================== QR / PDF =====================
def generar_qr_dinamico_cdmx(folio):
    try:
        url = f"{URL_CONSULTA_BASE}/consulta/{folio}"
        qr  = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_M,
                             box_size=4, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img, url
    except Exception as e:
        logger.error(f"[QR] {e}")
        return None, None


def generar_pdf_unificado_cdmx(datos: dict) -> str:
    """
    FIX 1: Todo el cuerpo va dentro de _pdf_generation_lock — PyMuPDF no es
    thread-safe, dos generaciones simultáneas sin este Lock corrompen el PDF.

    FIX 2: str() forzado en TODOS los insert_text — blinda contra cualquier
    valor no-string (int, None, etc.) que truene con
    "'int' object has no attribute 'splitlines'".
    """
    with _pdf_generation_lock:
        fol          = datos["folio"]
        fecha_exp_dt = datos["fecha_exp"]
        fecha_ven_dt = datos["fecha_ven"]

        if isinstance(fecha_exp_dt, str):
            fecha_exp_dt = datetime.fromisoformat(fecha_exp_dt.replace("Z", "+00:00"))
        if fecha_exp_dt.tzinfo is None:
            fecha_exp_dt = fecha_exp_dt.replace(tzinfo=TZ_CDMX)
        else:
            fecha_exp_dt = fecha_exp_dt.astimezone(TZ_CDMX)

        if isinstance(fecha_ven_dt, str):
            fecha_ven_str = fecha_ven_dt
        else:
            if fecha_ven_dt.tzinfo is None:
                fecha_ven_dt = fecha_ven_dt.replace(tzinfo=TZ_CDMX)
            else:
                fecha_ven_dt = fecha_ven_dt.astimezone(TZ_CDMX)
            fecha_ven_str = fecha_ven_dt.strftime("%d/%m/%Y")

        out = os.path.join(OUTPUT_DIR, f"{fol}.pdf")

        try:
            # ── PÁGINA 1 ──────────────────────────────────────────────────────
            doc1 = fitz.open(PLANTILLA_PRINCIPAL)
            pg1  = doc1[0]

            meses = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                     7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
            fecha_texto = f"{fecha_exp_dt.day} de {meses[fecha_exp_dt.month]} del {fecha_exp_dt.year}"

            pg1.insert_text((50,  130), "FOLIO: ",                        fontsize=12, fontname="helv", color=(0,0,0))
            pg1.insert_text((100, 130), str(fol),                         fontsize=12, fontname="helv", color=(1,0,0))
            pg1.insert_text((130, 145), str(fecha_texto),                 fontsize=12, fontname="helv", color=(0,0,0))
            pg1.insert_text((87,  290), str(datos["marca"]),              fontsize=11, fontname="helv", color=(0,0,0))
            pg1.insert_text((375, 290), str(datos["numero_serie"]),       fontsize=11, fontname="helv", color=(0,0,0))
            pg1.insert_text((87,  307), str(datos["linea"]),              fontsize=11, fontname="helv", color=(0,0,0))
            pg1.insert_text((375, 307), str(datos["numero_motor"]),       fontsize=11, fontname="helv", color=(0,0,0))
            pg1.insert_text((87,  323), str(datos["anio"]),               fontsize=11, fontname="helv", color=(0,0,0))
            pg1.insert_text((375, 323), str(fecha_ven_str),               fontsize=11, fontname="helv", color=(0,0,0))
            if datos.get("nombre"):
                pg1.insert_text((375, 340), str(datos["nombre"]),         fontsize=11, fontname="helv", color=(0,0,0))

            img_qr, _ = generar_qr_dinamico_cdmx(fol)
            if img_qr:
                buf = BytesIO()
                img_qr.save(buf, format="PNG")
                buf.seek(0)
                pg1.insert_image(fitz.Rect(49, 653, 145, 749),
                                 pixmap=fitz.Pixmap(buf.read()), overlay=True)

            # ── PÁGINA 2 ──────────────────────────────────────────────────────
            if os.path.exists(PLANTILLA_SECUNDARIA):
                doc2 = fitz.open(PLANTILLA_SECUNDARIA)
                pg2  = doc2[0]

                titulo_p2 = (f"IMPUESTO POR DERECHO DE AUTOMOVIL Y MOTOCICLETAS "
                             f"(PERMISO PARA CIRCULAR {DIAS_PERMISO} DIAS)")
                anio_str = str(fecha_exp_dt.year)

                pg2.insert_text((135, 170), str(titulo_p2),                        fontsize=6,  fontname="hebo", color=(0,0,0))
                pg2.insert_text((135, 194), str(datos["numero_serie"]),             fontsize=6,  fontname="hebo", color=(0,0,0))
                pg2.insert_text((135, 202), anio_str,                               fontsize=6,  fontname="hebo", color=(0,0,0))
                pg2.insert_text((385, 430), f"${PRECIO_PERMISO}",                  fontsize=16, fontname="hebo", color=(0,0,0))
                pg2.insert_text((190, 324), fecha_exp_dt.strftime('%d/%m/%Y'),      fontsize=6,  fontname="hebo", color=(0,0,0))

                doc1.insert_pdf(doc2)
                doc2.close()

            doc1.save(out)
            doc1.close()
            logger.info(f"[PDF] ✅ {out}")

            # Sube a Storage y guarda pdf_url
            url = subir_pdf_a_storage(out, fol)
            if url:
                try:
                    supabase.table("folios_registrados") \
                        .update({"pdf_url": url}).eq("folio", fol).execute()
                except Exception as e:
                    logger.error(f"[WARN] No se pudo guardar pdf_url: {e}")

        except Exception as e:
            logger.error(f"[PDF ERROR] {e}")
            fb = fitz.open()
            fb.new_page().insert_text((50, 50), f"ERROR - {fol}", fontsize=12)
            fb.save(out)
            fb.close()

        return out


def generar_pdf_en_background(datos: dict):
    """Para llamar en threading.Thread — no bloquea el request HTTP."""
    generar_pdf_unificado_cdmx(datos)

# ===================== ARMAR RESULTADO =====================

def _armar_resultado_cdmx(r: dict, folio: str) -> dict:
    """
    Construye el dict de resultado para las páginas de consulta.
    puede_renovar = True solo si está VENCIDO y NO es folio de lote (user_id).
    """
    fe = parse_date_any(r.get('fecha_expedicion'))
    fv = parse_date_any(r.get('fecha_vencimiento'))
    hoy    = today_cdmx()
    estado = "VIGENTE" if hoy <= fv else "VENCIDO"

    es_de_lote    = r.get('user_id') is not None
    puede_renovar = (estado == "VENCIDO") and not es_de_lote

    return {
        "estado":            estado,
        "color":             "verde" if estado == "VIGENTE" else "cafe",
        "folio":             folio,
        "folio_actual":      folio,
        "fecha_expedicion":  fe.strftime('%d/%m/%Y'),
        "fecha_vencimiento": fv.strftime('%d/%m/%Y'),
        "marca":             r.get('marca', ''),
        "linea":             r.get('linea', ''),
        "año":               r.get('anio', ''),
        "numero_serie":      r.get('numero_serie', ''),
        "numero_motor":      r.get('numero_motor', ''),
        "entidad":           r.get('entidad', ENTIDAD),
        "puede_renovar":     puede_renovar,
    }

# ===================== RUTAS =====================
@app.route('/')
def inicio():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == 'Serg890105tm3' and password == 'Serg890105tm3':
            session['admin']    = True
            session['username'] = 'Serg890105tm3'
            return redirect(url_for('admin'))

        resp = supabase.table("verificaciondigitalcdmx")\
            .select("*").eq("username", username).eq("password", password).execute()
        if resp.data:
            session['user_id']  = resp.data[0].get('id')
            session['username'] = resp.data[0]['username']
            session['admin']    = False
            return redirect(url_for('registro_usuario'))

        flash('Usuario o contraseña incorrectos', 'error')
    return render_template('login.html')


@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('panel.html')


@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        folios   = int(request.form['folios'])
        existe   = supabase.table("verificaciondigitalcdmx")\
            .select("id").eq("username", username).limit(1).execute()
        if existe.data:
            flash('Error: el usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": username, "password": password,
                "folios_asignac": folios, "folios_usados": 0
            }).execute()
            flash('Usuario creado.', 'success')
    return render_template('crear_usuario.html')


@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if not session.get('username'):
        return redirect(url_for('login'))
    if session.get('admin'):
        return redirect(url_for('admin'))

    ud = supabase.table("verificaciondigitalcdmx")\
        .select("*").eq("username", session['username']).limit(1).execute()
    if not ud.data:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for('login'))

    usuario            = ud.data[0]
    folios_asignados   = int(usuario.get('folios_asignac', 0))
    folios_usados      = int(usuario.get('folios_usados', 0))
    folios_disponibles = folios_asignados - folios_usados
    porcentaje         = (folios_usados / folios_asignados * 100) if folios_asignados else 0
    ctx = dict(folios_asignados=folios_asignados, folios_usados=folios_usados,
               folios_disponibles=folios_disponibles, porcentaje=porcentaje)

    if request.method == 'POST':
        if folios_disponibles <= 0:
            flash("⚠️ Sin folios disponibles.", "error")
            return render_template('registro_usuario.html', **ctx)

        folio_manual = request.form.get('folio', '').strip()
        marca        = request.form.get('marca', '').strip().upper()
        linea        = request.form.get('linea', '').strip().upper()
        anio         = request.form.get('anio', '').strip()
        serie        = request.form.get('serie', '').strip().upper()
        motor        = request.form.get('motor', '').strip().upper()
        nombre       = request.form.get('nombre', '').strip().upper() or 'SIN NOMBRE'
        fecha_str    = request.form.get('fecha_inicio', '').strip()

        if not all([marca, linea, anio, serie, motor]):
            flash("❌ Faltan campos obligatorios.", "error")
            return render_template('registro_usuario.html', **ctx)

        fecha_inicio = now_cdmx() if not fecha_str else \
            datetime.strptime(fecha_str, '%Y-%m-%d').replace(tzinfo=TZ_CDMX)

        datos = {
            "folio": folio_manual or None, "marca": marca, "linea": linea,
            "anio": anio, "numero_serie": serie, "numero_motor": motor,
            "nombre": nombre,
            "fecha_exp": fecha_inicio,
            "fecha_ven": fecha_inicio + timedelta(days=DIAS_PERMISO),
            # CON user_id -> folio de lote, sin autoservicio de renovación
            "user_id": session.get('user_id'),
            "estado_pago": "VALIDADO",
        }

        if not guardar_folio_con_reintento(datos, session['username']):
            flash("❌ Error al registrar.", "error")
            return render_template('registro_usuario.html', **ctx)

        threading.Thread(
            target=generar_pdf_en_background,
            args=(dict(datos),),
            daemon=True
        ).start()

        supabase.table("verificaciondigitalcdmx")\
            .update({"folios_usados": folios_usados + 1})\
            .eq("username", session['username']).execute()

        flash(f'✅ Folio: {datos["folio"]}', 'success')
        return render_template('exitoso.html',
                               folio=datos["folio"], serie=serie,
                               fecha_generacion=fecha_inicio.strftime('%d/%m/%Y %H:%M'))

    return render_template('registro_usuario.html', **ctx)


@app.route('/mis_permisos')
def mis_permisos():
    if not session.get('username') or session.get('admin'):
        return redirect(url_for('login'))

    permisos = supabase.table("folios_registrados")\
        .select("*").eq("creado_por", session['username'])\
        .order("fecha_expedicion", desc=True).execute().data or []

    hoy = today_cdmx()
    for p in permisos:
        try:
            fv = parse_date_any(p.get('fecha_vencimiento'))
            fe = parse_date_any(p.get('fecha_expedicion'))
            p['fecha_formateada'] = fe.strftime('%d/%m/%Y')
            p['hora_formateada']  = "00:00:00"
            p['estado']           = "VIGENTE" if hoy <= fv else "VENCIDO"
        except Exception:
            p['fecha_formateada'] = p['hora_formateada'] = p['estado'] = 'ERROR'

    ur = supabase.table("verificaciondigitalcdmx")\
        .select("folios_asignac,folios_usados")\
        .eq("username", session['username']).limit(1).execute().data
    ur = ur[0] if ur else {"folios_asignac": 0, "folios_usados": 0}

    return render_template('mis_permisos.html',
                           permisos=permisos, total_generados=len(permisos),
                           folios_asignados=int(ur.get('folios_asignac', 0)),
                           folios_usados=int(ur.get('folios_usados', 0)))


@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio_manual = request.form.get('folio', '').strip()
        marca        = request.form.get('marca', '').strip().upper()
        linea        = request.form.get('linea', '').strip().upper()
        anio         = request.form.get('anio', '').strip()
        serie        = request.form.get('serie', '').strip().upper()
        motor        = request.form.get('motor', '').strip().upper()
        nombre       = request.form.get('nombre', '').strip().upper() or 'SIN NOMBRE'
        fecha_str    = request.form.get('fecha_inicio', '').strip()

        if not all([marca, linea, anio, serie, motor, fecha_str]):
            flash("❌ Faltan campos.", "error")
            return redirect(url_for('registro_admin'))

        try:
            fecha_inicio = datetime.strptime(fecha_str, '%Y-%m-%d').replace(tzinfo=TZ_CDMX)
        except Exception:
            flash("❌ Fecha inválida.", "error")
            return redirect(url_for('registro_admin'))

        datos = {
            "folio": folio_manual or None, "marca": marca, "linea": linea,
            "anio": anio, "numero_serie": serie, "numero_motor": motor,
            "nombre": nombre,
            "fecha_exp": fecha_inicio,
            "fecha_ven": fecha_inicio + timedelta(days=DIAS_PERMISO),
            # SIN user_id -> folio oficial, puede renovarse con autoservicio
            "estado_pago": "VALIDADO",
        }

        if not guardar_folio_con_reintento(datos, "ADMIN"):
            flash("❌ Error al registrar.", "error")
            return redirect(url_for('registro_admin'))

        threading.Thread(
            target=generar_pdf_en_background,
            args=(dict(datos),),
            daemon=True
        ).start()

        flash('✅ Permiso generado.', 'success')
        return render_template('exitoso.html',
                               folio=datos["folio"], serie=serie,
                               fecha_generacion=fecha_inicio.strftime('%d/%m/%Y %H:%M'))

    return render_template('registro_admin.html')


@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    if request.method == 'POST':
        folio = request.form['folio'].strip()
        rows  = supabase.table("folios_registrados")\
            .select("*").eq("folio", folio).limit(1).execute().data
        if not rows:
            resultado = {"estado": "NO REGISTRADO", "color": "rojo", "folio": folio,
                         "puede_renovar": False}
        else:
            resultado = _armar_resultado_cdmx(rows[0], folio)
        return render_template('resultado_consulta.html', resultado=resultado)
    return render_template('consulta_folio.html')


@app.route('/consulta/<folio>')
def consulta_folio_directo(folio):
    row = supabase.table("folios_registrados")\
        .select("*").eq("folio", folio).limit(1).execute().data
    if not row:
        return render_template("resultado_consulta.html",
                               resultado={"estado":"NO REGISTRADO","color":"rojo","folio":folio,
                                          "puede_renovar": False})
    resultado = _armar_resultado_cdmx(row[0], folio)
    return render_template("resultado_consulta.html", resultado=resultado)


# ═══════════════════════════════════════════════════════════════════════════
# RENOVACIÓN — solo folios OFICIALES (sin user_id). Nunca para lotes.
# IDEMPOTENCIA: si ya hay una renovación PENDIENTE_PAGO del mismo folio
# viejo, regresa esa en vez de crear otra.
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/renovar_folio/<folio_viejo>', methods=['POST'])
def renovar_folio(folio_viejo):
    t0 = time.time()
    folio_viejo = folio_viejo.strip().upper()
    logger.info(f"[RENOVAR] INICIO folio_viejo={folio_viejo}")

    resp = supabase.table("folios_registrados").select("*").eq("folio", folio_viejo).execute()
    if not resp.data:
        return jsonify({"ok": False, "error": "Folio original no encontrado"}), 404

    original = resp.data[0]

    if original.get("user_id"):
        return jsonify({
            "ok": False,
            "error": "Este folio fue emitido por un proveedor. Contacta a quien te lo entregó para renovarlo."
        }), 403

    # Idempotencia: si ya existe renovación pendiente para este folio_viejo
    ya_existente = supabase.table("folios_registrados") \
        .select("folio") \
        .eq("folio_origen", folio_viejo) \
        .eq("estado_pago", "PENDIENTE_PAGO") \
        .order("fecha_expedicion", desc=True) \
        .limit(1).execute()

    if ya_existente.data:
        folio_existente = ya_existente.data[0]["folio"]
        logger.info(f"[RENOVAR] Ya existía: {folio_existente}")
        return jsonify({
            "ok": True,
            "folio_nuevo": folio_existente,
            "horas_limite": HORAS_LIMITE_PAGO
        })

    fecha_exp = now_cdmx()
    fecha_ven = fecha_exp + timedelta(days=DIAS_PERMISO)

    datos = {
        "folio":         None,
        "marca":         original.get("marca", ""),
        "linea":         original.get("linea", ""),
        "anio":          original.get("anio", ""),
        "numero_serie":  original.get("numero_serie", ""),
        "numero_motor":  original.get("numero_motor", ""),
        "nombre":        original.get("nombre", "SIN NOMBRE"),
        "fecha_exp":     fecha_exp,
        "fecha_ven":     fecha_ven,
        "estado_pago":   "PENDIENTE_PAGO",
        "folio_origen":  folio_viejo,
        # SIN user_id -> sigue siendo oficial, puede volver a renovarse
    }

    if not guardar_folio_con_reintento(datos, "RENOVACION"):
        return jsonify({"ok": False, "error": "No se pudo registrar la renovación"}), 500

    folio_nuevo = datos["folio"]

    threading.Thread(
        target=generar_pdf_en_background,
        args=(dict(datos),),
        daemon=True
    ).start()

    logger.info(f"[RENOVAR] FIN {time.time()-t0:.2f}s folio_nuevo={folio_nuevo}")
    return jsonify({
        "ok": True,
        "folio_nuevo": folio_nuevo,
        "horas_limite": HORAS_LIMITE_PAGO
    })


@app.route('/estado_pdf/<folio>')
def estado_pdf(folio):
    """Polling desde el frontend — regresa pdf_url cuando el thread lo sube."""
    resp = supabase.table("folios_registrados").select("pdf_url").eq("folio", folio).execute()
    pdf_url = resp.data[0].get("pdf_url", "") if resp.data else ""
    return jsonify({"pdf_url": pdf_url})


@app.route('/admin/validar_pago/<folio>', methods=['POST'])
def validar_pago(folio):
    if not session.get('admin'):
        return jsonify({"ok": False, "error": "no autorizado"}), 403
    folio = folio.strip().upper()
    try:
        supabase.table("folios_registrados") \
            .update({"estado_pago": "VALIDADO"}).eq("folio", folio).execute()
        # Si viene de un form normal (admin_folios), redirige
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' \
                or request.accept_mimetypes.best == 'application/json':
            return jsonify({"ok": True})
        flash(f"Folio {folio} validado.", "success")
        return redirect(request.referrer or url_for('admin_folios'))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False, "error": str(e)}), 500
        flash(f"Error: {e}", "error")
        return redirect(url_for('admin_folios'))


# ===================== LIMPIEZA 48H =====================

def limpiar_folios_no_pagados_cdmx():
    """Corre en APScheduler cada 15 min. Borra renovaciones PENDIENTE_PAGO > 48h."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    try:
        limite = (now_cdmx() - timedelta(hours=HORAS_LIMITE_PAGO)).isoformat()
        vencidos = supabase.table("folios_registrados") \
            .select("folio") \
            .eq("estado_pago", "PENDIENTE_PAGO") \
            .eq("entidad", ENTIDAD) \
            .lt("fecha_expedicion", limite) \
            .execute()

        for row in (vencidos.data or []):
            folio = row["folio"]
            supabase.table("folios_registrados").delete().eq("folio", folio).execute()
            ruta = os.path.join(OUTPUT_DIR, f"{folio}.pdf")
            if os.path.exists(ruta):
                os.remove(ruta)
            try:
                supabase.storage.from_(BUCKET_NAME).remove([f"{folio}.pdf"])
            except Exception:
                pass
            logger.info(f"[LIMPIEZA 48H] {folio} eliminado")
    except Exception as e:
        logger.error(f"[LIMPIEZA 48H] {e}")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone="America/Mexico_City")
    scheduler.add_job(limpiar_folios_no_pagados_cdmx, 'interval', minutes=15)
    scheduler.start()
    logger.info("[SCHEDULER] Limpieza 48h activa")
except ImportError:
    logger.warning("[SCHEDULER] APScheduler no instalado, limpieza 48h desactivada")

# ===================== ADMIN TEST FECHAS =====================

@app.route('/admin/test_fechas', methods=['GET', 'POST'])
def admin_test_fechas():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        accion = request.form.get('accion')
        folio  = request.form.get('folio', '').strip().upper()

        if not folio:
            flash("Escribe un folio.", "error")
            return redirect(url_for('admin_test_fechas'))

        resp = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
        if not resp.data:
            flash(f"Folio {folio} no encontrado.", "error")
            return redirect(url_for('admin_test_fechas'))

        if accion == 'vencer_permiso':
            nueva_ven = now_cdmx() - timedelta(days=1)
            supabase.table("folios_registrados") \
                .update({"fecha_vencimiento": nueva_ven.date().isoformat()}) \
                .eq("folio", folio).execute()
            flash(f"Folio {folio} marcado VENCIDO. Pruébalo en /consulta/{folio}", "success")

        elif accion == 'vencer_pago_48h':
            nueva_exp = now_cdmx() - timedelta(hours=49)
            supabase.table("folios_registrados") \
                .update({"fecha_expedicion": nueva_exp.isoformat()}) \
                .eq("folio", folio).execute()
            flash(f"Folio {folio}: expedición movida 49h atrás. "
                  f"Si sigue PENDIENTE_PAGO, el scheduler lo borra en máx 15 min.", "success")

        elif accion == 'restaurar':
            hoy = now_cdmx()
            ven = hoy + timedelta(days=DIAS_PERMISO)
            supabase.table("folios_registrados") \
                .update({
                    "fecha_expedicion": hoy.date().isoformat(),
                    "fecha_vencimiento": ven.date().isoformat()
                }) \
                .eq("folio", folio).execute()
            flash(f"Folio {folio} restaurado a vigencia normal ({DIAS_PERMISO} días).", "success")

        return redirect(url_for('admin_test_fechas') + f"?folio={folio}")

    folio_buscar = request.args.get('folio', '').strip().upper()
    resultado = None
    if folio_buscar:
        resp = supabase.table("folios_registrados").select("*").eq("folio", folio_buscar).execute()
        if resp.data:
            resultado = resp.data[0]
        else:
            flash(f"Folio {folio_buscar} no encontrado.", "error")

    return render_template('admin_test_fechas.html', resultado=resultado, folio_buscar=folio_buscar)


# ===================== DESCARGAS =====================
@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    # Prioridad: Storage > disco local
    resp = supabase.table("folios_registrados").select("pdf_url").eq("folio", folio).execute()
    if resp.data and resp.data[0].get("pdf_url"):
        return redirect(resp.data[0]["pdf_url"])

    ruta = os.path.join(OUTPUT_DIR, f"{folio}.pdf")
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, as_attachment=True,
                     download_name=f"{folio}_cdmx.pdf",
                     mimetype='application/pdf')


# ===================== ADMIN FOLIOS =====================
@app.route('/admin_folios')
def admin_folios():
    if not session.get('admin'):
        return redirect(url_for('login'))

    filtro        = request.args.get('filtro', '').strip()
    criterio      = request.args.get('criterio', 'folio')
    estado_filtro = request.args.get('estado', 'todos')
    fecha_inicio  = request.args.get('fecha_inicio', '')
    fecha_fin     = request.args.get('fecha_fin', '')
    ordenar       = request.args.get('ordenar', 'desc')

    q = supabase.table("folios_registrados").select("*").eq("entidad", ENTIDAD)
    if filtro:
        if criterio == 'folio':
            q = q.ilike('folio', f'%{filtro}%')
        elif criterio == 'numero_serie':
            q = q.ilike('numero_serie', f'%{filtro}%')
    if fecha_inicio:
        q = q.gte('fecha_expedicion', fecha_inicio)
    if fecha_fin:
        q = q.lte('fecha_expedicion', fecha_fin)
    q      = q.order('fecha_expedicion', desc=(ordenar=='desc'))
    folios = q.execute().data or []

    hoy, out = today_cdmx(), []
    for f in folios:
        try:
            fv = parse_date_any(f.get('fecha_vencimiento'))
            f['estado'] = "VIGENTE" if hoy <= fv else "VENCIDO"
        except Exception:
            f['estado'] = 'ERROR'
        if estado_filtro == 'todos' or estado_filtro == f['estado'].lower():
            out.append(f)

    return render_template('admin_folios.html',
                           folios=out, filtro=filtro, criterio=criterio,
                           estado=estado_filtro, fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin, ordenar=ordenar)


@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        supabase.table("folios_registrados").update({
            "marca":             request.form['marca'],
            "linea":             request.form['linea'],
            "anio":              request.form['anio'],
            "numero_serie":      request.form['serie'],
            "numero_motor":      request.form['motor'],
            "fecha_expedicion":  request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento'],
        }).eq("folio", folio).execute()
        flash("Folio actualizado.", "success")
        return redirect(url_for('admin_folios'))
    resp = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
    if not resp.data:
        flash("Folio no encontrado.", "error")
        return redirect(url_for('admin_folios'))
    return render_template("editar_folio.html", folio=resp.data[0])


@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if not session.get('admin'):
        return redirect(url_for('login'))
    supabase.table("folios_registrados").delete().eq("folio", request.form['folio']).execute()
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ===================== ADMIN TABLAS =====================
@app.route('/admin_tablas')
def admin_tablas():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('admin_tablas.html', tablas=TABLAS_DISPONIBLES)


@app.route('/admin_tabla/<nombre_tabla>')
def admin_tabla(nombre_tabla):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        flash('Tabla no encontrada', 'error')
        return redirect(url_for('admin_tablas'))

    info_tabla = TABLAS_DISPONIBLES[nombre_tabla]
    pk_col     = info_tabla['pk_col']

    q    = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1) or 1))

    try:
        todos = supabase.table(nombre_tabla).select("*").limit(20000).execute().data or []

        if q:
            q_lower   = q.lower()
            filtrados = [
                r for r in todos
                if any(q_lower in str(v).lower() for v in r.values() if v is not None)
            ]
        else:
            filtrados = todos

        total  = len(filtrados)
        offset = (page - 1) * PAGE_SIZE
        registros = filtrados[offset: offset + PAGE_SIZE]

    except Exception as e:
        flash(f'Error al cargar datos: {e}', 'error')
        registros, total, offset, todos = [], 0, 0, []

    columnas    = list(registros[0].keys()) if registros \
                  else (list(todos[0].keys()) if todos else info_tabla.get('columnas', []))
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return render_template('admin_tabla_detalle.html',
                           nombre_tabla=nombre_tabla, info_tabla=info_tabla,
                           registros=registros, columnas=columnas, pk_col=pk_col,
                           q=q, page=page, offset=offset, total=total,
                           total_pages=total_pages)


@app.route('/api/update_cell', methods=['POST'])
def api_update_cell():
    if not session.get('admin'):
        return jsonify({"ok": False, "error": "no autorizado"}), 403
    d      = request.get_json(force=True)
    tabla  = d.get('tabla')
    pk_col = d.get('pk_col')
    pk_val = d.get('pk_val')
    col    = d.get('col')
    val    = d.get('val', '')
    if tabla not in TABLAS_DISPONIBLES or not col or not pk_val:
        return jsonify({"ok": False, "error": "datos inválidos"}), 400
    try:
        supabase.table(tabla).update({col: val or None}).eq(pk_col, pk_val).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/delete_row', methods=['POST'])
def api_delete_row():
    if not session.get('admin'):
        return jsonify({"ok": False, "error": "no autorizado"}), 403
    d      = request.get_json(force=True)
    tabla  = d.get('tabla')
    pk_col = d.get('pk_col')
    pk_val = d.get('pk_val')
    if tabla not in TABLAS_DISPONIBLES or not pk_val:
        return jsonify({"ok": False, "error": "datos inválidos"}), 400
    try:
        supabase.table(tabla).delete().eq(pk_col, pk_val).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/descargar_tabla/<nombre_tabla>')
def descargar_tabla(nombre_tabla):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        abort(404)
    try:
        registros = supabase.table(nombre_tabla).select("*").limit(200_000).execute().data or []
    except Exception as e:
        flash(f'Error al exportar: {e}', 'error')
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
    if not registros:
        flash("Sin registros para exportar.", "error")
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
    columnas = list(registros[0].keys())
    ahora    = now_cdmx().strftime('%Y-%m-%d %H:%M:%S')
    out = StringIO()
    out.write(f"TABLA: {nombre_tabla}\nEXPORTADO: {ahora}\nTOTAL: {len(registros)} registros\n")
    out.write("=" * 80 + "\n")
    out.write("|".join(str(c).upper() for c in columnas) + "\n")
    out.write("-" * 80 + "\n")
    for reg in registros:
        out.write("|".join(str(reg.get(c, '') or '') for c in columnas) + "\n")
    nombre_archivo = f"{nombre_tabla}_{now_cdmx().strftime('%Y%m%d_%H%M')}.txt"
    return Response(out.getvalue(), mimetype='text/plain; charset=utf-8',
                    headers={'Content-Disposition': f'attachment;filename={nombre_archivo}'})


@app.route('/admin_editar_registro/<nombre_tabla>/<registro_id>', methods=['GET', 'POST'])
def admin_editar_registro(nombre_tabla, registro_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        return redirect(url_for('admin_tablas'))
    info   = TABLAS_DISPONIBLES[nombre_tabla]
    pk_col = info['pk_col']
    if request.method == 'POST':
        datos = {c: request.form[c].strip() for c in info.get('columnas', [])
                 if c in request.form and request.form[c].strip()}
        try:
            supabase.table(nombre_tabla).update(datos).eq(pk_col, registro_id).execute()
            flash('Actualizado.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
    reg = supabase.table(nombre_tabla).select("*").eq(pk_col, registro_id).execute().data
    if not reg:
        flash('No encontrado.', 'error')
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
    return render_template('admin_editar_registro.html',
                           nombre_tabla=nombre_tabla, info_tabla=info,
                           registro=reg[0], registro_id=registro_id)


@app.route('/admin_eliminar_registro/<nombre_tabla>/<registro_id>', methods=['POST'])
def admin_eliminar_registro(nombre_tabla, registro_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        return redirect(url_for('admin_tablas'))
    pk_col = TABLAS_DISPONIBLES[nombre_tabla]['pk_col']
    try:
        supabase.table(nombre_tabla).delete().eq(pk_col, registro_id).execute()
        flash('Eliminado.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))


@app.route('/admin_agregar_registro/<nombre_tabla>', methods=['GET', 'POST'])
def admin_agregar_registro(nombre_tabla):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        return redirect(url_for('admin_tablas'))
    info = TABLAS_DISPONIBLES[nombre_tabla]
    if request.method == 'POST':
        datos = {c: request.form[c].strip() for c in info.get('columnas', [])
                 if c != 'id' and c in request.form and request.form[c].strip()}
        try:
            supabase.table(nombre_tabla).insert(datos).execute()
            flash('Agregado.', 'success')
            return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
        except Exception as e:
            flash(f'Error: {e}', 'error')
    return render_template('admin_agregar_registro.html',
                           nombre_tabla=nombre_tabla, info_tabla=info)


# ===================== MAIN =====================
if __name__ == '__main__':
    logger.info("🚀 SERVIDOR CDMX")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
