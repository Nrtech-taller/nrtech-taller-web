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


init_db()


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

    nombre = request.form.get("nombre", "")
    telefono = request.form.get("telefono", "")
    email = request.form.get("email", "")
    tipo = request.form.get("tipo", "")
    marca = request.form.get("marca", "")
    modelo = request.form.get("modelo", "")
    numero_serie = request.form.get("numero_serie", "")
    imei = request.form.get("imei", "")
    estado_general = request.form.get("estado_general", "")
    falla_cliente = request.form.get("falla_cliente", "")

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
        numero_orden,cliente_id,tipo_equipo,marca,modelo,numero_serie,imei,
        estado_general,falla_cliente,diagnostico_tecnico,fecha_ingreso,estado,presupuesto,observaciones
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

    import datetime

    anio = datetime.datetime.now().year

    numero_orden = f"NR-{anio}-{oid:04d}"

    cur.execute(
        "UPDATE ordenes SET numero_orden=%s WHERE id=%s",
        (numero_orden, oid),
    )

    con.commit()
    con.close()

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

        html += f"""
        <tr>

        <td>{r['numero_orden']}</td>
        <td>{r['nombre']}</td>
        <td>{equipo}</td>
        <td>{r['estado']}</td>
        <td>{r['presupuesto']}</td>

        <td>

        <a href="/actualizar?numero={r['numero_orden']}">Actualizar</a>

        </td>

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

        html += f"""
        <tr>

        <td>{o['numero_orden']}</td>
        <td>{o['nombre']}</td>
        <td>{equipo}</td>
        <td>{o['estado']}</td>
        <td>{o['presupuesto']}</td>

        <td>

        <a href="/actualizar?numero={o['numero_orden']}">Actualizar</a>

        </td>

        </tr>
        """

    html += "</table><p><a href='/'>Volver</a></p>"

    return html


@app.route("/actualizar", methods=["GET", "POST"])
def actualizar():

    if not session.get("login"):
        return redirect("/login")

    if request.method == "GET":

        numero = request.args.get("numero", "")

        return f"""
        <h3>Actualizar orden</h3>

        <form method="post">

        Numero
        <input name="numero" value="{numero}"><br><br>

        Estado

        <select name="estado">

        <option value="">-- elegir --</option>
        <option value="En diagnostico">En diagnostico</option>
        <option value="Esperando aprobacion">Esperando aprobacion</option>
        <option value="Esperando repuesto">Esperando repuesto</option>
        <option value="En reparacion">En reparacion</option>
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

    numero = request.form.get("numero")
    estado = request.form.get("estado")
    diag = request.form.get("diag")
    pres = request.form.get("presupuesto")

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

    con.commit()
    con.close()

    return redirect(f"/buscar?q={numero}")


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)