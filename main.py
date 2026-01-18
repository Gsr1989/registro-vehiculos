from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz
import os
import vonage
import qrcode
from PIL import Image
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Supabase config
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vonage
VONAGE_KEY = "3a43e40b"
VONAGE_SECRET = "RF1Uvng7cxLTddp9"
vonage_client = vonage.Client(key=VONAGE_KEY, secret=VONAGE_SECRET)
sms = vonage.Sms(vonage_client)

# ENTIDAD FIJA PARA ESTE SISTEMA
ENTIDAD = "cdmx"

# URL BASE PARA QR DINÁMICOS
URL_CONSULTA_BASE = "https://semovidigitalgob.onrender.com"

# PLANTILLAS PDF
OUTPUT_DIR = "documentos"
PLANTILLA_PRINCIPAL = "cdmxdigital2025ppp.pdf"
PLANTILLA_SECUNDARIA = "elbueno.pdf"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def enviar_sms(numero: str, folio: str):
    mensaje = (
        f"⚠️ AVISO: El permiso con folio {folio} ha vencido. "
        "Evita corralón y multas. Renueva hoy mismo. "
        "No respondas a este mensaje. Contáctanos por WhatsApp."
    )
    return sms.send_message({
        "from": "ValidacionMX",
        "to": f"52{numero}",
        "text": mensaje,
    })

# =========================================
# 🔥 GENERACIÓN DE QR DINÁMICO (DEL BOT)
# =========================================
def generar_qr_dinamico_cdmx(folio):
    """Genera QR con URL dinámica para consulta del folio"""
    try:
        url_directa = f"{URL_CONSULTA_BASE}/consulta/{folio}"

        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1
        )
        qr.add_data(url_directa)
        qr.make(fit=True)

        img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        print(f"[QR CDMX] Generado para folio {folio} -> {url_directa}")
        return img_qr, url_directa

    except Exception as e:
        print(f"[ERROR QR CDMX] {e}")
        return None, None

# =========================================
# 🔥 GENERACIÓN AUTOMÁTICA DE FOLIOS (122 + CONSECUTIVO)
# =========================================
def generar_folio_automatico():
    """
    Genera folio con prefijo fijo 122 + consecutivo
    Formato: 1221, 1222, 1223... 12210, 12211... infinito
    Intenta 100,000 veces hasta encontrar uno disponible
    """
    PREFIJO = "122"
    
    # 1. Buscar todos los folios que empiezan con 122
    todos = supabase.table("folios_registrados")\
        .select("folio")\
        .execute().data
    
    consecutivos = []
    for f in todos:
        folio_str = str(f['folio'])
        if folio_str.startswith(PREFIJO):
            try:
                # Extraer el número después de "122"
                # "1221" → 1, "12210" → 10, "122100" → 100
                num = int(folio_str[3:])
                consecutivos.append(num)
            except:
                pass
    
    # 2. Si no hay folios, empezar en 1
    if not consecutivos:
        consecutivo_actual = 1
    else:
        # Si hay folios, empezar desde el más alto + 1
        consecutivo_actual = max(consecutivos) + 1
    
    # 3. Intentar hasta 100,000 veces encontrar folio disponible
    for intento in range(100000):
        folio_candidato = f"{PREFIJO}{consecutivo_actual}"
        
        # Verificar si existe en BD
        existe = supabase.table("folios_registrados")\
            .select("folio")\
            .eq("folio", folio_candidato)\
            .execute().data
        
        if not existe:
            # ¡FOLIO DISPONIBLE!
            print(f"[FOLIO GENERADO] {folio_candidato} (intento {intento + 1})")
            return folio_candidato
        
        # Si está ocupado, probar el siguiente
        consecutivo_actual += 1
    
    # Si después de 100,000 intentos no encontró nada
    raise Exception("No se pudo generar folio después de 100,000 intentos")

