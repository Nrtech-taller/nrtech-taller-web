from flask import Flask, request, redirect, session
import os
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = "nrtech_secret_key"

USER = "admin"
PASS = "N41043406@"

DATABASE_URL = os.environ.get("DATABASE_URL")


def db():
    # Render Postgres requiere ssl
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


# crear tablas al iniciar
init_db()

@app.route("/login", methods=["GET","POST"])
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

    user = request.form.get("user","").strip()
    password = request.form.get("pass","").strip()

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
    <h2>NR Tech - Taller (Web)</h2>
    <ul>
      <li><a href="/crear">Crear orden</a></li>
<li><a href="/buscar">Buscar orden</a></li>
<li><a href="/ver_ordenes">Ver todas las órdenes</a></li>
<li><a href="/actualizar">Actualizar orden</a></li>
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
          Falla segun cliente: <input name="falla_cliente"><br>
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

    # cliente
    cur.execute("SELECT id FROM clientes WHERE email=%s", (email,))
    row = cur.fetchone()

    if row:
        cliente_id = row["id"]
        # opcional: actualizar nombre/teléfono si cambian
        cur.execute(
            "UPDATE clientes SET nombre=%s, telefono=%s WHERE id=%s",
            (nombre, telefono, cliente_id)
        )
    else:
        cur.execute(
            "INSERT INTO clientes(nombre,telefono,email) VALUES(%s,%s,%s) RETURNING id",
            (nombre, telefono, email)
        )
        cliente_id = cur.fetchone()["id"]

    # orden (INSERT ... RETURNING id)
    cur.execute("""
      INSERT INTO ordenes(
        numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
        estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado, presupuesto, observaciones
      ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,%s)
      RETURNING id
    """, ("", cliente_id, tipo, marca, modelo, numero_serie, imei,
          estado_general, falla_cliente, "", "Recibido en taller", 0.0, ""))

    oid = cur.fetchone()["id"]
    anio = str(os.environ.get("ANIO_OVERRIDE") or "")  # no usado, por si querés
    anio = str(__import__("datetime").datetime.now().year)

    numero_orden = f"NR-{anio}-{oid:04d}"
    cur.execute("UPDATE ordenes SET numero_orden=%s WHERE id=%s", (numero_orden, oid))

    con.commit()
    con.close()

    return f"""
    <h3>Orden creada ✅</h3>
    <p><b>Número:</b> {numero_orden}</p>
    <p><a href="/buscar?numero={numero_orden}">Ver orden</a></p>
    <p><a href="/">Volver</a></p>
    """


@app.get("/buscar")
def buscar():
    if not session.get("login"):
        return redirect("/login")

    numero = request.args.get("numero", "").strip()
    if not numero:
        return """
        <h3>Buscar orden</h3>
        <form>
          Número (NR-AAAA-0001): <input name="numero">
          <button>Buscar</button>
        </form>
        <p><a href="/">Volver</a></p>
        """

    con = db()
    cur = con.cursor()

    cur.execute("""
      SELECT o.numero_orden, c.nombre, c.telefono, c.email, o.tipo_equipo, o.marca, o.modelo,
             o.estado, o.presupuesto, o.diagnostico_tecnico
      FROM ordenes o
      JOIN clientes c ON o.cliente_id=c.id
      WHERE o.numero_orden=%s
    """, (numero,))
    r = cur.fetchone()
    con.close()

    if not r:
        return f"<p>No encontrada: {numero}</p><p><a href='/buscar'>Volver</a></p>"

    pres = "En diagnóstico" if float(r["presupuesto"] or 0) == 0 else f"${r['presupuesto']}"
    return f"""
    <h3>Orden {r['numero_orden']}</h3>
    <p><b>Cliente:</b> {r['nombre']} ({r['telefono']}) - {r['email']}</p>
    <p><b>Equipo:</b> {r['tipo_equipo']} {r['marca']} {r['modelo']}</p>
    <p><b>Estado:</b> {r['estado']}</p>
    <p><b>Presupuesto:</b> {pres}</p>
    <p><b>Diagnóstico:</b> {r['diagnostico_tecnico']}</p>
    <p><a href="/actualizar?numero={r['numero_orden']}">Actualizar</a></p>
    <p><a href="/">Volver</a></p>
    """


