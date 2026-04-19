from flask import Flask, render_template, render_template_string, request, redirect, \
    url_for, flash, session, send_file, abort, jsonify, Response
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client
import fitz
import os
import qrcode
from PIL import Image
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

# ===================== SUPABASE CONFIG =====================
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

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===================== FOLIOS CDMX: 412 + CONSECUTIVO =====================
PREFIJO_CDMX = "412"

def generar_folio_automatico_cdmx():
    """
    Genera folio con prefijo 412 + consecutivo.
    Lee TODOS los folios existentes, toma el máximo y busca desde max+1
    en pasos de +1 hasta encontrar uno libre.
    """
    logger.info("[FOLIO] Iniciando generación automática CDMX")

    todos = supabase.table("folios_registrados")\
        .select("folio")\
        .like("folio", f"{PREFIJO_CDMX}%")\
        .execute().data or []

    consecutivos = []
    for f in todos:
        folio_str = str(f.get('folio', ''))
        if folio_str.startswith(PREFIJO_CDMX):
            sufijo = folio_str[len(PREFIJO_CDMX):]
            if sufijo.isdigit():
                consecutivos.append(int(sufijo))

    siguiente = (max(consecutivos) + 1) if consecutivos else 1
    logger.info(f"[FOLIO] Consecutivos válidos: {len(consecutivos)} — siguiente candidato: {PREFIJO_CDMX}{siguiente}")

    for intento in range(10_000_000):
        candidato = f"{PREFIJO_CDMX}{siguiente + intento}"
        existe = supabase.table("folios_registrados")\
            .select("folio").eq("folio", candidato).limit(1).execute().data
        if not existe:
            logger.info(f"[FOLIO] ✅ Encontrado: {candidato} (intento {intento + 1})")
            return candidato
        logger.info(f"[FOLIO] {candidato} ocupado → probando siguiente")
        if intento > 0 and intento % 10_000 == 0:
            logger.info(f"[FOLIO] Buscando... intento {intento}")

    raise Exception("No se encontró folio disponible después de 10,000,000 intentos")


def guardar_folio_con_reintento(datos, username):
    """
    Guarda folio en BD.
    - Folio MANUAL → usa ese exactamente.
    - Sin folio → genera automático +1 hasta encontrar libre.
    """
    fexp_date = parse_date_any(datos["fecha_exp"])
    fven_date = parse_date_any(datos["fecha_ven"])

    # ── MODO MANUAL ──────────────────────────────────────────────────────────
    if datos.get("folio") and datos["folio"].strip():
        folio_manual = datos["folio"].strip()
        logger.info(f"[FOLIO MANUAL] Intentando usar: {folio_manual}")
        try:
            supabase.table("folios_registrados").insert({
                "folio":             folio_manual,
                "marca":             datos["marca"],
                "linea":             datos["linea"],
                "anio":              datos["anio"],
                "numero_serie":      datos["numero_serie"],
                "numero_motor":      datos["numero_motor"],
                "nombre":            datos.get("nombre", "SIN NOMBRE"),
                "fecha_expedicion":  fexp_date.isoformat(),
                "fecha_vencimiento": fven_date.isoformat(),
                "entidad":           ENTIDAD,
                "estado":            "ACTIVO",
                "creado_por":        username
            }).execute()
            datos["folio"] = folio_manual
            logger.info(f"[DB] ✅ Folio MANUAL {folio_manual} guardado")
            return True
        except Exception as e:
            em = str(e).lower()
            if "duplicate" in em or "unique" in em or "23505" in em:
                logger.error(f"[ERROR] Folio {folio_manual} YA EXISTE")
            else:
                logger.error(f"[ERROR BD] {e}")
            return False

    # ── MODO AUTOMÁTICO +1 ────────────────────────────────────────────────────
    logger.info("[FOLIO AUTO] Generando folio automático...")
    try:
        folio_base = generar_folio_automatico_cdmx()
    except Exception as e:
        logger.error(f"[ERROR] No se pudo generar folio: {e}")
        return False

    num_inicial = int(folio_base[len(PREFIJO_CDMX):]) if folio_base[len(PREFIJO_CDMX):].isdigit() else 1

    for intento in range(10_000_000):
        candidato = f"{PREFIJO_CDMX}{num_inicial + intento}"
        try:
            supabase.table("folios_registrados").insert({
                "folio":             candidato,
                "marca":             datos["marca"],
                "linea":             datos["linea"],
                "anio":              datos["anio"],
                "numero_serie":      datos["numero_serie"],
                "numero_motor":      datos["numero_motor"],
                "nombre":            datos.get("nombre", "SIN NOMBRE"),
                "fecha_expedicion":  fexp_date.isoformat(),
                "fecha_vencimiento": fven_date.isoformat(),
                "entidad":           ENTIDAD,
                "estado":            "ACTIVO",
                "creado_por":        username
            }).execute()
            datos["folio"] = candidato
            logger.info(f"[DB] ✅ Folio AUTO {candidato} guardado (intento {intento + 1})")
            return True
        except Exception as e:
            em = str(e).lower()
            if "duplicate" in em or "unique" in em or "23505" in em:
                logger.warning(f"[DUP] {candidato} existe → siguiente")
                continue
            logger.error(f"[ERROR BD] {e}")
            return False
        if intento > 0 and intento % 10_000 == 0:
            logger.info(f"[DB] Guardando... intento {intento}")

    logger.error(f"[ERROR] Sin folio disponible tras 10,000,000 intentos")
    return False

