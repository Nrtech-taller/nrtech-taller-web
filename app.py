from flask import Flask, request, redirect
import sqlite3

DB = "taller.db"
app = Flask(__name__)

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

@app.get("/")
def home():
    return """
    <h2>NR Tech - Taller (Web)</h2>
    <ul>
      <li><a href="/crear">Crear orden</a></li>
      <li><a href="/buscar">Buscar orden</a></li>
      <li><a href="/actualizar">Actualizar orden</a></li>
    </ul>
    """

@app.route("/crear", methods=["GET","POST"])
def crear():
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

    nombre = request.form.get("nombre","").strip()
    telefono = request.form.get("telefono","").strip()
    email = request.form.get("email","").strip()
    tipo = request.form.get("tipo","").strip()
    marca = request.form.get("marca","").strip()
    modelo = request.form.get("modelo","").strip()
    numero_serie = request.form.get("numero_serie","").strip()
    imei = request.form.get("imei","").strip()
    estado_general = request.form.get("estado_general","").strip()
    falla_cliente = request.form.get("falla_cliente","").strip()

    con = db()
    cur = con.cursor()

    # cliente
    cur.execute("SELECT id FROM clientes WHERE email=?", (email,))
    row = cur.fetchone()
    if row:
        cliente_id = row["id"]
    else:
        cur.execute("INSERT INTO clientes(nombre,telefono,email) VALUES(?,?,?)", (nombre, telefono, email))
        cliente_id = cur.lastrowid

    # orden
    cur.execute("""
      INSERT INTO ordenes(
        numero_orden, cliente_id, tipo_equipo, marca, modelo, numero_serie, imei,
        estado_general, falla_cliente, diagnostico_tecnico, fecha_ingreso, estado, presupuesto, observaciones
      ) VALUES(?,?,?,?,?,?,?,?,?,?,date('now'),?,?,?)
    """, ("", cliente_id, tipo, marca, modelo, numero_serie, imei,
          estado_general, falla_cliente, "", "Recibido en taller", 0.0, ""))

    oid = cur.lastrowid
    # numero profesional
    cur.execute("SELECT strftime('%Y','now') as anio")
    anio = cur.fetchone()["anio"]
    numero_orden = f"NR-{anio}-{oid:04d}"
    cur.execute("UPDATE ordenes SET numero_orden=? WHERE id=?", (numero_orden, oid))

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
    numero = request.args.get("numero","").strip()
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
      FROM ordenes o JOIN clientes c ON o.cliente_id=c.id
      WHERE o.numero_orden=?
    """, (numero,))
    r = cur.fetchone()
    con.close()

    if not r:
        return f"<p>No encontrada: {numero}</p><p><a href='/buscar'>Volver</a></p>"

    pres = "En diagnóstico" if float(r["presupuesto"]) == 0 else f"${r['presupuesto']}"
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

@app.route("/actualizar", methods=["GET","POST"])
def actualizar():
    if request.method == "GET":
        numero = request.args.get("numero","").strip()
        return f"""
        <h3>Actualizar orden</h3>
        <form method="post">
          Número: <input name="numero" value="{numero}"><br>
          Nuevo estado: <input name="estado"><br>
          Nuevo diagnóstico: <input name="diag"><br>
          Nuevo presupuesto: <input name="presupuesto"><br>
          <button type="submit">Guardar</button>
        </form>
        <p><a href="/">Volver</a></p>
        """

    numero = request.form.get("numero","").strip()
    nuevo_estado = request.form.get("estado","").strip()
    nuevo_diag = request.form.get("diag","").strip()
    nuevo_pres = request.form.get("presupuesto","").strip()

    con = db()
    cur = con.cursor()
    cur.execute("SELECT estado, diagnostico_tecnico, presupuesto FROM ordenes WHERE numero_orden=?", (numero,))
    old = cur.fetchone()
    if not old:
        con.close()
        return f"<p>No encontrada: {numero}</p><p><a href='/actualizar'>Volver</a></p>"

    if nuevo_estado:
        cur.execute("UPDATE ordenes SET estado=? WHERE numero_orden=?", (nuevo_estado, numero))
    if nuevo_diag:
        cur.execute("UPDATE ordenes SET diagnostico_tecnico=? WHERE numero_orden=?", (nuevo_diag, numero))
    if nuevo_pres:
        try:
            p = float(nuevo_pres)
        except:
            p = 0.0
        cur.execute("UPDATE ordenes SET presupuesto=? WHERE numero_orden=?", (p, numero))

    con.commit()
    con.close()
    return redirect(f"/buscar?numero={numero}")

if __name__ == "__main__":
    app.run(if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False))