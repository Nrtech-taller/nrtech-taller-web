import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

# Crear columna numero_orden si no existe
cursor.execute("""
ALTER TABLE ordenes 
ADD COLUMN numero_orden TEXT
""")

conexion.commit()
conexion.close()
print("Columna numero_orden creada correctamente.")