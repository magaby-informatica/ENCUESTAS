import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, CondPageBreak, KeepTogether)
from reportlab.graphics.shapes import Drawing, String, Rect
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart

NAVY = colors.HexColor('#1F3A5F')
GRIS = colors.HexColor('#EEF2F7')
C_QUIZ = colors.HexColor('#1F3A5F')
C_PRES = colors.HexColor('#E08A1E')
BORDE = colors.HexColor('#C5CCD6')
ANCHO = landscape(letter)[0] - 3 * cm


def _fecha(f):
    s = str(f)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return s


def _n(v):
    return f"{int(v):,}".replace(',', '.')


def _norm(s):
    s = ' '.join(str(s or '').split())
    return s.upper() if s else 'SIN ORGANISMO'


def _corto(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + '…'


def _heat(v, vmax):
    """Devuelve (color_fondo, color_texto) segun intensidad."""
    if v <= 0:
        return colors.HexColor('#F6F7F9'), colors.HexColor('#B8BEC8')
    t = (v / float(vmax)) ** 0.5
    a, b = (255, 240, 214), (178, 40, 12)
    rgb = [int(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    fondo = colors.Color(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return fondo, (colors.white if t > 0.55 else colors.black)


def _leyenda(d, x, y):
    d.add(Rect(x, y, 8, 8, fillColor=C_QUIZ, strokeColor=None))
    d.add(String(x + 12, y, 'Quiz', fontName='Helvetica', fontSize=8))
    d.add(Rect(x + 50, y, 8, 8, fillColor=C_PRES, strokeColor=None))
    d.add(String(x + 62, y, 'Presaber', fontName='Helvetica', fontSize=8))


def _barras_organismos(orgs):
    """Barras horizontales apiladas (quiz + presaber) para una lista de organismos."""
    alto = max(3.2 * cm, 0.62 * cm * len(orgs) + 1.6 * cm)
    d = Drawing(ANCHO, alto)
    bc = HorizontalBarChart()
    bc.x = 7.6 * cm
    bc.y = 0.5 * cm
    bc.width = ANCHO - 9.2 * cm
    bc.height = alto - 1.3 * cm
    rev = list(reversed(orgs))
    bc.data = [[o['quiz'] for o in rev], [o['presaber'] for o in rev]]
    bc.categoryAxis.categoryNames = [_corto(o['nombre'], 44) for o in rev]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.dx = -3
    bc.categoryAxis.style = 'stacked'
    bc.categoryAxis.visibleTicks = 0
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_QUIZ
    bc.bars[1].fillColor = C_PRES
    bc.bars.strokeColor = None
    bc.barWidth = 9
    bc.groupSpacing = 4
    d.add(bc)
    # total al final de cada barra
    mx = max([o['total'] for o in orgs] + [1])
    vmax = bc.valueAxis.valueMax if bc.valueAxis.valueMax else mx
    _leyenda(d, 7.6 * cm, alto - 0.5 * cm)
    return d


def _barras_jornadas(org, jornadas):
    """Barras verticales apiladas por jornada para un organismo."""
    ids = [j['id_jornada'] for j in jornadas if org['por_jornada'].get(j['id_jornada'])]
    alto = 4.0 * cm
    d = Drawing(ANCHO, alto)
    if not ids:
        return d
    bc = VerticalBarChart()
    bc.x = 1.2 * cm
    bc.y = 0.8 * cm
    bc.width = min(ANCHO - 3 * cm, max(6 * cm, 1.3 * cm * len(ids)))
    bc.height = alto - 1.5 * cm
    bc.data = [[org['por_jornada'][i]['quiz'] for i in ids],
               [org['por_jornada'][i]['presaber'] for i in ids]]
    bc.categoryAxis.categoryNames = ['J%s' % i for i in ids]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.style = 'stacked'
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_QUIZ
    bc.bars[1].fillColor = C_PRES
    bc.bars.strokeColor = None
    bc.groupSpacing = 6
    d.add(bc)
    _leyenda(d, 1.2 * cm, alto - 0.45 * cm)
    return d


def _preparar(respuestas, jornadas):
    orden = {j['id_jornada']: i for i, j in enumerate(jornadas)}
    orgs = {}
    for r in respuestas:
        k = _norm(r.get('organismo'))
        nombre = ' '.join(str(r.get('organismo') or '').split()) or 'Sin organismo'
        o = orgs.setdefault(k, {'nombre': nombre, 'quiz': 0, 'presaber': 0,
                                'total': 0, 'por_jornada': {}})
        jid = r['id_jornada']
        n = int(r.get('n') or 0)
        pj = o['por_jornada'].setdefault(jid, {'quiz': 0, 'presaber': 0})
        tipo = 'quiz' if r.get('tipo') == 'quiz' else 'presaber'
        pj[tipo] += n
        o[tipo] += n
        o['total'] += n
    lista = sorted(orgs.values(), key=lambda o: (-o['total'], o['nombre']))
    for o in lista:
        o['jornadas'] = sorted(o['por_jornada'].keys(), key=lambda i: orden.get(i, 10 ** 6))
    return lista


def generar_informe_organismos_pdf(respuestas, jornadas):
    """respuestas: dicts id_jornada, organismo, tipo ('quiz'|'presaber'), n
    jornadas: dicts id_jornada, nombre, fecha (en orden cronologico)"""
    orgs = _preparar(respuestas, jornadas)
    info_j = {j['id_jornada']: j for j in jornadas}
    ids_con_datos = [j['id_jornada'] for j in jornadas
                     if any(j['id_jornada'] in o['por_jornada'] for o in orgs)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title='Informe por organismo - ENCUESTAS')
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle('H1', parent=ss['Title'], fontName='Helvetica-Bold',
                        fontSize=18, textColor=NAVY, alignment=0, spaceAfter=4)
    H2 = ParagraphStyle('H2', parent=ss['Heading2'], fontName='Helvetica-Bold',
                        fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=6)
    H3 = ParagraphStyle('H3', parent=ss['Heading3'], fontName='Helvetica-Bold',
                        fontSize=10.5, textColor=NAVY, spaceBefore=8, spaceAfter=3)
    TXT = ParagraphStyle('TXT', parent=ss['Normal'], fontName='Helvetica', fontSize=9.5, leading=13)
    CEL = ParagraphStyle('CEL', parent=TXT, fontSize=8, leading=10)
    BUL = ParagraphStyle('BUL', parent=TXT, leftIndent=12, bulletIndent=2, spaceAfter=3)

    tq = sum(o['quiz'] for o in orgs)
    tp = sum(o['presaber'] for o in orgs)
    tt = tq + tp
    S = []
    S.append(Paragraph('Informe por organismo - ENCUESTAS', H1))
    S.append(Paragraph('Alcaldía de Cali - Control Disciplinario. Generado el %s.'
                       % datetime.now().strftime('%d/%m/%Y %H:%M'), TXT))
    S.append(Paragraph('Resumen general', H2))
    S.append(Paragraph(
        'Organismos con encuestas: <b>%s</b>. Jornadas con respuestas: <b>%s</b>. '
        'Encuestas con organismo (quiz + presaber): <b>%s</b> (quiz %s, presaber %s). '
        'La encuesta de ciudadanos no registra organismo y no se incluye.'
        % (_n(len(orgs)), _n(len(ids_con_datos)), _n(tt), _n(tq), _n(tp)), TXT))

    # ---------- 1. Barras por organismo ----------
    S.append(Paragraph('Encuestas por organismo', H2))
    TAM = 18
    for i in range(0, len(orgs), TAM):
        S.append(_barras_organismos(orgs[i:i + TAM]))
        if i + TAM < len(orgs):
            S.append(PageBreak())

    # ---------- 2. Mapa de calor ----------
    S.append(PageBreak())
    S.append(Paragraph('Mapa de calor: organismo × jornada', H2))
    vmax = max([o['por_jornada'][j]['quiz'] + o['por_jornada'][j]['presaber']
                for o in orgs for j in o['por_jornada']] + [1])
    S.append(Paragraph(
        'Cada celda es el total de encuestas (quiz + presaber) del organismo en esa jornada. '
        'Más oscuro = más encuestas (máximo %s). Las columnas son los ID de jornada; '
        'su nombre y fecha están en la tabla siguiente.' % _n(vmax), TXT))
    # escala
    esc = [['0'] + [_n(round(vmax * f)) for f in (0.1, 0.25, 0.5, 0.75, 1)]]
    te = Table(esc, colWidths=[1.4 * cm] * 6, rowHeights=[0.5 * cm])
    est = [('FONTSIZE', (0, 0), (-1, -1), 7), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]
    for c, v in enumerate([0, vmax * 0.1, vmax * 0.25, vmax * 0.5, vmax * 0.75, vmax]):
        bg, fg = _heat(v if v > 0 else 0, vmax)
        est += [('BACKGROUND', (c, 0), (c, 0), bg), ('TEXTCOLOR', (c, 0), (c, 0), fg)]
    te.setStyle(TableStyle(est))
    te.hAlign = 'LEFT'
    S.append(Spacer(1, 4))
    S.append(te)
    S.append(Spacer(1, 6))

    BLOQ = 28
    bloques = [ids_con_datos[i:i + BLOQ] for i in range(0, len(ids_con_datos), BLOQ)] or [[]]
    ancho_org, ancho_tot = 6.8 * cm, 1.4 * cm
    for b, bloque in enumerate(bloques):
        if len(bloques) > 1:
            S.append(Paragraph('Jornadas %s a %s' % (bloque[0], bloque[-1]), H3))
        cw = min(0.95 * cm, (ANCHO - ancho_org - ancho_tot) / max(len(bloque), 1))
        datos = [['Organismo'] + [str(i) for i in bloque] + ['Total']]
        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6.5),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.white),
            ('FONTNAME', (-1, 1), (-1, -1), 'Helvetica-Bold'),
        ]
        for r, o in enumerate(orgs, start=1):
            fila = [_corto(o['nombre'], 46)]
            for c, jid in enumerate(bloque, start=1):
                pj = o['por_jornada'].get(jid)
                v = (pj['quiz'] + pj['presaber']) if pj else 0
                fila.append(str(v) if v else '')
                bg, fg = _heat(v, vmax)
                estilo += [('BACKGROUND', (c, r), (c, r), bg), ('TEXTCOLOR', (c, r), (c, r), fg)]
            fila.append(_n(o['total']))
            datos.append(fila)
        t = Table(datos, colWidths=[ancho_org] + [cw] * len(bloque) + [ancho_tot],
                  repeatRows=1, rowHeights=0.42 * cm)
        t.setStyle(TableStyle(estilo))
        S.append(t)
        if b < len(bloques) - 1:
            S.append(PageBreak())

    # ---------- 3. Tabla de jornadas ----------
    S.append(PageBreak())
    S.append(Paragraph('Jornadas incluidas', H2))
    dj = [['ID', 'Jornada', 'Fecha', 'Quiz', 'Presaber', 'Total']]
    for jid in ids_con_datos:
        j = info_j[jid]
        q = sum(o['por_jornada'].get(jid, {}).get('quiz', 0) for o in orgs)
        p = sum(o['por_jornada'].get(jid, {}).get('presaber', 0) for o in orgs)
        dj.append([str(jid), Paragraph(escape(str(j.get('nombre') or '-')), CEL),
                   _fecha(j.get('fecha')), _n(q), _n(p), _n(q + p)])
    tj = Table(dj, colWidths=[1.3 * cm, 13 * cm, 2.6 * cm, 2 * cm, 2.4 * cm, 2 * cm], repeatRows=1)
    tj.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, BORDE)]))
    S.append(tj)

    # ---------- 4. Detalle por organismo ----------
    S.append(PageBreak())
    S.append(Paragraph('Detalle por organismo', H2))
    for o in orgs:
        S.append(CondPageBreak(9.5 * cm))
        S.append(Paragraph(
            '%s &nbsp;<font size="9" color="#555555">- %s encuestas en %s jornada(s)</font>'
            % (escape(o['nombre']), _n(o['total']), _n(len(o['jornadas']))), H3))
        dt = [['ID', 'Jornada', 'Fecha', 'Quiz', 'Presaber', 'Total']]
        for jid in o['jornadas']:
            j = info_j.get(jid, {})
            pj = o['por_jornada'][jid]
            dt.append([str(jid), Paragraph(escape(str(j.get('nombre') or '-')), CEL),
                       _fecha(j.get('fecha')), _n(pj['quiz']), _n(pj['presaber']),
                       _n(pj['quiz'] + pj['presaber'])])
        dt.append(['', 'TOTAL', '', _n(o['quiz']), _n(o['presaber']), _n(o['total'])])
        tt_ = Table(dt, colWidths=[1.3 * cm, 13 * cm, 2.6 * cm, 2 * cm, 2.4 * cm, 2 * cm],
                    repeatRows=1)
        tt_.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRIS]),
            ('BACKGROUND', (0, -1), (-1, -1), GRIS), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, BORDE)]))
        S.append(tt_)
        S.append(Spacer(1, 4))
        S.append(_barras_jornadas(o, jornadas))

    # ---------- Observaciones ----------
    obs = []
    if orgs and tt:
        top = orgs[:3]
        parte = sum(o['total'] for o in top) * 100.0 / tt
        obs.append('Los 3 organismos con más encuestas (%s) concentran el %.0f%% del total.'
                   % (', '.join(o['nombre'] for o in top), parte))
    sin = [o for o in orgs if _norm(o['nombre']) == 'SIN ORGANISMO']
    if sin:
        obs.append('%s encuestas no tienen organismo registrado.' % _n(sin[0]['total']))
    uno = [o['nombre'] for o in orgs if len(o['jornadas']) == 1]
    if uno:
        obs.append('%s organismo(s) participaron en una sola jornada.' % _n(len(uno)))
    if obs:
        S.append(CondPageBreak(4 * cm))
        S.append(Paragraph('Observaciones', H2))
        for t in obs:
            S.append(Paragraph(escape(t), BUL, bulletText='•'))

    def pie(canvas, d):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(landscape(letter)[0] - 1.5 * cm, 0.8 * cm, 'Página %d' % d.page)
        canvas.restoreState()

    doc.build(S, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
