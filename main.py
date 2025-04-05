from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from datetime import datetime, timedelta
import sqlite3
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

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
            numero_serie TEXT
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
    numero_serie = request.form['numero_serie']
    fecha_expedicion = datetime.now()
    fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

    try:
        conn = conectar_db()
        conn.execute('INSERT INTO folios (folio, fecha_expedicion, fecha_vencimiento, numero_serie) VALUES (?, ?, ?, ?)',
                     (folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d'), numero_serie))
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
                               fecha_vencimiento=fecha_venc.strftime('%d/%m/%Y'),
                               numero_serie=fila['numero_serie'])
    else:
        return render_template('resultado_consulta.html', encontrado=False)

@app.route('/generar_comprobante', methods=['POST'])
def generar_comprobante():
    folio = request.form['folio']
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if not fila:
        return "Folio no encontrado", 404

    fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
    dias = (datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d') - fecha_exp).days
    fecha_pago = fecha_exp.strftime('%d/%m/%Y')
    serie = fila['numero_serie'] if 'numero_serie' in fila.keys() else 'SIN SERIE'

    generar_comprobante_precio_izquierda_final(serie, fecha_pago, dias)
    final_path = f"comprobante_precio_final_{dias}.pdf"

    return send_file(final_path, as_attachment=True)

def generar_comprobante_precio_izquierda_final(serie, fecha_pago, dias):
    precios = {30: "$374.00", 60: "$748.00", 90: "$1122.00"}
    precio = precios.get(dias, "$0.00")
    texto_vigencia = f"PERMISO PARA CIRCULAR {dias} DÍAS"

    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    can.setFont("Helvetica-Bold", 7.2)
    x_serie = 119
    y_serie = 635
    y_vigencia = y_serie + 21.1
    can.drawString(x_serie, y_vigencia, texto_vigencia)
    can.drawString(x_serie, y_serie, serie)
    can.drawString(176, 494.4, fecha_pago)

    # Precio ajustado
    can.setFont("Helvetica-Bold", 11.4)
    can.drawString(397.3, y_vigencia - 272, precio)

    can.save()
    packet.seek(0)

    template_path = "recibo de pago semovo.pdf"
    existing_pdf = PdfReader(template_path)
    output = PdfWriter()
    template_page = existing_pdf.pages[0]
    overlay = PdfReader(packet)
    template_page.merge_page(overlay.pages[0])
    output.add_page(template_page)

    with open(f"comprobante_precio_final_{dias}.pdf", "wb") as f:
        output.write(f)

if __name__ == '__main__':
    app.run(debug=True)
