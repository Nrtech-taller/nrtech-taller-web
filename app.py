from flask import Flask, request, redirect, session, flash, get_flashed_messages
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


def estado_presupuesto_badge(estado, aprobado=False, rechazado=False, fecha_aprobacion=None, fecha_rechazo=None):
    if aprobado:
        fecha = f"<br><small>{fecha_aprobacion.strftime('%d/%m/%Y %H:%M') if hasattr(fecha_aprobacion,'strftime') else fecha_aprobacion}</small>" if fecha_aprobacion else ""
        return f"<span style='color:white;background:#16a34a;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>Aceptado</span>{fecha}"
    if rechazado:
        fecha = f"<br><small>{fecha_rechazo.strftime('%d/%m/%Y %H:%M') if hasattr(fecha_rechazo,'strftime') else fecha_rechazo}</small>" if fecha_rechazo else ""
        return f"<span style='color:white;background:#dc2626;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>Rechazado</span>{fecha}"
    if estado == "Esperando aprobación":
        return "<span style='color:white;background:#f59e0b;padding:6px 12px;border-radius:999px;font-weight:bold;font-size:12px;'>Pendiente</span>"
    return "<span style='color:#6b7280;'>Sin decisión</span>"

def html_layout(titulo, contenido):
    avisos = get_flashed_messages(with_categories=True)
    avisos_html = ""
    for categoria, mensaje in avisos:
        if categoria == "error":
            fondo, borde, color, icono = "#fef2f2", "#fecaca", "#991b1b", "❌"
        else:
            fondo, borde, color, icono = "#f0fdf4", "#bbf7d0", "#166534", "✅"
        avisos_html += f"""
        <div style="background:{fondo};border:1px solid {borde};color:{color};padding:13px 15px;border-radius:12px;margin-bottom:14px;font-weight:700;">
          {icono} {escape(str(mensaje))}
        </div>
        """
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
            {avisos_html}
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
    CREATE TABLE IF NOT EXISTS stock_productos (
        id SERIAL PRIMARY KEY, codigo TEXT UNIQUE, grupo TEXT NOT NULL, nombre TEXT NOT NULL,
        categoria TEXT, marca TEXT, modelos_compatibles TEXT, proveedor TEXT,
        costo NUMERIC DEFAULT 0, precio_venta NUMERIC DEFAULT 0, cantidad INTEGER DEFAULT 0,
        stock_minimo INTEGER DEFAULT 0, ubicacion TEXT, activo BOOLEAN DEFAULT TRUE,
        fecha_alta TIMESTAMP DEFAULT NOW(), fecha_actualizacion TIMESTAMP DEFAULT NOW()
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_movimientos (
        id SERIAL PRIMARY KEY, producto_id INTEGER REFERENCES stock_productos(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, cantidad_anterior INTEGER, cantidad_nueva INTEGER,
        costo_unitario NUMERIC, proveedor TEXT, referencia TEXT, observacion TEXT, fecha TIMESTAMP DEFAULT NOW()
    );
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS ventas (
      id SERIAL PRIMARY KEY, numero_venta TEXT UNIQUE, cliente_id INTEGER REFERENCES clientes(id),
      fecha TIMESTAMP DEFAULT NOW(), forma_pago TEXT, total NUMERIC DEFAULT 0,
      costo_total NUMERIC DEFAULT 0, comprobante_numero TEXT UNIQUE, token_publico TEXT UNIQUE,
      garantia_dias INTEGER DEFAULT 30
    );""")
    cur.execute("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS garantia_dias INTEGER DEFAULT 30;")
    cur.execute("""CREATE TABLE IF NOT EXISTS venta_items (
      id SERIAL PRIMARY KEY, venta_id INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
      descripcion TEXT NOT NULL, cantidad INTEGER DEFAULT 1,
      precio_unitario NUMERIC DEFAULT 0, costo_unitario NUMERIC DEFAULT 0
    );""")

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
    # Corrige órdenes antiguas marcadas como Entregado sin fecha de entrega.
    # Si tienen comprobante, usamos su fecha; si no, la fecha actual.
    cur.execute("""
        UPDATE ordenes
        SET fecha_entregado = COALESCE(fecha_comprobante::date, CURRENT_DATE)
        WHERE estado = 'Entregado' AND fecha_entregado IS NULL
    """)


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
        return False

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
        return True
    except Exception as e:
        print("Error al enviar email:", e)
        return False


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
      <a href="/venta" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #bbf7d0;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">🛒 Nueva venta</h3><p style="margin:0;color:#6b7280;">Accesorios y ventas de mostrador.</p></div></a>
      <a href="/ventas" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #bfdbfe;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📚 Ventas</h3><p style="margin:0;color:#6b7280;">Historial de ventas y facturas emitidas.</p></div></a>
      <a href="/facturacion" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #c7d2fe;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📑 Facturación</h3><p style="margin:0;color:#6b7280;">Archivo mensual de todas las facturas.</p></div></a>
      <a href="/stock" style="text-decoration:none;color:inherit;"><div style="background:white;border:1px solid #fde68a;border-radius:18px;padding:22px;"><h3 style="margin:0 0 8px;">📦 Stock</h3><p style="margin:0;color:#6b7280;">Repuestos, accesorios y consumibles.</p></div></a>
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



@app.route("/venta", methods=["GET","POST"])
def venta_directa():
    if not session.get("login"): return redirect("/login")
    if request.method=="POST":
        nombre=request.form.get("nombre","").strip(); tel=request.form.get("telefono","").strip()
        email=request.form.get("email","").strip(); forma=request.form.get("forma_pago","").strip()
        try: garantia_dias=max(0,int(request.form.get("garantia_dias","30") or 30))
        except: garantia_dias=30
        ds=request.form.getlist("descripcion"); qs=request.form.getlist("cantidad")
        ps=request.form.getlist("precio"); cs=request.form.getlist("costo")
        items=[]; total=0.0; costos=0.0
        for d,q,p,c in zip(ds,qs,ps,cs):
            if not d.strip(): continue
            try: q=max(1,int(q or 1))
            except: q=1
            try: pv=float((p or "0").replace(",","."))
            except: pv=0
            try: cv=float((c or "0").replace(",","."))
            except: cv=0
            items.append((d.strip(),q,pv,cv)); total+=q*pv; costos+=q*cv
        if not items:
            flash("Agregá al menos un artículo.","error"); return redirect("/venta")
        con=db(); cur=con.cursor(); cid=None
        if tel:
            cur.execute("SELECT id FROM clientes WHERE telefono=%s LIMIT 1",(tel,)); r=cur.fetchone(); cid=r["id"] if r else None
        if not cid and (nombre or tel or email):
            cur.execute("INSERT INTO clientes(nombre,telefono,email) VALUES(%s,%s,%s) RETURNING id",(nombre or "Cliente mostrador",tel,email))
            cid=cur.fetchone()["id"]
        token=secrets.token_urlsafe(24)
        cur.execute("INSERT INTO ventas(numero_venta,cliente_id,forma_pago,total,costo_total,token_publico,garantia_dias) VALUES('',%s,%s,%s,%s,%s,%s) RETURNING id",(cid,forma,total,costos,token,garantia_dias))
        vid=cur.fetchone()["id"]; numero=f"V-{datetime.datetime.now().year}-{vid:05d}"; comp=f"NR-FAC-{datetime.datetime.now().year}-{vid:05d}"
        cur.execute("UPDATE ventas SET numero_venta=%s,comprobante_numero=%s WHERE id=%s",(numero,comp,vid))
        for it in items: cur.execute("INSERT INTO venta_items(venta_id,descripcion,cantidad,precio_unitario,costo_unitario) VALUES(%s,%s,%s,%s,%s)",(vid,*it))
        con.commit(); con.close()
        flash(f"Venta {numero} registrada y factura {comp} emitida por $ {total:,.2f}.","success")
        return redirect(f"/venta_comprobante/{vid}")
    return html_layout("Nueva venta",card_html("""
    <h2 style='margin-top:0'>🛒 Nueva venta</h2><p style='color:#64748b'>Para cargadores, cables, fundas, vidrios y otras ventas sin reparación.</p>
    <form method='post'><h3>Cliente <small style='font-weight:normal'>(opcional)</small></h3>
    <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px'><input name='nombre' placeholder='Nombre' style='padding:10px'><input name='telefono' placeholder='WhatsApp' style='padding:10px'><input name='email' type='email' placeholder='Email' style='padding:10px'></div>
    <h3>Artículos</h3><div id='items'><div class='item' style='display:grid;grid-template-columns:2fr .6fr 1fr 1fr;gap:8px;margin-bottom:8px'><input name='descripcion' required placeholder='Artículo' style='padding:10px'><input name='cantidad' type='number' min='1' value='1' style='padding:10px'><input name='precio' required placeholder='Precio venta' style='padding:10px'><input name='costo' placeholder='Costo' style='padding:10px'></div></div>
    <button type='button' onclick='addItem()'>+ Agregar artículo</button>
    <h3>Pago y garantía</h3>
    <select name='forma_pago' required style='padding:10px;margin-right:8px'><option>Efectivo</option><option>Transferencia</option><option>Mercado Pago</option><option>Débito</option><option>Crédito</option><option>Otro</option></select>
    <select name='garantia_dias' style='padding:10px'><option value='0'>Sin garantía comercial</option><option value='30' selected>Garantía 30 días</option><option value='90'>Garantía 90 días</option><option value='180'>Garantía 180 días</option><option value='365'>Garantía 365 días</option></select><br>
    <button style='margin-top:16px;background:#059669;color:white;border:0;padding:12px 18px;border-radius:10px;font-weight:bold'>💾 Registrar venta y emitir factura</button></form>
    <script>function addItem(){let d=document.querySelector('.item').cloneNode(true);d.querySelectorAll('input').forEach(x=>x.value=x.name==='cantidad'?'1':'');document.getElementById('items').appendChild(d)}</script>
    """))

@app.get("/venta_comprobante/<int:vid>")
def venta_comprobante(vid):
    if not session.get("login"): return redirect("/login")
    con=db(); cur=con.cursor()
    cur.execute("SELECT v.*,c.nombre,c.telefono,c.email FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=%s",(vid,)); v=cur.fetchone()
    if not v: con.close(); return redirect("/")
    cur.execute("SELECT * FROM venta_items WHERE venta_id=%s ORDER BY id",(vid,)); items=cur.fetchall(); con.close()
    filas="".join(f"<tr><td>{escape(i['descripcion'])}</td><td>{i['cantidad']}</td><td>$ {float(i['precio_unitario']):,.2f}</td><td>$ {float(i['cantidad'])*float(i['precio_unitario']):,.2f}</td></tr>" for i in items)
    base=BASE_URL or request.url_root.rstrip("/"); pub=f"{base}/venta_publica/{v['token_publico']}"
    tel="".join(ch for ch in str(v.get("telefono") or "") if ch.isdigit())
    if tel.startswith("0"): tel="598"+tel[1:]
    wa_text=quote(f"Hola {v.get('nombre') or ''}, te enviamos tu factura {v['comprobante_numero']} de NR Tech.\nTotal: $ {float(v['total']):,.2f}\nFactura y garantía: {pub}")
    wa=f"https://wa.me/{tel}?text={wa_text}" if tel else f"https://wa.me/?text={wa_text}"
    email_btn = f"<a href='/venta_email/{vid}' style='background:#7c3aed;color:white;padding:11px;text-decoration:none;border-radius:9px'>✉️ Enviar por email</a>" if v.get("email") else "<span style='padding:11px;color:#94a3b8'>✉️ Sin email cargado</span>"
    return html_layout("Venta",card_html(f"""<h2>✅ Venta registrada / factura emitida</h2><p><b>{v['comprobante_numero']}</b></p><table style='width:100%'>{filas}</table><h2>Total: $ {float(v['total']):,.2f}</h2>
    <div style='display:flex;gap:10px;flex-wrap:wrap'><a target='_blank' href='{wa}' style='background:#16a34a;color:white;padding:11px;text-decoration:none;border-radius:9px'>📲 Enviar por WhatsApp</a>{email_btn}<a target='_blank' href='{pub}' style='background:#2563eb;color:white;padding:11px;text-decoration:none;border-radius:9px'>📄 Ver</a><a target='_blank' href='/venta_imprimir/{vid}' style='background:#334155;color:white;padding:11px;text-decoration:none;border-radius:9px'>🖨️ Imprimir</a><a href='/ventas' style='background:#475569;color:white;padding:11px;text-decoration:none;border-radius:9px'>← Volver a ventas</a><a href='/' style='background:#0f172a;color:white;padding:11px;text-decoration:none;border-radius:9px'>🏠 Inicio</a></div>
    <p style='color:#64748b'>Esta factura ya quedó emitida y no se duplica al volver a abrirla.</p>"""))


@app.get("/venta_email/<int:vid>")
def venta_email(vid):
    if not session.get("login"):
        return redirect("/login")
    con=db(); cur=con.cursor()
    cur.execute("""SELECT v.*,c.nombre,c.email FROM ventas v
                   LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=%s""",(vid,))
    v=cur.fetchone(); con.close()
    if not v:
        return redirect("/ventas")
    if not v.get("email"):
        flash("El cliente no tiene email cargado.","error")
        return redirect(f"/venta_comprobante/{vid}")
    base=BASE_URL or request.url_root.rstrip("/")
    pub=f"{base}/venta_publica/{v['token_publico']}"
    asunto=f"NR Tech - Factura {v['comprobante_numero']}"
    cuerpo=f"""Hola {v.get('nombre') or ''},

Te enviamos la factura de tu compra en NR Tech.

Factura: {v['comprobante_numero']}
Total: $ {float(v['total']):,.2f}
Forma de pago: {v.get('forma_pago') or '-'}

Podés consultar tu factura y las condiciones de garantía aquí:
{pub}

NR Tech
Tecnología en buenas manos
"""
    if not REMITENTE_EMAIL or not CONTRASENA_APP:
        flash("No se pudo enviar el email: falta configurar la cuenta de correo.","error")
        return redirect(f"/venta_comprobante/{vid}")
    try:
        msg=EmailMessage()
        msg["Subject"]=asunto; msg["From"]=REMITENTE_EMAIL; msg["To"]=v["email"]
        msg.set_content(cuerpo)
        with smtplib.SMTP_SSL("smtp.gmail.com",465,timeout=25) as smtp:
            smtp.login(REMITENTE_EMAIL,CONTRASENA_APP); smtp.send_message(msg)
        flash(f"Factura enviada correctamente por email a {v['email']}.","success")
    except Exception as e:
        print("Error email venta:",e)
        flash("No se pudo enviar la factura por email.","error")
    return redirect(f"/venta_comprobante/{vid}")


@app.get("/venta_publica/<token>")
def venta_publica(token):
    con=db(); cur=con.cursor()
    cur.execute("""SELECT v.*,c.nombre FROM ventas v
                   LEFT JOIN clientes c ON c.id=v.cliente_id
                   WHERE token_publico=%s""",(token,))
    v=cur.fetchone()
    if not v:
        con.close()
        return "Factura no encontrada",404
    cur.execute("SELECT * FROM venta_items WHERE venta_id=%s ORDER BY id",(v["id"],))
    its=cur.fetchall()
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1")
    cfg=cur.fetchone() or {}
    con.close()

    filas="".join(
        f"<tr><td style='padding:9px;border-bottom:1px solid #e5e7eb'>{escape(i['descripcion'])}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #e5e7eb;text-align:center'>{i['cantidad']}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #e5e7eb;text-align:right'>$ {float(i['precio_unitario']):,.2f}</td>"
        f"<td style='padding:9px;border-bottom:1px solid #e5e7eb;text-align:right'>$ {float(i['cantidad'])*float(i['precio_unitario']):,.2f}</td></tr>"
        for i in its
    )
    fecha=v["fecha"].date() if hasattr(v["fecha"],"date") else datetime.date.today()
    dias=int(v.get("garantia_dias") or 0)
    vence=fecha+datetime.timedelta(days=dias) if dias>0 else None
    garantia_html = (
        f"""<div style='background:#f0fdf4;border:1px solid #bbf7d0;padding:14px;border-radius:12px;margin-top:18px'>
        <h3 style='margin-top:0'>🛡️ Garantía de la venta</h3>
        <p><strong>Duración:</strong> {dias} días · <strong>Válida hasta:</strong> {vence.strftime('%d/%m/%Y')}</p>
        <p><strong>Cubre:</strong> fallas o defectos relacionados directamente con los artículos detallados en esta factura, dentro del plazo indicado y sujetos a revisión.</p>
        <p><strong>No cubre:</strong> golpes, caídas, humedad o líquidos, sobrecargas eléctricas, mal uso, daños físicos, manipulación por terceros ni daños ajenos al funcionamiento normal del producto.</p>
        <p style='font-size:13px;color:#475569'>Para solicitar garantía se deberá presentar esta factura o identificar la venta correspondiente. NR Tech realizará una revisión previa para determinar si corresponde la cobertura.</p>
        </div>"""
        if dias>0 else
        "<div style='background:#f8fafc;padding:12px;border-radius:10px;margin-top:18px'><strong>Garantía comercial:</strong> no especificada para esta venta.</div>"
    )
    return html_layout("Factura NR Tech",card_html(f"""
      <div style='text-align:center'>
        <h1 style='margin-bottom:4px'>{escape(str(cfg.get('nombre_comercial') or 'NR Tech'))}</h1>
        <div style='color:#64748b'>Tecnología en buenas manos</div>
      </div>
      <div style='border:2px solid #111827;padding:8px;text-align:center;font-weight:900;margin:14px 0'>FACTURA · MONOTRIBUTO</div>
      <p><strong>Titular:</strong> {escape(str(cfg.get('titular') or '-'))}<br>
      <strong>RUT:</strong> {escape(str(cfg.get('rut') or '-'))}<br>
      <strong>Domicilio fiscal:</strong> {escape(str(cfg.get('domicilio_fiscal') or '-'))}<br>
      <strong>Tel./WhatsApp:</strong> {escape(str(cfg.get('telefono') or '-'))}<br>
      <strong>Email:</strong> {escape(str(cfg.get('email') or '-'))}</p>
      <hr>
      <p><strong>Factura:</strong> {escape(str(v['comprobante_numero']))}<br>
      <strong>Fecha:</strong> {v['fecha'].strftime('%d/%m/%Y %H:%M') if hasattr(v['fecha'],'strftime') else escape(str(v['fecha']))}<br>
      <strong>Cliente:</strong> {escape(str(v.get('nombre') or 'Consumidor final'))}<br>
      <strong>Forma de pago:</strong> {escape(str(v['forma_pago'] or '-'))}</p>
      <table style='width:100%;border-collapse:collapse;margin-top:12px'>
        <tr style='background:#eff6ff'><th style='padding:9px;text-align:left'>Artículo</th><th>Cant.</th><th style='text-align:right'>Precio</th><th style='text-align:right'>Subtotal</th></tr>
        {filas}
      </table>
      <h2 style='text-align:right'>Total: $ {float(v['total']):,.2f}</h2>
      {garantia_html}
      <div style='display:grid;grid-template-columns:1fr 150px;gap:16px;align-items:center;margin-top:18px'>
        <div style='font-size:12px;color:#64748b'>Factura y respaldo de garantía de NR Tech. Guardá este documento para futuras consultas.</div>
        <div style='text-align:center'><img src='/qr_venta/{token}.png' style='width:130px;height:130px'><div style='font-size:11px'>Verificar factura</div></div>
      </div>
      <div style='display:flex;gap:10px;flex-wrap:wrap;margin-top:18px'>
        <a href='/' style='background:#2563eb;color:white;padding:11px 15px;border-radius:10px;text-decoration:none;font-weight:bold'>🏠 Inicio</a>
        <a href='/ventas' style='background:#475569;color:white;padding:11px 15px;border-radius:10px;text-decoration:none;font-weight:bold'>← Volver a ventas</a>
      </div>
    """))


@app.get("/qr_venta/<token>.png")
def qr_venta(token):
    url=f"{BASE_URL or request.url_root.rstrip('/')}/venta_publica/{token}"
    img=qrcode.make(url)
    bio=BytesIO(); img.save(bio,format="PNG"); bio.seek(0)
    return send_file(bio,mimetype="image/png")


@app.get("/venta_imprimir/<int:vid>")
def venta_imprimir(vid):
    if not session.get("login"):
        return redirect("/login")
    con=db(); cur=con.cursor()
    cur.execute("""SELECT v.*,c.nombre FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=%s""",(vid,))
    v=cur.fetchone()
    if not v:
        con.close()
        return redirect("/")
    cur.execute("SELECT * FROM venta_items WHERE venta_id=%s ORDER BY id",(vid,))
    its=cur.fetchall()
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1")
    cfg=cur.fetchone() or {}
    con.close()

    filas="".join(
        f"<tr><td>{escape(i['descripcion'])}</td><td>{i['cantidad']}</td><td>$ {float(i['precio_unitario']):,.2f}</td><td>$ {float(i['cantidad'])*float(i['precio_unitario']):,.2f}</td></tr>"
        for i in its
    )
    dias=int(v.get("garantia_dias") or 0)
    fecha=v["fecha"].date() if hasattr(v["fecha"],"date") else datetime.date.today()
    vence=fecha+datetime.timedelta(days=dias) if dias>0 else None
    garantia = f"""
      <div class='garantia'>
        <h3>Condiciones de garantía – NR Tech</h3>
        <p><b>Garantía:</b> {dias} días — válida hasta {vence.strftime('%d/%m/%Y')}</p>
        <p>La garantía cubre fallas o defectos relacionados directamente con los artículos detallados en esta factura durante el plazo indicado y sujetos a revisión.</p>
        <p>No cubre golpes, caídas, humedad o líquidos, sobrecargas eléctricas, mal uso, daños físicos, manipulación por terceros ni daños ajenos al funcionamiento normal del producto.</p>
        <p>Para solicitar garantía se deberá presentar esta factura o identificar la venta correspondiente. NR Tech realizará una revisión previa para determinar si corresponde la cobertura.</p>
      </div>
    """ if dias>0 else "<div class='garantia'><b>Garantía comercial:</b> no especificada para esta venta.</div>"

    return f"""<!doctype html><html><head><meta charset='utf-8'>
    <title>{escape(str(v['comprobante_numero']))}</title>
    <style>
      @page{{size:A4;margin:15mm}}
      body{{font-family:Arial;color:#111827;max-width:780px;margin:20px auto}}
      .head{{border-bottom:3px solid #111827;padding-bottom:12px}}
      .fiscal{{border:2px solid #111827;text-align:center;padding:8px;font-weight:900;margin:14px 0}}
      table{{width:100%;border-collapse:collapse}} td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
      .garantia{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin-top:18px;font-size:12px;line-height:1.45}}
      .qr{{text-align:right;margin-top:12px}} .qr img{{width:120px;height:120px}}
      @media print{{button{{display:none}}body{{margin:0}}}}
    </style></head><body>
    <button onclick='window.print()'>🖨️ Imprimir</button>
    <div class='head'><h1 style='margin:0'>{escape(str(cfg.get('nombre_comercial') or 'NR Tech'))}</h1>
      <div>Tecnología en buenas manos</div>
      <div>{escape(str(cfg.get('titular') or '-'))}</div>
      <div>RUT: {escape(str(cfg.get('rut') or '-'))}</div>
      <div>{escape(str(cfg.get('domicilio_fiscal') or '-'))}</div>
      <div>Tel./WhatsApp: {escape(str(cfg.get('telefono') or '-'))} · {escape(str(cfg.get('email') or '-'))}</div>
    </div>
    <div class='fiscal'>FACTURA · MONOTRIBUTO</div>
    <p><b>N.º:</b> {escape(str(v['comprobante_numero']))}<br>
       <b>Fecha:</b> {v['fecha'].strftime('%d/%m/%Y %H:%M') if hasattr(v['fecha'],'strftime') else escape(str(v['fecha']))}<br>
       <b>Cliente:</b> {escape(str(v.get('nombre') or 'Consumidor final'))}<br>
       <b>Forma de pago:</b> {escape(str(v['forma_pago'] or '-'))}</p>
    <table><tr><th>Artículo</th><th>Cant.</th><th>Precio</th><th>Subtotal</th></tr>{filas}</table>
    <h2 style='text-align:right'>Total: $ {float(v['total']):,.2f}</h2>
    {garantia}
    <div class='qr'><img src='/qr_venta/{v["token_publico"]}.png'><br><small>Verificar factura y garantía</small></div>
    </body></html>"""



@app.get("/finanzas_pendientes")
def finanzas_pendientes():
    if not session.get("login"):
        return redirect("/login")

    hoy=datetime.date.today()
    try:
        anio=int(request.args.get("anio",hoy.year))
        mes=int(request.args.get("mes",hoy.month))
    except Exception:
        anio,mes=hoy.year,hoy.month

    con=db(); cur=con.cursor()
    cur.execute("""
      SELECT o.numero_orden,c.nombre,c.telefono,o.tipo_equipo,o.marca,o.modelo,
             COALESCE(o.comprobante_total,o.presupuesto,0) AS total,
             COALESCE(o.cobrado,0) AS cobrado,
             GREATEST(COALESCE(o.comprobante_total,o.presupuesto,0)-COALESCE(o.cobrado,0),0) AS saldo,
             COALESCE(o.fecha_entregado,o.fecha_comprobante::date) AS fecha
      FROM ordenes o
      JOIN clientes c ON c.id=o.cliente_id
      WHERE o.estado='Entregado'
        AND COALESCE(o.fecha_entregado,o.fecha_comprobante::date) IS NOT NULL
        AND EXTRACT(YEAR FROM COALESCE(o.fecha_entregado,o.fecha_comprobante::date))=%s
        AND EXTRACT(MONTH FROM COALESCE(o.fecha_entregado,o.fecha_comprobante::date))=%s
        AND GREATEST(COALESCE(o.comprobante_total,o.presupuesto,0)-COALESCE(o.cobrado,0),0) > 0
      ORDER BY fecha DESC,o.id DESC
    """,(anio,mes))
    filas=cur.fetchall(); con.close()

    total_pendiente=sum(float(r.get("saldo") or 0) for r in filas)
    html_filas=""
    for r in filas:
        equipo=" ".join([str(r.get("tipo_equipo") or ""),str(r.get("marca") or ""),str(r.get("modelo") or "")]).strip() or "-"
        html_filas+=f"""
          <tr>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(r.get("fecha") or "-"))}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(r["numero_orden"]))}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(r.get("nombre") or "-"))}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(equipo)}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>$ {float(r.get("total") or 0):,.2f}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>$ {float(r.get("cobrado") or 0):,.2f}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb;font-weight:bold;color:#b91c1c'>$ {float(r.get("saldo") or 0):,.2f}</td>
            <td style='padding:10px;border-bottom:1px solid #e5e7eb'>
              <a href='/editar?numero={quote(str(r["numero_orden"]))}' style='color:#2563eb;font-weight:bold'>Abrir orden</a>
            </td>
          </tr>
        """

    return html_layout("Pendientes de cobro",card_html(f"""
      <div style='display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap'>
        <div>
          <h2 style='margin:0'>💸 Pendientes de cobro</h2>
          <p style='color:#64748b'>Detalle de órdenes entregadas con saldo pendiente del período {mes:02d}/{anio}.</p>
        </div>
        <a href='/finanzas?anio={anio}&mes={mes}' style='font-weight:bold;color:#2563eb'>← Volver a Finanzas</a>
      </div>
      <div style='background:#fef2f2;border:1px solid #fecaca;padding:14px;border-radius:12px;margin:15px 0'>
        <small>Saldo total pendiente</small>
        <div style='font-size:28px;font-weight:900;color:#b91c1c'>$ {total_pendiente:,.2f}</div>
      </div>
      <div style='overflow-x:auto'>
        <table style='width:100%;border-collapse:collapse'>
          <tr style='background:#eff6ff;text-align:left'>
            <th style='padding:10px'>Fecha</th><th style='padding:10px'>Orden</th><th style='padding:10px'>Cliente</th>
            <th style='padding:10px'>Equipo</th><th style='padding:10px'>Total</th><th style='padding:10px'>Cobrado</th>
            <th style='padding:10px'>Saldo</th><th style='padding:10px'></th>
          </tr>
          {html_filas or "<tr><td colspan='8' style='padding:18px;text-align:center;color:#64748b'>No hay saldos pendientes en este período.</td></tr>"}
        </table>
      </div>
    """))


@app.get("/ventas")
def listar_ventas():
    if not session.get("login"):
        return redirect("/login")
    con=db(); cur=con.cursor()
    cur.execute("""
      SELECT v.id,v.numero_venta,v.fecha,v.forma_pago,v.total,v.costo_total,v.comprobante_numero,
             c.nombre,c.telefono
      FROM ventas v
      LEFT JOIN clientes c ON c.id=v.cliente_id
      ORDER BY v.id DESC
    """)
    ventas=cur.fetchall(); con.close()
    filas=""
    for v in ventas:
        gan=float(v.get("total") or 0)-float(v.get("costo_total") or 0)
        filas+=f"""
        <tr>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(v['fecha'].strftime('%d/%m/%Y %H:%M') if hasattr(v['fecha'],'strftime') else v['fecha']))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(v['numero_venta']))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(v['comprobante_numero']))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>{escape(str(v.get('nombre') or 'Consumidor final'))}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>$ {float(v.get('total') or 0):,.2f}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>$ {gan:,.2f}</td>
          <td style='padding:10px;border-bottom:1px solid #e5e7eb'>
            <a href='/venta_comprobante/{v["id"]}' style='color:#2563eb;font-weight:bold;margin-right:10px'>Ver</a>
            <a href='/eliminar_venta?id={v["id"]}' style='color:#dc2626;font-weight:bold'>Eliminar</a>
          </td>
        </tr>"""
    return html_layout("Ventas",card_html(f"""
      <div style='display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap'>
        <div><h2 style='margin:0'>📚 Ventas</h2><p style='color:#64748b'>Historial de ventas directas y facturas emitidas.</p></div>
        <a href='/venta' style='background:#059669;color:white;padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:bold'>🛒 Nueva venta</a>
      </div>
      <div style='overflow-x:auto;margin-top:16px'>
      <table style='width:100%;border-collapse:collapse'>
        <tr style='background:#eff6ff;text-align:left'>
          <th style='padding:10px'>Fecha</th><th style='padding:10px'>Venta</th><th style='padding:10px'>Factura</th>
          <th style='padding:10px'>Cliente</th><th style='padding:10px'>Total</th><th style='padding:10px'>Ganancia</th><th style='padding:10px'></th>
        </tr>
        {filas or "<tr><td colspan='7' style='padding:18px;text-align:center;color:#64748b'>No hay ventas registradas.</td></tr>"}
      </table></div>
      <p style='margin-top:16px'><a href='/'>🏠 Inicio</a></p>
    """))


@app.route("/eliminar_venta", methods=["GET","POST"])
def eliminar_venta():
    if not session.get("login"):
        return redirect("/login")
    try:
        vid=int(request.values.get("id","0"))
    except:
        return redirect("/ventas")
    con=db(); cur=con.cursor()
    cur.execute("""SELECT v.*,c.nombre FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=%s""",(vid,))
    v=cur.fetchone()
    if not v:
        con.close(); return redirect("/ventas")
    if request.method=="POST":
        if request.form.get("confirmar")!="ELIMINAR":
            con.close()
            return html_layout("Confirmación",card_html("<h2>No se eliminó la venta</h2><p>Debés escribir ELIMINAR exactamente.</p>"))
        cur.execute("DELETE FROM ventas WHERE id=%s",(vid,))
        con.commit(); con.close()
        flash(f"Venta {v['numero_venta']} eliminada. También dejó de contar en Finanzas.","success")
        return redirect("/ventas")
    con.close()
    return html_layout("Eliminar venta",card_html(f"""
      <h2 style='color:#b91c1c;margin-top:0'>🗑️ Eliminar venta</h2>
      <div style='background:#fef2f2;border:1px solid #fecaca;padding:14px;border-radius:12px'>
        Venta: <b>{escape(str(v['numero_venta']))}</b><br>
        Factura: <b>{escape(str(v['comprobante_numero']))}</b><br>
        Cliente: {escape(str(v.get('nombre') or 'Consumidor final'))}<br>
        Total: <b>$ {float(v.get('total') or 0):,.2f}</b>
      </div>
      <p><strong>Al eliminarla también se descontará automáticamente de Finanzas.</strong></p>
      <p style='color:#b45309;font-size:13px'>Usá esta opción para pruebas o registros cargados por error. Una factura fiscal real debería anularse, no borrarse.</p>
      <form method='post'>
        <input type='hidden' name='id' value='{vid}'>
        <label>Escribí <b>ELIMINAR</b>:</label><br>
        <input name='confirmar' autocomplete='off' style='padding:10px;margin:8px 0;border:1px solid #d1d5db;border-radius:9px'>
        <br><button style='background:#dc2626;color:white;border:0;padding:11px 16px;border-radius:10px;font-weight:bold'>Eliminar venta</button>
        <a href='/ventas' style='margin-left:10px'>Cancelar</a>
      </form>
    """))




@app.get("/stock")
def stock():
    if not session.get("login"): return redirect("/login")
    q=request.args.get("q","").strip(); grupo=request.args.get("grupo","").strip()
    con=db(); cur=con.cursor(); sql="SELECT * FROM stock_productos WHERE activo=TRUE"; params=[]
    if grupo: sql+=" AND grupo=%s"; params.append(grupo)
    if q:
        like=f"%{q}%"; sql+=" AND (COALESCE(codigo,'') ILIKE %s OR COALESCE(nombre,'') ILIKE %s OR COALESCE(categoria,'') ILIKE %s OR COALESCE(marca,'') ILIKE %s OR COALESCE(modelos_compatibles,'') ILIKE %s OR COALESCE(proveedor,'') ILIKE %s)"; params += [like]*6
    sql+=" ORDER BY CASE WHEN cantidad<=stock_minimo THEN 0 ELSE 1 END, grupo,nombre"
    cur.execute(sql,tuple(params)); productos=cur.fetchall()
    cur.execute("""SELECT COUNT(*) productos,COALESCE(SUM(cantidad),0) unidades,COALESCE(SUM(cantidad*costo),0) inversion,
      COALESCE(SUM(CASE WHEN cantidad<=0 THEN 1 ELSE 0 END),0) sin_stock,
      COALESCE(SUM(CASE WHEN cantidad>0 AND cantidad<=stock_minimo THEN 1 ELSE 0 END),0) bajo FROM stock_productos WHERE activo=TRUE""")
    resumen=cur.fetchone() or {}; con.close()
    filas=""
    for x in productos:
        cant=int(x.get("cantidad") or 0); minv=int(x.get("stock_minimo") or 0)
        estado = "<span style='background:#fee2e2;color:#991b1b;padding:5px 9px;border-radius:999px;font-weight:bold'>Sin stock</span>" if cant<=0 else ("<span style='background:#fef3c7;color:#92400e;padding:5px 9px;border-radius:999px;font-weight:bold'>Stock bajo</span>" if cant<=minv else "<span style='background:#dcfce7;color:#166534;padding:5px 9px;border-radius:999px;font-weight:bold'>OK</span>")
        filas+=f"""<tr><td>{escape(str(x.get('codigo') or '-'))}</td><td><b>{escape(str(x.get('nombre') or '-'))}</b><br><small>{escape(str(x.get('marca') or ''))}</small></td><td>{escape(str(x.get('grupo') or '-'))}</td><td>{escape(str(x.get('categoria') or '-'))}</td><td>{escape(str(x.get('modelos_compatibles') or '-'))}</td><td>{cant}</td><td>{minv}</td><td>{estado}</td><td>{escape(str(x.get('ubicacion') or '-'))}</td><td>$ {float(x.get('costo') or 0):,.2f}</td><td>$ {float(x.get('precio_venta') or 0):,.2f}</td><td><a href='/stock/producto/{x["id"]}' style='font-weight:bold;color:#2563eb;margin-right:8px'>Ver</a><a href='/stock/movimiento/{x["id"]}' style='font-weight:bold;color:#16a34a'>Movimiento</a></td></tr>"""
    return html_layout("Stock",card_html(f"""<div style='display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap'><div><h2 style='margin:0'>📦 Stock</h2><p style='color:#64748b'>Repuestos, accesorios de venta y artículos/consumibles del taller.</p></div><div><a href='/stock/nuevo' style='background:#2563eb;color:white;padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:bold'>➕ Nuevo producto</a> <a href='/stock/movimientos' style='background:#475569;color:white;padding:10px 14px;border-radius:10px;text-decoration:none;font-weight:bold'>📜 Movimientos</a> <a href='/'>🏠 Inicio</a></div></div>
    <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:16px 0'><div style='background:#f8fafc;padding:14px;border-radius:12px'><small>Productos</small><div style='font-size:24px;font-weight:900'>{int(resumen.get("productos") or 0)}</div></div><div style='background:#f8fafc;padding:14px;border-radius:12px'><small>Unidades</small><div style='font-size:24px;font-weight:900'>{int(resumen.get("unidades") or 0)}</div></div><div style='background:#eff6ff;padding:14px;border-radius:12px'><small>Invertido</small><div style='font-size:24px;font-weight:900'>$ {float(resumen.get("inversion") or 0):,.2f}</div></div><div style='background:#fef3c7;padding:14px;border-radius:12px'><small>Stock bajo</small><div style='font-size:24px;font-weight:900'>{int(resumen.get("bajo") or 0)}</div></div><div style='background:#fee2e2;padding:14px;border-radius:12px'><small>Sin stock</small><div style='font-size:24px;font-weight:900'>{int(resumen.get("sin_stock") or 0)}</div></div></div>
    <form method='get' style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px'><select name='grupo' style='padding:9px'><option value=''>Todos los grupos</option><option value='Repuesto' {'selected' if grupo=='Repuesto' else ''}>Repuestos</option><option value='Accesorio' {'selected' if grupo=='Accesorio' else ''}>Accesorios</option><option value='Herramienta / consumible' {'selected' if grupo=='Herramienta / consumible' else ''}>Herramientas / consumibles</option></select><input name='q' value='{escape(q)}' placeholder='Buscar código, producto, modelo, proveedor...' style='padding:9px;min-width:280px'><button style='padding:9px 14px'>Buscar</button></form>
    <div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse;min-width:1150px'><tr style='background:#eff6ff'><th>Código</th><th>Producto</th><th>Grupo</th><th>Categoría</th><th>Compatibilidad</th><th>Stock</th><th>Mín.</th><th>Estado</th><th>Ubicación</th><th>Costo</th><th>Venta</th><th></th></tr>{filas or "<tr><td colspan='12' style='padding:18px;text-align:center;color:#64748b'>No hay productos cargados.</td></tr>"}</table></div><style>table th,table td{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}}</style>"""))

