
import os
from flask import Flask, render_template, request, redirect, session, url_for
import qrcode
from reportlab.pdfgen import canvas
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clave_secreta"

USUARIO = "admin"
CONTRASENA = "1234"

os.makedirs("pdfs", exist_ok=True)

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
            error = "Usuario o contraseÃ±a incorrectos"
    return render_template("login.html", error=error)

@app.route("/panel")
def panel():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("panel.html", usuario=session["usuario"])

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if "usuario" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        marca = request.form["marca"]
        linea = request.form["linea"]
        anio = request.form["anio"]
        serie = request.form["serie"]
        motor = request.form["motor"]

        datos = f"Marca: {marca}\nLÃ­nea: {linea}\nAÃ±o: {anio}\nSerie: {serie}\nMotor: {motor}"

        # Crear cÃ³digo QR
        qr = qrcode.make(datos)
        qr_path = f"pdfs/qr_{serie}.png"
        qr.save(qr_path)

        # Crear PDF
        pdf_path = f"pdfs/{serie}.pdf"
        c = canvas.Canvas(pdf_path)
        c.setFont("Helvetica", 12)
        c.drawString(50, 800, f"Registro de vehÃ­culo - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        y = 780
        for linea in datos.split("\n"):
            c.drawString(50, y, linea)
            y -= 20
        c.drawImage(qr_path, 50, y - 170, width=150, height=150)
        c.save()

        return render_template("exitoso.html")
    
    return render_template("registro_vehiculo.html")

@app.route("/error")
def error():
    mensaje = request.args.get("mensaje", "Ha ocurrido un error.")
    return render_template("error.html", mensaje=mensaje)

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
