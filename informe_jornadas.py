import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

NAVY = colors.HexColor('#1F3A5F')
GRIS = colors.HexColor('#EEF2F7')


def _fecha(f):
    s = str(f)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return s


def _n(v):
    return f"{int(v):,}".replace(',', '.')


def generar_informe_pdf(filas):
    """filas: lista de dicts con claves en minuscula:
    id_jornada, nombre, fecha, estado, quiz, ciudadanos, presaber"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title='Informe de jornadas - ENCUESTAS')

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle('H1', parent=ss['Title'], fontName='Helvetica-Bold',
                        fontSize=18, textColor=NAVY, alignment=0, spaceAfter=4)
    H2 = ParagraphStyle('H2', parent=ss['Heading2'], fontName='Helvetica-Bold',
                        fontSize=12, textColor=NAVY, spaceBefore=12, spaceAfter=6)
    TXT = ParagraphStyle('TXT', parent=ss['Normal'], fontName='Helvetica', fontSize=9.5, leading=13)
    CEL = ParagraphStyle('CEL', parent=TXT, fontSize=8, leading=10)
    BUL = ParagraphStyle('BUL', parent=TXT, leftIndent=12, bulletIndent=2, spaceAfter=3)

    for f in filas:
        f['quiz'] = int(f.get('quiz') or 0)
        f['ciudadanos'] = int(f.get('ciudadanos') or 0)
        f['presaber'] = int(f.get('presaber') or 0)
        f['total'] = f['quiz'] + f['ciudadanos'] + f['presaber']

    tq = sum(f['quiz'] for f in filas)
    tc = sum(f['ciudadanos'] for f in filas)
    tp = sum(f['presaber'] for f in filas)
    tt = tq + tc + tp
    unicas = tp + tc

    S = []
    S.append(Paragraph('Informe de jornadas - ENCUESTAS', H1))
    S.append(Paragraph(
        f'Alcaldía de Cali - Control Disciplinario. Generado el '
        f'{datetime.now().strftime("%d/%m/%Y %H:%M")}.', TXT))

    S.append(Paragraph('Resumen general', H2))
    S.append(Paragraph(
        f'Total de jornadas: <b>{_n(len(filas))}</b>. Encuestas registradas: <b>{_n(tt)}</b> '
        f'(quiz {_n(tq)}, ciudadano {_n(tc)}, presaber {_n(tp)}). '
        f'Personas únicas (presaber + ciudadano): <b>{_n(unicas)}</b>.', TXT))

    # Detalle por jornada
    S.append(Paragraph('Detalle por jornada', H2))
    datos = [['ID', 'Jornada', 'Fecha', 'Estado', 'Quiz', 'Ciudadano', 'Presaber', 'Total']]
    for f in filas:
        datos.append([
            str(f['id_jornada']),
            Paragraph(escape(str(f.get('nombre') or '-')), CEL),
            _fecha(f.get('fecha')),
            str(f.get('estado') or '-'),
            _n(f['quiz']), _n(f['ciudadanos']), _n(f['presaber']), _n(f['total'])])
    datos.append(['', 'TOTAL', '', '', _n(tq), _n(tc), _n(tp), _n(tt)])
    anchos = [1.3 * cm, 10.5 * cm, 2.5 * cm, 2.3 * cm, 1.7 * cm, 2.2 * cm, 2.2 * cm, 2.0 * cm]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRIS]),
        ('BACKGROUND', (0, -1), (-1, -1), GRIS),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#C5CCD6')),
    ]))
    S.append(t)

    # Consolidado
    S.append(Paragraph('Consolidado', H2))
    cons = [['Tipo de encuesta', 'Encuestados'],
            ['Quiz', _n(tq)], ['Ciudadano', _n(tc)], ['Presaber', _n(tp)],
            ['Total encuestas', _n(tt)], ['Personas únicas (presaber + ciudadano)', _n(unicas)]]
    c = Table(cons, colWidths=[9 * cm, 4 * cm])
    c.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#C5CCD6')),
    ]))
    S.append(c)

    # Observaciones (calculadas)
    obs = []
    if tc == 0:
        obs.append('La encuesta de ciudadano no tiene respuestas en ninguna jornada.')
    vacias = [f for f in filas if f['total'] == 0]
    if vacias:
        ids = ', '.join(str(f['id_jornada']) for f in vacias)
        activas = [str(f['id_jornada']) for f in vacias if str(f.get('estado')).upper() == 'ACTIVA']
        txt = f'{len(vacias)} jornada(s) sin respuestas: IDs {ids}.'
        if activas:
            txt += f' Siguen en estado ACTIVA: {", ".join(activas)}.'
        obs.append(txt)
    grupos = {}
    for f in filas:
        k = (str(f.get('nombre') or '').strip().lower(), str(f.get('fecha'))[:10])
        grupos.setdefault(k, []).append(f)
    for k, g in grupos.items():
        if len(g) > 1 and k[0]:
            ids = ' y '.join(str(x['id_jornada']) for x in g)
            obs.append(f'Las jornadas {ids} tienen el mismo nombre y fecha ({_fecha(k[1])}); '
                       f'podrían ser una sola.')
    if obs:
        S.append(Paragraph('Observaciones', H2))
        for o in obs:
            S.append(Paragraph(escape(o), BUL, bulletText='•'))

    def pie(canvas, d):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(landscape(letter)[0] - 1.5 * cm, 0.8 * cm, f'Página {d.page}')
        canvas.restoreState()

    doc.build(S, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
