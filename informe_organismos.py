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
    d.add(Rect(x, y, 9, 9, fillColor=C_QUIZ, strokeColor=None))
    d.add(String(x + 14, y, 'Quiz', fontName='Helvetica', fontSize=12))
    d.add(Rect(x + 60, y, 9, 9, fillColor=C_PRES, strokeColor=None))
    d.add(String(x + 74, y, 'Presaber', fontName='Helvetica', fontSize=12))


def _barras_organismos(orgs):
    """Barras horizontales apiladas (quiz + presaber) para una lista de organismos."""
    alto = max(3.6 * cm, 0.9 * cm * len(orgs) + 2.2 * cm)
    d = Drawing(ANCHO, alto)
    bc = HorizontalBarChart()
    bc.x = 9.8 * cm
    bc.y = 0.8 * cm
    bc.width = ANCHO - 11.4 * cm
    bc.height = alto - 1.9 * cm
    rev = list(reversed(orgs))
    bc.data = [[o['quiz'] for o in rev], [o['presaber'] for o in rev]]
    bc.categoryAxis.categoryNames = [_corto(o['nombre'], 40) for o in rev]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 12
    bc.categoryAxis.labels.dx = -3
    bc.categoryAxis.style = 'stacked'
    bc.categoryAxis.visibleTicks = 0
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 12
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_QUIZ
    bc.bars[1].fillColor = C_PRES
    bc.bars.strokeColor = None
    bc.barWidth = 14
    bc.groupSpacing = 4
    d.add(bc)
    # total al final de cada barra
    mx = max([o['total'] for o in orgs] + [1])
    vmax = bc.valueAxis.valueMax if bc.valueAxis.valueMax else mx
    _leyenda(d, 9.8 * cm, alto - 0.7 * cm)
    return d


def _barras_jornadas(org, jornadas):
    """Barras verticales apiladas por jornada para un organismo."""
    ids = [j['id_jornada'] for j in jornadas if org['por_jornada'].get(j['id_jornada'])]
    alto = 5.6 * cm
    d = Drawing(ANCHO, alto)
    if not ids:
        return d
    bc = VerticalBarChart()
    bc.x = 1.2 * cm
    bc.y = 1.1 * cm
    bc.width = min(ANCHO - 3 * cm, max(6 * cm, 1.7 * cm * len(ids)))
    bc.height = alto - 2.1 * cm
    bc.data = [[org['por_jornada'][i]['quiz'] for i in ids],
               [org['por_jornada'][i]['presaber'] for i in ids]]
    bc.categoryAxis.categoryNames = ['J%s' % i for i in ids]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 12
    bc.categoryAxis.style = 'stacked'
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 12
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_QUIZ
    bc.bars[1].fillColor = C_PRES
    bc.bars.strokeColor = None
    bc.groupSpacing = 6
    d.add(bc)
    _leyenda(d, 1.2 * cm, alto - 0.6 * cm)
    return d


