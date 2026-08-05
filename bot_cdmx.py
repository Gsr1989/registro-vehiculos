"""
CDMX — Bot de Telegram (aiogram).

Es TU archivo original. Cambios:
  · Ya NO crea su propia app FastAPI (eso lo hace main.py)
  · Supabase, el lock de PDF y las constantes vienen de config_cdmx
  · Se agregó snapshot_timers() para que el panel web pueda listarlos
  · El lifespan se partió en arranque_bot() / cierre_bot(), que llama main.py
Los handlers, el FSM y las coordenadas del PDF quedaron idénticos.
"""

from datetime import datetime, timedelta
import os
import asyncio
import aiohttp
import qrcode
import fitz
from io import BytesIO

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import (FSInputFile, ContentType, InlineKeyboardMarkup,
                           InlineKeyboardButton, CallbackQuery)
from aiogram.client.session.aiohttp import AiohttpSession

from config_cdmx import (
    supabase, logger, BOT_TOKEN, BASE_URL, URL_CONSULTA_BASE,
    OUTPUT_DIR, PLANTILLA_PRINCIPAL, PLANTILLA_SECUNDARIA,
    PRECIO_PERMISO, DIAS_PERMISO, HORAS_TIMER_BOT, PDF_LOCK, PREFIJO_BOT,
)

# Nombres que el archivo original usaba
PLANTILLA_PDF   = PLANTILLA_PRINCIPAL
PLANTILLA_BUENO = PLANTILLA_SECUNDARIA

_bot_session = AiohttpSession(timeout=aiohttp.ClientTimeout(total=300))
bot     = Bot(token=BOT_TOKEN, session=_bot_session)
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)

timers_activos       = {}
user_folios          = {}
pending_comprobantes = {}

FOLIO_PREFIJO      = PREFIJO_BOT      # "122"
folio_counter      = {"siguiente": 1}
MAX_INTENTOS_FOLIO = 100_000
_folio_lock        = asyncio.Lock()

# El candado de PDF es el COMPARTIDO con el panel (PyMuPDF no es thread-safe
# y ahora los dos corren en el mismo proceso)
_pdf_generation_lock = PDF_LOCK

MINUTOS_TIMER = HORAS_TIMER_BOT * 60   # 2160


# ── WATERMARK ─────────────────────────────────────────────────────────────────

def _sb_leer_watermark():
    try:
        r = supabase.table("folio_watermark").select("ultimo_asignado").eq("prefijo", FOLIO_PREFIJO).execute()
        if r.data:
            return r.data[0]["ultimo_asignado"]
        return None
    except Exception as e:
        print(f"[ERROR] leer_watermark: {e}")
        return None


def _sb_guardar_watermark(numero: int):
    try:
        supabase.table("folio_watermark").upsert({
            "prefijo": FOLIO_PREFIJO,
            "ultimo_asignado": numero
        }).execute()
        print(f"[WATERMARK] Guardado: {FOLIO_PREFIJO}{numero}")
    except Exception as e:
        print(f"[ERROR] guardar_watermark: {e}")


# ── FOLIO ─────────────────────────────────────────────────────────────────────

def _sb_folio_existe(folio: str) -> bool:
    try:
        r = supabase.table("folios_registrados").select("folio").eq("folio", folio).execute()
        return len(r.data) > 0
    except Exception as e:
        print(f"[ERROR] Verificando folio {folio}: {e}")
        return False


def _sb_obtener_siguiente_folio() -> str:
    """Pide candidatos en bloques de 500 con UNA sola consulta (.in_)."""
    inicio = folio_counter["siguiente"]
    BLOQUE = 500
    revisados = 0

    while revisados < MAX_INTENTOS_FOLIO:
        candidatos = [f"{FOLIO_PREFIJO}{inicio + i}" for i in range(BLOQUE)]

        try:
            resp = supabase.table("folios_registrados") \
                .select("folio").in_("folio", candidatos).execute()
            ocupados = {r["folio"] for r in (resp.data or [])}
        except Exception as e:
            print(f"[ERROR] consultando bloque de folios: {e}")
            ocupados = set()

        print(f"[FOLIO] bloque de {BLOQUE} revisado, ocupados={len(ocupados)}")

        for i, folio in enumerate(candidatos):
            if folio not in ocupados:
                numero_final = inicio + i
                folio_counter["siguiente"] = numero_final + 1
                _sb_guardar_watermark(numero_final)
                print(f"[FOLIO] Asignado: {folio}  (siguiente: {folio_counter['siguiente']})")
                return folio

        inicio += BLOQUE
        revisados += BLOQUE

    raise Exception("Sin folio disponible — limite alcanzado")


