from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from db import get_connection
from datetime import date, datetime, timedelta
import functools
import uuid

app = Flask(__name__)
app.config.from_object('config.Config')

COOKIE_DISPOSITIVO = 'encuestass_device_id'
COOKIE_DURACION_DIAS = 365

def row(r):
    """Normaliza una fila de PostgreSQL (claves minúsculas) a mayúsculas
    para compatibilidad con el código que usa r['COLUMNA']."""
    if r is None:
        return None
    if hasattr(r, 'keys'):
        return {k.upper(): v for k, v in r.items()}
    return r

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if 'usuario_id' not in session and 'invitado_jornada_id' not in session:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if session.get('rol') != 1:
            flash('Acceso restringido a administradores')
            return redirect(url_for('menu'))
        return view(*args, **kwargs)
    return wrapped

def es_admin():
    return session.get('rol') == 1

def get_jornada_activa():
    if 'invitado_jornada_id' in session:
        jornada_id = session['invitado_jornada_id']
    else:
        jornada_id = session.get('jornada_id')
    if not jornada_id:
        return None
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM jornadas WHERE ID_JORNADA=%s", (jornada_id,))
        jornada = cur.fetchone()
    conn.close()
    return jornada

def encuestas_de_jornada(jornada):
    """Devuelve lista de encuestas que PERTENECEN a la jornada
    (independiente de si están activas ahora mismo o no).
    Usado por el administrador para ver/gestionar todo el conjunto."""
    if not jornada:
        return []
    enc = []
    if jornada.get('ENC_QUIZ'):
        enc.append('quiz')
    if jornada.get('ENC_PRESABER'):
        enc.append('presaber')
    if jornada.get('ENC_CIUDADANOS'):
        enc.append('ciudadanos')
    return enc

def encuestas_activas_jornada(jornada):
    """Devuelve lista de encuestas que el INVITADO puede contestar
    AHORA MISMO. El administrador las prende/apaga en tiempo real
    desde la pantalla de Jornadas, sin importar cuáles pertenecen
    a la jornada en general."""
    if not jornada:
        return []
    enc = []
    if jornada.get('ENC_QUIZ_ACTIVA'):
        enc.append('quiz')
    if jornada.get('ENC_PRESABER_ACTIVA'):
        enc.append('presaber')
    if jornada.get('ENC_CIUDADANOS_ACTIVA'):
        enc.append('ciudadanos')
    return enc

def primera_encuesta_url(jornada):
    """URL de la primera encuesta ACTIVA en este momento."""
    enc = encuestas_activas_jornada(jornada)
    if not enc:
        return url_for('menu')
    if enc[0] == 'quiz':
        return url_for('preguntas')
    if enc[0] == 'presaber':
        return url_for('presaber')
    return url_for('ciudadanos')


def url_de_encuesta(nombre):
    if nombre == 'quiz':
        return url_for('preguntas')
    if nombre == 'presaber':
        return url_for('presaber')
    return url_for('ciudadanos')


def guardar_snapshot_respuesta(nombre_encuesta, titulo, pares):
    """Guarda en sesión una copia legible de la encuesta recién
    respondida, para mostrarla luego en el resumen del invitado.
    `pares` es una lista de tuplas (pregunta, respuesta)."""
    snapshots = session.get('mis_respuestas', [])
    snapshots.append({'encuesta': nombre_encuesta, 'titulo': titulo, 'pares': pares})
    session['mis_respuestas'] = snapshots


def siguiente_paso_invitado(encuesta_recien_completada):
    """
    Tras guardar una encuesta como invitado:
    - Si quedan otras encuestas activas de la jornada sin responder,
      lo manda a la siguiente (con aviso) para completar el proceso.
    - Si ya completó todas las encuestas activas, cierra su sesión
      y lo regresa a la pantalla de PIN.
    - Antes de cerrar, vuelve a consultar la jornada en vivo: si el
      administrador activó una nueva encuesta mientras el invitado
      respondía otra, se le pide completarla también.
    Si no es invitado, devuelve None (sin acción especial).
    """
    if session.get('rol') != 0:
        return None

    token = session.get('device_token')
    id_jornada = session.get('invitado_jornada_id')
    if token and id_jornada:
        marcar_encuesta_respondida_dispositivo(token, id_jornada, encuesta_recien_completada)

    pendientes = session.get('pendientes_jornada', [])
    if encuesta_recien_completada in pendientes:
        pendientes = [e for e in pendientes if e != encuesta_recien_completada]

    if not pendientes:
        # Revisar si el admin activó alguna encuesta nueva mientras
        # el invitado estaba respondiendo (ej: activó Quiz a mitad
        # de la jornada). Solo se piden las que aún no respondió.
        jornada_actual = get_jornada_activa()
        activas_ahora = encuestas_activas_jornada(jornada_actual)
        ya_respondidas = {b['encuesta'] for b in session.get('mis_respuestas', [])}
        pendientes = [e for e in activas_ahora if e not in ya_respondidas]

    session['pendientes_jornada'] = pendientes

    if pendientes:
        # Verificar si las encuestas pendientes están activas ahora
        jornada_actual = get_jornada_activa()
        activas_ahora = encuestas_activas_jornada(jornada_actual)
        pendientes_activos = [e for e in pendientes if e in activas_ahora]
        pendientes_inactivos = [e for e in pendientes if e not in activas_ahora]

        if pendientes_activos:
            # Hay encuestas pendientes Y activas — ir a la siguiente
            flash('✓ Encuesta guardada. Ahora complete la siguiente encuesta para terminar el proceso.')
            return redirect(url_de_encuesta(pendientes_activos[0]))
        else:
            # Hay encuestas pendientes pero el admin aún NO las activó
            # Mandar a pantalla de espera con auto-refresh
            nombres = ', '.join(e.upper() for e in pendientes_inactivos)
            session['esperando_encuestas'] = pendientes_inactivos
            flash(f'✓ Encuesta guardada. Por favor espere mientras el administrador activa: {nombres}')
            return redirect(url_for('espera_activa'))

    flash('✓ Encuesta guardada correctamente. Ha completado todas las encuestas de esta jornada.')
    return redirect(url_for('resumen_invitado'))


