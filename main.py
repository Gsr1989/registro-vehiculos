desde flask importar Flask, render_template, solicitud, redirigir, url_para, flash, sesión, enviar_archivo
desde datetime importar datetime, timedelta
desde supabase importar create_client, Cliente
importar fitz
importar sistema operativo

aplicación = Flask(__nombre__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
CLAVE SUPABASE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Cliente = crear_cliente(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def inicio():
    retorno redirección(url_para('login'))

@app.route('/login', métodos=['GET', 'POST'])
definición de inicio de sesión():
    si solicitud.metodo == 'POST':
        nombre de usuario = request.form['nombre de usuario']
        contraseña = request.form['contraseña']
        si el nombre de usuario == 'Gsr89roja.' y la contraseña == 'serg890105':
            sesión['admin'] = Verdadero
            retorno redirección(url_para('admin'))
        respuesta = supabase.table("verificaciondigitalcdmx").select("*").eq("nombreusuario", nombreusuario).eq("contraseña", contraseña).execute()
        usuarios = respuesta.datos
        Si usuarios:
            sesión['user_id'] = usuarios[0]['id']
            sesión['nombre de usuario'] = usuarios[0]['nombre de usuario']
            devolver redirección(url_for('registro_usuario'))
        demás:
            flash('Credenciales incorrectas', 'error')
    devolver render_template('login.html')

@app.route('/admin')
definición admin():
    si 'admin' no está en sesión:
        retorno redirección(url_para('login'))
    devolver render_template('panel.html')

@app.route('/registro_admin', métodos=['GET', 'POST'])
def registro_admin():
    si 'admin' no está en sesión:
        retorno redirección(url_para('login'))

    si solicitud.metodo == 'POST':
        folio = solicitud.formulario['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = solicitud.formulario['anio']
        numero_serie = solicitud.formulario['serie']
        numero_motor = solicitud.formulario['motor']
        vigencia = int(solicitud.formulario['vigencia'])

        existente = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
        si existente.data:
            flash('Error: el folio ya existe.', 'error')
            devolver render_template('registro_admin.html')

        fecha_expedicion = fechahora.ahora()
        fecha_vencimiento = fecha_expedicion + timedelta(dias=vigencia)

        datos = {
            "folio": folio,
            "marca": marca,
            "línea": línea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": fecha_expedicion.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat()
        }

        supabase.table("folios_registrados").insert(data).execute()

        # GENERAR PDF USANDO EL BUENO
        doc = fitz.open("elbueno.pdf")
        página = doc[0]
        página.insertar_texto((149.018, 193.880), numero_serie, tamaño de fuente=6, nombre de fuente="helv", color=(0, 0, 0))
        página.insertar_texto((190, 324), fecha_expedicion.strftime('%d/%m/%Y'), tamaño de fuente=6, nombre de fuente="helv", color=(0, 0, 0))
        si no os.path.exists("documentos"):
            os.makedirs("documentos")
        doc.save(f"documentos/{folio}.pdf")

        return render_template("exitoso.html", folio=folio)

    devolver render_template("registro_admin.html")
