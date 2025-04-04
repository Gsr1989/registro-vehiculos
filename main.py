from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = 'clave_secreta'

# Conexión a la base de datos
def conectar_db():
    conn = sqlite3.connect('folios.db')
    conn.row_factory = sqlite3.Row
    return conn

# Crear tabla si no existe
def crear_tabla():
    conn = conectar_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS folios (
            folio TEXT PRIMARY KEY,
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

@app.route('/admin')
def admin():
    return render_template('registro_folio.html')

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    folio = request.form['folio']
    vigencia = int(request.form['vigencia'])

    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('INSERT INTO folios (folio, fecha_expedicion, fecha_vencimiento) VALUES (?, ?, ?)',
                     (folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('admin'))

@app.route('/consulta')
def consulta():
    return render_template('consulta_folio.html')

@app.route('/resultado_consulta', methods=['POST'])
def resultado_consulta():
    folio = request.form['folio']
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if fila:
        fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
        fecha_venc = datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d')
        hoy = datetime.now()

        if hoy <= fecha_venc:
            estado = 'Vigente'
        else:
            estado = 'Vencido'

        return render_template('resultado_consulta.html',
                               encontrado=True,
                               folio=folio,
                               estado=estado,
                               fecha_expedicion=fecha_exp.strftime('%d/%m/%Y'),
                               fecha_vencimiento=fecha_venc.strftime('%d/%m/%Y'))
    else:
        return render_template('resultado_consulta.html', encontrado=False)

if __name__ == '__main__':
    app.run(debug=True)
