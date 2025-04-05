from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'clave_secreta'

def conectar_db():
    conn = sqlite3.connect('folios.db')
    conn.row_factory = sqlite3.Row
    return conn

def crear_tabla():
    conn = conectar_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS folios (
            folio TEXT PRIMARY KEY,
            marca TEXT,
            linea TEXT,
            ano INTEGER,
            num_serie TEXT,
            num_motor TEXT,
            fecha_expedicion TEXT,
            fecha_vencimiento TEXT
        )
    ''')
    conn.commit()
    conn.close()

crear_tabla()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == 'admin':  # Cambia esta parte con la contraseña real
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('Contraseña incorrecta', 'error')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('registro_folio.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    folio = request.form['folio']
    marca = request.form['marca']
    linea = request.form['linea']
    ano = request.form['ano']
    num_serie = request.form['num_serie']
    num_motor = request.form['num_motor']
    vigencia = int(request.form['vigencia'])
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('INSERT INTO folios (folio, marca, linea, ano, num_serie, num_motor, fecha_expedicion, fecha_vencimiento) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (folio, marca, linea, ano, num_serie, num_motor, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('admin'))

@app.route('/consulta', methods=['GET'])
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST'])
def resultado_consulta():
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
            'estado': estado,
            'fecha_expedicion': fecha_exp.strftime('%d/%m/%Y'),
            'fecha_vencimiento': fecha_venc.strftime('%d/%m/%Y'),
            'marca': fila['marca'],
            'linea': fila['linea'],
            'ano': fila['ano'],
            'num_serie': fila['num_serie'],
            'num_motor': fila['num_motor']
        }
    else:
        resultado = {
            'estado': 'No encontrado'
        }

    return render_template('resultado_consulta.html', resultado=resultado)

if __name__ == '__main__':
    app.run(debug=True)
