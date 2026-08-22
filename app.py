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
from html import escape
from urllib.parse import quote
from io import BytesIO
from flask import send_file
import qrcode

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
    cur.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS acepta_promociones BOOLEAN DEFAULT FALSE;")

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
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS costo_repuestos NUMERIC DEFAULT 0;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS mano_obra NUMERIC DEFAULT 0;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS cobrado NUMERIC DEFAULT 0;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS forma_pago TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS token_publico TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS garantia_dias INTEGER DEFAULT 30;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_entregado DATE;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS comprobante_numero TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS fecha_comprobante TIMESTAMP;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS comprobante_forma_pago TEXT;")
    cur.execute("ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS comprobante_total NUMERIC;")


    cur.execute("""
    CREATE TABLE IF NOT EXISTS solicitudes_ingreso (
        id SERIAL PRIMARY KEY,
        token TEXT UNIQUE NOT NULL,
        estado TEXT DEFAULT 'Pendiente',
        nombre TEXT,
        telefono TEXT,
        email TEXT,
        cedula TEXT,
        tipo_equipo TEXT,
        marca TEXT,
        modelo TEXT,
        numero_serie TEXT,
        imei TEXT,
        falla_cliente TEXT,
        accesorios TEXT,
        bloqueo_tipo TEXT,
        clave_bloqueo TEXT,
        patron_bloqueo TEXT,
        acepta_terminos BOOLEAN DEFAULT FALSE,
        acepta_promociones BOOLEAN DEFAULT FALSE,
        fecha_creacion TIMESTAMP DEFAULT NOW(),
        fecha_envio TIMESTAMP,
        fecha_revision TIMESTAMP
    );
    """)

    # Configuración comercial/fiscal de NR Tech.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_empresa (
        id INTEGER PRIMARY KEY,
        nombre_comercial TEXT DEFAULT 'NR Tech',
        titular TEXT,
        rut TEXT,
        domicilio_fiscal TEXT,
        telefono TEXT,
        email TEXT,
        regimen TEXT DEFAULT 'MONOTRIBUTO'
    );
    """)
    cur.execute("""
        INSERT INTO configuracion_empresa (id, nombre_comercial, titular, rut, domicilio_fiscal, telefono, email, regimen)
        VALUES (1, 'NR Tech', 'RODRIGUEZ PEÑA NICOLAS GUSTAVO', '221029060015',
                'FLORES, AV. GRAL. 3249 301, MONTEVIDEO, CP 18000', '098705065',
                'info.nrsolucionestecno@gmail.com', 'MONOTRIBUTO')
        ON CONFLICT (id) DO NOTHING
    """)
    # Completa automáticamente los datos oficiales si la fila ya existía pero estaba vacía.
    cur.execute("""
        UPDATE configuracion_empresa SET
            nombre_comercial = COALESCE(NULLIF(nombre_comercial, ''), 'NR Tech'),
            titular = COALESCE(NULLIF(titular, ''), 'RODRIGUEZ PEÑA NICOLAS GUSTAVO'),
            rut = COALESCE(NULLIF(rut, ''), '221029060015'),
            domicilio_fiscal = COALESCE(NULLIF(domicilio_fiscal, ''), 'FLORES, AV. GRAL. 3249 301, MONTEVIDEO, CP 18000'),
            telefono = '098705065',
            email = COALESCE(NULLIF(email, ''), 'info.nrsolucionestecno@gmail.com'),
            regimen = 'MONOTRIBUTO'
        WHERE id = 1
    """)

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
        "Entregado": 0,
    }
    for fila in estados_raw:
        if fila["estado"] in resumen:
            resumen[fila["estado"]] = fila["total"]

    contenido = f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;">
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Recibidos</small><div style="font-size:27px;font-weight:800;">{resumen['Recibido en taller']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Diagnóstico</small><div style="font-size:27px;font-weight:800;">{resumen['En diagnóstico']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Esperando aprobación</small><div style="font-size:27px;font-weight:800;">{resumen['Esperando aprobación']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Esperando repuesto</small><div style="font-size:27px;font-weight:800;">{resumen['Esperando repuesto']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>En reparación</small><div style="font-size:27px;font-weight:800;">{resumen['En reparación']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Listos</small><div style="font-size:27px;font-weight:800;">{resumen['Listo para retirar']}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:16px;"><small>Entregados</small><div style="font-size:27px;font-weight:800;">{resumen['Entregado']}</div></div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;">
      <a href="/crear" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">➕ Crear orden</h3><p style="margin:0;color:#6b7280;">Registrar un nuevo equipo.</p></div></a>
      <a href="/buscar" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">🔎 Buscar orden</h3><p style="margin:0;color:#6b7280;">Buscar por cliente, IMEI o número.</p></div></a>
      <a href="/ver_ordenes" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📋 Ver órdenes</h3><p style="margin:0;color:#6b7280;">Gestionar reparaciones.</p></div></a>
      <a href="/clientes" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">👤 Clientes</h3><p style="margin:0;color:#6b7280;">Fichas e historial.</p></div></a>
      <a href="/solicitudes_ingreso" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #bbf7d0;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📲 Autoregistro cliente</h3><p style="margin:0;color:#6b7280;">Generar link/QR y revisar solicitudes.</p></div></a>
      <a href="/finanzas" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #bfdbfe;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">💰 Finanzas</h3><p style="margin:0;color:#6b7280;">Facturación, costos, ganancia y control de Monotributo.</p></div></a>
      <a href="/difusion" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #bbf7d0;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📢 Difusión WhatsApp</h3><p style="margin:0;color:#6b7280;">Clientes que aceptaron recibir promociones.</p></div></a>
      <a href="/configuracion_empresa" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">⚙️ Datos de NR Tech</h3><p style="margin:0;color:#6b7280;">Datos comerciales y fiscales del taller.</p></div></a>
      <a href="/logout" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">🚪 Salir</h3><p style="margin:0;color:#6b7280;">Cerrar sesión.</p></div></a>
    </div>
    """
    return html_layout("Inicio", contenido)


