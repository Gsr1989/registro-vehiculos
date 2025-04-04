folio = request.form['folio']
    conn = conectar_db()
    cursor = conn.execute('SELECT * FROM folios WHERE folio = ?', (folio,))
    fila = cursor.fetchone()
    conn.close()

    if fila:
        fecha_exp = datetime.strptime(fila['fecha_expedicion'], '%Y-%m-%d')
        fecha_venc = datetime.strptime(fila['fecha_vencimiento'], '%Y-%m-%d')
        hoy = datetime.now()

        if hoy <= fecha_venc:
            estado = 'Vigente'
        else:
            estado = 'Vencido'

        return render_template('resultado_consulta.html',
                               encontrado=True,
                               folio=folio,
                               estado=estado,
                               fecha_expedicion=fecha_exp.strftime('%d/%m/%Y'),
                               fecha_vencimiento=fecha_venc.strftime('%d/%m/%Y'))
    else:
        return render_template('resultado_consulta.html', encontrado=False)

if __name__ == '__main__':
    app.run(debug=True)
