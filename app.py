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
        observaciones TEXT
    );
    """)

    con.commit()
    con.close()


def enviar_email(destino, numero_orden, cliente, tipo, marca, modelo, estado, presupuesto, tipo_mensaje="actualizacion"):
    if not destino or not REMITENTE_EMAIL or not CONTRASENA_APP:
        print("Email no enviado: faltan GMAIL_USER o GMAIL_APP_PASSWORD.")
        return

    try:
        pres = float(presupuesto or 0)
    except:
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
        f"Presupuesto: {presupuesto_mostrar}\n\n"
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

    return """
    <h2>Base de datos reiniciada</h2>
    <p>Las tablas fueron borradas y creadas nuevamente.</p>
    <a href="/">Volver</a>
    """

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return """
        <h3>Login NR Tech</h3>
        <form method="post">
          Usuario: <input name="user"><br>
          Contraseña: <input name="pass" type="password"><br>
          <button>Entrar</button>
        </form>
        """

    user = request.form.get("user", "").strip()
    password = request.form.get("pass", "").strip()

    if user == USER and password == PASS:
        session["login"] = True
        return redirect("/")
    else:
        return "<p>Usuario o contraseña incorrectos</p><p><a href='/login'>Volver</a></p>"


@app.get("/logout")
def logout():
    session.pop("login", None)
    return redirect("/login")


@app.get("/")
def home():
    if not session.get("login"):
        return redirect("/login")

    return """
    <h2>NR Tech - Taller</h2>
    <ul>
      <li><a href="/crear">Crear orden</a></li>
      <li><a href="/buscar">Buscar orden</a></li>
      <li><a href="/ver_ordenes">Ver todas las órdenes</a></li>
      <li><a href="/logout">Salir</a></li>
    </ul>
    """


@app.route("/crear", methods=["GET", "POST"])
def crear():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        return """
        <h3>Crear orden</h3>
        <form method="post">
          Nombre: <input name="nombre"><br>
          Teléfono: <input name="telefono"><br>
          Email: <input name="email"><br><br>

          Tipo equipo: <input name="tipo"><br>
          Marca: <input name="marca"><br>
          Modelo: <input name="modelo"><br>
          N° serie: <input name="numero_serie"><br>
          IMEI: <input name="imei"><br>

          Estado general: <input name="estado_general"><br>
          Falla cliente: <input name="falla_cliente"><br>

          <button type="submit">Guardar</button>
        </form>

        <p><a href="/">Volver</a></p>
        """

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

    cur.execute(
        """
        INSERT INTO ordenes(
            numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
            estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado, presupuesto, observaciones
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,%s)
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
        ),
    )

    oid = cur.fetchone()["id"]
    anio = datetime.datetime.now().year
    numero_orden = f"NR-{anio}-{oid:04d}"

    cur.execute(
        "UPDATE ordenes SET numero_orden=%s WHERE id=%s",
        (numero_orden, oid),
    )

    con.commit()
    con.close()

    print("Intentando enviar email de ingreso a:", email)
    enviar_email(
        destino=email,
        numero_orden=numero_orden,
        cliente=nombre,
        tipo=tipo,
        marca=marca,
        modelo=modelo,
        estado="Recibido en taller",
        presupuesto=0,
        tipo_mensaje="ingreso"
    )

    return f"""
    <h3>Orden creada</h3>
    Numero: {numero_orden}
    <p><a href="/buscar?q={numero_orden}">Ver orden</a></p>
    <p><a href="/">Volver</a></p>
    """