# =========================================
# 🔥 GENERACIÓN PDF UNIFICADO (2 PÁGINAS EN 1 ARCHIVO)
# =========================================
def generar_pdf_unificado_cdmx(datos: dict) -> str:
    """
    Genera UN SOLO PDF con ambas plantillas (2 páginas)
    Página 1: cdmxdigital2025ppp.pdf con todos los datos + QR
    Página 2: elbueno.pdf con serie y fecha
    """
    filename = f"{OUTPUT_DIR}/{datos['folio']}.pdf"
    
    try:
        # ===== PÁGINA 1: PLANTILLA PRINCIPAL =====
        if not os.path.exists(PLANTILLA_PRINCIPAL):
            print(f"[WARNING] No se encuentra {PLANTILLA_PRINCIPAL}, usando plantilla simple")
            doc_principal = fitz.open(PLANTILLA_SECUNDARIA)
        else:
            doc_principal = fitz.open(PLANTILLA_PRINCIPAL)
        
        page_principal = doc_principal[0]

        # Insertar datos en coordenadas específicas (del bot)
        page_principal.insert_text((50, 130), "FOLIO: ", fontsize=12, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((100, 130), datos["folio"], fontsize=12, fontname="helv", color=(1, 0, 0))
        page_principal.insert_text((130, 145), datos["fecha"], fontsize=12, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((87, 290), datos["marca"], fontsize=11, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((375, 290), datos["numero_serie"], fontsize=11, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((87, 307), datos["linea"], fontsize=11, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((375, 307), datos["numero_motor"], fontsize=11, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((87, 323), datos["anio"], fontsize=11, fontname="helv", color=(0, 0, 0))
        page_principal.insert_text((375, 323), datos["vigencia"], fontsize=11, fontname="helv", color=(0, 0, 0))
        
        # Insertar nombre si existe
        if "nombre" in datos and datos["nombre"]:
            page_principal.insert_text((375, 340), datos["nombre"], fontsize=11, fontname="helv", color=(0, 0, 0))
            print(f"[PDF] Nombre insertado: {datos['nombre']}")

        # QR dinámico
        img_qr, url_qr = generar_qr_dinamico_cdmx(datos["folio"])

        if img_qr:
            buf = BytesIO()
            img_qr.save(buf, format="PNG")
            buf.seek(0)
            qr_pix = fitz.Pixmap(buf.read())

            # Coordenadas del QR (del bot)
            x_qr = 49
            y_qr = 653
            ancho_qr = 96
            alto_qr = 96

            page_principal.insert_image(
                fitz.Rect(x_qr, y_qr, x_qr + ancho_qr, y_qr + alto_qr),
                pixmap=qr_pix,
                overlay=True
            )
            print(f"[QR CDMX] Insertado en página 1 en coordenadas ({x_qr}, {y_qr})")

        # ===== PÁGINA 2: PLANTILLA SECUNDARIA =====
        if os.path.exists(PLANTILLA_SECUNDARIA):
            doc_secundario = fitz.open(PLANTILLA_SECUNDARIA)
            page_secundaria = doc_secundario[0]
            
            # Insertar datos en coordenadas específicas (del Flask original)
            page_secundaria.insert_text(
                (135.02, 193.88), 
                datos["numero_serie"], 
                fontsize=6, 
                fontname="helv", 
                color=(0, 0, 0)
            )
            page_secundaria.insert_text(
                (190, 324), 
                datos["fecha_expedicion"].strftime('%d/%m/%Y'), 
                fontsize=6, 
                fontname="helv", 
                color=(0, 0, 0)
            )

            # ===== UNIR AMBAS PÁGINAS =====
            doc_principal.insert_pdf(doc_secundario)
            doc_secundario.close()
            print(f"[PDF UNIFICADO] Página 2 agregada desde {PLANTILLA_SECUNDARIA}")
        else:
            print(f"[WARNING] No se encuentra {PLANTILLA_SECUNDARIA}, PDF tendrá solo 1 página")

        doc_principal.save(filename)
        doc_principal.close()
        
        print(f"[PDF UNIFICADO CDMX] ✅ Generado: {filename}")
        
    except Exception as e:
        print(f"[ERROR] Generando PDF unificado CDMX: {e}")
        # Crear PDF de respaldo con error
        doc_fallback = fitz.open()
        page = doc_fallback.new_page()
        page.insert_text((50, 50), f"ERROR - Folio: {datos['folio']}", fontsize=12)
        page.insert_text((50, 80), f"Contacte al soporte técnico", fontsize=10)
        doc_fallback.save(filename)
        doc_fallback.close()
    
    return filename

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Admin hardcode
        if username == 'Serg890105tm3' and password == 'Serg890105tm3':
            session['admin'] = True
            session['username'] = 'Serg890105tm3'
            return redirect(url_for('admin'))

        # Usuario normal
        resp = supabase.table("verificaciondigitalcdmx")\
            .select("*")\
            .eq("username", username)\
            .eq("password", password)\
            .execute()

        if resp.data:
            session['user_id'] = resp.data[0]['id']
            session['username'] = resp.data[0]['username']
            session['admin'] = False
            return redirect(url_for('registro_usuario'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
    
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        folios = int(request.form['folios'])
        
        existe = supabase.table("verificaciondigitalcdmx")\
            .select("id")\
            .eq("username", username)\
            .execute()
        
        if existe.data:
            flash('Error: el nombre de usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": username,
                "password": password,
                "folios_asignac": folios,
                "folios_usados": 0
            }).execute()
            flash('Usuario creado exitosamente.', 'success')
    
    return render_template('crear_usuario.html')

# =========================================
# 🔥 REGISTRO USUARIO - FOLIO AUTOMÁTICO + NOMBRE
# =========================================
@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if not session.get('username'):
        return redirect(url_for('login'))
    
    # Bloquear si es admin
    if session.get('admin'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        # ✅ GENERAR FOLIO AUTOMÁTICO (USUARIOS)
        try:
            folio = generar_folio_automatico()
        except Exception as e:
            flash(f'Error al generar folio: {e}', 'error')
            return redirect(url_for('registro_usuario'))
        
        marca = request.form['marca'].upper()
        linea = request.form['linea'].upper()
        anio = request.form['anio']
        numero_serie = request.form['serie'].upper()
        numero_motor = request.form['motor'].upper()
        nombre = request.form['nombre'].upper()  # ✅ CAPTURAR NOMBRE
        vigencia_dias = int(request.form.get('vigencia', 30))
        fecha_expedicion_str = request.form.get('fecha_expedicion')

        try:
            fecha_expedicion = datetime.strptime(fecha_expedicion_str, "%Y-%m-%d")
        except:
            fecha_expedicion = datetime.now()

        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia_dias)

        # Obtener datos del usuario
        usr_data = supabase.table("verificaciondigitalcdmx")\
            .select("folios_asignac, folios_usados")\
            .eq("username", session['username']).execute().data

        if not usr_data:
            flash('Usuario no válido.', 'error')
            return redirect(url_for('login'))

        usr = usr_data[0]
        
        # Verificar si tiene folios disponibles
        if usr['folios_asignac'] - usr['folios_usados'] <= 0:
            flash('No tienes folios disponibles. Contacta al administrador.', 'error')
            return redirect(url_for('registro_usuario'))

        # Preparar datos para PDF unificado
        hoy = fecha_expedicion
        meses = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        
        datos_pdf = {
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha": f"{hoy.day} de {meses[hoy.month]} del {hoy.year}",
            "vigencia": fecha_vencimiento.strftime("%d/%m/%Y"),
            "fecha_expedicion": fecha_expedicion,
            "nombre": nombre  # ✅ NOMBRE
        }

        # Insertar en BD CON REGISTRO DE USUARIO ✅✅✅
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "nombre": nombre,
            "fecha_expedicion": fecha_expedicion.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat(),
            "entidad": "cdmx",
            "creado_por": session['username']  # ✅ NUEVA LÍNEA
        }).execute()

        # ✅ GENERAR PDF UNIFICADO (2 PÁGINAS)
        try:
            generar_pdf_unificado_cdmx(datos_pdf)
        except Exception as e:
            flash(f"Error al generar PDF: {e}", 'error')

        # Actualizar contador de folios usados
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": usr['folios_usados'] + 1
        }).eq("username", session['username']).execute()

        flash('Folio registrado correctamente.', 'success')
        return render_template('exitoso.html', 
                             folio=folio, 
                             serie=numero_serie, 
                             fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))

    # GET - Obtener datos de folios del usuario
    datos = supabase.table("verificaciondigitalcdmx")\
        .select("folios_asignac, folios_usados")\
        .eq("username", session['username']).execute().data

    if not datos:
        flash("No se encontró información de folios.", "error")
        return redirect(url_for('login'))
    
    usr = datos[0]
    folios_asignados = usr['folios_asignac']
    folios_usados = usr['folios_usados']
    folios_disponibles = folios_asignados - folios_usados
    porcentaje = (folios_usados / folios_asignados * 100) if folios_asignados > 0 else 0

    return render_template('registro_usuario.html', 
                         folios_asignados=folios_asignados,
                         folios_usados=folios_usados,
                         folios_disponibles=folios_disponibles,
                         porcentaje=porcentaje)

# =========================================
# 🔥 HISTORIAL DE PERMISOS DEL USUARIO
# =========================================
@app.route('/mis_permisos')
def mis_permisos():
    if not session.get('username') or session.get('admin'):
        flash('Acceso denegado.', 'error')
        return redirect(url_for('login'))
    
    # Buscar todos los folios generados por este usuario
    permisos = supabase.table("folios_registrados")\
        .select("*")\
        .eq("creado_por", session['username'])\
        .order("fecha_expedicion", desc=True)\
        .execute().data
    
    # Procesar datos
    hoy = datetime.now()
    for p in permisos:
        try:
            fe = datetime.fromisoformat(p['fecha_expedicion'])
            fv = datetime.fromisoformat(p['fecha_vencimiento'])
            p['fecha_formateada'] = fe.strftime('%d/%m/%Y')
            p['hora_formateada'] = fe.strftime('%H:%M:%S')
            p['estado'] = "VIGENTE" if hoy <= fv else "VENCIDO"
        except:
            p['fecha_formateada'] = 'Error'
            p['hora_formateada'] = 'Error'
            p['estado'] = 'ERROR'
    
    # Obtener stats del usuario
    usr_data = supabase.table("verificaciondigitalcdmx")\
        .select("folios_asignac, folios_usados")\
        .eq("username", session['username']).execute().data[0]
    
    return render_template('mis_permisos.html', 
                         permisos=permisos,
                         total_generados=len(permisos),
                         folios_asignados=usr_data['folios_asignac'],
                         folios_usados=usr_data['folios_usados'])

# =========================================
# 🔥 REGISTRO ADMIN - FOLIO MANUAL + NOMBRE
# =========================================
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # ✅ CAPTURAR FOLIO MANUAL (ADMIN)
        folio = request.form['folio'].strip().upper()
        
        # Validar que el folio no exista
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_admin'))
        
        marca = request.form['marca'].upper()
        linea = request.form['linea'].upper()
        anio = request.form['anio']
        numero_serie = request.form['serie'].upper()
        numero_motor = request.form['motor'].upper()
        nombre = request.form['nombre'].upper()  # ✅ CAPTURAR NOMBRE
        telefono = request.form.get('telefono', '0')
        vigencia_dias = int(request.form['vigencia'])

        # Fecha de expedición editable
        try:
            fecha_exp_str = request.form.get('fecha_expedicion', '')
            fecha_expedicion = datetime.strptime(fecha_exp_str, '%Y-%m-%d') if fecha_exp_str else datetime.now()
        except ValueError:
            fecha_expedicion = datetime.now()

        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia_dias)

        # Preparar datos para PDF unificado
        hoy = fecha_expedicion
        meses = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
            5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
            9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        
        datos_pdf = {
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha": f"{hoy.day} de {meses[hoy.month]} del {hoy.year}",
            "vigencia": fecha_vencimiento.strftime("%d/%m/%Y"),
            "fecha_expedicion": fecha_expedicion,
            "nombre": nombre  # ✅ NOMBRE
        }

        # Insertar en Supabase CON CREADO_POR ✅✅✅
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "nombre": nombre,
            "numero_telefono": telefono,
            "fecha_expedicion": fecha_expedicion.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat(),
            "entidad": ENTIDAD,
            "creado_por": "ADMIN"  # ✅ NUEVA LÍNEA
        }).execute()

        # ✅ GENERAR PDF UNIFICADO (2 PÁGINAS)
        try:
            generar_pdf_unificado_cdmx(datos_pdf)
        except Exception as e:
            flash(f"Error al generar PDF: {e}", 'error')

        flash('Folio admin registrado.', 'success')
        return render_template('exitoso.html',
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))

    return render_template('registro_admin.html')

