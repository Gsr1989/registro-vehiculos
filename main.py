from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from models import db, Vehiculo
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
import qrcode

app = Flask(__name__)
app.secret_key = 'secreto123'

# Configuración base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vehiculos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Crear tablas al iniciar
@app.before_request
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

    nuevo = Vehiculo(
        marca=marca,
        linea=linea,
        anio=anio,
        numero_serie=serie,
        numero_motor=motor,
        fecha=datetime.now()
    )
    db.session.add(nuevo)
    db.session.commit()

    return render_template('exitoso.html', mensaje='Vehículo registrado correctamente')

if __name__ == '__main__':
    app.run(debug=True)