@app.get("/buscar")
def buscar():
    if not session.get("login"):
        return redirect("/login")

    q = request.args.get("q", "").strip()

    if not q:
        return """
        <h3>Buscar orden</h3>
        <form>
          Buscar por numero, nombre, telefono, email, imei o serie<br><br>
          <input name="q">
          <button>Buscar</button>
        </form>
        <p><a href="/">Volver</a></p>
        """

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
        return "Sin resultados"

    html = """
    <h3>Resultados</h3>
    <table border=1 cellpadding=6>
    <tr>
      <th>Numero</th>
      <th>Cliente</th>
      <th>Equipo</th>
      <th>Estado</th>
      <th>Presupuesto</th>
      <th></th>
    </tr>
    """

    for r in resultados:
        equipo = f"{r['tipo_equipo']} {r['marca']} {r['modelo']}"
        pres = "En diagnóstico" if float(r["presupuesto"] or 0) == 0 else f"${r['presupuesto']}"

        html += f"""
        <tr>
          <td>{r['numero_orden']}</td>
          <td>{r['nombre']}</td>
          <td>{equipo}</td>
          <td>{r['estado']}</td>
          <td>{pres}</td>
          <td><a href="/actualizar?numero={r['numero_orden']}">Actualizar</a></td>
        </tr>
        """

    html += "</table><p><a href='/'>Volver</a></p>"
    return html


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
    <h2>Todas las ordenes</h2>
    <table border=1 cellpadding=6>
    <tr>
      <th>Numero</th>
      <th>Cliente</th>
      <th>Equipo</th>
      <th>Estado</th>
      <th>Presupuesto</th>
      <th></th>
    </tr>
    """

    for o in ordenes:
        equipo = f"{o['tipo_equipo']} {o['marca']} {o['modelo']}"
        pres = "En diagnóstico" if float(o["presupuesto"] or 0) == 0 else f"${o['presupuesto']}"

        html += f"""
        <tr>
          <td>{o['numero_orden']}</td>
          <td>{o['nombre']}</td>
          <td>{equipo}</td>
          <td>{o['estado']}</td>
          <td>{pres}</td>
          <td><a href="/actualizar?numero={o['numero_orden']}">Actualizar</a></td>
        </tr>
        """

    html += "</table><p><a href='/'>Volver</a></p>"
    return html


@app.route("/actualizar", methods=["GET", "POST"])
def actualizar():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        numero = request.args.get("numero", "").strip()

        return f"""
        <h3>Actualizar orden</h3>
        <form method="post">
          Numero
          <input name="numero" value="{numero}"><br><br>

          Estado
          <select name="estado">
            <option value="">-- elegir --</option>
            <option value="En diagnóstico">En diagnóstico</option>
            <option value="Esperando aprobación">Esperando aprobación</option>
            <option value="Esperando repuesto">Esperando repuesto</option>
            <option value="En reparación">En reparación</option>
            <option value="Listo para retirar">Listo para retirar</option>
            <option value="Entregado">Entregado</option>
          </select>
          <br><br>

          Diagnostico
          <input name="diag"><br>

          Presupuesto
          <input name="presupuesto"><br>

          <button>Guardar</button>
        </form>

        <p><a href="/">Volver</a></p>
        """

    numero = request.form.get("numero", "").strip()
    estado = request.form.get("estado", "").strip()
    diag = request.form.get("diag", "").strip()
    pres = request.form.get("presupuesto", "").strip()

    con = db()
    cur = con.cursor()

    if estado:
        cur.execute(
            "UPDATE ordenes SET estado=%s WHERE numero_orden=%s",
            (estado, numero),
        )

    if diag:
        cur.execute(
            "UPDATE ordenes SET diagnostico_tecnico=%s WHERE numero_orden=%s",
            (diag, numero),
        )

    if pres:
        cur.execute(
            "UPDATE ordenes SET presupuesto=%s WHERE numero_orden=%s",
            (pres, numero),
        )

    cur.execute(
        """
        SELECT o.numero_orden, c.nombre, c.email, o.tipo_equipo, o.marca, o.modelo,
               o.estado, o.presupuesto
        FROM ordenes o
        JOIN clientes c ON o.cliente_id=c.id
        WHERE o.numero_orden=%s
        """,
        (numero,),
    )
    info = cur.fetchone()

    con.commit()
    con.close()

    print("INFO UPDATE:", info)

    if info and info["email"]:
        print("Intentando enviar actualización a:", info["email"])
        enviar_email(
            destino=info["email"],
            numero_orden=info["numero_orden"],
            cliente=info["nombre"],
            tipo=info["tipo_equipo"],
            marca=info["marca"],
            modelo=info["modelo"],
            estado=info["estado"],
            presupuesto=info["presupuesto"],
            tipo_mensaje="actualizacion"
        )
    else:
        print("No se pudo enviar email de actualización: falta email o info.")

    return redirect(f"/buscar?q={numero}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)