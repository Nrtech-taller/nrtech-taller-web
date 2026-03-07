from flask import Flask, request, redirect, session
import os
import psycopg
from psycopg.rows import dict_row
import smtplib
import mimetypes
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr
import datetime
import secrets

app = Flask(__name__)
app.secret_key = "nrtech_secret_key"

USER = "admin"
PASS = "N41043406@"

REMITENTE_EMAIL = os.environ.get("GMAIL_USER")
CONTRASENA_APP = os.environ.get("GMAIL_APP_PASSWORD")
WHATSAPP_LINK = "https://wa.me/59898705065"
BASE_URL = os.environ.get("BASE_URL")
DATABASE_URL = os.environ.get("DATABASE_URL")


def db():
    return psycopg.connect(DATABASE_URL, sslmode="require", row_factory=dict_row)


def estado_presupuesto_badge(estado):
    if estado == "Aprobado":
        return "<span style='color:white;background:#16a34a;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>Aceptado</span>"
    elif estado == "Rechazado":
        return "<span style='color:white;background:#dc2626;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>Rechazado</span>"
    elif estado == "Esperando aprobación":
        return "<span style='color:white;background:#f59e0b;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>En espera</span>"
    return "<span style='color:#6b7280;'>-</span>"


def html_layout(titulo, contenido):
    return f"""
    <html>
      <head>
        <meta charset="utf-8">
        <title>{titulo}</title>
      </head>
      <body style="margin:0; font-family:Arial, sans-serif; background:#f3f6fb; color:#111827;">
        <div style="max-width:1100px; margin:0 auto; padding:24px;">
          <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8); color:white; border-radius:18px; padding:24px 28px; box-shadow:0 10px 30px rgba(0,0,0,0.12);">
            <h1 style="margin:0; font-size:28px;">NR Tech</h1>
            <p style="margin:8px 0 0 0; opacity:0.92;">Sistema de gestión de reparaciones</p>
          </div>

          <div style="margin-top:18px;">
            {contenido}
          </div>
        </div>
      </body>
    </html>
    """


def card_html(contenido):
    return f"""
    <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
      {contenido}
    </div>
    """


def tabla_estilo_inicio():
    return """
    <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; background:white; border-radius:16px; overflow:hidden;">
    """