@app.get("/finanzas")
def finanzas():
    if not session.get("login"):
        return redirect("/login")

    hoy = datetime.date.today()
    try:
        anio = int(request.args.get("anio", hoy.year))
        mes = int(request.args.get("mes", hoy.month))
    except Exception:
        anio, mes = hoy.year, hoy.month
    if mes < 1 or mes > 12:
        mes = hoy.month

    tope_anual = float(os.environ.get("MONOTRIBUTO_TOPE_ANUAL", "1175537"))
    con = db(); cur = con.cursor()
    cur.execute("""
        SELECT
            COALESCE(SUM(presupuesto),0) AS facturado,
            COALESCE(SUM(cobrado),0) AS cobrado,
            COALESCE(SUM(costo_repuestos),0) AS costos,
            COALESCE(SUM(GREATEST(presupuesto-cobrado,0)),0) AS pendiente,
            COALESCE(SUM(presupuesto-costo_repuestos),0) AS margen,
            COUNT(*) AS trabajos
        FROM ordenes
        WHERE fecha_entregado IS NOT NULL
          AND EXTRACT(YEAR FROM fecha_entregado)=%s
          AND EXTRACT(MONTH FROM fecha_entregado)=%s
    """, (anio, mes))
    mes_data = cur.fetchone() or {}

    cur.execute("""
        SELECT COALESCE(SUM(presupuesto),0) AS facturado_anual
        FROM ordenes
        WHERE fecha_entregado IS NOT NULL
          AND EXTRACT(YEAR FROM fecha_entregado)=%s
    """, (anio,))
    anual = float((cur.fetchone() or {}).get("facturado_anual") or 0)

    cur.execute("""
        SELECT EXTRACT(MONTH FROM fecha_entregado)::int AS mes,
               COALESCE(SUM(presupuesto),0) AS facturado,
               COALESCE(SUM(costo_repuestos),0) AS costos,
               COALESCE(SUM(presupuesto-costo_repuestos),0) AS margen,
               COUNT(*) AS trabajos
        FROM ordenes
        WHERE fecha_entregado IS NOT NULL
          AND EXTRACT(YEAR FROM fecha_entregado)=%s
        GROUP BY 1 ORDER BY 1
    """, (anio,))
    por_mes = {r['mes']: r for r in cur.fetchall()}
    con.close()

    def dinero(v):
        try: return f"${float(v or 0):,.0f}".replace(",", ".")
        except Exception: return "$0"

    nombres = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Setiembre","Octubre","Noviembre","Diciembre"]
    restante = max(tope_anual-anual, 0)
    pct = min((anual/tope_anual*100) if tope_anual else 0, 100)
    opciones_mes = ''.join(f'<option value="{i}" {"selected" if i==mes else ""}>{nombres[i-1]}</option>' for i in range(1,13))
    opciones_anio = ''.join(f'<option value="{y}" {"selected" if y==anio else ""}>{y}</option>' for y in range(hoy.year-2,hoy.year+2))

    filas = ''
    for i in range(1,13):
        r = por_mes.get(i, {})
        filas += f"<tr><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{nombres[i-1]}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(r.get('facturado',0))}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(r.get('costos',0))}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(r.get('margen',0))}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{int(r.get('trabajos',0) or 0)}</td></tr>"

    contenido = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <div><h2 style="margin:0;">💰 Finanzas</h2><p style="margin:5px 0 0;color:#64748b;">Solo cuenta trabajos marcados como <strong>Entregados</strong>; los presupuestos pendientes no suman.</p></div>
      <a href="/" style="text-decoration:none;font-weight:bold;color:#2563eb;">🏠 Inicio</a>
    </div>
    <form method="get" style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:14px;margin-bottom:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:end;">
      <div><label>Mes</label><br><select name="mes" style="padding:9px;border:1px solid #d1d5db;border-radius:9px;">{opciones_mes}</select></div>
      <div><label>Año</label><br><select name="anio" style="padding:9px;border:1px solid #d1d5db;border-radius:9px;">{opciones_anio}</select></div>
      <button style="padding:10px 16px;border:0;border-radius:10px;background:#2563eb;color:white;font-weight:bold;">Ver período</button>
    </form>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:18px;">
      <div style="background:white;border:1px solid #bfdbfe;border-radius:14px;padding:15px;"><small>Facturación bruta</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('facturado'))}</div></div>
      <div style="background:white;border:1px solid #bbf7d0;border-radius:14px;padding:15px;"><small>Cobrado</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('cobrado'))}</div></div>
      <div style="background:white;border:1px solid #fed7aa;border-radius:14px;padding:15px;"><small>Costo repuestos</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('costos'))}</div></div>
      <div style="background:white;border:1px solid #fecaca;border-radius:14px;padding:15px;"><small>Pendiente de cobrar</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('pendiente'))}</div></div>
      <div style="background:white;border:1px solid #c7d2fe;border-radius:14px;padding:15px;"><small>Ganancia estimada</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('margen'))}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:14px;padding:15px;"><small>Trabajos entregados</small><div style="font-size:24px;font-weight:800;">{int(mes_data.get('trabajos') or 0)}</div></div>
    </div>

    <div style="background:white;border:1px solid #bfdbfe;border-radius:18px;padding:18px;margin-bottom:18px;">
      <h3 style="margin-top:0;">Control Monotributo {anio}</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;">
        <div><small>Facturado en el año</small><div style="font-size:24px;font-weight:800;">{dinero(anual)}</div></div>
        <div><small>Tope anual configurado</small><div style="font-size:24px;font-weight:800;">{dinero(tope_anual)}</div></div>
        <div><small>Margen disponible</small><div style="font-size:24px;font-weight:800;">{dinero(restante)}</div></div>
        <div><small>Utilizado</small><div style="font-size:24px;font-weight:800;">{pct:.1f}%</div></div>
      </div>
      <div style="height:14px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin-top:14px;"><div style="height:100%;width:{pct:.1f}%;background:#2563eb;"></div></div>
      <p style="font-size:12px;color:#64748b;margin-bottom:0;">El control usa la facturación bruta de trabajos entregados. El tope puede actualizarse cada año desde la configuración del servidor.</p>
    </div>

    <div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:18px;overflow-x:auto;">
      <h3 style="margin-top:0;">Resumen mes a mes — {anio}</h3>
      <table style="width:100%;border-collapse:collapse;min-width:620px;"><tr style="background:#eff6ff;text-align:left;"><th style="padding:10px">Mes</th><th style="padding:10px">Facturado</th><th style="padding:10px">Costos</th><th style="padding:10px">Ganancia est.</th><th style="padding:10px">Trabajos</th></tr>{filas}</table>
    </div>
    """
    return html_layout("Finanzas", contenido)


@app.route("/crear", methods=["GET", "POST"])
def crear():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        return html_layout(
            "Crear orden",
            card_html("""
            <h2 style="margin-top:0;">Crear orden</h2>
            <p style="color:#6b7280;margin-top:-6px;">Rápida para usar en el mostrador. Las opciones extra se despliegan solo cuando las necesitás.</p>
            <form method="post" id="formOrden">
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;">
                <div>
                  <h3 style="margin-top:0;">👤 Cliente</h3>
                  <label>Nombre</label><input name="nombre" required style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;">
                  <label>Teléfono</label><input name="telefono" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;">
                  <label>Email</label><input name="email" type="email" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;">
                  <details style="margin-top:8px;"><summary style="cursor:pointer;font-weight:700;color:#475569;">Más datos del cliente</summary>
                    <div style="padding-top:10px;"><label>Dirección</label><input name="direccion" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"><label>Cédula</label><input name="cedula" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"><label>Notas</label><input name="notas" style="width:100%;padding:10px;margin:6px 0;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"></div>
                  </details>
                </div>
                <div>
                  <h3 style="margin-top:0;">📱 Equipo</h3>
                  <label>Tipo</label><select name="tipo" style="width:100%;padding:10px;margin:6px 0 10px;border:1px solid #d1d5db;border-radius:10px;"><option>Celular</option><option>Tablet</option><option>Notebook</option><option>PC</option><option>Consola</option><option>Otro</option></select>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;"><div><label>Marca</label><input name="marca" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"></div><div><label>Modelo</label><input name="modelo" style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"></div></div>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;"><input name="imei" placeholder="IMEI" style="padding:10px;border:1px solid #d1d5db;border-radius:10px;"><input name="numero_serie" placeholder="N° serie" style="padding:10px;border:1px solid #d1d5db;border-radius:10px;"></div>
                  <label style="display:block;margin-top:10px;">Accesorios</label><input name="accesorios" placeholder="Funda, cargador, sin accesorios..." style="width:100%;padding:10px;margin:6px 0 10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;">
                  <label>Estado general</label><input name="estado_general" placeholder="Pantalla rota, marcas, etc." style="width:100%;padding:10px;margin:6px 0;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;">
                </div>
              </div>

              <div style="margin-top:18px;padding:16px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;">
                <h3 style="margin:0 0 10px;">⚡ Servicio</h3>
                <select name="servicio_rapido" id="servicioRapido" onchange="aplicarServicio()" style="width:100%;max-width:520px;padding:10px;border:1px solid #d1d5db;border-radius:10px;">
                  <option value="">Elegir plantilla...</option><option>Cambio de módulo / pantalla</option><option>Cambio de batería</option><option>Pin / conector de carga</option><option>No enciende</option><option>Software / sistema</option><option>Mantenimiento PC</option><option>Diagnóstico general</option><option>Otro</option>
                </select>
                <textarea name="falla_cliente" id="fallaCliente" rows="2" placeholder="Falla declarada por el cliente" style="width:100%;max-width:760px;padding:10px;margin-top:10px;box-sizing:border-box;border:1px solid #d1d5db;border-radius:10px;"></textarea>
              </div>

              <details style="margin-top:14px;padding:14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:14px;">
                <summary style="cursor:pointer;font-weight:800;">🔐 Acceso al equipo</summary>
                <div style="padding-top:12px;"><select name="bloqueo_tipo" id="bloqueoTipo" onchange="mostrarBloqueo()" style="padding:10px;border:1px solid #d1d5db;border-radius:10px;"><option>Sin bloqueo</option><option>PIN / clave</option><option>Patrón</option></select>
                <div id="bloqueoClave" style="display:none;margin-top:10px;"><input name="clave_bloqueo" autocomplete="off" placeholder="PIN / clave" style="padding:10px;border:1px solid #d1d5db;border-radius:10px;"></div>
                <div id="bloqueoPatron" style="display:none;margin-top:12px;"><input type="hidden" name="patron_bloqueo" id="patronBloqueo"><div id="patronGrid" style="display:grid;grid-template-columns:repeat(3,52px);gap:9px;width:max-content;">
                  <button type="button" onclick="puntoPatron(1,this)" class="punto">1</button><button type="button" onclick="puntoPatron(2,this)" class="punto">2</button><button type="button" onclick="puntoPatron(3,this)" class="punto">3</button><button type="button" onclick="puntoPatron(4,this)" class="punto">4</button><button type="button" onclick="puntoPatron(5,this)" class="punto">5</button><button type="button" onclick="puntoPatron(6,this)" class="punto">6</button><button type="button" onclick="puntoPatron(7,this)" class="punto">7</button><button type="button" onclick="puntoPatron(8,this)" class="punto">8</button><button type="button" onclick="puntoPatron(9,this)" class="punto">9</button>
                </div><div id="patronTexto" style="font-size:13px;color:#6b7280;margin:8px 0;">Patrón: -</div><button type="button" onclick="limpiarPatron()" style="border:0;padding:8px 11px;border-radius:8px;">Limpiar</button></div></div>
              </details>

              <details style="margin-top:14px;padding:14px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;"><summary style="cursor:pointer;font-weight:700;">📅 Entrega y comunicación</summary><div style="padding-top:10px;"><label>Fecha estimada</label><br><input type="date" name="fecha_entrega" style="padding:10px;margin:6px 0;border:1px solid #d1d5db;border-radius:10px;"><label style="display:flex;gap:8px;align-items:center;margin-top:10px;"><input type="checkbox" name="enviar_email_ingreso" value="1"> Enviar confirmación de ingreso por email</label></div></details>

              <div style="margin-top:18px;"><button type="submit" style="background:#2563eb;color:white;border:0;padding:13px 20px;border-radius:12px;font-weight:800;">Guardar orden</button><a href="/" style="margin-left:12px;color:#2563eb;font-weight:700;text-decoration:none;">Cancelar</a></div>
            </form>
            <style>.punto{width:52px;height:52px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:800;cursor:pointer}</style>
            <script>
              const plantillas={"Cambio de módulo / pantalla":"Cliente declara pantalla rota, sin imagen, con manchas, líneas, parpadeo o falla de táctil.","Cambio de batería":"Cliente declara poca duración de batería, apagados inesperados o batería degradada.","Pin / conector de carga":"Cliente declara que el equipo no carga, carga intermitente o presenta juego en el conector.","No enciende":"Cliente declara que el equipo no enciende o no da señales de funcionamiento.","Software / sistema":"Cliente solicita revisión de software, sistema operativo, lentitud, errores o configuración.","Mantenimiento PC":"Cliente solicita mantenimiento general, limpieza interna y control de temperaturas.","Diagnóstico general":"Cliente solicita diagnóstico técnico para determinar la falla del equipo."};
              function aplicarServicio(){const s=document.getElementById('servicioRapido').value,f=document.getElementById('fallaCliente');if(plantillas[s]&&!f.value.trim())f.value=plantillas[s];}
              let patron=[];
              function mostrarBloqueo(){const t=document.getElementById('bloqueoTipo').value;document.getElementById('bloqueoClave').style.display=t==='PIN / clave'?'block':'none';document.getElementById('bloqueoPatron').style.display=t==='Patrón'?'block':'none';}
              function puntoPatron(n,b){if(patron.includes(n))return;patron.push(n);b.style.background='#0ea5e9';b.style.color='white';document.getElementById('patronBloqueo').value=patron.join('-');document.getElementById('patronTexto').innerText='Patrón: '+patron.join(' → ');}
              function limpiarPatron(){patron=[];document.getElementById('patronBloqueo').value='';document.getElementById('patronTexto').innerText='Patrón: -';document.querySelectorAll('#patronGrid button').forEach(b=>{b.style.background='white';b.style.color='black';});}
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
            <a href="/actualizar?numero={r['numero_orden']}" style="color:#2563eb; font-weight:bold; margin-right:10px;">Actualizar</a>
            <a href="/etiqueta?numero={r['numero_orden']}" target="_blank" style="color:#7c3aed; font-weight:bold;">Etiqueta</a>
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
        ORDER BY CASE WHEN o.estado = 'Entregado' THEN 1 ELSE 0 END ASC, o.id DESC
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
            <a href="/actualizar?numero={o['numero_orden']}" style="color:#2563eb; font-weight:bold; margin-right:10px;">Actualizar</a>
            <a href="/etiqueta?numero={o['numero_orden']}" target="_blank" style="color:#7c3aed; font-weight:bold; margin-right:10px;">Etiqueta</a>
            <a href="/entrega?numero={o['numero_orden']}" style="color:#b45309; font-weight:bold;">Entrega</a>
            <a href="/comprobante?numero={o['numero_orden']}" style="color:#059669; font-weight:bold; margin-left:10px;">Comprobante</a> 
            <a href="/eliminar_orden?numero={o['numero_orden']}" style="color:#dc2626; font-weight:bold; margin-left:10px;">Eliminar</a>
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
        con = db(); cur = con.cursor()
        cur.execute("""SELECT o.*, c.nombre, c.telefono, c.email, c.direccion, c.cedula, c.notas FROM ordenes o JOIN clientes c ON o.cliente_id=c.id WHERE o.numero_orden=%s""", (numero,))
        x = cur.fetchone(); con.close()
        if not x:
            return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))

        def val(c):
            return escape(str(x[c] or ""))
        servicios=["", "Cambio de módulo / pantalla","Cambio de batería","Pin / conector de carga","No enciende","Software / sistema","Mantenimiento PC","Diagnóstico general","Otro"]
        servicio_opts="".join(f'<option value="{escape(s)}" {"selected" if str(x["servicio_rapido"] or "")==s else ""}>{escape(s or "Elegir plantilla...")}</option>' for s in servicios)
        bloqueos=["Sin bloqueo","PIN / clave","Patrón"]
        bloqueo_opts="".join(f'<option value="{b}" {"selected" if str(x["bloqueo_tipo"] or "Sin bloqueo")==b else ""}>{b}</option>' for b in bloqueos)
        formas=["","Efectivo","Transferencia","Débito","Crédito","Mixto"]
        forma_opts="".join(f'<option value="{f}" {"selected" if str(x["forma_pago"] or "")==f else ""}>{f or "Sin definir"}</option>' for f in formas)

        contenido=f"""
        <h2 style="margin-top:0;">Editar {val('numero_orden')}</h2>
        <p style="color:#6b7280;margin-top:-6px;">Todo editable, pero ordenado en bloques desplegables.</p>
        <form method="post"><input type="hidden" name="numero" value="{val('numero_orden')}">
          <details open style="padding:14px;border:1px solid #e5e7eb;border-radius:14px;margin-bottom:12px;"><summary style="cursor:pointer;font-weight:800;">👤 Cliente y equipo</summary>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;padding-top:12px;">
              <div><label>Nombre</label><input name="nombre" value="{val('nombre')}" style="width:100%;padding:9px;margin:5px 0;box-sizing:border-box;"><label>Teléfono</label><input name="telefono" value="{val('telefono')}" style="width:100%;padding:9px;margin:5px 0;box-sizing:border-box;"><label>Email</label><input name="email" value="{val('email')}" style="width:100%;padding:9px;margin:5px 0;box-sizing:border-box;"></div>
              <div><label>Tipo</label><input name="tipo" value="{val('tipo_equipo')}" style="width:100%;padding:9px;margin:5px 0;box-sizing:border-box;"><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;"><input name="marca" value="{val('marca')}" placeholder="Marca" style="padding:9px;"><input name="modelo" value="{val('modelo')}" placeholder="Modelo" style="padding:9px;"></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;"><input name="imei" value="{val('imei')}" placeholder="IMEI" style="padding:9px;"><input name="numero_serie" value="{val('numero_serie')}" placeholder="Serie" style="padding:9px;"></div></div>
            </div>
          </details>

          <details open style="padding:14px;border:1px solid #e5e7eb;border-radius:14px;margin-bottom:12px;"><summary style="cursor:pointer;font-weight:800;">⚡ Servicio y estado</summary><div style="padding-top:12px;">
            <select name="servicio_rapido" id="servicioRapido" onchange="aplicarServicio()" style="padding:9px;max-width:420px;width:100%;">{servicio_opts}</select>
            <textarea name="falla_cliente" id="fallaCliente" rows="2" style="display:block;width:100%;max-width:760px;padding:9px;margin-top:8px;box-sizing:border-box;">{val('falla_cliente')}</textarea>
            <input name="estado_general" value="{val('estado_general')}" placeholder="Estado general" style="width:100%;max-width:520px;padding:9px;margin-top:8px;box-sizing:border-box;">
            <input name="accesorios" value="{val('accesorios')}" placeholder="Accesorios" style="width:100%;max-width:520px;padding:9px;margin-top:8px;box-sizing:border-box;">
          </div></details>

          <details style="padding:14px;background:#fff7ed;border:1px solid #fed7aa;border-radius:14px;margin-bottom:12px;"><summary style="cursor:pointer;font-weight:800;">🔐 Acceso al equipo</summary><div style="padding-top:12px;">
            <select name="bloqueo_tipo" id="bloqueoTipo" onchange="mostrarBloqueo()" style="padding:9px;">{bloqueo_opts}</select>
            <div id="bloqueoClave" style="display:none;margin-top:8px;"><input name="clave_bloqueo" value="{val('clave_bloqueo')}" autocomplete="off" placeholder="PIN / clave" style="padding:9px;"></div>
            <div id="bloqueoPatron" style="display:none;margin-top:10px;"><input type="hidden" name="patron_bloqueo" id="patronBloqueo" value="{val('patron_bloqueo')}"><div id="patronGrid" style="display:grid;grid-template-columns:repeat(3,50px);gap:8px;width:max-content;">{''.join(f'<button type="button" onclick="puntoPatron({n},this)" class="punto" data-n="{n}">{n}</button>' for n in range(1,10))}</div><div id="patronTexto" style="font-size:13px;color:#6b7280;margin:8px 0;"></div><button type="button" onclick="limpiarPatron()">Limpiar</button></div>
          </div></details>

          <details style="padding:14px;border:1px solid #e5e7eb;border-radius:14px;margin-bottom:12px;"><summary style="cursor:pointer;font-weight:800;">📝 Datos adicionales</summary><div style="padding-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;"><input name="direccion" value="{val('direccion')}" placeholder="Dirección" style="padding:9px;"><input name="cedula" value="{val('cedula')}" placeholder="Cédula" style="padding:9px;"><input name="notas" value="{val('notas')}" placeholder="Notas cliente" style="padding:9px;"><input type="date" name="fecha_entrega" value="{val('fecha_entrega')}" style="padding:9px;"></div><textarea name="observaciones" rows="2" placeholder="Observaciones" style="width:100%;max-width:760px;padding:9px;margin-top:10px;box-sizing:border-box;">{val('observaciones')}</textarea></details>

          <details style="padding:14px;background:#f8fafc;border:1px solid #dbeafe;border-radius:14px;margin-bottom:14px;"><summary style="cursor:pointer;font-weight:800;">💰 Finanzas de la orden</summary><div style="padding-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;max-width:850px;">
            <div><small>Presupuesto</small><div style="font-weight:800;font-size:20px;">${val('presupuesto')}</div></div>
            <div><label>Costo repuestos</label><input id="finCosto" name="costo_repuestos" type="number" min="0" step="0.01" value="{val('costo_repuestos')}" oninput="calcularFinanzas()" style="width:100%;padding:9px;box-sizing:border-box;"></div>
            <div><label>Mano de obra</label><input name="mano_obra" type="number" min="0" step="0.01" value="{val('mano_obra')}" style="width:100%;padding:9px;box-sizing:border-box;"></div>
            <div><label>Cobrado / seña</label><input id="finCobrado" name="cobrado" type="number" min="0" step="0.01" value="{val('cobrado')}" oninput="calcularFinanzas()" style="width:100%;padding:9px;box-sizing:border-box;"></div>
            <div><label>Forma pago</label><select name="forma_pago" style="width:100%;padding:9px;">{forma_opts}</select></div>
          </div><input id="finPrecio" type="hidden" value="{val('presupuesto')}"><div style="margin-top:10px;"><strong>Saldo:</strong> <span id="finSaldo"></span> &nbsp; | &nbsp; <strong>Margen:</strong> <span id="finMargen"></span></div></details>

          <button type="submit" style="background:#0f766e;color:white;border:0;padding:12px 18px;border-radius:11px;font-weight:800;">Guardar correcciones</button>
          <a href="/actualizar?numero={val('numero_orden')}" style="margin-left:10px;color:#2563eb;font-weight:700;text-decoration:none;">Actualizar reparación</a>
        </form>
        <div style="display:flex;gap:9px;flex-wrap:wrap;margin-top:16px;"><a href="/etiqueta?numero={val('numero_orden')}" target="_blank" style="background:#7c3aed;color:white;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:700;">🖨️ Etiquetas</a><a href="/ver_ordenes" style="background:#111827;color:white;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:700;">📋 Órdenes</a><a href="/" style="background:#e5e7eb;color:#111;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:700;">🏠 Inicio</a></div>
        <style>.punto{{width:50px;height:50px;border-radius:50%;border:2px solid #0ea5e9;background:white;font-weight:800;cursor:pointer}}</style>
        <script>
          const plantillas={{"Cambio de módulo / pantalla":"Cliente declara pantalla rota, sin imagen, con manchas, líneas, parpadeo o falla de táctil.","Cambio de batería":"Cliente declara poca duración de batería, apagados inesperados o batería degradada.","Pin / conector de carga":"Cliente declara que el equipo no carga, carga intermitente o presenta juego en el conector.","No enciende":"Cliente declara que el equipo no enciende o no da señales de funcionamiento.","Software / sistema":"Cliente solicita revisión de software, sistema operativo, lentitud, errores o configuración.","Mantenimiento PC":"Cliente solicita mantenimiento general, limpieza interna y control de temperaturas.","Diagnóstico general":"Cliente solicita diagnóstico técnico para determinar la falla del equipo."}};
          function aplicarServicio(){{const s=document.getElementById('servicioRapido').value,f=document.getElementById('fallaCliente');if(plantillas[s]&&!f.value.trim())f.value=plantillas[s];}}
          let patron=(document.getElementById('patronBloqueo').value||'').split('-').map(Number).filter(Boolean);
          function pintarPatron(){{document.querySelectorAll('#patronGrid button').forEach(b=>{{const n=Number(b.dataset.n);b.style.background=patron.includes(n)?'#0ea5e9':'white';b.style.color=patron.includes(n)?'white':'black';}});document.getElementById('patronTexto').innerText='Patrón: '+(patron.length?patron.join(' → '):'-');}}
          function mostrarBloqueo(){{const tp=document.getElementById('bloqueoTipo').value;document.getElementById('bloqueoClave').style.display=tp==='PIN / clave'?'block':'none';document.getElementById('bloqueoPatron').style.display=tp==='Patrón'?'block':'none';}}
          function puntoPatron(n,b){{if(patron.includes(n))return;patron.push(n);document.getElementById('patronBloqueo').value=patron.join('-');pintarPatron();}}
          function limpiarPatron(){{patron=[];document.getElementById('patronBloqueo').value='';pintarPatron();}}
          function calcularFinanzas(){{const p=parseFloat(document.getElementById('finPrecio').value||0),c=parseFloat(document.getElementById('finCosto').value||0),co=parseFloat(document.getElementById('finCobrado').value||0);document.getElementById('finSaldo').innerText='$'+Math.max(p-co,0).toLocaleString('es-UY');document.getElementById('finMargen').innerText='$'+(p-c).toLocaleString('es-UY');}}
          mostrarBloqueo();pintarPatron();calcularFinanzas();
        </script>
        """
        return html_layout("Editar orden", card_html(contenido))

    numero=request.form.get("numero","").strip(); con=db(); cur=con.cursor(); cur.execute("SELECT cliente_id FROM ordenes WHERE numero_orden=%s",(numero,)); orden=cur.fetchone()
    if not orden:
        con.close(); return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))
    cliente_id=orden["cliente_id"]
    cur.execute("""UPDATE clientes SET nombre=%s,telefono=%s,email=%s,direccion=%s,cedula=%s,notas=%s WHERE id=%s""",(request.form.get("nombre","").strip(),request.form.get("telefono","").strip(),request.form.get("email","").strip(),request.form.get("direccion","").strip(),request.form.get("cedula","").strip(),request.form.get("notas","").strip(),cliente_id))
    cur.execute("""UPDATE ordenes SET tipo_equipo=%s,marca=%s,modelo=%s,numero_serie=%s,imei=%s,estado_general=%s,accesorios=%s,servicio_rapido=%s,fecha_entrega=%s,bloqueo_tipo=%s,clave_bloqueo=%s,patron_bloqueo=%s,costo_repuestos=%s,mano_obra=%s,cobrado=%s,forma_pago=%s,falla_cliente=%s,observaciones=%s WHERE numero_orden=%s""",(request.form.get("tipo","").strip(),request.form.get("marca","").strip(),request.form.get("modelo","").strip(),request.form.get("numero_serie","").strip(),request.form.get("imei","").strip(),request.form.get("estado_general","").strip(),request.form.get("accesorios","").strip(),request.form.get("servicio_rapido","").strip(),request.form.get("fecha_entrega","").strip() or None,request.form.get("bloqueo_tipo","").strip(),request.form.get("clave_bloqueo","").strip(),request.form.get("patron_bloqueo","").strip(),request.form.get("costo_repuestos","0").strip() or 0,request.form.get("mano_obra","0").strip() or 0,request.form.get("cobrado","0").strip() or 0,request.form.get("forma_pago","").strip(),request.form.get("falla_cliente","").strip(),request.form.get("observaciones","").strip(),numero))
    con.commit(); con.close(); return redirect("/ver_ordenes")


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
    <p><a href="/eliminar_cliente?id={id}" style="display:inline-block;background:#fee2e2;color:#b91c1c;padding:9px 13px;border-radius:9px;text-decoration:none;font-weight:bold;">🗑️ Eliminar cliente</a></p>

    <h3 style="margin-top:24px;">📢 Comunicaciones</h3>
    <form method="post" action="/cliente/{id}/promociones" style="background:#f8fafc;padding:12px;border-radius:10px;margin-bottom:18px;">
      <label><input type="checkbox" name="acepta_promociones" value="1" {"checked" if cliente.get("acepta_promociones") else ""}> Cliente acepta recibir novedades/promociones por WhatsApp</label>
      <button style="margin-left:10px;padding:7px 12px;border:0;border-radius:8px;background:#2563eb;color:white;font-weight:bold">Guardar</button>
    </form>

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




