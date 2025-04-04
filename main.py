from flask import Flask, render_template, request, redirect, flash
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'secreto123'  # Cambia esto por algo más seguro en producción

# Crear base de datos si no existe
def crear_bd():
    if not os.path.exists('datos.db'):
        conn = sqlite3.connect('datos.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_serie TEXT,
                folio TEXT UNIQUE,
                fecha_expedicion TEXT,
                fecha_vencimiento TEXT
            )
        ''')
        conn.commit()
        conn.close()

crear_bd()

# Ruta para registrar
@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        numero_serie = request.form['numero_serie']
        folio = request.form['folio']
        vigencia_dias = int(request.form['vigencia_dias'])

        fecha_expedicion = datetime.now()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia_dias)

        try:
            conn = sqlite3.connect('datos.db')
            c = conn.cursor()
            c.execute('INSERT INTO registros (numero_serie, folio, fecha_expedicion, fecha_vencimiento) VALUES (?, ?, ?, ?)', 
                      (numero_serie, folio, fecha_expedicion.strftime('%Y-%m-%d'), fecha_vencimiento.strftime('%Y-%m-%d')))
            conn.commit()
            conn.close()
            flash(f'Folio {folio} registrado exitosamente.', 'success')
        except sqlite3.IntegrityError:
            flash('Ese folio ya existe. Usa uno diferente.', 'error')
        return redirect('/registrar')
    return render_template('registro.html')

# Ruta para consulta
@app.route('/consulta', methods=['GET', 'POST'])
def consulta():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        conn = sqlite3.connect('datos.db')
        c = conn.cursor()
        c.execute('SELECT fecha_expedicion, fecha_vencimiento FROM registros WHERE folio = ?', (folio,))
        fila = c.fetchone()
        conn.close()

        if fila:
            fecha_expedicion = datetime.strptime(fila[0], '%Y-%m-%d')
            fecha_vencimiento = datetime.strptime(fila[1], '%Y-%m-%d')
            hoy = datetime.now()

            if hoy <= fecha_vencimiento:
                resultado = {
                    'tipo': 'activo',
                    'mensaje': f"El folio Nº {folio} se encuentra activo y vence el día {fecha_vencimiento.strftime('%d/%m/%Y')}."
                }
            else:
                resultado = {
                    'tipo': 'vencido',
                    'mensaje': f"El folio Nº {folio} ha vencido desde el día {fecha_vencimiento.strftime('%d/%m/%Y')}."
                }
        else:
            resultado = {
                'tipo': 'no_encontrado',
                'mensaje': "Este folio no se encuentra en nuestros registros."
            }
    return render_template('consulta.html', resultado=resultado)

if __name__ == '__main__':
    app.run(debug=True)
