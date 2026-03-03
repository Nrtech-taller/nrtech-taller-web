import sqlite3
from datetime import datetime


# =========================
# CONFIG
# =========================
DB_NAME = "taller.db"

REMITENTE_EMAIL = "info.nrsolucionestecno@gmail.com"
CONTRASENA_APP = "tztynfdwczkbbode"
WHATSAPP_LINK = "https://wa.me/59898705065"  # WhatsApp NR Tech


# =========================
# DB
# =========================
conexion = sqlite3.connect(DB_NAME)
cursor = conexion.cursor()


def crear_tablas():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        email TEXT UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_orden TEXT UNIQUE,
        cliente_id INTEGER,
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
        presupuesto REAL DEFAULT 0,
        observaciones TEXT,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_orden TEXT,
        campo TEXT,
        valor_anterior TEXT,
        valor_nuevo TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conexion.commit()


def asegurar_numero_orden():
    """
    Si existe alguna orden vieja sin numero_orden, se lo genera.
    """
    cursor.execute("SELECT id FROM ordenes WHERE numero_orden IS NULL OR numero_orden = ''")
    filas = cursor.fetchall()
    if not filas:
        return

    anio = datetime.now().year
    for (oid,) in filas:
        nro = f"NR-{anio}-{oid:04d}"
        cursor.execute("UPDATE ordenes SET numero_orden=? WHERE id=?", (nro, oid))
    conexion.commit()


# =========================
# EMAIL (HTML + LOGO INLINE)
# =========================
def enviar_email(destino, numero_orden, cliente, tipo, marca, modelo, estado, presupuesto):
    import smtplib
    from email.message import EmailMessage
    from email.utils import formataddr
    import mimetypes
    from pathlib import Path

    # Presupuesto
    try:
        pres = float(presupuesto)
    except:
        pres = 0.0
    presupuesto_mostrar = "En diagnóstico" if pres == 0 else f"${pres}"

    asunto = f"Actualización de orden {numero_orden} – NR Tech"

    # Logo local inline
    logo_path = Path(__file__).with_name("logo_nrtech.png")
    logo_cid = "logo_nrtech" if logo_path.exists() else None

    # === HTML (claro + logo grande + linea + boton pro) ===
    cuerpo_html = f"""
    <html>
      <body style="margin:0; padding:0; background:#f6f8fb; font-family: Arial, sans-serif; color:#111827;">
        <div style="max-width:720px; margin:0 auto; padding:22px;">

          <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:16px; overflow:hidden; box-shadow:0 10px 30px rgba(17,24,39,0.08);">

            <!-- Header -->
            <div style="background:linear-gradient(135deg,#38bdf8,#3b82f6); padding:40px 22px; text-align:center;">
              {("<img src='cid:logo_nrtech' alt='NR Tech' style='max-height:180px; width:auto; display:block; margin:0 auto;' />" if logo_cid else "")}
              <div style="width:60px; height:3px; background:rgba(255,255,255,0.6); margin:18px auto 0 auto; border-radius:10px;"></div>
            </div>

            <!-- Body -->
            <div style="padding:18px 22px 10px 22px;">
              <p style="margin:0 0 12px 0; font-size:14px;">
                Hola <strong>{cliente}</strong>, te informamos una actualización de tu orden:
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

            <!-- Footer -->
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

    # Adjuntar logo inline si existe
    if logo_cid and logo_path.exists():
        ctype, _ = mimetypes.guess_type(str(logo_path))
        if ctype is None:
            ctype = "image/png"
        maintype, subtype = ctype.split("/", 1)
        with open(logo_path, "rb") as f:
            img_data = f.read()
        msg.get_payload()[1].add_related(img_data, maintype=maintype, subtype=subtype, cid=logo_cid)

    try:
        print("Conectando a Gmail...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as smtp:
            print("Iniciando sesión...")
            smtp.login(REMITENTE_EMAIL, CONTRASENA_APP)
            print("Enviando email...")
            smtp.send_message(msg)
        print("Email enviado al cliente correctamente.")
    except Exception as e:
        print("Error al enviar email:", e)


# =========================
# FUNCIONES SISTEMA
# =========================
def crear_orden():
    nombre = input("Nombre cliente: ").strip()
    telefono = input("Telefono: ").strip()
    email = input("Email: ").strip()

    # cliente (si ya existe, lo reutilizamos)
    cursor.execute("SELECT id, nombre, email FROM clientes WHERE email = ?", (email,))
    cli = cursor.fetchone()

    if cli:
        cliente_id = cli[0]
    else:
        cursor.execute(
            "INSERT INTO clientes (nombre, telefono, email) VALUES (?, ?, ?)",
            (nombre, telefono, email)
        )
        conexion.commit()
        cliente_id = cursor.lastrowid

    tipo = input("Tipo equipo: ").strip()
    marca = input("Marca: ").strip()
    modelo = input("Modelo: ").strip()
    numero_serie = input("Numero de serie: ").strip()
    imei = input("IMEI (si aplica): ").strip()
    estado_general = input("Estado general del equipo: ").strip()
    falla_cliente = input("Falla segun cliente: ").strip()
    diagnostico_tecnico = input("Diagnostico tecnico (opcional): ").strip()

    estado = "Recibido en taller"
    presupuesto = 0.0
    observaciones = ""
    fecha = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO ordenes (
        numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
        estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado, presupuesto, observaciones
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "", cliente_id, tipo, marca, modelo, numero_serie, imei,
        estado_general, falla_cliente, diagnostico_tecnico, fecha, estado, presupuesto, observaciones
    ))
    conexion.commit()

    oid = cursor.lastrowid
    anio = datetime.now().year
    numero_orden = f"NR-{anio}-{oid:04d}"

    cursor.execute("UPDATE ordenes SET numero_orden=? WHERE id=?", (numero_orden, oid))
    conexion.commit()

    print("\nOrden creada correctamente.")
    print("Numero profesional:", numero_orden)

    enviar_email(
        destino=email,
        numero_orden=numero_orden,
        cliente=nombre,
        tipo=tipo,
        marca=marca,
        modelo=modelo,
        estado=estado,
        presupuesto=presupuesto
    )


def ver_ordenes():
    cursor.execute("""
    SELECT ordenes.numero_orden,
           clientes.nombre,
           ordenes.tipo_equipo,
           ordenes.marca,
           ordenes.modelo,
           ordenes.estado,
           ordenes.presupuesto
    FROM ordenes
    JOIN clientes ON ordenes.cliente_id = clientes.id
    ORDER BY ordenes.id DESC
    """)
    ordenes = cursor.fetchall()

    print("\n--- LISTADO COMPLETO ---")
    if not ordenes:
        print("No hay órdenes registradas.")
        return

    for o in ordenes:
        presupuesto_mostrar = "En diagnóstico" if float(o[6]) == 0 else f"${o[6]}"
        print(f"""
