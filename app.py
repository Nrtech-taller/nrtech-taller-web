from flask import Flask, request, redirect, session, render_template_string, url_for
import os
import psycopg
from psycopg.rows import dict_row
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

app = Flask(__name__)
app.secret_key = "nrtech_secret_key"

USER = "admin"
PASS = "N41043406@"

REMITENTE_EMAIL = os.environ.get("GMAIL_USER")
CONTRASENA_APP = os.environ.get("GMAIL_APP_PASSWORD")
WHATSAPP_LINK = "https://wa.me/59898705065"
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL")


def db():
    return psycopg.connect(DATABASE_URL, sslmode="require", row_factory=dict_row)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            cedula TEXT,
            notas TEXT,
            fecha_alta TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ordenes (
            id SERIAL PRIMARY KEY,
            numero_orden TEXT UNIQUE,
            cliente_id INTEGER REFERENCES clientes(id),
            tipo_equipo TEXT,
            marca TEXT,
            modelo TEXT,
            imei_serie TEXT,
            falla TEXT,
            observaciones TEXT,
            presupuesto NUMERIC(10,2),
            estado TEXT DEFAULT 'recibido',
            cerrado BOOLEAN DEFAULT FALSE,
            fecha_ingreso TIMESTAMP DEFAULT NOW(),
            fecha_actualizacion TIMESTAMP DEFAULT NOW(),
            fecha_entrega TIMESTAMP
        );
    """)

    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS numero_orden TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS cliente_id INTEGER REFERENCES clientes(id);")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS tipo_equipo TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS marca TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS modelo TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS imei_serie TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS falla TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS observaciones TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS presupuesto NUMERIC(10,2);")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'recibido';")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS cerrado BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_ingreso TIMESTAMP DEFAULT NOW();")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_actualizacion TIMESTAMP DEFAULT NOW();")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_entrega TIMESTAMP;")

    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE indexname = 'idx_ordenes_numero_orden'
            ) THEN
                CREATE INDEX idx_ordenes_numero_orden ON ordenes(numero_orden);
            END IF;
        END$$;
    """)

    con.commit()
    con.close()


def login_required():
    return session.get("logged_in") is True


def generar_numero_orden():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 AS siguiente FROM ordenes")
    siguiente = cur.fetchone()["siguiente"]
    con.close()
    return f"NR-{siguiente:05d}"


def color_estado(estado):
    colores = {
        "recibido": "#6c757d",
        "diagnostico": "#0dcaf0",
        "esperando_aprobacion": "#fd7e14",
        "esperando_repuesto": "#ffc107",
        "en_reparacion": "#0d6efd",
        "listo_para_retirar": "#198754",
        "entregado": "#212529",
        "cancelado": "#dc3545",
        "presupuesto_aceptado": "#198754",
        "presupuesto_rechazado": "#dc3545",
    }
    return colores.get(estado, "#6c757d")


def enviar_email(destino, asunto, html):
    if not REMITENTE_EMAIL or not CONTRASENA_APP or not destino:
        return False, "Faltan variables de mail o destino"

    try:
        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = formataddr(("NR Tech", REMITENTE_EMAIL))
        msg["To"] = destino
        msg.set_content("Tu cliente de correo no soporta HTML.")
        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(REMITENTE_EMAIL, CONTRASENA_APP)
            smtp.send_message(msg)

        return True, "Mail enviado"
    except Exception as e:
        return False, str(e)


