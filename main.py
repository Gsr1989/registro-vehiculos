from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Configura tu Supabase
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == '1234':
            session['admin'] = True
            return redirect(url_for('admin'))

        response = supabase.table('verificaciondigitalcdmx').select('*').eq('username', username).eq('password', password).execute()

        if response.data:
            session['username'] = username
            return redirect(url_for('registro_usuario'))
        else:
            flash('Credenciales incorrectas', 'error')

    return render_template('login.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        folios = int(request.form['folios'])

        existing = supabase.table('verificaciondigitalcdmx').select('*').eq('username', username).execute()

        if existing.data:
            flash('El usuario ya existe', 'error')
        else:
            supabase.table('verificaciondigitalcdmx').insert({
                'username': username,
                'password': password,
                'folios_asignac': folios,
                'folios_usados': 0
            }).execute()
            flash('Usuario creado correctamente', 'success')

    return render_template('crear_usuario.html')

@app.route('/registro_usuario')
def registro_usuario():
    if 'username' not in session:
        return redirect(url_for('login'))

    usuario = supabase.table('verificaciondigitalcdmx').select('folios_asignac, folios_usados').eq('username', session['username']).execute().data[0]

    return render_template('registro_usuario.html', folios_info=usuario)

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = supabase.table('verificaciondigitalcdmx').select('*').eq('username', username).execute().data[0]

    if user_data['folios_usados'] >= user_data['folios_asignac']:
        flash('Ya usaste todos tus folios disponibles.', 'error')
        return redirect(url_for('registro_usuario'))

    folio = request.form['folio']
    vigencia = int(request.form['vigencia'])
    marca = request.form['marca']
    linea = request.form['linea']
    año = int(request.form['año'])
    numero_serie = request.form['numero_serie']
    numero_motor = request.form['numero_motor']
    fecha_expedicion = datetime.now().date()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    # Revisar si el folio ya existe
    existe = supabase.table('verificaciondigitalcdmx').select('folio').eq('folio', folio).execute()

    if existe.data:
        flash('Este folio ya está registrado.', 'error')
        return redirect(url_for('registro_usuario'))

    supabase.table('verificaciondigitalcdmx').update({
        'folios_usados': user_data['folios_usados'] + 1
    }).eq('username', username).execute()

    supabase.table('verificaciondigitalcdmx').insert({
        'username': username,
        'folio': folio,
        'vigencia_dias': vigencia,
        'marca': marca,
        'linea': linea,
        'año': año,
        'numero_serie': numero_serie,
        'numero_motor': numero_motor,
        'fecha_expedicion': str(fecha_expedicion),
        'fecha_vencim': str(fecha_vencimiento),
        'estado': 'Vigente'
    }).execute()

    flash('Folio registrado exitosamente.', 'success')
    return redirect(url_for('registro_usuario'))

@app.route('/consulta', methods=['GET'])
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST'])
def resultado_consulta():
    folio = request.form['folio']
    response = supabase.table('verificaciondigitalcdmx').select('*').eq('folio', folio).execute()

    resultado = {}
    if response.data:
        datos = response.data[0]
        fecha_exp = datetime.strptime(datos['fecha_expedicion'], '%Y-%m-%d')
        fecha_venc = datetime.strptime(datos['fecha_vencim'], '%Y-%m-%d')
        hoy = datetime.now().date()

        estado = 'Vigente' if hoy <= fecha_venc.date() else 'Vencido'

        resultado = {
            'estado': estado,
            'fecha_expedicion': fecha_exp.strftime('%d/%m/%Y'),
            'fecha_vencimiento': fecha_venc.strftime('%d/%m/%Y'),
            'marca': datos['marca'],
            'linea': datos['linea'],
            'año': datos['año'],
            'numero_serie': datos['numero_serie'],
            'numero_motor': datos['numero_motor']
        }
    else:
        resultado['estado'] = 'No encontrado'

    return render_template('resultado_consulta.html', resultado=resultado)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
