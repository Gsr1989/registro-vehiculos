from flask import Flask, render_template, request, redirect, url_for, session, flash from datetime import datetime, timedelta import sqlite3

app = Flask(name) app.secret_key = 'clave_secreta'

def conectar_db(): conn = sqlite3.connect('folios.db') conn.row_factory = sqlite3.Row return conn

def crear_tabla(): conn = conectar_db() conn.execute(''' CREATE TABLE IF NOT EXISTS folios ( folio TEXT PRIMARY KEY, marca TEXT, linea TEXT, anio TEXT, numero_serie TEXT, numero_motor TEXT, fecha_expedicion TEXT, fecha_vencimiento TEXT ) ''') conn.commit() conn.close()

crear_tabla()

@app.route('/') def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST']) def login(): if request.method == 'POST': usuario = request.form['usuario'] contrasena = request.form['contrasena'] if usuario == 'admin' and contrasena == 'admin123': session['usuario'] = usuario return redirect(url_for('admin')) else: flash('Credenciales incorrectas') return render_template('login.html')

@app.route('/admin') def admin(): if 'usuario' not in session: return redirect(url_for('login')) return render_template('panel.html')

@app.route('/registrar_folio', methods=['POST']) def registrar_folio(): if 'usuario' not in session: return redirect(url_for('login'))

folio = request.form['folio']
marca = request.form['marca']
linea = request.form['linea']
anio = request.form['anio']
numero_serie = request.form['numero_serie']
numero_motor = request.form['numero_motor']
vigencia = int(request.form['vigencia'])

fecha_expedicion = datetime.now()
fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

try:
    conn = conectar_db()
    conn.execute('''INSERT INTO folios 
                    (folio, marca, linea, anio, numero_serie, numero_motor, fecha_expedicion, fecha_vencimiento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (folio, marca, linea, anio, numero_serie, numero_motor,
                  fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    flash('Folio registrado exitosamente.', 'success')
except sqlite3.IntegrityError:
    flash('Este folio ya está registrado.', 'error')

return redirect(url_for('admin'))

@app.route('/consulta', methods=['GET']) def consulta(): return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['GET', 'POST']) def resultado_consulta(): resultado = {} if request.method == 'POST': folio = request.form['folio'] conn = conectar_db() cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,)) fila = cursor.fetchone() conn.close()

if fila:
        fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
        fecha_venc = datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d')
        hoy = datetime.now()

        estado = 'Vigente' if hoy <= fecha_venc else 'Vencido'

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
        resultado = {'estado': 'No encontrado'}

return render_template('resultado_consulta.html', resultado=resultado)

@app.route('/logout') def logout(): session.pop('usuario', None) return redirect(url_for('login'))

if name == 'main': app.run(debug=True)

