
from flask import Flask, render_template, request, redirect, session, url_for
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = "clave_secreta"

USUARIO = "admin"
CONTRASENA = "1234"
FOLIO = 100
if not os.path.exists("documentos"):
    os.makedirs("documentos")

@app.route("/")
def index():
    if "usuario" in session:
        return redirect(url_for("panel"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        usuario = request.form["usuario"]
        contrasena = request.form["contrasena"]
        if usuario == USUARIO and contrasena == CONTRASENA:
            session["usuario"] = usuario
            return redirect(url_for("panel"))
        else:
            error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)

@app.route("/panel")
def panel():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("panel.html", usuario=session["usuario"])

@app.route("/registro", methods=["GET", "POST"])
def registro():
    global FOLIO
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        marca = request.form["marca"]
        linea = request.form["linea"]
        anio = request.form["anio"]
        serie = request.form["serie"]
        motor = request.form["motor"]

        folio = f"{FOLIO:04d}"
        fecha_expedicion = datetime.today()
        fecha_vencimiento = fecha_expedicion + timedelta(days=30)

        # Crear QR
        texto_qr = f"Folio: {folio}\nMarca: {marca}\nLínea: {linea}\nAño: {anio}\nSerie: {serie}\nMotor: {motor}\nExpedición: {fecha_expedicion.strftime('%d/%m/%Y')}\nVencimiento: {fecha_vencimiento.strftime('%d/%m/%Y')}"
        img = qrcode.make(texto_qr)
        ruta_qr = f"documentos/qr_{folio}.png"
        img.save(ruta_qr)

        # PDF principal
        pdf_path = f"documentos/registro_{folio}.pdf"
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.drawString(100, 750, f"Folio: {folio}")
        c.drawString(100, 730, f"Marca: {marca}")
        c.drawString(100, 710, f"Línea: {linea}")
        c.drawString(100, 690, f"Año: {anio}")
        c.drawString(100, 670, f"Número de serie: {serie}")
        c.drawString(100, 650, f"Número de motor: {motor}")
        c.drawString(100, 630, f"Expedición: {fecha_expedicion.strftime('%d/%m/%Y')}")
        c.drawString(100, 610, f"Vigencia: {fecha_vencimiento.strftime('%d/%m/%Y')}")
        c.drawImage(ruta_qr, 400, 600, width=150, height=150)
        c.save()

        # PDF comprobante
        comprobante_path = f"documentos/comprobante_{folio}.pdf"
        cc = canvas.Canvas(comprobante_path, pagesize=letter)
        cc.drawString(100, 750, f"Referencia: {serie}")
        cc.drawString(100, 730, f"Fecha de pago: {fecha_expedicion.strftime('%d/%m/%Y')}")
        cc.save()

        FOLIO += 1
        return render_template("exitoso.html")

    return render_template("registro_vehiculo.html")

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
