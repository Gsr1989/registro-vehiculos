from flask import Flask, render_template, request, redirect, url_for, flash, session from datetime import datetime, timedelta from supabase import create_client, Client import os

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
    except Exception as e:
        flash('Error: el nombre de usuario ya existe o hubo un problema.', 'error')

return render_template('crear_usuario.html')

@app.route('/registro_usuario', methods=['GET', 'POST']) def registro_usuario(): if 'user_id' not in session: return redirect(url_for('login'))

user_id = session['user_id']
response = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
folios_info = response.data[0] if response.data else {}

if request.method == 'POST':
    folio = request.form['folio']
    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    numero_serie = request.form['numero_serie']
    numero_motor = request.form['numero_motor']
    vigencia_dias = int(request.form['vigencia'])
    nombre_solicitante = request.form['nombre_solicitante']

    # Verifica si el folio ya existe
    folio_existente = supabase.table("folios_registrados").select("id").eq("folio", folio).execute().data
    if folio_existente:
        flash('Este folio ya está registrado.', 'error')
        return redirect(url_for('registro_usuario'))

    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia_dias)

    datos_folio = {
        "folio": folio,
        "marca": marca,
        "linea": linea,
        "anio": anio,
        "numero_serie": numero_serie,
        "numero_motor": numero_motor,
        "vigencia_dias": vigencia_dias,
        "fecha_expedicion": fecha_expedicion.isoformat(),
        "fecha_vencimiento": fecha_vencimiento.isoformat(),
        "nombre_solicitante": nombre_solicitante
    }

    supabase.table("folios_registrados").insert(datos_folio).execute()

    # Aumentar contador de folios usados
    supabase.table("verificaciondigitalcdmx").update({"folios_usados": folios_info['folios_usados'] + 1}).eq("id", user_id).execute()
    flash('Folio registrado exitosamente.', 'success')

return render_template('registro_usuario.html', folios_info=folios_info)

@app.route('/logout') def logout(): session.clear() return redirect(url_for('login'))

@app.route('/consulta_folio', methods=['GET', 'POST']) def consulta_folio(): if request.method == 'POST': folio = request.form['folio'] resultado = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data if resultado: resultado = resultado[0] hoy = datetime.now().date() fecha_vencimiento = datetime.fromisoformat(resultado['fecha_vencimiento']).date() if hoy <= fecha_vencimiento: resultado['estado'] = 'Vigente' else: resultado['estado'] = 'Vencido' else: resultado = {'estado': 'No encontrado'}

return render_template('resultado_consulta.html', resultado=resultado)

return render_template('consulta_folio.html')

if name == 'main': app.run(debug=True)