def tabla_estilo_fin():
    return """
      </table>
    </div>
    """


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        telefono TEXT,
        email TEXT UNIQUE
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
        numero_serie TEXT,
        imei TEXT,
        estado_general TEXT,
        falla_cliente TEXT,
        diagnostico_tecnico TEXT,
        fecha_ingreso DATE,
        estado TEXT,
        presupuesto NUMERIC DEFAULT 0,
        observaciones TEXT,
        token_aprobacion TEXT,
        presupuesto_aprobado BOOLEAN DEFAULT FALSE,
        fecha_aprobacion TIMESTAMP,
        presupuesto_rechazado BOOLEAN DEFAULT FALSE,
        fecha_rechazo TIMESTAMP
    );
    """)

    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS token_aprobacion TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS presupuesto_aprobado BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_aprobacion TIMESTAMP;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS presupuesto_rechazado BOOLEAN DEFAULT FALSE;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_rechazo TIMESTAMP;")

    con.commit()
    con.close()


def enviar_email(destino, numero_orden, cliente, tipo, marca, modelo, estado, presupuesto,
                 tipo_mensaje="actualizacion", token_aprobacion=None,
                 presupuesto_aprobado=False, presupuesto_rechazado=False):
    if not destino or not REMITENTE_EMAIL or not CONTRASENA_APP:
        print("Email no enviado: faltan GMAIL_USER o GMAIL_APP_PASSWORD.")
        return

    try:
        pres = float(presupuesto or 0)
    except Exception:
        pres = 0.0

    presupuesto_mostrar = "En diagnóstico" if pres == 0 else f"${pres}"

    if tipo_mensaje == "ingreso":
        asunto = f"Ingreso de orden {numero_orden} – NR Tech"
        saludo_texto = "te confirmamos el ingreso de tu equipo al taller:"
    else:
        asunto = f"Actualización de orden {numero_orden} – NR Tech"
        saludo_texto = "te informamos una actualización de tu orden:"

    logo_path = Path(__file__).with_name("logo_nrtech.png")
    logo_cid = "logo_nrtech" if logo_path.exists() else None

    botones_presupuesto_html = ""
    texto_presupuesto = ""

    if (
        estado == "Esperando aprobación"
        and not presupuesto_aprobado
        and not presupuesto_rechazado
        and token_aprobacion
        and BASE_URL
        and pres > 0
    ):
        link_aprobacion = f"{BASE_URL}/aceptar_presupuesto/{token_aprobacion}"
        link_rechazo = f"{BASE_URL}/rechazar_presupuesto/{token_aprobacion}"

        botones_presupuesto_html = f"""
        <div style="text-align:center; margin-top:16px;">
          <a href="{link_aprobacion}" style="
            display:inline-block;
            background:#16a34a;
            color:#ffffff;
            text-decoration:none;
            font-weight:700;
            padding:14px 22px;
            border-radius:14px;
            font-size:14px;
            letter-spacing:0.3px;
            box-shadow:0 6px 18px rgba(22,163,74,0.25);
            margin-right:8px;
          ">
            ✅ Aceptar presupuesto
          </a>

          <a href="{link_rechazo}" style="
            display:inline-block;
            background:#dc2626;
            color:#ffffff;
            text-decoration:none;
            font-weight:700;
            padding:14px 22px;
            border-radius:14px;
            font-size:14px;
            letter-spacing:0.3px;
            box-shadow:0 6px 18px rgba(220,38,38,0.25);
            margin-left:8px;
          ">
            ❌ Rechazar presupuesto
          </a>
        </div>
        <p style="margin-top:10px; font-size:12px; color:#6b7280; text-align:center;">
          Al tocar un botón no se confirma automáticamente. Primero se mostrará una confirmación final.
        </p>
        """

        texto_presupuesto = (
            f"\nAceptar presupuesto: {link_aprobacion}\n"
            f"Rechazar presupuesto: {link_rechazo}\n"
        )

    cuerpo_html = f"""
    <html>
      <body style="margin:0; padding:0; background:#f6f8fb; font-family: Arial, sans-serif; color:#111827;">
        <div style="max-width:720px; margin:0 auto; padding:22px;">
          <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:16px; overflow:hidden; box-shadow:0 10px 30px rgba(17,24,39,0.08);">

            <div style="background:linear-gradient(135deg,#38bdf8,#3b82f6); padding:40px 22px; text-align:center;">
              {("<img src='cid:logo_nrtech' alt='NR Tech' style='max-height:180px; width:auto; display:block; margin:0 auto;' />" if logo_cid else "")}
              <div style="width:60px; height:3px; background:rgba(255,255,255,0.6); margin:18px auto 0 auto; border-radius:10px;"></div>
            </div>

            <div style="padding:18px 22px 10px 22px;">
              <p style="margin:0 0 12px 0; font-size:14px;">
                Hola <strong>{cliente}</strong>, {saludo_texto}
              </p>

              <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:14px; padding:14px;">
                <div style="margin:6px 0; font-size:13px;"><strong>N° de orden:</strong> <span style="color:#2563eb;">{numero_orden}</span></div>
                <div style="margin:6px 0; font-size:13px;"><strong>Equipo:</strong> {tipo} {marca} {modelo}</div>
                <div style="margin:6px 0; font-size:13px;"><strong>Estado:</strong> <span style="color:#16a34a;">{estado}</span></div>
                <div style="margin:6px 0; font-size:13px;"><strong>Presupuesto:</strong> <span style="color:#b45309;">{presupuesto_mostrar}</span></div>
              </div>

              {botones_presupuesto_html}

              <div style="text-align:center; margin-top:18px;">
                <a href="{WHATSAPP_LINK}" style="
                  display:inline-block;
                  background:#111827;
                  color:#ffffff;
                  text-decoration:none;
                  font-weight:600;
                  padding:14px 22px;
                  border-radius:14px;
                  font-size:14px;
                  letter-spacing:0.3px;
                  box-shadow:0 6px 18px rgba(0,0,0,0.15);
                ">
                  💬 Consultar por WhatsApp
                </a>
              </div>

              <h3 style="margin:18px 0 8px 0; font-size:14px; color:#111827;">Políticas de NR Tech</h3>
              <div style="font-size:12px; color:#4b5563; line-height:1.55;">
                • Aceptación de presupuesto: una vez aceptado, se autoriza la reparación.<br>
                • Plazo de retiro: 30 días corridos desde la notificación de disponibilidad.<br>
                • No retiro: vencido el plazo, NR Tech podrá disponer del dispositivo para recuperar costos (previa notificación).<br>
                • Garantía: 30 días sobre mano de obra y repuestos utilizados (no cubre golpes, humedad o manipulación externa).<br>
                • Datos: recomendamos respaldo previo; no nos responsabilizamos por pérdida de información.
              </div>
            </div>

            <div style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:12px 22px; font-size:11px; color:#6b7280; text-align:center;">
              Este correo fue enviado automáticamente. Guardá tu número de orden para futuras consultas.
            </div>

          </div>
        </div>
      </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr(("NR Tech – Tecnología en buenas manos", REMITENTE_EMAIL))
    msg["To"] = destino

    msg.set_content(
        f"Hola {cliente}.\n\n"
        f"Orden: {numero_orden}\n"
        f"Equipo: {tipo} {marca} {modelo}\n"
        f"Estado: {estado}\n"
        f"Presupuesto: {presupuesto_mostrar}\n"
        f"{texto_presupuesto}\n"
        f"WhatsApp: {WHATSAPP_LINK}\n"
        f"NR Tech"
    )
    msg.add_alternative(cuerpo_html, subtype="html")

    if logo_cid and logo_path.exists():
        ctype, _ = mimetypes.guess_type(str(logo_path))
        if ctype is None:
            ctype = "image/png"
        maintype, subtype = ctype.split("/", 1)
        with open(logo_path, "rb") as f:
            img_data = f.read()
        msg.get_payload()[1].add_related(img_data, maintype=maintype, subtype=subtype, cid=logo_cid)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as smtp:
            smtp.login(REMITENTE_EMAIL, CONTRASENA_APP)
            smtp.send_message(msg)
        print("Email enviado correctamente.")
    except Exception as e:
        print("Error al enviar email:", e)


