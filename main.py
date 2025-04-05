from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
import sqlite3
from reportlab.pdfgen import canvas
from io import BytesIO

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
            fecha_expedicion TEXT,
            fecha_vencimiento TEXT,
            serie TEXT
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
        usuario = request.form['usuario']
        contraseña = request.form['contraseña']
        if usuario == 'admin' and contraseña == 'admin123':
            session['usuario'] = usuario
            return redirect(url_for('panel'))
        else:
            flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('index'))

@app.route('/panel')
def panel():
    if 'usuario' in session:
        return render_template('panel.html')
    else:
        return redirect(url_for('login'))

@app.route('/registro_folio')
def registro_folio():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('registro_folio.html')

@app.route('/registrar_folio', methods=['POST'])
def registrar_folio():
    folio = request.form['folio']
    serie = request.form['serie']
    vigencia = int(request.form['vigencia'])

    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('INSERT INTO folios (folio, fecha_expedicion, fecha_vencimiento, serie) VALUES (?, ?, ?, ?)',
                     (folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d'), serie))
        conn.commit()
        conn.close()
        flash('Folio registrado exitosamente.', 'success')
    except sqlite3.IntegrityError:
        flash('Este folio ya está registrado.', 'error')

    return redirect(url_for('registro_folio'))

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
                               fecha_vencimiento=fecha_venc.strftime('%d/%m/%Y'),
                               serie=fila['serie'])
    else:
        return render_template('resultado_consulta.html', encontrado=False)

@app.route('/generar_comprobante/<folio>')
def generar_comprobante(folio):
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if not fila:
        return "Folio no encontrado", 404

    fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
    dias = (datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d') - fecha_exp).days

    precio = {30: 374.00, 60: 748.00, 90: 1122.00}.get(dias, 0)

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    p.drawString(50, 800, f"Permiso para circular {dias} días")
    p.drawString(50, 780, f"Referencia: {fila['serie']}")
    p.drawString(50, 760, f"Fecha de pago: {fecha_exp.strftime('%d/%m/%Y')}")
    p.drawString(50, 740, f"Precio: ${precio:.2f}")

    p.showPage()
    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='comprobante_pago.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
