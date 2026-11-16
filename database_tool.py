import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "admision_logistica.db"


def inicializar_bd():
    """
    Inicializa la base de datos SQLite local (On-Premise simulada) con 3 tablas:
    1. inventario: Stock físico de stands y cajas de folletos.
    2. agenda_horarios: Base de datos pre-cargada con bloques DISPONIBLE y OCUPADO.
    3. reservas: Registro histórico transaccional de todas las reservas confirmadas.
    """
    conexion = sqlite3.connect(str(DB_PATH))
    cursor = conexion.cursor()

    # 1. Tabla de Inventario Físico
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id_item INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_item TEXT UNIQUE NOT NULL,
            stock_total INTEGER NOT NULL,
            stock_disponible INTEGER NOT NULL
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM inventario")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO inventario (nombre_item, stock_total, stock_disponible) VALUES (?, ?, ?)",
            [
                ("Stands Institucionales", 30, 20),
                ("Cajas de Folletos", 50, 50),
            ],
        )

    # 2. Tabla de Agenda de Horarios y Furgones (Pre-cargada para simulación real)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agenda_horarios (
            id_bloque INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            bloque TEXT NOT NULL,
            estado TEXT NOT NULL,
            colegio_asignado TEXT NOT NULL,
            vehiculo_asignado TEXT NOT NULL,
            UNIQUE(fecha, bloque)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM agenda_horarios")
    if cursor.fetchone()[0] == 0:
        horarios_iniciales = [
            ("2026-11-23", "Mañana", "OCUPADO", "Colegio Verbo Divino", "Furgón Institucional 1"),
            ("2026-11-23", "Tarde", "DISPONIBLE", "Ninguno", "Sin asignar"),
            ("2026-11-24", "Mañana", "OCUPADO", "Saint George's College", "Furgón Institucional 1"),
            ("2026-11-24", "Tarde", "OCUPADO", "The Grange School", "Vehículo Liviano UAI"),
            ("2026-11-25", "Mañana", "DISPONIBLE", "Ninguno", "Sin asignar"),
            ("2026-11-25", "Tarde", "OCUPADO", "Colegio Tabancura", "Furgón Institucional 1"),
            ("2026-11-26", "Mañana", "DISPONIBLE", "Ninguno", "Sin asignar"),
            ("2026-11-26", "Tarde", "DISPONIBLE", "Ninguno", "Sin asignar"),
            ("2026-11-27", "Mañana", "OCUPADO", "Instituto Nacional", "Furgón Institucional 1"),
            ("2026-11-27", "Tarde", "DISPONIBLE", "Ninguno", "Sin asignar"),
        ]
        cursor.executemany(
            """INSERT INTO agenda_horarios 
               (fecha, bloque, estado, colegio_asignado, vehiculo_asignado) 
               VALUES (?, ?, ?, ?, ?)""",
            horarios_iniciales,
        )

    # 3. Tabla de Reservas Confirmadas (Auditoría y Persistencia)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id_reserva INTEGER PRIMARY KEY AUTOINCREMENT,
            colegio TEXT NOT NULL,
            fecha TEXT NOT NULL,
            bloque TEXT NOT NULL,
            cantidad_stands INTEGER NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conexion.commit()
    conexion.close()


def tool_consultar_agenda(fecha: str = "") -> dict:
    """
    Consulta los bloques horarios (Mañana y Tarde) disponibles y ocupados en la base de datos.
    Si no se especifica fecha, devuelve toda la programación semanal.

    Args:
        fecha (str): Fecha opcional en formato YYYY-MM-DD para filtrar la agenda.

    Returns:
        dict: Lista de bloques horarios con su estado (DISPONIBLE u OCUPADO) y colegio asignado.
    """
    inicializar_bd()
    conexion = sqlite3.connect(str(DB_PATH))
    cursor = conexion.cursor()
    try:
        if fecha and fecha.strip():
            cursor.execute(
                "SELECT fecha, bloque, estado, colegio_asignado, vehiculo_asignado FROM agenda_horarios WHERE fecha = ? ORDER BY fecha, bloque",
                (fecha.strip(),),
            )
        else:
            cursor.execute(
                "SELECT fecha, bloque, estado, colegio_asignado, vehiculo_asignado FROM agenda_horarios ORDER BY fecha, bloque"
            )
        filas = cursor.fetchall()
        agenda = [
            {
                "fecha": f[0],
                "bloque": f[1],
                "estado": f[2],
                "colegio_asignado": f[3],
                "vehiculo_asignado": f[4],
            }
            for f in filas
        ]
        return {"estado": "ok", "agenda_horarios": agenda}
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}
    finally:
        conexion.close()