def _preparar(respuestas, jornadas):
    orden = {j['id_jornada']: i for i, j in enumerate(jornadas)}
    orgs = {}
    for r in respuestas:
        k = _norm(r.get('organismo'))
        nombre = ' '.join(str(r.get('organismo') or '').split()) or 'Sin organismo'
        o = orgs.setdefault(k, {'key': k, 'nombre': nombre, 'quiz': 0, 'presaber': 0,
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


def generar_informe_organismos_pdf(respuestas, jornadas, detalle=None):
    """respuestas: dicts id_jornada, organismo, tipo ('quiz'|'presaber'), n
    jornadas: dicts id_jornada, nombre, fecha (en orden cronologico)"""
    orgs = _preparar(respuestas, jornadas)
    orgs, filtro = _filtrar(orgs)
    con_det = detalle is not None or _modo_detalle()
    det = (detalle if detalle is not None else _cargar_detalle()) if con_det else {}
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
                        fontSize=24, textColor=NAVY, alignment=0, spaceAfter=4)
    H2 = ParagraphStyle('H2', parent=ss['Heading2'], fontName='Helvetica-Bold',
                        fontSize=17, textColor=NAVY, spaceBefore=10, spaceAfter=6)
    H3 = ParagraphStyle('H3', parent=ss['Heading3'], fontName='Helvetica-Bold',
                        fontSize=14, textColor=NAVY, spaceBefore=8, spaceAfter=3)
    TXT = ParagraphStyle('TXT', parent=ss['Normal'], fontName='Helvetica', fontSize=12, leading=16)
    CEL = ParagraphStyle('CEL', parent=TXT, fontSize=12, leading=14)
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
    TAM = 11
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
    te = Table(esc, colWidths=[1.9 * cm] * 6, rowHeights=[0.7 * cm])
    est = [('FONTSIZE', (0, 0), (-1, -1), 12), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]
    for c, v in enumerate([0, vmax * 0.1, vmax * 0.25, vmax * 0.5, vmax * 0.75, vmax]):
        bg, fg = _heat(v if v > 0 else 0, vmax)
        est += [('BACKGROUND', (c, 0), (c, 0), bg), ('TEXTCOLOR', (c, 0), (c, 0), fg)]
    te.setStyle(TableStyle(est))
    te.hAlign = 'LEFT'
    S.append(Spacer(1, 4))
    S.append(te)
    S.append(Spacer(1, 6))

    BLOQ = 12
    bloques = [ids_con_datos[i:i + BLOQ] for i in range(0, len(ids_con_datos), BLOQ)] or [[]]
    ancho_org, ancho_tot = 8.8 * cm, 1.9 * cm
    for b, bloque in enumerate(bloques):
        if len(bloques) > 1:
            S.append(Paragraph('Jornadas %s a %s' % (bloque[0], bloque[-1]), H3))
        cw = min(1.15 * cm, (ANCHO - ancho_org - ancho_tot) / max(len(bloque), 1))
        datos = [['Organismo'] + [str(i) for i in bloque] + ['Total']]
        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.white),
            ('FONTNAME', (-1, 1), (-1, -1), 'Helvetica-Bold'),
        ]
        for r, o in enumerate(orgs, start=1):
            fila = [Paragraph(escape(o['nombre']), CEL)]
            for c, jid in enumerate(bloque, start=1):
                pj = o['por_jornada'].get(jid)
                v = (pj['quiz'] + pj['presaber']) if pj else 0
                fila.append(str(v) if v else '')
                bg, fg = _heat(v, vmax)
                estilo += [('BACKGROUND', (c, r), (c, r), bg), ('TEXTCOLOR', (c, r), (c, r), fg)]
            fila.append(_n(o['total']))
            datos.append(fila)
        t = Table(datos, colWidths=[ancho_org] + [cw] * len(bloque) + [ancho_tot],
                  repeatRows=1)
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
    tj = Table(dj, colWidths=[1.5 * cm, 10.2 * cm, 3.3 * cm, 2.4 * cm, 3.1 * cm, 2.4 * cm], repeatRows=1)
    tj.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, BORDE)]))
    S.append(tj)
    S.append(PageBreak())
    if con_det:
        S += _pdf_referencias(H2, H3, TXT, CEL)

    # ---------- 4. Detalle por organismo ----------
    S.append(PageBreak())
    S.append(Paragraph('Detalle por organismo', H2))
    for o in orgs:
        S.append(CondPageBreak(9 * cm))
        S.append(Paragraph(
            '%s &nbsp;<font size="12" color="#555555">- %s encuestas en %s jornada(s)</font>'
            % (escape(o['nombre']), _n(o['total']), _n(len(o['jornadas']))), H3))
        dt = [['ID', 'Jornada', 'Fecha', 'Quiz', 'Presaber', 'Total']]
        for jid in o['jornadas']:
            j = info_j.get(jid, {})
            pj = o['por_jornada'][jid]
            dt.append([str(jid), Paragraph(escape(str(j.get('nombre') or '-')), CEL),
                       _fecha(j.get('fecha')), _n(pj['quiz']), _n(pj['presaber']),
                       _n(pj['quiz'] + pj['presaber'])])
        dt.append(['', 'TOTAL', '', _n(o['quiz']), _n(o['presaber']), _n(o['total'])])
        tt_ = Table(dt, colWidths=[1.5 * cm, 10.2 * cm, 3.3 * cm, 2.4 * cm, 3.1 * cm, 2.4 * cm],
                    repeatRows=1)
        tt_.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRIS]),
            ('BACKGROUND', (0, -1), (-1, -1), GRIS), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, BORDE)]))
        S.append(tt_)
        S.append(Spacer(1, 4))
        S.append(_barras_jornadas(o, jornadas))
        if con_det:
            dl = [det.get((o['key'], i)) for i in o['jornadas']]
            S.append(Paragraph('Resumen del organismo (todas sus jornadas)', H3))
            S += _pdf_resultados(_sumar([x for x in dl if x]), o['quiz'], o['presaber'], TXT)
            for i, x in zip(o['jornadas'], dl):
                j = info_j.get(i, {})
                bloque = [Paragraph('Jornada %s · %s <font size="12" color="#555555">(%s)</font>'
                                    % (i, escape(str(j.get('nombre') or '-')), _fecha(j.get('fecha'))), H3)]
                bloque += _pdf_resultados(x, _pj(o, i, 'quiz'), _pj(o, i, 'presaber'), TXT)
                S.append(KeepTogether(bloque))

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


# =====================================================================
#  VERSION HTML (se ve en pantalla; el PDF sale con "Guardar como PDF")
# =====================================================================
from html import escape as _e


