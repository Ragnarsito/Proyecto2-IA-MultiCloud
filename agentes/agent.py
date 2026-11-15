import os
import sys
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Forzar salida UTF-8 en consola Windows para evitar errores con tildes (ej. "Éxito")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Agregar el directorio raíz al path para importar database_tool.py sin errores de ruta
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Cargar variables de entorno (.env) siguiendo buenas prácticas de seguridad
load_dotenv(ROOT_DIR / ".env")

# Importar el componente Agent de Google ADK (compatible con distintas sub-versiones del SDK)
try:
    from google.adk.agents import Agent
except ImportError:
    from google.adk import Agent

# Importar las funciones de la Base de Datos On-Premise simulada (Paso 1)
from database_tool import inicializar_bd, tool_registrar_reserva

# Asegurar que la base de datos esté inicializada en la raíz del proyecto
os.chdir(ROOT_DIR)
inicializar_bd()

# Modelo configurable por variable de entorno (por defecto gemini-2.5-flash según cátedra)
MODELO_LLM = os.getenv("ADK_MODEL", "gemini-2.5-flash")


# =====================================================================
# HERRAMIENTA COMPLEMENTARIA DE CONSULTA (Function Tool con Docstring)
# =====================================================================
def tool_consultar_stock() -> dict:
    """
    Consulta el stock disponible actual de Stands Institucionales y Cajas de Folletos
    en la base de datos local de logística de admisión.

    Returns:
        dict: Diccionario con el inventario disponible actual o detalle del error.
    """
    db_path = ROOT_DIR / "admision_logistica.db"
    conexion = sqlite3.connect(str(db_path))
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT nombre_item, stock_disponible FROM inventario")
        filas = cursor.fetchall()
        inventario_actual = {nombre: stock for nombre, stock in filas}
        return {"estado": "ok", "inventario_disponible": inventario_actual}
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

No inventes confirmaciones sin invocar primero 'tool_registrar_reserva'.
Una vez ejecutada la herramienta, entrega el resultado exacto de la transacción y transfiere al 'planificador_rutas_agent' si la reserva fue exitosa, o al 'notificador_agent' si hubo un error de stock.""",
    tools=[tool_registrar_reserva],
)

# Agente 4 (Nivel 3): Planificador de Rutas y Transporte
planificador_rutas_agent = Agent(
    name="planificador_rutas_agent",
    model=MODELO_LLM,
    description="Agente especialista en logística de traslado y estimación de rutas para eventos.",
    instruction="""Eres el Agente Planificador de Rutas (Nivel 3) de Admisión UAI.
Recibes la confirmación de reserva de materiales y evalúas la logística de traslado desde el campus Peñalolén hacia el colegio de destino:
1. Determina la viabilidad del traslado y estima una ventana horaria de salida (recomendando salir al menos 90 minutos antes en horario punta en la Región Metropolitana).
2. Indica el tipo de vehículo requerido según el volumen (1 a 2 stands: vehículo institucional liviano; 3 a 5 stands: furgón de carga).
3. Al finalizar tu evaluación de ruta, transfiere el contexto completo al 'notificador_agent' para emitir el cierre operativo.""",
)

# Agente 5 (Nivel 3): Notificador Operativo
notificador_agent = Agent(
    name="notificador_agent",
    model=MODELO_LLM,
    description="Agente encargado de consolidar la operación y redactar el informe final para el equipo de admisión.",
    instruction="""Eres el Agente Notificador (Nivel 3) de Admisión UAI.