def _sb_inicializar_folio():
    try:
        watermark = _sb_leer_watermark()
        if watermark is not None:
            folio_counter["siguiente"] = watermark + 1
            print(f"[INFO] Folio desde watermark: {FOLIO_PREFIJO}{watermark} -> siguiente: {folio_counter['siguiente']}")
            return
        r = supabase.table("folios_registrados").select("folio").like("folio", f"{FOLIO_PREFIJO}%").execute()
        consecutivos = []
        for row in r.data or []:
            f = row.get("folio", "")
            if isinstance(f, str) and f.startswith(FOLIO_PREFIJO):
                sufijo = f[len(FOLIO_PREFIJO):]
                if sufijo.isdigit():
                    consecutivos.append(int(sufijo))
        if consecutivos:
            maximo = max(consecutivos)
            folio_counter["siguiente"] = maximo + 1
            _sb_guardar_watermark(maximo)
            print(f"[INFO] Folio desde DB (primera vez): {FOLIO_PREFIJO}{maximo} -> siguiente: {folio_counter['siguiente']}")
        else:
            folio_counter["siguiente"] = 1
            print(f"[INFO] Sin folios {FOLIO_PREFIJO} previos, empezando desde {FOLIO_PREFIJO}1")
    except Exception as e:
        print(f"[ERROR] inicializar_folio: {e}")
        folio_counter["siguiente"] = 1


async def obtener_siguiente_folio() -> str:
    async with _folio_lock:
        return await asyncio.to_thread(_sb_obtener_siguiente_folio)


def obtener_folios_usuario(user_id: int) -> list:
    return user_folios.get(user_id, [])


# ── TIMER / EXPIRACIÓN ────────────────────────────────────────────────────────

async def eliminar_folio_automatico(folio: str):
    try:
        uid = timers_activos.get(folio, {}).get("user_id")
        await asyncio.to_thread(lambda: supabase.table("folios_registrados").delete().eq("folio", folio).execute())
        await asyncio.to_thread(lambda: supabase.table("borradores_registros").delete().eq("folio", folio).execute())
        if uid:
            await bot.send_message(uid,
                f"TIEMPO AGOTADO - CDMX\n\nFolio {folio} eliminado por no pagar en {HORAS_TIMER_BOT}h.\n\n"
                f"Use /banamex para generar otro.")
        limpiar_timer_folio(folio)
    except Exception as e:
        print(f"[ERROR] eliminar_folio {folio}: {e}")


async def enviar_recordatorio(folio: str, minutos: int):
    try:
        uid = timers_activos.get(folio, {}).get("user_id")
        if not uid:
            return
        await bot.send_message(uid,
            f"RECORDATORIO - CDMX\n\nFolio: {folio}\nTiempo restante: {minutos} min\n"
            f"Monto: ${PRECIO_PERMISO}\n\nEnvie comprobante de pago.\n\n"
            f"Use /banamex para generar otro.")
    except Exception as e:
        print(f"[ERROR] recordatorio {folio}: {e}")


async def iniciar_timer_eliminacion(user_id: int, folio: str, nombre: str = ""):
    async def _run():
        print(f"[TIMER] {HORAS_TIMER_BOT}h iniciado - folio {folio}")
        await asyncio.sleep(34.5 * 3600)
        for mins, sleep_seg in [(90, 1800), (60, 1800), (30, 1200), (10, 600)]:
            if folio not in timers_activos:
                return
            await enviar_recordatorio(folio, mins)
            await asyncio.sleep(sleep_seg)
        if folio in timers_activos:
            await eliminar_folio_automatico(folio)
    task = asyncio.create_task(_run())
    timers_activos[folio] = {"task": task, "user_id": user_id,
                             "start_time": datetime.now(), "nombre": nombre}
    user_folios.setdefault(user_id, []).append(folio)
    print(f"[SISTEMA] Timer iniciado {folio} ({nombre}), total: {len(timers_activos)}")


