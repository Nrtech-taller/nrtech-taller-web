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


@app.after_request
def evitar_cache(response):
    # El sistema cambia datos frecuentemente. Evitamos que el navegador
    # muestre listados viejos al volver atrás o después de actualizar.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
    email TEXT,
    direccion TEXT,
    cedula TEXT,
    notas TEXT,
    fecha_alta TIMESTAMP DEFAULT NOW()
);
""")

    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS direccion TEXT;")
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cedula TEXT;")
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS notas TEXT;")
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS fecha_alta TIMESTAMP DEFAULT NOW();")

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
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS accesorios TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_entrega DATE;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS servicio_rapido TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS bloqueo_tipo TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS clave_bloqueo TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS patron_bloqueo TEXT;")

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

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT estado, COUNT(*) as total
        FROM ordenes
        GROUP BY estado
    """)
    estados_raw = cur.fetchall()
    con.close()

    resumen = {
        "Recibido en taller": 0,
        "En diagnóstico": 0,
        "Esperando aprobación": 0,
        "Esperando repuesto": 0,
        "En reparación": 0,
        "Listo para retirar": 0,
    }

    for fila in estados_raw:
        if fila["estado"] in resumen:
            resumen[fila["estado"]] = fila["total"]

    contenido = f"""
    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:20px;">
      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">Recibidos</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("Recibido en taller", 0)}</p>
      </div>

      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">Diagnóstico</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("En diagnóstico", 0)}</p>
      </div>

      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">Esperando aprobación</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("Esperando aprobación", 0)}</p>
      </div>

      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">Esperando repuesto</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("Esperando repuesto", 0)}</p>
      </div>

      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">En reparación</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("En reparación", 0)}</p>
      </div>

      <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
        <h3 style="margin:0 0 6px 0;">Listo para retirar</h3>
        <p style="margin:0; font-size:28px; font-weight:bold;">{resumen.get("Listo para retirar", 0)}</p>
      </div>
    </div>

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

      <a href="/clientes" style="text-decoration:none; color:inherit;">
        <div style="background:white; border:1px solid #e5e7eb; border-radius:18px; padding:22px; box-shadow:0 8px 24px rgba(15,23,42,0.06);">
          <h3 style="margin:0 0 8px 0;">👤 Clientes</h3>
          <p style="margin:0; color:#6b7280;">Ver fichas e historial de cada cliente.</p>
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
            <p style="color:#6b7280; margin-top:-6px;">Ingreso rápido y completo del equipo.</p>

            <form method="post" id="formOrden">
              <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px;">
                <div>
                  <h3 style="margin-top:0;">👤 Cliente</h3>
                  <label>Nombre</label><br>
                  <input name="nombre" required style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>Teléfono</label><br>
                  <input name="telefono" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>Email</label><br>
                  <input name="email" type="email" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>Dirección</label><br>
                  <input name="direccion" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>Cédula</label><br>
                  <input name="cedula" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>
                </div>

                <div>
                  <h3 style="margin-top:0;">📱 Equipo</h3>
                  <label>Tipo de equipo</label><br>
                  <select name="tipo" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;">
                    <option value="Celular">Celular</option>
                    <option value="Tablet">Tablet</option>
                    <option value="Notebook">Notebook</option>
                    <option value="PC">PC</option>
                    <option value="Consola">Consola</option>
                    <option value="Otro">Otro</option>
                  </select><br>

                  <label>Marca</label><br>
                  <input name="marca" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>Modelo</label><br>
                  <input name="modelo" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>

                  <label>IMEI / Serie</label><br>
                  <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                    <input name="imei" placeholder="IMEI" style="width:100%; padding:10px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;">
                    <input name="numero_serie" placeholder="N° de serie" style="width:100%; padding:10px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;">
                  </div>

                  <label style="display:block; margin-top:12px;">Accesorios recibidos</label>
                  <input name="accesorios" placeholder="Ej: funda, cargador, sin accesorios" style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;">

                  <label>Estado general</label><br>
                  <input name="estado_general" placeholder="Ej: pantalla rota, marcas de uso..." style="width:100%; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"><br>
                </div>
              </div>

              <div style="margin-top:20px; padding:18px; background:#f8fafc; border:1px solid #e5e7eb; border-radius:14px;">
                <h3 style="margin-top:0;">⚡ Servicio rápido</h3>
                <label>Plantilla</label><br>
                <select name="servicio_rapido" id="servicioRapido" onchange="aplicarServicio()" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;">
                  <option value="">Elegir servicio...</option>
                  <option value="Cambio de módulo / pantalla">Cambio de módulo / pantalla</option>
                  <option value="Cambio de batería">Cambio de batería</option>
                  <option value="Pin / conector de carga">Pin / conector de carga</option>
                  <option value="No enciende">No enciende</option>
                  <option value="Software / sistema">Software / sistema</option>
                  <option value="Mantenimiento PC">Mantenimiento PC</option>
                  <option value="Diagnóstico general">Diagnóstico general</option>
                  <option value="Otro">Otro</option>
                </select><br>

                <label>Falla declarada por el cliente</label><br>
                <textarea name="falla_cliente" id="fallaCliente" rows="3" style="width:100%; max-width:760px; padding:10px; margin:6px 0 12px; box-sizing:border-box; border:1px solid #d1d5db; border-radius:10px;"></textarea><br>

                <label>Fecha estimada de entrega</label><br>
                <input type="date" name="fecha_entrega" style="width:100%; max-width:260px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>
              </div>

              <div style="margin-top:20px; padding:18px; background:#fff7ed; border:1px solid #fed7aa; border-radius:14px;">
                <h3 style="margin-top:0;">🔐 Acceso al equipo</h3>
                <label>Tipo de bloqueo</label><br>
                <select name="bloqueo_tipo" id="bloqueoTipo" onchange="mostrarBloqueo()" style="width:100%; max-width:300px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;">
                  <option value="Sin bloqueo">Sin bloqueo</option>
                  <option value="PIN / clave">PIN / clave</option>
                  <option value="Patrón">Patrón</option>
                </select>

                <div id="bloqueoClave" style="display:none; margin-top:8px;">
                  <label>PIN / clave</label><br>
                  <input name="clave_bloqueo" autocomplete="off" style="width:100%; max-width:300px; padding:10px; margin-top:6px; border:1px solid #d1d5db; border-radius:10px;">
                </div>

                <div id="bloqueoPatron" style="display:none; margin-top:12px;">
                  <input type="hidden" name="patron_bloqueo" id="patronBloqueo">
                  <div id="patronGrid" style="display:grid; grid-template-columns:repeat(3,56px); gap:10px; width:max-content; margin:8px 0;">
                    <button type="button" onclick="puntoPatron(1,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">1</button>
                    <button type="button" onclick="puntoPatron(2,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">2</button>
                    <button type="button" onclick="puntoPatron(3,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">3</button>
                    <button type="button" onclick="puntoPatron(4,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">4</button>
                    <button type="button" onclick="puntoPatron(5,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">5</button>
                    <button type="button" onclick="puntoPatron(6,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">6</button>
                    <button type="button" onclick="puntoPatron(7,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">7</button>
                    <button type="button" onclick="puntoPatron(8,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">8</button>
                    <button type="button" onclick="puntoPatron(9,this)" style="width:56px;height:56px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:bold;">9</button>
                  </div>
                  <div id="patronTexto" style="font-size:13px; color:#6b7280; margin-bottom:8px;">Patrón: -</div>
                  <button type="button" onclick="limpiarPatron()" style="background:#e5e7eb;border:none;padding:8px 12px;border-radius:9px;cursor:pointer;">Limpiar patrón</button>
                </div>
              </div>

              <label style="display:flex; align-items:center; gap:10px; margin:18px 0; max-width:620px; padding:12px 14px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:12px;">
                <input type="checkbox" name="enviar_email_ingreso" value="1" style="width:18px; height:18px;">
                <span><strong>Enviar confirmación de ingreso por email</strong><br><small style="color:#6b7280;">Solo se envía si lo marcás.</small></span>
              </label>

              <button type="submit" style="background:#2563eb; color:white; border:none; padding:13px 20px; border-radius:12px; font-weight:bold; cursor:pointer;">Guardar orden</button>
              <a href="/" style="margin-left:12px; color:#2563eb; font-weight:bold; text-decoration:none;">Cancelar</a>
            </form>

            <script>
              const plantillas = {
                "Cambio de módulo / pantalla": "Cliente declara pantalla rota, sin imagen, con manchas, líneas, parpadeo o falla de táctil.",
                "Cambio de batería": "Cliente declara poca duración de batería, apagados inesperados o batería degradada.",
                "Pin / conector de carga": "Cliente declara que el equipo no carga, carga intermitente o presenta juego en el conector.",
                "No enciende": "Cliente declara que el equipo no enciende o no da señales de funcionamiento.",
                "Software / sistema": "Cliente solicita revisión de software, sistema operativo, lentitud, errores o configuración.",
                "Mantenimiento PC": "Cliente solicita mantenimiento general, limpieza interna y control de temperaturas.",
                "Diagnóstico general": "Cliente solicita diagnóstico técnico para determinar la falla del equipo."
              };

              function aplicarServicio(){
                const servicio = document.getElementById('servicioRapido').value;
                const falla = document.getElementById('fallaCliente');
                if (plantillas[servicio] && !falla.value.trim()) falla.value = plantillas[servicio];
              }

              let patron = [];
              function mostrarBloqueo(){
                const tipo = document.getElementById('bloqueoTipo').value;
                document.getElementById('bloqueoClave').style.display = tipo === 'PIN / clave' ? 'block' : 'none';
                document.getElementById('bloqueoPatron').style.display = tipo === 'Patrón' ? 'block' : 'none';
              }
              function puntoPatron(n, btn){
                if (patron.includes(n)) return;
                patron.push(n);
                btn.style.background = '#0ea5e9';
                btn.style.color = 'white';
                document.getElementById('patronBloqueo').value = patron.join('-');
                document.getElementById('patronTexto').innerText = 'Patrón: ' + patron.join(' → ');
              }
              function limpiarPatron(){
                patron = [];
                document.getElementById('patronBloqueo').value = '';
                document.getElementById('patronTexto').innerText = 'Patrón: -';
                document.querySelectorAll('#patronGrid button').forEach(b => { b.style.background='white'; b.style.color='#111827'; });
              }
            </script>
            """)
        )

    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    email = request.form.get("email", "").strip()
    direccion = request.form.get("direccion", "").strip()
    cedula = request.form.get("cedula", "").strip()
    notas = request.form.get("notas", "").strip()
    tipo = request.form.get("tipo", "").strip()
    marca = request.form.get("marca", "").strip()
    modelo = request.form.get("modelo", "").strip()
    numero_serie = request.form.get("numero_serie", "").strip()
    imei = request.form.get("imei", "").strip()
    estado_general = request.form.get("estado_general", "").strip()
    falla_cliente = request.form.get("falla_cliente", "").strip()
    accesorios = request.form.get("accesorios", "").strip()
    fecha_entrega = request.form.get("fecha_entrega", "").strip() or None
    servicio_rapido = request.form.get("servicio_rapido", "").strip()
    bloqueo_tipo = request.form.get("bloqueo_tipo", "").strip()
    clave_bloqueo = request.form.get("clave_bloqueo", "").strip()
    patron_bloqueo = request.form.get("patron_bloqueo", "").strip()
    enviar_ingreso = request.form.get("enviar_email_ingreso") == "1"

    con = db()
    cur = con.cursor()
    cliente_id = None

    if telefono:
        cur.execute("SELECT id FROM clientes WHERE telefono=%s LIMIT 1", (telefono,))
        row = cur.fetchone()
        if row:
            cliente_id = row["id"]

    if not cliente_id and email:
        cur.execute("SELECT id FROM clientes WHERE email=%s LIMIT 1", (email,))
        row = cur.fetchone()
        if row:
            cliente_id = row["id"]

    if cliente_id:
        cur.execute("""
            UPDATE clientes
            SET nombre=%s, telefono=%s, email=%s, direccion=%s, cedula=%s, notas=%s
            WHERE id=%s
        """, (nombre, telefono, email, direccion, cedula, notas, cliente_id))
    else:
        cur.execute("""
            INSERT INTO clientes(nombre, telefono, email, direccion, cedula, notas)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING id
        """, (nombre, telefono, email, direccion, cedula, notas))
        cliente_id = cur.fetchone()["id"]

    token_aprobacion = secrets.token_urlsafe(32)
    cur.execute(
        """
        INSERT INTO ordenes(
            numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
            estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado,
            presupuesto, observaciones, token_aprobacion, presupuesto_aprobado,
            fecha_aprobacion, presupuesto_rechazado, fecha_rechazo,
            accesorios, fecha_entrega, servicio_rapido, bloqueo_tipo, clave_bloqueo, patron_bloqueo
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            "", cliente_id, tipo, marca, modelo, numero_serie, imei,
            estado_general, falla_cliente, "", "Recibido en taller", 0, "",
            token_aprobacion, False, None, False, None,
            accesorios, fecha_entrega, servicio_rapido, bloqueo_tipo, clave_bloqueo, patron_bloqueo,
        ),
    )

    oid = cur.fetchone()["id"]
    anio = datetime.datetime.now().year
    numero_orden = f"NR-{anio}-{oid:04d}"
    cur.execute("UPDATE ordenes SET numero_orden=%s WHERE id=%s", (numero_orden, oid))
    con.commit()
    con.close()

    if enviar_ingreso and email:
        enviar_email(
            destino=email, numero_orden=numero_orden, cliente=nombre, tipo=tipo, marca=marca,
            modelo=modelo, estado="Recibido en taller", presupuesto=0, tipo_mensaje="ingreso",
            token_aprobacion=token_aprobacion, presupuesto_aprobado=False, presupuesto_rechazado=False
        )

    return redirect(f"/editar?numero={numero_orden}")


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
            <a href="/editar?numero={r['numero_orden']}" style="color:#0f766e; font-weight:bold; margin-right:10px;">Editar</a>
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
            <a href="/editar?numero={o['numero_orden']}" style="color:#0f766e; font-weight:bold; margin-right:10px;">Editar</a>
            <a href="/actualizar?numero={o['numero_orden']}" style="color:#2563eb; font-weight:bold;">Actualizar</a>
          </td>
        </tr>
        """

    html += tabla_estilo_fin()
    html += "<p style='margin-top:18px;'><a href='/' style='color:#2563eb; font-weight:bold;'>Volver</a></p>"

    return html_layout("Todas las órdenes", card_html(html))


@app.route("/editar", methods=["GET", "POST"])
def editar():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        numero = request.args.get("numero", "").strip()
        if not numero:
            return redirect("/buscar")

        con = db()
        cur = con.cursor()
        cur.execute(
            """
            SELECT o.*, c.nombre, c.telefono, c.email, c.direccion, c.cedula, c.notas
            FROM ordenes o
            JOIN clientes c ON o.cliente_id=c.id
            WHERE o.numero_orden=%s
            """,
            (numero,),
        )
        x = cur.fetchone()
        con.close()

        if not x:
            return html_layout("No encontrada", card_html("<h2 style='margin-top:0;'>Orden no encontrada</h2>"))

        def val(campo):
            return str(x[campo] or "").replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

        return html_layout(
            "Editar orden",
            card_html(f"""
            <h2 style="margin-top:0;">Editar orden {val('numero_orden')}</h2>
            <p style="color:#6b7280; margin-top:-6px;">Corregí los datos sin enviar ningún email al cliente.</p>

            <form method="post">
              <input type="hidden" name="numero" value="{val('numero_orden')}">

              <h3>Cliente</h3>
              <label>Nombre</label><br>
              <input name="nombre" value="{val('nombre')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Teléfono</label><br>
              <input name="telefono" value="{val('telefono')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Email</label><br>
              <input name="email" type="email" value="{val('email')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Dirección</label><br>
              <input name="direccion" value="{val('direccion')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Cédula</label><br>
              <input name="cedula" value="{val('cedula')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Notas cliente</label><br>
              <input name="notas" value="{val('notas')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 18px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <h3>Equipo</h3>
              <label>Tipo de equipo</label><br>
              <input name="tipo" value="{val('tipo_equipo')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Marca</label><br>
              <input name="marca" value="{val('marca')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Modelo</label><br>
              <input name="modelo" value="{val('modelo')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>N° de serie</label><br>
              <input name="numero_serie" value="{val('numero_serie')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>IMEI</label><br>
              <input name="imei" value="{val('imei')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Estado general</label><br>
              <input name="estado_general" value="{val('estado_general')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Accesorios recibidos</label><br>
              <input name="accesorios" value="{val('accesorios')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Servicio rápido / plantilla</label><br>
              <input name="servicio_rapido" value="{val('servicio_rapido')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Fecha estimada de entrega</label><br>
              <input type="date" name="fecha_entrega" value="{val('fecha_entrega')}" style="width:100%; max-width:260px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Tipo de bloqueo</label><br>
              <input name="bloqueo_tipo" value="{val('bloqueo_tipo')}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>PIN / clave</label><br>
              <input name="clave_bloqueo" value="{val('clave_bloqueo')}" autocomplete="off" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Patrón</label><br>
              <input name="patron_bloqueo" value="{val('patron_bloqueo')}" placeholder="Ej: 1-2-5-8" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label>Falla declarada por el cliente</label><br>
              <textarea name="falla_cliente" rows="3" style="width:100%; max-width:520px; padding:10px; margin:6px 0 12px; border:1px solid #d1d5db; border-radius:10px;">{val('falla_cliente')}</textarea><br>

              <label>Observaciones</label><br>
              <textarea name="observaciones" rows="3" style="width:100%; max-width:520px; padding:10px; margin:6px 0 18px; border:1px solid #d1d5db; border-radius:10px;">{val('observaciones')}</textarea><br>

              <button type="submit" style="background:#0f766e; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Guardar correcciones</button>
              <a href="/actualizar?numero={val('numero_orden')}" style="margin-left:12px; color:#2563eb; font-weight:bold; text-decoration:none;">Actualizar reparación</a>
            </form>

            <div style="margin-top:16px; padding:12px 14px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:12px; color:#166534;">
              Guardar aquí <strong>no envía email</strong> al cliente.
            </div>

            <div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:16px;">
              <a href="/ver_ordenes" style="display:inline-block; background:#111827; color:white; padding:10px 16px; border-radius:10px; font-weight:bold; text-decoration:none;">📋 Ver órdenes</a>
              <a href="/" style="display:inline-block; background:#e5e7eb; color:#111827; padding:10px 16px; border-radius:10px; font-weight:bold; text-decoration:none;">🏠 Inicio</a>
            </div>
            """)
        )

    numero = request.form.get("numero", "").strip()
    con = db()
    cur = con.cursor()
    cur.execute("SELECT cliente_id FROM ordenes WHERE numero_orden=%s", (numero,))
    orden = cur.fetchone()
    if not orden:
        con.close()
        return html_layout("No encontrada", card_html("<h2 style='margin-top:0;'>Orden no encontrada</h2>"))

    cliente_id = orden["cliente_id"]
    cur.execute(
        """
        UPDATE clientes
        SET nombre=%s, telefono=%s, email=%s, direccion=%s, cedula=%s, notas=%s
        WHERE id=%s
        """,
        (
            request.form.get("nombre", "").strip(),
            request.form.get("telefono", "").strip(),
            request.form.get("email", "").strip(),
            request.form.get("direccion", "").strip(),
            request.form.get("cedula", "").strip(),
            request.form.get("notas", "").strip(),
            cliente_id,
        ),
    )
    cur.execute(
        """
        UPDATE ordenes
        SET tipo_equipo=%s, marca=%s, modelo=%s, numero_serie=%s, imei=%s,
            estado_general=%s, accesorios=%s, servicio_rapido=%s, fecha_entrega=%s,
            bloqueo_tipo=%s, clave_bloqueo=%s, patron_bloqueo=%s,
            falla_cliente=%s, observaciones=%s
        WHERE numero_orden=%s
        """,
        (
            request.form.get("tipo", "").strip(),
            request.form.get("marca", "").strip(),
            request.form.get("modelo", "").strip(),
            request.form.get("numero_serie", "").strip(),
            request.form.get("imei", "").strip(),
            request.form.get("estado_general", "").strip(),
            request.form.get("accesorios", "").strip(),
            request.form.get("servicio_rapido", "").strip(),
            request.form.get("fecha_entrega", "").strip() or None,
            request.form.get("bloqueo_tipo", "").strip(),
            request.form.get("clave_bloqueo", "").strip(),
            request.form.get("patron_bloqueo", "").strip(),
            request.form.get("falla_cliente", "").strip(),
            request.form.get("observaciones", "").strip(),
            numero,
        ),
    )
    con.commit()
    con.close()
    return redirect("/ver_ordenes")


@app.route("/actualizar", methods=["GET", "POST"])
def actualizar():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        numero = request.args.get("numero", "").strip()
        if not numero:
            return redirect("/buscar")

        con = db()
        cur = con.cursor()
        cur.execute(
            """
            SELECT o.numero_orden, o.estado, o.diagnostico_tecnico, o.presupuesto,
                   o.token_aprobacion, o.presupuesto_aprobado, o.presupuesto_rechazado,
                   c.nombre, c.email
            FROM ordenes o
            JOIN clientes c ON o.cliente_id=c.id
            WHERE o.numero_orden=%s
            """,
            (numero,),
        )
        actual = cur.fetchone()
        con.close()

        if not actual:
            return html_layout("No encontrada", card_html("<h2 style='margin-top:0;'>Orden no encontrada</h2>"))

        estados = [
            "Recibido en taller", "En diagnóstico", "Esperando aprobación", "Aprobado",
            "Rechazado", "Esperando repuesto", "En reparación", "Listo para retirar", "Entregado"
        ]
        opciones = "".join(
            f'<option value="{e}" {"selected" if actual["estado"] == e else ""}>{e}</option>'
            for e in estados
        )
        diag_val = str(actual["diagnostico_tecnico"] or "").replace('&','&amp;').replace('"','&quot;').replace('<','&lt;').replace('>','&gt;')
        pres_val = str(actual["presupuesto"] or 0)

        boton_presupuesto = ""
        if actual["estado"] == "Esperando aprobación" and float(actual["presupuesto"] or 0) > 0 and actual["email"]:
            boton_presupuesto = f"""
            <form method="post" action="/enviar_presupuesto" style="margin-top:14px;">
              <input type="hidden" name="numero" value="{actual['numero_orden']}">
              <button type="submit" style="background:#f59e0b; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">📧 Enviar presupuesto al cliente</button>
            </form>
            """

        return html_layout(
            "Actualizar orden",
            card_html(f"""
            <h2 style="margin-top:0;">Actualizar orden {actual['numero_orden']}</h2>
            <p style="color:#6b7280; margin-top:-6px;">Los cambios se guardan sin email, salvo que marques la opción de envío.</p>

            <form method="post">
              <input type="hidden" name="numero" value="{actual['numero_orden']}">

              <label>Estado</label><br>
              <select name="estado" style="width:100%; max-width:520px; padding:10px; margin:6px 0 16px; border:1px solid #d1d5db; border-radius:10px;">
                {opciones}
              </select><br>

              <label>Diagnóstico</label><br>
              <textarea name="diag" rows="4" style="width:100%; max-width:520px; padding:10px; margin:6px 0 16px; border:1px solid #d1d5db; border-radius:10px;">{diag_val}</textarea><br>

              <label>Presupuesto</label><br>
              <input name="presupuesto" type="number" step="0.01" min="0" value="{pres_val}" style="width:100%; max-width:520px; padding:10px; margin:6px 0 18px; border:1px solid #d1d5db; border-radius:10px;"><br>

              <label style="display:flex; align-items:center; gap:10px; margin:4px 0 18px; max-width:520px; padding:12px 14px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:12px;">
                <input type="checkbox" name="enviar_email" value="1" style="width:18px; height:18px;">
                <span><strong>Enviar esta actualización por email al cliente</strong><br><small style="color:#6b7280;">Si no lo marcás, el cliente no recibe ningún correo.</small></span>
              </label>

              <button type="submit" style="background:#2563eb; color:white; border:none; padding:12px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Guardar actualización</button>
              <a href="/editar?numero={actual['numero_orden']}" style="margin-left:12px; color:#0f766e; font-weight:bold; text-decoration:none;">Editar datos</a>
            </form>

            {boton_presupuesto}

            <div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:20px;">
              <a href="/ver_ordenes" style="display:inline-block; background:#111827; color:white; padding:10px 16px; border-radius:10px; font-weight:bold; text-decoration:none;">📋 Ver órdenes</a>
              <a href="/" style="display:inline-block; background:#e5e7eb; color:#111827; padding:10px 16px; border-radius:10px; font-weight:bold; text-decoration:none;">🏠 Inicio</a>
            </div>
            """)
        )

    numero = request.form.get("numero", "").strip()
    estado = request.form.get("estado", "").strip()
    diag = request.form.get("diag", "").strip()
    pres = request.form.get("presupuesto", "").strip()
    enviar = request.form.get("enviar_email") == "1"

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

    if estado == "Esperando aprobación" and actual["estado"] != "Esperando aprobación":
        nuevo_token = secrets.token_urlsafe(32)
        cur.execute(
            """
            UPDATE ordenes
            SET token_aprobacion=%s, presupuesto_aprobado=FALSE, fecha_aprobacion=NULL,
                presupuesto_rechazado=FALSE, fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (nuevo_token, numero),
        )

    if estado == "Aprobado":
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_aprobado=TRUE, fecha_aprobacion=%s,
                presupuesto_rechazado=FALSE, fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (datetime.datetime.now(), numero),
        )
    elif estado == "Rechazado":
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_rechazado=TRUE, fecha_rechazo=%s,
                presupuesto_aprobado=FALSE, fecha_aprobacion=NULL
            WHERE numero_orden=%s
            """,
            (datetime.datetime.now(), numero),
        )
    elif estado not in ["Esperando aprobación", "Aprobado", "Rechazado"]:
        cur.execute(
            """
            UPDATE ordenes
            SET presupuesto_aprobado=FALSE, fecha_aprobacion=NULL,
                presupuesto_rechazado=FALSE, fecha_rechazo=NULL
            WHERE numero_orden=%s
            """,
            (numero,),
        )

    cur.execute(
        """
        UPDATE ordenes
        SET estado=%s, diagnostico_tecnico=%s, presupuesto=%s
        WHERE numero_orden=%s
        """,
        (estado or actual["estado"], diag, pres or 0, numero),
    )

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

    if enviar and info and info["email"]:
        enviar_email(
            destino=info["email"], numero_orden=info["numero_orden"], cliente=info["nombre"],
            tipo=info["tipo_equipo"], marca=info["marca"], modelo=info["modelo"],
            estado=info["estado"], presupuesto=info["presupuesto"], tipo_mensaje="actualizacion",
            token_aprobacion=info["token_aprobacion"], presupuesto_aprobado=info["presupuesto_aprobado"],
            presupuesto_rechazado=info["presupuesto_rechazado"]
        )

    return redirect("/ver_ordenes")


@app.post("/enviar_presupuesto")
def enviar_presupuesto_manual():
    if not session.get("login"):
        return redirect("/login")

    numero = request.form.get("numero", "").strip()
    con = db()
    cur = con.cursor()
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
    con.close()

    if not info:
        return html_layout("No encontrada", card_html("<h2 style='margin-top:0;'>Orden no encontrada</h2>"))
    if not info["email"]:
        return html_layout("Sin email", card_html(f"<h2 style='margin-top:0;'>El cliente no tiene email</h2><p><a href='/editar?numero={numero}'>Agregar email</a></p>"))
    if info["estado"] != "Esperando aprobación" or float(info["presupuesto"] or 0) <= 0:
        return html_layout("No disponible", card_html(f"<h2 style='margin-top:0;'>No se puede enviar el presupuesto</h2><p>La orden debe estar en <strong>Esperando aprobación</strong> y tener un importe mayor a 0.</p><p><a href='/actualizar?numero={numero}'>Volver</a></p>"))

    enviar_email(
        destino=info["email"], numero_orden=info["numero_orden"], cliente=info["nombre"],
        tipo=info["tipo_equipo"], marca=info["marca"], modelo=info["modelo"],
        estado=info["estado"], presupuesto=info["presupuesto"], tipo_mensaje="actualizacion",
        token_aprobacion=info["token_aprobacion"], presupuesto_aprobado=info["presupuesto_aprobado"],
        presupuesto_rechazado=info["presupuesto_rechazado"]
    )
    return redirect(f"/actualizar?numero={numero}")


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

@app.get("/clientes")
def clientes():
    if not session.get("login"):
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
                COALESCE(email, '') ILIKE %s OR
                COALESCE(cedula, '') ILIKE %s
            ORDER BY id DESC
        """, (like, like, like, like))
    else:
        cur.execute("SELECT * FROM clientes ORDER BY id DESC")

    clientes = cur.fetchall()
    con.close()

    html = f"""
    <h2 style="margin-top:0;">Clientes</h2>

    <form method="get" style="margin-bottom:18px;">
      <input name="q" value="{q}" placeholder="Buscar por nombre, teléfono, email o cédula"
        style="width:100%; max-width:420px; padding:10px; border:1px solid #d1d5db; border-radius:10px;">
      <button style="margin-left:8px; background:#2563eb; color:white; border:none; padding:11px 18px; border-radius:12px; font-weight:bold; cursor:pointer;">Buscar</button>
    </form>
    """

    html += tabla_estilo_inicio() + """
      <tr style="background:#eff6ff; text-align:left;">
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Nombre</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Teléfono</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Email</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Dirección</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for c in clientes:
        html += f"""
        <tr>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{c['nombre'] or '-'}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{c['telefono'] or '-'}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{c['email'] or '-'}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{c['direccion'] or '-'}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">
            <a href="/cliente/{c['id']}" style="color:#2563eb; font-weight:bold;">Ver ficha</a>
          </td>
        </tr>
        """

    html += tabla_estilo_fin()
    html += "<p style='margin-top:18px;'><a href='/' style='color:#2563eb; font-weight:bold;'>Volver</a></p>"

    return html_layout("Clientes", card_html(html))
@app.get("/cliente/<int:id>")
def ver_cliente(id):
    if not session.get("login"):
        return redirect("/login")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    cliente = cur.fetchone()

    if not cliente:
        con.close()
        return html_layout("No encontrado", card_html("<h2 style='margin-top:0;'>Cliente no encontrado</h2>"))

    cur.execute("""
        SELECT numero_orden, tipo_equipo, marca, modelo, estado, presupuesto
        FROM ordenes
        WHERE cliente_id=%s
        ORDER BY id DESC
    """, (id,))
    ordenes = cur.fetchall()
    con.close()

    html = f"""
    <h2 style="margin-top:0;">Ficha del cliente</h2>
    <p><strong>Nombre:</strong> {cliente['nombre'] or '-'}</p>
    <p><strong>Teléfono:</strong> {cliente['telefono'] or '-'}</p>
    <p><strong>Email:</strong> {cliente['email'] or '-'}</p>
    <p><strong>Dirección:</strong> {cliente['direccion'] or '-'}</p>
    <p><strong>Cédula:</strong> {cliente['cedula'] or '-'}</p>
    <p><strong>Notas:</strong> {cliente['notas'] or '-'}</p>

    <h3 style="margin-top:26px;">Historial de órdenes</h3>
    """

    html += tabla_estilo_inicio() + """
      <tr style="background:#eff6ff; text-align:left;">
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Número</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Equipo</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Estado</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Presupuesto</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for o in ordenes:
        equipo = f"{o['tipo_equipo'] or ''} {o['marca'] or ''} {o['modelo'] or ''}"
        pres = "En diagnóstico" if float(o["presupuesto"] or 0) == 0 else f"${o['presupuesto']}"
        html += f"""
        <tr>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{o['numero_orden']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{equipo}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{o['estado']}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">{pres}</td>
          <td style="padding:12px; border-bottom:1px solid #e5e7eb;">
            <a href="/actualizar?numero={o['numero_orden']}" style="color:#2563eb; font-weight:bold;">Ver / actualizar</a>
          </td>
        </tr>
        """

    html += tabla_estilo_fin()
    html += "<p style='margin-top:18px;'><a href='/clientes' style='color:#2563eb; font-weight:bold;'>Volver a clientes</a></p>"

    return html_layout("Ficha cliente", card_html(html))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)