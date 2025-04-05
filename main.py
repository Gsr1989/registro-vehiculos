from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from datetime import datetime, timedelta
import sqlite3
from reportlab.pdfgen import canvas
import io

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
            serie TEXT,
            vigencia INTEGER,
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
        if request.form['username'] == 'admin' and request.form['password'] == '1234':
            session['admin'] = True
            return redirect(url_for('panel'))
        else:
            flash('Credenciales incorrectas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/panel')
def panel():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    if not session.get('admin'):
        return redirect(url_for('login'))

    folio = request.form['folio']
    serie = request.form['serie']
    vigencia = int(request.form['vigencia'])

    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('INSERT INTO folios (folio, serie, vigencia, fecha_expedicion, fecha_vencimiento) VALUES (?, ?, ?, ?, ?)',
                     (folio, serie, vigencia,
                      fecha_expedicion.strftime('%Y-%m-%d'),
                      fecha_vencimiento.strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('panel'))

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

    if fila:
        fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
        fecha_venc = datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d')
        hoy = datetime.now()
        estado = 'vigente' if hoy <= fecha_venc else 'vencido'

        return render_template('resultado_consulta.html',
                               encontrado=True,
                               folio=folio,
                               estado=estado,
                               fecha_expedicion=fecha_exp.strftime('%d/%m/%Y'),
                               fecha_vencimiento=fecha_venc.strftime('%d/%m/%Y'),
                               serie=fila['serie'],
                               vigencia=fila['vigencia'])
    else:
        return render_template('resultado_consulta.html', encontrado=False)

@app.route('/generar_comprobante/<folio>')
def generar_comprobante(folio):
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if not fila:
        return 'Folio no encontrado', 404

    serie = fila['serie']
    fecha_pago = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d').strftime('%d/%m/%Y')
    vigencia = fila['vigencia']
    monto = {30: 374.00, 60: 748.00, 90: 1122.00}.get(vigencia, 0.0)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(240, 730, f"PERMISO PARA CIRCULAR {vigencia} DÍAS")
    c.drawString(500, 525, serie)
    c.drawString(500, 505, fecha_pago)
    c.setFont("Helvetica-Bold", 11.4)
    c.drawString(440, 355, f"${monto:.2f}")
    c.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='comprobante_pago.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