@app.route("/eliminar_orden", methods=["GET", "POST"])
def eliminar_orden():
    if not session.get("login"):
        return redirect("/login")
    numero=request.args.get("numero","").strip() if request.method=="GET" else request.form.get("numero","").strip()
    con=db(); cur=con.cursor()
    cur.execute("""SELECT o.numero_orden,o.tipo_equipo,o.marca,o.modelo,c.nombre
                   FROM ordenes o JOIN clientes c ON o.cliente_id=c.id
                   WHERE o.numero_orden=%s""",(numero,))
    x=cur.fetchone()
    if not x:
        con.close()
        return html_layout("No encontrada",card_html("<h2>Orden no encontrada</h2>"))
    if request.method=="POST":
        confirmar=request.form.get("confirmar","")
        if confirmar=="ELIMINAR":
            cur.execute("DELETE FROM ordenes WHERE numero_orden=%s",(numero,))
            con.commit(); con.close()
            return redirect("/ver_ordenes")
        con.close()
        return html_layout("Confirmación",card_html("<h2>No se eliminó la orden</h2><p>Debés escribir ELIMINAR exactamente.</p>"))
    con.close()
    equipo=" ".join([str(x.get("tipo_equipo") or ""),str(x.get("marca") or ""),str(x.get("modelo") or "")]).strip()
    return html_layout("Eliminar orden",card_html(f"""
      <h2 style='color:#b91c1c;margin-top:0'>🗑️ Eliminar orden</h2>
      <p>Vas a eliminar permanentemente:</p>
      <div style='background:#fef2f2;border:1px solid #fecaca;padding:14px;border-radius:12px'>
        <b>{escape(str(x['numero_orden']))}</b><br>
        Cliente: {escape(str(x.get('nombre') or '-'))}<br>
        Equipo: {escape(equipo)}
      </div>
      <p><b>Esto también deja de contar esta orden en los cálculos del sistema.</b></p>
      <form method='post'>
        <input type='hidden' name='numero' value='{escape(numero)}'>
        <label>Escribí <b>ELIMINAR</b> para confirmar:</label>
        <input name='confirmar' autocomplete='off' style='width:100%;max-width:300px;padding:10px;margin:8px 0;border:1px solid #d1d5db;border-radius:9px'>
        <br><button style='background:#dc2626;color:white;border:0;padding:11px 16px;border-radius:10px;font-weight:bold'>Eliminar definitivamente</button>
        <a href='/ver_ordenes' style='margin-left:10px'>Cancelar</a>
      </form>
    """))


