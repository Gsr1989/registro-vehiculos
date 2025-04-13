desde flask importar Flask, render_template, solicitud, redirigir, url_para, flash, sesión desde datetime importar datetime, timedelta desde supabase importar create_client, Cliente

aplicación = Flask(nombre)

@app.route('/generar_pdf/<folio>') def generar_pdf(folio): resultado = supabase.table("folios_registrados").select("*").eq("folio", folio).execute() if not resultado.data: flash("Folio no encontrado.", "error") return redirección(url_for('admin_folios'))

datos = resultado.data[0] plantilla = "cdmxdigital20252.pdf" doc = fitz.open(plantilla) page = doc[0]

Página.insertar_texto((180.47, 291.00), folio, tamaño de fuente=10) Página.insertar_texto((159.67, 233.59), folio[-4:], tamaño de fuente=10) Página.insertar_texto((247.05, 262.15), datetime.fromisoformat(datos['fecha_expedicion']).strftime("%d DE %B DE %Y"), tamaño de fuente=10) Página.insertar_texto((175.45, 542.22), datos['marca'], tamaño de fuente=10) Página.insertar_texto((283, 542.22), datos['linea'], tamaño de fuente=10) Página.insertar_texto((390, 542.22), datos['anio'], tamaño de fuente=10) página.insertar_texto((175.45, 650.22), datos['numero_serie'], tamaño de fuente=10) página.insertar_texto((283, 650.22), datos['numero_motor'], tamaño de fuente=10) página.insertar_texto((390, 650.22), datetime.fromisoformat(datos['fecha_vencimiento']).strftime("%d/%m/%Y"), tamaño de fuente=10) página.insertar_texto((390, 625.22), "DOCUMENTO DIGITAL", tamaño de fuente=10)

qr_data = f"https://validacion.cdmx.mx/folio/{folio}" qr_img = qrcode.make(qr_data) qr_path = f"temp_qr_{folio}.png" qr_img.save(qr_path) page.insert_image(fitz.Rect(460, 720, 560, 820), filename=qr_path)

salida = f"static/permiso_{folio}.pdf" doc.save(salida) doc.close()

si os.path.exists(qr_path): os.remove(qr_path)

retorno redireccionamiento(url_for('static', filename=f'permiso_{folio}.pdf'))

app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co" SUPABASE_CLAVE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws" supabase: Cliente = crear_cliente(SUPABASE_URL, SUPABASE_CLAVE)

@app.route('/') def inicio(): return redirect(url_for('login'))

@app.route('/login', métodos=['GET', 'POST']) def login(): si solicitud.método == 'POST': nombre de usuario = solicitud.formulario['nombre de usuario'] contraseña = solicitud.formulario['contraseña']

si nombre de usuario == 'Gsr89roja.' y contraseña == 'serg890105': sesión['admin'] = True return redirect(url_for('admin'))

respuesta = supabase.table("verificaciondigitalcdmx").select("*").eq("nombreusuario", nombreusuario).eq("contraseña", contraseña).execute()
usuarios = respuesta.datos

Si usuarios:
    sesión['user_id'] = usuarios[0]['id']
    sesión['nombre de usuario'] = usuarios[0]['nombre de usuario']
    devolver redirección(url_for('registro_usuario'))
demás:
    flash('Credenciales incorrectas', 'error')

devolver render_template('login.html')

@app.route('/admin') def admin(): si 'admin' no está en sesión: return redirect(url_for('login')) return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST']) def crear_usuario(): si 'admin' no está en sesión: return redirect(url_for('login'))

si solicitud.método == 'POST': nombre de usuario = solicitud.formulario['nombre de usuario'] contraseña = solicitud.formulario['contraseña'] folios = int(solicitud.formulario['folios'])

existe = supabase.table("verificaciondigitalcdmx").select("id").eq("nombreusuario", nombreusuario).execute()
si existe.data:
    flash('Error: el nombre de usuario ya existe.', 'error')
    devolver render_template('crear_usuario.html')