Recibes el estado de la reserva en base de datos y el plan logístico de ruta.
Redacta un resumen ejecutivo claro, estructurado y profesional para el equipo de Admisión en terreno que incluya:
- Estado de la Solicitud (Confirmada o Rechazada).
- Detalle del Colegio, Fecha y Cantidad de Stands asignados (o motivo del rechazo).
- Plan de Transporte y horario sugerido de salida (si aplica).""",
)


# =====================================================================
# NIVEL 2: AGENTE ANALISTA DE INVENTARIO Y REGLAS DE NEGOCIO (Profundidad 2)
# =====================================================================

# Agente 2 (Nivel 2): Analista de Inventario y Reglas Operativas
analista_inventario_agent = Agent(
    name="analista_inventario_agent",
    model=MODELO_LLM,
    description="Agente de nivel intermedio que valida reglas de negocio, consulta stock y coordina a los agentes de Nivel 3.",
    instruction="""Eres el Agente Analista de Inventario (Nivel 2) de Admisión UAI.
Recibes del Agente Orquestador los datos de una solicitud de visita escolar (colegio, fecha y cantidad de stands).
Sigue estrictamente este flujo de razonamiento:
1. Regla de negocio de transporte: Ninguna visita individual puede solicitar más de 5 stands por límite de capacidad vehicular. Si piden más de 5 stands o una cantidad menor o igual a 0, rechaza la solicitud y delega inmediatamente al 'notificador_agent' explicando el motivo.
2. Verifica la disponibilidad actual ejecutando la herramienta 'tool_consultar_stock'.
3. Si las reglas se cumplen, delega la ejecución al 'gestor_reservas_agent' (Nivel 3) para que registre la reserva en la base de datos, luego coordina con 'planificador_rutas_agent' (Nivel 3) y finalmente con 'notificador_agent' (Nivel 3).""",
    tools=[tool_consultar_stock],
    sub_agents=[
        gestor_reservas_agent,
        planificador_rutas_agent,
        notificador_agent,
    ],
)


# =====================================================================
# NIVEL 1: AGENTE ORQUESTADOR PRINCIPAL / ROOT AGENT (Profundidad 1)
# =====================================================================

# Agente 1 (Nivel 1): Root Agent (Punto de entrada exigido por Google ADK)
root_agent = Agent(
    name="root_agent",
    model=MODELO_LLM,
    description="Agente Orquestador Principal (Nivel 1) del Sistema Logístico de Admisión UAI.",
    instruction="""Eres el Agente Orquestador Principal (Nivel 1) de Logística de Admisión y Difusión de la Universidad Adolfo Ibáñez.
Tu misión es:
1. Recibir la solicitud en lenguaje natural del usuario para asistir a un colegio o feria vocacional.
2. Identificar los 3 parámetros esenciales: Nombre del Colegio, Fecha de la visita (formato YYYY-MM-DD) y Cantidad de Stands solicitados.
3. Si falta alguno de estos 3 datos críticos en el mensaje del usuario, pídeselo brevemente antes de continuar.
4. Una vez identificados los 3 datos, transfiere la solicitud al sub-agente 'analista_inventario_agent' (Nivel 2) para validar inventario, registrar en la base de datos y planificar la ruta.""",
    sub_agents=[analista_inventario_agent],
)


# =====================================================================
# BLOQUE DE VERIFICACIÓN LOCAL DE TOPOLOGÍA
# =====================================================================
if __name__ == "__main__":
    print("=== VERIFICACIÓN DE TOPOLOGÍA MULTI-AGENTE (GOOGLE ADK) ===")
    print(f"Nivel 1 (Orquestador): {root_agent.name} | Modelo: {MODELO_LLM}")
    for sub_n2 in root_agent.sub_agents:
        print(f"  └── Nivel 2 (Analista): {sub_n2.name} | Tools: {[t.__name__ for t in sub_n2.tools]}")
        for sub_n3 in sub_n2.sub_agents:
            tools_n3 = [t.__name__ for t in sub_n3.tools] if sub_n3.tools else ["Ninguna (Razonamiento)"]
            print(f"        └── Nivel 3 (Especialista): {sub_n3.name} | Tools: {tools_n3}")
    print("\nTopología de 5 agentes y 3 niveles de profundidad cargada sin errores.")
    print("Para abrir la interfaz gráfica de pruebas ADK, ejecuta en la terminal: adk web")

    