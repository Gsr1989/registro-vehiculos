from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
import sqlite3
import os
from reportlab.pdfgen import canvas
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'clave_secreta'

# --- CONEXIÓN Y CREACIÓN DE TABLA ---
def conectar_db():
    conn = sqlite3.connect('folios.db')
    conn.row_factory = sqlite3.Row
    return conn

def crear_tabla():
    conn = conectar_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS folios (
            folio TEXT PRIMARY KEY,
            serie TEXT,
            vigencia INTEGER,
            fecha_expedicion TEXT,
            fecha_vencimiento TEXT,
            marca TEXT,
            linea TEXT,
            anio TEXT,
            motor TEXT
        )
    ''')
    conn.commit()
    conn.close()

crear_tabla()

# --- INICIO ---
@app.route('/')
def index():
    return render_template('index.html')

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contraseña = request.form['contraseña']
        if usuario == 'admin' and contraseña == 'admin123':
            session['usuario'] = usuario
            return redirect(url_for('panel'))
        else:
            flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

# --- PANEL ---
@app.route('/panel')
def panel():
    if 'usuario' in session:
        return render_template('panel.html')
    return redirect(url_for('login'))

# --- CERRAR SESIÓN ---
@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('index'))

# --- REGISTRO DE FOLIOS ---
@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    folio = request.form['folio']
    serie = request.form['serie']
    vigencia = int(request.form['vigencia'])
    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    motor = request.form['motor']
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('''
            INSERT INTO folios (folio, serie, vigencia, fecha_expedicion, fecha_vencimiento, marca, linea, anio, motor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            folio, serie, vigencia,
            fecha_expedicion.strftime('%Y-%m-%d'),
            fecha_vencimiento.strftime('%Y-%m-%d'),
            marca, linea, anio, motor
        ))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('panel'))

# --- CONSULTA ---
@app.route('/consulta')
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
                color = 'verde'
            else:
                estado = 'Vencido'
                color = 'amarillo'
            resultado = {
                'folio': folio,
                'estado': estado,
                'color': color,
                'fecha_expedicion': fecha_exp.strftime('%d/%m/%Y'),
                'fecha_vencimiento': fecha_venc.strftime('%d/%m/%Y'),
                'marca': fila['marca'],
                'linea': fila['linea'],
                'anio': fila['anio'],
                'serie': fila['serie'],
                'motor': fila['motor'],
                'vigencia': fila['vigencia']
            }
        else:
            resultado = {'estado': 'No encontrado', 'color': 'rojo'}

        return render_template('resultado_consulta.html', resultado=resultado)
    return redirect(url_for('consulta'))

# --- GENERAR COMPROBANTE PDF ---
@app.route('/comprobante/<folio>')
def comprobante(folio):
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if not fila:
        return 'Folio no encontrado', 404

    fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
    precio = {30: 374, 60: 748, 90: 1122}.get(fila['vigencia'], 0)

    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.setFont("Helvetica", 12)
    c.drawString(50, 800, f"Permiso para circular {fila['vigencia']} días")
    c.drawString(50, 780, f"Referencia: {fila['serie']}")
    c.drawString(50, 760, f"Fecha de pago: {fecha_exp.strftime('%d/%m/%Y')}")
    c.drawString(50, 740, f"Precio: ${precio:.2f}")
    c.save()

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="comprobante_pago.pdf", mimetype='application/pdf')

# --- MAIN ---
if __name__ == '__main__':
    app.run(debug=True)
