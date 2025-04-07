from flask import Flask, render_template, request, redirect, url_for, flash, session from datetime import datetime, timedelta from supabase import create_client, Client

app = Flask(name) app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co" SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws" supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/') def inicio(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST']) def login(): if request.method == 'POST': username = request.form['username'] password = request.form['password']

if username == 'admin' and password == '1234':
        session['admin'] = True
        return redirect(url_for('admin'))

    response = supabase.table("verificaciondigitalcdmx").select("*").eq("username", username).eq("password", password).execute()
    usuarios = response.data

    if usuarios:
        session['user_id'] = usuarios[0]['id']
        session['username'] = usuarios[0]['username']
        return redirect(url_for('registro_usuario'))
    else:
        flash('Credenciales incorrectas', 'error')

return render_template('login.html')

@app.route('/admin') def admin(): if 'admin' not in session: return redirect(url_for('login')) return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST']) def crear_usuario(): if 'admin' not in session: return redirect(url_for('login'))

if request.method == 'POST':
    username = request.form['username']
    password = request.form['password']
    folios = int(request.form['folios'])

    try:
        data = {
            "username": username,
            "password": password,
            "folios_asignac": folios,
            "folios_usados": 0
        }
        supabase.table("verificaciondigitalcdmx").insert(data).execute()
        flash('Usuario creado exitosamente.', 'success')
    except Exception:
        flash('Error: el nombre de usuario ya existe o hubo un problema.', 'error')

return render_template('crear_usuario.html')

@app.route('/registro_usuario') def registro_usuario(): if 'user_id' not in session: return redirect(url_for('login'))

user_id = session['user_id']
response = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
folios_info = response.data[0] if response.data else {}

return render_template('registro_usuario.html', folios_info=folios_info)

@app.route('/registro_admin', methods=['GET', 'POST']) def registro_folio(): if 'admin' not in session: return redirect(url_for('login'))

if request.method == 'POST':
    folio = request.form['folio']
    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    serie = request.form['serie']
    motor = request.form['motor']
    vigencia = int(request.form['vigencia'])
    nombre_solicitante = request.form['nombre_solicitante']
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    data = {
        "folio": folio,
        "marca": marca,
        "linea": linea,
        "año": anio,
        "numero_serie": serie,
        "numero_motor": motor,
        "vigencia_dias": vigencia,
        "nombre_solicitante": nombre_solicitante,
        "fecha_expedicion": fecha_expedicion.date().isoformat(),
        "fecha_vencimiento": fecha_vencimiento.date().isoformat(),
        "estado": "Vigente",
        "usuario_id": None
    }

    try:
        supabase.table("folios_registrados").insert(data).execute()
        flash("Folio registrado correctamente.", "success")
    except Exception:
        flash("Error al registrar el folio o ya está en uso.", "error")

return render_template('registro_admin.html')

@app.route('/consulta_folio', methods=['GET']) def consulta(): return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST']) def resultado_consulta(): folio = request.form['folio'] response = supabase.table("folios_registrados").select("*").eq("folio", folio).execute() registros = response.data

if not registros:
    return render_template("resultado_consulta.html", resultado={"estado": "No encontrado"})

registro = registros[0]
hoy = datetime.now().date()
vencimiento = datetime.strptime(registro['fecha_vencimiento'], "%Y-%m-%d").date()

estado = "Vigente" if hoy <= vencimiento else "Vencido"

resultado = {
    "estado": estado,
    "fecha_expedicion": registro['fecha_expedicion'],
    "fecha_vencimiento": registro['fecha_vencimiento'],
    "marca": registro['marca'],
    "linea": registro['linea'],
    "año": registro['año'],
    "numero_serie": registro['numero_serie'],
    "numero_motor": registro['numero_motor']
}

return render_template("resultado_consulta.html", resultado=resultado)

@app.route('/logout') def logout(): session.clear() return redirect(url_for('login'))

if name == 'main': app.run(debug=True)

