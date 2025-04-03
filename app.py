from flask import Flask, render_template, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from models import db, Vehiculo
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.pdfgen import canvas
import qrcode

app = Flask(__name__)
app.secret_key = 'secreto123'

# Configuración base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vehiculos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

@app.before_first_request
def crear_tablas():
    db.create_all()

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/ingresar', methods=['POST'])
def ingresar():
    usuario = request.form['usuario']
    password = request.form['password']
    if usuario == 'admin' and password == '1234':
        session['usuario'] = usuario
        return redirect('/panel')
    else:
        return render_template('error.html', mensaje='Credenciales incorrectas')

@app.route('/panel')
def panel():
    if 'usuario' not in session:
        return redirect('/')
    return render_template('panel.html')

@app.route('/registrar', methods=['POST'])
def registrar():
    if 'usuario' not in session:
        return redirect('/')

    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    numero_serie = request.form['numero_serie']
    numero_motor = request.form['numero_motor']
    vigencia = int(request.form['vigencia'])

    fecha_registro = datetime.utcnow()
    fecha_expiracion = fecha_registro + timedelta(days=vigencia)

    ultimo = Vehiculo.query.order_by(Vehiculo.id.desc()).first()
    if ultimo and ultimo.folio:
        folio_num = int(ultimo.folio)
    else:
        folio_num = 99
    folio = f"{folio_num + 1:04d}"

    qr_data = f"Folio: {folio}\nMarca: {marca}\nLínea: {linea}\nAño: {anio}\nSerie: {numero_serie}\nMotor: {numero_motor}\nVigencia: {vigencia} días"

    qr_img = qrcode.make(qr_data)
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer)
    qr_buffer.seek(0)

    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer)
    pdf.drawString(100, 800, f"Folio: {folio}")
    pdf.drawString(100, 780, f"Marca: {marca}")
    pdf.drawString(100, 760, f"Línea: {linea}")
    pdf.drawString(100, 740, f"Año: {anio}")
    pdf.drawString(100, 720, f"Número de serie: {numero_serie}")
    pdf.drawString(100, 700, f"Número de motor: {numero_motor}")
    pdf.drawString(100, 680, f"Vigencia: {vigencia} días")
    pdf.drawString(100, 660, f"Fecha de registro: {fecha_registro.strftime('%Y-%m-%d')}")
    pdf.drawString(100, 640, f"Expira: {fecha_expiracion.strftime('%Y-%m-%d')}")
    pdf.drawImage(qr_buffer, 400, 700, width=100, height=100)
    pdf.showPage()
    pdf.save()
    pdf_buffer.seek(0)

    nuevo = Vehiculo(
        marca=marca,
        linea=linea,
        anio=anio,
        numero_serie=numero_serie,
        numero_motor=numero_motor,
        fecha_registro=fecha_registro,
        fecha_expiracion=fecha_expiracion,
        vigencia_dias=vigencia,
        folio=folio,
        usuario=session['usuario']
    )
    db.session.add(nuevo)
    db.session.commit()

    return send_file(pdf_buffer, as_attachment=True, download_name=f"{folio}_vehiculo.pdf")

@app.route('/registros')
def registros():
    if 'usuario' not in session:
        return redirect('/')
    vehiculos = Vehiculo.query.all()
    return render_template('registros.html', vehiculos=vehiculos)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