@app.route("/actualizar", methods=["GET", "POST"])
def actualizar():
    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":
        numero = request.args.get("numero", "").strip()
        return f"""
        <h3>Actualizar orden</h3>
        <form method="post">
          Número: <input name="numero" value="{numero}"><br>
          Nuevo estado:
<select name="estado">
<option value="">-- elegir --</option>
<option value="Recibido en taller">Recibido en taller</option>
<option value="En diagnóstico">En diagnóstico</option>
<option value="Esperando aprobación">Esperando aprobación</option>
<option value="Esperando repuesto">Esperando repuesto</option>
<option value="En reparación">En reparación</option>
<option value="Listo para retirar">Listo para retirar</option>
<option value="Entregado">Entregado</option>
</select><br>
          Nuevo diagnóstico: <input name="diag"><br>
          Nuevo presupuesto: <input name="presupuesto"><br>
          <button type="submit">Guardar</button>
        </form>
        <p><a href="/">Volver</a></p>
        """

    numero = request.form.get("numero", "").strip()
    nuevo_estado = request.form.get("estado", "").strip()
    nuevo_diag = request.form.get("diag", "").strip()
    nuevo_pres = request.form.get("presupuesto", "").strip()

    con = db()
    cur = con.cursor()

    cur.execute("SELECT estado, diagnostico_tecnico, presupuesto FROM ordenes WHERE numero_orden=%s", (numero,))
    old = cur.fetchone()
    if not old:
        con.close()
        return f"<p>No encontrada: {numero}</p><p><a href='/actualizar'>Volver</a></p>"

    if nuevo_estado:
        cur.execute("UPDATE ordenes SET estado=%s WHERE numero_orden=%s", (nuevo_estado, numero))
    if nuevo_diag:
        cur.execute("UPDATE ordenes SET diagnostico_tecnico=%s WHERE numero_orden=%s", (nuevo_diag, numero))
    if nuevo_pres:
        try:
            p = float(nuevo_pres)
        except:
            p = 0.0
        cur.execute("UPDATE ordenes SET presupuesto=%s WHERE numero_orden=%s", (p, numero))

    con.commit()
    con.close()
    return redirect(f"/buscar?numero={numero}")

@app.get("/ver_ordenes")
def ver_ordenes():
    if not session.get("login"):
        return redirect("/login")

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT o.numero_orden, c.nombre, o.tipo_equipo, o.marca, o.modelo,
               o.estado, o.presupuesto
        FROM ordenes o
        JOIN clientes c ON o.cliente_id = c.id
        ORDER BY o.id DESC
    """)
    ordenes = cur.fetchall()
    con.close()

    html = """
    <h2>Todas las órdenes</h2>
    <p><a href="/">Volver al menú</a></p>
    <table border="1" cellpadding="8" cellspacing="0">
      <tr>
        <th>Número</th>
        <th>Cliente</th>
        <th>Equipo</th>
        <th>Estado</th>
        <th>Presupuesto</th>
        <th>Acción</th>
      </tr>
    """

    for orden in ordenes:
        presupuesto = "En diagnóstico" if float(orden["presupuesto"] or 0) == 0 else f"${orden['presupuesto']}"
        equipo = f"{orden['tipo_equipo']} {orden['marca']} {orden['modelo']}"

        html += f"""
        <tr>
          <td>{orden['numero_orden']}</td>
          <td>{orden['nombre']}</td>
          <td>{equipo}</td>
          <td>{orden['estado']}</td>
          <td>{presupuesto}</td>
          <td><a href="/actualizar?numero={orden['numero_orden']}">Actualizar</a></td>
        </tr>
        """

    html += "</table>"
    return html

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)