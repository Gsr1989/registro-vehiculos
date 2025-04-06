from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Configuración de Supabase
url = 'https://xsagwqepoljfsogusubw.supabase.co'
key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws'
supabase: Client = create_client(url, key)

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

        result = supabase.table('verificaciondigitalcdmx').select('*').eq('username', username).eq('password', password).execute()

        if result.data:
            user = result.data[0]
            session['user_id'] = user['id']
            session['username'] = user['username']
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

        try:
            supabase.table('verificaciondigitalcdmx').insert({
                'username': username,
                'password': password,
                'folios_asignac': folios,
                'folios_usados': 0
            }).execute()
            flash('Usuario creado exitosamente.', 'success')
        except Exception as e:
            flash('El nombre de usuario ya existe o hubo un error.', 'error')

    return render_template('crear_usuario.html')

@app.route('/registro_usuario')
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    result = supabase.table('verificaciondigitalcdmx').select('folios_asignac, folios_usados').eq('id', session['user_id']).execute()
    usuario = result.data[0] if result.data else None

    return render_template('registro_usuario.html', folios_info=usuario)

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user_data = supabase.table('verificaciondigitalcdmx').select('*').eq('id', user_id).execute().data[0]

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

    # Verificar si el folio ya existe
    ya_existe = supabase.table('verificaciondigitalcdmx').select('folio').eq('folio', folio).execute().data
    if ya_existe:
        flash('Este folio ya está registrado.', 'error')
        return redirect(url_for('registro_usuario'))

    # Insertar folio
    supabase.table('verificaciondigitalcdmx').update({
        'folio': folio,
        'marca': marca,
        'linea': linea,
        'año': año,
        'numero_serie': numero_serie,
        'numero_motor': numero_motor,
        'vigencia_dias': vigencia,
        'fecha_expedicion': fecha_expedicion.isoformat(),
        'fecha_vencim': fecha_vencimiento.isoformat(),
        'estado': 'Vigente'
    }).eq('id', user_id).execute()

    supabase.table('verificaciondigitalcdmx').update({
        'folios_usados': user_data['folios_usados'] + 1
    }).eq('id', user_id).execute()

    flash('Folio registrado exitosamente.', 'success')
    return redirect(url_for('registro_usuario'))

@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio = request.form['folio']
        vigencia = int(request.form['vigencia'])
        marca = request.form['marca']
        linea = request.form['linea']
        año = int(request.form['año'])
        numero_serie = request.form['numero_serie']
        numero_motor = request.form['numero_motor']
        fecha_expedicion = datetime.now().date()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        ya_existe = supabase.table('verificaciondigitalcdmx').select('folio').eq('folio', folio).execute().data
        if ya_existe:
            flash('Este folio ya está registrado.', 'error')
            return redirect(url_for('registro_admin'))

        supabase.table('verificaciondigitalcdmx').insert({
            'folio': folio,
            'marca': marca,
            'linea': linea,
            'año': año,
            'numero_serie': numero_serie,
            'numero_motor': numero_motor,
            'vigencia_dias': vigencia,
            'fecha_expedicion': fecha_expedicion.isoformat(),
            'fecha_vencim': fecha_vencimiento.isoformat(),
            'estado': 'Vigente'
        }).execute()

        flash('Folio registrado correctamente (admin).', 'success')

    return render_template('registro_admin.html')

@app.route('/consulta')
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST'])
def resultado_consulta():
    folio = request.form['folio']
    result = supabase.table('verificaciondigitalcdmx').select('*').eq('folio', folio).execute()
    fila = result.data[0] if result.data else None

    resultado = {}
    if fila:
        fecha_exp = datetime.fromisoformat(fila['fecha_expedicion'])
        fecha_venc = datetime.fromisoformat(fila['fecha_vencim'])
        hoy = datetime.now().date()

        estado = 'Vigente' if hoy <= fecha_venc else 'Vencido'

        resultado = {
            'estado': estado,
            'fecha_expedicion': fecha_exp.strftime('%d/%m/%Y'),
            'fecha_vencimiento': fecha_venc.strftime('%d/%m/%Y'),
            'marca': fila['marca'],
            'linea': fila['linea'],
            'año': fila['año'],
            'numero_serie': fila['numero_serie'],
            'numero_motor': fila['numero_motor']
        }
    else:
        resultado = {
            'estado': 'No encontrado'
        }

    return render_template('resultado_consulta.html', resultado=resultado)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
