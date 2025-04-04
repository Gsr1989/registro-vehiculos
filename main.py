from flask import Flask, render_template, request, redirect, session, send_file
from flask_sqlalchemy import SQLAlchemy
from models import db, Vehiculo
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
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
    if 'usuario' in session:
        return render_template('panel.html')
    else:
        return redirect('/')

@app.route('/registrar_vehiculo', methods=['POST'])
def registrar_vehiculo():
    if 'usuario' not in session:
        return redirect('/')

    marca = request.form['marca']
    linea = request.form['linea']
    anio = request.form['anio']
    serie = request.form['serie']
    motor = request.form['motor']
    fecha = datetime.now()

    vehiculo = Vehiculo(
        marca=marca,
        linea=linea,
        anio=anio,
        numero_serie=serie,
        numero_motor=motor,
        fecha=fecha
    )
    db.session.add(vehiculo)
    db.session.commit()

    # Crear QR
    qr_data = f"Marca: {marca}\nLínea: {linea}\nAño: {anio}\nSerie: {serie}\nMotor: {motor}"
    qr = qrcode.make(qr_data)
    qr_buffer = BytesIO()
    qr.save(qr_buffer)
    qr_buffer.seek(0)

    # Crear PDF
    pdf_buffer = BytesIO()
    p = canvas.Canvas(pdf_buffer)
    p.drawString(100, 800, "Comprobante de Registro de Vehículo")
    p.drawString(100, 780, f"Marca: {marca}")
    p.drawString(100, 760, f"Línea: {linea}")
    p.drawString(100, 740, f"Año: {anio}")
    p.drawString(100, 720, f"Serie: {serie}")
    p.drawString(100, 700, f"Motor: {motor}")
    p.drawString(100, 680, f"Fecha: {fecha.strftime('%Y-%m-%d %H:%M:%S')}")

    qr_img = ImageReader(qr_buffer)
    p.drawImage(qr_img, 400, 700, width=120, height=120)
    p.showPage()
    p.save()
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, as_attachment=True, download_name=f'{serie}.pdf', mimetype='application/pdf')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
