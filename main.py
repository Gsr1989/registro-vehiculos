from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file from datetime import datetime, timedelta from supabase import create_client, Client import fitz import os import io import qrcode import vonage

--- Configuración ---

app = Flask(name) app.secret_key = 'clave_muy_segura_123456'

Supabase

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co" SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwbXMiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTc0Mzk2Mzc1NSwiZXhwIjoyMDU5NTM5NzU1fQ.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws" supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

Vonage SMS

VONAGE_KEY = "3a43e40b" VONAGE_SECRET = "RF1Uvng7cxLTddp9" client_sms = vonage.Client(key=VONAGE_KEY, secret=VONAGE_SECRET) sms = vonage.Sms(client_sms)

def enviar_sms(numero, folio): mensaje = f"⚠️ AVISO: El permiso con folio {folio} ha vencido. Evita corralón y multas. Renueva hoy mismo. No respondas a este mensaje. Contáctanos por WhatsApp." response = sms.send_message({ "from": "ValidacionMX", "to": f"52{numero}", "text": mensaje, }) return response

---------------- Rutas ----------------

@app.route('/') def inicio(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST']) def login(): if request.method == 'POST': username = request.form['username'] password = request.form['password'] # Admin hardcode if username == 'Gsr89roja.' and password == 'serg890105': session['admin'] = True return redirect(url_for('admin')) # Usuario normal resp = supabase.table("verificaciondigitalcdmx").select("*") 
.eq("username", username).eq("password", password).execute() usuarios = resp.data if usuarios: session['user_id'] = usuarios[0]['id'] session['username'] = usuarios[0]['username'] return redirect(url_for('registro_usuario')) flash('Credenciales incorrectas', 'error') return render_template('login.html')

@app.route('/admin') def admin(): if 'admin' not in session: return redirect(url_for('login')) return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST']) def crear_usuario(): if 'admin' not in session: return redirect(url_for('login')) if request.method == 'POST': # ... código existente ... pass return render_template('crear_usuario.html')

@app.route('/registro_usuario', methods=['GET', 'POST']) def registro_usuario(): # ... código existente sin cambios para formulario usuario ... return render_template('registro_usuario.html')

@app.route('/registro_admin', methods=['GET', 'POST']) def registro_admin(): if 'admin' not in session: return redirect(url_for('login')) if request.method == 'POST': # Captura campos del formulario folio = request.form['folio'] marca = request.form['marca'] linea = request.form['linea'] anio = request.form['anio'] numero_serie = request.form['serie'] numero_motor = request.form['motor'] vigencia = int(request.form['vigencia']) numero_telefono = request.form['telefono']  # <-- NUEVO

# Validaciones
    existe = supabase.table("folios_registrados").select("*") \
        .eq("folio", folio).execute()
    if existe.data:
        flash('Error: el folio ya existe.', 'error')
        return render_template('registro_admin.html')

    # Fechas
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    # Graba registro con teléfono
    data = {
        "folio": folio,
        "marca": marca,
        "linea": linea,
        "anio": anio,
        "numero_serie": numero_serie,
        "numero_motor": numero_motor,
        "fecha_expedicion": fecha_expedicion.isoformat(),
        "fecha_vencimiento": fecha_vencimiento.isoformat(),
        "numero_telefono": numero_telefono  # <-- nuevo campo
    }
    supabase.table("folios_registrados").insert(data).execute()

    # Generación de PDF (igual que antes)
    doc = fitz.open("elbueno.pdf")
    page = doc[0]
    page.insert_text((135.02, 193.88), numero_serie, fontsize=6, fontname="helv", color=(0, 0, 0))
    page.insert_text((190, 324), fecha_expedicion.strftime('%d/%m/%Y'), fontsize=6, fontname="helv", color=(0, 0, 0))
    if not os.path.exists("documentos"):
        os.makedirs("documentos")
    doc.save(f"documentos/{folio}.pdf")

    flash('Folio registrado correctamente y PDF generado.', 'success')
    return render_template('exitoso.html', folio=folio, serie=numero_serie, fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))
return render_template('registro_admin.html')

@app.route('/enviar_alertas') def enviar_alertas(): if 'admin' not in session: return redirect(url_for('login')) hoy = datetime.now().date() registros = supabase.table("folios_registrados").select("*").execute().data for r in registros: venc = datetime.fromisoformat(r['fecha_vencimiento']).date() tel = r.get('numero_telefono') fol = r.get('folio') if venc <= hoy and tel: enviar_sms(tel, fol) flash('Mensajes enviados a los folios vencidos.', 'success') return redirect(url_for('admin_folios'))

@app.route('/consulta_folio', methods=['GET', 'POST']) def consulta_folio(): # ... código existente ... return render_template('consulta_folio.html')

@app.route('/admin_folios') def admin_folios(): # ... código existente para mostrar tabla ... return render_template('admin_folios.html', folios=folios, filtro=filtro, criterio=criterio, ordenar=ordenar, estado=estado_filtro, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)

@app.route('/editar_folio/<folio>', methods=['GET', 'POST']) def editar_folio(folio): # ... código existente ... return redirect(url_for('admin_folios'))

@app.route('/eliminar_folio', methods=['POST']) def eliminar_folio(): # ... código existente ... return redirect(url_for('admin_folios'))

@app.route('/descargar_pdf/<folio>') def descargar_pdf(folio): return send_file(f"documentos/{folio}.pdf", as_attachment=True)

@app.route('/logout') def logout(): session.clear() return redirect(url_for('login'))

if name == 'main': app.run(debug=True)