# ===================== GENERACIÓN QR Y PDF =====================
def generar_qr_dinamico_cdmx(folio):
    try:
        url = f"{URL_CONSULTA_BASE}/consulta/{folio}"
        qr  = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_M,
                             box_size=4, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        logger.info(f"[QR] ✅ {folio}")
        return img, url
    except Exception as e:
        logger.error(f"[ERROR QR] {e}")
        return None, None


def generar_pdf_unificado_cdmx(datos: dict) -> str:
    fol          = datos["folio"]
    fecha_exp_dt = datos["fecha_exp"]
    fecha_ven_dt = datos["fecha_ven"]

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
        # =====================================================================
        # PÁGINA 1
        # =====================================================================
        doc1 = fitz.open(PLANTILLA_PRINCIPAL)
        pg1  = doc1[0]

        meses = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                 7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
        fecha_texto = f"{fecha_exp_dt.day} de {meses[fecha_exp_dt.month]} del {fecha_exp_dt.year}"

        pg1.insert_text((50,  130), "FOLIO: ",                  fontsize=12, fontname="helv", color=(0,0,0))
        pg1.insert_text((100, 130), fol,                        fontsize=12, fontname="helv", color=(1,0,0))
        pg1.insert_text((130, 145), fecha_texto,                fontsize=12, fontname="helv", color=(0,0,0))
        pg1.insert_text((87,  290), datos["marca"],             fontsize=11, fontname="helv", color=(0,0,0))
        pg1.insert_text((375, 290), datos["numero_serie"],      fontsize=11, fontname="helv", color=(0,0,0))
        pg1.insert_text((87,  307), datos["linea"],             fontsize=11, fontname="helv", color=(0,0,0))
        pg1.insert_text((375, 307), datos["numero_motor"],      fontsize=11, fontname="helv", color=(0,0,0))
        pg1.insert_text((87,  323), str(datos["anio"]),         fontsize=11, fontname="helv", color=(0,0,0))
        pg1.insert_text((375, 323), fecha_ven_str,              fontsize=11, fontname="helv", color=(0,0,0))
        if datos.get("nombre"):
            pg1.insert_text((375, 340), datos["nombre"],        fontsize=11, fontname="helv", color=(0,0,0))

        img_qr, _ = generar_qr_dinamico_cdmx(fol)
        if img_qr:
            buf = BytesIO()
            img_qr.save(buf, format="PNG")
            buf.seek(0)
            qr_pix = fitz.Pixmap(buf.read())
            pg1.insert_image(fitz.Rect(49, 653, 145, 749), pixmap=qr_pix, overlay=True)

        # =====================================================================
        # PÁGINA 2 — coordenadas explícitas
        # =====================================================================
        if os.path.exists(PLANTILLA_SECUNDARIA):
            doc2 = fitz.open(PLANTILLA_SECUNDARIA)
            pg2  = doc2[0]

            titulo_p2 = (f"IMPUESTO POR DERECHO DE AUTOMOVIL Y MOTOCICLETAS "
                         f"(PERMISO PARA CIRCULAR {DIAS_PERMISO} DIAS)")
            anio_str  = str(datos["anio"])

            pg2.insert_text((135, 170), titulo_p2,                      fontsize=6,  fontname="hebo", color=(0,0,0))
            pg2.insert_text((135, 194), datos["numero_serie"],           fontsize=6,  fontname="hebo", color=(0,0,0))
            pg2.insert_text((135, 202), anio_str,                        fontsize=6,  fontname="hebo", color=(0,0,0))
            pg2.insert_text((385, 411), f"${PRECIO_PERMISO}",            fontsize=16, fontname="hebo", color=(0,0,0))
            pg2.insert_text((190, 324), fecha_exp_dt.strftime('%d/%m/%Y'), fontsize=6, fontname="hebo", color=(0,0,0))

            doc1.insert_pdf(doc2)
            doc2.close()

        doc1.save(out)
        doc1.close()
        logger.info(f"[PDF] ✅ {out}")

    except Exception as e:
        logger.error(f"[ERROR PDF] {e}")
        fb = fitz.open()
        fb.new_page().insert_text((50, 50), f"ERROR - Folio: {fol}", fontsize=12)
        fb.save(out)
        fb.close()

    return out