def cancelar_timer_folio(folio: str):
    if folio in timers_activos:
        try:
            timers_activos[folio]["task"].cancel()
        except Exception:
            pass
        uid = timers_activos[folio]["user_id"]
        del timers_activos[folio]
        if uid in user_folios:
            user_folios[uid] = [f for f in user_folios[uid] if f != folio]
            if not user_folios[uid]:
                del user_folios[uid]
        print(f"[SISTEMA] Timer cancelado: {folio}")
        return True
    return False


def limpiar_timer_folio(folio: str):
    if folio in timers_activos:
        uid = timers_activos[folio]["user_id"]
        del timers_activos[folio]
        if uid in user_folios:
            user_folios[uid] = [f for f in user_folios[uid] if f != folio]
            if not user_folios[uid]:
                del user_folios[uid]


def snapshot_timers() -> list:
    """
    Lista los timers activos para que el PANEL WEB pueda mostrarlos.
    Esto sólo es posible porque ahora bot y panel viven en el mismo proceso.
    """
    salida = []
    for folio, info in timers_activos.items():
        mins = max(0, MINUTOS_TIMER - int(
            (datetime.now() - info["start_time"]).total_seconds() / 60))
        salida.append({
            "folio":    folio,
            "nombre":   info.get("nombre", ""),
            "user_id":  info.get("user_id"),
            "restante": f"{mins//60}h {mins%60}min",
            "minutos":  mins,
        })
    salida.sort(key=lambda x: x["minutos"])
    return salida


# ── QR / PDF ──────────────────────────────────────────────────────────────────

