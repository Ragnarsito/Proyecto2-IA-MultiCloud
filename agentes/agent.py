import os
import sys
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Forzar salida UTF-8 en consola Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

try:
    from google.adk.agents import Agent
except ImportError:
    from google.adk import Agent

from database_tool import (
    inicializar_bd,
    tool_consultar_agenda,
    tool_registrar_reserva,
)

os.chdir(ROOT_DIR)
inicializar_bd()

MODELO_LLM = os.getenv("ADK_MODEL", "gemini-flash-lite-latest")


# =====================================================================
# HERRAMIENTA DE CONSULTA DE STOCK (Function Tool con Docstring)
# =====================================================================
def tool_consultar_stock() -> dict:
    """
    Consulta el stock disponible actual de Stands Institucionales y Cajas de Folletos
    en la base de datos local de logística de admisión, junto con el total de reservas.

    Returns:
        dict: Diccionario con el inventario disponible actual y reservas registradas.
    """
    db_path = ROOT_DIR / "admision_logistica.db"
    conexion = sqlite3.connect(str(db_path))
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT nombre_item, stock_disponible FROM inventario")
        filas = cursor.fetchall()
        inventario_actual = {nombre: stock for nombre, stock in filas}

        cursor.execute("SELECT id_reserva, colegio, fecha, bloque, cantidad_stands FROM reservas ORDER BY id_reserva DESC LIMIT 5")
        ultimas_reservas = [
            {"id": r[0], "colegio": r[1], "fecha": r[2], "bloque": r[3], "stands": r[4]}
            for r in cursor.fetchall()
        ]
        return {
            "estado": "ok",
            "inventario_disponible": inventario_actual,
            "ultimas_reservas_registradas": ultimas_reservas,
        }
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}
    finally:
        conexion.close()


# =====================================================================
# NIVEL 3: AGENTES ESPECIALISTAS DE EJECUCIÓN (Profundidad 3)
# =====================================================================

# Agente 3 (Nivel 3): Gestor de Reservas con Tool API hacia BD propia
gestor_reservas_agent = Agent(
    name="gestor_reservas_agent",
    model=MODELO_LLM,
    description="Agente especialista que escribe reservas en la base de datos SQLite mediante Tool API.",
    instruction="""Eres el Agente Gestor de Reservas (Nivel 3) de Admisión UAI.
Tu única responsabilidad es ejecutar la herramienta 'tool_registrar_reserva' pasando exactamente:
- colegio (str): Nombre del colegio o evento.
- fecha (str): Fecha solicitada en formato YYYY-MM-DD.
- cantidad_stands (int): Número entero de stands a reservar.
- bloque (str): 'Mañana' o 'Tarde' (si el usuario no especificó bloque, usa 'Mañana' por defecto).

No inventes confirmaciones sin invocar primero 'tool_registrar_reserva'.
Una vez ejecutada la herramienta:
- Si la reserva fue exitosa, entrega el resultado exacto (incluyendo el ID de reserva y stock restante) y transfiere al 'planificador_rutas_agent'.
- Si hubo un error de horario ocupado o falta de stock, transfiere directamente al 'notificador_agent' indicando los horarios alternativos disponibles.""",
    tools=[tool_registrar_reserva],
)

# Agente 4 (Nivel 3): Planificador de Rutas y Transporte
planificador_rutas_agent = Agent(
    name="planificador_rutas_agent",
    model=MODELO_LLM,
    description="Agente especialista en logística de traslado y estimación de rutas para eventos.",
    instruction="""Eres el Agente Planificador de Rutas (Nivel 3) de Admisión UAI.
Recibes la confirmación de reserva de materiales y evalúas la logística de traslado desde el campus Peñalolén hacia el colegio de destino:
1. Determina la ventana horaria de salida según el bloque reservado:
   - Bloque Mañana (08:30 - 13:00): Recomendar salida desde Peñalolén a las 07:00 AM (90 min antes por tráfico punta).
   - Bloque Tarde (14:00 - 17:30): Recomendar salida desde Peñalolén a las 12:30 PM.
2. Indica el tipo de vehículo requerido según el volumen (1 a 2 stands: Vehículo Institucional Liviano; 3 a 5 stands: Furgón Institucional 1).
3. Al finalizar tu evaluación de ruta, transfiere el contexto completo al 'notificador_agent' para emitir el cierre operativo.""",
)