# ===================== TEMPLATE TABLA INLINE EDITABLE ========================
TABLE_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin · {{ info_tabla.nombre }}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Courier New',monospace;background:#0d0d0d;color:#e2e8f0;min-height:100vh}
header{background:#111827;border-bottom:1px solid #1f2937;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:200}
.title{font-size:13px;font-weight:700;letter-spacing:2px;color:#f1f5f9}
.dot{width:8px;height:8px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;display:inline-block;margin-right:10px}
.toolbar{display:flex;gap:10px;align-items:center;padding:12px 20px;background:#111827;border-bottom:1px solid #1f2937;flex-wrap:wrap}
.search-box{background:#1f2937;border:1px solid #374151;color:#e2e8f0;border-radius:6px;padding:8px 14px;font-family:inherit;font-size:12px;width:340px;outline:none;transition:border .2s}
.search-box:focus{border-color:#3b82f6}
.search-box::placeholder{color:#6b7280}
.btn{background:transparent;border:1px solid #374151;color:#9ca3af;border-radius:6px;padding:7px 14px;cursor:pointer;font-size:11px;font-family:inherit;letter-spacing:1px;text-decoration:none;display:inline-flex;align-items:center;gap:5px;transition:all .15s;white-space:nowrap}
.btn:hover{border-color:#6b7280;color:#e2e8f0}
.btn-blue{border-color:#1d4ed8;color:#60a5fa}
.btn-blue:hover{background:#1e3a5f}
.counter{font-size:11px;color:#6b7280;letter-spacing:1px;margin-left:4px}
.table-wrap{overflow-x:auto;padding:16px 20px 60px}
table{width:100%;border-collapse:collapse;font-size:11px;table-layout:auto}
thead th{background:#1f2937;color:#6b7280;padding:9px 8px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:700;border-bottom:1px solid #374151;white-space:nowrap;position:sticky;top:55px;z-index:100}
tbody tr{transition:background .1s}
tbody tr:nth-child(odd){background:#111827}
tbody tr:nth-child(even){background:#0d0d0d}
tbody tr:hover{background:#1a2335}
tbody tr.hidden{display:none}
td{padding:3px 4px;border-bottom:1px solid #111827;vertical-align:middle}
.cell-input{background:transparent;border:1px solid transparent;color:#9ca3af;border-radius:4px;padding:4px 6px;font-size:11px;font-family:inherit;width:100%;min-width:90px;outline:none;transition:all .15s}
.cell-input:hover{border-color:#374151}
.cell-input:focus{background:#1e3a5f;border-color:#3b82f6;color:#93c5fd;min-width:140px}
.cell-input.saving{background:#064e3b;border-color:#10b981;color:#6ee7b7}
.cell-input.saved{background:#065f46;border-color:#10b981}
.cell-input.err{background:#7f1d1d;border-color:#ef4444;color:#fca5a5}
.col-num{color:#4b5563;user-select:none;font-size:10px;white-space:nowrap;padding:3px 8px}
.col-folio .cell-input{color:#fbbf24}
.col-estado .cell-input{color:#f59e0b}
.col-nombre .cell-input,.col-contribuyente .cell-input{color:#e2e8f0}
.btn-del{background:transparent;border:1px solid #374151;color:#ef4444;border-radius:4px;padding:3px 8px;cursor:pointer;font-size:10px;font-family:inherit;white-space:nowrap}
.btn-del:hover{background:#7f1d1d;border-color:#ef4444}
.empty{text-align:center;color:#4b5563;padding:60px;font-size:12px;letter-spacing:1px}
.toast{position:fixed;bottom:24px;right:24px;z-index:999;padding:10px 18px;border-radius:8px;font-size:12px;letter-spacing:1px;opacity:0;transition:opacity .3s;pointer-events:none;max-width:320px}
.toast.show{opacity:1}
.toast.ok{background:#064e3b;border:1px solid #10b981;color:#6ee7b7}
.toast.err{background:#7f1d1d;border:1px solid #ef4444;color:#fca5a5}
</style>
</head>
<body>

<header>
  <div style="display:flex;align-items:center">
    <span class="dot"></span>
    <span class="title">ADMIN · {{ info_tabla.nombre | upper }}</span>
    <span class="counter" id="row-counter" style="margin-left:14px">{{ registros|length }} registros</span>
  </div>
  <div style="display:flex;gap:8px">
    <a href="/descargar_tabla/{{ nombre_tabla }}" class="btn btn-blue">⬇ CSV</a>
    <a href="/admin_tablas" class="btn">← TABLAS</a>
    <a href="/admin" class="btn">⌂ ADMIN</a>
  </div>
</header>

<div class="toolbar">
  <input
    type="text"
    class="search-box"
    id="search-input"
    placeholder="Buscar en todos los campos — folio, nombre, serie, estado..."
    oninput="filterTable(this.value)"
    autocomplete="off"
  >
  <span class="counter" id="search-info"></span>
</div>

<div class="table-wrap">
  {% if registros %}
  <table id="main-table">
    <thead>
      <tr>
        <th>#</th>
        {% for col in columnas %}
        <th>{{ col }}</th>
        {% endfor %}
        <th>DEL</th>
      </tr>
    </thead>
    <tbody>
      {% for reg in registros %}
      <tr data-idx="{{ loop.index }}">
        <td class="col-num">{{ loop.index }}</td>
        {% for col in columnas %}
        <td class="col-{{ col }}">
          <input
            type="text"
            class="cell-input"
            value="{{ reg.get(col, '') if reg.get(col) is not none else '' }}"
            data-col="{{ col }}"
            data-pk="{{ reg.get(pk_col, '') }}"
            onblur="saveCell(this)"
            onkeydown="handleKey(event, this)"
            title="{{ col }}: {{ reg.get(col, '') }}"
          >
        </td>
        {% endfor %}
        <td>
          <button
            class="btn-del"
            onclick="deleteRow(this, '{{ reg.get(pk_col, '') }}')"
            title="Eliminar registro"
          >✕</button>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">SIN REGISTROS EN ESTA TABLA</div>
  {% endif %}
</div>

<div class="toast" id="toast"></div>

<script>
const TABLA   = "{{ nombre_tabla }}";
const PK_COL  = "{{ pk_col }}";

// ── Búsqueda universal (sin selector de columna) ──────────────────────────────
function filterTable(q) {
  q = q.toLowerCase().trim();
  const rows = document.querySelectorAll('#main-table tbody tr');
  let visible = 0;

  rows.forEach(row => {
    if (!q) {
      row.classList.remove('hidden');
      visible++;
      return;
    }
    // Busca en TODOS los inputs del row
    const inputs = row.querySelectorAll('.cell-input');
    let found = false;
    inputs.forEach(inp => {
      if (inp.value.toLowerCase().includes(q)) found = true;
    });
    row.classList.toggle('hidden', !found);
    if (found) visible++;
  });

  document.getElementById('row-counter').textContent = visible + ' registro(s)';
  document.getElementById('search-info').textContent =
    q ? ('(' + visible + ' resultado(s))') : '';
}

// ── Guardar celda (blur / Enter) ──────────────────────────────────────────────
function handleKey(e, inp) {
  if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
  if (e.key === 'Escape') { inp.value = inp.defaultValue; inp.blur(); }
}

function saveCell(input) {
  const pk  = input.dataset.pk;
  const col = input.dataset.col;
  const val = input.value;
  if (val === input.defaultValue) return;   // sin cambios

  input.classList.add('saving');

  fetch('/api/update_cell', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tabla: TABLA, pk_col: PK_COL, pk_val: pk, col: col, val: val})
  })
  .then(r => r.json())
  .then(d => {
    input.classList.remove('saving');
    if (d.ok) {
      input.defaultValue = val;
      input.classList.add('saved');
      setTimeout(() => input.classList.remove('saved'), 1500);
      showToast('✓ ' + col + ' guardado', true);
    } else {
      input.value = input.defaultValue;
      input.classList.add('err');
      setTimeout(() => input.classList.remove('err'), 2000);
      showToast('Error: ' + (d.error || 'desconocido'), false);
    }
  })
  .catch(() => {
    input.classList.remove('saving');
    showToast('Error de red', false);
  });
}

// ── Eliminar fila ─────────────────────────────────────────────────────────────
function deleteRow(btn, pk) {
  if (!confirm('¿Eliminar este registro? Esta acción no se puede deshacer.')) return;
  btn.disabled = true;
  btn.textContent = '...';

  fetch('/api/delete_row', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tabla: TABLA, pk_col: PK_COL, pk_val: pk})
  })
  .then(r => r.json())
  .then(d => {
    if (d.ok) {
      const tr = btn.closest('tr');
      tr.style.opacity = '0';
      tr.style.transition = 'opacity .3s';
      setTimeout(() => {
        tr.remove();
        const cnt = document.querySelectorAll('#main-table tbody tr:not(.hidden)').length;
        document.getElementById('row-counter').textContent = cnt + ' registro(s)';
      }, 300);
      showToast('Registro eliminado', true);
    } else {
      btn.disabled = false;
      btn.textContent = '✕';
      showToast('Error al eliminar: ' + (d.error || '?'), false);
    }
  })
  .catch(() => {
    btn.disabled = false;
    btn.textContent = '✕';
    showToast('Error de red', false);
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer;
function showToast(msg, ok) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = 'toast show ' + (ok ? 'ok' : 'err');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
}

// Focus en búsqueda al cargar
document.getElementById('search-input').focus();
</script>
</body>
</html>
"""

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
            logger.info("[LOGIN] Admin")
            return redirect(url_for('admin'))

        resp = supabase.table("verificaciondigitalcdmx")\
            .select("*").eq("username", username).eq("password", password).execute()

        if resp.data:
            session['user_id']  = resp.data[0].get('id')
            session['username'] = resp.data[0]['username']
            session['admin']    = False
            logger.info(f"[LOGIN] {username}")
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

        existe = supabase.table("verificaciondigitalcdmx")\
            .select("id").eq("username", username).limit(1).execute()

        if existe.data:
            flash('Error: el usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username":       username,
                "password":       password,
                "folios_asignac": folios,
                "folios_usados":  0
            }).execute()
            flash('Usuario creado.', 'success')

    return render_template('crear_usuario.html')


@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if not session.get('username'):
        return redirect(url_for('login'))
    if session.get('admin'):
        return redirect(url_for('admin'))

    user_data = supabase.table("verificaciondigitalcdmx")\
        .select("*").eq("username", session['username']).limit(1).execute()

    if not user_data.data:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for('login'))

    usuario            = user_data.data[0]
    folios_asignados   = int(usuario.get('folios_asignac', 0))
    folios_usados      = int(usuario.get('folios_usados', 0))
    folios_disponibles = folios_asignados - folios_usados
    porcentaje         = (folios_usados / folios_asignados * 100) if folios_asignados > 0 else 0

    if request.method == 'POST':
        if folios_disponibles <= 0:
            flash("⚠️ Sin folios disponibles.", "error")
            return render_template('registro_usuario.html',
                                   folios_asignados=folios_asignados,
                                   folios_usados=folios_usados,
                                   folios_disponibles=folios_disponibles,
                                   porcentaje=porcentaje)

        folio_manual  = request.form.get('folio', '').strip()
        marca         = request.form.get('marca', '').strip().upper()
        linea         = request.form.get('linea', '').strip().upper()
        anio          = request.form.get('anio', '').strip()
        numero_serie  = request.form.get('serie', '').strip().upper()
        numero_motor  = request.form.get('motor', '').strip().upper()
        nombre        = request.form.get('nombre', '').strip().upper() or 'SIN NOMBRE'
        fecha_inicio_str = request.form.get('fecha_inicio', '').strip()

        if not all([marca, linea, anio, numero_serie, numero_motor]):
            flash("❌ Faltan campos obligatorios.", "error")
            return render_template('registro_usuario.html',
                                   folios_asignados=folios_asignados,
                                   folios_usados=folios_usados,
                                   folios_disponibles=folios_disponibles,
                                   porcentaje=porcentaje)

        if not fecha_inicio_str:
            fecha_inicio = now_cdmx()
        else:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').replace(tzinfo=TZ_CDMX)
            except Exception:
                flash("❌ Fecha inválida.", "error")
                return render_template('registro_usuario.html',
                                       folios_asignados=folios_asignados,
                                       folios_usados=folios_usados,
                                       folios_disponibles=folios_disponibles,
                                       porcentaje=porcentaje)

        venc  = fecha_inicio + timedelta(days=DIAS_PERMISO)
        datos = {
            "folio":        folio_manual or None,
            "marca":        marca,
            "linea":        linea,
            "anio":         anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "nombre":       nombre,
            "fecha_exp":    fecha_inicio,
            "fecha_ven":    venc
        }

        ok = guardar_folio_con_reintento(datos, session['username'])
        if not ok:
            flash("❌ Error al registrar (folio duplicado o error de BD).", "error")
            return render_template('registro_usuario.html',
                                   folios_asignados=folios_asignados,
                                   folios_usados=folios_usados,
                                   folios_disponibles=folios_disponibles,
                                   porcentaje=porcentaje)

        folio_final = datos["folio"]
        generar_pdf_unificado_cdmx(datos)

        supabase.table("verificaciondigitalcdmx")\
            .update({"folios_usados": folios_usados + 1})\
            .eq("username", session['username']).execute()

        flash(f'✅ Folio: {folio_final}', 'success')
        return render_template('exitoso.html',
                               folio=folio_final,
                               serie=numero_serie,
                               fecha_generacion=fecha_inicio.strftime('%d/%m/%Y %H:%M'))

    return render_template('registro_usuario.html',
                           folios_asignados=folios_asignados,
                           folios_usados=folios_usados,
                           folios_disponibles=folios_disponibles,
                           porcentaje=porcentaje)


@app.route('/mis_permisos')
def mis_permisos():
    if not session.get('username') or session.get('admin'):
        flash('Acceso denegado.', 'error')
        return redirect(url_for('login'))

    permisos = supabase.table("folios_registrados")\
        .select("*")\
        .eq("creado_por", session['username'])\
        .order("fecha_expedicion", desc=True)\
        .execute().data or []

    hoy = today_cdmx()
    for p in permisos:
        try:
            fe = parse_date_any(p.get('fecha_expedicion'))
            fv = parse_date_any(p.get('fecha_vencimiento'))
            p['fecha_formateada'] = fe.strftime('%d/%m/%Y')
            p['hora_formateada']  = "00:00:00"
            p['estado']           = "VIGENTE" if hoy <= fv else "VENCIDO"
        except Exception:
            p['fecha_formateada'] = 'Error'
            p['hora_formateada']  = 'Error'
            p['estado']           = 'ERROR'

    usr_data = supabase.table("verificaciondigitalcdmx")\
        .select("folios_asignac, folios_usados")\
        .eq("username", session['username']).limit(1).execute().data
    usr_row = usr_data[0] if usr_data else {"folios_asignac": 0, "folios_usados": 0}

    return render_template('mis_permisos.html',
                           permisos=permisos,
                           total_generados=len(permisos),
                           folios_asignados=int(usr_row.get('folios_asignac', 0)),
                           folios_usados=int(usr_row.get('folios_usados', 0)))


@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio_manual     = request.form.get('folio', '').strip()
        marca            = request.form.get('marca', '').strip().upper()
        linea            = request.form.get('linea', '').strip().upper()
        anio             = request.form.get('anio', '').strip()
        numero_serie     = request.form.get('serie', '').strip().upper()
        numero_motor     = request.form.get('motor', '').strip().upper()
        nombre           = request.form.get('nombre', '').strip().upper() or 'SIN NOMBRE'
        fecha_inicio_str = request.form.get('fecha_inicio', '').strip()

        if not all([marca, linea, anio, numero_serie, numero_motor, fecha_inicio_str]):
            flash("❌ Faltan campos.", "error")
            return redirect(url_for('registro_admin'))

        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').replace(tzinfo=TZ_CDMX)
        except Exception:
            flash("❌ Fecha inválida.", "error")
            return redirect(url_for('registro_admin'))

        venc  = fecha_inicio + timedelta(days=DIAS_PERMISO)
        datos = {
            "folio":        folio_manual or None,
            "marca":        marca,
            "linea":        linea,
            "anio":         anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "nombre":       nombre,
            "fecha_exp":    fecha_inicio,
            "fecha_ven":    venc
        }

        ok = guardar_folio_con_reintento(datos, "ADMIN")
        if not ok:
            flash("❌ Error al registrar (folio duplicado o error de BD).", "error")
            return redirect(url_for('registro_admin'))

        folio_final = datos["folio"]
        generar_pdf_unificado_cdmx(datos)

        flash('✅ Permiso generado.', 'success')
        return render_template('exitoso.html',
                               folio=folio_final,
                               serie=numero_serie,
                               fecha_generacion=fecha_inicio.strftime('%d/%m/%Y %H:%M'))

    return render_template('registro_admin.html')


@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio    = request.form['folio'].strip()
        registros = supabase.table("folios_registrados")\
            .select("*").eq("folio", folio).limit(1).execute().data

        if not registros:
            resultado = {"estado": "NO REGISTRADO", "color": "rojo", "folio": folio}
        else:
            r    = registros[0]
            fexp = parse_date_any(r.get('fecha_expedicion'))
            fven = parse_date_any(r.get('fecha_vencimiento'))
            hoy  = today_cdmx()
            estado = "VIGENTE" if hoy <= fven else "VENCIDO"
            color  = "verde"   if estado == "VIGENTE" else "cafe"
            resultado = {
                "estado":           estado,
                "color":            color,
                "folio":            folio,
                "fecha_expedicion": fexp.strftime('%d/%m/%Y'),
                "fecha_vencimiento":fven.strftime('%d/%m/%Y'),
                "marca":            r.get('marca', ''),
                "linea":            r.get('linea', ''),
                "año":              r.get('anio', ''),
                "numero_serie":     r.get('numero_serie', ''),
                "numero_motor":     r.get('numero_motor', ''),
                "entidad":          r.get('entidad', ENTIDAD)
            }
        return render_template('resultado_consulta.html', resultado=resultado)
    return render_template('consulta_folio.html')


@app.route('/consulta/<folio>')
def consulta_folio_directo(folio):
    row = supabase.table("folios_registrados")\
        .select("*").eq("folio", folio).limit(1).execute().data

    if not row:
        return render_template("resultado_consulta.html", resultado={
            "estado": "NO REGISTRADO", "color": "rojo", "folio": folio
        })

    r  = row[0]
    fe = parse_date_any(r.get('fecha_expedicion'))
    fv = parse_date_any(r.get('fecha_vencimiento'))
    hoy    = today_cdmx()
    estado = "VIGENTE" if hoy <= fv else "VENCIDO"
    color  = "verde"   if estado == "VIGENTE" else "cafe"

    return render_template("resultado_consulta.html", resultado={
        "estado":           estado,
        "color":            color,
        "folio":            folio,
        "fecha_expedicion": fe.strftime("%d/%m/%Y"),
        "fecha_vencimiento":fv.strftime("%d/%m/%Y"),
        "marca":            r.get('marca', ''),
        "linea":            r.get('linea', ''),
        "año":              r.get('anio', ''),
        "numero_serie":     r.get('numero_serie', ''),
        "numero_motor":     r.get('numero_motor', ''),
        "entidad":          r.get('entidad', ENTIDAD)
    })


@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    ruta_pdf = os.path.join(OUTPUT_DIR, f"{folio}.pdf")
    if not os.path.exists(ruta_pdf):
        abort(404)
    return send_file(ruta_pdf, as_attachment=True,
                     download_name=f"{folio}_cdmx.pdf",
                     mimetype='application/pdf')


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

    query = supabase.table("folios_registrados").select("*").eq("entidad", ENTIDAD)

    if filtro:
        if criterio == 'folio':
            query = query.ilike('folio', f'%{filtro}%')
        elif criterio == 'numero_serie':
            query = query.ilike('numero_serie', f'%{filtro}%')

    if fecha_inicio:
        query = query.gte('fecha_expedicion', fecha_inicio)
    if fecha_fin:
        query = query.lte('fecha_expedicion', fecha_fin)

    query  = query.order('fecha_expedicion', desc=(ordenar == 'desc'))
    folios = query.execute().data or []

    hoy              = today_cdmx()
    folios_filtrados = []
    for f in folios:
        try:
            fv        = parse_date_any(f.get('fecha_vencimiento'))
            f['estado'] = "VIGENTE" if hoy <= fv else "VENCIDO"
        except Exception:
            f['estado'] = 'ERROR'
        if estado_filtro == 'todos':
            folios_filtrados.append(f)
        elif estado_filtro == f['estado'].lower():
            folios_filtrados.append(f)

    return render_template('admin_folios.html',
                           folios=folios_filtrados,
                           filtro=filtro, criterio=criterio,
                           estado=estado_filtro, fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin, ordenar=ordenar)


@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = {
            "marca":             request.form['marca'],
            "linea":             request.form['linea'],
            "anio":              request.form['anio'],
            "numero_serie":      request.form['serie'],
            "numero_motor":      request.form['motor'],
            "fecha_expedicion":  request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento']
        }
        supabase.table("folios_registrados").update(data).eq("folio", folio).execute()
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
    folio = request.form['folio']
    supabase.table("folios_registrados").delete().eq("folio", folio).execute()
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ===================== ADMINISTRACIÓN DE TABLAS =====================

TABLAS_DISPONIBLES = {
    'folios_registrados': {
        'nombre':   'Folios Registrados',
        'pk_col':   'folio',
        'columnas': ['folio', 'marca', 'linea', 'anio', 'numero_serie', 'numero_motor',
                     'nombre', 'fecha_expedicion', 'fecha_vencimiento',
                     'entidad', 'estado', 'creado_por']
    },
    'verificaciondigitalcdmx': {
        'nombre':   'Usuarios del Sistema',
        'pk_col':   'id',
        'columnas': ['id', 'username', 'password', 'folios_asignac', 'folios_usados']
    }
}


@app.route('/admin_tablas')
def admin_tablas():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('admin_tablas.html', tablas=TABLAS_DISPONIBLES)


@app.route('/admin_tabla/<nombre_tabla>')
def admin_tabla(nombre_tabla):
    """
    Tabla completa inline editable.
    - Muestra TODAS las columnas y TODOS los registros.
    - Búsqueda universal: un solo campo que filtra en todos los campos (JS client-side).
    - Cada celda es editable (blur/Enter → PATCH a /api/update_cell).
    - Botón ✕ por fila → DELETE a /api/delete_row.
    - Botón ⬇ CSV → /descargar_tabla/<nombre_tabla>.
    """
    if not session.get('admin'):
        return redirect(url_for('login'))

    if nombre_tabla not in TABLAS_DISPONIBLES:
        flash('Tabla no encontrada', 'error')
        return redirect(url_for('admin_tablas'))

    info_tabla = TABLAS_DISPONIBLES[nombre_tabla]
    pk_col     = info_tabla['pk_col']

    try:
        registros = supabase.table(nombre_tabla).select("*").limit(10000).execute().data or []
    except Exception as e:
        registros = []
        flash(f'Error al cargar datos: {e}', 'error')

    # Usar TODAS las columnas reales que devuelve Supabase (no solo las predefinidas)
    if registros:
        columnas = list(registros[0].keys())
    else:
        columnas = info_tabla.get('columnas', [])

    return render_template_string(TABLE_TEMPLATE,
                                  nombre_tabla=nombre_tabla,
                                  info_tabla=info_tabla,
                                  registros=registros,
                                  columnas=columnas,
                                  pk_col=pk_col)


# ===================== API INLINE EDITING =====================================

@app.route('/api/update_cell', methods=['POST'])
def api_update_cell():
    """PATCH de una sola celda desde la tabla inline."""
    if not session.get('admin'):
        return jsonify({"ok": False, "error": "no autorizado"}), 403

    data   = request.get_json(force=True)
    tabla  = data.get('tabla')
    pk_col = data.get('pk_col')
    pk_val = data.get('pk_val')
    col    = data.get('col')
    val    = data.get('val', '')

    if tabla not in TABLAS_DISPONIBLES:
        return jsonify({"ok": False, "error": "tabla no permitida"}), 400

    if not col or not pk_val:
        return jsonify({"ok": False, "error": "datos incompletos"}), 400

    try:
        supabase.table(tabla).update({col: val or None}).eq(pk_col, pk_val).execute()
        logger.info(f"[API] UPDATE {tabla}.{col} pk={pk_val}")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"[API ERROR] update_cell: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/delete_row', methods=['POST'])
def api_delete_row():
    """DELETE de una fila desde la tabla inline."""
    if not session.get('admin'):
        return jsonify({"ok": False, "error": "no autorizado"}), 403

    data   = request.get_json(force=True)
    tabla  = data.get('tabla')
    pk_col = data.get('pk_col')
    pk_val = data.get('pk_val')

    if tabla not in TABLAS_DISPONIBLES:
        return jsonify({"ok": False, "error": "tabla no permitida"}), 400

    if not pk_val:
        return jsonify({"ok": False, "error": "pk vacío"}), 400

    try:
        supabase.table(tabla).delete().eq(pk_col, pk_val).execute()
        logger.info(f"[API] DELETE {tabla} pk={pk_val}")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"[API ERROR] delete_row: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/descargar_tabla/<nombre_tabla>')
def descargar_tabla(nombre_tabla):
    """Descarga TODOS los registros de la tabla como CSV."""
    if not session.get('admin'):
        return redirect(url_for('login'))

    if nombre_tabla not in TABLAS_DISPONIBLES:
        abort(404)

    try:
        registros = supabase.table(nombre_tabla).select("*").limit(100_000).execute().data or []
    except Exception as e:
        flash(f'Error al exportar: {e}', 'error')
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))

    if not registros:
        flash("Sin registros para exportar.", "error")
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(registros[0].keys()), extrasaction='ignore')
    writer.writeheader()
    writer.writerows(registros)

    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment;filename={nombre_tabla}.csv'}
    )


# ===================== RUTAS HEREDADAS (compatibilidad con templates) =========

@app.route('/admin_editar_registro/<nombre_tabla>/<registro_id>', methods=['GET', 'POST'])
def admin_editar_registro(nombre_tabla, registro_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        flash('Tabla no encontrada', 'error')
        return redirect(url_for('admin_tablas'))

    info_tabla = TABLAS_DISPONIBLES[nombre_tabla]
    pk_col     = info_tabla['pk_col']

    if request.method == 'POST':
        datos = {}
        for columna in info_tabla['columnas']:
            if columna in request.form:
                valor = request.form[columna].strip()
                if valor:
                    datos[columna] = valor
        try:
            supabase.table(nombre_tabla).update(datos).eq(pk_col, registro_id).execute()
            flash('Registro actualizado correctamente', 'success')
            return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
        except Exception as e:
            flash(f'Error al actualizar: {e}', 'error')

    try:
        registro = supabase.table(nombre_tabla).select("*").eq(pk_col, registro_id).execute().data
        if not registro:
            flash('Registro no encontrado', 'error')
            return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
        registro = registro[0]
    except Exception as e:
        flash(f'Error al cargar registro: {e}', 'error')
        return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))

    return render_template('admin_editar_registro.html',
                           nombre_tabla=nombre_tabla,
                           info_tabla=info_tabla,
                           registro=registro,
                           registro_id=registro_id)


@app.route('/admin_eliminar_registro/<nombre_tabla>/<registro_id>', methods=['POST'])
def admin_eliminar_registro(nombre_tabla, registro_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        flash('Tabla no encontrada', 'error')
        return redirect(url_for('admin_tablas'))

    pk_col = TABLAS_DISPONIBLES[nombre_tabla]['pk_col']
    try:
        supabase.table(nombre_tabla).delete().eq(pk_col, registro_id).execute()
        flash('Registro eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'error')

    return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))


@app.route('/admin_agregar_registro/<nombre_tabla>', methods=['GET', 'POST'])
def admin_agregar_registro(nombre_tabla):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if nombre_tabla not in TABLAS_DISPONIBLES:
        flash('Tabla no encontrada', 'error')
        return redirect(url_for('admin_tablas'))

    info_tabla = TABLAS_DISPONIBLES[nombre_tabla]

    if request.method == 'POST':
        datos = {}
        for columna in info_tabla['columnas']:
            if columna != 'id' and columna in request.form:
                valor = request.form[columna].strip()
                if valor:
                    datos[columna] = valor
        try:
            supabase.table(nombre_tabla).insert(datos).execute()
            flash('Registro agregado correctamente', 'success')
            return redirect(url_for('admin_tabla', nombre_tabla=nombre_tabla))
        except Exception as e:
            flash(f'Error al agregar: {e}', 'error')

    return render_template('admin_agregar_registro.html',
                           nombre_tabla=nombre_tabla,
                           info_tabla=info_tabla)


# ===================== MAIN =====================
if __name__ == '__main__':
    logger.info("🚀 SERVIDOR CDMX INICIADO")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