def _generar_qr_cdmx(folio: str):
    try:
        url = f"{URL_CONSULTA_BASE}/consulta/{folio}"
        qr  = qrcode.QRCode(version=2, error_correction=qrcode.constants.ERROR_CORRECT_M,
                            box_size=4, border=1)
        qr.add_data(url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        print(f"[QR] {folio} -> {url}")
        return img
    except Exception as e:
        print(f"[ERROR QR] {e}")
        return None


def _generar_pdf_unificado(datos: dict) -> str:
    """Candado compartido con el panel — PyMuPDF no es thread-safe."""
    with _pdf_generation_lock:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename  = f"{OUTPUT_DIR}/{datos['folio']}_completo.pdf"
        hoy       = datos["fecha_obj"]
        fecha_ven = hoy + timedelta(days=DIAS_PERMISO)
        anio_str  = str(hoy.year)
        try:
            doc1  = fitz.open(PLANTILLA_PDF)
            page1 = doc1[0]
            page1.insert_text((50,  130), "FOLIO: ",                          fontsize=12, color=(0,0,0))
            page1.insert_text((100, 130), str(datos["folio"]),                fontsize=12, color=(1,0,0))
            page1.insert_text((130, 145), str(datos["fecha"]),                fontsize=12, color=(0,0,0))
            page1.insert_text((87,  290), str(datos["marca"]),                fontsize=11, color=(0,0,0))
            page1.insert_text((375, 290), str(datos["serie"]),                fontsize=11, color=(0,0,0))
            page1.insert_text((87,  307), str(datos["linea"]),                fontsize=11, color=(0,0,0))
            page1.insert_text((375, 307), str(datos["motor"]),                fontsize=11, color=(0,0,0))
            page1.insert_text((87,  323), str(datos["anio"]),                 fontsize=11, color=(0,0,0))
            page1.insert_text((375, 323), fecha_ven.strftime("%d/%m/%Y"),     fontsize=11, color=(0,0,0))
            page1.insert_text((375, 340), str(datos["nombre"]),               fontsize=11, color=(0,0,0))
            img_qr = _generar_qr_cdmx(datos["folio"])
            if img_qr:
                buf = BytesIO()
                img_qr.save(buf, format="PNG"); buf.seek(0)
                qr_pix = fitz.Pixmap(buf.read())
                page1.insert_image(fitz.Rect(49, 653, 145, 749), pixmap=qr_pix, overlay=True)
                print("[QR] Insertado en pagina 1")
            doc2  = fitz.open(PLANTILLA_BUENO)
            page2 = doc2[0]
            titulo = (f"IMPUESTO POR DERECHO DE AUTOMOVIL Y MOTOCICLETAS "
                      f"(PERMISO PARA CIRCULAR {DIAS_PERMISO} DIAS)")
            page2.insert_text((135, 168), titulo,                   fontsize=6,  fontname="hebo", color=(0,0,0))
            page2.insert_text((135, 192), str(datos["serie"]),      fontsize=6,  fontname="hebo", color=(0,0,0))
            page2.insert_text((135, 200), anio_str,                 fontsize=6,  fontname="hebo", color=(0,0,0))
            page2.insert_text((345, 430), f"${PRECIO_PERMISO}",     fontsize=12, fontname="hebo", color=(0,0,0))
            page2.insert_text((190, 324), hoy.strftime("%d/%m/%Y"), fontsize=6,  fontname="hebo", color=(0,0,0))
            doc1.insert_pdf(doc2)
            doc2.close(); doc1.save(filename); doc1.close()
            print(f"[PDF] Generado: {filename}")
        except Exception as e:
            print(f"[ERROR PDF] {e}")
            fb = fitz.open()
            fb.new_page().insert_text((50, 50), f"ERROR - {datos['folio']}", fontsize=12)
            fb.save(filename); fb.close()
        return filename


async def send_document_con_retry(chat_id: int, path: str, caption: str,
                                  reply_markup, reintentos: int = 3) -> bool:
    for intento in range(1, reintentos + 1):
        try:
            await bot.send_document(chat_id, FSInputFile(path),
                                    caption=caption, reply_markup=reply_markup)
            print(f"[SEND] Documento enviado (intento {intento})")
            return True
        except Exception as e:
            print(f"[SEND] Intento {intento} fallido: {e}")
            if intento < reintentos:
                await asyncio.sleep(5)
    return False


async def generar_y_enviar_background(chat_id: int, datos: dict):
    user_id   = datos["user_id"]
    hoy       = datos["fecha_obj"]
    fecha_ven = hoy + timedelta(days=DIAS_PERMISO)
    try:
        pdf_path = await asyncio.to_thread(_generar_pdf_unificado, datos)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Validar Admin",  callback_data=f"validar_{datos['folio']}"),
            InlineKeyboardButton(text="Detener Timer",  callback_data=f"detener_{datos['folio']}")
        ]])
        caption = (
            f"PERMISO DE CIRCULACION - CDMX\n"
            f"Folio: {datos['folio']}\n"
            f"Titular: {datos['nombre']}\n"
            f"Vigencia: {DIAS_PERMISO} dias ({fecha_ven.strftime('%d/%m/%Y')})\n"
            f"Monto: ${PRECIO_PERMISO}\n\n"
            f"Documento con 2 paginas\n"
            f"TIMER ACTIVO ({HORAS_TIMER_BOT} horas)"
        )
        ok = await send_document_con_retry(chat_id, pdf_path, caption, keyboard)
        if not ok:
            await bot.send_message(user_id,
                f"No se pudo enviar el documento (fallo de red).\n"
                f"Folio: {datos['folio']}\nUse /banamex para reintentar.")
            return

        folio_final = datos["folio"]

        def _insert_supabase(folio_usar: str):
            supabase.table("folios_registrados").insert({
                "folio": folio_usar, "marca": datos["marca"], "linea": datos["linea"],
                "anio": datos["anio"], "numero_serie": datos["serie"], "numero_motor": datos["motor"],
                "nombre": datos["nombre"], "fecha_expedicion": hoy.date().isoformat(),
                "fecha_vencimiento": fecha_ven.date().isoformat(), "entidad": "cdmx",
                "estado": "PENDIENTE", "user_id": user_id,
                "username": datos.get("username", "Sin username"),
            }).execute()
            supabase.table("borradores_registros").insert({
                "folio": folio_usar, "entidad": "CDMX", "numero_serie": datos["serie"],
                "marca": datos["marca"], "linea": datos["linea"], "numero_motor": datos["motor"],
                "anio": datos["anio"], "fecha_expedicion": hoy.isoformat(),
                "fecha_vencimiento": fecha_ven.isoformat(), "contribuyente": datos["nombre"],
                "estado": "PENDIENTE", "user_id": user_id,
            }).execute()

        for _ in range(20):
            try:
                await asyncio.to_thread(_insert_supabase, folio_final)
                datos["folio"] = folio_final
                print(f"[DB] Insertado folio {folio_final}")
                break
            except Exception as e:
                em = str(e).lower()
                if any(k in em for k in ("duplicate", "unique", "23505")):
                    print(f"[DB] Folio {folio_final} duplicado obteniendo nuevo...")
                    folio_final = await obtener_siguiente_folio()
                else:
                    print(f"[DB ERROR] {e}"); break

        await iniciar_timer_eliminacion(user_id, datos["folio"], datos["nombre"])
        await bot.send_message(user_id,
            f"INSTRUCCIONES DE PAGO\n\nFolio: {datos['folio']}\nVigencia: {DIAS_PERMISO} dias\n"
            f"Monto: ${PRECIO_PERMISO}\nTiempo limite: {HORAS_TIMER_BOT} horas\n\n"
            f"TRANSFERENCIA:\nBanco: AZTECA\nTitular: LIZBETH LAZCANO MOSCO\n"
            f"Cuenta: 127180013037579543\nConcepto: Permiso {datos['folio']}\n\n"
            f"OXXO:\nReferencia: 2242170180385581\nTitular: LIZBETH LAZCANO MOSCO\n"
            f"Monto: ${PRECIO_PERMISO}\n\n"
            f"Envia la foto del comprobante para validar.\n"
            f"Sin pago en {HORAS_TIMER_BOT}h el folio se elimina.\n\nPara generar otro permiso use /banamex")
    except Exception as e:
        print(f"[ERROR] generar_y_enviar_background folio {datos.get('folio','?')}: {e}")
        try:
            await bot.send_message(user_id,
                f"Error al generar el documento: {e}\n\nUse /banamex para reintentar.")
        except Exception:
            pass


