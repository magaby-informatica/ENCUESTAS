@app.route('/jornadas/informe_organismos')
@login_required
@admin_required
def jornadas_informe_organismos():
    from informe_organismos import generar_informe_organismos_pdf, generar_informe_organismos_html
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id_jornada, nombre, fecha FROM jornadas ORDER BY fecha, id_jornada""")
        jornadas_ = [{str(k).lower(): r[k] for k in r.keys()} for r in cur.fetchall()]
        cur.execute("""SELECT id_jornada, nombre_organismo AS organismo, 'quiz' AS tipo, COUNT(*) AS n
                       FROM preguntas WHERE id_jornada IS NOT NULL GROUP BY 1, 2
                       UNION ALL
                       SELECT id_jornada, organismo, 'presaber', COUNT(*)
                       FROM presaber WHERE id_jornada IS NOT NULL GROUP BY 1, 2""")
        resp = [{str(k).lower(): r[k] for k in r.keys()} for r in cur.fetchall()]
    finally:
        conn.close()
    if request.args.get('formato') != 'pdf':
        return generar_informe_organismos_html(
            resp, jornadas_, url_for('jornadas_informe_organismos', formato='pdf'))
    pdf = generar_informe_organismos_pdf(resp, jornadas_)
    r = make_response(pdf)
    r.headers['Content-Type'] = 'application/pdf'
    r.headers['Content-Disposition'] = 'attachment; filename=informe_organismos_%s.pdf' % date.today().strftime('%Y%m%d')
    return r