@app.route("/eliminar_cliente", methods=["GET","POST"])
def eliminar_cliente():
    if not session.get("login"):
        return redirect("/login")
    try:
        cid=int(request.args.get("id") if request.method=="GET" else request.form.get("id"))
    except Exception:
        return redirect("/clientes")
    con=db(); cur=con.cursor()
    cur.execute("SELECT * FROM clientes WHERE id=%s",(cid,))
    c=cur.fetchone()
    if not c:
        con.close(); return html_layout("No encontrado",card_html("<h2>Cliente no encontrado</h2>"))
    cur.execute("SELECT COUNT(*) AS total FROM ordenes WHERE cliente_id=%s",(cid,))
    total=int(cur.fetchone()["total"] or 0)
    if request.method=="POST":
        if request.form.get("confirmar")!="ELIMINAR":
            con.close()
            return html_layout("Confirmación",card_html("<h2>No se eliminó el cliente</h2><p>Debés escribir ELIMINAR exactamente.</p>"))
        # Explicitly delete their orders first so test clients can be cleaned safely.
        cur.execute("DELETE FROM ordenes WHERE cliente_id=%s",(cid,))
        cur.execute("DELETE FROM clientes WHERE id=%s",(cid,))
        con.commit(); con.close()
        return redirect("/clientes")
    con.close()
    return html_layout("Eliminar cliente",card_html(f"""
      <h2 style='color:#b91c1c;margin-top:0'>🗑️ Eliminar cliente</h2>
      <p>Cliente: <b>{escape(str(c.get('nombre') or '-'))}</b></p>
      <div style='background:#fef2f2;border:1px solid #fecaca;padding:14px;border-radius:12px'>
        Este cliente tiene <b>{total} orden(es)</b>. Si continuás, <b>también se eliminarán todas sus órdenes</b>.
        Al borrarlas dejarán de intervenir en costos, ingresos y ganancias.
      </div>
      <form method='post' style='margin-top:16px'>
        <input type='hidden' name='id' value='{cid}'>
        <label>Escribí <b>ELIMINAR</b> para confirmar:</label>
        <input name='confirmar' autocomplete='off' style='width:100%;max-width:300px;padding:10px;margin:8px 0;border:1px solid #d1d5db;border-radius:9px'>
        <br><button style='background:#dc2626;color:white;border:0;padding:11px 16px;border-radius:10px;font-weight:bold'>Eliminar cliente y sus órdenes</button>
        <a href='/cliente/{cid}' style='margin-left:10px'>Cancelar</a>
      </form>
    """))


@app.route("/difusion", methods=["GET", "POST"])
def difusion():
    if not session.get("login"):
        return redirect("/login")

    q = request.args.get("q", "").strip()
    con = db(); cur = con.cursor()
    sql = """
      SELECT id,nombre,telefono,email,fecha_alta
      FROM clientes
      WHERE COALESCE(acepta_promociones,FALSE)=TRUE
        AND COALESCE(telefono,'') <> ''
    """
    params=[]
    if q:
        sql += " AND (COALESCE(nombre,'') ILIKE %s OR COALESCE(telefono,'') ILIKE %s)"
        like=f"%{q}%"; params=[like,like]
    sql += " ORDER BY nombre ASC"
    cur.execute(sql, tuple(params))
    filas=cur.fetchall(); con.close()

    mensaje = request.form.get("mensaje","").strip() if request.method=="POST" else ""
    cards=""
    for c in filas:
        tel="".join(ch for ch in str(c.get("telefono") or "") if ch.isdigit())
        if tel.startswith("0"): tel="598"+tel[1:]
        elif not tel.startswith("598"): tel="598"+tel
        link=""
        if mensaje:
            link="https://wa.me/"+tel+"?text="+quote(mensaje)
        cards += f"""
        <tr>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(c.get('nombre') or '-'))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(c.get('telefono') or '-'))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>
            {f'<a target="_blank" href="{link}" style="color:#16a34a;font-weight:bold">Abrir WhatsApp</a>' if mensaje else 'Escribí el mensaje arriba'}
          </td>
        </tr>"""

    contenido=f"""
      <h2 style='margin-top:0'>📢 Difusión WhatsApp</h2>
      <p style='color:#64748b'>Solo aparecen clientes que aceptaron recibir promociones.</p>
      <div style='background:#f0fdf4;padding:12px;border-radius:10px;margin-bottom:16px'>
        <strong>{len(filas)} contactos habilitados</strong>
      </div>
      <form method='post'>
        <label><strong>Mensaje de campaña</strong></label>
        <textarea name='mensaje' rows='5' placeholder='Ej: Hola 👋 En NR Tech tenemos...' style='width:100%;padding:11px;margin-top:6px;border:1px solid #d1d5db;border-radius:10px'>{escape(mensaje)}</textarea>
        <button style='margin-top:10px;background:#16a34a;color:white;border:0;padding:11px 16px;border-radius:10px;font-weight:bold'>Preparar WhatsApp</button>
      </form>
      <div style='overflow-x:auto;margin-top:18px'>
      <table style='width:100%;border-collapse:collapse'>
        <tr style='background:#eff6ff;text-align:left'><th style='padding:10px'>Cliente</th><th style='padding:10px'>WhatsApp</th><th style='padding:10px'></th></tr>
        {cards or "<tr><td colspan='3' style='padding:18px;text-align:center;color:#64748b'>Todavía no hay clientes habilitados para difusión.</td></tr>"}
      </table></div>
      <p style='font-size:12px;color:#64748b;margin-top:16px'>Esta versión prepara el mensaje individualmente y abre WhatsApp para que vos confirmes el envío. No realiza envíos masivos automáticos.</p>
      <p><a href='/'>🏠 Inicio</a></p>
    """
    return html_layout("Difusión WhatsApp", card_html(contenido))


@app.post("/cliente/<int:id>/promociones")
def cambiar_promociones(id):
    if not session.get("login"):
        return redirect("/login")
    valor = request.form.get("acepta_promociones") == "1"
    con=db(); cur=con.cursor()
    cur.execute("UPDATE clientes SET acepta_promociones=%s WHERE id=%s",(valor,id))
    con.commit(); con.close()
    return redirect(f"/cliente/{id}")


def _config_empresa():
    con = db(); cur = con.cursor()
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1")
    cfg = cur.fetchone(); con.close()
    return cfg or {}


