from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'clave_secreta'

USUARIO = 'admin'
CONTRASEÑA = '1234'

def conectar_db():
    conn = sqlite3.connect('folios.db')
    conn.row_factory = sqlite3.Row
    return conn

def crear_tabla():
    conn = conectar_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS folios (
            folio TEXT PRIMARY KEY,
            fecha_expedicion TEXT,
            fecha_vencimiento TEXT,
            marca TEXT,
            linea TEXT,
            anio TEXT,
            numero_serie TEXT,
            numero_motor TEXT
        )
    ''')
    conn.commit()
    conn.close()

def actualizar_tabla():
    conn = conectar_db()
    try:
        conn.execute('ALTER TABLE folios ADD COLUMN marca TEXT')
        conn.execute('ALTER TABLE folios ADD COLUMN linea TEXT')
        conn.execute('ALTER TABLE folios ADD COLUMN anio TEXT')
        conn.execute('ALTER TABLE folios ADD COLUMN numero_serie TEXT')
        conn.execute('ALTER TABLE folios ADD COLUMN numero_motor TEXT')
        conn.commit()
    except:
        pass
    conn.close()

crear_tabla()
actualizar_tabla()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contraseña = request.form['contraseña']
        if usuario == USUARIO and contraseña == CONTRASEÑA:
            session['autenticado'] = True
            return redirect(url_for('admin'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('autenticado', None)
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if not session.get('autenticado'):
        return redirect(url_for('login'))
    return render_template('registro_folio.html')

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if not session.get('autenticado'):
        return redirect(url_for('login'))

    folio = request.form['folio']
    vigencia = int(request.form['vigencia'])
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    # Nuevos campos
    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    numero_serie = request.form['numero_serie']
    numero_motor = request.form['numero_motor']

    try:
        conn = conectar_db()
        conn.execute('''
            INSERT INTO folios (
                folio, fecha_expedicion, fecha_vencimiento,
                marca, linea, anio, numero_serie, numero_motor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d'),
            marca, linea, anio, numero_serie, numero_motor
        ))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('admin'))

@app.route('/consulta', methods=['GET'])
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['GET', 'POST'])
def resultado_consulta():
    if request.method == 'POST':
        folio = request.form['folio']
        conn = conectar_db()
        cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
        fila = cursor.fetchone()
        conn.close()

        resultado = {}
        if fila:
            fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
            fecha_venc = datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d')
            hoy = datetime.now()

            if hoy <= fecha_venc:
                estado = 'Vigente'
            else:
                estado = 'Vencido'

            resultado = {
                'folio': folio,
                'estado': estado,
                'fecha_expedicion': fecha_exp.strftime('%d/%m/%Y'),
                'fecha_vencimiento': fecha_venc.strftime('%d/%m/%Y'),
                'marca': fila['marca'],
                'linea': fila['linea'],
                'anio': fila['anio'],
                'numero_serie': fila['numero_serie'],
                'numero_motor': fila['numero_motor']
            }
        else:
            resultado = {
                'estado': 'No encontrado'
            }

        return render_template('resultado_consulta.html', resultado=resultado)

    return render_template('resultado_consulta.html')

if __name__ == '__main__':
    app.run(debug=True)
