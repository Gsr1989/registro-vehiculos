from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from supabase import create_client, Client
import os

app = Flask(__name__)
app.secret_key = 'clave_super_segura'

# Configuración de Supabase
url = "https://xsagwqepoljfsogusubw.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(url, key)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        password = request.form['password']

        if user == "admin" and password == "1234":
            session['admin'] = True
            return redirect(url_for('panel_admin'))

        data = supabase.table('verificaciondigitalcdmx').select("*").eq("username", user).eq("password", password).execute()

        if data.data:
            session['usuario'] = user
            return redirect(url_for('registro_usuario'))
        else:
            flash('Credenciales incorrectas', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/panel_admin')
def panel_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user = request.form['username']
        password = request.form['password']
        folios = int(request.form['folios'])

        supabase.table('verificaciondigitalcdmx').insert({
            'username': user,
            'password': password,
            'folios_asignac': folios,
            'folios_usados': 0
        }).execute()

        flash('Usuario creado correctamente', 'success')
        return redirect(url_for('crear_usuario'))

    return render_template('crear_usuario.html')

@app.route('/registro_usuario')
def registro_usuario():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    user = session['usuario']
    result = supabase.table('verificaciondigitalcdmx').select("folios_asignac, folios_usados").eq("username", user).execute()
    folios_info = result.data[0] if result.data else {'folios_asignac': 0, 'folios_usados': 0}
    return render_template('registro_usuario.html', folios_info=folios_info)

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    user = session['usuario']
    data = supabase.table('verificaciondigitalcdmx').select("*").eq("username", user).execute().data[0]

    if data['folios_usados'] >= data['folios_asignac']:
        flash('Ya usaste todos tus folios', 'error')
        return redirect(url_for('registro_usuario'))

    folio = request.form['folio']
    vigencia = int(request.form['vigencia_dias'])
    fecha_expedicion = datetime.now().date()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    # Verificar si el folio ya existe
    existente = supabase.table('verificaciondigitalcdmx').select("*").eq("folio", folio).execute().data
    if existente:
        flash("Ese folio ya está registrado", "error")
        return redirect(url_for('registro_usuario'))

    datos = {
        "username": user,
        "folio": folio,
        "numero_serie": request.form['numero_serie'],
        "marca": request.form['marca'],
        "linea": request.form['linea'],
        "año": int(request.form['año']),
        "numero_motor": request.form['numero_motor'],
        "vigencia_dias": vigencia,
        "fecha_expedic": fecha_expedicion.isoformat(),
        "fecha_vencim": fecha_vencimiento.isoformat(),
        "estado": "Vigente"
    }

    supabase.table('verificaciondigitalcdmx').insert(datos).execute()
    supabase.table('verificaciondigitalcdmx').update({"folios_usados": data["folios_usados"] + 1}).eq("username", user).execute()

    flash('Folio registrado con éxito', 'success')
    return redirect(url_for('registro_usuario'))

@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio = request.form['folio']
        vigencia = int(request.form['vigencia_dias'])
        fecha_expedicion = datetime.now().date()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        existente = supabase.table('verificaciondigitalcdmx').select("*").eq("folio", folio).execute().data
        if existente:
            flash("Ese folio ya está registrado", "error")
            return redirect(url_for('registro_admin'))

        datos = {
            "username": "admin",
            "folio": folio,
            "numero_serie": request.form['numero_serie'],
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "año": int(request.form['año']),
            "numero_motor": request.form['numero_motor'],
            "vigencia_dias": vigencia,
            "fecha_expedic": fecha_expedicion.isoformat(),
            "fecha_vencim": fecha_vencimiento.isoformat(),
            "estado": "Vigente"
        }

        supabase.table('verificaciondigitalcdmx').insert(datos).execute()
        flash('Folio registrado correctamente', 'success')

    return render_template('registro_admin.html')

@app.route('/consulta', methods=['GET'])
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST'])
def resultado_consulta():
    folio = request.form['folio']
    resultado = supabase.table('verificaciondigitalcdmx').select("*").eq("folio", folio).execute().data

    if not resultado:
        return render_template('resultado_consulta.html', resultado={'estado': 'Este folio no se encuentra en nuestros registros'})

    registro = resultado[0]
    fecha_vencimiento = datetime.strptime(registro['fecha_vencim'], "%Y-%m-%d").date()
    hoy = datetime.now().date()

    if hoy > fecha_vencimiento:
        estado = "Vencido"
    else:
        estado = "Vigente"

    return render_template('resultado_consulta.html', resultado={
        'estado': estado,
        'folio': registro['folio'],
        'marca': registro['marca'],
        'linea': registro['linea'],
        'año': registro['año'],
        'numero_serie': registro['numero_serie'],
        'numero_motor': registro['numero_motor'],
        'fecha_expedicion': registro['fecha_expedic'],
        'fecha_vencimiento': registro['fecha_vencim']
    })

if __name__ == '__main__':
    app.run(debug=True)