def encuesta_bloqueada_para_invitado(nombre_encuesta, jornada):
    """True si un invitado NO debe poder acceder a esta encuesta
    en este momento (el admin no la ha activado todavía)."""
    if session.get('rol') != 0:
        return False  # el admin siempre puede entrar a probar/ver formularios
    activas = encuestas_activas_jornada(jornada)
    return nombre_encuesta not in activas


# ---------------------------------------------------------
# Control de dispositivo único por jornada
# (cookie persistente + registro en BD para permitir
#  reanudar si se cae el internet, pero bloquear reintentos
#  de jornadas ya completadas desde el mismo celular)
# ---------------------------------------------------------
def obtener_o_crear_device_token():
    """Lee la cookie de dispositivo si existe; si no, genera una nueva.
    Devuelve (token, es_nuevo)."""
    token = request.cookies.get(COOKIE_DISPOSITIVO)
    if token:
        return token, False
    return str(uuid.uuid4()), True


def consultar_dispositivo_jornada(token, id_jornada):
    """Devuelve el registro de dispositivos_jornada para este token+jornada, o None."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM dispositivos_jornada WHERE DISPOSITIVO_TOKEN=%s AND ID_JORNADA=%s",
            (token, id_jornada)
        )
        row = cur.fetchone()
    conn.close()
    return row


def registrar_dispositivo_jornada(token, id_jornada):
    """Crea el registro de seguimiento si no existe."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ID FROM dispositivos_jornada WHERE DISPOSITIVO_TOKEN=%s AND ID_JORNADA=%s",
            (token, id_jornada)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO dispositivos_jornada (DISPOSITIVO_TOKEN, ID_JORNADA, IP_REGISTRO) VALUES (%s,%s,%s)",
                (token, id_jornada, request.remote_addr)
            )
    conn.commit()
    conn.close()


