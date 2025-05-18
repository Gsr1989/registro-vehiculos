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
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0."
    "NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vonage SMS setup
VONAGE_KEY = "3a43e40b"
VONAGE_SECRET = "RF1Uvng7cxLTddp9"
vonage_client = vonage.Client(key=VONAGE_KEY, secret=VONAGE_SECRET)
sms = vonage.Sms(vonage_client)

# Template definitions and coordinates for non-CDMX entities
PLANTILLAS = {
    "guerrero": {
        "file": "recibo_permiso_guerrero_img.pdf",
        "coords": {
            "folio": (700, 1750, 120),
            "fecha_expedicion": (2200, 1750, 120),
            "fecha_vencimiento": (4000, 1750, 120),
            "contribuyente": (950, 1930, 120),
        },
    },
    "oaxaca": {
        "file": "oaxacaverga.pdf",
        "coords": {
            "fecha_expedicion": (136, 141, 10),
            "numero_serie": (136, 166, 10),
            "hora": (146, 206, 10),
        },
    },
    "edomex": {
        "file": "labuena3.0.pdf",
        "coords": {
            "fecha_1": (80, 142, 15),
            "fecha_2": (218, 142, 15),
            "fecha_3": (182, 283, 9),
            "fecha_4": (130, 435, 20),
            "numero_serie": (162, 185, 9),
        },
    },
    "gto": {
        "file": "guanajuato.pdf",
        "coords": {
            "numero_serie": (255.0, 180.0, 10),
            "fecha_expedicion": (255.0, 396.0, 10),
        },
    },
    "morelos": {
        "file": "morelosvergas1.pdf",
        "coords": {
            "nombre": (155, 245, 18),
            "folio": (1045, 205, 20),
            "fecha_expedicion": (1045, 275, 20),
            "hora": (1045, 348, 20),
        },
    },
}

