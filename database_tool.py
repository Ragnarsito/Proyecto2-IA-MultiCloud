import sqlite3
from datetime import datetime

# 1. INICIALIZACIÓN DE LA BASE DE DATOS (Entorno On-Premise Simulado)
def inicializar_bd():
    conexion = sqlite3.connect("admision_logistica.db")
    cursor = conexion.cursor()
    
    # Tabla de inventario total
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventario (
            id_item INTEGER PRIMARY KEY,
            nombre_item TEXT,
            stock_total INTEGER,
            stock_disponible INTEGER
        )
    ''')
    
    # Tabla para registrar las reservas hechas por el Agente (Tool API)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservas_ferias (
            id_reserva INTEGER PRIMARY KEY AUTOINCREMENT,
            colegio_destino TEXT,
            fecha_visita TEXT,
            cantidad_stands INTEGER,
            estado TEXT,
            fecha_registro TIMESTAMP
        )
    ''')
    
    # Insertar stock inicial si está vacía
    cursor.execute("SELECT COUNT(*) FROM inventario")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO inventario (nombre_item, stock_total, stock_disponible) VALUES ('Stands Institucionales', 10, 10)")
        cursor.execute("INSERT INTO inventario (nombre_item, stock_total, stock_disponible) VALUES ('Cajas de Folletos', 50, 50)")
    
    conexion.commit()
    conexion.close()

# 2. EL TOOL API (La función que ejecutará el Agente de Nivel 3)
def tool_registrar_reserva(colegio: str, fecha: str, cantidad_stands: int) -> str:
    """
    API Tool para que el agente registre la salida de material hacia un colegio.
    Verifica disponibilidad y asegura la transacción (ACID).
    """
    conexion = sqlite3.connect("admision_logistica.db")
    cursor = conexion.cursor()
    
    try:
        # Verificar stock
        cursor.execute("SELECT stock_disponible FROM inventario WHERE nombre_item = 'Stands Institucionales'")
        stock_actual = cursor.fetchone()[0]
        
        if stock_actual >= cantidad_stands:
            # Transacción: Descontar inventario y registrar reserva
            nuevo_stock = stock_actual - cantidad_stands
            cursor.execute("UPDATE inventario SET stock_disponible = ? WHERE nombre_item = 'Stands Institucionales'", (nuevo_stock,))
            
            fecha_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO reservas_ferias (colegio_destino, fecha_visita, cantidad_stands, estado, fecha_registro)
                VALUES (?, ?, ?, 'Confirmado', ?)
            ''', (colegio, fecha, cantidad_stands, fecha_registro))
            
            conexion.commit()
            resultado = f"Éxito: Reserva confirmada para {colegio}. Stands asignados: {cantidad_stands}. Stock restante: {nuevo_stock}."
        else:
            resultado = f"Error Logístico: Stock insuficiente. Se solicitaron {cantidad_stands} stands, pero solo hay {stock_actual} disponibles."
            
    except Exception as e:
        conexion.rollback()
        resultado = f"Error de sistema en la base de datos: {str(e)}"
    finally:
        conexion.close()
        
    return resultado

# Bloque de prueba local
if __name__ == "__main__":
    inicializar_bd()
    print("Base de datos inicializada correctamente.")
    # Prueba manual para ver si funciona antes de conectarla al LLM
    print(tool_registrar_reserva("Colegio San Miguel", "2026-11-20", 2))

    