def marcar_encuesta_respondida_dispositivo(token, id_jornada, nombre_encuesta):
    """Agrega la encuesta a la lista de respondidas de este dispositivo
    para esta jornada, y marca COMPLETADO si ya no quedan pendientes
    entre las encuestas que estaban activas."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT RESPONDIDAS FROM dispositivos_jornada WHERE DISPOSITIVO_TOKEN=%s AND ID_JORNADA=%s",
            (token, id_jornada)
        )
        row = cur.fetchone()
        respondidas = set(row['RESPONDIDAS'].split(',')) if row and row['RESPONDIDAS'] else set()
        respondidas.discard('')
        respondidas.add(nombre_encuesta)
        nuevas = ','.join(sorted(respondidas))

        cur.execute(
            "SELECT ENC_QUIZ_ACTIVA, ENC_PRESABER_ACTIVA, ENC_CIUDADANOS_ACTIVA FROM jornadas WHERE ID_JORNADA=%s",
            (id_jornada,)
        )
        jrow = cur.fetchone()
        activas = encuestas_activas_jornada(jrow) if jrow else []
        completado = 1 if activas and all(e in respondidas for e in activas) else 0

        cur.execute(
            "UPDATE dispositivos_jornada SET RESPONDIDAS=%s, COMPLETADO=%s WHERE DISPOSITIVO_TOKEN=%s AND ID_JORNADA=%s",
            (nuevas, completado, token, id_jornada)
        )
    conn.commit()
    conn.close()
    return respondidas, bool(completado)


# ---------------------------------------------------------
# LOGIN UNIFICADO
# ---------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        tipo = request.form.get('tipo')

        # --- Admin ---
        if tipo == 'admin':
            usuario = request.form.get('usuario', '')
            password = request.form.get('password', '')
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM usuarios WHERE USUARIO=%s AND PASSWORD=%s AND ESTADO=1",
                    (usuario, password)
                )
                user = cur.fetchone()
            conn.close()
            if user:
                session['usuario_id'] = user['IDUSUARIO']
                session['usuario'] = user['USUARIO']
                session['rol'] = user['ROL']
                return redirect(url_for('menu'))
            flash('Usuario o contraseña incorrectos')

        # --- Invitado por PIN ---
        elif tipo == 'pin':
            pin = request.form.get('pin', '').strip()
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM jornadas WHERE PIN=%s AND ESTADO='ACTIVA'",
                    (pin,)
                )
                jornada = cur.fetchone()
            conn.close()

            if not jornada:
                flash('PIN incorrecto o jornada no activa')
                return render_template('login.html')

            id_jornada = jornada['ID_JORNADA']
            token, es_nuevo = obtener_o_crear_device_token()
            registro = consultar_dispositivo_jornada(token, id_jornada)

            # Si este dispositivo ya completó TODAS las encuestas de
            # esta jornada, se bloquea un nuevo intento.
            if registro and registro.get('COMPLETADO'):
                flash('Este dispositivo ya completó las encuestas de esta jornada. No es posible volver a contestar.')
                resp = make_response(render_template('login.html'))
                if es_nuevo:
                    resp.set_cookie(COOKIE_DISPOSITIVO, token,
                        max_age=COOKIE_DURACION_DIAS * 86400, httponly=True, samesite='Lax')
                return resp

            enc_activas = encuestas_activas_jornada(jornada)
            if not enc_activas:
                flash('Aún no hay ninguna encuesta habilitada para esta jornada. Por favor espera a que el administrador la active.')
                return render_template('login.html')

            # Ya respondidas por este dispositivo (si venía retomando tras perder conexión)
            ya_respondidas = set()
            if registro and registro.get('RESPONDIDAS'):
                ya_respondidas = set(registro['RESPONDIDAS'].split(','))
                ya_respondidas.discard('')

            registrar_dispositivo_jornada(token, id_jornada)

            session.clear()
            session['invitado_jornada_id'] = id_jornada
            session['usuario'] = 'Invitado'
            session['rol'] = 0
            session['jornada_nombre'] = jornada['NOMBRE']
            session['device_token'] = token
            session['encuestas_jornada'] = enc_activas
            # Solo quedan pendientes las que aún no había respondido este dispositivo
            pendientes = [e for e in enc_activas if e not in ya_respondidas]
            session['pendientes_jornada'] = pendientes

            if ya_respondidas:
                flash('Hemos detectado respuestas previas de este dispositivo. Continuando donde lo dejaste.')

            resp = make_response(redirect(primera_encuesta_url(jornada) if pendientes else url_for('resumen_invitado')))
            if es_nuevo:
                resp.set_cookie(COOKIE_DISPOSITIVO, token,
                    max_age=COOKIE_DURACION_DIAS * 86400, httponly=True, samesite='Lax')
            return resp

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------
# MENU (solo admin llega aquí; invitado va directo a encuesta)
# ---------------------------------------------------------
@app.route('/menu')
@login_required
def menu():
    jornada = get_jornada_activa()
    if session.get('rol') == 0:
        activas = encuestas_activas_jornada(jornada)
        return render_template('espera_invitado.html', jornada=jornada, activas=activas)
    return render_template('menu.html', jornada=jornada, admin=es_admin())


# ---------------------------------------------------------
# JORNADAS (solo admin)
# ---------------------------------------------------------
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

        enc_ciudadanos = 1 if f.get('enc_ciudadanos') else 0
        enc_quiz       = 1 if f.get('enc_quiz') else 0
        enc_presaber   = 1 if f.get('enc_presaber') else 0
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


@app.route('/jornadas/activar/<int:id_jornada>')
@login_required
@admin_required
def jornadas_activar(id_jornada):
    session['jornada_id'] = id_jornada
    flash('Jornada activada')
    return redirect(request.referrer or url_for('jornadas'))


@app.route('/jornadas/desactivar')
@login_required
@admin_required
def jornadas_desactivar():
    session.pop('jornada_id', None)
    flash('Jornada desactivada')
    return redirect(request.referrer or url_for('jornadas'))


@app.route('/jornadas/cerrar/<int:id_jornada>')
@login_required
@admin_required
def jornadas_cerrar(id_jornada):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE jornadas SET ESTADO='CERRADA' WHERE ID_JORNADA=%s", (id_jornada,))
    conn.close()
    flash('Jornada cerrada')
    return redirect(url_for('jornadas'))


@app.route('/jornadas/<int:id_jornada>/toggle_encuesta/<string:nombre>')
@login_required
@admin_required
def jornadas_toggle_encuesta(id_jornada, nombre):
    """Prende/apaga en vivo el acceso del invitado a Quiz, Presaber
    o Ciudadanos, sin afectar cuáles encuestas pertenecen a la jornada."""
    columnas = {
        'quiz': 'ENC_QUIZ_ACTIVA',
        'presaber': 'ENC_PRESABER_ACTIVA',
        'ciudadanos': 'ENC_CIUDADANOS_ACTIVA',
    }
    if nombre not in columnas:
        flash('Encuesta no válida')
        return redirect(url_for('jornadas'))

    col = columnas[nombre]
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(f"UPDATE jornadas SET {col} = NOT {col}::boolean WHERE ID_JORNADA=%s", (id_jornada,))
    conn.commit()
    conn.close()
    flash(f'Estado de {nombre.upper()} actualizado para los encuestadores')
    return redirect(request.referrer or url_for('jornadas'))


@app.route('/jornadas/<int:id_jornada>')
@login_required
@admin_required
def jornadas_detalle(id_jornada):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM jornadas WHERE ID_JORNADA=%s", (id_jornada,))
        jornada = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS TOTAL FROM encuestas_ciudadanos WHERE ID_JORNADA=%s", (id_jornada,))
        total_ciudadanos = cur.fetchone()['TOTAL']
        cur.execute("SELECT COUNT(*) AS TOTAL FROM preguntas WHERE ID_JORNADA=%s", (id_jornada,))
        total_preguntas = cur.fetchone()['TOTAL']
        cur.execute("SELECT COUNT(*) AS TOTAL FROM presaber WHERE ID_JORNADA=%s", (id_jornada,))
        total_presaber = cur.fetchone()['TOTAL']
    conn.close()
    if not jornada:
        flash('Jornada no encontrada')
        return redirect(url_for('jornadas'))
    total_general = total_ciudadanos + total_preguntas + total_presaber
    meta = jornada.get('META_ENCUESTADOS') or 0
    porcentaje = round((total_general / meta) * 100, 1) if meta > 0 else None
    return render_template('jornada_detalle.html',
        jornada=jornada, total_ciudadanos=total_ciudadanos,
        total_preguntas=total_preguntas, total_presaber=total_presaber,
        total_general=total_general, porcentaje=porcentaje, admin=es_admin())


# ---------------------------------------------------------
# DASHBOARD DE JORNADA
# ---------------------------------------------------------
@app.route('/dashboard/<int:id_jornada>')
@login_required
@admin_required
def dashboard(id_jornada):
    conn = get_connection()
    with conn.cursor() as cur:
        # Info jornada
        cur.execute("SELECT * FROM jornadas WHERE ID_JORNADA=%s", (id_jornada,))
        jornada = cur.fetchone()
        if not jornada:
            conn.close()
            flash('Jornada no encontrada')
            return redirect(url_for('menu'))

        # ── TOTALES CORRECTOS ──
        # Presaber = persona única cuando hay Quiz+Presaber
        # Ciudadanos = persona única para jornadas ciudadanas
        cur.execute("SELECT COUNT(*) AS T FROM encuestas_ciudadanos WHERE ID_JORNADA=%s", (id_jornada,))
        total_ciudadanos = cur.fetchone()['T']
        cur.execute("SELECT COUNT(*) AS T FROM preguntas WHERE ID_JORNADA=%s", (id_jornada,))
        total_quiz = cur.fetchone()['T']
        cur.execute("SELECT COUNT(*) AS T FROM presaber WHERE ID_JORNADA=%s", (id_jornada,))
        total_presaber = cur.fetchone()['T']

        # Personas únicas: Presaber cuenta como persona cuando hay encuestas servidor
        # Ciudadanos cuenta cuando hay encuestas ciudadanas
        personas_servidor = total_presaber  # Presaber siempre primero → 1 persona
        personas_ciudadano = total_ciudadanos
        total_personas = personas_servidor + personas_ciudadano

        # ── DISTRIBUCIÓN POR ORGANISMO (quiz) ──
        cur.execute("""
            SELECT COALESCE(NOMBRE_ORGANISMO,'Sin organismo') AS ORG, COUNT(*) AS CNT
            FROM preguntas WHERE ID_JORNADA=%s
            GROUP BY NOMBRE_ORGANISMO ORDER BY cnt DESC
        """, (id_jornada,))
        dist_organismo_quiz = cur.fetchall()

        # ── DISTRIBUCIÓN POR ORGANISMO (presaber) ──
        cur.execute("""
            SELECT COALESCE(ORGANISMO,'Sin organismo') AS ORG, COUNT(*) AS CNT
            FROM presaber WHERE ID_JORNADA=%s
            GROUP BY ORGANISMO ORDER BY cnt DESC
        """, (id_jornada,))
        dist_organismo_presaber = cur.fetchall()

        # ── DISTRIBUCIÓN POR CARGO ──
        cur.execute("""
            SELECT COALESCE(UPPER(CARGO),'Sin cargo') AS CARGO, COUNT(*) AS CNT
            FROM preguntas WHERE ID_JORNADA=%s AND CARGO IS NOT NULL AND CARGO!=''
            GROUP BY UPPER(CARGO) ORDER BY cnt DESC LIMIT 15
        """, (id_jornada,))
        dist_cargo_quiz = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(UPPER(CARGO),'Sin cargo') AS CARGO, COUNT(*) AS CNT
            FROM presaber WHERE ID_JORNADA=%s AND CARGO IS NOT NULL AND CARGO!=''
            GROUP BY UPPER(CARGO) ORDER BY cnt DESC LIMIT 15
        """, (id_jornada,))
        dist_cargo_presaber = cur.fetchall()

        # ── DISTRIBUCIÓN POR PROFESIÓN ──
        cur.execute("""
            SELECT COALESCE(UPPER(PROFESION),'Sin profesión') AS PROF, COUNT(*) AS CNT
            FROM preguntas WHERE ID_JORNADA=%s AND PROFESION IS NOT NULL AND PROFESION!=''
            GROUP BY UPPER(PROFESION) ORDER BY cnt DESC LIMIT 15
        """, (id_jornada,))
        dist_prof_quiz = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(UPPER(PROFESION),'Sin profesión') AS PROF, COUNT(*) AS CNT
            FROM presaber WHERE ID_JORNADA=%s AND PROFESION IS NOT NULL AND PROFESION!=''
            GROUP BY UPPER(PROFESION) ORDER BY cnt DESC LIMIT 15
        """, (id_jornada,))
        dist_prof_presaber = cur.fetchall()

        # ── RESPUESTAS QUIZ (correctas = opción correcta por pregunta) ──
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
        quiz_stats = {}
        if total_quiz > 0:
            for col, correcta in CORRECTAS_QUIZ.items():
                cur.execute(f"""
                    SELECT {col} AS RESP, COUNT(*) AS CNT
                    FROM preguntas WHERE ID_JORNADA=%s AND {col} IS NOT NULL
                    GROUP BY {col}
                """, (id_jornada,))
                rows = cur.fetchall()
                total_resp = sum(r['CNT'] for r in rows)
                correctas = sum(r['CNT'] for r in rows if r['RESP'] and correcta.lower() in r['RESP'].lower())
                quiz_stats[col] = {
                    'correctas': correctas,
                    'incorrectas': total_resp - correctas,
                    'total': total_resp,
                    'pct': round(correctas / total_resp * 100, 1) if total_resp else 0
                }

        # ── RESULTADOS PRESABER (% SI / NO por conducta) ──
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
        presaber_stats = {}
        if total_presaber > 0:
            for col, label in PRESABER_LABELS.items():
                cur.execute(f"""
                    SELECT {col} AS RESP, COUNT(*) AS CNT
                    FROM presaber WHERE ID_JORNADA=%s AND {col} IS NOT NULL
                    GROUP BY {col}
                """, (id_jornada,))
                rows = cur.fetchall()
                total_r = sum(r['CNT'] for r in rows)
                si = sum(r['CNT'] for r in rows if r['RESP'] == 'SI')
                no = sum(r['CNT'] for r in rows if r['RESP'] == 'NO')
                presaber_stats[col] = {
                    'label': label,
                    'si': si, 'no': no, 'total': total_r,
                    'pct_si': round(si / total_r * 100, 1) if total_r else 0,
                    'pct_no': round(no / total_r * 100, 1) if total_r else 0,
                }

        # ── RESULTADOS CIUDADANOS ──
        CIUDADANOS_LABELS = {
            'Pregunta_1': 'Pregunta 1',
            'Pregunta_2': 'Pregunta 2',
            'Pregunta_3': 'Pregunta 3',
            'Pregunta_4': 'Pregunta 4',
            'Pregunta_5': 'Pregunta 5',
            'Pregunta_6': 'Pregunta 6',
            'Pregunta_7': 'Pregunta 7',
        }
        ciudadanos_stats = {}
        if total_ciudadanos > 0:
            for col, label in CIUDADANOS_LABELS.items():
                cur.execute(f"""
                    SELECT {col} AS RESP, COUNT(*) AS CNT
                    FROM encuestas_ciudadanos WHERE ID_JORNADA=%s AND {col} IS NOT NULL
                    GROUP BY {col}
                """, (id_jornada,))
                rows = cur.fetchall()
                total_r = sum(r['CNT'] for r in rows)
                si = sum(r['CNT'] for r in rows if str(r['RESP']).upper() in ('SI','1'))
                no = sum(r['CNT'] for r in rows if str(r['RESP']).upper() in ('NO','0'))
                ciudadanos_stats[col] = {
                    'label': label,
                    'si': si, 'no': no, 'total': total_r,
                    'pct_si': round(si / total_r * 100, 1) if total_r else 0,
                    'pct_no': round(no / total_r * 100, 1) if total_r else 0,
                }

        # ── CAPACITACIÓN (quiz y presaber) ──
        cur.execute("""
            SELECT CAPACITACION_LEY_DISCIPLINARIA AS RESP, COUNT(*) AS CNT
            FROM preguntas WHERE ID_JORNADA=%s AND CAPACITACION_LEY_DISCIPLINARIA IS NOT NULL
            GROUP BY CAPACITACION_LEY_DISCIPLINARIA
        """, (id_jornada,))
        cap_quiz = {r['RESP']: r['CNT'] for r in cur.fetchall()}

        cur.execute("""
            SELECT CAPACITACION_LEY AS RESP, COUNT(*) AS CNT
            FROM presaber WHERE ID_JORNADA=%s AND CAPACITACION_LEY IS NOT NULL
            GROUP BY CAPACITACION_LEY
        """, (id_jornada,))
        cap_presaber = {r['RESP']: r['CNT'] for r in cur.fetchall()}

        # ── SERVIDOR PUBLICO ──
        cur.execute("""
            SELECT SERVIDOR_PUBLICO_PLANTA AS RESP, COUNT(*) AS CNT
            FROM preguntas WHERE ID_JORNADA=%s AND SERVIDOR_PUBLICO_PLANTA IS NOT NULL
            GROUP BY SERVIDOR_PUBLICO_PLANTA
        """, (id_jornada,))
        servidor_quiz = {r['RESP']: r['CNT'] for r in cur.fetchall()}

    conn.close()

    total_general = total_ciudadanos + total_quiz + total_presaber
    meta = jornada.get('META_ENCUESTADOS') or 0
    pct_meta = round(total_personas / meta * 100, 1) if meta > 0 else None

    return render_template('dashboard.html',
        jornada=jornada,
        admin=es_admin(),
        total_ciudadanos=total_ciudadanos,
        total_quiz=total_quiz,
        total_presaber=total_presaber,
        total_general=total_general,
        total_personas=total_personas,
        personas_servidor=personas_servidor,
        personas_ciudadano=personas_ciudadano,
        meta=meta,
        pct_meta=pct_meta,
        dist_organismo_quiz=dist_organismo_quiz,
        dist_organismo_presaber=dist_organismo_presaber,
        dist_cargo_quiz=dist_cargo_quiz,
        dist_cargo_presaber=dist_cargo_presaber,
        dist_prof_quiz=dist_prof_quiz,
        dist_prof_presaber=dist_prof_presaber,
        quiz_stats=quiz_stats,
        presaber_stats=presaber_stats,
        ciudadanos_stats=ciudadanos_stats,
        cap_quiz=cap_quiz,
        cap_presaber=cap_presaber,
        servidor_quiz=servidor_quiz,
    )


# ---------------------------------------------------------
# API organismo → educacion
# ---------------------------------------------------------
@app.route('/api/organismo_es_educacion/<int:id_organismo>')
@login_required
def api_organismo_es_educacion(id_organismo):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT ORGANISMO FROM organismos WHERE ID_ORGANISMO=%s", (id_organismo,))
        row = cur.fetchone()
    conn.close()
    es_educacion = bool(row and row['ORGANISMO'] and
                        row['ORGANISMO'].strip().upper() == 'SECRETARIA DE EDUCACION')
    return jsonify({'es_educacion': es_educacion})


# ---------------------------------------------------------
# API: estado de encuestas activas de la jornada (polling)
# El celular del invitado consulta esto cada 5 segundos
# para saber si el admin activó la siguiente encuesta.
# ---------------------------------------------------------
@app.route('/api/estado_jornada/<int:id_jornada>')
@login_required
def api_estado_jornada(id_jornada):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ENC_QUIZ_ACTIVA, ENC_PRESABER_ACTIVA, ENC_CIUDADANOS_ACTIVA
            FROM jornadas WHERE ID_JORNADA=%s
        """, (id_jornada,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Jornada no encontrada'}), 404
    activas = encuestas_activas_jornada(row)
    return jsonify({'activas': activas})


# ---------------------------------------------------------
# API sugerencias de Cargo y Profesión
# ---------------------------------------------------------
@app.route('/api/sugerencias')
@login_required
def api_sugerencias():
    conn = get_connection()
    with conn.cursor() as cur:
        # Cargos de preguntas y presaber
        cur.execute("""
            SELECT DISTINCT UPPER(CARGO) AS VAL FROM preguntas WHERE CARGO IS NOT NULL AND CARGO != ''
            UNION
            SELECT DISTINCT UPPER(CARGO) FROM presaber WHERE CARGO IS NOT NULL AND CARGO != ''
            ORDER BY val
        """)
        cargos = [r['VAL'] for r in cur.fetchall()]
        # Profesiones de preguntas y presaber
        cur.execute("""
            SELECT DISTINCT UPPER(PROFESION) AS VAL FROM preguntas WHERE PROFESION IS NOT NULL AND PROFESION != ''
            UNION
            SELECT DISTINCT UPPER(PROFESION) FROM presaber WHERE PROFESION IS NOT NULL AND PROFESION != ''
            ORDER BY val
        """)
        profesiones = [r['VAL'] for r in cur.fetchall()]
        # Estudios de ciudadanos
        cur.execute("""
            SELECT DISTINCT UPPER(ESTUDIOS) AS VAL FROM encuestas_ciudadanos
            WHERE ESTUDIOS IS NOT NULL AND ESTUDIOS != ''
            ORDER BY val
        """)
        estudios = [r['VAL'] for r in cur.fetchall()]
        # Ocupaciones de ciudadanos
        cur.execute("""
            SELECT DISTINCT UPPER(OCUPACION) AS VAL FROM encuestas_ciudadanos
            WHERE OCUPACION IS NOT NULL AND OCUPACION != ''
            ORDER BY val
        """)
        ocupaciones = [r['VAL'] for r in cur.fetchall()]
    conn.close()
    return jsonify({
        'cargos': cargos,
        'profesiones': profesiones,
        'estudios': estudios,
        'ocupaciones': ocupaciones
    })


# ---------------------------------------------------------
# API: estado actual de encuestas activas para una jornada
# Usada por el polling de la pantalla de espera del invitado
# ---------------------------------------------------------
@app.route('/api/encuestas_activas/<int:id_jornada>')
def api_encuestas_activas(id_jornada):
    """Devuelve qué encuestas están activas en este momento
    para una jornada. No requiere login para poder usarla
    desde la pantalla de espera del invitado."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ENC_QUIZ_ACTIVA, ENC_PRESABER_ACTIVA, ENC_CIUDADANOS_ACTIVA
            FROM jornadas WHERE ID_JORNADA=%s AND ESTADO='ACTIVA'
        """, (id_jornada,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({'activas': []})
    activas = []
    if row['ENC_PRESABER_ACTIVA']:
        activas.append('presaber')
    if row['ENC_QUIZ_ACTIVA']:
        activas.append('quiz')
    if row['ENC_CIUDADANOS_ACTIVA']:
        activas.append('ciudadanos')
    return jsonify({'activas': activas})


@app.route('/resumen_invitado')
@login_required
def resumen_invitado():
    if session.get('rol') != 0:
        return redirect(url_for('menu'))
    respuestas = session.get('mis_respuestas', [])
    jornada_nombre = session.get('jornada_nombre', 'la jornada')
    return render_template('resumen_invitado.html',
        respuestas=respuestas, jornada_nombre=jornada_nombre)


@app.route('/finalizar_invitado')
def finalizar_invitado():
    """Cierra la sesión del invitado tras ver su resumen."""
    session.clear()
    flash('Gracias por participar. ¡Hasta pronto!')
    return redirect(url_for('login'))


@app.route('/espera_activa')
@login_required
def espera_activa():
    """Pantalla de espera con auto-refresh cada 5 segundos.
    Cuando el admin activa la siguiente encuesta, redirige automáticamente."""
    if session.get('rol') != 0:
        return redirect(url_for('menu'))

    id_jornada = session.get('invitado_jornada_id')
    esperando = session.get('esperando_encuestas', [])
    jornada_nombre = session.get('jornada_nombre', 'la jornada')

    # Verificar si ya se activó alguna de las encuestas esperadas
    jornada_actual = get_jornada_activa()
    activas_ahora = encuestas_activas_jornada(jornada_actual)
    ya_respondidas = {b['encuesta'] for b in session.get('mis_respuestas', [])}
    pendientes_activos = [e for e in esperando if e in activas_ahora and e not in ya_respondidas]

    if pendientes_activos:
        # Ya activaron una — redirigir directamente
        session['pendientes_jornada'] = pendientes_activos
        flash('✓ El administrador ha habilitado la siguiente encuesta. ¡Puede continuar!')
        return redirect(url_de_encuesta(pendientes_activos[0]))

    return render_template('espera_activa.html',
        jornada_nombre=jornada_nombre,
        esperando=esperando,
        id_jornada=id_jornada)


# ---------------------------------------------------------
# ENCUESTA CIUDADANOS
# ---------------------------------------------------------
@app.route('/ciudadanos', methods=['GET', 'POST'])
@login_required
def ciudadanos():
    jornada = get_jornada_activa()
    encuestas = encuestas_de_jornada(jornada)

    if encuesta_bloqueada_para_invitado('ciudadanos', jornada):
        flash('Esta encuesta aún no ha sido habilitada por el administrador.')
        return redirect(url_for('menu'))

    if request.method == 'POST':
        f = request.form
        id_jornada = jornada['ID_JORNADA'] if jornada else None
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO encuestas_ciudadanos
                (ID_ENCUESTA, USUARIO, FECHA, ESTUDIOS, OCUPACION,
                 Pregunta_1, Pregunta_2, Pregunta_3, Pregunta_4,
                 Pregunta_5, Pregunta_6, Pregunta_7, ID_JORNADA)
                VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session['usuario'], f.get('fecha', date.today()),
                f.get('estudios'), f.get('ocupacion'),
                f.get('pregunta_1'), f.get('pregunta_2'),
                f.get('pregunta_3'), f.get('pregunta_4'),
                f.get('pregunta_5'), f.get('pregunta_6'),
                f.get('pregunta_7'), id_jornada
            ))
        conn.commit()
        conn.close()
        guardar_snapshot_respuesta('ciudadanos', 'Encuesta Ciudadanos', [
            ('Fecha', f.get('fecha', date.today())),
            ('Estudios', f.get('estudios')),
            ('Ocupación', f.get('ocupacion')),
            ('Pregunta 1', f.get('pregunta_1')),
            ('Pregunta 2', f.get('pregunta_2')),
            ('Pregunta 3', f.get('pregunta_3')),
            ('Pregunta 4', f.get('pregunta_4')),
            ('Pregunta 5', f.get('pregunta_5')),
            ('Pregunta 6', f.get('pregunta_6')),
            ('Pregunta 7', f.get('pregunta_7')),
        ])
        flash('✓ Encuesta guardada.')
        salida = siguiente_paso_invitado('ciudadanos')
        if salida:
            return salida
        return redirect(url_for('ciudadanos'))

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM jornadas WHERE ESTADO='ACTIVA' ORDER BY FECHA DESC")
        jornadas_disponibles = cur.fetchall()
    conn.close()
    return render_template('ciudadanos.html',
        today=date.today().isoformat(), jornada=jornada,
        jornadas_disponibles=jornadas_disponibles,
        admin=es_admin(), encuestas=encuestas)


