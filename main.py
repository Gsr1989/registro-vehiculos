from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz
import os
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0."
    "NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generar_pdf_estado(folio, numero_serie, fecha_expedicion, estado):
    """
    Genera un PDF usando la plantilla correspondiente al estado y lo guarda en
    static/pdfs/{estado}/{folio}.pdf
    """
    plantillas = {
        "cdmx": "elbueno.pdf",
        "edomex": "labuena3.0.pdf",
        "morelos": "morelosvergas1.pdf",
        "guanajuato": "guanajuato.pdf",
        "oaxaca": "oaxacaverga.pdf"
    }
    # Ruta a la plantilla
    plantilla_path = os.path.join("static", "plantillas", estado, plantillas[estado])
    # Carpeta de salida
    pdf_output_folder = os.path.join("static", "pdfs", estado)
    os.makedirs(pdf_output_folder, exist_ok=True)

    try:
        doc = fitz.open(plantilla_path)
        page = doc[0]
        # Inserta el número de serie
        page.insert_text((149.02, 193.88),
                         numero_serie,
                         fontsize=6,
                         fontname="helv",
                         color=(0, 0, 0))
        # Inserta la fecha de expedición
        page.insert_text((190, 324),
                         fecha_expedicion.strftime("%d/%m/%Y"),
                         fontsize=6,
                         fontname="helv",
                         color=(0, 0, 0))
        # Guarda el PDF final
        output_pdf_path = os.path.join(pdf_output_folder, f"{folio}.pdf")
        doc.save(output_pdf_path)
        print(f"PDF guardado en: {output_pdf_path}")
    except Exception as e:
        print(f"Error al generar PDF para {estado}: {e}")


@app.route('/')
def inicio():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Admin hardcoded
        if username == 'Gsr89roja.' and password == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))
        # Usuario normal
        resp = supabase.table("verificaciondigitalcdmx")\
                        .select("*")\
                        .eq("username", username)\
                        .eq("password", password)\
                        .execute()
        usuarios = resp.data
        if usuarios:
            session['user_id'] = usuarios[0]['id']
            session['username'] = usuarios[0]['username']
            return redirect(url_for('registro_usuario'))
        else:
            flash('Credenciales incorrectas', 'error')
    return render_template('login.html')


@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('panel.html')


@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        folios = int(request.form['folios'])
        existe = supabase.table("verificaciondigitalcdmx")\
                         .select("id")\
                         .eq("username", username)\
                         .execute()
        if existe.data:
            flash('Error: el nombre de usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx")\
                    .insert({
                        "username": username,
                        "password": password,
                        "folios_asignac": folios,
                        "folios_usados": 0
                    })\
                    .execute()
            flash('Usuario creado exitosamente.', 'success')
    return render_template('crear_usuario.html')


@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia = int(request.form['vigencia'])

        # Verifica folio duplicado
        if supabase.table("folios_registrados")\
                   .select("*")\
                   .eq("folio", folio)\
                   .execute().data:
            flash('Error: folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        # Verifica disponibilidad de folios del usuario
        usr = supabase.table("verificaciondigitalcdmx")\
                      .select("folios_asignac, folios_usados")\
                      .eq("id", user_id)\
                      .execute().data[0]
        restantes = usr['folios_asignac'] - usr['folios_usados']
        if restantes <= 0:
            flash('No tienes folios disponibles.', 'error')
            return redirect(url_for('registro_usuario'))

        # Fechas
        fecha_expedicion = datetime.now()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        # Inserta en BD
        supabase.table("folios_registrados")\
                .insert({
                    "folio": folio,
                    "marca": marca,
                    "linea": linea,
                    "anio": anio,
                    "numero_serie": numero_serie,
                    "numero_motor": numero_motor,
                    "fecha_expedicion": fecha_expedicion.isoformat(),
                    "fecha_vencimiento": fecha_vencimiento.isoformat()
                })\
                .execute()

        # Actualiza contador de folios usados
        supabase.table("verificaciondigitalcdmx")\
                .update({"folios_usados": usr['folios_usados'] + 1})\
                .eq("id", user_id)\
                .execute()

        # Genera PDF para CDMX
        generar_pdf_estado(folio, numero_serie, fecha_expedicion, "cdmx")

        flash('Folio registrado y PDF generado.', 'success')
        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))

    # GET
    info = supabase.table("verificaciondigitalcdmx")\
                   .select("folios_asignac, folios_usados")\
                   .eq("id", user_id)\
                   .execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)