Numero: {o[0]}
Cliente: {o[1]}
Equipo: {o[2]} {o[3]} {o[4]}
Estado: {o[5]}
Presupuesto: {presupuesto_mostrar}
--------------------------
""")


def actualizar_estado_diagnostico_presupuesto():
    numero = input("Numero de orden (ej: NR-2026-0001): ").strip()

    cursor.execute("""
    SELECT clientes.nombre, clientes.email, ordenes.tipo_equipo, ordenes.marca, ordenes.modelo,
           ordenes.estado, ordenes.diagnostico_tecnico, ordenes.presupuesto
    FROM ordenes
    JOIN clientes ON ordenes.cliente_id = clientes.id
    WHERE ordenes.numero_orden = ?
    """, (numero,))
    r = cursor.fetchone()

    if not r:
        print("No se encontró la orden.")
        return

    cliente_nombre, cliente_email, tipo, marca, modelo, estado_actual, diag_actual, pres_actual = r

    print(f"Estado actual: {estado_actual}")
    print(f"Diagnóstico actual: {diag_actual}")
    print(f"Presupuesto actual: {pres_actual if float(pres_actual) != 0 else 'En diagnóstico'}")

    nuevo_estado = input("Nuevo estado (Enter para no cambiar): ").strip()
    nuevo_diag = input("Nuevo diagnóstico técnico (Enter para no cambiar): ").strip()
    nuevo_presupuesto = input("Nuevo presupuesto (Enter para no cambiar): ").strip()

    if nuevo_estado != "":
        cursor.execute("UPDATE ordenes SET estado = ? WHERE numero_orden = ?", (nuevo_estado, numero))
        cursor.execute("""
            INSERT INTO historial (numero_orden, campo, valor_anterior, valor_nuevo)
            VALUES (?, ?, ?, ?)
        """, (numero, "estado", estado_actual, nuevo_estado))
        estado_actual = nuevo_estado

    if nuevo_diag != "":
        cursor.execute("UPDATE ordenes SET diagnostico_tecnico = ? WHERE numero_orden = ?", (nuevo_diag, numero))
        cursor.execute("""
            INSERT INTO historial (numero_orden, campo, valor_anterior, valor_nuevo)
            VALUES (?, ?, ?, ?)
        """, (numero, "diagnostico_tecnico", diag_actual, nuevo_diag))
        diag_actual = nuevo_diag

    if nuevo_presupuesto != "":
        try:
            pres_nuevo = float(nuevo_presupuesto)
        except:
            pres_nuevo = 0.0
        cursor.execute("UPDATE ordenes SET presupuesto = ? WHERE numero_orden = ?", (pres_nuevo, numero))
        cursor.execute("""
            INSERT INTO historial (numero_orden, campo, valor_anterior, valor_nuevo)
            VALUES (?, ?, ?, ?)
        """, (numero, "presupuesto", str(pres_actual), str(pres_nuevo)))
        pres_actual = pres_nuevo

    conexion.commit()
    print("Datos actualizados correctamente.")

    enviar_email(
        destino=cliente_email,
        numero_orden=numero,
        cliente=cliente_nombre,
        tipo=tipo,
        marca=marca,
        modelo=modelo,
        estado=estado_actual,
        presupuesto=pres_actual
    )


def buscar_orden():
    numero = input("Ingresá el numero de orden (ej: NR-2026-0001): ").strip()

    cursor.execute("""
    SELECT ordenes.numero_orden,
           clientes.nombre,
           clientes.telefono,
           clientes.email,
           ordenes.tipo_equipo,
           ordenes.marca,
           ordenes.modelo,
           ordenes.numero_serie,
           ordenes.imei,
           ordenes.estado_general,
           ordenes.falla_cliente,
           ordenes.diagnostico_tecnico,
           ordenes.estado,
           ordenes.presupuesto,
           ordenes.fecha_ingreso
    FROM ordenes
    JOIN clientes ON ordenes.cliente_id = clientes.id
    WHERE ordenes.numero_orden = ?
    """, (numero,))
    x = cursor.fetchone()

    if not x:
        print("No se encontró la orden con ese número.")
        return

    presupuesto_mostrar = "En diagnóstico" if float(x[13]) == 0 else f"${x[13]}"
    print("\n--- DETALLE ORDEN ---")
    print(f"Numero: {x[0]}")
    print(f"Cliente: {x[1]}")
    print(f"Telefono: {x[2]}")
    print(f"Email: {x[3]}")
    print(f"Equipo: {x[4]} {x[5]} {x[6]}")
    print(f"Número de serie: {x[7]}")
    print(f"IMEI: {x[8]}")
    print(f"Estado general: {x[9]}")
    print(f"Falla según cliente: {x[10]}")
    print(f"Diagnóstico técnico: {x[11]}")
    print(f"Estado actual: {x[12]}")
    print(f"Presupuesto: {presupuesto_mostrar}")
    print(f"Fecha ingreso: {x[14]}")
    print("--------------------------")


def ver_historial():
    numero = input("Numero de orden para ver historial: ").strip()
    cursor.execute("""
        SELECT campo, valor_anterior, valor_nuevo, fecha
        FROM historial
        WHERE numero_orden = ?
        ORDER BY fecha
    """, (numero,))
    cambios = cursor.fetchall()

    if not cambios:
        print("No hay historial para esta orden.")
        return

    print(f"\n--- HISTORIAL ORDEN {numero} ---")
    for campo, anterior, nuevo, fecha in cambios:
        print(f"{fecha}: {campo} → {anterior} | {nuevo}")
    print("----------------------------")


def reporte_ingresos():
    print("\n--- INGRESO TOTAL (solo 'Presupuesto aprobado') ---")
    cursor.execute("SELECT SUM(presupuesto) FROM ordenes WHERE estado = 'Presupuesto aprobado'")
    total = cursor.fetchone()[0] or 0
    print(f"Ingreso total: ${total}")

    print("\n--- INGRESO POR MES ---")
    cursor.execute("""
    SELECT strftime('%Y-%m', fecha_ingreso) AS mes, SUM(presupuesto)
    FROM ordenes
    WHERE estado = 'Presupuesto aprobado'
    GROUP BY mes
    """)
    for mes, total_mes in cursor.fetchall():
        print(f"{mes}: ${total_mes}")

    print("\n--- INGRESO POR CLIENTE ---")
    cursor.execute("""
    SELECT clientes.nombre, SUM(ordenes.presupuesto)
    FROM ordenes
    JOIN clientes ON ordenes.cliente_id = clientes.id
    WHERE ordenes.estado = 'Presupuesto aprobado'
    GROUP BY clientes.nombre
    """)
    for cliente, total_cliente in cursor.fetchall():
        print(f"{cliente}: ${total_cliente}")


# =========================
# INIT
# =========================
crear_tablas()
asegurar_numero_orden()


# =========================
# MENU
# =========================
while True:
    print("\n--- SISTEMA TALLER ---")
    print("1 - Crear orden")
    print("2 - Ver ordenes")
    print("3 - Actualizar estado/diagnostico/presupuesto")
    print("4 - Buscar orden por numero")
    print("5 - Ver historial de orden")
    print("6 - Reporte de ingresos")
    print("7 - Salir")

    opcion = input("Elegir opcion: ").strip()

    if opcion == "1":
        crear_orden()
    elif opcion == "2":
        ver_ordenes()
    elif opcion == "3":
        actualizar_estado_diagnostico_presupuesto()
    elif opcion == "4":
        buscar_orden()
    elif opcion == "5":
        ver_historial()
    elif opcion == "6":
        reporte_ingresos()
    elif opcion == "7":
        break
    else:
        print("Opcion invalida")

conexion.close()
print("Sistema cerrado.")