@app.route('/ciudadanos/lista')
@login_required
@admin_required
def ciudadanos_lista():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ec.*, j.NOMBRE AS NOMBRE_JORNADA
            FROM encuestas_ciudadanos ec
            LEFT JOIN jornadas j ON ec.ID_JORNADA = j.ID_JORNADA
            ORDER BY ec.FECHA DESC
        """)
        registros = cur.fetchall()
    conn.close()
    return render_template('ciudadanos_lista.html', registros=registros)


# ---------------------------------------------------------
# ENCUESTA QUIZ
# ---------------------------------------------------------
@app.route('/preguntas', methods=['GET', 'POST'])
@login_required
def preguntas():
    conn = get_connection()
    jornada = get_jornada_activa()
    encuestas = encuestas_de_jornada(jornada)

    if encuesta_bloqueada_para_invitado('quiz', jornada):
        conn.close()
        flash('Esta encuesta aún no ha sido habilitada por el administrador.')
        return redirect(url_for('menu'))

    if request.method == 'POST':
        f = request.form
        id_jornada = jornada['ID_JORNADA'] if jornada else None
        with conn.cursor() as cur:
            nombre_org = None
            if f.get('organismo_p'):
                cur.execute("SELECT ORGANISMO FROM organismos WHERE ID_ORGANISMO=%s", (f.get('organismo_p'),))
                row = cur.fetchone()
                nombre_org = row['ORGANISMO'] if row else None
            nom_ie = None
            if f.get('institucion_educativa'):
                cur.execute("SELECT INSTITUCION_EDUCATIVA FROM directorio_ie WHERE ITEM=%s", (f.get('institucion_educativa'),))
                row = cur.fetchone()
                nom_ie = row['INSTITUCION_EDUCATIVA'] if row else None
            cur.execute("""
                INSERT INTO preguntas
                (USUARIO, FECHA, SERVIDOR_PUBLICO_PLANTA, CARGO, PROFESION,
                 ORGANISMO_P, NOMBRE_ORGANISMO, INSTITUCION_EDUCATIVA, NOM_INS_EDUCATIVA,
                 CAPACITACION_LEY_DISCIPLINARIA, P1, P2, P3, P4, P5, P6, P7, P8, ID_JORNADA)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session['usuario'], f.get('fecha', date.today()),
                f.get('servidor_publico'), f.get('cargo'), f.get('profesion'),
                f.get('organismo_p') or None, nombre_org,
                f.get('institucion_educativa') or None, nom_ie,
                f.get('capacitacion'),
                f.get('p1'), f.get('p2'), f.get('p3'), f.get('p4'),
                f.get('p5'), f.get('p6'), f.get('p7'), f.get('p8'),
                id_jornada
            ))
        conn.commit()
        conn.close()
        guardar_snapshot_respuesta('quiz', 'Quiz — Ley Disciplinaria', [
            ('Fecha', f.get('fecha', date.today())),
            ('Cargo', f.get('cargo')),
            ('Profesión', f.get('profesion')),
            ('¿Servidor público de planta?', f.get('servidor_publico')),
            ('¿Recibió capacitación?', f.get('capacitacion')),
            ('Pregunta 1', f.get('p1')),
            ('Pregunta 2', f.get('p2')),
            ('Pregunta 3', f.get('p3')),
            ('Pregunta 4', f.get('p4')),
            ('Pregunta 5', f.get('p5')),
            ('Pregunta 6', f.get('p6')),
            ('Pregunta 7', f.get('p7')),
            ('Pregunta 8', f.get('p8')),
        ])
        flash('✓ Encuesta guardada.')
        salida = siguiente_paso_invitado('quiz')
        if salida:
            return salida
        return redirect(url_for('preguntas'))

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM organismos ORDER BY ORGANISMO")
        organismos = cur.fetchall()
        cur.execute("SELECT * FROM directorio_ie ORDER BY INSTITUCION_EDUCATIVA")
        instituciones = cur.fetchall()
    conn.close()
    return render_template('preguntas.html',
        organismos=organismos, instituciones=instituciones,
        today=date.today().isoformat(), jornada=jornada,
        admin=es_admin(), encuestas=encuestas)