def _heat_css(v, vmax):
    if v <= 0:
        return '#f6f7f9', '#b8bec8'
    t = (v / float(vmax)) ** 0.5
    a, b = (255, 240, 214), (178, 40, 12)
    r, g, bl = [int(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    return 'rgb(%d,%d,%d)' % (r, g, bl), ('#fff' if t > 0.55 else '#000')


_CSS = """
*{box-sizing:border-box}
body{font-family:Arial,Helvetica,sans-serif;font-size:12pt;color:#1b2430;margin:0;background:#f4f6f9}
.hoja{max-width:1250px;margin:0 auto;padding:24px;background:#fff}
h1{font-size:24pt;color:#1F3A5F;margin:0 0 4px}
h2{font-size:17pt;color:#1F3A5F;margin:28px 0 10px;border-bottom:2px solid #1F3A5F;padding-bottom:4px}
h3{font-size:14pt;color:#1F3A5F;margin:0 0 8px}
.sub{color:#555;margin:0 0 14px}
.barra-acc{position:sticky;top:0;background:#fff;padding:10px 0;display:flex;gap:10px;flex-wrap:wrap;border-bottom:1px solid #dfe4ec;z-index:5}
.btn{display:inline-block;background:#1F3A5F;color:#fff;text-decoration:none;border:0;border-radius:6px;padding:9px 16px;font:bold 12pt Arial,Helvetica,sans-serif;cursor:pointer}
.btn.sec{background:#fff;color:#1F3A5F;border:2px solid #1F3A5F}
.tarjetas{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.tarj{flex:1;min-width:170px;background:#EEF2F7;border-radius:8px;padding:12px 14px}
.tarj b{display:block;font-size:22pt;color:#1F3A5F}
.leyenda{display:flex;gap:18px;margin:6px 0 10px;font-size:12pt}
.leyenda i{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:6px;vertical-align:-2px}
.q{background:#1F3A5F}.p{background:#E08A1E}
.fila-b{display:flex;align-items:center;margin:5px 0}
.fila-b .nom{width:360px;font-size:12pt;padding-right:10px;text-align:right;flex:none}
.fila-b .pista{flex:1;display:flex;height:22px}
.fila-b .pista span{display:block;height:100%}
.fila-b .tot{width:60px;padding-left:8px;font-weight:bold;flex:none}
table{border-collapse:collapse;width:100%}
th{background:#1F3A5F;color:#fff;text-align:left;padding:7px 8px;font-size:12pt}
td{padding:6px 8px;border-bottom:1px solid #dfe4ec;font-size:12pt}
tr:nth-child(even) td{background:#f5f7fa}
td.n,th.n{text-align:right}
tr.tot td{font-weight:bold;background:#EEF2F7}
.mapa{overflow-x:auto;margin:8px 0 16px}
.mapa table{width:auto}
.mapa th,.mapa td{text-align:center;padding:5px 7px;font-size:12pt;border:1px solid #fff;min-width:50px}
.mapa th:first-child,.mapa td:first-child{text-align:left;min-width:300px;position:sticky;left:0;background:#fff;color:#1b2430;font-size:12pt;border-right:2px solid #dfe4ec}
.mapa th:first-child{background:#1F3A5F;color:#fff}
.mapa td.t{font-weight:bold;background:#EEF2F7 !important}
.escala{display:flex;gap:0;margin:6px 0 4px}
.escala span{padding:4px 10px;font-size:12pt;min-width:60px;text-align:center}
.org{border:1px solid #dfe4ec;border-radius:8px;padding:14px;margin:14px 0;page-break-inside:avoid;break-inside:avoid}
.cols{display:flex;align-items:flex-end;gap:10px;height:170px;margin-top:10px;border-bottom:2px solid #9aa6b6;padding:0 6px}
.col{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:48px}
.col .v{font-size:12pt;margin-bottom:2px}
.col .ap{width:34px;display:flex;flex-direction:column;justify-content:flex-end}
.etq{display:flex;gap:10px;padding:2px 6px}
.etq span{min-width:48px;text-align:center;font-size:12pt}
ul{margin:6px 0 0 18px}
li{margin:4px 0}
@page{size:landscape;margin:1.2cm}
@media print{
 body{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
 .hoja{max-width:none;padding:0}
 .barra-acc{display:none}
 .mapa{overflow:visible}
 .mapa th:first-child,.mapa td:first-child{position:static}
 h2{page-break-after:avoid}
 .corte{page-break-before:always}
}
"""


def generar_informe_organismos_html(respuestas, jornadas, url_pdf='', detalle=None):
    from urllib.parse import quote
    orgs = _preparar(respuestas, jornadas)
    orgs, filtro = _filtrar(orgs)
    con_det = detalle is not None or _modo_detalle()
    det = (detalle if detalle is not None else _cargar_detalle()) if con_det else {}
    if url_pdf and con_det:
        url_pdf = url_pdf + '&detalle=1'
    if filtro and url_pdf:
        url_pdf = url_pdf + '&org=' + quote(filtro)
    q_ = ('detalle=1' if con_det else '')
    q_org = ('&org=' + quote(filtro)) if filtro else ''
    info_j = {j['id_jornada']: j for j in jornadas}
    ids = [j['id_jornada'] for j in jornadas
           if any(j['id_jornada'] in o['por_jornada'] for o in orgs)]
    tq = sum(o['quiz'] for o in orgs)
    tp = sum(o['presaber'] for o in orgs)
    tt = tq + tp
    mx = max([o['total'] for o in orgs] + [1])
    vmax = max([o['por_jornada'][j]['quiz'] + o['por_jornada'][j]['presaber']
                for o in orgs for j in o['por_jornada']] + [1])
    H = []
    a = H.append
    a('<!doctype html><html lang="es"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<title>Informe por organismo - ENCUESTAS</title><style>%s</style></head><body>'
      '<div class="hoja">' % (_CSS + _CSS_EXTRA))
    a('<div class="barra-acc">'
      '')
    if url_pdf:
        a('<a class="btn" href="%s">⬇ Descargar PDF</a>' % _e(url_pdf))
    if con_det:
        a('<a class="btn sec" href="?%s">Ver resumido</a>' % q_org.lstrip('&'))
    else:
        a('<a class="btn sec" href="?detalle=1%s">Ver con detalle por jornada</a>' % q_org)
    a('<a class="btn sec" href="javascript:history.back()">← Volver</a></div>')
    a('<h1>Informe por organismo - ENCUESTAS</h1>')
    if filtro:
        a('<p class="sub"><b>Filtrado por organismo:</b> %s &nbsp;<a href="?%s">Ver todos</a></p>' % (_e(filtro), q_))
    a('<p class="sub">Alcaldía de Cali - Control Disciplinario. Generado el %s.</p>'
      % datetime.now().strftime('%d/%m/%Y %H:%M'))
    a('<div class="tarjetas">'
      '<div class="tarj"><b>%s</b>organismos</div>'
      '<div class="tarj"><b>%s</b>jornadas con respuestas</div>'
      '<div class="tarj"><b>%s</b>encuestas (quiz + presaber)</div>'
      '<div class="tarj"><b>%s</b>quiz</div>'
      '<div class="tarj"><b>%s</b>presaber</div></div>'
      % (_n(len(orgs)), _n(len(ids)), _n(tt), _n(tq), _n(tp)))
    a('<p class="sub">La encuesta de ciudadanos no registra organismo y no se incluye.</p>')

    # barras
    a('<h2>Encuestas por organismo</h2>')
    a('<div class="leyenda"><span><i class="q"></i>Quiz</span><span><i class="p"></i>Presaber</span></div>')
    for o in orgs:
        a('<div class="fila-b"><div class="nom">%s</div><div class="pista">'
          '<span class="q" style="width:%.2f%%" title="Quiz: %s"></span>'
          '<span class="p" style="width:%.2f%%" title="Presaber: %s"></span>'
          '</div><div class="tot">%s</div></div>'
          % (_e(o['nombre']), o['quiz'] * 100.0 / mx, _n(o['quiz']),
             o['presaber'] * 100.0 / mx, _n(o['presaber']), _n(o['total'])))

    # mapa de calor
    a('<h2 class="corte">Mapa de calor: organismo × jornada</h2>')
    a('<p class="sub">Cada celda es el total de encuestas (quiz + presaber) del organismo en esa jornada. '
      'Más oscuro = más encuestas (máximo %s). Las columnas son los ID de jornada.</p>' % _n(vmax))
    a('<div class="escala">')
    for v in (0, vmax * 0.1, vmax * 0.25, vmax * 0.5, vmax * 0.75, vmax):
        bg, fg = _heat_css(v, vmax)
        a('<span style="background:%s;color:%s">%s</span>' % (bg, fg, _n(round(v))))
    a('</div>')
    BLQ = 12
    bloques = [ids[i:i + BLQ] for i in range(0, len(ids), BLQ)] or [[]]
    for bloque in bloques:
        if len(bloques) > 1:
            a('<h3 style="margin-top:14px">Jornadas %s a %s</h3>' % (bloque[0], bloque[-1]))
        a('<div class="mapa"><table><tr><th>Organismo</th>')
        for i in bloque:
            a('<th title="%s">%s</th>' % (_e(str(info_j[i].get('nombre') or '')), i))
        a('<th>Total</th></tr>')
        for o in orgs:
            a('<tr><td>%s</td>' % _e(o['nombre']))
            for i in bloque:
                pj = o['por_jornada'].get(i)
                v = (pj['quiz'] + pj['presaber']) if pj else 0
                bg, fg = _heat_css(v, vmax)
                a('<td style="background:%s;color:%s">%s</td>' % (bg, fg, v if v else ''))
            a('<td class="t">%s</td></tr>' % _n(o['total']))
        a('</table></div>')

    # jornadas
    a('<h2>Jornadas incluidas</h2><table><tr><th>ID</th><th>Jornada</th><th>Fecha</th>'
      '<th class="n">Quiz</th><th class="n">Presaber</th><th class="n">Total</th></tr>')
    for i in ids:
        q = sum(o['por_jornada'].get(i, {}).get('quiz', 0) for o in orgs)
        p = sum(o['por_jornada'].get(i, {}).get('presaber', 0) for o in orgs)
        a('<tr><td>%s</td><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td>'
          '<td class="n">%s</td></tr>' % (i, _e(str(info_j[i].get('nombre') or '-')),
                                          _fecha(info_j[i].get('fecha')), _n(q), _n(p), _n(q + p)))
    a('</table>')
    if con_det:
        a(_html_referencias())

    # detalle
    a('<h2 class="corte">Detalle por organismo</h2>')
    for o in orgs:
        a('<div class="org"><h3>%s <span style="font-weight:normal;font-size:12pt;color:#555">'
          '- %s encuestas en %s jornada(s)</span> <a class="vl" style="font-size:12pt;font-weight:normal" href="?org=%s%s">ver solo este organismo</a></h3>'
          '<table><tr><th>ID</th><th>Jornada</th><th>Fecha</th><th class="n">Quiz</th>'
          '<th class="n">Presaber</th><th class="n">Total</th></tr>'
          % (_e(o['nombre']), _n(o['total']), _n(len(o['jornadas'])), quote(o['nombre']), ('&detalle=1' if con_det else '')))
        for i in o['jornadas']:
            pj = o['por_jornada'][i]
            a('<tr><td>%s</td><td>%s</td><td>%s</td><td class="n">%s</td><td class="n">%s</td>'
              '<td class="n">%s</td></tr>'
              % (i, _e(str(info_j.get(i, {}).get('nombre') or '-')), _fecha(info_j.get(i, {}).get('fecha')),
                 _n(pj['quiz']), _n(pj['presaber']), _n(pj['quiz'] + pj['presaber'])))
        a('<tr class="tot"><td></td><td>TOTAL</td><td></td><td class="n">%s</td><td class="n">%s</td>'
          '<td class="n">%s</td></tr></table>' % (_n(o['quiz']), _n(o['presaber']), _n(o['total'])))
        om = max([o['por_jornada'][i]['quiz'] + o['por_jornada'][i]['presaber'] for i in o['jornadas']] + [1])
        a('<div class="cols">')
        for i in o['jornadas']:
            pj = o['por_jornada'][i]
            hq = pj['quiz'] * 110.0 / om
            hp = pj['presaber'] * 110.0 / om
            a('<div class="col"><div class="v">%s</div><div class="ap">'
              '<span class="p" style="height:%.1fpx"></span><span class="q" style="height:%.1fpx"></span>'
              '</div></div>' % (_n(pj['quiz'] + pj['presaber']), hp, hq))
        a('</div><div class="etq">')
        for i in o['jornadas']:
            a('<span>J%s</span>' % i)
        a('</div>')
        if con_det:
            dl = [det.get((o['key'], i)) for i in o['jornadas']]
            a('<div class="res-org"><h4>Resumen del organismo (todas sus jornadas)</h4>')
            a(_html_resultados(_sumar([x for x in dl if x]), o['quiz'], o['presaber']))
            a('</div>')
            for i, x in zip(o['jornadas'], dl):
                jj = info_j.get(i, {})
                a('<div class="jor"><h4>Jornada %s · %s <small style="font-weight:normal;color:#555">(%s)</small></h4>'
                  % (i, _e(str(jj.get('nombre') or '-')), _fecha(jj.get('fecha'))))
                a(_html_resultados(x, _pj(o, i, 'quiz'), _pj(o, i, 'presaber')))
                a('</div>')
        a('</div>')

    # observaciones
    obs = []
    if orgs and tt:
        top = orgs[:3]
        obs.append('Los 3 organismos con más encuestas (%s) concentran el %.0f%% del total.'
                   % (', '.join(o['nombre'] for o in top), sum(o['total'] for o in top) * 100.0 / tt))
    sin = [o for o in orgs if _norm(o['nombre']) == 'SIN ORGANISMO']
    if sin:
        obs.append('%s encuestas no tienen organismo registrado.' % _n(sin[0]['total']))
    uno = [o for o in orgs if len(o['jornadas']) == 1]
    if uno:
        obs.append('%s organismo(s) participaron en una sola jornada.' % _n(len(uno)))
    if obs:
        a('<h2>Observaciones</h2><ul>%s</ul>' % ''.join('<li>%s</li>' % _e(x) for x in obs))
    a('</div></body></html>')
    return ''.join(H)


# =====================================================================
#  RESULTADOS POR PREGUNTA (por organismo y por jornada)
# =====================================================================
CORRECTAS_QUIZ = {
    'P1': 'b) Preventiva, Correctiva',
    'P2': 'a) Verbal y Ordinario conforme a la Ley 2094 de 2021',
    'P3': 'c) Gravísimas, Graves y Leves',
    'P4': 'a) Servidores públicos, aunque se encuentren retirados del servicio',
    'P5': 'd) Todas las anteriores',
    'P6': 'a) Procuraduría General de la Nación, Personerías Municipales y Distritales',
    'P7': 'b) Tiene poder sancionatorio / No tiene poder sancionatorio',
    'P8': 'd) b y c son correctas.',
}
PRESABER_LABELS = {
    'Q1': 'No tratar con respeto a las personas',
    'Q2': 'Solicitar dádivas o beneficios',
    'Q3': 'Ejecutar actos de violencia',
    'Q4': 'No dedicar el tiempo laboral',
    'Q5': 'Incumplir horario de trabajo',
    'Q6': 'Omitir respuesta a peticiones',
    'Q7': 'No acreditar requisitos del cargo',
    'Q8': 'No capacitarse en su área',
}
QUIZ_NOMBRE = {
    'P1': 'Funciones del Control',
    'P2': 'Procedimientos',
    'P3': 'Clasificación de faltas',
    'P4': 'Sujetos disciplinables',
    'P5': 'Medios de prueba',
    'P6': 'Quién ejerce la acción',
    'P7': 'Control Disc. vs Interno',
    'P8': 'Auto inhibitorio',
}
QUIZ_TEXTO = {
    'P1': '¿Qué funciones adelanta el Departamento Administrativo de Control Disciplinario Interno de Instrucción?',
    'P2': '¿Mediante qué procedimientos se puede adelantar la acción disciplinaria?',
    'P3': 'Las faltas disciplinarias se clasifican en:',
    'P4': '¿Quiénes son sujetos disciplinables?',
    'P5': '¿Cuáles son medios de prueba en la acción disciplinaria?',
    'P6': '¿Quiénes ejercen la acción disciplinaria?',
    'P7': 'Una diferencia entre Control Disciplinario Interno de Instrucción y Control Interno:',
    'P8': 'El Auto Inhibitorio que profiera el Departamento Administrativo de Control Disciplinario:',
}
PRESABER_NOMBRE = {
    'Q1': 'No tratar con respeto',
    'Q2': 'Solicitar dádivas',
    'Q3': 'Actos de violencia',
    'Q4': 'No dedicar tiempo laboral',
    'Q5': 'Incumplir horario',
    'Q6': 'Omitir peticiones',
    'Q7': 'No acreditar requisitos',
    'Q8': 'No capacitarse',
}
C_SI = colors.HexColor('#1F3A5F')
C_NO = colors.HexColor('#A9B8CC')


def _vacio():
    return {'p': {c: [0, 0] for c in CORRECTAS_QUIZ},
            'q': {c: [0, 0] for c in PRESABER_LABELS},
            'cq': {'SI': 0, 'NO': 0}, 'cp': {'SI': 0, 'NO': 0}}


def _cargar_detalle():
    """Lee de la base los resultados por (organismo, jornada). Si falla, devuelve {}."""
    det = {}
    try:
        from db import get_connection
        conn = get_connection()
    except Exception:
        return det

    def slot(r):
        return det.setdefault((_norm(r['organismo']), r['id_jornada']), _vacio())

    try:
        cur = conn.cursor()
        for col, ok in CORRECTAS_QUIZ.items():
            c = col.lower()
            cur.execute("SELECT id_jornada, nombre_organismo AS organismo, %s AS resp, COUNT(*) AS n "
                        "FROM preguntas WHERE id_jornada IS NOT NULL AND %s IS NOT NULL "
                        "GROUP BY 1, 2, 3" % (c, c))
            for r in cur.fetchall():
                s = slot(r)
                n = int(r['n'])
                s['p'][col][1] += n
                if ok.lower() in str(r['resp']).lower():
                    s['p'][col][0] += n
        for col in PRESABER_LABELS:
            c = col.lower()
            cur.execute("SELECT id_jornada, organismo, %s AS resp, COUNT(*) AS n "
                        "FROM presaber WHERE id_jornada IS NOT NULL AND %s IS NOT NULL "
                        "GROUP BY 1, 2, 3" % (c, c))
            for r in cur.fetchall():
                s = slot(r)
                v = str(r['resp']).strip().upper()
                if v == 'SI':
                    s['q'][col][0] += int(r['n'])
                elif v == 'NO':
                    s['q'][col][1] += int(r['n'])
        cur.execute("SELECT id_jornada, nombre_organismo AS organismo, capacitacion_ley_disciplinaria AS resp, "
                    "COUNT(*) AS n FROM preguntas WHERE id_jornada IS NOT NULL GROUP BY 1, 2, 3")
        for r in cur.fetchall():
            v = str(r['resp']).strip().upper()
            if v in ('SI', 'NO'):
                slot(r)['cq'][v] += int(r['n'])
        cur.execute("SELECT id_jornada, organismo, capacitacion_ley AS resp, COUNT(*) AS n "
                    "FROM presaber WHERE id_jornada IS NOT NULL GROUP BY 1, 2, 3")
        for r in cur.fetchall():
            v = str(r['resp']).strip().upper()
            if v in ('SI', 'NO'):
                slot(r)['cp'][v] += int(r['n'])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return det


def _sumar(lista):
    t = _vacio()
    for d in lista:
        for c in t['p']:
            t['p'][c][0] += d['p'][c][0]
            t['p'][c][1] += d['p'][c][1]
        for c in t['q']:
            t['q'][c][0] += d['q'][c][0]
            t['q'][c][1] += d['q'][c][1]
        for k in ('SI', 'NO'):
            t['cq'][k] += d['cq'][k]
            t['cp'][k] += d['cp'][k]
    return t


def _acierto(d):
    ok = sum(v[0] for v in d['p'].values())
    tot = sum(v[1] for v in d['p'].values())
    return (ok * 100.0 / tot) if tot else None


def _capacitados(d):
    si = d['cq']['SI'] + d['cp']['SI']
    tot = si + d['cq']['NO'] + d['cp']['NO']
    return si, tot


def _modo_detalle():
    try:
        from flask import request
        return request.args.get('detalle') == '1'
    except Exception:
        return False


def _org_filtro():
    try:
        from flask import request
        return ' '.join((request.args.get('org') or '').split()).upper()
    except Exception:
        return ''


def _filtrar(orgs):
    f = _org_filtro()
    if not f:
        return orgs, ''
    return [o for o in orgs if f in _norm(o['nombre'])], f


def _pj(o, jid, tipo):
    return o['por_jornada'].get(jid, {}).get(tipo, 0)


# ---------------------------- HTML ----------------------------------
def _html_resultados(d, nq, npres):
    d = d or _vacio()
    ac = _acierto(d)
    si, tot = _capacitados(d)
    h = ['<div class="mini">'
         '<div class="tarj"><b>%s</b>total de asistentes (quiz + presaber)</div>'
         '<div class="tarj"><b>%s</b>participantes quiz</div>'
         '<div class="tarj"><b>%s</b>acierto global del quiz</div>'
         '<div class="tarj"><b>%s</b>participantes presaber</div>'
         '<div class="tarj"><b>%s</b>capacitados en ley disciplinaria</div></div>'
         % (_n(nq + npres), _n(nq), ('%.0f%%' % ac) if ac is not None else '—', _n(npres),
            ('%s de %s' % (_n(si), _n(tot))) if tot else '—')]
    h.append('<div class="res2"><div><h5>Quiz · % de acierto por pregunta</h5>')
    for c, (ok, t) in d['p'].items():
        pct = ok * 100.0 / t if t else 0
        h.append('<div class="rb"><span class="rl" title="%s">%s</span><span class="rp"><i style="width:%.1f%%"></i></span>'
                 '<span class="rv">%s <small>(%s/%s)</small></span></div>'
                 % (_e(QUIZ_TEXTO[c]), _e(QUIZ_NOMBRE[c]), pct, ('%.0f%%' % pct) if t else '—', _n(ok), _n(t)))
    h.append('</div><div><h5>Presaber · % SI / NO por conducta</h5>')
    for c, label in PRESABER_LABELS.items():
        s, n = d['q'][c]
        t = s + n
        ps = s * 100.0 / t if t else 0
        pn = n * 100.0 / t if t else 0
        h.append('<div class="rb"><span class="rl" title="%s">%s</span><span class="rp"><i class="si" style="width:%.1f%%"></i>'
                 '<i class="no" style="width:%.1f%%"></i></span><span class="rv">SI %.0f%% · NO %.0f%%</span></div>'
                 % (_e(label), _e(PRESABER_NOMBRE[c]), ps, pn, ps, pn))
    h.append('</div></div>')
    return ''.join(h)


def _html_referencias():
    h = ['<h2>Referencia de preguntas</h2><h5>Quiz · pregunta y respuesta correcta</h5><table>'
         '<tr><th>Nombre</th><th>Pregunta</th><th>Respuesta correcta</th></tr>']
    for c, t in CORRECTAS_QUIZ.items():
        h.append('<tr><td><b>%s</b></td><td>%s</td><td>%s</td></tr>' % (_e(QUIZ_NOMBRE[c]), _e(QUIZ_TEXTO[c]), _e(t)))
    h.append('</table><h5>Presaber · conducta consultada (responde SI / NO)</h5><table>'
             '<tr><th>Nombre</th><th>Conducta</th></tr>')
    for c, t in PRESABER_LABELS.items():
        h.append('<tr><td><b>%s</b></td><td>%s</td></tr>' % (_e(PRESABER_NOMBRE[c]), _e(t)))
    h.append('</table>')
    return ''.join(h)


_CSS_EXTRA = """
h4{font-size:13pt;color:#1F3A5F;margin:18px 0 6px}
h5{font-size:12pt;margin:8px 0 6px;color:#1b2430}
.mini{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0}
.mini .tarj{min-width:140px;padding:8px 12px}
.mini .tarj b{font-size:16pt}
.res2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.org{page-break-inside:auto;break-inside:auto}
@media print{.vl{display:none}}
.rb{display:flex;align-items:center;gap:8px;margin:4px 0}
.rl{width:190px;font-weight:bold;flex:none}
.rp{flex:1;display:flex;height:20px;background:#eef2f7;border-radius:3px;overflow:hidden}
.rp i{display:block;height:100%;background:#1F3A5F}
.rp i.no{background:#A9B8CC}
.rv{width:120px;flex:none;font-size:12pt}
.jor{border-top:1px solid #dfe4ec;margin-top:12px;padding-top:4px;page-break-inside:avoid;break-inside:avoid}
.res-org{background:#f7f9fc;border-radius:8px;padding:6px 12px 10px;margin-top:12px}
@media (max-width:900px){.res2{grid-template-columns:1fr}}
"""


# ---------------------------- PDF (reportlab) -----------------------
def _chart_quiz(d):
    W = 12.0 * cm
    H = 0.64 * cm * len(CORRECTAS_QUIZ) + 1.1 * cm
    dr = Drawing(W, H)
    bc = HorizontalBarChart()
    bc.x = 4.9 * cm
    bc.y = 0.7 * cm
    bc.width = W - 4.9 * cm - 1.9 * cm
    bc.height = H - 0.9 * cm
    rev = list(reversed(list(CORRECTAS_QUIZ)))
    bc.data = [[(d['p'][c][0] * 100.0 / d['p'][c][1]) if d['p'][c][1] else 0 for c in rev]]
    bc.categoryAxis.categoryNames = [QUIZ_NOMBRE[c] for c in rev]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 12
    bc.categoryAxis.visibleTicks = 0
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 100
    bc.valueAxis.valueStep = 25
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 12
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_QUIZ
    bc.bars.strokeColor = None
    bc.barWidth = 11
    bc.barLabelFormat = '%0.0f%%'
    bc.barLabels.fontName = 'Helvetica'
    bc.barLabels.fontSize = 12
    bc.barLabels.boxAnchor = 'w'
    bc.barLabels.dx = 4
    dr.add(bc)
    return dr


def _chart_pres(d):
    W = 12.0 * cm
    H = 0.64 * cm * len(PRESABER_LABELS) + 1.1 * cm
    dr = Drawing(W, H)
    bc = HorizontalBarChart()
    bc.x = 4.9 * cm
    bc.y = 0.7 * cm
    bc.width = W - 4.9 * cm - 0.5 * cm
    bc.height = H - 0.9 * cm
    rev = list(reversed(list(PRESABER_LABELS)))
    si, no = [], []
    for c in rev:
        s, n = d['q'][c]
        t = s + n
        si.append(s * 100.0 / t if t else 0)
        no.append(n * 100.0 / t if t else 0)
    bc.data = [si, no]
    bc.categoryAxis.categoryNames = [PRESABER_NOMBRE[c] for c in rev]
    bc.categoryAxis.labels.fontName = 'Helvetica'
    bc.categoryAxis.labels.fontSize = 12
    bc.categoryAxis.style = 'stacked'
    bc.categoryAxis.visibleTicks = 0
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 100
    bc.valueAxis.valueStep = 25
    bc.valueAxis.labels.fontName = 'Helvetica'
    bc.valueAxis.labels.fontSize = 12
    bc.valueAxis.visibleGrid = 1
    bc.valueAxis.gridStrokeColor = colors.HexColor('#E3E7ED')
    bc.bars[0].fillColor = C_SI
    bc.bars[1].fillColor = C_NO
    bc.bars.strokeColor = None
    bc.barWidth = 11
    bc.barLabelFormat = lambda v: '' if v < 14 else '%d%%' % round(v)
    bc.barLabels.fontName = 'Helvetica'
    bc.barLabels.fontSize = 11
    bc.barLabels.boxAnchor = 'e'
    bc.barLabels.dx = -3
    bc.barLabels.fillColor = colors.black
    bc.barLabels[0].fillColor = colors.white
    dr.add(bc)
    return dr


def _pdf_resultados(d, nq, npres, TXT):
    d = d or _vacio()
    ac = _acierto(d)
    si, tot = _capacitados(d)
    t1 = Paragraph('Total de asistentes: <b>%s</b> · Quiz: <b>%s</b> · acierto global <b>%s</b>'
                   % (_n(nq + npres), _n(nq), ('%.0f%%' % ac) if ac is not None else '—'), TXT)
    t2 = Paragraph('Presaber: <b>%s</b> participantes · capacitados en la ley: <b>%s</b>'
                   % (_n(npres), ('%s de %s' % (_n(si), _n(tot))) if tot else '—'), TXT)
    tb = Table([[t1, t2]], colWidths=[12.4 * cm, 12.4 * cm])
    tb.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), GRIS), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 5),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    leg = Drawing(12.0 * cm, 0.5 * cm)
    leg.add(Rect(4.9 * cm, 1, 9, 9, fillColor=C_SI, strokeColor=None))
    leg.add(String(4.9 * cm + 14, 1, 'SI', fontName='Helvetica', fontSize=12))
    leg.add(Rect(4.9 * cm + 50, 1, 9, 9, fillColor=C_NO, strokeColor=None))
    leg.add(String(4.9 * cm + 64, 1, 'NO', fontName='Helvetica', fontSize=12))
    ch = Table([[[Paragraph('<b>Quiz · % de acierto por pregunta</b>', TXT), _chart_quiz(d)],
                 [Paragraph('<b>Presaber · % SI / NO por conducta</b>', TXT), leg, _chart_pres(d)]]],
               colWidths=[12.4 * cm, 12.4 * cm])
    ch.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    return [tb, Spacer(1, 4), ch]


def _pdf_referencias(H2, H3, TXT, CEL):
    out = [Paragraph('Referencia de preguntas', H2)]
    q = [['Nombre', 'Pregunta', 'Respuesta correcta']] + \
        [[Paragraph('<b>%s</b>' % escape(QUIZ_NOMBRE[c]), CEL), Paragraph(escape(QUIZ_TEXTO[c]), CEL),
          Paragraph(escape(t), CEL)] for c, t in CORRECTAS_QUIZ.items()]
    p = [['Nombre', 'Conducta consultada (SI / NO)']] + \
        [[Paragraph('<b>%s</b>' % escape(PRESABER_NOMBRE[c]), CEL), Paragraph(escape(t), CEL)]
         for c, t in PRESABER_LABELS.items()]
    est = TableStyle([('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                      ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 12),
                      ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.25, BORDE),
                      ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS])])
    t1 = Table(q, colWidths=[5.0 * cm, 10.3 * cm, 9.0 * cm], repeatRows=1)
    t1.setStyle(est)
    t2 = Table(p, colWidths=[5.0 * cm, 19.3 * cm], repeatRows=1)
    t2.setStyle(est)
    out += [t1, Spacer(1, 10), t2]
    return out