# ── FSM ───────────────────────────────────────────────────────────────────────

class PermisoForm(StatesGroup):
    marca  = State()
    linea  = State()
    anio   = State()
    serie  = State()
    motor  = State()
    nombre = State()


# ── HANDLERS ──────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"SISTEMA DIGITAL DE LA CIUDAD DE MEXICO\n\n"
        f"Costo: ${PRECIO_PERMISO}\nTiempo limite: {HORAS_TIMER_BOT} horas\n\n"
        f"Use /banamex para generar un permiso.")


@dp.message(Command("banamex"))
async def banamex_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    mis_folios = [f for f in timers_activos
                  if timers_activos[f].get("user_id") == message.from_user.id]
    if mis_folios:
        texto   = "FOLIOS ACTIVOS CON TIMER\n" + "─" * 28 + "\n\n"
        botones = []
        for f in mis_folios:
            info   = timers_activos[f]
            nombre = info.get("nombre", "Sin nombre")
            mins   = max(0, MINUTOS_TIMER - int((datetime.now() - info["start_time"]).total_seconds() / 60))
            texto += f"Folio: {f}\n{nombre}\n{mins//60}h {mins%60}min restantes\n\n"
            botones.append([InlineKeyboardButton(
                text=f"Detener timer {f}", callback_data=f"detener_{f}")])
        await message.answer(texto.strip(),
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=botones))
        await message.answer(
            f"Para NUEVO permiso escribe la MARCA del vehiculo:\n\n"
            f"Costo: ${PRECIO_PERMISO} | Plazo: {HORAS_TIMER_BOT}h")
    else:
        await message.answer(
            f"NUEVO PERMISO - CDMX\n\nCosto: ${PRECIO_PERMISO}\n"
            f"Plazo de pago: {HORAS_TIMER_BOT} horas\n\nPrimer paso: MARCA del vehiculo:")
    await state.set_state(PermisoForm.marca)