datos = {
    "nombre de usuario": nombre de usuario,
    "contraseña": contraseña,
    "folios_asignac": folios,
    "folios_usados": 0
}
supabase.table("verificaciondigitalcdmx").insert(data).execute()
flash('Usuario creado exitosamente.', 'success')

devolver render_template('crear_usuario.html')

@app.route('/registro_usuario', methods=['GET', 'POST']) def registro_usuario(): si 'user_id' no está en sesión: return redirect(url_for('login'))

user_id = sesión['user_id']

si solicitud.método == 'POST': folio = solicitud.formulario['folio'] marca = solicitud.formulario['marca'] linea = solicitud.formulario['linea'] anio = solicitud.formulario['anio'] numero_serie = solicitud.formulario['serie'] numero_motor = solicitud.formulario['motor'] vigencia = int(solicitud.formulario['vigencia'])

existente = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
si existente.data:
    flash('Error: el folio ya existe.', 'error')
    devolver redirección(url_for('registro_usuario'))

usuario_data = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
si no es usuario_data.data:
    flash("No se pudo obtener la información del usuario.", "error")
    devolver redirección(url_for('registro_usuario'))

folios = usuario_data.data[0]
restantes = folios['folios_asignac'] - folios['folios_usados']
si restantes <= 0:
    flash("No tienes folios disponibles para registrar.", "error")
    devolver redirección(url_for('registro_usuario'))

fecha_expedicion = fechahora.ahora()
fecha_vencimiento = fecha_expedicion + timedelta(dias=vigencia)

datos = {
    "folio": folio,
    "marca": marca,
    "línea": línea,
    "anio": anio,
    "numero_serie": numero_serie,
    "numero_motor": numero_motor,
    "fecha_expedicion": fecha_expedicion.isoformat(),
    "fecha_vencimiento": fecha_vencimiento.isoformat()
}

supabase.table("folios_registrados").insert(data).execute()
supabase.table("verificaciondigitalcdmx").update({
    "folios_usados": folios["folios_usados"] + 1
}).eq("id", id_usuario).execute()
flash("Folio registrado correctamente.", "éxito")
devolver redirección(url_for('registro_usuario'))

respuesta = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute() folios_info = respuesta.data[0] if respuesta.data else {} return render_template("registro_usuario.html", folios_info=folios_info)

@app.route('/registro_admin', methods=['GET', 'POST']) def registro_admin(): si 'admin' no está en sesión: return redirect(url_for('login'))

si solicitud.método == 'POST': folio = solicitud.formulario['folio'] marca = solicitud.formulario['marca'] linea = solicitud.formulario['linea'] anio = solicitud.formulario['anio'] numero_serie = solicitud.formulario['serie'] numero_motor = solicitud.formulario['motor'] vigencia = int(solicitud.formulario['vigencia'])

existente = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
si existente.data:
    flash('Error: el folio ya existe.', 'error')
    devolver render_template('registro_admin.html')

fecha_expedicion = fechahora.ahora()
fecha_vencimiento = fecha_expedicion + timedelta(dias=vigencia)

datos = {
    "folio": folio,
    "marca": marca,
    "línea": línea,
    "anio": anio,
    "numero_serie": numero_serie,
    "numero_motor": numero_motor,
    "fecha_expedicion": fecha_expedicion.isoformat(),
    "fecha_vencimiento": fecha_vencimiento.isoformat()
}

supabase.table("folios_registrados").insert(data).execute()
flash('Folio registrado correctamente.', 'éxito')

devolver render_template('registro_admin.html')

@app.route('/admin_folios', methods=['GET']) def admin_folios(): si 'admin' no está en sesión: return redirect(url_for('login'))

filtro = request.args.get('filtro', '').strip() criterio = request.args.get('criterio', 'folio') ordenar = request.args.get('ordenar', 'desc') estado_filtro = request.args.get('estado', 'todos') fecha_inicio = request.args.get('fecha_inicio', '') fecha_fin = request.args.get('fecha_fin', '')

consulta = supabase.table("folios_registrados").select("*")