# Default entity for CDMX (Matrix)
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
        user = request.form['username']
        pwd  = request.form['password']
        if user == 'Gsr89roja.' and pwd == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))
        resp = supabase.table("verificaciondigitalcdmx")\
            .select("*")\
            .eq("username", user)\
            .eq("password", pwd)\
            .execute()
        if resp.data:
            session['user_id']  = resp.data[0]['id']
            session['username'] = resp.data[0]['username']
            return redirect(url_for('registro_usuario'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET','POST'])
def crear_usuario():
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        user   = request.form['username']
        pwd    = request.form['password']
        folios = int(request.form['folios'])
        ex = supabase.table("verificaciondigitalcdmx")\
            .select("id")\
            .eq("username", user)\
            .execute()
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

@app.route('/registro_usuario', methods=['GET','POST'])
def registro_usuario():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio        = request.form['folio']
        marca        = request.form['marca']
        linea        = request.form['linea']
        anio         = request.form['anio']
        serie        = request.form['serie']
        motor        = request.form['motor']
        vigencia     = int(request.form['vigencia'])
        entidad      = request.form.get('entidad', ENTIDAD).lower().strip()

        # Único
        if supabase.table("folios_registrados")\
            .select("*").eq("folio", folio).execute().data:
            flash('Folio existe.', 'error')
            return redirect(url_for('registro_usuario'))

        usr = supabase.table("verificaciondigitalcdmx")\
            .select("folios_asignac, folios_usados")\
            .eq("id", session['user_id']).execute().data[0]
        if usr['folios_asignac'] - usr['folios_usados'] <= 0:
            flash('Sin folios.', 'error')
            return redirect(url_for('registro_usuario'))

        ahora = datetime.now()
        venc  = ahora + timedelta(days=vigencia)

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

        # Generar PDF
        try:
            if entidad == "cdmx":
                doc = fitz.open("elbueno.pdf")
                p = doc[0]
                p.insert_text((110.02,193.88), serie, fontsize=6, fontname="helv", color=(0,0,0))
                p.insert_text((190,324), ahora.strftime('%d/%m/%Y'), fontsize=6, fontname="helv", color=(0,0,0))
                os.makedirs("documentos", exist_ok=True)
                doc.save(f"documentos/{folio}.pdf")
            elif entidad in PLANTILLAS:
                tpl = PLANTILLAS[entidad]
                doc = fitz.open(tpl["file"])
                p   = doc[0]
                c   = tpl["coords"]
                if entidad == "guerrero":
                    p.insert_text(c["folio"][:2], folio, fontsize=c["folio"][2], fontname="helv")
                    p.insert_text(c["fecha_expedicion"][:2], ahora.strftime('%d/%m/%Y'), fontsize=c["fecha_expedicion"][2], fontname="helv")
                    p.insert_text(c["fecha_vencimiento"][:2], venc.strftime('%d/%m/%Y'), fontsize=c["fecha_vencimiento"][2], fontname="helv")
                    p.insert_text(c["contribuyente"][:2], session.get("username","").upper(), fontsize=c["contribuyente"][2], fontname="helv")
                elif entidad == "oaxaca":
                    p.insert_text(c["fecha_expedicion"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_expedicion"][2])
                    p.insert_text(c["numero_serie"][:2], serie, fontsize=c["numero_serie"][2])
                    p.insert_text(c["hora"][:2], ahora.strftime("%H:%M:%S"), fontsize=c["hora"][2])
                elif entidad == "edomex":
                    p.insert_text(c["fecha_1"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_1"][2], fontname="helv")
                    p.insert_text(c["fecha_2"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_2"][2], fontname="helv")
                    p.insert_text(c["fecha_3"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_3"][2], fontname="helv")
                    p.insert_text(c["fecha_4"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_4"][2], fontname="helv")
                    p.insert_text(c["numero_serie"][:2], serie, fontsize=c["numero_serie"][2], fontname="helv")
                elif entidad == "gto":
                    p.insert_text(c["numero_serie"][:2], serie, fontsize=c["numero_serie"][2], fontname="helv")
                    p.insert_text(c["fecha_expedicion"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_expedicion"][2], fontname="helv")
                elif entidad == "morelos":
                    p.insert_text(c["nombre"][:2], session.get("username",""), fontsize=c["nombre"][2], fontname="helv")
                    p.insert_text(c["folio"][:2], folio, fontsize=c["folio"][2], fontname="helv")
                    p.insert_text(c["fecha_expedicion"][:2], ahora.strftime("%d/%m/%Y"), fontsize=c["fecha_expedicion"][2], fontname="helv")
                    p.insert_text(c["hora"][:2], ahora.strftime("%H:%M:%S"), fontsize=c["hora"][2], fontname="helv")
                os.makedirs("documentos", exist_ok=True)
                doc.save(f"documentos/{folio}_{entidad}.pdf")
            else:
                raise Exception("Entidad no reconocida")
        except Exception as e:
            flash(f"Error PDF: {e}", 'error')

        flash('Folio registrado y PDF generado.', 'success')
        return render_template('exitoso.html',
                               folio=folio,
                               serie=serie,
                               fecha_generacion=ahora.strftime('%d/%m/%Y'))

    return render_template('registro_usuario.html')

@app.route('/registro_admin', methods=['GET','POST'])
def registro_admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    # Similar a registro_usuario, con teléfono y ENTIDAD
    return render_template('registro_admin.html')

@app.route('/consulta_folio', methods=['GET','POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio'].strip().upper()
        data = supabase.table("folios_registrados")\
            .select("*")\
            .eq("folio", folio)\
            .execute().data
        if not data:
            resultado = {"estado":"NO SE ENCUENTRA REGISTRADO","color":"rojo","folio":folio}
        else:
            r = data[0]
            fexp = datetime.fromisoformat(r['fecha_expedicion'])
            fven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fven else "VENCIDO"
            color  = "verde" if estado=="VIGENTE" else "cafe"
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
                "entidad": r.get('entidad','')
            }
    return render_template('consulta_folio.html', resultado=resultado)

@app.route('/admin_folios')
def admin_folios():
    if not session.get('admin'):
        return redirect(url_for('login'))
    registros = supabase.table("folios_registrados")\
        .select("*").execute().data or []
    return render_template('admin_folios.html', folios=registros)

@app.route('/enviar_sms_manual', methods=['POST'])
def enviar_sms_manual():
    if not session.get('admin'):
        return redirect(url_for('login'))
    folio = request.form['folio']
    tel   = request.form['telefono']
    try:
        enviar_sms(tel, folio)
        flash(f"SMS enviado a {tel}.", "success")
    except Exception as e:
        flash(f"Error SMS: {e}", "error")
    return redirect(url_for('admin_folios'))

@app.route('/enviar_alertas', methods=['POST'])
def enviar_alertas():
    if not session.get('admin'):
        return redirect(url_for('login'))
    enviados = 0
    hoy = datetime.now().date()
    for r in supabase.table("folios_registrados").select("*").execute().data:
        if r.get('numero_telefono'):
            if datetime.fromisoformat(r['fecha_vencimiento']).date() <= hoy:
                enviar_sms(r['numero_telefono'], r['folio'])
                enviados += 1
    flash(f"Enviados {enviados} alertas.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/editar_folio/<folio>', methods=['GET','POST'])
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
    # también borra folio_entidad.pdf si existe
    for e in PLANTILLAS.keys():
        p = f"documentos/{folio}_{e}.pdf"
        if os.path.exists(p): os.remove(p)
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    reg = supabase.table("folios_registrados").select("entidad")\
        .eq("folio", folio).execute().data
    if not reg:
        flash("No registrado.", "error")
        return redirect(request.referrer or url_for('admin_folios'))
    e = reg[0]['entidad'].lower()
    if e == "cdmx":
        ruta = f"documentos/{folio}.pdf"
    else:
        ruta = f"documentos/{folio}_{e}.pdf"
    if not os.path.exists(ruta):
        flash("PDF no existe.", "error")
        return redirect(request.referrer or url_for('admin_folios'))
    return send_file(ruta, as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