@app.route("/configuracion_empresa", methods=["GET", "POST"])
def configuracion_empresa():
    if not session.get("login"):
        return redirect("/login")
    if request.method == "POST":
        campos = ["nombre_comercial", "titular", "rut", "domicilio_fiscal", "telefono", "email"]
        vals = [request.form.get(c, "").strip() for c in campos]
        con = db(); cur = con.cursor()
        cur.execute("""UPDATE configuracion_empresa SET nombre_comercial=%s,titular=%s,rut=%s,domicilio_fiscal=%s,telefono=%s,email=%s,regimen='MONOTRIBUTO' WHERE id=1""", vals)
        con.commit(); con.close()
        return redirect("/configuracion_empresa?guardado=1")
    cfg = _config_empresa(); guardado = request.args.get("guardado") == "1"
    def v(k): return escape(str(cfg.get(k) or ""))
    contenido = f"""
      <h2 style='margin-top:0'>⚙️ Datos de NR Tech</h2>
      <p style='color:#64748b'>Datos comerciales y fiscales utilizados en los comprobantes y respaldos de NR Tech.</p>
      {"<div style='background:#f0fdf4;padding:12px;border-radius:10px;margin-bottom:12px'>✅ Datos guardados.</div>" if guardado else ""}
      <form method='post'>
        <label><b>Nombre comercial</b></label><input name='nombre_comercial' value='{v("nombre_comercial")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <label><b>Titular / razón social</b></label><input name='titular' value='{v("titular")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <label><b>RUT</b></label><input name='rut' value='{v("rut")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <label><b>Domicilio fiscal</b></label><input name='domicilio_fiscal' value='{v("domicilio_fiscal")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <label><b>Teléfono</b></label><input name='telefono' value='{v("telefono")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <label><b>Email</b></label><input name='email' value='{v("email")}' style='width:100%;padding:10px;margin:5px 0 12px'>
        <div style='background:#eff6ff;padding:12px;border-radius:10px;margin:8px 0 16px'><b>Régimen:</b> MONOTRIBUTO</div>
        <button style='background:#2563eb;color:white;border:0;padding:12px 18px;border-radius:10px;font-weight:800'>Guardar datos</button>
      </form><p><a href='/'>← Volver al inicio</a></p>
    """
    return html_layout("Datos de NR Tech", card_html(contenido))


def _asegurar_token_y_comprobante(cur, orden):
    token = orden.get("token_publico") if hasattr(orden, "get") else orden["token_publico"]
    comprobante = orden.get("comprobante_numero") if hasattr(orden, "get") else orden["comprobante_numero"]
    if not token:
        token = secrets.token_urlsafe(24)
        cur.execute("UPDATE ordenes SET token_publico=%s WHERE numero_orden=%s", (token, orden["numero_orden"]))
    if not comprobante:
        cur.execute("SELECT COUNT(*) AS total FROM ordenes WHERE comprobante_numero IS NOT NULL")
        n = int(cur.fetchone()["total"] or 0) + 1
        comprobante = f"NR-COMP-{datetime.datetime.now().year}-{n:05d}"
        cur.execute("UPDATE ordenes SET comprobante_numero=%s, fecha_comprobante=NOW() WHERE numero_orden=%s", (comprobante, orden["numero_orden"]))
    return token, comprobante


def _buscar_entrega_por_numero(numero):
    con = db(); cur = con.cursor()
    cur.execute("""
        SELECT o.*, c.nombre, c.telefono, c.email
        FROM ordenes o JOIN clientes c ON o.cliente_id=c.id
        WHERE o.numero_orden=%s
    """, (numero,))
    x = cur.fetchone(); con.close(); return x


@app.route("/comprobante", methods=["GET", "POST"])
def comprobante():
    if not session.get("login"):
        return redirect("/login")
    numero = request.values.get("numero", "").strip()
    if not numero:
        return redirect("/ver_ordenes")
    con = db(); cur = con.cursor()
    cur.execute("""SELECT o.*, c.nombre, c.telefono, c.email FROM ordenes o JOIN clientes c ON c.id=o.cliente_id WHERE o.numero_orden=%s""", (numero,))
    o = cur.fetchone()
    if not o:
        con.close(); return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1")
    emp = cur.fetchone()
    if request.method == "POST":
        forma = request.form.get("forma_pago", "").strip()
        try: total = float(request.form.get("total", "0").replace(",", "."))
        except: total = float(o['presupuesto'] or 0)
        token, comp = _asegurar_token_y_comprobante(cur, o)
        cur.execute("UPDATE ordenes SET comprobante_forma_pago=%s, comprobante_total=%s, forma_pago=COALESCE(NULLIF(%s,''),forma_pago) WHERE numero_orden=%s", (forma,total,forma,numero))
        con.commit(); con.close()
        return redirect(f"/imprimir_comprobante?numero={quote(numero)}")
    total = o['comprobante_total'] if o.get('comprobante_total') is not None else (o['presupuesto'] or 0)
    forma = o.get('comprobante_forma_pago') or o.get('forma_pago') or ''
    con.close()
    html=f"""
      <h2 style='margin-top:0'>🧾 Generar comprobante</h2>
      <p><b>Orden:</b> {escape(numero)} · <b>Cliente:</b> {escape(o['nombre'] or '-')}</p>
      <p><b>Equipo:</b> {escape(' '.join(filter(None,[o['tipo_equipo'],o['marca'],o['modelo']])) or '-')}</p>
      <form method='post'>
        <input type='hidden' name='numero' value='{escape(numero)}'>
        <label><b>Total cobrado / venta</b></label><br>
        <input name='total' value='{total}' inputmode='decimal' style='padding:10px;width:220px;margin:6px 0 14px;border:1px solid #d1d5db;border-radius:10px'><br>
        <label><b>Forma de pago</b></label><br>
        <select name='forma_pago' style='padding:10px;width:240px;margin:6px 0 16px;border:1px solid #d1d5db;border-radius:10px'>
          {''.join(f"<option value='{x}' {'selected' if forma==x else ''}>{x}</option>" for x in ['Efectivo','Transferencia','Mercado Pago','Débito','Crédito','Otro'])}
        </select><br>
        <button style='background:#059669;color:white;border:0;padding:12px 18px;border-radius:10px;font-weight:800;cursor:pointer'>Generar e imprimir</button>
        <a href='/ver_ordenes' style='margin-left:12px'>Cancelar</a>
      </form>
      <p style='font-size:12px;color:#64748b;margin-top:18px'>Documento interno de la operación. La identificación fiscal usa los datos configurados de NR Tech.</p>
    """
    return html_layout("Comprobante", card_html(html))