@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia = int(request.form['vigencia'])

        if supabase.table("folios_registrados")\
                   .select("*")\
                   .eq("folio", folio)\
                   .execute().data:
            flash('Error: folio ya existe.', 'error')
            return render_template('registro_admin.html')

        fecha_expedicion = datetime.now()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        supabase.table("folios_registrados")\
                .insert({
                    "folio": folio,
                    "marca": marca,
                    "linea": linea,
                    "anio": anio,
                    "numero_serie": numero_serie,
                    "numero_motor": numero_motor,
                    "fecha_expedicion": fecha_expedicion.isoformat(),
                    "fecha_vencimiento": fecha_vencimiento.isoformat()
                })\
                .execute()

        # Genera PDF para CDMX
        generar_pdf_estado(folio, numero_serie, fecha_expedicion, "cdmx")

        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_expedicion.strftime('%d/%m/%Y'))
    return render_template('registro_admin.html')


@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        resp = supabase.table("folios_registrados")\
                       .select("*")\
                       .eq("folio", folio)\
                       .execute().data
        if not resp:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO",
                         "color": "rojo",
                         "folio": folio}
        else:
            r = resp[0]
            fecha_exp = datetime.fromisoformat(r['fecha_expedicion'])
            fecha_ven = datetime.fromisoformat(r['fecha_vencimiento'])
            hoy = datetime.now()
            estado = "VIGENTE" if hoy <= fecha_ven else "VENCIDO"
            color = "verde" if estado == "VIGENTE" else "cafe"
            resultado = {
                "estado": estado,
                "color": color,
                "folio": folio,
                "fecha_expedicion": fecha_exp.strftime('%d/%m/%Y'),
                "fecha_vencimiento": fecha_ven.strftime('%d/%m/%Y'),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor']
            }
    return render_template("consulta_folio.html", resultado=resultado)


@app.route('/descargar_pdf/<estado>/<folio>')
def descargar_pdf(estado, folio):
    path = f"static/pdfs/{estado}/{folio}.pdf"
    return send_file(path, as_attachment=True)


@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))

    filtro      = request.args.get('filtro', '').strip()
    criterio    = request.args.get('criterio', 'folio')
    ordenar     = request.args.get('ordenar', 'desc')
    estado_fil  = request.args.get('estado', 'todos')
    fecha_inicio= request.args.get('fecha_inicio', '')
    fecha_fin   = request.args.get('fecha_fin', '')

    query = supabase.table("folios_registrados").select("*")
    if filtro:
        if criterio == "folio":
            query = query.ilike("folio", f"%{filtro}%")
        else:
            query = query.ilike("numero_serie", f"%{filtro}%")
    data = query.execute().data or []

    hoy = datetime.now()
    filtrados = []
    for f in data:
        try:
            fe = datetime.fromisoformat(f['fecha_expedicion'])
            fv = datetime.fromisoformat(f['fecha_vencimiento'])
        except:
            continue
        est = "VIGENTE" if hoy <= fv else "VENCIDO"
        f['estado'] = est
        if estado_fil in ("vigente","vencido") and est != estado_fil.upper():
            continue
        if fecha_inicio:
            if fe < datetime.strptime(fecha_inicio, "%Y-%m-%d"):
                continue
        if fecha_fin:
            if fe > datetime.strptime(fecha_fin, "%Y-%m-%d"):
                continue
        filtrados.append(f)
    filtrados.sort(key=lambda x: x['fecha_expedicion'], reverse=(ordenar=="desc"))

    return render_template("admin_folios.html",
                           folios=filtrados,
                           filtro=filtro,
                           criterio=criterio,
                           ordenar=ordenar,
                           estado=estado_fil,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)


@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        upd = {
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": request.form['numero_serie'],
            "numero_motor": request.form['numero_motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento']
        }
        supabase.table("folios_registrados")\
                .update(upd)\
                .eq("folio", folio)\
                .execute()
        flash("Folio actualizado correctamente.", "success")
        return redirect(url_for('admin_folios'))
    resp = supabase.table("folios_registrados")\
                   .select("*")\
                   .eq("folio", folio)\
                   .execute().data
    if not resp:
        flash("Folio no encontrado.", "error")
        return redirect(url_for('admin_folios'))
    return render_template("editar_folio.html", folio=resp[0])


@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if 'admin' not in session:
        return redirect(url_for('login'))
    folio = request.form['folio']
    supabase.table("folios_registrados")\
            .delete()\
            .eq("folio", folio)\
            .execute()
    flash("Folio eliminado correctamente.", "success")
    return redirect(url_for('admin_folios'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
