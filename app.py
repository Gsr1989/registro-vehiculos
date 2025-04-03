
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'clave_secreta'

# Usuario fijo
USUARIO = "admin"
CONTRASENA = "1234"

# Almacén temporal (en memoria)
vehiculos = []

@app.route("/")
def index():
    if 'usuario' in session:
        return redirect(url_for('panel'))
    return redirect(url_for('login'))

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

@app.route("/panel", methods=["GET", "POST"])
def panel():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    if request.method == "POST":
        datos = {
            "marca": request.form["marca"],
            "linea": request.form["linea"],
            "anio": request.form["anio"],
            "serie": request.form["serie"],
            "motor": request.form["motor"]
        }
        vehiculos.append(datos)
        return render_template("panel.html", mensaje="Vehículo registrado correctamente", usuario=session['usuario'])
    return render_template("panel.html", usuario=session['usuario'])

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
