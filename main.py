from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from supabase import create_client, Client
import os

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Configuración de Supabase
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ruta de inicio
@app.route('/')
def inicio():
    return redirect(url_for('login'))

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

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

# Panel de administrador
@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('panel.html')

# Ruta para crear nuevos usuarios (solo admin)
@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))

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

# Panel para usuarios normales
@app.route('/registro_usuario')
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    response = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
    folios_info = response.data[0] if response.data else {}

    return render_template('registro_usuario.html', folios_info=folios_info)

# Ruta para registro de folios por parte del admin
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

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
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "nombre_solicitante": nombre_solicitante,
            "fecha_expedicion": fecha_expedicion.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat(),
            "estado": "Vigente"
        }

        try:
            # Verificar que el folio no exista
            existe = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
            if existe.data:
                flash("Este folio ya fue registrado", "error")
            else:
                supabase.table("folios_registrados").insert(data).execute()
                flash("Folio registrado exitosamente", "success")
        except Exception as e:
            flash("Ocurrió un error al registrar el folio", "error")

    return render_template('registro_admin.html')

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Iniciar servidor
if __name__ == '__main__':
    app.run(debug=True)