if filtro: if criterio == "folio": consulta = query.ilike("folio", f"%{filtro}%") elif criterio == "numero_serie": consulta = query.ilike("numero_serie", f"%{filtro}%")

resultado = query.execute() folios = resultado.data o []

hoy = datetime.now() filtrados = []

para folio en folios: prueba: fecha_exp = datetime.fromisoformat(folio.get("fecha_expedicion", "")) fecha_ven = datetime.fromisoformat(folio.get("fecha_vencimiento", "")) excepto: continuar

estado = "VIGENTE" if hoy <= fecha_ven else "VENCIDO"
folio["estado"] = estado

if estado_filtro == "vigente" y estado != "VIGENTE":
    continuar
if estado_filtro == "vencido" y estado != "VENCIDO":
    continuar

si fecha_inicio:
    intentar:
        fi = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        si fecha_exp < fi:
            continuar
    excepto:
        aprobar
si fecha_fin:
    intentar:
        ff = datetime.strptime(fecha_fin, "%Y-%m-%d")
        si fecha_exp > ff:
            continuar
    excepto:
        aprobar

filtrados.append(folio)

filtrados.sort(key=lambda x: x.get("fecha_expedicion", ""), reverse=(ordenar == "desc"))

return render_template( "admin_folios.html", folios=filtrados, filtro=filtro, criterio=criterio, ordenar=ordenar, estado=estado_filtro, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin )

@app.route('/eliminar_folio', methods=['POST']) def eliminar_folio(): si 'admin' no está en sesión: return redirect(url_for('login'))

folio = request.form['folio'] supabase.table("folios_registrados").delete().eq("folio", folio).execute() flash('Folio eliminado correctamente.', 'success') return redirección(url_for('admin_folios'))

@app.route('/editar_folio/<folio>', methods=['GET', 'POST']) def editar_folio(folio): si 'admin' no está en sesión: return redirect(url_for('login'))

if request.method == 'POST': data = { "marca": request.form['marca'], "linea": request.form['linea'], "anio": request.form['anio'], "numero_serie": request.form['numero_serie'], "numero_motor": request.form['numero_motor'], "fecha_expedicion": request.form['fecha_expedicion'], "fecha_vencimiento": request.form['fecha_vencimiento'] } supabase.table("folios_registrados").update(data).eq("folio", folio).execute() flash("Folio actualizado correctamente.", "success") return redirección(url_for('admin_folios'))

resultado = supabase.table("folios_registrados").select("*").eq("folio", folio).execute() if resultado.data: return render_template("editar_folio.html", folio=resultado.data[0]) else: flash("Folio no encontrado.", "error") return redirección(url_for('admin_folios'))

@app.route('/consulta_folio', methods=['GET', 'POST']) def consulta_folio(): resultado = None if request.method == 'POST': folio = request.form['folio'] response = supabase.table("folios_registrados").select("*").eq("folio", folio).execute() registros = response.data

if not registros: resultado = {"estado": "No encontrado", "folio": folio} else: registro = registros[0] fecha_expedicion = datetime.fromisoformat(registro['fecha_expedicion']) fecha_vencimiento = datetime.fromisoformat(registro['fecha_vencimiento']) hoy = datetime.now() estado = "VIGENTE" if hoy <= fecha_vencimiento else "VENCIDO"

resultado = {
        "estado": estado,
        "folio": folio,
        "fecha_expedicion": fecha_expedicion.strftime("%d/%m/%Y"),
        "fecha_vencimiento": fecha_vencimiento.strftime("%d/%m/%Y"),
        "marca": registro['marca'],
        "linea": registro['linea'],
        "año": registro['anio'],
        "numero_serie": registro['numero_serie'],
        "numero_motor": registro['numero_motor']
    }

return render_template("resultado_consulta.html", resultado=resultado)

devolver render_template("consulta_folio.html")

@app.route('/logout') def logout(): session.clear() return redirect(url_for('login'))

si nombre == 'main': app.run(debug=True)

MÃ¡ndamelo ya armado para descargar
