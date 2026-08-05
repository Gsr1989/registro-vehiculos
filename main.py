"""
CDMX — FUSIÓN: panel web (Flask) + bot de Telegram (aiogram) en UN SOLO servicio.

Antes eran dos servicios de Render ($14/mes). Ahora es uno solo ($7/mes).

Cómo funciona:
  · FastAPI atiende /webhook (async) → se lo pasa al Dispatcher de aiogram
  · TODO lo demás (/login, /admin_folios, /consulta/..., /static, etc.) se lo
    pasa a tu app Flask con WSGIMiddleware, sin tocar una sola ruta

Orden IMPORTANTE: las rutas de FastAPI se declaran ANTES del mount("/"),
porque el mount atrapa todo lo que no se haya resuelto antes.

Start command en Render:
    gunicorn main:app -k uvicorn.workers.UvicornWorker -w 1 --timeout 120

El -w 1 es obligatorio: con más workers los timers del bot viven en memorias
separadas y se comportan raro.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Adaptador WSGI→ASGI. a2wsgi es el recomendado; si no está, cae al de Starlette.
try:
    from a2wsgi import WSGIMiddleware
except ImportError:  # pragma: no cover
    from starlette.middleware.wsgi import WSGIMiddleware

import config_cdmx as cfg
import bot_cdmx
import panel_cdmx


# ===================== LIFESPAN =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg.logger.info("=" * 60)
    cfg.logger.info("[SISTEMA] CDMX FUSIONADO v8.0 — panel + bot en un servicio")
    cfg.logger.info("=" * 60)

    # 1) Bot: inicializa contador de folios (serie 122) y registra el webhook
    try:
        await bot_cdmx.arranque_bot()
    except Exception as e:
        cfg.logger.error(f"[ARRANQUE BOT] {e}")

    # 2) Panel: scheduler de limpieza 48h (antes arrancaba al importar)
    try:
        panel_cdmx.iniciar_scheduler()
    except Exception as e:
        cfg.logger.error(f"[ARRANQUE SCHEDULER] {e}")

    cfg.logger.info(f"[SISTEMA] Listo — folio bot: {cfg.PREFIJO_BOT}{bot_cdmx.folio_counter['siguiente']}")
    cfg.logger.info(f"[SISTEMA] Panel en /  ·  Webhook en /webhook")

    yield

    cfg.logger.info("[CIERRE] Deteniendo servicios...")
    try:
        panel_cdmx.detener_scheduler()
    except Exception:
        pass
    try:
        await bot_cdmx.cierre_bot()
    except Exception:
        pass
    cfg.logger.info("[CIERRE] Listo")


app = FastAPI(
    lifespan=lifespan,
    title="CDMX — Panel + Bot",
    version="8.0",
    docs_url=None,       # sin /docs público
    redoc_url=None,
)


# ===================== WEBHOOK DE TELEGRAM =====================

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        await bot_cdmx.procesar_update(data)
        return {"ok": True}
    except Exception as e:
        cfg.logger.error(f"[WEBHOOK] {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)


# ===================== SALUD / DIAGNÓSTICO =====================
# El health del bot vivía en "/", pero ahí ahora va el login del panel.
# Se movió a /health y /status para no chocar.

@app.get("/health")
async def health():
    return {
        "ok":               True,
        "sistema":          "CDMX FUSIONADO v8.0",
        "panel":            "Flask montado en /",
        "bot":              "aiogram vía /webhook",
        "vigencia":         f"{cfg.DIAS_PERMISO} dias",
        "precio":           f"${cfg.PRECIO_PERMISO}",
        "timer_bot":        f"{cfg.HORAS_TIMER_BOT} horas",
        "limpieza_panel":   f"{cfg.HORAS_LIMITE_PAGO} horas",
        "timers_activos":   len(bot_cdmx.timers_activos),
        "folio_bot":        f"{cfg.PREFIJO_BOT}{bot_cdmx.folio_counter['siguiente']}",
        "prefijo_panel":    cfg.PREFIJO_PANEL,
    }


@app.get("/status")
async def status_detail():
    from datetime import datetime
    return {
        "sistema":        "CDMX FUSIONADO v8.0",
        "timers_activos": len(bot_cdmx.timers_activos),
        "folios":         bot_cdmx.snapshot_timers(),
        "folio_bot":      f"{cfg.PREFIJO_BOT}{bot_cdmx.folio_counter['siguiente']}",
        "timestamp":      datetime.now().isoformat(),
    }


# ===================== PANEL FLASK (va al final, atrapa todo lo demás) ========
# Cualquier ruta que no sea /webhook, /health o /status llega a Flask:
#   /  /login  /admin  /admin_folios  /consulta/<folio>  /static/...  etc.
app.mount("/", WSGIMiddleware(panel_cdmx.flask_app))


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
