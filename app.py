@app.route('/jornadas', methods=['GET', 'POST'])
@login_required
@admin_required
def jornadas():
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        nombre_org = None
        if f.get('organismo_id'):
            with conn.cursor() as cur:
                cur.execute("SELECT ORGANISMO FROM organismos WHERE ID_ORGANISMO=%s", (f.get('organismo_id'),))
                row = cur.fetchone()
                nombre_org = row['ORGANISMO'] if row else None
        nom_ie = None
        if f.get('institucion_educativa_id'):
            with conn.cursor() as cur:
                cur.execute("SELECT INSTITUCION_EDUCATIVA FROM directorio_ie WHERE ITEM=%s", (f.get('institucion_educativa_id'),))
                row = cur.fetchone()
                nom_ie = row['INSTITUCION_EDUCATIVA'] if row else None

        enc_ciudadanos = True if f.get('enc_ciudadanos') else False
        enc_quiz       = True if f.get('enc_quiz') else False
        enc_presaber   = True if f.get('enc_presaber') else False
        # Al menos una debe estar seleccionada
        if not (enc_ciudadanos or enc_quiz or enc_presaber):
            flash('Debes seleccionar al menos una encuesta')
            conn.close()
            return redirect(url_for('jornadas'))

        # TIPO_PUBLICO para compatibilidad
        if enc_ciudadanos and not enc_quiz and not enc_presaber:
            tipo_publico = 'CIUDADANO'
        else:
            tipo_publico = 'SERVIDOR'

        pin = f.get('pin', '').strip() or None
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jornadas
                (NOMBRE, FECHA, LUGAR, DIRECCION, RESPONSABLE, META_ENCUESTADOS,
                 TIPO_PUBLICO, ORGANISMO_ID, NOMBRE_ORGANISMO,
                 INSTITUCION_EDUCATIVA_ID, NOM_INS_EDUCATIVA, CREADO_POR, PIN,
                 ENC_CIUDADANOS, ENC_QUIZ, ENC_PRESABER,
                 ENC_CIUDADANOS_ACTIVA, ENC_QUIZ_ACTIVA, ENC_PRESABER_ACTIVA)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING ID_JORNADA
            """, (
                f.get('nombre'), f.get('fecha'), f.get('lugar'), f.get('direccion'),
                f.get('responsable'), f.get('meta_encuestados') or 0,
                tipo_publico,
                f.get('organismo_id') or None, nombre_org,
                f.get('institucion_educativa_id') or None, nom_ie,
                session['usuario'], pin,
                enc_ciudadanos, enc_quiz, enc_presaber,
                enc_ciudadanos, enc_quiz, enc_presaber
            ))
            nueva_id = cur.fetchone()['ID_JORNADA']
        conn.commit()
        session['jornada_id'] = nueva_id
        flash('Jornada creada y activada')
        conn.close()
        return redirect(url_for('jornadas'))

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM organismos ORDER BY ORGANISMO")
        organismos_list = cur.fetchall()
        cur.execute("SELECT * FROM directorio_ie ORDER BY INSTITUCION_EDUCATIVA")
        instituciones = cur.fetchall()
        cur.execute("SELECT * FROM jornadas ORDER BY FECHA DESC, ID_JORNADA DESC")
        registros = cur.fetchall()
    conn.close()
    return render_template('jornadas.html',
        organismos=organismos_list, instituciones=instituciones,
        registros=registros, today=date.today().isoformat(),
        jornada_activa_id=session.get('jornada_id'))