@app.route('/preguntas/lista')
@login_required
@admin_required
def preguntas_lista():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.*, j.NOMBRE AS NOMBRE_JORNADA
            FROM preguntas p
            LEFT JOIN jornadas j ON p.ID_JORNADA = j.ID_JORNADA
            ORDER BY p.NOMBRE_ORGANISMO, p.FECHA DESC
        """)
        registros = cur.fetchall()
    conn.close()
    return render_template('preguntas_lista.html', registros=registros)


# ---------------------------------------------------------
# ENCUESTA PRESABER
# ---------------------------------------------------------
@app.route('/presaber', methods=['GET', 'POST'])
@login_required
def presaber():
    conn = get_connection()
    jornada = get_jornada_activa()
    encuestas = encuestas_de_jornada(jornada)

    if encuesta_bloqueada_para_invitado('presaber', jornada):
        conn.close()
        flash('Esta encuesta aún no ha sido habilitada por el administrador.')
        return redirect(url_for('menu'))

    if request.method == 'POST':
        f = request.form
        id_jornada = jornada['ID_JORNADA'] if jornada else None
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO presaber
                (USUARIO, FECHA, SERVIDOR_PUBLICO_PLANTA, CARGO, PROFESION,
                 ORGANISMO, INSTITUCION_EDUCATIVA, CAPACITACION_LEY, CUANTAS,
                 Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, ANIO, MES, ID_JORNADA)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session['usuario'], f.get('fecha', date.today()),
                f.get('servidor_publico'), f.get('cargo'), f.get('profesion'),
                f.get('organismo'), f.get('institucion_educativa'),
                f.get('capacitacion'), f.get('cuantas') or None,
                f.get('q1'), f.get('q2'), f.get('q3'), f.get('q4'),
                f.get('q5'), f.get('q6'), f.get('q7'), f.get('q8'),
                date.today().year, date.today().strftime('%B'),
                id_jornada
            ))
        conn.commit()
        conn.close()
        guardar_snapshot_respuesta('presaber', 'Presaber', [
            ('Fecha', f.get('fecha', date.today())),
            ('Cargo', f.get('cargo')),
            ('Profesión', f.get('profesion')),
            ('Organismo', f.get('organismo')),
            ('¿Servidor público de planta?', f.get('servidor_publico')),
            ('¿Recibió capacitación?', f.get('capacitacion')),
            ('¿Cuántas capacitaciones?', f.get('cuantas')),
            ('1. No tratar con respeto', f.get('q1')),
            ('2. Solicitar dádivas/beneficios', f.get('q2')),
            ('3. Actos de violencia', f.get('q3')),
            ('4. No dedicar el tiempo laboral', f.get('q4')),
            ('5. Incumplir horario de trabajo', f.get('q5')),
            ('6. Omitir respuesta a peticiones', f.get('q6')),
            ('7. No acreditar requisitos del cargo', f.get('q7')),
            ('8. No capacitarse en su área', f.get('q8')),
        ])
        flash('✓ Encuesta guardada.')
        salida = siguiente_paso_invitado('presaber')
        if salida:
            return salida
        return redirect(url_for('presaber'))

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM organismos ORDER BY ORGANISMO")
        organismos = cur.fetchall()
        cur.execute("SELECT * FROM directorio_ie ORDER BY INSTITUCION_EDUCATIVA")
        instituciones = cur.fetchall()
    conn.close()
    return render_template('presaber.html',
        organismos=organismos, instituciones=instituciones,
        today=date.today().isoformat(), jornada=jornada,
        admin=es_admin(), encuestas=encuestas)


@app.route('/presaber/lista')
@login_required
@admin_required
def presaber_lista():
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pr.*, j.NOMBRE AS NOMBRE_JORNADA
            FROM presaber pr
            LEFT JOIN jornadas j ON pr.ID_JORNADA = j.ID_JORNADA
            ORDER BY pr.ANIO, pr.MES, pr.ID_RESPUESTA
        """)
        registros = cur.fetchall()
    conn.close()
    return render_template('presaber_lista.html', registros=registros)