@app.route('/consulta_folio', methods=['GET','POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio'].strip().upper()
        registros = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not registros:
            resultado = {"estado":"NO SE ENCUENTRA REGISTRADO","color":"rojo","folio":folio}
        else:
            r = registros[0]
            fexp = datetime.fromisoformat(r['fecha_expedicion'])
            fven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fven else "VENCIDO"
            color = "verde" if estado=="VIGENTE" else "cafe"
            resultado = {
                "estado": estado,
                "color": color,
                "folio": folio,
                "fecha_expedicion": fexp.strftime('%d/%m/%Y'),
                "fecha_vencimiento": fven.strftime('%d/%m/%Y'),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor'],
                "entidad": r.get('entidad', '')
            }
        return render_template('resultado_consulta.html', resultado=resultado)
    return render_template('consulta_folio.html')

@app.route('/admin_folios')
def admin_folios():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    filtro = request.args.get('filtro','').strip()
    criterio = request.args.get('criterio','folio')
    ordenar = request.args.get('ordenar','desc')
    estado_filtro = request.args.get('estado','todos')
    fecha_inicio = request.args.get('fecha_inicio','')
    fecha_fin = request.args.get('fecha_fin','')
    query = supabase.table("folios_registrados").select("*")
    if filtro:
        if criterio=="folio":
            query = query.ilike("folio",f"%{filtro}%")
        elif criterio=="numero_serie":
            query = query.ilike("numero_serie",f"%{filtro}%")
    registros = query.execute().data or []
    hoy = datetime.now()
    filtrados=[]
    for fol in registros:
        try:
            fe = datetime.fromisoformat(fol['fecha_expedicion'])
            fv = datetime.fromisoformat(fol['fecha_vencimiento'])
        except:
            continue
        fol["estado"] = "VIGENTE" if hoy<=fv else "VENCIDO"
        if estado_filtro=="vigente" and fol["estado"]!="VIGENTE": continue
        if estado_filtro=="vencido" and fol["estado"]!="VENCIDO": continue
        if fecha_inicio:
            try:
                fi = datetime.strptime(fecha_inicio,"%Y-%m-%d")
                if fe<fi: continue
            except: pass
        if fecha_fin:
            try:
                ff = datetime.strptime(fecha_fin,"%Y-%m-%d")
                if fe>ff: continue
            except: pass
        filtrados.append(fol)
    filtrados.sort(key=lambda x:x['fecha_expedicion'],reverse=(ordenar=='desc'))
    return render_template('admin_folios.html',
        folios=filtrados,
        filtro=filtro,
        criterio=criterio,
        ordenar=ordenar,
        estado=estado_filtro,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )

@app.route('/enviar_sms_manual', methods=['POST'])
def enviar_sms_manual():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    folio = request.form['folio']
    telefono = request.form.get('telefono')
    try:
        enviar_sms(telefono, folio)
        flash(f"SMS enviado al {telefono} para el folio {folio}.", "success")
    except Exception as e:
        flash(f"Error al enviar SMS: {e}", "error")
    return redirect(url_for('admin_folios'))

@app.route('/enviar_alertas', methods=['POST'])
def enviar_alertas():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    hoy = datetime.now().date()
    enviados = 0
    for r in supabase.table("folios_registrados").select("*").execute().data:
        try:
            if datetime.fromisoformat(r['fecha_vencimiento']).date()<=hoy and r.get('numero_telefono'):
                enviar_sms(r['numero_telefono'], r['folio'])
                enviados += 1
        except:
            pass
    flash(f"Se enviaron {enviados} SMS de alerta.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/editar_folio/<folio>', methods=['GET','POST'])
def editar_folio(folio):
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    if request.method=='POST':
        data = {
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": request.form['serie'],
            "numero_motor": request.form['motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento']
        }
        supabase.table("folios_registrados").update(data).eq("folio",folio).execute()
        flash("Folio actualizado correctamente.","success")
        return redirect(url_for('admin_folios'))
    resp = supabase.table("folios_registrados").select("*").eq("folio",folio).execute().data
    if resp:
        return render_template('editar_folio.html', folio=resp[0])
    flash("Folio no encontrado.","error")
    return redirect(url_for('admin_folios'))

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    folio = request.form['folio']
    supabase.table("folios_registrados").delete().eq("folio",folio).execute()
    flash("Folio eliminado correctamente.","success")
    return redirect(url_for('admin_folios'))

@app.route('/eliminar_folios_masivo', methods=['POST'])
def eliminar_folios_masivo():
    if not session.get('admin'):
        flash('Acceso denegado. Solo administradores.', 'error')
        return redirect(url_for('login'))
    
    folios = request.form.getlist('folios')
    if not folios:
        flash("No seleccionaste ningún folio.", "error")
        return redirect(url_for('admin_folios'))
    try:
        supabase.table("folios_registrados").delete().in_("folio", folios).execute()
        flash(f"Se eliminaron {len(folios)} folios correctamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar folios: {e}", "error")
    return redirect(url_for('admin_folios'))

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    # Busca el PDF unificado
    pdf_path = f"{OUTPUT_DIR}/{folio}.pdf"
    
    if not os.path.exists(pdf_path):
        flash("PDF no existe para este folio.", "error")
        return redirect(request.referrer or url_for('admin_folios'))
    
    return send_file(pdf_path, as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/consulta/<folio>')
def consulta_folio_directo(folio):
    """Ruta para QR dinámicos - versión flexible"""
    
    # Buscar sin filtro de entidad primero
    row = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
    
    if not row:
        return render_template("resultado_consulta.html", resultado={
            "estado": "NO SE ENCUENTRA REGISTRADO",
            "folio": folio
        })
    
    r = row[0]
    fe = datetime.fromisoformat(r['fecha_expedicion'])
    fv = datetime.fromisoformat(r['fecha_vencimiento'])
    estado = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
    
    resultado = {
        "estado": estado,
        "folio": folio,
        "fecha_expedicion": fe.strftime("%d/%m/%Y"),
        "fecha_vencimiento": fv.strftime("%d/%m/%Y"),
        "marca": r['marca'],
        "linea": r['linea'],
        "año": r['anio'],
        "numero_serie": r['numero_serie'],
        "numero_motor": r['numero_motor'],
        "entidad": r.get('entidad', '')
    }
    
    return render_template("resultado_consulta.html", resultado=resultado)
    
if __name__ == '__main__':
    app.run(debug=True)