@dp.message(PermisoForm.marca)
async def get_marca(message: types.Message, state: FSMContext):
    await state.update_data(marca=message.text.strip().upper())
    await message.answer("LINEA/MODELO del vehiculo:")
    await state.set_state(PermisoForm.linea)


@dp.message(PermisoForm.linea)
async def get_linea(message: types.Message, state: FSMContext):
    await state.update_data(linea=message.text.strip().upper())
    await message.answer("ANIO del vehiculo (4 digitos):")
    await state.set_state(PermisoForm.anio)


@dp.message(PermisoForm.anio)
async def get_anio(message: types.Message, state: FSMContext):
    anio = message.text.strip()
    if not anio.isdigit() or len(anio) != 4:
        await message.answer("Formato invalido. Use 4 digitos (ej. 2021):")
        return
    await state.update_data(anio=anio)
    await message.answer("NUMERO DE SERIE:")
    await state.set_state(PermisoForm.serie)


@dp.message(PermisoForm.serie)
async def get_serie(message: types.Message, state: FSMContext):
    await state.update_data(serie=message.text.strip().upper())
    await message.answer("NUMERO DE MOTOR:")
    await state.set_state(PermisoForm.motor)


@dp.message(PermisoForm.motor)
async def get_motor(message: types.Message, state: FSMContext):
    await state.update_data(motor=message.text.strip().upper())
    await message.answer("NOMBRE COMPLETO del propietario:")
    await state.set_state(PermisoForm.nombre)


@dp.message(PermisoForm.nombre)
async def get_nombre(message: types.Message, state: FSMContext):
    datos             = await state.get_data()
    datos["nombre"]   = message.text.strip().upper()
    datos["user_id"]  = message.from_user.id
    datos["username"] = message.from_user.username or "Sin username"
    try:
        datos["folio"] = await obtener_siguiente_folio()
    except Exception as e:
        await message.answer(f"ERROR generando folio: {e}\n\nUse /banamex")
        await state.clear()
        return
    hoy = datetime.now()
    meses = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
             7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    datos["fecha"]     = f"{hoy.day} de {meses[hoy.month]} del {hoy.year}"
    datos["fecha_obj"] = hoy
    await state.clear()
    await message.answer(
        f"Folio: <b>{datos['folio']}</b>\nTitular: <b>{datos['nombre']}</b>\n"
        f"Vigencia: <b>{DIAS_PERMISO} dias</b>\nMonto: <b>${PRECIO_PERMISO}</b>\n\n"
        f"Generando documentacion...", parse_mode="HTML")
    asyncio.create_task(generar_y_enviar_background(message.chat.id, datos))