# ---------------------------------------------------------
# ADMIN: ORGANISMOS, DIRECTORIO IE, USUARIOS
# ---------------------------------------------------------
@app.route('/organismos', methods=['GET', 'POST'])
@login_required
@admin_required
def organismos():
    conn = get_connection()
    if request.method == 'POST':
        with conn.cursor() as cur:
            cur.execute("INSERT INTO organismos (ORGANISMO) VALUES (%s)", (request.form['organismo'],))
        conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM organismos ORDER BY ORGANISMO")
        registros = cur.fetchall()
    conn.close()
    return render_template('organismos.html', registros=registros)


@app.route('/organismos/eliminar/<int:id_organismo>')
@login_required
@admin_required
def organismos_eliminar(id_organismo):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM organismos WHERE ID_ORGANISMO=%s", (id_organismo,))
    conn.close()
    return redirect(url_for('organismos'))


@app.route('/directorio', methods=['GET', 'POST'])
@login_required
@admin_required
def directorio():
    conn = get_connection()
    if request.method == 'POST':
        with conn.cursor() as cur:
            cur.execute("INSERT INTO directorio_ie (INSTITUCION_EDUCATIVA) VALUES (%s)", (request.form['institucion'],))
        conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM directorio_ie ORDER BY INSTITUCION_EDUCATIVA")
        registros = cur.fetchall()
    conn.close()
    return render_template('directorio.html', registros=registros)


