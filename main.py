from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

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
            año TEXT,
            numero_serie TEXT,
            numero_motor TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            folios_asignados INTEGER DEFAULT 0,
            folios_usados INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

crear_tabla()

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

        conn = conectar_db()
        usuario = conn.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()

        if usuario:
            session['user_id'] = usuario['id']
            session['username'] = usuario['username']
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
            conn = conectar_db()
            conn.execute('INSERT INTO usuarios (username, password, folios_asignados) VALUES (?, ?, ?)',
                         (username, password, folios))
            conn.commit()
            flash('Usuario creado exitosamente.', 'success')
        except sqlite3.IntegrityError:
            flash('El nombre de usuario ya existe.', 'error')
        finally:
            conn.close()

    return render_template('crear_usuario.html')

@app.route('/registro_usuario')
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = conectar_db()
    usuario = conn.execute('SELECT folios_asignados, folios_usados FROM usuarios WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()

    return render_template('registro_usuario.html', folios_info=usuario)

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = conectar_db()
    usuario = conn.execute('SELECT folios_asignados, folios_usados FROM usuarios WHERE id = ?', (user_id,)).fetchone()

    if usuario['folios_usados'] >= usuario['folios_asignados']:
        conn.close()
        flash('Ya usaste todos tus folios disponibles.', 'error')
        return redirect(url_for('registro_usuario'))

    folio = request.form['folio']
    vigencia = int(request.form['vigencia'])
    marca = request.form['marca']
    linea = request.form['linea']
    año = request.form['año']
    numero_serie = request.form['numero_serie']
    numero_motor = request.form['numero_motor']
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn.execute('''
            INSERT INTO folios (folio, fecha_expedicion, fecha_vencimiento, marca, linea, año, numero_serie, numero_motor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d'),
              marca, linea, año, numero_serie, numero_motor))

        conn.execute('UPDATE usuarios SET folios_usados = folios_usados + 1 WHERE id = ?', (user_id,))
        conn.commit()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    conn.close()
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
        año = request.form['año']
        numero_serie = request.form['numero_serie']
        numero_motor = request.form['numero_motor']
        fecha_expedicion = datetime.now()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        try:
            conn = conectar_db()
            conn.execute('''
                INSERT INTO folios (folio, fecha_expedicion, fecha_vencimiento, marca, linea, año, numero_serie, numero_motor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d'),
                  marca, linea, año, numero_serie, numero_motor))
            conn.commit()
            flash('Folio registrado correctamente (admin).', 'success')
        except sqlite3.IntegrityError:
            flash('Este folio ya está registrado.', 'error')
        finally:
            conn.close()

    return render_template('registro_admin.html')

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