# Agente 5 (Nivel 3): Notificador Operativo
notificador_agent = Agent(
    name="notificador_agent",
    model=MODELO_LLM,
    description="Agente encargado de consolidar la operación y redactar el informe final para el equipo de admisión.",
    instruction="""Eres el Agente Notificador (Nivel 3) de Admisión UAI.
Recibes el estado de la reserva en base de datos, la disponibilidad de agenda y el plan logístico de ruta.
Redacta un resumen ejecutivo claro, estructurado y profesional para el equipo de Admisión en terreno que incluya:
- Estado de la Solicitud (Confirmada con su ID de Reserva en BD, Rechazada por Tope de Horario/Regla, o Reporte de Disponibilidad).
- Detalle del Colegio, Fecha, Bloque Horario ('Mañana' o 'Tarde') y Cantidad de Stands asignados (o bloques disponibles sugeridos en caso de rechazo).
- Stock restante en bodega y Plan de Transporte con horario sugerido de salida desde Campus Peñalolén (si aplica).""",
)


# =====================================================================
# NIVEL 2: AGENTE ANALISTA DE INVENTARIO Y AGENDA (Profundidad 2)
# =====================================================================

analista_inventario_agent = Agent(
    name="analista_inventario_agent",
    model=MODELO_LLM,
    description="Agente de nivel intermedio que valida reglas de negocio, consulta stock y revisa la agenda de horarios disponibles/ocupados.",
    instruction="""Eres el Agente Analista de Inventario y Agenda (Nivel 2) de Admisión UAI.
Sigue estrictamente este flujo de razonamiento:
1. Si el usuario solo desea consultar qué horarios o stock están disponibles, ejecuta 'tool_consultar_agenda' y 'tool_consultar_stock', y transfiere al 'notificador_agent' para que le muestre la tabla de bloques DISPONIBLE y OCUPADO.
2. Si el usuario solicita agendar una visita:
   a) Regla de negocio de transporte: Ninguna visita individual puede solicitar más de 5 stands por límite de capacidad vehicular. Si piden más de 5 stands o <= 0, rechaza la solicitud y delega inmediatamente al 'notificador_agent' explicando el motivo.
   b) Ejecuta 'tool_consultar_stock' y 'tool_consultar_agenda' (pasando la fecha solicitada) para verificar el stock y comprobar si el bloque ('Mañana' o 'Tarde') está DISPONIBLE u OCUPADO.
   c) Si el bloque solicitado aparece OCUPADO en 'tool_consultar_agenda', no registres la reserva: transfiere directamente al 'notificador_agent' informando qué colegio ocupa ese bloque y cuáles bloques están en estado DISPONIBLE.
   d) Si el bloque está DISPONIBLE y hay stock suficiente, delega al 'gestor_reservas_agent' (Nivel 3) para registrar la reserva en SQLite.""",
    tools=[tool_consultar_stock, tool_consultar_agenda],
    sub_agents=[
        gestor_reservas_agent,
        planificador_rutas_agent,
        notificador_agent,
    ],
)


# =====================================================================
# NIVEL 1: AGENTE ORQUESTADOR PRINCIPAL / ROOT AGENT (Profundidad 1)
# =====================================================================

root_agent = Agent(
    name="root_agent",
    model=MODELO_LLM,
    description="Agente Orquestador Principal (Nivel 1) del Sistema Logístico de Admisión UAI.",
    instruction="""Eres el Agente Orquestador Principal (Nivel 1) de Logística de Admisión y Difusión de la Universidad Adolfo Ibáñez.
Tu misión es:
1. Recibir la consulta o solicitud en lenguaje natural del usuario.
2. Si el usuario pregunta por la disponibilidad de horarios, agenda de la semana o stock en bodega, transfiere de inmediato la solicitud a 'analista_inventario_agent' (Nivel 2).
3. Si el usuario solicita agendar una visita a un colegio o feria vocacional, identifica: Nombre del Colegio, Fecha de la visita (formato YYYY-MM-DD), Cantidad de Stands solicitados y Bloque Horario ('Mañana' o 'Tarde'; si no menciona bloque, asume 'Mañana').
4. Si falta el Colegio, la Fecha o la Cantidad de Stands, pídeselo brevemente antes de continuar.
5. Una vez identificados los datos, transfiere la solicitud al sub-agente 'analista_inventario_agent' (Nivel 2).""",
    sub_agents=[analista_inventario_agent],
)


if __name__ == "__main__":
    print("=== VERIFICACIÓN DE TOPOLOGÍA MULTI-AGENTE (GOOGLE ADK) ===")
    print(f"Nivel 1 (Orquestador): {root_agent.name} | Modelo: {MODELO_LLM}")
    for sub_n2 in root_agent.sub_agents:
        print(f"  └── Nivel 2 (Analista): {sub_n2.name} | Tools: {[t.__name__ for t in sub_n2.tools]}")
        for sub_n3 in sub_n2.sub_agents:
            tools_n3 = [t.__name__ for t in sub_n3.tools] if sub_n3.tools else ["Ninguna (Razonamiento)"]
            print(f"        └── Nivel 3 (Especialista): {sub_n3.name} | Tools: {tools_n3}")

            