@app.route("/stock/nuevo",methods=["GET","POST"])
def stock_nuevo():
    if not session.get("login"): return redirect("/login")
    if request.method=="POST":
        grupo=request.form.get("grupo","").strip(); nombre=request.form.get("nombre","").strip(); codigo=request.form.get("codigo","").strip(); categoria=request.form.get("categoria","").strip(); marca=request.form.get("marca","").strip(); compat=request.form.get("compatibilidad","").strip(); proveedor=request.form.get("proveedor","").strip(); ubicacion=request.form.get("ubicacion","").strip()
        try:costo=float((request.form.get("costo") or "0").replace(",","."))
        except:costo=0
        try:precio=float((request.form.get("precio") or "0").replace(",","."))
        except:precio=0
        try:cantidad=max(0,int(request.form.get("cantidad") or 0))
        except:cantidad=0
        try:minimo=max(0,int(request.form.get("minimo") or 0))
        except:minimo=0
        if not nombre or grupo not in ["Repuesto","Accesorio","Herramienta / consumible"]: flash("Completá nombre y grupo correctamente.","error"); return redirect("/stock/nuevo")
        con=db();cur=con.cursor()
        if not codigo:
            cur.execute("SELECT COALESCE(MAX(id),0)+1 n FROM stock_productos"); n=int(cur.fetchone()["n"] or 1); pref={"Repuesto":"REP","Accesorio":"ACC","Herramienta / consumible":"CON"}[grupo]; codigo=f"{pref}-{n:05d}"
        try:
            cur.execute("""INSERT INTO stock_productos(codigo,grupo,nombre,categoria,marca,modelos_compatibles,proveedor,costo,precio_venta,cantidad,stock_minimo,ubicacion) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(codigo,grupo,nombre,categoria,marca,compat,proveedor,costo,precio,cantidad,minimo,ubicacion)); pid=cur.fetchone()["id"]
            if cantidad>0: cur.execute("""INSERT INTO stock_movimientos(producto_id,tipo,cantidad,cantidad_anterior,cantidad_nueva,costo_unitario,proveedor,observacion) VALUES(%s,'Alta inicial',%s,0,%s,%s,%s,'Carga inicial de stock')""",(pid,cantidad,cantidad,costo,proveedor))
            con.commit()
        except Exception:
            con.rollback();con.close();flash("No se pudo guardar. Revisá que el código no esté repetido.","error");return redirect("/stock/nuevo")
        con.close();flash(f"Producto {codigo} agregado correctamente.","success");return redirect(f"/stock/producto/{pid}")
    return html_layout("Nuevo producto",card_html("""<h2 style='margin-top:0'>➕ Nuevo producto de stock</h2><form method='post'><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px'><div><label>Grupo *</label><br><select name='grupo' required style='width:100%;padding:10px'><option value=''>Elegir...</option><option>Repuesto</option><option>Accesorio</option><option>Herramienta / consumible</option></select></div><div><label>Código interno</label><br><input name='codigo' placeholder='Automático si queda vacío' style='width:100%;padding:10px'></div><div><label>Nombre *</label><br><input name='nombre' required style='width:100%;padding:10px'></div><div><label>Categoría</label><br><input name='categoria' placeholder='Pantalla, batería, cargador...' style='width:100%;padding:10px'></div><div><label>Marca</label><br><input name='marca' style='width:100%;padding:10px'></div><div><label>Proveedor</label><br><input name='proveedor' style='width:100%;padding:10px'></div><div><label>Costo unitario</label><br><input name='costo' value='0' style='width:100%;padding:10px'></div><div><label>Precio de venta</label><br><input name='precio' value='0' style='width:100%;padding:10px'></div><div><label>Cantidad inicial</label><br><input name='cantidad' type='number' min='0' value='0' style='width:100%;padding:10px'></div><div><label>Stock mínimo</label><br><input name='minimo' type='number' min='0' value='0' style='width:100%;padding:10px'></div><div><label>Ubicación física</label><br><input name='ubicacion' placeholder='Cajón A3 / Estante 2' style='width:100%;padding:10px'></div></div><div style='margin-top:12px'><label>Compatibilidad / modelos</label><br><textarea name='compatibilidad' rows='3' style='width:100%;padding:10px'></textarea></div><button style='margin-top:14px;background:#2563eb;color:white;border:0;padding:12px 18px;border-radius:10px;font-weight:bold'>Guardar producto</button> <a href='/stock'>Cancelar</a></form>"""))

@app.route("/stock/producto/<int:pid>",methods=["GET","POST"])
def stock_producto(pid):
    if not session.get("login"):return redirect("/login")
    con=db();cur=con.cursor();cur.execute("SELECT * FROM stock_productos WHERE id=%s",(pid,));p=cur.fetchone()
    if not p:con.close();return redirect("/stock")
    if request.method=="POST":
        try:costo=float((request.form.get("costo") or "0").replace(",","."))
        except:costo=float(p.get("costo") or 0)
        try:precio=float((request.form.get("precio") or "0").replace(",","."))
        except:precio=float(p.get("precio_venta") or 0)
        try:minimo=max(0,int(request.form.get("minimo") or 0))
        except:minimo=int(p.get("stock_minimo") or 0)
        cur.execute("""UPDATE stock_productos SET nombre=%s,categoria=%s,marca=%s,modelos_compatibles=%s,proveedor=%s,costo=%s,precio_venta=%s,stock_minimo=%s,ubicacion=%s,fecha_actualizacion=NOW() WHERE id=%s""",(request.form.get("nombre","").strip(),request.form.get("categoria","").strip(),request.form.get("marca","").strip(),request.form.get("compatibilidad","").strip(),request.form.get("proveedor","").strip(),costo,precio,minimo,request.form.get("ubicacion","").strip(),pid));con.commit();con.close();flash("Producto actualizado correctamente.","success");return redirect(f"/stock/producto/{pid}")
    cur.execute("SELECT * FROM stock_movimientos WHERE producto_id=%s ORDER BY id DESC LIMIT 20",(pid,));movs=cur.fetchall();con.close();filas="".join(f"<tr><td>{escape(str(m['fecha']))}</td><td>{escape(str(m['tipo']))}</td><td>{m['cantidad']}</td><td>{m.get('cantidad_anterior')}</td><td>{m.get('cantidad_nueva')}</td><td>{escape(str(m.get('referencia') or '-'))}</td></tr>" for m in movs)
    return html_layout("Producto",card_html(f"""<h2>{escape(str(p['nombre']))}</h2><p><b>{escape(str(p['codigo']))}</b> · {escape(str(p['grupo']))}</p><div style='background:#eff6ff;padding:14px;border-radius:12px'><b>Stock actual:</b> {int(p.get('cantidad') or 0)} · <b>Mínimo:</b> {int(p.get('stock_minimo') or 0)} · <b>Ubicación:</b> {escape(str(p.get('ubicacion') or '-'))}</div><p><a href='/stock/movimiento/{pid}' style='font-weight:bold;color:#16a34a'>➕ Registrar movimiento</a> · <a href='/stock'>Volver</a></p><form method='post'><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px'><input name='nombre' value='{escape(str(p.get("nombre") or ""))}' placeholder='Nombre'><input name='categoria' value='{escape(str(p.get("categoria") or ""))}' placeholder='Categoría'><input name='marca' value='{escape(str(p.get("marca") or ""))}' placeholder='Marca'><input name='proveedor' value='{escape(str(p.get("proveedor") or ""))}' placeholder='Proveedor'><input name='costo' value='{p.get("costo") or 0}' placeholder='Costo'><input name='precio' value='{p.get("precio_venta") or 0}' placeholder='Precio venta'><input type='number' name='minimo' value='{int(p.get("stock_minimo") or 0)}'><input name='ubicacion' value='{escape(str(p.get("ubicacion") or ""))}' placeholder='Ubicación'></div><textarea name='compatibilidad' rows='3' style='width:100%;margin-top:10px'>{escape(str(p.get("modelos_compatibles") or ""))}</textarea><button style='margin-top:10px'>Guardar cambios</button></form><h3>Últimos movimientos</h3><div style='overflow-x:auto'><table style='width:100%'><tr><th>Fecha</th><th>Tipo</th><th>Cant.</th><th>Antes</th><th>Después</th><th>Referencia</th></tr>{filas or '<tr><td colspan="6">Sin movimientos.</td></tr>'}</table></div>"""))

@app.route("/stock/movimiento/<int:pid>",methods=["GET","POST"])
def stock_movimiento(pid):
    if not session.get("login"):return redirect("/login")
    con=db();cur=con.cursor();cur.execute("SELECT * FROM stock_productos WHERE id=%s",(pid,));p=cur.fetchone()
    if not p:con.close();return redirect("/stock")
    if request.method=="POST":
        tipo=request.form.get("tipo","").strip();
        try:cantidad=max(1,int(request.form.get("cantidad") or 1))
        except:cantidad=1
        anterior=int(p.get("cantidad") or 0)
        if tipo in ["Entrada compra","Devolución","Ajuste +"]: nueva=anterior+cantidad; mov=cantidad
        elif tipo in ["Salida manual","Merma / rotura","Ajuste -"]:
            if cantidad>anterior:con.close();flash("No hay suficiente stock para esa salida.","error");return redirect(f"/stock/movimiento/{pid}")
            nueva=anterior-cantidad;mov=-cantidad
        else:con.close();flash("Elegí un tipo válido.","error");return redirect(f"/stock/movimiento/{pid}")
        try:costo=float((request.form.get("costo") or p.get("costo") or 0).replace(",",".")) if isinstance(request.form.get("costo") or '',str) else float(p.get("costo") or 0)
        except:costo=float(p.get("costo") or 0)
        proveedor=request.form.get("proveedor","").strip() or p.get("proveedor");ref=request.form.get("referencia","").strip();obs=request.form.get("observacion","").strip()
        cur.execute("UPDATE stock_productos SET cantidad=%s,costo=%s,proveedor=%s,fecha_actualizacion=NOW() WHERE id=%s",(nueva,costo,proveedor,pid));cur.execute("""INSERT INTO stock_movimientos(producto_id,tipo,cantidad,cantidad_anterior,cantidad_nueva,costo_unitario,proveedor,referencia,observacion) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(pid,tipo,mov,anterior,nueva,costo,proveedor,ref,obs));con.commit();con.close();flash(f"Movimiento registrado. Stock: {anterior} → {nueva}.","success");return redirect(f"/stock/producto/{pid}")
    con.close();return html_layout("Movimiento",card_html(f"""<h2>📦 Movimiento — {escape(str(p['nombre']))}</h2><p>Stock actual: <b>{int(p.get('cantidad') or 0)}</b></p><form method='post'><select name='tipo' required><option>Entrada compra</option><option>Devolución</option><option>Ajuste +</option><option>Salida manual</option><option>Merma / rotura</option><option>Ajuste -</option></select><br><br><input name='cantidad' type='number' min='1' value='1' placeholder='Cantidad'><br><br><input name='costo' value='{p.get("costo") or 0}' placeholder='Costo unitario'><br><br><input name='proveedor' value='{escape(str(p.get("proveedor") or ""))}' placeholder='Proveedor'><br><br><input name='referencia' placeholder='Referencia'><br><br><textarea name='observacion' placeholder='Observación'></textarea><br><button>Guardar movimiento</button> <a href='/stock/producto/{pid}'>Cancelar</a></form>"""))

@app.get("/stock/movimientos")
def stock_movimientos():
    if not session.get("login"):return redirect("/login")
    con=db();cur=con.cursor();cur.execute("""SELECT m.*,p.codigo,p.nombre FROM stock_movimientos m JOIN stock_productos p ON p.id=m.producto_id ORDER BY m.id DESC LIMIT 300""");ms=cur.fetchall();con.close();filas="".join(f"<tr><td>{escape(str(m['fecha']))}</td><td>{escape(str(m['codigo']))}</td><td>{escape(str(m['nombre']))}</td><td>{escape(str(m['tipo']))}</td><td>{m['cantidad']}</td><td>{m.get('cantidad_anterior')}</td><td>{m.get('cantidad_nueva')}</td><td>{escape(str(m.get('referencia') or '-'))}</td></tr>" for m in ms);return html_layout("Movimientos",card_html(f"""<h2>📜 Movimientos de stock</h2><p><a href='/stock'>← Volver a Stock</a></p><div style='overflow-x:auto'><table style='width:100%'><tr><th>Fecha</th><th>Código</th><th>Producto</th><th>Tipo</th><th>Movimiento</th><th>Antes</th><th>Después</th><th>Referencia</th></tr>{filas or '<tr><td colspan="8">Sin movimientos.</td></tr>'}</table></div>"""))


@app.get("/facturacion")
def facturacion():
    if not session.get("login"):
        return redirect("/login")
    hoy=datetime.date.today()
    try:
        anio=int(request.args.get("anio",hoy.year)); mes=int(request.args.get("mes",hoy.month))
    except Exception:
        anio,mes=hoy.year,hoy.month
    q=request.args.get("q","").strip()

    con=db(); cur=con.cursor()
    cur.execute("""
      SELECT o.comprobante_numero AS factura,o.fecha_comprobante AS fecha,c.nombre,
             'Reparación' AS origen,o.numero_orden AS referencia,
             COALESCE(o.comprobante_total,o.presupuesto,0) AS total,
             o.numero_orden AS orden_id,NULL::integer AS venta_id
      FROM ordenes o JOIN clientes c ON c.id=o.cliente_id
      WHERE o.comprobante_numero IS NOT NULL
        AND EXTRACT(YEAR FROM o.fecha_comprobante)=%s AND EXTRACT(MONTH FROM o.fecha_comprobante)=%s
        AND (%s='' OR o.comprobante_numero ILIKE %s OR o.numero_orden ILIKE %s OR c.nombre ILIKE %s)
      UNION ALL
      SELECT v.comprobante_numero,v.fecha,COALESCE(c.nombre,'Consumidor final'),
             'Venta',v.numero_venta,v.total,NULL::text,v.id
      FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id
      WHERE v.comprobante_numero IS NOT NULL
        AND EXTRACT(YEAR FROM v.fecha)=%s AND EXTRACT(MONTH FROM v.fecha)=%s
        AND (%s='' OR v.comprobante_numero ILIKE %s OR v.numero_venta ILIKE %s OR COALESCE(c.nombre,'') ILIKE %s)
      ORDER BY fecha DESC
    """,(anio,mes,q,f"%{q}%",f"%{q}%",f"%{q}%",anio,mes,q,f"%{q}%",f"%{q}%",f"%{q}%"))
    docs=cur.fetchall(); con.close()

    filas=""
    for d in docs:
        if d["origen"]=="Venta":
            acciones=f"<a href='/venta_comprobante/{d['venta_id']}' style='font-weight:bold;color:#2563eb'>Ver / enviar</a>"
        else:
            acciones=f"<a href='/imprimir_comprobante?numero={quote(str(d['orden_id']))}' target='_blank' style='font-weight:bold;color:#2563eb'>Ver / imprimir</a> · <a href='/entrega?numero={quote(str(d['orden_id']))}' style='font-weight:bold;color:#16a34a'>Enviar</a>"
        filas+=f"""<tr><td>{escape(str(d['fecha'].strftime('%d/%m/%Y %H:%M') if hasattr(d['fecha'],'strftime') else d['fecha']))}</td>
        <td><b>{escape(str(d['factura']))}</b></td><td>{escape(str(d['origen']))}</td><td>{escape(str(d['referencia']))}</td>
        <td>{escape(str(d.get('nombre') or '-'))}</td><td>$ {float(d.get('total') or 0):,.2f}</td><td>{acciones}</td></tr>"""

    nombres=["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Setiembre","Octubre","Noviembre","Diciembre"]
    opts_m="".join(f"<option value='{i}' {'selected' if i==mes else ''}>{nombres[i-1]}</option>" for i in range(1,13))
    opts_a="".join(f"<option value='{y}' {'selected' if y==anio else ''}>{y}</option>" for y in range(hoy.year-3,hoy.year+2))
    return html_layout("Facturación",card_html(f"""
      <div style='display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap'>
        <div><h2 style='margin:0'>📑 Facturación</h2><p style='color:#64748b'>Archivo mensual de facturas emitidas de reparaciones y ventas.</p></div>
        <a href='/' style='font-weight:bold;color:#2563eb'>🏠 Inicio</a>
      </div>
      <form method='get' style='display:flex;gap:8px;flex-wrap:wrap;margin:16px 0'>
        <select name='mes' style='padding:9px'>{opts_m}</select><select name='anio' style='padding:9px'>{opts_a}</select>
        <input name='q' value='{escape(q)}' placeholder='Factura, cliente, orden o venta' style='padding:9px;min-width:240px'>
        <button style='padding:9px 14px'>Buscar</button>
      </form>
      <div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse'>
      <tr style='background:#eff6ff'><th>Fecha</th><th>Factura</th><th>Origen</th><th>Referencia</th><th>Cliente</th><th>Total</th><th></th></tr>
      {filas or "<tr><td colspan='7' style='padding:18px;text-align:center;color:#64748b'>No hay facturas emitidas en este período.</td></tr>"}
      </table></div>
      <style>table td,table th{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left}}</style>
    """))


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
            COALESCE(SUM(COALESCE(comprobante_total,presupuesto)),0) AS facturado,
            COALESCE(SUM(cobrado),0) AS cobrado,
            COALESCE(SUM(costo_repuestos),0) AS costos,
            COALESCE(SUM(GREATEST(COALESCE(comprobante_total,presupuesto)-cobrado,0)),0) AS pendiente,
            COALESCE(SUM(COALESCE(comprobante_total,presupuesto)-costo_repuestos),0) AS margen,
            COUNT(*) AS trabajos
        FROM ordenes
        WHERE estado = 'Entregado'
          AND COALESCE(fecha_entregado, fecha_comprobante::date) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(fecha_entregado, fecha_comprobante::date))=%s
          AND EXTRACT(MONTH FROM COALESCE(fecha_entregado, fecha_comprobante::date))=%s
    """, (anio, mes))
    mes_data = cur.fetchone() or {}

    cur.execute("""
        SELECT COALESCE(SUM(COALESCE(comprobante_total,presupuesto)),0) AS facturado_anual
        FROM ordenes
        WHERE estado = 'Entregado'
          AND COALESCE(fecha_entregado, fecha_comprobante::date) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(fecha_entregado, fecha_comprobante::date))=%s
    """, (anio,))
    anual = float((cur.fetchone() or {}).get("facturado_anual") or 0)

    cur.execute("""
        SELECT EXTRACT(MONTH FROM COALESCE(fecha_entregado, fecha_comprobante::date))::int AS mes,
               COALESCE(SUM(COALESCE(comprobante_total,presupuesto)),0) AS facturado,
               COALESCE(SUM(costo_repuestos),0) AS costos,
               COALESCE(SUM(COALESCE(comprobante_total,presupuesto)-costo_repuestos),0) AS margen,
               COUNT(*) AS trabajos
        FROM ordenes
        WHERE estado = 'Entregado'
          AND COALESCE(fecha_entregado, fecha_comprobante::date) IS NOT NULL
          AND EXTRACT(YEAR FROM COALESCE(fecha_entregado, fecha_comprobante::date))=%s
        GROUP BY 1 ORDER BY 1
    """, (anio,))
    por_mes = {r['mes']: r for r in cur.fetchall()}
    cur.execute("SELECT COALESCE(SUM(total),0) total,COALESCE(SUM(costo_total),0) costos,COUNT(*) cantidad FROM ventas WHERE EXTRACT(YEAR FROM fecha)=%s AND EXTRACT(MONTH FROM fecha)=%s",(anio,mes))
    vm=cur.fetchone() or {}
    cur.execute("SELECT COALESCE(SUM(total),0) total FROM ventas WHERE EXTRACT(YEAR FROM fecha)=%s",(anio,))
    va=float((cur.fetchone() or {}).get("total") or 0)
    con.close()
    mes_data["facturado"]=float(mes_data.get("facturado") or 0)+float(vm.get("total") or 0)
    mes_data["cobrado"]=float(mes_data.get("cobrado") or 0)+float(vm.get("total") or 0)
    mes_data["costos"]=float(mes_data.get("costos") or 0)+float(vm.get("costos") or 0)
    mes_data["margen"]=float(mes_data.get("margen") or 0)+float(vm.get("total") or 0)-float(vm.get("costos") or 0)
    reparaciones_mes = int(mes_data.get("trabajos") or 0)
    ventas_mes_cantidad = int(vm.get("cantidad") or 0)
    anual += va
    # Ventas por mes para que el resumen anual separe reparaciones de ventas.
    con2=db(); cur2=con2.cursor()
    cur2.execute("""
        SELECT EXTRACT(MONTH FROM fecha)::int AS mes,
               COALESCE(SUM(total),0) AS facturado,
               COALESCE(SUM(costo_total),0) AS costos,
               COUNT(*) AS ventas
        FROM ventas
        WHERE EXTRACT(YEAR FROM fecha)=%s
        GROUP BY 1 ORDER BY 1
    """,(anio,))
    ventas_por_mes={r["mes"]:r for r in cur2.fetchall()}
    con2.close()

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
        v = ventas_por_mes.get(i, {})
        fact = float(r.get('facturado',0) or 0)+float(v.get('facturado',0) or 0)
        costos = float(r.get('costos',0) or 0)+float(v.get('costos',0) or 0)
        margen = fact-costos
        filas += f"<tr><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{nombres[i-1]}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(fact)}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(costos)}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{dinero(margen)}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{int(r.get('trabajos',0) or 0)}</td><td style='padding:10px;border-bottom:1px solid #e5e7eb'>{int(v.get('ventas',0) or 0)}</td></tr>"

    contenido = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <div><h2 style="margin:0;">💰 Finanzas</h2><p style="margin:5px 0 0;color:#64748b;">Resumen del período: reparaciones entregadas y ventas directas se muestran por separado, pero ambas integran la facturación total.</p></div>
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
      <a href="/finanzas_pendientes?anio={anio}&mes={mes}" style="text-decoration:none;color:inherit">
        <div style="background:white;border:1px solid #fecaca;border-radius:14px;padding:15px;cursor:pointer;">
          <small>Pendiente de cobrar · ver detalle</small>
          <div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('pendiente'))}</div>
        </div>
      </a>
      <div style="background:white;border:1px solid #c7d2fe;border-radius:14px;padding:15px;"><small>Ganancia estimada</small><div style="font-size:24px;font-weight:800;">{dinero(mes_data.get('margen'))}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:14px;padding:15px;"><small>🔧 Reparaciones entregadas</small><div style="font-size:24px;font-weight:800;">{reparaciones_mes}</div></div>
      <div style="background:white;border:1px solid #e5e7eb;border-radius:14px;padding:15px;"><small>🛒 Ventas realizadas</small><div style="font-size:24px;font-weight:800;">{ventas_mes_cantidad}</div></div>
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
      <table style="width:100%;border-collapse:collapse;min-width:620px;"><tr style="background:#eff6ff;text-align:left;"><th style="padding:10px">Mes</th><th style="padding:10px">Facturado</th><th style="padding:10px">Costos</th><th style="padding:10px">Ganancia est.</th><th style="padding:10px">Reparaciones</th><th style="padding:10px">Ventas</th></tr>{filas}</table>
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

    flash(f"Orden {numero_orden} creada correctamente.", "success")
    if enviar_ingreso and email:
        ok_email = enviar_email(
            destino=email, numero_orden=numero_orden, cliente=nombre, tipo=tipo, marca=marca,
            modelo=modelo, estado="Recibido en taller", presupuesto=0, tipo_mensaje="ingreso",
            token_aprobacion=token_aprobacion, presupuesto_aprobado=False, presupuesto_rechazado=False
        )
        if ok_email:
            flash(f"Email de ingreso enviado correctamente a {email}.", "success")
        else:
            flash("La orden se creó, pero el email no pudo enviarse.", "error")
    elif enviar_ingreso and not email:
        flash("La orden se creó, pero no se envió email porque el cliente no tiene correo.", "error")

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
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Respuesta del cliente</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for r in resultados:
        equipo = f"{r['tipo_equipo']} {r['marca']} {r['modelo']}"
        pres = "En diagnóstico" if float(r["presupuesto"] or 0) == 0 else f"${r['presupuesto']}"
        badge = estado_presupuesto_badge(r["estado"], r.get("presupuesto_aprobado"), r.get("presupuesto_rechazado"), r.get("fecha_aprobacion"), r.get("fecha_rechazo"))

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
        <th style="padding:12px; border-bottom:1px solid #dbeafe;">Respuesta del cliente</th>
        <th style="padding:12px; border-bottom:1px solid #dbeafe;"></th>
      </tr>
    """

    for o in ordenes:
        equipo = f"{o['tipo_equipo']} {o['marca']} {o['modelo']}"
        pres = "En diagnóstico" if float(o["presupuesto"] or 0) == 0 else f"${o['presupuesto']}"
        badge = estado_presupuesto_badge(o["estado"], o.get("presupuesto_aprobado"), o.get("presupuesto_rechazado"), o.get("fecha_aprobacion"), o.get("fecha_rechazo"))

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
                   o.token_aprobacion, o.presupuesto_aprobado, o.presupuesto_rechazado, o.fecha_aprobacion, o.fecha_rechazo,
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
        if not actual.get("presupuesto_aprobado") and not actual.get("presupuesto_rechazado"):
            nuevo_token = secrets.token_urlsafe(32)
            cur.execute(
                "UPDATE ordenes SET token_aprobacion=%s WHERE numero_orden=%s",
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
    cur.execute(
        """
        UPDATE ordenes
        SET estado=%s,
            diagnostico_tecnico=%s,
            presupuesto=%s,
            fecha_entregado = CASE
                WHEN %s = 'Entregado' THEN COALESCE(fecha_entregado, CURRENT_DATE)
                ELSE fecha_entregado
            END
        WHERE numero_orden=%s
        """,
        (estado or actual["estado"], diag, pres or 0, estado or actual["estado"], numero),
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

    flash(f"Orden {numero} actualizada correctamente.", "success")
    if enviar and info and info["email"]:
        ok_email = enviar_email(
            destino=info["email"], numero_orden=info["numero_orden"], cliente=info["nombre"],
            tipo=info["tipo_equipo"], marca=info["marca"], modelo=info["modelo"],
            estado=info["estado"], presupuesto=info["presupuesto"], tipo_mensaje="actualizacion",
            token_aprobacion=info["token_aprobacion"], presupuesto_aprobado=info["presupuesto_aprobado"],
            presupuesto_rechazado=info["presupuesto_rechazado"]
        )
        if ok_email:
            flash(f"Email enviado correctamente a {info['email']}.", "success")
        else:
            flash("La actualización se guardó, pero el email no pudo enviarse.", "error")
    elif enviar:
        flash("La actualización se guardó, pero el cliente no tiene email.", "error")

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

    ok_email = enviar_email(
        destino=info["email"], numero_orden=info["numero_orden"], cliente=info["nombre"],
        tipo=info["tipo_equipo"], marca=info["marca"], modelo=info["modelo"],
        estado=info["estado"], presupuesto=info["presupuesto"], tipo_mensaje="actualizacion",
        token_aprobacion=info["token_aprobacion"], presupuesto_aprobado=info["presupuesto_aprobado"],
        presupuesto_rechazado=info["presupuesto_rechazado"]
    )
    if ok_email:
        flash(f"Presupuesto enviado correctamente a {info['email']}.", "success")
    else:
        flash("No se pudo enviar el presupuesto por email.", "error")
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
    cur.execute("""SELECT o.*, c.nombre, c.telefono, c.email
                   FROM ordenes o JOIN clientes c ON c.id=o.cliente_id
                   WHERE o.numero_orden=%s""", (numero,))
    o = cur.fetchone()
    if not o:
        con.close()
        return html_layout("No encontrada", card_html("<h2>Orden no encontrada</h2>"))

    # Si ya existe, no permitimos generar ni modificar otro comprobante para la misma orden.
    if o.get("comprobante_numero"):
        con.close()
        total = o.get("comprobante_total") if o.get("comprobante_total") is not None else (o.get("presupuesto") or 0)
        forma = o.get("comprobante_forma_pago") or o.get("forma_pago") or "-"
        return html_layout("Comprobante", card_html(f"""
          <h2 style='margin-top:0'>🧾 Comprobante ya emitido</h2>
          <div style='background:#f0fdf4;border:1px solid #bbf7d0;padding:14px;border-radius:12px'>
            <strong>✅ Esta orden ya tiene comprobante.</strong><br>
            N.º: <strong>{escape(str(o['comprobante_numero']))}</strong><br>
            Total: <strong>$ {float(total or 0):,.2f}</strong><br>
            Forma de pago: <strong>{escape(str(forma))}</strong>
          </div>
          <p style='color:#64748b'>Para evitar duplicados, el sistema no permite generar un segundo comprobante para la misma orden.</p>
          <div style='display:flex;gap:10px;flex-wrap:wrap'>
            <a href='/imprimir_comprobante?numero={quote(numero)}' style='background:#334155;color:white;padding:11px 15px;border-radius:10px;text-decoration:none;font-weight:bold'>🖨️ Ver / imprimir</a>
            <a href='/entrega?numero={quote(numero)}' style='background:#16a34a;color:white;padding:11px 15px;border-radius:10px;text-decoration:none;font-weight:bold'>📲 Enviar / entrega</a>
            <a href='/ver_ordenes' style='padding:11px 5px'>Volver</a>
          </div>
        """))

    if request.method == "POST":
        forma = request.form.get("forma_pago", "").strip()
        try:
            total = float(request.form.get("total", "0").replace(",", "."))
        except Exception:
            total = float(o.get("presupuesto") or 0)

        token, comp = _asegurar_token_y_comprobante(cur, o)
        cur.execute("""
            UPDATE ordenes
            SET comprobante_forma_pago=%s,
                comprobante_total=%s,
                forma_pago=COALESCE(NULLIF(%s,''),forma_pago)
            WHERE numero_orden=%s
        """, (forma, total, forma, numero))
        con.commit(); con.close()
        flash(f"Comprobante {comp} generado y guardado correctamente por $ {total:,.2f}.", "success")
        return redirect(f"/comprobante?numero={quote(numero)}")

    total = o.get("presupuesto") or 0
    forma = o.get("forma_pago") or ""
    con.close()
    return html_layout("Comprobante", card_html(f"""
      <h2 style='margin-top:0'>🧾 Generar comprobante</h2>
      <p><b>Orden:</b> {escape(numero)} · <b>Cliente:</b> {escape(o['nombre'] or '-')}</p>
      <p><b>Equipo:</b> {escape(' '.join(filter(None,[o['tipo_equipo'],o['marca'],o['modelo']])) or '-')}</p>
      <div style='background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:10px;margin-bottom:14px'>
        ⚠️ Una vez generado, este comprobante quedará asociado a la orden y <strong>no se podrá generar otro</strong>.
      </div>
      <form method='post'>
        <input type='hidden' name='numero' value='{escape(numero)}'>
        <label><b>Total final de la venta</b></label><br>
        <input name='total' value='{total}' inputmode='decimal' required style='padding:10px;width:220px;margin:6px 0 14px;border:1px solid #d1d5db;border-radius:10px'><br>
        <label><b>Forma de pago</b></label><br>
        <select name='forma_pago' required style='padding:10px;width:240px;margin:6px 0 16px;border:1px solid #d1d5db;border-radius:10px'>
          {''.join(f"<option value='{x}' {'selected' if forma==x else ''}>{x}</option>" for x in ['Efectivo','Transferencia','Mercado Pago','Débito','Crédito','Otro'])}
        </select><br>
        <button style='background:#059669;color:white;border:0;padding:12px 18px;border-radius:10px;font-weight:800;cursor:pointer'>💾 Generar comprobante</button>
        <a href='/ver_ordenes' style='margin-left:12px'>Cancelar</a>
      </form>
    """))


@app.get("/imprimir_comprobante")
def imprimir_comprobante():
    if not session.get("login"):
        return redirect("/login")
    numero=request.args.get("numero","").strip()
    generado = request.args.get("generado") == "1"
    con=db(); cur=con.cursor()
    cur.execute("""SELECT o.*,c.nombre,c.telefono,c.email FROM ordenes o JOIN clientes c ON c.id=o.cliente_id WHERE o.numero_orden=%s""",(numero,))
    o=cur.fetchone()
    cur.execute("SELECT * FROM configuracion_empresa WHERE id=1"); emp=cur.fetchone()
    if not o:
        con.close(); return "Orden no encontrada",404
    if not o.get("comprobante_numero"):
        con.close()
        flash("Primero tenés que generar el comprobante.", "error")
        return redirect(f"/comprobante?numero={quote(numero)}")
    token = o.get("token_publico")
    comp = o.get("comprobante_numero")
    if not token:
        token = secrets.token_urlsafe(24)
        cur.execute("UPDATE ordenes SET token_publico=%s WHERE numero_orden=%s", (token, numero))
        con.commit()
    con.close()
    total=o.get('comprobante_total') if o.get('comprobante_total') is not None else (o['presupuesto'] or 0)
    forma=o.get('comprobante_forma_pago') or o.get('forma_pago') or '-'
    trabajo=o.get('diagnostico_tecnico') or o.get('falla_cliente') or 'Servicio técnico'
    fecha=o.get('fecha_comprobante') or datetime.datetime.now()
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(comp)}</title><style>@page{{size:A4;margin:16mm}}body{{font-family:Arial;color:#111;max-width:760px;margin:auto}}.head{{border-bottom:3px solid #111;padding-bottom:12px}}.box{{border:1px solid #ddd;border-radius:12px;padding:18px;margin-top:16px}}.r{{margin:7px 0}}button{{padding:10px 16px}}@media print{{button{{display:none}}}}</style></head><body>
      {("<div style='background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;padding:12px 14px;border-radius:10px;margin-bottom:14px;font-weight:bold'>✅ Comprobante generado correctamente y guardado en la orden.</div>" if generado else "")}
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
        token = orden.get("token_publico")
        if not token:
            token = secrets.token_urlsafe(24)
            cur.execute("UPDATE ordenes SET token_publico=%s WHERE numero_orden=%s", (token, numero))
        comprobante = orden.get("comprobante_numero")
        cur.execute("""
            UPDATE ordenes
            SET garantia_dias=%s,
                fecha_entregado=COALESCE(fecha_entregado, CURRENT_DATE),
                estado='Entregado'
            WHERE numero_orden=%s
        """, (garantia_dias, numero))
        con.commit(); con.close()
        url_publica = f"{BASE_URL or request.url_root.rstrip('/')}/documento/{token}"

        if accion in ("email", "imprimir", "whatsapp") and not comprobante:
            flash("La entrega quedó marcada, pero primero tenés que generar el comprobante antes de enviarlo o imprimirlo.", "error")
            return redirect(f"/comprobante?numero={quote(numero)}")

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
                flash(f"Comprobante y garantía enviados correctamente a {orden2['email']}.", "success")
            except Exception as e:
                print("Error envío entrega:", e)
                flash("La entrega quedó guardada, pero el email no pudo enviarse.", "error")
            return redirect(f"/entrega?numero={numero}")

        if accion == "imprimir":
            return redirect(f"/imprimir_entrega?numero={numero}&guardado=1")
        if accion == "whatsapp":
            orden2 = _buscar_entrega_por_numero(numero)
            tel = ''.join(ch for ch in str(orden2['telefono'] or '') if ch.isdigit())
            if tel and not tel.startswith('598'):
                tel = '598' + tel.lstrip('0')
            texto = f"Hola {orden2['nombre']}, tu equipo ya fue entregado por NR Tech. Orden {numero}. Comprobante {comprobante}. Garantía: {garantia_dias} días. Podés ver tu comprobante, QR y garantía acá: {url_publica}"
            destino = f"https://wa.me/{tel}?text={quote(texto)}" if tel else f"https://wa.me/?text={quote(texto)}"
            return redirect(destino)
        flash(f"Entrega de {numero} guardada correctamente.", "success")
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
    guardado = request.args.get("guardado") == "1"
    con = db(); cur = con.cursor()
    cur.execute("""SELECT o.*, c.nombre FROM ordenes o JOIN clientes c ON o.cliente_id=c.id WHERE o.numero_orden=%s""", (numero,))
    x = cur.fetchone()
    if not x:
        con.close(); return "Orden no encontrada", 404
    token, comprobante = _asegurar_token_y_comprobante(cur, x); con.commit(); con.close()
    cfg = _config_empresa()
    fecha = x['fecha_entregado'] or datetime.date.today(); garantia=int(x['garantia_dias'] or 30); vence=fecha+datetime.timedelta(days=garantia)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{comprobante}</title><style>@page{{size:A4;margin:16mm}}body{{font-family:Arial;color:#111;max-width:760px;margin:auto}}.box{{border:1px solid #ddd;border-radius:12px;padding:18px}}.row{{margin:8px 0}}img{{width:150px;height:150px}}@media print{{button{{display:none}}}}</style></head><body>
      {("<div style='background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;padding:12px 14px;border-radius:10px;margin-bottom:14px;font-weight:bold'>✅ Entrega guardada correctamente. Comprobante y garantía listos para imprimir.</div>" if guardado else "")}
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
      WHERE estado <> 'Convertida'
      ORDER BY CASE WHEN estado='Completada' THEN 0 ELSE 1 END, id DESC
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

    # Una vez convertida, ya no pertenece a Autoregistro.
    if s.get("estado") == "Convertida":
        con.close()
        flash("Esta solicitud ya fue convertida en orden y salió de Autoregistro.", "success")
        return redirect("/ver_ordenes")

    if request.method == "POST":
        accion = request.form.get("accion", "guardar")

        # El técnico puede corregir/completar todos los datos antes de crear la orden.
        datos = {
            "nombre": request.form.get("nombre", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "email": request.form.get("email", "").strip(),
            "cedula": request.form.get("cedula", "").strip(),
            "tipo_equipo": request.form.get("tipo_equipo", "").strip(),
            "marca": request.form.get("marca", "").strip(),
            "modelo": request.form.get("modelo", "").strip(),
            "numero_serie": request.form.get("numero_serie", "").strip(),
            "imei": request.form.get("imei", "").strip(),
            "falla_cliente": request.form.get("falla_cliente", "").strip(),
            "accesorios": request.form.get("accesorios", "").strip(),
            "bloqueo_tipo": request.form.get("bloqueo_tipo", "Sin bloqueo").strip(),
            "clave_bloqueo": request.form.get("clave_bloqueo", "").strip(),
            "patron_bloqueo": request.form.get("patron_bloqueo", "").strip(),
        }

        cur.execute("""
          UPDATE solicitudes_ingreso SET
            nombre=%s, telefono=%s, email=%s, cedula=%s,
            tipo_equipo=%s, marca=%s, modelo=%s, numero_serie=%s, imei=%s,
            falla_cliente=%s, accesorios=%s, bloqueo_tipo=%s, clave_bloqueo=%s,
            patron_bloqueo=%s
          WHERE id=%s
        """, (
            datos["nombre"], datos["telefono"], datos["email"], datos["cedula"],
            datos["tipo_equipo"], datos["marca"], datos["modelo"], datos["numero_serie"], datos["imei"],
            datos["falla_cliente"], datos["accesorios"], datos["bloqueo_tipo"],
            datos["clave_bloqueo"], datos["patron_bloqueo"], sid
        ))

        if accion == "guardar":
            con.commit(); con.close()
            flash("Datos de la solicitud actualizados correctamente.", "success")
            return redirect(f"/revisar_solicitud/{sid}")

        if accion != "crear":
            con.rollback(); con.close()
            return redirect(f"/revisar_solicitud/{sid}")

        if not datos["nombre"] or not datos["telefono"] or not datos["tipo_equipo"] or not datos["falla_cliente"]:
            con.rollback(); con.close()
            flash("Antes de crear la orden completá al menos nombre, teléfono, tipo de equipo y falla.", "error")
            return redirect(f"/revisar_solicitud/{sid}")

        cliente_id = None
        if datos["telefono"]:
            cur.execute("SELECT id FROM clientes WHERE telefono=%s LIMIT 1", (datos["telefono"],))
            r = cur.fetchone()
            cliente_id = r["id"] if r else None
        if not cliente_id and datos["email"]:
            cur.execute("SELECT id FROM clientes WHERE email=%s LIMIT 1", (datos["email"],))
            r = cur.fetchone()
            cliente_id = r["id"] if r else None

        if cliente_id:
            cur.execute("""
              UPDATE clientes SET nombre=%s,telefono=%s,email=%s,cedula=%s,acepta_promociones=%s
              WHERE id=%s
            """, (
                datos["nombre"], datos["telefono"], datos["email"], datos["cedula"],
                bool(s.get("acepta_promociones")), cliente_id
            ))
        else:
            cur.execute("""
              INSERT INTO clientes(nombre,telefono,email,cedula,acepta_promociones)
              VALUES(%s,%s,%s,%s,%s) RETURNING id
            """, (
                datos["nombre"], datos["telefono"], datos["email"], datos["cedula"],
                bool(s.get("acepta_promociones"))
            ))
            cliente_id = cur.fetchone()["id"]

        token_aprobacion = secrets.token_urlsafe(32)
        cur.execute("""
          INSERT INTO ordenes(
            numero_orden,cliente_id,tipo_equipo,marca,modelo,numero_serie,imei,
            estado_general,falla_cliente,diagnostico_tecnico,fecha_ingreso,estado,presupuesto,observaciones,
            token_aprobacion,presupuesto_aprobado,presupuesto_rechazado,accesorios,bloqueo_tipo,clave_bloqueo,patron_bloqueo
          )
          VALUES('',%s,%s,%s,%s,%s,%s,'',%s,'',CURRENT_DATE,'Recibido en taller',0,'',%s,FALSE,FALSE,%s,%s,%s,%s)
          RETURNING id
        """, (
            cliente_id, datos["tipo_equipo"], datos["marca"], datos["modelo"],
            datos["numero_serie"], datos["imei"], datos["falla_cliente"],
            token_aprobacion, datos["accesorios"], datos["bloqueo_tipo"],
            datos["clave_bloqueo"], datos["patron_bloqueo"]
        ))

        oid = cur.fetchone()["id"]
        numero = f"NR-{datetime.datetime.now().year}-{oid:04d}"
        cur.execute("UPDATE ordenes SET numero_orden=%s WHERE id=%s", (numero, oid))
        cur.execute("UPDATE solicitudes_ingreso SET estado='Convertida', fecha_revision=NOW() WHERE id=%s", (sid,))
        con.commit(); con.close()

        flash(f"Orden {numero} creada correctamente. La solicitud salió de Autoregistro.", "success")
        return redirect(f"/editar?numero={quote(numero)}")

    con.close()

    def e(campo):
        return escape(str(s.get(campo) or ""))

    bloqueo_actual = str(s.get("bloqueo_tipo") or "Sin bloqueo")
    opciones_bloqueo = "".join(
        f"<option value='{x}' {'selected' if bloqueo_actual==x else ''}>{x}</option>"
        for x in ["Sin bloqueo", "PIN / clave", "Patrón"]
    )

    return html_layout("Revisar solicitud", card_html(f"""
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <div>
          <h2 style="margin:0">✏️ Revisar y completar solicitud #{sid}</h2>
          <p style="color:#64748b;margin:5px 0 0">Corregí o completá lo que el cliente no supo ingresar antes de crear la orden.</p>
        </div>
        <a href="/solicitudes_ingreso" style="font-weight:bold;color:#2563eb">← Autoregistro</a>
      </div>

      <form method="post" style="margin-top:18px">
        <div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin-bottom:14px">
          <h3 style="margin-top:0">👤 Cliente</h3>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px">
            <div><label>Nombre *</label><input name="nombre" required value="{e('nombre')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Teléfono *</label><input name="telefono" required value="{e('telefono')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Email</label><input name="email" type="email" value="{e('email')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Cédula</label><input name="cedula" value="{e('cedula')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
          </div>
        </div>

        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:14px;margin-bottom:14px">
          <h3 style="margin-top:0">📱 Equipo</h3>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px">
            <div><label>Tipo *</label><input name="tipo_equipo" required value="{e('tipo_equipo')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Marca</label><input name="marca" value="{e('marca')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Modelo</label><input name="modelo" value="{e('modelo')}" placeholder="Podés completarlo vos" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>N.º serie</label><input name="numero_serie" value="{e('numero_serie')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>IMEI</label><input name="imei" value="{e('imei')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
          </div>
          <label style="display:block;margin-top:10px">Falla declarada *</label>
          <textarea name="falla_cliente" required rows="3" style="width:100%;padding:10px;box-sizing:border-box">{e('falla_cliente')}</textarea>
          <label style="display:block;margin-top:10px">Accesorios entregados</label>
          <input name="accesorios" value="{e('accesorios')}" style="width:100%;padding:10px;box-sizing:border-box">
        </div>

        <details style="padding:14px;border:1px solid #e5e7eb;border-radius:14px;margin-bottom:14px">
          <summary style="font-weight:bold;cursor:pointer">🔐 Datos de desbloqueo</summary>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:12px">
            <div><label>Tipo</label><select name="bloqueo_tipo" style="width:100%;padding:10px">{opciones_bloqueo}</select></div>
            <div><label>PIN / clave</label><input name="clave_bloqueo" value="{e('clave_bloqueo')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
            <div><label>Patrón</label><input name="patron_bloqueo" value="{e('patron_bloqueo')}" style="width:100%;padding:10px;box-sizing:border-box"></div>
          </div>
        </details>

        <div style="background:#f0fdf4;border:1px solid #bbf7d0;padding:12px;border-radius:12px;margin-bottom:14px">
          <b>Promociones WhatsApp:</b> {"Aceptadas por el cliente" if s.get("acepta_promociones") else "No aceptadas"}
        </div>

        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button name="accion" value="guardar" style="background:#475569;color:white;border:0;padding:12px 16px;border-radius:10px;font-weight:bold">💾 Guardar cambios</button>
          <button name="accion" value="crear" style="background:#16a34a;color:white;border:0;padding:12px 16px;border-radius:10px;font-weight:bold">✅ Confirmar y crear orden</button>
          <a href="/solicitudes_ingreso" style="padding:12px">Cancelar</a>
        </div>
      </form>
    """))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)