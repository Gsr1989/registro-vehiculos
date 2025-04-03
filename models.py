from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Vehiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(100))
    linea = db.Column(db.String(100))
    anio = db.Column(db.String(10))
    numero_serie = db.Column(db.String(100), unique=True)
    numero_motor = db.Column(db.String(100))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    vigencia_dias = db.Column(db.Integer)
    fecha_expiracion = db.Column(db.DateTime)
    folio = db.Column(db.String(10), unique=True)
    usuario = db.Column(db.String(100))

    def estado(self):
        hoy = datetime.utcnow()
        return "Vigente" if hoy <= self.fecha_expiracion else "Vencido"