@app.route('/directorio/eliminar/<int:item>')
@login_required
@admin_required
def directorio_eliminar(item):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM directorio_ie WHERE ITEM=%s", (item,))
    conn.close()
    return redirect(url_for('directorio'))


@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def usuarios():
    conn = get_connection()
    if request.method == 'POST':
        f = request.form
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (USUARIO, PASSWORD, ROL, ESTADO) VALUES (%s,%s,%s,%s)",
                (f['usuario'], f['password'], f['rol'], 1)
            )
        conn.commit()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT u.*, r.ROL AS NOMBRE_ROL FROM usuarios u
            JOIN roles r ON u.ROL = r.IDROL ORDER BY u.USUARIO
        """)
        registros = cur.fetchall()
        cur.execute("SELECT * FROM roles")
        roles = cur.fetchall()
    conn.close()
    return render_template('usuarios.html', registros=registros, roles=roles)


@app.route('/usuarios/toggle/<int:idusuario>')
@login_required
@admin_required
def usuarios_toggle(idusuario):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE usuarios SET ESTADO = NOT ESTADO::boolean WHERE IDUSUARIO=%s", (idusuario,))
    conn.commit()
    conn.close()
    return redirect(url_for('usuarios'))


@app.route('/usuarios/editar/<int:idusuario>', methods=['POST'])
@login_required
@admin_required
def usuarios_editar(idusuario):
    conn = get_connection()
    f = request.form
    with conn.cursor() as cur:
        if f.get('password'):
            cur.execute(
                "UPDATE usuarios SET USUARIO=%s, PASSWORD=%s, ROL=%s WHERE IDUSUARIO=%s",
                (f['usuario'], f['password'], f['rol'], idusuario)
            )
        else:
            cur.execute(
                "UPDATE usuarios SET USUARIO=%s, ROL=%s WHERE IDUSUARIO=%s",
                (f['usuario'], f['rol'], idusuario)
            )
    conn.commit()
    conn.close()
    flash('Usuario actualizado correctamente')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/eliminar/<int:idusuario>')
@login_required
@admin_required
def usuarios_eliminar(idusuario):
    if idusuario == session.get('usuario_id'):
        flash('No puedes eliminar tu propio usuario')
        return redirect(url_for('usuarios'))
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM usuarios WHERE IDUSUARIO=%s", (idusuario,))
    conn.commit()
    conn.close()
    flash('Usuario eliminado')
    return redirect(url_for('usuarios'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