def tool_registrar_reserva(
    colegio: str,
    fecha: str,
    cantidad_stands: int,
    bloque: str = "General",
) -> str:
    """
    Registra una reserva de stands en la base de datos SQLite, validando previamente
    que exista stock disponible y que el bloque horario (Mañana o Tarde) no esté ocupado.

    Args:
        colegio (str): Nombre del colegio o evento de destino.
        fecha (str): Fecha del evento en formato YYYY-MM-DD.
        cantidad_stands (int): Cantidad de stands institucionales a reservar (1 a 5).
        bloque (str): Bloque horario solicitado ('Mañana' o 'Tarde'). Por defecto 'General'.

    Returns:
        str: Mensaje de confirmación con ID de reserva y stock restante, o detalle del rechazo.
    """
    inicializar_bd()
    if cantidad_stands <= 0:
        return "Error: La cantidad de stands debe ser mayor a 0."
    if cantidad_stands > 5:
        return "Error de Regla de Negocio: No se pueden asignar más de 5 stands por visita debido al límite vehicular."

    conexion = sqlite3.connect(str(DB_PATH))
    cursor = conexion.cursor()

    try:
        # 1. Si se especifica bloque Mañana o Tarde, validar disponibilidad horaria
        bloque_norm = bloque.strip().capitalize() if bloque else "General"
        if bloque_norm in ("Mañana", "Tarde"):
            cursor.execute(
                "SELECT estado, colegio_asignado FROM agenda_horarios WHERE fecha = ? AND bloque = ?",
                (fecha.strip(), bloque_norm),
            )
            fila_horario = cursor.fetchone()
            if fila_horario and fila_horario[0] == "OCUPADO":
                return (
                    f"Error de Horario: El bloque '{bloque_norm}' del día {fecha} ya se encuentra OCUPADO "
                    f"por '{fila_horario[1]}'. Por favor seleccione otro bloque o fecha."
                )

        # 2. Verificar stock de Stands Institucionales
        cursor.execute(
            "SELECT stock_disponible FROM inventario WHERE nombre_item = 'Stands Institucionales'"
        )
        fila_stock = cursor.fetchone()
        if not fila_stock:
            return "Error: No existe el ítem 'Stands Institucionales' en el inventario."

        stock_actual = fila_stock[0]
        if stock_actual < cantidad_stands:
            return (
                f"Error de Stock: Solicitud de {cantidad_stands} stands excede el stock disponible "
                f"en bodega ({stock_actual} unidades)."
            )

        # 3. Descontar stock en inventario
        nuevo_stock = stock_actual - cantidad_stands
        cursor.execute(
            "UPDATE inventario SET stock_disponible = ? WHERE nombre_item = 'Stands Institucionales'",
            (nuevo_stock,),
        )

        # 4. Actualizar u ocupar el bloque en agenda_horarios si es Mañana o Tarde
        vehiculo = "Vehículo Liviano UAI" if cantidad_stands <= 2 else "Furgón Institucional 1"
        if bloque_norm in ("Mañana", "Tarde"):
            cursor.execute(
                """INSERT INTO agenda_horarios (fecha, bloque, estado, colegio_asignado, vehiculo_asignado)
                   VALUES (?, ?, 'OCUPADO', ?, ?)
                   ON CONFLICT(fecha, bloque) DO UPDATE SET
                   estado = 'OCUPADO', colegio_asignado = excluded.colegio_asignado, vehiculo_asignado = excluded.vehiculo_asignado""",
                (fecha.strip(), bloque_norm, colegio.strip(), vehiculo),
            )

        # 5. Insertar registro auditable en la tabla reservas
        cursor.execute(
            "INSERT INTO reservas (colegio, fecha, bloque, cantidad_stands) VALUES (?, ?, ?, ?)",
            (colegio.strip(), fecha.strip(), bloque_norm, cantidad_stands),
        )
        id_reserva = cursor.lastrowid

        conexion.commit()
        return (
            f"Éxito: Reserva #{id_reserva} registrada en BD para '{colegio}' el {fecha} "
            f"(Bloque: {bloque_norm}) con {cantidad_stands} stands. Stock restante en bodega: {nuevo_stock}."
        )
    except Exception as e:
        conexion.rollback()
        return f"Error en base de datos: {str(e)}"
    finally:
        conexion.close()


if __name__ == "__main__":
    inicializar_bd()
    print("Base de datos 'admision_logistica.db' inicializada con tablas: inventario, agenda_horarios y reservas.")


    