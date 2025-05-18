from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz
import os
import vonage

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Supabase configuration
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vonage SMS
VONAGE_KEY = "3a43e40b"
VONAGE_SECRET = "RF1Uvng7cxLTddp9"
vonage_client = vonage.Client(key=VONAGE_KEY, secret=VONAGE_SECRET)
sms = vonage.Sms(vonage_client)

ENTIDAD = "cdmx"

def enviar_sms(numero: str, folio: str):
    mensaje = (
        f"⚠️ AVISO: El permiso con folio {folio} ha vencido. "
        "Evita corralón y multas. Renueva hoy mismo. "
        "No respondas a este mensaje. Contáctanos por WhatsApp."
    )
    return sms.send_message({
        "from": "ValidacionMX",
        "to": f"52{numero}",
        "text": mensaje,
    })

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'Gsr89roja.' and password == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))
        resp = supabase.table("verificaciondigitalcdmx").select("*").eq("username", username).eq("password", password).execute()
        if resp.data:
            session['user_id'] = resp.data[0]['id']
            session['username'] = resp.data[0]['username']
            return redirect(url_for('registro_usuario'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('panel.html')
    @app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        folios = int(request.form['folios'])
        ex = supabase.table("verificaciondigitalcdmx").select("id").eq("username", user).execute()
        if ex.data:
            flash('Usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": user,
                "password": pwd,
                "folios_asignac": folios,
                "folios_usados": 0
            }).execute()
            flash('Usuario creado.', 'success')
    return render_template('crear_usuario.html')

@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        serie = request.form['serie']
        motor = request.form['motor']
        vigencia = int(request.form['vigencia'])
        entidad = request.form.get('entidad', ENTIDAD).lower().strip()

        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Folio existe.', 'error')
            return redirect(url_for('registro_usuario'))

        usr = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", session['user_id']).execute().data[0]
        if usr['folios_asignac'] - usr['folios_usados'] <= 0:
            flash('Sin folios.', 'error')
            return redirect(url_for('registro_usuario'))

        ahora = datetime.now()
        venc = ahora + timedelta(days=vigencia)

        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "fecha_expedicion": ahora.isoformat(),
            "fecha_vencimiento": venc.isoformat(),
            "entidad": entidad
        }).execute()

        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": usr['folios_usados'] + 1
        }).eq("id", session['user_id']).execute()

        # Generar PDF simple (ajusta según tu plantilla)
        try:
            doc = fitz.open("elbueno.pdf")
            p = doc[0]
            p.insert_text((110.02,193.88), serie, fontsize=6, fontname="helv", color=(0,0,0))
            p.insert_text((190,324), ahora.strftime('%d/%m/%Y'), fontsize=6, fontname="helv", color=(0,0,0))
            os.makedirs("documentos", exist_ok=True)
            doc.save(f"documentos/{folio}.pdf")
        except Exception as e:
            flash(f"Error PDF: {e}", 'error')

        flash('Folio registrado y PDF generado.', 'success')
        return render_template('exitoso.html', folio=folio, serie=serie, fecha_generacion=ahora.strftime('%d/%m/%Y'))
    return render_template('registro_usuario.html')

@app.route('/admin_folios')
def admin_folios():
    if not session.get('admin'):
        return redirect(url_for('login'))
    filtro = request.args.get('filtro', '').strip()
    criterio = request.args.get('criterio', 'folio')
    ordenar = request.args.get('ordenar', 'desc')
    estado_filtro = request.args.get('estado', 'todos')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')

    consulta = supabase.table("folios_registrados").select("*")
    if filtro:
        if criterio == "folio":
            consulta = consulta.ilike("folio", f"%{filtro}%")
        elif criterio == "numero_serie":
            consulta = consulta.ilike("numero_serie", f"%{filtro}%")
    registros = consulta.execute().data or []

    hoy = datetime.now()
    filtrados = []
    for fol in registros:
        try:
            fe = datetime.fromisoformat(fol['fecha_expedicion'])
            fv = datetime.fromisoformat(fol['fecha_vencimiento'])
        except:
            continue
        fol["estado"] = "VIGENTE" if hoy <= fv else "VENCIDO"
        if estado_filtro == "vigente" and fol["estado"] != "VIGENTE":
            continue
        if estado_filtro == "vencido" and fol["estado"] != "VENCIDO":
            continue
        if fecha_inicio:
            try:
                fi = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                if fe < fi:
                    continue
            except:
                pass
        if fecha_fin:
            try:
                ff = datetime.strptime(fecha_fin, "%Y-%m-%d")
                if fe > ff:
                    continue
            except:
                pass
        filtrados.append(fol)
    filtrados.sort(key=lambda x: x['fecha_expedicion'], reverse=(ordenar == 'desc'))
    return render_template('admin_folios.html',
                           folios=filtrados,
                           filtro=filtro,
                           criterio=criterio,
                           ordenar=ordenar,
                           estado=estado_filtro,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    reg = supabase.table("folios_registrados").select("entidad").eq("folio", folio).execute().data
    if not reg:
        flash("No registrado.", "error")
        return redirect(request.referrer or url_for('admin_folios'))
    entidad = reg[0]['entidad'].lower()
    ruta = f"documentos/{folio}.pdf" if entidad == "cdmx" else f"documentos/{folio}_{entidad}.pdf"
    if not os.path.exists(ruta):
        flash("PDF no existe.", "error")
        return redirect(request.referrer or url_for('admin_folios'))
    return send_file(ruta, as_attachment=True)

@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        datos = {
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": request.form['serie'],
            "numero_motor": request.form['motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento'],
        }
        supabase.table("folios_registrados").update(datos).eq("folio", folio).execute()
        flash("Folio actualizado.", "success")
        return redirect(url_for('admin_folios'))
    r = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
    if not r:
        flash("No encontrado.", "error")
        return redirect(url_for('admin_folios'))
    return render_template('editar_folio.html', folio=r[0])

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if not session.get('admin'):
        return redirect(url_for('login'))
    folio = request.form['folio']
    supabase.table("folios_registrados").delete().eq("folio", folio).execute()
    path = f"documentos/{folio}.pdf"
    if os.path.exists(path): os.remove(path)
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio'].strip().upper()
        data = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not data:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO", "color": "rojo", "folio": folio}
        else:
            r = data[0]
            fexp = datetime.fromisoformat(r['fecha_expedicion'])
            fven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fven else "VENCIDO"
            color = "verde" if estado == "VIGENTE" else "cafe"
            resultado = {
                "estado": estado,
                "color": color,
                "folio": folio,
                "fecha_expedicion": fexp.strftime('%d/%m/%Y'),
                "fecha_vencimiento": fven.strftime('%d/%m/%Y'),
                "marca": r['marca'],
                "linea": r['linea'],
                "anio": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor'],
                "entidad": r.get('entidad', '')
            }
    return render_template('consulta_folio.html', resultado=resultado)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
