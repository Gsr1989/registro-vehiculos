
from flask import Flask, render_template, request, redirect, session, url_for

app = Flask(__name__)
app.secret_key = "clave_secreta"

USUARIO = "admin"
CONTRASENA = "1234"

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
    if "usuario" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        marca = request.form["marca"]
        linea = request.form["linea"]
        anio = request.form["anio"]
        serie = request.form["serie"]
        motor = request.form["motor"]

        # Aquí después se conectará con PDF, folios, etc.
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
