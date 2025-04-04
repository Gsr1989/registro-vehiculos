from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Vehiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(100), nullable=False)
    linea = db.Column(db.String(100), nullable=False)
    anio = db.Column(db.String(4), nullable=False)
    serie = db.Column(db.String(100), nullable=False, unique=True)
    motor = db.Column(db.String(100), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