init_db()


@app.get("/reset_db")
def reset_db():
    if not session.get("login"):
        return redirect("/login")

    con = db()
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS ordenes CASCADE;")
    cur.execute("DROP TABLE IF EXISTS clientes CASCADE;")
    con.commit()
    con.close()

    init_db()

    return html_layout(
        "Base reiniciada",
        card_html("""
        <h2 style="margin-top:0;">Base de datos reiniciada</h2>
        <p>Las tablas fueron borradas y creadas nuevamente.</p>
        <p><a href="/" style="color:#2563eb; font-weight:bold;">Volver</a></p>
        """)
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return html_layout(
            "Login",
            card_html("""
            <h2 style="margin-top:0;">Login NR Tech</h2>
            <form method="post">
              <label>Usuario</label><br>
              <input name="user" style="width:100%; max-width:360px; padding:10px; margin-top:6px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Contraseña</label><br>
              <input name="pass" type="password" style="width:100%; max-width:360px; padding:10px; margin-top:6px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <button style="background:#2563eb; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Entrar</button>
            </form>
            """)
        )

    user = request.form.get("user", "").strip()
    password = request.form.get("pass", "").strip()

    if user == USER and password == PASS:
        session["login"] = True
        return redirect("/")

    return html_layout(
        "Login",
        card_html("""
        <h2 style="margin-top:0;">Usuario o contraseña incorrectos</h2>
        <p><a href="/login" style="color:#2563eb; font-weight:bold;">Volver</a></p>
        """)
    )


@app.get("/logout")
def logout():
    session.pop("login", None)
    return redirect("/login")


@app.get("/")
def home():
    if not session.get("login"):
        return redirect("/login")

    contenido = """
    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px;">
      <a href="/crear" style="text-decoration:none; color:inherit;">
        <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
          <h3 style="margin:0 0 8px 0;">➕ Crear orden</h3>
          <p style="margin:0; color:#6b7280;">Registrar un nuevo equipo en el taller.</p>
        </div>
      </a>

      <a href="/buscar" style="text-decoration:none; color:inherit;">
        <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
          <h3 style="margin:0 0 8px 0;">🔎 Buscar orden</h3>
          <p style="margin:0; color:#6b7280;">Buscar por número, nombre, email, IMEI o serie.</p>
        </div>
      </a>

      <a href="/ver_ordenes" style="text-decoration:none; color:inherit;">
        <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
          <h3 style="margin:0 0 8px 0;">📋 Ver órdenes</h3>
          <p style="margin:0; color:#6b7280;">Ver todas las reparaciones registradas.</p>
        </div>
      </a>

      <a href="/logout" style="text-decoration:none; color:inherit;">
        <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
          <h3 style="margin:0 0 8px 0;">🚪 Salir</h3>
          <p style="margin:0; color:#6b7280;">Cerrar sesión del sistema.</p>
        </div>
      </a>
    </div>
    """

    return html_layout("Inicio", contenido)


@app.route("/crear", methods=["GET", "POST"])
def crear():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        return html_layout(
            "Crear orden",
            card_html("""
            <h2 style="margin-top:0;">Crear orden</h2>
            <form method="post">
              <label>Nombre</label><br>
              <input name="nombre" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Teléfono</label><br>
              <input name="telefono" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Email</label><br>
              <input name="email" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:20px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Tipo equipo</label><br>
              <input name="tipo" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Marca</label><br>
              <input name="marca" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Modelo</label><br>
              <input name="modelo" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>N° serie</label><br>
              <input name="numero_serie" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>IMEI</label><br>
              <input name="imei" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Estado general</label><br>
              <input name="estado_general" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Falla cliente</label><br>
              <input name="falla_cliente" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:18px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <button type="submit" style="background:#2563eb; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Guardar</button>
            </form>

            <p style="margin-top:18px;"><a href="/" style="color:#2563eb; font-weight:bold;">Volver</a></p>
            """)
        )

    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    email = request.form.get("email", "").strip()
    tipo = request.form.get("tipo", "").strip()
    marca = request.form.get("marca", "").strip()
    modelo = request.form.get("modelo", "").strip()
    numero_serie = request.form.get("numero_serie", "").strip()
    imei = request.form.get("imei", "").strip()
    estado_general = request.form.get("estado_general", "").strip()
    falla_cliente = request.form.get("falla_cliente", "").strip()

    con = db()
    cur = con.cursor()

    cur.execute("SELECT id FROM clientes WHERE email=%s", (email,))
    row = cur.fetchone()

    if row:
        cliente_id = row["id"]
    else:
        cur.execute(
            "INSERT INTO clientes(nombre,telefono,email) VALUES(%s,%s,%s) RETURNING id",
            (nombre, telefono, email),
        )
        cliente_id = cur.fetchone()["id"]

    token_aprobacion = secrets.token_urlsafe(32)

    cur.execute(
        """
        INSERT INTO ordenes(
            numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
            estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado,
            presupuesto, observaciones, token_aprobacion, presupuesto_aprobado,
            fecha_aprobacion, presupuesto_rechazado, fecha_rechazo
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            "",
            cliente_id,
            tipo,
            marca,
            modelo,
            numero_serie,
            imei,
            estado_general,
            falla_cliente,
            "",
            "Recibido en taller",
            0,
            "",
            token_aprobacion,
            False,
            None,
            False,
            None,
        ),
    )

    oid = cur.fetchone()["id"]
    anio = datetime.datetime.now().year
    numero_orden = f"NR-{anio}-{oid:04d}"

    cur.execute("UPDATE ordenes SET numero_orden=%s WHERE id=%s", (numero_orden, oid))
    con.commit()
    con.close()

    enviar_email(
        destino=email,
        numero_orden=numero_orden,
        cliente=nombre,
        tipo=tipo,
        marca=marca,
        modelo=modelo,
        estado="Recibido en taller",
        presupuesto=0,
        tipo_mensaje="ingreso",
        token_aprobacion=token_aprobacion,
        presupuesto_aprobado=False,
        presupuesto_rechazado=False
    )

    return html_layout(
        "Orden creada",
        card_html(f"""
        <h2 style="margin-top:0;">Orden creada correctamente</h2>
        <p><strong>Número:</strong> {numero_orden}</p>
        <p><a href="/buscar?q={numero_orden}" style="color:#2563eb; font-weight:bold;">Ver orden</a></p>
        <p><a href="/" style="color:#2563eb; font-weight:bold;">Volver</a></p>
        """)
    )


@app.get("/buscar")
def buscar():
    if not session.get("login"):
        return redirect("/login")

    q = request.args.get("q", "").strip()

    if not q:
        return html_layout(
            "Buscar orden",
            card_html("""
            <h2 style="margin-top:0;">Buscar orden</h2>
            <form>
              <p style="margin-top:0; color:#6b7280;">Buscar por número, nombre, teléfono, email, IMEI o serie</p>
              <input name="q" style="width:100%; max-width:420px; padding:10px; border:1px solid #d1d5db; border-radius:10px;">
              <button style="margin-left:8px; background:#2563eb; color:white; border:none; padding:11px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Buscar</button>
            </form>
            <p style="margin-top:18px;"><a href="/" style="color:#2563eb; font-weight:bold;">Volver</a></p>
            """)
        )

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT o.numero_orden,c.nombre,o.tipo_equipo,o.marca,o.modelo,
               o.estado,o.presupuesto
        FROM ordenes o
        JOIN clientes c ON o.cliente_id=c.id
        WHERE
            o.numero_orden ILIKE %s OR
            c.nombre ILIKE %s OR
            c.telefono ILIKE %s OR
            c.email ILIKE %s OR
            o.imei ILIKE %s OR
            o.numero_serie ILIKE %s
        """,
        (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"),
    )

    resultados = cur.fetchall()
    con.close()

    if not resultados:
        return html_layout(
            "Sin resultados",
            card_html("""
            <h2 style="margin-top:0;">Sin resultados</h2>
            <p>No se encontró ninguna orden con esa búsqueda.</p>
            <p><a href="/buscar" style="color:#2563eb; font-weight:bold;">Volver a buscar</a></p>
            """)
        )

    html = """
    <h2 style="margin-top:0;">Resultados</h2>
    """ + tabla_estilo_inicio() + """
      <tr style="background:#eff6ff; text-align:left;">
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Número</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Cliente</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Equipo</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Estado</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Presupuesto</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Decisión</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for r in resultados:
        equipo = f"{r['tipo_equipo']} {r['marca']} {r['modelo']}"
        pres = "En diagnóstico" if float(r["presupuesto"] or 0) == 0 else f"${r['presupuesto']}"
        badge = estado_presupuesto_badge(r["estado"])

        html += f"""
        <tr>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{r['numero_orden']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{r['nombre']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{equipo}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{r['estado']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{pres}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{badge}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">
            <a href="/actualizar?numero={r['numero_orden']}" style="color:#2563eb; font-weight:bold;">Actualizar</a>
          </td>
        </tr>
        """

    html += tabla_estilo_fin()
    html += "<p style='margin-top:18px;'><a href='/' style='color:#2563eb; font-weight:bold;'>Volver</a></p>"

    return html_layout("Resultados", card_html(html))


@app.get("/ver_ordenes")
def ver_ordenes():
    if not session.get("login"):
        return redirect("/login")

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT o.numero_orden,c.nombre,o.tipo_equipo,o.marca,o.modelo,
               o.estado,o.presupuesto
        FROM ordenes o
        JOIN clientes c ON o.cliente_id=c.id
        ORDER BY o.id DESC
        """
    )

    ordenes = cur.fetchall()
    con.close()

    html = """
    <h2 style="margin-top:0;">Todas las órdenes</h2>
    """ + tabla_estilo_inicio() + """
      <tr style="background:#eff6ff; text-align:left;">
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Número</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Cliente</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Equipo</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Estado</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Presupuesto</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Decisión</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for o in ordenes:
        equipo = f"{o['tipo_equipo']} {o['marca']} {o['modelo']}"
        pres = "En diagnóstico" if float(o["presupuesto"] or 0) == 0 else f"${o['presupuesto']}"
        badge = estado_presupuesto_badge(o["estado"])

        html += f"""
        <tr>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{o['numero_orden']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{o['nombre']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{equipo}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{o['estado']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{pres}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{badge}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">
            <a href="/actualizar?numero={o['numero_orden']}" style="color:#2563eb; font-weight:bold;">Actualizar</a>
          </td>
        </tr>
        """

    html += tabla_estilo_fin()
    html += "<p style='margin-top:18px;'><a href='/' style='color:#2563eb; font-weight:bold;'>Volver</a></p>"

    return html_layout("Todas las órdenes", card_html(html))


@app.route("/actualizar", methods=["GET", "POST"])
def actualizar():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        numero = request.args.get("numero", "").strip()

        return html_layout(
            "Actualizar orden",
            card_html(f"""
            <h2 style="margin-top:0;">Actualizar orden</h2>
            <form method="post">
              <label>Número</label><br>
              <input name="numero" value="{numero}" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:16px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Estado</label><br>
              <select name="estado" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:16px; border:1px solid #d1d5db; border-radius:10px;">
                <option value="">-- elegir --</option>
                <option value="En diagnóstico">En diagnóstico</option>
                <option value="Esperando aprobación">Esperando aprobación</option>
                <option value="Aprobado">Aprobado</option>
                <option value="Rechazado">Rechazado</option>
                <option value="Esperando repuesto">Esperando repuesto</option>
                <option value="En reparación">En reparación</option>
                <option value="Listo para retirar">Listo para retirar</option>
                <option value="Entregado">Entregado</option>
              </select><br>

              <label>Diagnóstico</label><br>
              <input name="diag" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:16px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Presupuesto</label><br>
              <input name="presupuesto" style="width:100%; max-width:420px; padding:10px; margin-top:6px; margin-bottom:18px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <button style="background:#2563eb; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Guardar</button>
            </form>

            <p style="margin-top:18px;"><a href="/" style="color:#2563eb; font-weight:bold;">Volver</a></p>
            """)
        )

    numero = request.form.get("numero", "").strip()
    estado = request.form.get("estado", "").strip()
    diag = request.form.get("diag", "").strip()
    pres = request.form.get("presupuesto", "").strip()

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT o.*, c.nombre, c.email
        FROM ordenes o
        JOIN clientes c ON o.cliente_id = c.id
        WHERE o.numero_orden = %s
        """,
        (numero,),
    )
    actual = cur.fetchone()

    if not actual:
        con.close()
        return html_layout("No encontrada", card_html("<h2 style='margin-top:0;'>Orden no encontrada</h2>"))

    if estado == "Esperando aprobación":
        nuevo_token = secrets.token_urlsafe(32)
        cur.execute(
            """
            UPDATE ordenes
            SET token_aprobacion=%s,
                presupuesto_aprobado=FALSE,
                fecha_aprobacion=NULL,
                presupuesto_rechazado=FALSE,
                fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (nuevo_token, numero),
        )

    if estado == "Aprobado":
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_aprobado=TRUE,
                fecha_aprobacion=%s,
                presupuesto_rechazado=FALSE,
                fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (datetime.datetime.now(), numero),
        )

    if estado == "Rechazado":
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_rechazado=TRUE,
                fecha_rechazo=%s,
                presupuesto_aprobado=FALSE,
                fecha_aprobacion=NULL
            WHERE numero_orden=%s
            """,
            (datetime.datetime.now(), numero),
        )

    if estado and estado not in ["Aprobado", "Rechazado", "Esperando aprobación"]:
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_aprobado=FALSE,
                fecha_aprobacion=NULL,
                presupuesto_rechazado=FALSE,
                fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (numero,),
        )

    if estado:
        cur.execute("UPDATE ordenes SET estado=%s WHERE numero_orden=%s", (estado, numero))

    if diag:
        cur.execute("UPDATE ordenes SET diagnostico_tecnico=%s WHERE numero_orden=%s", (diag, numero))

    if pres:
        cur.execute("UPDATE ordenes SET presupuesto=%s WHERE numero_orden=%s", (pres, numero))

    cur.execute(
        """
        SELECT o.numero_orden, c.nombre, c.email, o.tipo_equipo, o.marca, o.modelo,
               o.estado, o.presupuesto, o.token_aprobacion,
               o.presupuesto_aprobado, o.presupuesto_rechazado
        FROM ordenes o
        JOIN clientes c ON o.cliente_id=c.id
        WHERE o.numero_orden=%s
        """,
        (numero,),
    )
    info = cur.fetchone()

    con.commit()
    con.close()

    if info and info["email"]:
        enviar_email(
            destino=info["email"],
            numero_orden=info["numero_orden"],
            cliente=info["nombre"],
            tipo=info["tipo_equipo"],
            marca=info["marca"],
            modelo=info["modelo"],
            estado=info["estado"],
            presupuesto=info["presupuesto"],
            tipo_mensaje="actualizacion",
            token_aprobacion=info["token_aprobacion"],
            presupuesto_aprobado=info["presupuesto_aprobado"],
            presupuesto_rechazado=info["presupuesto_rechazado"]
        )

    return redirect(f"/buscar?q={numero}")


@app.get("/aceptar_presupuesto/<token>")
def aceptar_presupuesto(token):
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT o.numero_orden, o.tipo_equipo, o.marca, o.modelo, o.estado,
               o.presupuesto, o.presupuesto_aprobado, o.presupuesto_rechazado
        FROM ordenes o
        WHERE o.token_aprobacion=%s
        """,
        (token,),
    )
    orden = cur.fetchone()
    con.close()

    if not orden:
        return html_layout("Link inválido", card_html("<h2 style='margin-top:0;'>Link inválido o vencido</h2><p>Este enlace no es válido.</p>"))

    if orden["presupuesto_aprobado"]:
        return html_layout("Ya aceptado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya aceptado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue aceptada anteriormente.</p>"))

    if orden["presupuesto_rechazado"]:
        return html_layout("Ya rechazado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya rechazado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue rechazada anteriormente.</p>"))

    if orden["estado"] != "Esperando aprobación":
        return html_layout("No pendiente", card_html(f"<h2 style='margin-top:0;'>Esta orden ya no está pendiente</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya no se encuentra esperando aprobación.</p>"))

    pres = "En diagnóstico" if float(orden["presupuesto"] or 0) == 0 else f"${orden['presupuesto']}"
    equipo = f"{orden['tipo_equipo']} {orden['marca']} {orden['modelo']}"

    return html_layout(
        "Confirmación",
        card_html(f"""
        <h2 style="margin-top:0;">Confirmación de presupuesto</h2>
        <p><strong>Orden:</strong> {orden["numero_orden"]}</p>
        <p><strong>Equipo:</strong> {equipo}</p>
        <p><strong>Presupuesto:</strong> {pres}</p>

        <div style="background:#fff7ed; border:1px solid #fdba74; padding:14px; border-radius:12px; margin:18px 0;">
          Está a punto de aceptar el presupuesto de esta reparación.<br>
          Al confirmar, autoriza a NR Tech a continuar con el trabajo.
        </div>

        <p><strong>¿Está seguro que desea continuar?</strong></p>

        <form method="post" action="/confirmar_presupuesto/{token}">
          <button type="submit" style="background:#16a34a; color:white; border:none; padding:14px 22px; border-radius:12px; font-size:15px; cursor:pointer;">
            Sí, aceptar presupuesto
          </button>
        </form>
        """)
    )


@app.post("/confirmar_presupuesto/<token>")
def confirmar_presupuesto(token):
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT numero_orden, tipo_equipo, marca, modelo, estado, presupuesto,
               presupuesto_aprobado, presupuesto_rechazado
        FROM ordenes
        WHERE token_aprobacion=%s
        """,
        (token,),
    )
    orden = cur.fetchone()

    if not orden:
        con.close()
        return html_layout("Link inválido", card_html("<h2 style='margin-top:0;'>Link inválido o vencido</h2><p>Este enlace no es válido.</p>"))

    if orden["presupuesto_aprobado"]:
        con.close()
        return html_layout("Ya aceptado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya aceptado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue aceptada anteriormente.</p>"))

    if orden["presupuesto_rechazado"]:
        con.close()
        return html_layout("Ya rechazado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya rechazado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue rechazada anteriormente.</p>"))

    if orden["estado"] != "Esperando aprobación":
        con.close()
        return html_layout("No pendiente", card_html(f"<h2 style='margin-top:0;'>Esta orden ya no está pendiente</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya no se encuentra esperando aprobación.</p>"))

    cur.execute(
        """
        UPDATE ordenes
        SET presupuesto_aprobado=TRUE,
            fecha_aprobacion=%s,
            presupuesto_rechazado=FALSE,
            fecha_rechazo=NULL,
            estado=%s
        WHERE token_aprobacion=%s
        """,
        (datetime.datetime.now(), "Aprobado", token),
    )

    con.commit()
    con.close()

    equipo = f"{orden['tipo_equipo']} {orden['marca']} {orden['modelo']}"

    return html_layout(
        "Aceptado",
        card_html(f"""
        <h2 style="margin-top:0; color:#16a34a;">Presupuesto aceptado correctamente</h2>
        <p>Gracias por confirmar.</p>
        <p><strong>Orden:</strong> {orden["numero_orden"]}</p>
        <p><strong>Equipo:</strong> {equipo}</p>
        <p>NR Tech continuará con la reparación a la brevedad.</p>
        """)
    )


@app.get("/rechazar_presupuesto/<token>")
def rechazar_presupuesto(token):
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT o.numero_orden, o.tipo_equipo, o.marca, o.modelo, o.estado,
               o.presupuesto, o.presupuesto_aprobado, o.presupuesto_rechazado
        FROM ordenes o
        WHERE o.token_aprobacion=%s
        """,
        (token,),
    )
    orden = cur.fetchone()
    con.close()

    if not orden:
        return html_layout("Link inválido", card_html("<h2 style='margin-top:0;'>Link inválido o vencido</h2><p>Este enlace no es válido.</p>"))

    if orden["presupuesto_rechazado"]:
        return html_layout("Ya rechazado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya rechazado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue rechazada anteriormente.</p>"))

    if orden["presupuesto_aprobado"]:
        return html_layout("Ya aceptado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya aceptado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue aceptada anteriormente.</p>"))

    if orden["estado"] != "Esperando aprobación":
        return html_layout("No pendiente", card_html(f"<h2 style='margin-top:0;'>Esta orden ya no está pendiente</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya no se encuentra esperando aprobación.</p>"))

    pres = "En diagnóstico" if float(orden["presupuesto"] or 0) == 0 else f"${orden['presupuesto']}"
    equipo = f"{orden['tipo_equipo']} {orden['marca']} {orden['modelo']}"

    return html_layout(
        "Rechazo",
        card_html(f"""
        <h2 style="margin-top:0;">Rechazo de presupuesto</h2>
        <p><strong>Orden:</strong> {orden["numero_orden"]}</p>
        <p><strong>Equipo:</strong> {equipo}</p>
        <p><strong>Presupuesto:</strong> {pres}</p>

        <div style="background:#fef2f2; border:1px solid #fca5a5; padding:14px; border-radius:12px; margin:18px 0;">
          Está a punto de rechazar el presupuesto de esta reparación.
        </div>

        <p><strong>¿Está seguro que desea rechazarlo?</strong></p>

        <form method="post" action="/confirmar_rechazo_presupuesto/{token}">
          <button type="submit" style="background:#dc2626; color:white; border:none; padding:14px 22px; border-radius:12px; font-size:15px; cursor:pointer;">
            Sí, rechazar presupuesto
          </button>
        </form>
        """)
    )


@app.post("/confirmar_rechazo_presupuesto/<token>")
def confirmar_rechazo_presupuesto(token):
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT numero_orden, tipo_equipo, marca, modelo, estado, presupuesto,
               presupuesto_aprobado, presupuesto_rechazado
        FROM ordenes
        WHERE token_aprobacion=%s
        """,
        (token,),
    )
    orden = cur.fetchone()

    if not orden:
        con.close()
        return html_layout("Link inválido", card_html("<h2 style='margin-top:0;'>Link inválido o vencido</h2><p>Este enlace no es válido.</p>"))

    if orden["presupuesto_rechazado"]:
        con.close()
        return html_layout("Ya rechazado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya rechazado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue rechazada anteriormente.</p>"))

    if orden["presupuesto_aprobado"]:
        con.close()
        return html_layout("Ya aceptado", card_html(f"<h2 style='margin-top:0;'>Presupuesto ya aceptado</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya fue aceptada anteriormente.</p>"))

    if orden["estado"] != "Esperando aprobación":
        con.close()
        return html_layout("No pendiente", card_html(f"<h2 style='margin-top:0;'>Esta orden ya no está pendiente</h2><p>La orden <strong>{orden['numero_orden']}</strong> ya no se encuentra esperando aprobación.</p>"))

    cur.execute(
        """
        UPDATE ordenes
        SET presupuesto_rechazado=TRUE,
            fecha_rechazo=%s,
            presupuesto_aprobado=FALSE,
            fecha_aprobacion=NULL,
            estado=%s
        WHERE token_aprobacion=%s
        """,
        (datetime.datetime.now(), "Rechazado", token),
    )

    con.commit()
    con.close()

    equipo = f"{orden['tipo_equipo']} {orden['marca']} {orden['modelo']}"

    return html_layout(
        "Rechazado",
        card_html(f"""
        <h2 style="margin-top:0; color:#dc2626;">Presupuesto rechazado</h2>
        <p>La decisión fue registrada correctamente.</p>
        <p><strong>Orden:</strong> {orden["numero_orden"]}</p>
        <p><strong>Equipo:</strong> {equipo}</p>
        <p>Si desea retomar la reparación más adelante, podrá comunicarse con NR Tech.</p>
        """)
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)