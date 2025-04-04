from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Vehiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(100))
    linea = db.Column(db.String(100))
    anio = db.Column(db.Integer)
    numero_serie = db.Column(db.String(100), unique=True)
    numero_motor = db.Column(db.String(100))
    fecha = db.Column(db.DateTime)
