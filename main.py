from flask import Flask, render_template, request, redirect, session
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
        return render_template('error.html', mensaje="Credenciales incorrectas")

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

    fecha_expiracion = datetime.now() + timedelta(days=vigencia)
    folio = generar_folio()

    nuevo_vehiculo = Vehiculo(
        marca=marca,
        linea=linea,
        anio=anio,
        numero_serie=numero_serie,
        numero_motor=numero_motor,
        vigencia_dias=vigencia,
        fecha_expiracion=fecha_expiracion,
        folio=folio,
        usuario=session.get('usuario')
    )

    db.session.add(nuevo_vehiculo)
    db.session.commit()

    return render_template('exitoso.html', folio=folio)

def generar_folio():
    ultimo = Vehiculo.query.order_by(Vehiculo.id.desc()).first()
    if ultimo:
        numero = int(ultimo.folio)
        return f'{numero + 1:04d}'
    else:
        return '0100'

if __name__ == '__main__':
    app.run(debug=True)