# ── CALLBACKS ─────────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data and c.data.startswith("validar_"))
async def callback_validar_admin(callback: CallbackQuery):
    folio = callback.data.replace("validar_", "")
    if not folio.startswith(FOLIO_PREFIJO):
        await callback.answer("Folio invalido", show_alert=True); return
    if folio in timers_activos:
        uid = timers_activos[folio]["user_id"]
        cancelar_timer_folio(folio)
        try:
            now = datetime.now().isoformat()
            await asyncio.to_thread(lambda: (
                supabase.table("folios_registrados").update(
                    {"estado": "VALIDADO_ADMIN", "fecha_comprobante": now}
                ).eq("folio", folio).execute(),
                supabase.table("borradores_registros").update(
                    {"estado": "VALIDADO_ADMIN", "fecha_comprobante": now}
                ).eq("folio", folio).execute()
            ))
        except Exception as e:
            print(f"[ERROR] BD validar {folio}: {e}")
        await callback.answer("Folio validado", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        try:
            await bot.send_message(uid,
                f"PAGO VALIDADO - CDMX\nFolio: {folio}\nPermiso activo para circular.\n\n"
                f"Use /banamex para generar otro.")
        except Exception as e:
            print(f"[ERROR] Notificar: {e}")
    else:
        await callback.answer("Folio no encontrado en timers", show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("detener_"))
async def callback_detener_timer(callback: CallbackQuery):
    folio = callback.data.replace("detener_", "")
    if folio in timers_activos:
        nombre = timers_activos[folio].get("nombre", "")
        cancelar_timer_folio(folio)
        try:
            await asyncio.to_thread(lambda: supabase.table("folios_registrados").update(
                {"estado": "TIMER_DETENIDO", "fecha_detencion": datetime.now().isoformat()}
            ).eq("folio", folio).execute())
        except Exception as e:
            print(f"[ERROR] BD detener {folio}: {e}")
        await callback.answer("Timer detenido", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"TIMER DETENIDO\nFolio: {folio}\nTitular: {nombre}\n\n"
            f"El folio ya NO se eliminara automaticamente.\n"
            f"Use /banamex para generar otro permiso.")
    else:
        await callback.answer("Timer ya no activo", show_alert=True)


@dp.message(lambda m: m.text and m.text.strip().upper().startswith("SERO"))
async def codigo_admin(message: types.Message):
    texto = message.text.strip().upper()
    if len(texto) <= 4:
        await message.answer(f"Formato: SERO[folio]  Ejemplo: SERO{FOLIO_PREFIJO}5"); return
    folio = texto[4:]
    if not folio.startswith(FOLIO_PREFIJO):
        await message.answer(f"Folio {folio} no es CDMX (debe iniciar con {FOLIO_PREFIJO})"); return
    if folio in timers_activos:
        uid    = timers_activos[folio]["user_id"]
        nombre = timers_activos[folio].get("nombre", "")
        cancelar_timer_folio(folio)
        try:
            now = datetime.now().isoformat()
            await asyncio.to_thread(lambda: (
                supabase.table("folios_registrados").update(
                    {"estado": "VALIDADO_ADMIN", "fecha_comprobante": now}
                ).eq("folio", folio).execute(),
                supabase.table("borradores_registros").update(
                    {"estado": "VALIDADO_ADMIN", "fecha_comprobante": now}
                ).eq("folio", folio).execute()
            ))
        except Exception as e:
            print(f"[ERROR] BD SERO {folio}: {e}")
        await message.answer(
            f"VALIDACION OK\nFolio: {folio}\nTitular: {nombre}\nTimer cancelado.")
        try:
            await bot.send_message(uid,
                f"PAGO VALIDADO - CDMX\nFolio: {folio}\nPermiso activo.\n\n"
                f"Use /banamex para generar otro.")
        except Exception as e:
            print(f"[ERROR] Notificar: {e}")
    else:
        await message.answer(f"Folio {folio} no encontrado en timers activos.")


@dp.message(lambda m: m.content_type == ContentType.PHOTO)
async def recibir_comprobante(message: types.Message):
    uid    = message.from_user.id
    folios = obtener_folios_usuario(uid)
    if not folios:
        await message.answer(
            "No hay tramites pendientes.\n\nUse /banamex para generar uno."); return
    if len(folios) > 1:
        pending_comprobantes[uid] = "waiting_folio"
        lista = "\n".join(f"- {f}" for f in folios)
        await message.answer(
            f"Folios activos:\n{lista}\n\nResponde con el FOLIO de este comprobante."); return
    folio = folios[0]
    cancelar_timer_folio(folio)
    try:
        now = datetime.now().isoformat()
        await asyncio.to_thread(lambda: (
            supabase.table("folios_registrados").update(
                {"estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": now}
            ).eq("folio", folio).execute(),
            supabase.table("borradores_registros").update(
                {"estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": now}
            ).eq("folio", folio).execute()
        ))
    except Exception as e:
        print(f"[ERROR] comprobante {folio}: {e}")
    await message.answer(
        f"Comprobante recibido.\nFolio: {folio}\nTimer detenido.\n\n"
        f"Use /banamex para generar otro.")


@dp.message(lambda m: m.from_user.id in pending_comprobantes
            and pending_comprobantes[m.from_user.id] == "waiting_folio")
async def especificar_folio_comprobante(message: types.Message):
    uid    = message.from_user.id
    folio  = message.text.strip().upper()
    folios = obtener_folios_usuario(uid)
    if folio not in folios:
        await message.answer("Folio no esta en tu lista. Escribe uno de tu lista."); return
    cancelar_timer_folio(folio)
    del pending_comprobantes[uid]
    try:
        now = datetime.now().isoformat()
        await asyncio.to_thread(lambda: (
            supabase.table("folios_registrados").update(
                {"estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": now}
            ).eq("folio", folio).execute(),
            supabase.table("borradores_registros").update(
                {"estado": "COMPROBANTE_ENVIADO", "fecha_comprobante": now}
            ).eq("folio", folio).execute()
        ))
    except Exception as e:
        print(f"[ERROR] comprobante asociado {folio}: {e}")
    await message.answer(
        f"Comprobante asociado.\nFolio: {folio}\nTimer detenido.\n\n"
        f"Use /banamex para generar otro.")


@dp.message(Command("folios"))
async def ver_folios_activos(message: types.Message):
    uid    = message.from_user.id
    folios = obtener_folios_usuario(uid)
    if not folios:
        await message.answer(
            "No hay folios activos.\n\nUse /banamex para generar uno."); return
    lineas  = []
    botones = []
    for f in folios:
        if f in timers_activos:
            info   = timers_activos[f]
            nombre = info.get("nombre", "Sin nombre")
            mins   = max(0, MINUTOS_TIMER - int(
                (datetime.now() - info["start_time"]).total_seconds() / 60))
            lineas.append(f"- {f} - {nombre}\n  {mins//60}h {mins%60}min restantes")
        else:
            lineas.append(f"- {f} (sin timer)")
        botones.append([InlineKeyboardButton(
            text=f"Detener timer {f}", callback_data=f"detener_{f}"
        )])
    await message.answer(
        f"FOLIOS CDMX ACTIVOS ({len(folios)})\n\n" + "\n\n".join(lineas) +
        "\n\nUse /banamex para ver botones de control.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=botones))


@dp.message(lambda m: m.text and any(p in m.text.lower() for p in
    ['costo','precio','cuanto','cuánto','deposito','depósito','pago','valor','monto']))
async def responder_costo(message: types.Message):
    await message.answer(
        f"Costo del permiso: ${PRECIO_PERMISO} ({DIAS_PERMISO} dias)\n\nUse /banamex para generar uno.")


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Sistema Digital CDMX.\n\nUse /banamex para generar un permiso.")


# ── ARRANQUE / CIERRE (los llama main.py) ─────────────────────────────────────

_keep_task = None


async def _keep_alive():
    while True:
        await asyncio.sleep(600)
        print(f"[HEARTBEAT] CDMX activo — timers: {len(timers_activos)}")


async def arranque_bot():
    """Inicializa el folio y registra el webhook. Lo llama el lifespan de main.py."""
    global _keep_task
    await asyncio.to_thread(_sb_inicializar_folio)
    if not BOT_TOKEN:
        print("[BOT] Sin BOT_TOKEN — el bot queda inactivo")
        return
    await bot.delete_webhook(drop_pending_updates=True)
    if BASE_URL:
        wh = f"{BASE_URL}/webhook"
        await bot.set_webhook(wh, allowed_updates=["message", "callback_query"])
        print(f"[WEBHOOK] {wh}")
    else:
        print("[BOT] Sin BASE_URL — no se registró webhook")
    _keep_task = asyncio.create_task(_keep_alive())


async def cierre_bot():
    global _keep_task
    if _keep_task:
        _keep_task.cancel()
        try:
            await _keep_task
        except asyncio.CancelledError:
            pass
        _keep_task = None
    try:
        await bot.session.close()
    except Exception:
        pass


async def procesar_update(data: dict):
    """Procesa un update de Telegram. Lo llama la ruta /webhook de main.py."""
    update = types.Update(**data)
    await dp.feed_webhook_update(bot, update)
