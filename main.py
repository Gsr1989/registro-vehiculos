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

# Crear tablas al iniciar (corregido con app.before_request)
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

if __name__ == '__main__':
    app.run(debug=True)