def enviar_mail_presupuesto(orden_id):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.*, c.nombre, c.email, c.telefono
        FROM ordenes o
        JOIN clientes c ON c.id = o.cliente_id
        WHERE o.id = %s
    """, (orden_id,))
    orden = cur.fetchone()
    con.close()

    if not orden or not orden["email"]:
        return False, "El cliente no tiene email"

    aceptar_url = f"{BASE_URL}/presupuesto/aceptar/{orden_id}" if BASE_URL else "#"
    rechazar_url = f"{BASE_URL}/presupuesto/rechazar/{orden_id}" if BASE_URL else "#"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:20px;">
        <div style="max-width:700px; margin:auto; background:white; padding:30px; border-radius:12px;">
            <h2 style="color:#0d6efd; margin-top:0;">NR Tech - Presupuesto</h2>
            <p>Hola <b>{orden["nombre"]}</b>,</p>
            <p>Te enviamos el presupuesto de tu equipo.</p>

            <table style="width:100%; border-collapse: collapse; margin:20px 0;">
                <tr><td><b>Número de orden:</b></td><td>{orden["numero_orden"] or ""}</td></tr>
                <tr><td><b>Equipo:</b></td><td>{orden["tipo_equipo"] or ""} {orden["marca"] or ""} {orden["modelo"] or ""}</td></tr>
                <tr><td><b>IMEI / Serie:</b></td><td>{orden["imei_serie"] or ""}</td></tr>
                <tr><td><b>Falla:</b></td><td>{orden["falla"] or ""}</td></tr>
                <tr><td><b>Presupuesto:</b></td><td><b>USD {orden["presupuesto"] or 0}</b></td></tr>
            </table>

            <p>Podés responder desde estos botones:</p>

            <div style="margin:25px 0;">
                <a href="{aceptar_url}" style="background:#198754; color:white; text-decoration:none; padding:12px 20px; border-radius:8px; margin-right:10px; display:inline-block;">
                    Aceptar presupuesto
                </a>

                <a href="{rechazar_url}" style="background:#dc3545; color:white; text-decoration:none; padding:12px 20px; border-radius:8px; display:inline-block;">
                    Rechazar presupuesto
                </a>
            </div>

            <p>También podés escribirnos por WhatsApp:</p>
            <p><a href="{WHATSAPP_LINK}">{WHATSAPP_LINK}</a></p>

            <hr>
            <p style="color:#666; font-size:12px;">NR Tech - Tecnología en buenas manos</p>
        </div>
    </body>
    </html>
    """

    return enviar_email(orden["email"], f"Presupuesto {orden['numero_orden']} - NR Tech", html)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        user = request.form.get("username", "")
        password = request.form.get("password", "")
        if user == USER and password == PASS:
            session["logged_in"] = True
            return redirect("/")
        error = "Usuario o contraseña incorrectos"

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - NR Tech</title>
        <style>
            body { font-family: Arial; background:#f4f4f4; padding:40px; }
            .box { max-width:400px; margin:auto; background:white; padding:25px; border-radius:12px; }
            input { width:100%; padding:10px; margin:8px 0; }
            button { width:100%; padding:12px; background:#0d6efd; color:white; border:none; border-radius:8px; }
            .error { color:red; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Ingreso NR Tech</h2>
            {% if error %}<p class="error">{{ error }}</p>{% endif %}
            <form method="post">
                <input type="text" name="username" placeholder="Usuario" required>
                <input type="password" name="password" placeholder="Contraseña" required>
                <button type="submit">Entrar</button>
            </form>
        </div>
    </body>
    </html>
    """, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
def index():
    if not login_required():
        return redirect("/login")

    q = request.args.get("q", "").strip()

    con = db()
    cur = con.cursor()

    if q:
        like = f"%{q}%"
        cur.execute("""
            SELECT o.*, c.nombre, c.telefono, c.email
            FROM ordenes o
            JOIN clientes c ON c.id = o.cliente_id
            WHERE
                COALESCE(o.numero_orden, '') ILIKE %s OR
                COALESCE(c.nombre, '') ILIKE %s OR
                COALESCE(c.telefono, '') ILIKE %s OR
                COALESCE(o.imei_serie, '') ILIKE %s
            ORDER BY o.id DESC
        """, (like, like, like, like))
    else:
        cur.execute("""
            SELECT o.*, c.nombre, c.telefono, c.email
            FROM ordenes o
            JOIN clientes c ON c.id = o.cliente_id
            ORDER BY o.id DESC
        """)

    ordenes = cur.fetchall()

    cur.execute("""
        SELECT estado, COUNT(*) as total
        FROM ordenes
        WHERE cerrado = FALSE
        GROUP BY estado
    """)
    estados_raw = cur.fetchall()
    con.close()

    resumen = {
        "esperando_aprobacion": 0,
        "esperando_repuesto": 0,
        "en_reparacion": 0,
        "listo_para_retirar": 0,
        "diagnostico": 0,
        "recibido": 0,
    }

    for fila in estados_raw:
        resumen[fila["estado"]] = fila["total"]

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>NR Tech - Taller</title>
        <style>
            body { font-family: Arial; background:#f5f5f5; margin:0; padding:20px; }
            .topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
            .btn { padding:8px 12px; border:none; border-radius:8px; text-decoration:none; color:white; background:#0d6efd; display:inline-block; }
            .btn-dark { background:#212529; }
            .btn-green { background:#198754; }
            .btn-orange { background:#fd7e14; }
            .btn-red { background:#dc3545; }
            .btn-yellow { background:#d39e00; }
            .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:20px; }
            .card { background:white; padding:16px; border-radius:12px; box-shadow:0 1px 4px rgba(0,0,0,.08); }
            .search { background:white; padding:15px; border-radius:12px; margin-bottom:20px; }
            table { width:100%; border-collapse:collapse; background:white; border-radius:12px; overflow:hidden; }
            th, td { padding:10px; border-bottom:1px solid #eee; text-align:left; font-size:14px; vertical-align:top; }
            th { background:#111; color:white; }
            .badge { color:white; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:bold; display:inline-block; }
            .acciones a { margin:2px; }
            input, select, textarea { width:100%; padding:10px; margin:6px 0 12px; border:1px solid #ddd; border-radius:8px; }
            .small { font-size:12px; color:#666; }
        </style>
    </head>
    <body>
        <div class="topbar">
            <div>
                <h1 style="margin:0;">NR Tech - Taller</h1>
                <div class="small">Tecnología en buenas manos</div>
            </div>
            <div>
                <a class="btn" href="/nueva">Nueva orden</a>
                <a class="btn btn-dark" href="/clientes">Clientes</a>
                <a class="btn btn-red" href="/logout">Salir</a>
            </div>
        </div>

        <div class="cards">
            <div class="card"><b>Recibidos</b><br>{{ resumen.get('recibido', 0) }}</div>
            <div class="card"><b>Diagnóstico</b><br>{{ resumen.get('diagnostico', 0) }}</div>
            <div class="card"><b>Esperando aprobación</b><br>{{ resumen.get('esperando_aprobacion', 0) }}</div>
            <div class="card"><b>Esperando repuesto</b><br>{{ resumen.get('esperando_repuesto', 0) }}</div>
            <div class="card"><b>En reparación</b><br>{{ resumen.get('en_reparacion', 0) }}</div>
            <div class="card"><b>Listo para retirar</b><br>{{ resumen.get('listo_para_retirar', 0) }}</div>
        </div>

        <div class="search">
            <form method="get">
                <input type="text" name="q" placeholder="Buscar por nombre, número de orden, teléfono o IMEI" value="{{ q }}">
                <button class="btn" type="submit">Buscar</button>
                <a class="btn btn-dark" href="/">Limpiar</a>
            </form>
        </div>

        <table>
            <tr>
                <th>Orden</th>
                <th>Cliente</th>
                <th>Equipo</th>
                <th>Falla</th>
                <th>Presupuesto</th>
                <th>Estado</th>
                <th>Acciones</th>
            </tr>
            {% for o in ordenes %}
            <tr>
                <td>
                    <b>{{ o.numero_orden or "-" }}</b><br>
                    <span class="small">IMEI/Serie: {{ o.imei_serie or "-" }}</span>
                </td>
                <td>
                    <b>{{ o.nombre }}</b><br>
                    <span class="small">{{ o.telefono or "-" }}</span>
                </td>
                <td>{{ o.tipo_equipo or "" }} {{ o.marca or "" }} {{ o.modelo or "" }}</td>
                <td>{{ o.falla or "-" }}</td>
                <td>USD {{ o.presupuesto or 0 }}</td>
                <td>
                    <span class="badge" style="background:{{ color_estado(o.estado) }}">
                        {{ o.estado }}
                    </span>
                    {% if o.cerrado %}
                        <div class="small">Cerrada</div>
                    {% endif %}
                </td>
                <td class="acciones">
                    <a class="btn btn-dark" href="/orden/{{ o.id }}">Ver</a>
                    <a class="btn" href="/cliente/{{ o.cliente_id }}">Cliente</a>
                    <a class="btn btn-orange" href="/estado/{{ o.id }}/esperando_aprobacion">Esp. aprobación</a>
                    <a class="btn btn-yellow" href="/estado/{{ o.id }}/esperando_repuesto">Esp. repuesto</a>
                    <a class="btn" href="/estado/{{ o.id }}/en_reparacion">En reparación</a>
                    <a class="btn btn-green" href="/listo/{{ o.id }}">Listo</a>
                    <a class="btn btn-dark" href="/entregar/{{ o.id }}">Entregar</a>
                    <a class="btn btn-red" href="/mail_presupuesto/{{ o.id }}">Mandar mail</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """, ordenes=ordenes, q=q, resumen=resumen, color_estado=color_estado)


@app.route("/nueva", methods=["GET", "POST"])
def nueva():
    if not login_required():
        return redirect("/login")

    mensaje = ""

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        direccion = request.form.get("direccion", "").strip()
        cedula = request.form.get("cedula", "").strip()
        notas_cliente = request.form.get("notas_cliente", "").strip()

        tipo_equipo = request.form.get("tipo_equipo", "").strip()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        imei_serie = request.form.get("imei_serie", "").strip()
        falla = request.form.get("falla", "").strip()
        observaciones = request.form.get("observaciones", "").strip()
        presupuesto = request.form.get("presupuesto", "").strip()
        estado = request.form.get("estado", "recibido").strip()

        con = db()
        cur = con.cursor()

        cliente_id = None
        if telefono:
            cur.execute("SELECT id FROM clientes WHERE telefono = %s LIMIT 1", (telefono,))
            fila = cur.fetchone()
            if fila:
                cliente_id = fila["id"]

        if not cliente_id and email:
            cur.execute("SELECT id FROM clientes WHERE email = %s LIMIT 1", (email,))
            fila = cur.fetchone()
            if fila:
                cliente_id = fila["id"]

        if cliente_id:
            cur.execute("""
                UPDATE clientes
                SET nombre=%s, telefono=%s, email=%s, direccion=%s, cedula=%s, notas=%s
                WHERE id=%s
            """, (nombre, telefono, email, direccion, cedula, notas_cliente, cliente_id))
        else:
            cur.execute("""
                INSERT INTO clientes (nombre, telefono, email, direccion, cedula, notas)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (nombre, telefono, email, direccion, cedula, notas_cliente))
            cliente_id = cur.fetchone()["id"]

        numero_orden = generar_numero_orden()

        cur.execute("""
            INSERT INTO ordenes (
                numero_orden, cliente_id, tipo_equipo, marca, modelo,
                imei_serie, falla, observaciones, presupuesto, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            numero_orden, cliente_id, tipo_equipo, marca, modelo,
            imei_serie, falla, observaciones, presupuesto if presupuesto else None, estado
        ))

        con.commit()
        con.close()

        return redirect("/")

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Nueva orden</title>
        <style>
            body { font-family: Arial; background:#f5f5f5; padding:20px; }
            .box { max-width:900px; margin:auto; background:white; padding:25px; border-radius:12px; }
            .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
            input, select, textarea { width:100%; padding:10px; margin-top:6px; border:1px solid #ddd; border-radius:8px; }
            textarea { min-height:100px; }
            button, a { padding:10px 14px; border:none; border-radius:8px; text-decoration:none; display:inline-block; }
            button { background:#0d6efd; color:white; }
            .back { background:#212529; color:white; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Nueva orden</h2>
            <form method="post">
                <div class="grid">
                    <div>
                        <h3>Cliente</h3>
                        <label>Nombre</label>
                        <input type="text" name="nombre" required>

                        <label>Teléfono</label>
                        <input type="text" name="telefono">

                        <label>Email</label>
                        <input type="email" name="email">

                        <label>Dirección</label>
                        <input type="text" name="direccion">

                        <label>Cédula</label>
                        <input type="text" name="cedula">

                        <label>Notas cliente</label>
                        <textarea name="notas_cliente"></textarea>
                    </div>

                    <div>
                        <h3>Equipo / reparación</h3>
                        <label>Tipo de equipo</label>
                        <input type="text" name="tipo_equipo" placeholder="Celular, notebook, tablet...">

                        <label>Marca</label>
                        <input type="text" name="marca">

                        <label>Modelo</label>
                        <input type="text" name="modelo">

                        <label>IMEI / Serie</label>
                        <input type="text" name="imei_serie">

                        <label>Falla</label>
                        <textarea name="falla" required></textarea>

                        <label>Observaciones</label>
                        <textarea name="observaciones"></textarea>

                        <label>Presupuesto</label>
                        <input type="number" step="0.01" name="presupuesto">

                        <label>Estado inicial</label>
                        <select name="estado">
                            <option value="recibido">recibido</option>
                            <option value="diagnostico">diagnostico</option>
                            <option value="esperando_aprobacion">esperando_aprobacion</option>
                            <option value="esperando_repuesto">esperando_repuesto</option>
                            <option value="en_reparacion">en_reparacion</option>
                            <option value="listo_para_retirar">listo_para_retirar</option>
                        </select>
                    </div>
                </div>

                <br>
                <button type="submit">Guardar orden</button>
                <a class="back" href="/">Volver</a>
            </form>
        </div>
    </body>
    </html>
    """)


@app.route("/orden/<int:id>")
def ver_orden(id):
    if not login_required():
        return redirect("/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.*, c.nombre, c.telefono, c.email, c.direccion, c.cedula, c.notas
        FROM ordenes o
        JOIN clientes c ON c.id = o.cliente_id
        WHERE o.id = %s
    """, (id,))
    o = cur.fetchone()
    con.close()

    if not o:
        return "Orden no encontrada", 404

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Orden {{ o.numero_orden }}</title>
        <style>
            body { font-family: Arial; background:#f5f5f5; padding:20px; }
            .box { max-width:900px; margin:auto; background:white; padding:25px; border-radius:12px; }
            .btn { padding:10px 14px; border:none; border-radius:8px; text-decoration:none; color:white; background:#0d6efd; display:inline-block; }
            .dark { background:#212529; }
            .green { background:#198754; }
            .red { background:#dc3545; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Orden {{ o.numero_orden }}</h2>
            <p><b>Cliente:</b> {{ o.nombre }}</p>
            <p><b>Teléfono:</b> {{ o.telefono or '-' }}</p>
            <p><b>Email:</b> {{ o.email or '-' }}</p>
            <p><b>Equipo:</b> {{ o.tipo_equipo or '' }} {{ o.marca or '' }} {{ o.modelo or '' }}</p>
            <p><b>IMEI / Serie:</b> {{ o.imei_serie or '-' }}</p>
            <p><b>Falla:</b> {{ o.falla or '-' }}</p>
            <p><b>Observaciones:</b> {{ o.observaciones or '-' }}</p>
            <p><b>Presupuesto:</b> USD {{ o.presupuesto or 0 }}</p>
            <p><b>Estado:</b> {{ o.estado }}</p>
            <p><b>Ingreso:</b> {{ o.fecha_ingreso }}</p>
            <p><b>Entrega:</b> {{ o.fecha_entrega or '-' }}</p>

            <a class="btn dark" href="/">Volver</a>
            <a class="btn" href="/cliente/{{ o.cliente_id }}">Ver cliente</a>
            <a class="btn green" href="/listo/{{ o.id }}">Listo para retirar</a>
            <a class="btn dark" href="/entregar/{{ o.id }}">Finalizar / entregar</a>
            <a class="btn red" href="/mail_presupuesto/{{ o.id }}">Mandar mail</a>
        </div>
    </body>
    </html>
    """, o=o)


@app.route("/clientes")
def clientes():
    if not login_required():
        return redirect("/login")

    q = request.args.get("q", "").strip()
    con = db()
    cur = con.cursor()

    if q:
        like = f"%{q}%"
        cur.execute("""
            SELECT *
            FROM clientes
            WHERE
                COALESCE(nombre, '') ILIKE %s OR
                COALESCE(telefono, '') ILIKE %s OR
                COALESCE(email, '') ILIKE %s
            ORDER BY id DESC
        """, (like, like, like))
    else:
        cur.execute("SELECT * FROM clientes ORDER BY id DESC")

    clientes = cur.fetchall()
    con.close()

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Clientes</title>
        <style>
            body { font-family: Arial; background:#f5f5f5; padding:20px; }
            .box { max-width:1100px; margin:auto; }
            .btn { padding:8px 12px; border:none; border-radius:8px; text-decoration:none; color:white; background:#0d6efd; display:inline-block; }
            .dark { background:#212529; }
            table { width:100%; border-collapse:collapse; background:white; border-radius:12px; overflow:hidden; }
            th, td { padding:10px; border-bottom:1px solid #eee; text-align:left; }
            th { background:#111; color:white; }
            input { width:100%; padding:10px; margin:10px 0; border:1px solid #ddd; border-radius:8px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Clientes</h2>
            <form method="get">
                <input type="text" name="q" placeholder="Buscar cliente" value="{{ q }}">
                <button class="btn" type="submit">Buscar</button>
                <a class="btn dark" href="/">Volver</a>
            </form>

            <table>
                <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Teléfono</th>
                    <th>Email</th>
                    <th>Dirección</th>
                    <th>Acción</th>
                </tr>
                {% for c in clientes %}
                <tr>
                    <td>{{ c.id }}</td>
                    <td>{{ c.nombre }}</td>
                    <td>{{ c.telefono or '-' }}</td>
                    <td>{{ c.email or '-' }}</td>
                    <td>{{ c.direccion or '-' }}</td>
                    <td><a class="btn" href="/cliente/{{ c.id }}">Ver ficha</a></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    """, clientes=clientes, q=q)


@app.route("/cliente/<int:id>")
def ver_cliente(id):
    if not login_required():
        return redirect("/login")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT * FROM clientes WHERE id = %s", (id,))
    cliente = cur.fetchone()

    cur.execute("""
        SELECT *
        FROM ordenes
        WHERE cliente_id = %s
        ORDER BY id DESC
    """, (id,))
    ordenes = cur.fetchall()
    con.close()

    if not cliente:
        return "Cliente no encontrado", 404

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ficha cliente</title>
        <style>
            body { font-family: Arial; background:#f5f5f5; padding:20px; }
            .box { max-width:1000px; margin:auto; background:white; padding:25px; border-radius:12px; }
            .btn { padding:8px 12px; border:none; border-radius:8px; text-decoration:none; color:white; background:#0d6efd; display:inline-block; }
            .dark { background:#212529; }
            table { width:100%; border-collapse:collapse; margin-top:20px; }
            th, td { padding:10px; border-bottom:1px solid #eee; text-align:left; }
            th { background:#111; color:white; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Ficha del cliente</h2>
            <p><b>Nombre:</b> {{ cliente.nombre }}</p>
            <p><b>Teléfono:</b> {{ cliente.telefono or '-' }}</p>
            <p><b>Email:</b> {{ cliente.email or '-' }}</p>
            <p><b>Dirección:</b> {{ cliente.direccion or '-' }}</p>
            <p><b>Cédula:</b> {{ cliente.cedula or '-' }}</p>
            <p><b>Notas:</b> {{ cliente.notas or '-' }}</p>

            <a class="btn dark" href="/">Volver</a>

            <h3>Historial de órdenes</h3>
            <table>
                <tr>
                    <th>Orden</th>
                    <th>Equipo</th>
                    <th>Falla</th>
                    <th>Estado</th>
                    <th>Acción</th>
                </tr>
                {% for o in ordenes %}
                <tr>
                    <td>{{ o.numero_orden }}</td>
                    <td>{{ o.tipo_equipo or '' }} {{ o.marca or '' }} {{ o.modelo or '' }}</td>
                    <td>{{ o.falla or '-' }}</td>
                    <td>{{ o.estado }}</td>
                    <td><a class="btn" href="/orden/{{ o.id }}">Ver orden</a></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    """, cliente=cliente, ordenes=ordenes)


@app.route("/estado/<int:id>/<estado>")
def cambiar_estado(id, estado):
    if not login_required():
        return redirect("/login")

    estados_validos = {
        "recibido",
        "diagnostico",
        "esperando_aprobacion",
        "esperando_repuesto",
        "en_reparacion",
        "listo_para_retirar",
        "entregado",
        "cancelado",
        "presupuesto_aceptado",
        "presupuesto_rechazado",
    }

    if estado not in estados_validos:
        return "Estado inválido", 400

    con = db()
    cur = con.cursor()

    if estado == "entregado":
        cur.execute("""
            UPDATE ordenes
            SET estado=%s, cerrado=TRUE, fecha_entrega=NOW(), fecha_actualizacion=NOW()
            WHERE id=%s
        """, (estado, id))
    else:
        cur.execute("""
            UPDATE ordenes
            SET estado=%s, fecha_actualizacion=NOW()
            WHERE id=%s
        """, (estado, id))

    con.commit()
    con.close()
    return redirect("/")


@app.route("/listo/<int:id>")
def listo(id):
    if not login_required():
        return redirect("/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE ordenes
        SET estado='listo_para_retirar', fecha_actualizacion=NOW()
        WHERE id=%s
    """, (id,))
    con.commit()
    con.close()
    return redirect("/")


@app.route("/entregar/<int:id>")
def entregar(id):
    if not login_required():
        return redirect("/login")

    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE ordenes
        SET estado='entregado', cerrado=TRUE, fecha_entrega=NOW(), fecha_actualizacion=NOW()
        WHERE id=%s
    """, (id,))
    con.commit()
    con.close()
    return redirect("/")


@app.route("/mail_presupuesto/<int:id>")
def mail_presupuesto(id):
    if not login_required():
        return redirect("/login")

    ok, msg = enviar_mail_presupuesto(id)
    return f"""
    <html>
    <body style="font-family:Arial; padding:30px;">
        <h2>{'Éxito' if ok else 'Error'}</h2>
        <p>{msg}</p>
        <a href="/">Volver</a>
    </body>
    </html>
    """


@app.route("/presupuesto/aceptar/<int:id>")
def aceptar_presupuesto(id):
    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE ordenes
        SET estado='presupuesto_aceptado', fecha_actualizacion=NOW()
        WHERE id=%s
    """, (id,))
    con.commit()
    con.close()

    return """
    <html>
    <body style="font-family:Arial; text-align:center; padding:40px;">
        <h2 style="color:green;">Presupuesto aceptado</h2>
        <p>Gracias. En breve nos comunicamos contigo.</p>
    </body>
    </html>
    """


@app.route("/presupuesto/rechazar/<int:id>")
def rechazar_presupuesto(id):
    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE ordenes
        SET estado='presupuesto_rechazado', fecha_actualizacion=NOW()
        WHERE id=%s
    """, (id,))
    con.commit()
    con.close()

    return """
    <html>
    <body style="font-family:Arial; text-align:center; padding:40px;">
        <h2 style="color:red;">Presupuesto rechazado</h2>
        <p>Tu respuesta fue registrada correctamente.</p>
    </body>
    </html>
    """


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)