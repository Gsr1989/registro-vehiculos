"""
CDMX — Configuración compartida entre el panel web (Flask) y el bot (aiogram).

Todo lo que ANTES estaba duplicado en los dos archivos vive aquí una sola vez:
cliente de Supabase, rutas, constantes y — lo más importante — el candado
global de PyMuPDF.
"""

import os
import sys
import logging
import threading
from datetime import datetime, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client

# ===================== LOGGING =====================
sys.dont_write_bytecode = True
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cdmx")

# ===================== ZONA HORARIA =====================
TZ_CDMX = ZoneInfo("America/Mexico_City")


def now_cdmx() -> datetime:
    return datetime.now(TZ_CDMX)


def today_cdmx() -> date:
    return now_cdmx().date()


def parse_date_any(value) -> date:
    import re
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


# ===================== SUPABASE =====================
# Ahora por variable de entorno. Los valores por defecto son los que ya tenías,
# para que NO se rompa si todavía no las configuras en Render.
# Recomendación: ponlas en Render → Environment y borra los defaults de aquí.
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://xsagwqepoljfsogusubw.supabase.co"
)
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== CONFIG GENERAL =====================
BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
BASE_URL             = os.getenv("BASE_URL", "https://semovidigitalgob.onrender.com").rstrip("/")
URL_CONSULTA_BASE    = BASE_URL          # el QR apunta al mismo servicio fusionado

OUTPUT_DIR           = "documentos"
PLANTILLA_PRINCIPAL  = "cdmxdigital2025ppp.pdf"
PLANTILLA_SECUNDARIA = "elbueno.pdf"

ENTIDAD              = "cdmx"
PRECIO_PERMISO       = 374
DIAS_PERMISO         = 30
HORAS_LIMITE_PAGO    = 48       # limpieza del panel
HORAS_TIMER_BOT      = 36       # timer del bot
PAGE_SIZE            = 100
BUCKET_NAME          = "permisos-cdmx"

ADMIN_USER           = os.getenv("ADMIN_USER", "Serg890105tm3")
ADMIN_PASS           = os.getenv("ADMIN_PASS", "Serg890105tm3")
SECRET_KEY           = os.getenv("SECRET_KEY", "clave_muy_segura_123456")

# Prefijos de folio — SON DISTINTOS A PROPÓSITO, las series no se pisan
PREFIJO_PANEL        = "412"    # folios generados desde la web
PREFIJO_BOT          = "122"    # folios generados desde Telegram

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===================== CANDADO GLOBAL DE PDF =====================
# CRÍTICO: PyMuPDF (fitz) no es thread-safe. Antes de fusionar, el panel y el
# bot tenían cada quien su propio Lock — como eran procesos separados, no
# importaba. Ahora corren en el MISMO proceso, así que si el bot y la web
# generan un PDF al mismo tiempo, sin este candado compartido los documentos
# se corrompen entre sí. Los dos módulos importan ESTE, no crean el suyo.
PDF_LOCK = threading.Lock()

# ===================== TABLAS DEL PANEL =====================
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