@app.get("/imprimir_comprobante")
def imprimir_comprobante():
    if not session.get("login"):
        return redirect("/login")
    numero=request.args.get("numero","").strip()
    con=db(); cur=con.cursor()
    cur.execute("""SELECT o.*,c.nombre,c.telefono,c.email FROM ordenes o JOIN clientes c ON c.id=o.cliente_id WHERE o.numero_orden=%s""",(numero,))
    o=cur.fetchone()
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1"); emp=cur.fetchone()
    if not o:
        con.close(); return "Orden no encontrada",404
    token, comp=_asegurar_token_y_comprobante(cur,o); con.commit(); con.close()
    total=o.get('comprobante_total') if o.get('comprobante_total') is not None else (o['presupuesto'] or 0)
    forma=o.get('comprobante_forma_pago') or o.get('forma_pago') or '-'
    trabajo=o.get('diagnostico_tecnico') or o.get('falla_cliente') or 'Servicio técnico'
    fecha=o.get('fecha_comprobante') or datetime.datetime.now()
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(comp)}</title><style>@page{{size:A4;margin:16mm}}body{{font-family:Arial;color:#111;max-width:760px;margin:auto}}.head{{border-bottom:3px solid #111;padding-bottom:12px}}.box{{border:1px solid #ddd;border-radius:12px;padding:18px;margin-top:16px}}.r{{margin:7px 0}}button{{padding:10px 16px}}@media print{{button{{display:none}}}}</style></head><body>
      <div class='head'><h1 style='margin:0'>{escape((emp or {}).get('nombre_comercial') or 'NR Tech')}</h1><b>MONOTRIBUTO</b><div>{escape((emp or {}).get('titular') or '')}</div><div>RUT: {escape((emp or {}).get('rut') or '-')}</div><div>{escape((emp or {}).get('domicilio_fiscal') or '')}</div><div>Tel. {escape((emp or {}).get('telefono') or '')} · {escape((emp or {}).get('email') or '')}</div></div>
      <div class='box'><h2 style='margin-top:0'>Comprobante de operación</h2><div class='r'><b>N.º:</b> {escape(comp)}</div><div class='r'><b>Fecha:</b> {fecha.strftime('%d/%m/%Y') if hasattr(fecha,'strftime') else escape(str(fecha))}</div><div class='r'><b>Orden:</b> {escape(numero)}</div><hr><div class='r'><b>Cliente:</b> {escape(o['nombre'] or '-')}</div><div class='r'><b>Equipo:</b> {escape(' '.join(filter(None,[o['tipo_equipo'],o['marca'],o['modelo']])) or '-')}</div><div class='r'><b>Trabajo:</b> {escape(trabajo)}</div><div class='r'><b>Forma de pago:</b> {escape(str(forma))}</div><div class='r' style='font-size:22px'><b>Total: $ {float(total or 0):,.2f}</b></div>
      {f"<hr><div class='r'><b>Garantía:</b> {int(o.get('garantia_dias') or 30)} días</div><div class='r'><img src='/qr/{token}.png' style='width:120px;height:120px' alt='QR'><br><small>Escaneá para ver comprobante y garantía.</small></div>" if o.get('fecha_entregado') else ''}</div>
      <p style='font-size:12px;color:#666'>Respaldo generado por el sistema de gestión NR Tech.</p><button onclick='window.print()'>🖨️ Imprimir</button></body></html>"""

@app.route("/entrega", methods=["GET", "POST"])
def entrega():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        garantia_dias = int(request.form.get("garantia_dias", "30") or 30)
        accion = request.form.get("accion", "guardar")
        con = db(); cur = con.cursor()
        cur.execute("""
            SELECT o.*, c.nombre, c.telefono, c.email
            FROM ordenes o JOIN clientes c ON o.cliente_id=c.id
            WHERE o.numero_orden=%s
        """, (numero,))
        orden = cur.fetchone()
        if not orden:
            con.close(); return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))
        token, comprobante = _asegurar_token_y_comprobante(cur, orden)
        # Si todavía no se generó el comprobante V1, usamos el presupuesto como total inicial.
        # Luego puede editarse desde el botón Comprobante sin perder la entrega/garantía.
        cur.execute("""
            UPDATE ordenes
            SET garantia_dias=%s,
                fecha_entregado=COALESCE(fecha_entregado, CURRENT_DATE),
                estado='Entregado',
                comprobante_total=COALESCE(comprobante_total, presupuesto),
                comprobante_forma_pago=COALESCE(NULLIF(comprobante_forma_pago,''), forma_pago)
            WHERE numero_orden=%s
        """, (garantia_dias, numero))
        con.commit(); con.close()
        url_publica = f"{BASE_URL or request.url_root.rstrip('/')}/documento/{token}"

        if accion == "email":
            orden2 = _buscar_entrega_por_numero(numero)
            if not orden2 or not orden2["email"]:
                return html_layout("Sin email", card_html(f"<h2>El cliente no tiene email</h2><p><a href='/entrega?numero={numero}'>Volver</a></p>"))
            msg = EmailMessage()
            msg["Subject"] = f"Comprobante y garantía {numero} – NR Tech"
            msg["From"] = formataddr(("NR Tech – Tecnología en buenas manos", REMITENTE_EMAIL))
            msg["To"] = orden2["email"]
            msg.set_content(f"Hola {orden2['nombre']}.\n\nTu reparación {numero} fue entregada.\nComprobante: {comprobante}\nGarantía: {garantia_dias} días.\nVer comprobante, QR y garantía: {url_publica}\n\nNR Tech")
            msg.add_alternative(f"""
              <div style='font-family:Arial,sans-serif;max-width:640px;margin:auto'>
                <h2>NR Tech</h2><p>Hola <strong>{escape(orden2['nombre'] or '')}</strong>.</p>
                <p>Tu reparación <strong>{numero}</strong> fue marcada como entregada.</p>
                <p><strong>Comprobante:</strong> {comprobante}<br><strong>Garantía:</strong> {garantia_dias} días</p>
                <p><a href='{url_publica}' style='display:inline-block;background:#2563eb;color:white;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:bold'>Ver comprobante y garantía</a></p>
              </div>
            """, subtype="html")
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as smtp:
                    smtp.login(REMITENTE_EMAIL, CONTRASENA_APP); smtp.send_message(msg)
            except Exception as e:
                print("Error envío entrega:", e)
            return redirect(f"/entrega?numero={numero}&enviado=1")

        if accion == "imprimir":
            return redirect(f"/imprimir_entrega?numero={numero}")
        if accion == "whatsapp":
            orden2 = _buscar_entrega_por_numero(numero)
            tel = ''.join(ch for ch in str(orden2['telefono'] or '') if ch.isdigit())
            if tel and not tel.startswith('598'):
                tel = '598' + tel.lstrip('0')
            texto = f"Hola {orden2['nombre']}, tu equipo ya fue entregado por NR Tech. Orden {numero}. Comprobante {comprobante}. Garantía: {garantia_dias} días. Podés ver tu comprobante, QR y garantía acá: {url_publica}"
            destino = f"https://wa.me/{tel}?text={quote(texto)}" if tel else f"https://wa.me/?text={quote(texto)}"
            return redirect(destino)
        return redirect(f"/entrega?numero={numero}")

    numero = request.args.get("numero", "").strip()
    if not numero:
        return redirect("/ver_ordenes")
    x = _buscar_entrega_por_numero(numero)
    if not x:
        return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))
    garantia = int(x["garantia_dias"] or 30)
    enviado = request.args.get("enviado") == "1"
    total_entrega = float((x.get('comprobante_total') if x.get('comprobante_total') is not None else x['presupuesto']) or 0)
    comp_actual = x.get('comprobante_numero') or 'Todavía no generado'
    forma_actual = x.get('comprobante_forma_pago') or x.get('forma_pago') or '-'
    contenido = f"""
      <h2 style='margin-top:0'>📦 Entrega de {escape(numero)}</h2>
      <p style='color:#64748b'>Cerrá la reparación y elegí cómo darle el respaldo al cliente.</p>
      {"<div style='background:#f0fdf4;border:1px solid #bbf7d0;padding:12px;border-radius:10px;margin-bottom:14px'>✅ Email enviado.</div>" if enviado else ""}
      <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:18px'>
        <div style='background:#f8fafc;padding:13px;border-radius:12px'><small>Cliente</small><div style='font-weight:800'>{escape(x['nombre'] or '-')}</div></div>
        <div style='background:#f8fafc;padding:13px;border-radius:12px'><small>Equipo</small><div style='font-weight:800'>{escape((x['tipo_equipo'] or '')+' '+(x['marca'] or '')+' '+(x['modelo'] or ''))}</div></div>
        <div style='background:#f8fafc;padding:13px;border-radius:12px'><small>Total</small><div style='font-weight:800'>${total_entrega:,.0f}</div></div>
        <div style='background:#f8fafc;padding:13px;border-radius:12px'><small>Comprobante</small><div style='font-weight:800'>{escape(str(comp_actual))}</div><small>{escape(str(forma_actual))}</small></div>
      </div>
      <div style='display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px'>
        <a href='/comprobante?numero={quote(numero)}' style='background:#059669;color:white;padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:800'>🧾 Revisar / generar comprobante</a>
        {f"<a href='/documento/{x['token_publico']}' target='_blank' style='background:#7c3aed;color:white;padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:800'>🔗 Ver comprobante + garantía</a>" if x.get('token_publico') else ''}
      </div>
      <form method='post'>
        <input type='hidden' name='numero' value='{escape(numero)}'>
        <label><strong>Garantía</strong></label><br>
        <select name='garantia_dias' style='padding:10px;width:100%;max-width:280px;margin:6px 0 18px;border:1px solid #cbd5e1;border-radius:10px'>
          <option value='30' {'selected' if garantia==30 else ''}>30 días</option>
          <option value='90' {'selected' if garantia==90 else ''}>90 días</option>
          <option value='180' {'selected' if garantia==180 else ''}>180 días</option>
          <option value='365' {'selected' if garantia==365 else ''}>1 año</option>
        </select>
        <div style='display:flex;flex-wrap:wrap;gap:10px'>
          <button name='accion' value='whatsapp' style='background:#16a34a;color:white;border:0;padding:12px 16px;border-radius:10px;font-weight:800;cursor:pointer'>💬 WhatsApp</button>
          <button name='accion' value='email' {'disabled' if not x['email'] else ''} style='background:#2563eb;color:white;border:0;padding:12px 16px;border-radius:10px;font-weight:800;cursor:pointer'>📧 Email</button>
          <button name='accion' value='imprimir' style='background:#111827;color:white;border:0;padding:12px 16px;border-radius:10px;font-weight:800;cursor:pointer'>🖨️ Imprimir</button>
          <button name='accion' value='guardar' style='background:#e5e7eb;color:#111827;border:0;padding:12px 16px;border-radius:10px;font-weight:800;cursor:pointer'>Guardar entrega</button>
        </div>
      </form>
      <p style='margin-top:18px'><a href='/ver_ordenes'>← Volver a órdenes</a></p>
    """
    return html_layout("Entrega", card_html(contenido))


@app.get("/documento/<token>")
def documento_publico(token):
    con = db(); cur = con.cursor()
    cur.execute("""
      SELECT o.numero_orden,o.tipo_equipo,o.marca,o.modelo,o.diagnostico_tecnico,o.presupuesto,
             o.garantia_dias,o.fecha_entregado,o.comprobante_numero,o.forma_pago,
             o.comprobante_total,o.comprobante_forma_pago,c.nombre
      FROM ordenes o JOIN clientes c ON o.cliente_id=c.id
      WHERE o.token_publico=%s
    """, (token,))
    x = cur.fetchone(); con.close()
    if not x:
        return html_layout("No encontrado", card_html("<h2>Comprobante no encontrado</h2>"))
    cfg = _config_empresa()
    fecha = x['fecha_entregado'] or datetime.date.today()
    vence = fecha + datetime.timedelta(days=int(x['garantia_dias'] or 30))
    vigente = datetime.date.today() <= vence
    estado_g = "Vigente" if vigente else "Vencida"
    contenido = f"""
      <div style='text-align:center'><h2 style='margin-bottom:4px'>{escape(str(cfg.get('nombre_comercial') or 'NR Tech'))}</h2><div style='color:#64748b'>Tecnología en buenas manos</div></div>
      <div style='border:2px solid #111827;padding:8px;text-align:center;font-weight:900;margin:14px 0'>MONOTRIBUTO</div>
      <p><strong>RUT:</strong> {escape(str(cfg.get('rut') or 'Pendiente de configurar'))}</p>
      <hr style='border:0;border-top:1px solid #e5e7eb;margin:18px 0'>
      <p><strong>Comprobante:</strong> {escape(x['comprobante_numero'] or 'Pendiente')}</p>
      <p><strong>Orden:</strong> {escape(x['numero_orden'])}</p>
      <p><strong>Cliente:</strong> {escape(x['nombre'] or '-')}</p>
      <p><strong>Equipo:</strong> {escape((x['tipo_equipo'] or '')+' '+(x['marca'] or '')+' '+(x['modelo'] or ''))}</p>
      <p><strong>Trabajo:</strong> {escape(x['diagnostico_tecnico'] or 'Reparación / servicio técnico')}</p>
      <p><strong>Importe:</strong> ${float((x.get('comprobante_total') if x.get('comprobante_total') is not None else x['presupuesto']) or 0):,.0f}</p>
      <p><strong>Forma de pago:</strong> {escape(str(x.get('comprobante_forma_pago') or x.get('forma_pago') or '-'))}</p>
      <div style='background:{'#f0fdf4' if vigente else '#fef2f2'};padding:14px;border-radius:12px;margin-top:16px'>
        <strong>Garantía: {estado_g}</strong><br>Desde {fecha.strftime('%d/%m/%Y')} hasta {vence.strftime('%d/%m/%Y')} ({int(x['garantia_dias'] or 30)} días)
      </div>
      <hr style='border:0;border-top:1px solid #e5e7eb;margin:22px 0'>
      <div style='display:grid;grid-template-columns:1fr 180px;gap:22px;align-items:start'>
        <div>
          <h3 style='margin-top:0'>🛡️ Garantía del trabajo</h3>
          <p>Este trabajo cuenta con garantía sobre el servicio realizado.</p>
          <p><strong>Inicio:</strong> {fecha.strftime('%d/%m/%Y')}<br>
          <strong>Vencimiento:</strong> {vence.strftime('%d/%m/%Y')}<br>
          <strong>Duración:</strong> {int(x['garantia_dias'] or 30)} días</p>
          <p><strong>Cubre:</strong> exclusivamente fallas relacionadas directamente con el trabajo y/o repuestos detallados en este comprobante durante el plazo indicado.</p>
          <p><strong>No cubre:</strong> golpes, caídas, humedad o líquidos, mal uso, daños físicos, sobrecargas eléctricas, daños provocados por terceros, manipulación posterior ni fallas ajenas a la reparación realizada.</p>
          <div style='background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:10px;margin-top:12px'>
            <strong>🔒 Sello interno de garantía NR Tech</strong><br>
            Los equipos reparados podrán llevar un sello interno de garantía. La rotura, remoción o alteración del sello podrá invalidar la garantía cuando evidencie que el equipo fue abierto o manipulado por terceros durante el período de cobertura.
          </div>
          <p style='font-size:13px;color:#475569'><strong>Solicitud de garantía:</strong> se deberá presentar este comprobante o identificar la orden correspondiente. NR Tech realizará una revisión técnica previa para determinar si la falla está comprendida dentro de la garantía.</p>
        </div>
        <div style='text-align:center'>
          <img src='/qr/{token}.png' alt='QR de garantía' style='width:150px;height:150px;max-width:100%'>
          <div style='font-weight:800;margin-top:6px'>Orden {escape(x['numero_orden'])}</div>
          <div style='font-size:12px;color:#64748b;margin-top:5px'>Escaneá para verificar este comprobante y su garantía.</div>
        </div>
      </div>
      <div style='background:#eff6ff;padding:12px;border-radius:10px;margin-top:18px;font-size:14px'>
        <strong>Contacto NR Tech:</strong> {escape(str(cfg.get('telefono') or '-'))} · {escape(str(cfg.get('email') or '-'))}
      </div>
      <p style='font-size:12px;color:#64748b;margin-top:18px'>Documento de respaldo de la orden, pago y garantía de NR Tech.</p>
    """
    return html_layout("Comprobante y garantía", card_html(contenido))


@app.get("/qr/<token>.png")
def qr_documento(token):
    url = f"{BASE_URL or request.url_root.rstrip('/')}/documento/{token}"
    img = qrcode.make(url)
    bio = BytesIO(); img.save(bio, format="PNG"); bio.seek(0)
    return send_file(bio, mimetype="image/png")


@app.get("/imprimir_entrega")
def imprimir_entrega():
    if not session.get("login"):
        return redirect("/login")
    numero = request.args.get("numero", "").strip()
    con = db(); cur = con.cursor()
    cur.execute("""SELECT o.*, c.nombre FROM ordenes o JOIN clientes c ON o.cliente_id=c.id WHERE o.numero_orden=%s""", (numero,))
    x = cur.fetchone()
    if not x:
        con.close(); return "Orden no encontrada", 404
    token, comprobante = _asegurar_token_y_comprobante(cur, x); con.commit(); con.close()
    cfg = _config_empresa()
    fecha = x['fecha_entregado'] or datetime.date.today(); garantia=int(x['garantia_dias'] or 30); vence=fecha+datetime.timedelta(days=garantia)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{comprobante}</title><style>@page{{size:A4;margin:16mm}}body{{font-family:Arial;color:#111;max-width:760px;margin:auto}}.box{{border:1px solid #ddd;border-radius:12px;padding:18px}}.row{{margin:8px 0}}img{{width:150px;height:150px}}@media print{{button{{display:none}}}}</style></head><body>
      <div class='box'><h1 style='margin:0'>{escape(str(cfg.get('nombre_comercial') or 'NR Tech'))}</h1><div>Tecnología en buenas manos</div>
      <div style='border:2px solid #111;padding:7px;text-align:center;font-weight:bold;margin:12px 0'>MONOTRIBUTO</div>
      <div class='row'><b>RUT:</b> {escape(str(cfg.get('rut') or 'Pendiente de configurar'))}</div><hr>
      <div class='row'><b>Comprobante:</b> {comprobante}</div><div class='row'><b>Orden:</b> {escape(numero)}</div>
      <div class='row'><b>Cliente:</b> {escape(x['nombre'] or '-')}</div><div class='row'><b>Equipo:</b> {escape((x['tipo_equipo'] or '')+' '+(x['marca'] or '')+' '+(x['modelo'] or ''))}</div>
      <div class='row'><b>Trabajo:</b> {escape(x['diagnostico_tecnico'] or 'Reparación / servicio técnico')}</div><div class='row'><b>Importe:</b> ${float((x.get('comprobante_total') if x.get('comprobante_total') is not None else x['presupuesto']) or 0):,.0f}</div>
      <div class='row'><b>Forma de pago:</b> {escape(str(x.get('comprobante_forma_pago') or x.get('forma_pago') or '-'))}</div>
      <div class='row' style='font-size:16px;background:#f0fdf4;padding:10px;border-radius:8px'><b>Garantía:</b> {garantia} días — válida hasta {vence.strftime('%d/%m/%Y')} — Orden {escape(numero)}</div>
      <div style='display:grid;grid-template-columns:1fr 165px;gap:18px;align-items:start;margin-top:16px'>
        <div>
          <h3 style='margin:0 0 8px'>Condiciones de garantía – NR Tech</h3>
          <div style='font-size:12px;line-height:1.45'>
            La garantía cubre exclusivamente la reparación y/o repuestos detallados en este comprobante durante el plazo indicado. No cubre golpes, caídas, humedad o líquidos, sobrecargas eléctricas, mal uso, daños físicos, daños provocados por terceros, manipulación posterior ni fallas ajenas al trabajo realizado.
            <br><br><b>Sello interno de garantía:</b> los equipos reparados podrán llevar un sello interno NR Tech. La rotura, remoción o alteración del sello podrá invalidar la garantía cuando evidencie que el equipo fue abierto o manipulado por terceros durante el período de cobertura.
            <br><br>Para solicitar garantía se deberá presentar este comprobante o identificar la orden correspondiente. NR Tech realizará una revisión técnica previa para determinar si la falla está comprendida dentro de la garantía.
          </div>
        </div>
        <div style='text-align:center'><img src='/qr/{token}.png' alt='QR'><div style='font-size:11px;color:#666'>Escaneá para consultar y verificar comprobante y garantía.</div></div>
      </div>
      <div style='margin-top:14px;padding-top:10px;border-top:1px solid #ddd;font-size:12px'><b>Contacto NR Tech:</b> {escape(str(cfg.get('telefono') or '-'))} · {escape(str(cfg.get('email') or '-'))}</div>
      <p style='font-size:11px;color:#666'>Documento de respaldo de la orden, pago y garantía de NR Tech.</p></div>
      <button onclick='window.print()' style='margin-top:16px;padding:12px 18px'>Imprimir</button><script>setTimeout(()=>window.print(),500)</script></body></html>"""




@app.get("/etiqueta")
def etiqueta():
    if not session.get("login"):
        return redirect("/login")

    numero = request.args.get("numero", "").strip()
    if not numero:
        return redirect("/ver_ordenes")

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.numero_orden, o.tipo_equipo, o.marca, o.modelo, o.imei, o.numero_serie,
               o.accesorios, c.nombre
        FROM ordenes o
        JOIN clientes c ON o.cliente_id = c.id
        WHERE o.numero_orden = %s
    """, (numero,))
    x = cur.fetchone()
    con.close()

    if not x:
        return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))

    equipo = " ".join([
        str(x.get("tipo_equipo") or ""),
        str(x.get("marca") or ""),
        str(x.get("modelo") or "")
    ]).strip() or "Equipo"

    identificador = ""
    if x.get("imei"):
        identificador = f"IMEI: {escape(str(x['imei']))}"
    elif x.get("numero_serie"):
        identificador = f"Serie: {escape(str(x['numero_serie']))}"

    accesorios = str(x.get("accesorios") or "").strip()

    etiqueta_accesorios = ""
    if accesorios:
        etiqueta_accesorios = f"""
        <div class="etiqueta">
          <div class="marca">NR Tech</div>
          <div class="tipo">ACCESORIOS</div>
          <div class="orden">{escape(str(x['numero_orden']))}</div>
          <div class="cliente">{escape(str(x.get('nombre') or '-'))}</div>
          <div class="dato">{escape(accesorios)}</div>
        </div>
        """

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Etiquetas {escape(str(x['numero_orden']))}</title>
<style>
  @page {{ margin: 6mm; }}
  body {{ font-family: Arial, sans-serif; margin: 0; padding: 12px; color:#111827; }}
  .acciones {{ margin-bottom: 14px; }}
  .etiquetas {{ display:flex; flex-wrap:wrap; gap:12px; }}
  .etiqueta {{
    width: 72mm;
    min-height: 38mm;
    border: 2px solid #111827;
    border-radius: 8px;
    padding: 8px;
    box-sizing: border-box;
    page-break-inside: avoid;
  }}
  .marca {{ font-size: 16px; font-weight: 900; }}
  .tipo {{ font-size: 11px; font-weight: 800; margin-top: 3px; }}
  .orden {{ font-size: 18px; font-weight: 900; margin: 6px 0; }}
  .cliente {{ font-size: 13px; font-weight: 700; }}
  .dato {{ font-size: 12px; margin-top: 5px; line-height:1.3; }}
  @media print {{
    .acciones {{ display:none; }}
    body {{ padding:0; }}
  }}
</style>
</head>
<body>
  <div class="acciones">
    <button onclick="window.print()" style="padding:10px 16px;border:0;border-radius:10px;background:#2563eb;color:white;font-weight:bold;cursor:pointer;">🖨️ Imprimir etiquetas</button>
  </div>

  <div class="etiquetas">
    <div class="etiqueta">
      <div class="marca">NR Tech</div>
      <div class="tipo">EQUIPO</div>
      <div class="orden">{escape(str(x['numero_orden']))}</div>
      <div class="cliente">{escape(str(x.get('nombre') or '-'))}</div>
      <div class="dato">{escape(equipo)}</div>
      {f'<div class="dato">{identificador}</div>' if identificador else ''}
    </div>
    {etiqueta_accesorios}
  </div>
</body>
</html>"""


@app.route("/solicitudes_ingreso", methods=["GET", "POST"])
def solicitudes_ingreso():
    if not session.get("login"):
        return redirect("/login")

    con = db(); cur = con.cursor()

    if request.method == "POST":
        token = secrets.token_urlsafe(24)
        cur.execute("INSERT INTO solicitudes_ingreso(token) VALUES(%s) RETURNING id", (token,))
        sid = cur.fetchone()["id"]
        con.commit(); con.close()
        base = BASE_URL or request.url_root.rstrip("/")
        link = f"{base}/autoregistro/{token}"
        whatsapp = "https://wa.me/?text=" + quote(
            "Hola, te envío el formulario de ingreso de NR Tech para completar los datos de tu equipo:\n" + link
        )
        return html_layout("Link creado", card_html(f"""
          <h2 style='margin-top:0'>Solicitud creada</h2>
          <p><strong>ID:</strong> {sid}</p>
          <label>Link para el cliente</label>
          <input value="{escape(link)}" readonly onclick="this.select()" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px">
            <a href="{whatsapp}" target="_blank" style="background:#16a34a;color:white;padding:11px 16px;border-radius:10px;text-decoration:none;font-weight:bold">📲 Enviar por WhatsApp</a>
            <a href="/qr_autoregistro/{token}.png" target="_blank" style="background:#7c3aed;color:white;padding:11px 16px;border-radius:10px;text-decoration:none;font-weight:bold">QR</a>
            <a href="/solicitudes_ingreso" style="background:#e5e7eb;color:#111827;padding:11px 16px;border-radius:10px;text-decoration:none;font-weight:bold">Volver</a>
          </div>
        """))

    cur.execute("""
      SELECT id, token, estado, nombre, telefono, tipo_equipo, marca, modelo, fecha_creacion
      FROM solicitudes_ingreso
      ORDER BY CASE WHEN estado='Pendiente' THEN 0 ELSE 1 END, id DESC
    """)
    filas = cur.fetchall(); con.close()

    html = """
      <h2 style="margin-top:0">Autoregistro de clientes</h2>
      <p style="color:#6b7280">Generá un link para que el cliente complete sus datos desde el celular.</p>
      <form method="post"><button style="background:#2563eb;color:white;border:0;padding:12px 18px;border-radius:12px;font-weight:bold;cursor:pointer">➕ Crear solicitud</button></form>
      <div style="overflow-x:auto;margin-top:18px"><table style="width:100%;border-collapse:collapse;background:white">
        <tr style="background:#eff6ff;text-align:left">
          <th style="padding:10px">ID</th><th style="padding:10px">Cliente</th><th style="padding:10px">Equipo</th><th style="padding:10px">Estado</th><th style="padding:10px"></th>
        </tr>
    """
    for f in filas:
        equipo = " ".join([str(f.get("tipo_equipo") or ""), str(f.get("marca") or ""), str(f.get("modelo") or "")]).strip() or "-"
        html += f"""
          <tr>
            <td style="padding:10px;border-bottom:1px solid #e5e7eb">{f['id']}</td>
            <td style="padding:10px;border-bottom:1px solid #e5e7eb">{escape(str(f.get('nombre') or 'Pendiente de completar'))}</td>
            <td style="padding:10px;border-bottom:1px solid #e5e7eb">{escape(equipo)}</td>
            <td style="padding:10px;border-bottom:1px solid #e5e7eb">{escape(str(f['estado']))}</td>
            <td style="padding:10px;border-bottom:1px solid #e5e7eb"><a href="/revisar_solicitud/{f['id']}" style="font-weight:bold;color:#2563eb">Revisar</a></td>
          </tr>
        """
    html += "</table></div><p style='margin-top:18px'><a href='/'>🏠 Inicio</a></p>"
    return html_layout("Autoregistro", card_html(html))


@app.route("/autoregistro/<token>", methods=["GET", "POST"])
def autoregistro_cliente(token):
    con = db(); cur = con.cursor()
    cur.execute("SELECT * FROM solicitudes_ingreso WHERE token=%s", (token,))
    s = cur.fetchone()
    if not s:
        con.close()
        return html_layout("No disponible", card_html("<h2>Link inválido o vencido</h2>"))

    if request.method == "POST":
        acepta = request.form.get("acepta_terminos") == "1"
        if not acepta:
            con.close()
            return html_layout("Falta aceptar", card_html(f"<h2>Falta aceptar las condiciones</h2><p><a href='/autoregistro/{token}'>Volver</a></p>"))
        cur.execute("""
          UPDATE solicitudes_ingreso SET
            estado='Completada', nombre=%s, telefono=%s, email=%s, cedula=%s,
            tipo_equipo=%s, marca=%s, modelo=%s, numero_serie=%s, imei=%s,
            falla_cliente=%s, accesorios=%s, bloqueo_tipo=%s, clave_bloqueo=%s,
            patron_bloqueo=%s, acepta_terminos=%s, acepta_promociones=%s, fecha_envio=NOW()
          WHERE token=%s
        """, (
          request.form.get("nombre","").strip(), request.form.get("telefono","").strip(),
          request.form.get("email","").strip(), request.form.get("cedula","").strip(),
          request.form.get("tipo_equipo","").strip(), request.form.get("marca","").strip(),
          request.form.get("modelo","").strip(), request.form.get("numero_serie","").strip(),
          request.form.get("imei","").strip(), request.form.get("falla_cliente","").strip(),
          request.form.get("accesorios","").strip(), request.form.get("bloqueo_tipo","Sin bloqueo").strip(),
          request.form.get("clave_bloqueo","").strip(), request.form.get("patron_bloqueo","").strip(),
          True, request.form.get("acepta_promociones") == "1", token
        ))
        con.commit(); con.close()
        return html_layout("Datos enviados", card_html("""
          <div style='text-align:center'>
            <h2>✅ Datos enviados</h2>
            <p>NR Tech recibió tu información. El técnico la revisará antes de registrar el ingreso definitivo del equipo.</p>
          </div>
        """))

    con.close()
    return html_layout("Ingreso NR Tech", card_html(f"""
      <div style="text-align:center"><h2 style="margin-bottom:4px">NR Tech</h2><p style="color:#64748b;margin-top:0">Ingreso de equipo al taller</p></div>
      <form method="post">
        <h3>👤 Tus datos</h3>
        <label>Nombre y apellido *</label><input name="nombre" required style="width:100%;padding:10px;margin:5px 0 12px;border:1px solid #d1d5db;border-radius:10px">
        <label>Teléfono / WhatsApp *</label><input name="telefono" required style="width:100%;padding:10px;margin:5px 0 12px;border:1px solid #d1d5db;border-radius:10px">
        <label>Email (opcional)</label><input type="email" name="email" style="width:100%;padding:10px;margin:5px 0 12px;border:1px solid #d1d5db;border-radius:10px">
        <label>Cédula (opcional)</label><input name="cedula" style="width:100%;padding:10px;margin:5px 0 18px;border:1px solid #d1d5db;border-radius:10px">

        <h3>📱 Equipo</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
          <input name="tipo_equipo" placeholder="Tipo: celular, notebook..." style="padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <input name="marca" placeholder="Marca" style="padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <input name="modelo" placeholder="Modelo" style="padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <input name="numero_serie" placeholder="N° de serie" style="padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <input name="imei" placeholder="IMEI (si aplica)" style="padding:10px;border:1px solid #d1d5db;border-radius:10px">
        </div>
        <label style="display:block;margin-top:12px">Falla / motivo de ingreso *</label>
        <textarea name="falla_cliente" required rows="4" style="width:100%;padding:10px;margin-top:5px;border:1px solid #d1d5db;border-radius:10px"></textarea>
        <label style="display:block;margin-top:12px">Accesorios entregados</label>
        <input name="accesorios" placeholder="Ej: cargador, funda, SIM..." style="width:100%;padding:10px;margin-top:5px;border:1px solid #d1d5db;border-radius:10px">

        <details style="margin-top:16px;padding:12px;border:1px solid #e5e7eb;border-radius:12px">
          <summary style="cursor:pointer;font-weight:bold">🔐 Desbloqueo del equipo (solo si es necesario)</summary>
          <label style="display:block;margin-top:12px">Tipo</label>
          <select name="bloqueo_tipo" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px">
            <option>Sin bloqueo</option><option>PIN / clave</option><option>Patrón</option>
          </select>
          <label style="display:block;margin-top:10px">PIN / clave</label>
          <input name="clave_bloqueo" autocomplete="off" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px">
          <label style="display:block;margin-top:10px">Patrón (ej: 1-2-5-8)</label>
          <input name="patron_bloqueo" autocomplete="off" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:10px">
        </details>

        <label style="display:flex;gap:10px;align-items:flex-start;margin-top:18px;padding:12px;background:#f8fafc;border-radius:10px">
          <input type="checkbox" name="acepta_terminos" value="1" required style="margin-top:3px">
          <span>Acepto que NR Tech reciba el equipo para diagnóstico/reparación y que estos datos se utilicen para gestionar esta orden.</span>
        </label>
        <label style="display:flex;gap:10px;align-items:flex-start;margin-top:10px;padding:12px;background:#f0fdf4;border-radius:10px">
          <input type="checkbox" name="acepta_promociones" value="1" style="margin-top:3px">
          <span>Acepto recibir novedades y promociones de NR Tech por WhatsApp. <strong>Opcional.</strong></span>
        </label>
        <button style="margin-top:16px;background:#2563eb;color:white;border:0;padding:13px 20px;border-radius:12px;font-weight:bold">Enviar datos</button>
      </form>
    """))


@app.get("/qr_autoregistro/<token>.png")
def qr_autoregistro(token):
    url = f"{BASE_URL or request.url_root.rstrip('/')}/autoregistro/{token}"
    img = qrcode.make(url)
    bio = BytesIO(); img.save(bio, format="PNG"); bio.seek(0)
    return send_file(bio, mimetype="image/png")


@app.route("/revisar_solicitud/<int:sid>", methods=["GET", "POST"])
def revisar_solicitud(sid):
    if not session.get("login"):
        return redirect("/login")
    con = db(); cur = con.cursor()
    cur.execute("SELECT * FROM solicitudes_ingreso WHERE id=%s", (sid,))
    s = cur.fetchone()
    if not s:
        con.close()
        return html_layout("No encontrada", card_html("<h2>Solicitud no encontrada</h2>"))

    if request.method == "POST":
        telefono = str(s.get("telefono") or "").strip()
        email = str(s.get("email") or "").strip()
        cliente_id = None
        if telefono:
            cur.execute("SELECT id FROM clientes WHERE telefono=%s LIMIT 1", (telefono,))
            r=cur.fetchone(); cliente_id = r["id"] if r else None
        if not cliente_id and email:
            cur.execute("SELECT id FROM clientes WHERE email=%s LIMIT 1", (email,))
            r=cur.fetchone(); cliente_id = r["id"] if r else None
        if cliente_id:
            cur.execute("""UPDATE clientes SET nombre=%s,telefono=%s,email=%s,cedula=%s,acepta_promociones=%s WHERE id=%s""",
                        (s.get("nombre"), telefono, email, s.get("cedula"), bool(s.get("acepta_promociones")), cliente_id))
        else:
            cur.execute("""INSERT INTO clientes(nombre,telefono,email,cedula,acepta_promociones) VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                        (s.get("nombre"), telefono, email, s.get("cedula"), bool(s.get("acepta_promociones"))))
            cliente_id=cur.fetchone()["id"]

        token_aprobacion = secrets.token_urlsafe(32)
        cur.execute("""
          INSERT INTO ordenes(numero_orden,cliente_id,tipo_equipo,marca,modelo,numero_serie,imei,
          estado_general,falla_cliente,diagnostico_tecnico,fecha_ingreso,estado,presupuesto,observaciones,
          token_aprobacion,presupuesto_aprobado,presupuesto_rechazado,accesorios,bloqueo_tipo,clave_bloqueo,patron_bloqueo)
          VALUES('',%s,%s,%s,%s,%s,%s,'',%s,'',CURRENT_DATE,'Recibido en taller',0,'',%s,FALSE,FALSE,%s,%s,%s,%s)
          RETURNING id
        """, (cliente_id,s.get("tipo_equipo"),s.get("marca"),s.get("modelo"),s.get("numero_serie"),
              s.get("imei"),s.get("falla_cliente"),token_aprobacion,s.get("accesorios"),
              s.get("bloqueo_tipo"),s.get("clave_bloqueo"),s.get("patron_bloqueo")))
        oid=cur.fetchone()["id"]
        numero=f"NR-{datetime.datetime.now().year}-{oid:04d}"
        cur.execute("UPDATE ordenes SET numero_orden=%s WHERE id=%s",(numero,oid))
        cur.execute("UPDATE solicitudes_ingreso SET estado='Convertida', fecha_revision=NOW() WHERE id=%s",(sid,))
        con.commit(); con.close()
        return redirect(f"/buscar?q={numero}")

    con.close()
    def v(k): return escape(str(s.get(k) or "-"))
    promo = "Sí" if s.get("acepta_promociones") else "No"
    return html_layout("Revisar solicitud", card_html(f"""
      <h2 style="margin-top:0">Revisar solicitud #{sid}</h2>
      <p><strong>Estado:</strong> {v('estado')}</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px">
        <div><b>Cliente</b><br>{v('nombre')}<br>{v('telefono')}<br>{v('email')}<br>CI: {v('cedula')}</div>
        <div><b>Equipo</b><br>{v('tipo_equipo')} {v('marca')} {v('modelo')}<br>Serie: {v('numero_serie')}<br>IMEI: {v('imei')}</div>
      </div>
      <p><b>Falla:</b><br>{v('falla_cliente')}</p>
      <p><b>Accesorios:</b> {v('accesorios')}</p>
      <p><b>Bloqueo:</b> {v('bloqueo_tipo')} | Clave: {v('clave_bloqueo')} | Patrón: {v('patron_bloqueo')}</p>
      <p><b>Acepta promociones:</b> {promo}</p>
      {"<form method='post'><button style='background:#16a34a;color:white;border:0;padding:12px 18px;border-radius:12px;font-weight:bold'>✅ Confirmar y crear orden</button></form>" if s.get("estado")=="Completada" else ""}
      <p style="margin-top:16px"><a href="/solicitudes_ingreso">Volver</a></p>
    """))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)