import json
import random
import time
from agentes.agent import root_agent

# =====================================================================
# 1. GENERACIÓN SINTÉTICA DE 300 CASOS DE USO (GOLDEN SET)
# =====================================================================
colegios = ["San Ignacio", "Verbo Divino", "Instituto Nacional", "Carmela Carvajal", "Saint George", "Colegio Alicante"]
fechas = ["2026-11-20", "2026-11-25", "2026-12-01", "2026-12-05", "Hoy"]
cantidades = [1, 2, 4, 6, 15] # 6 y 15 forzarán el rechazo por la regla de Nivel 2 (>5)
estilos = [
    "Necesitamos ir al colegio {colegio} el {fecha} con {cantidad} stands.",
    "Hola, reserva {cantidad} stands para el {colegio} el día {fecha}.",
    "Urgente: feria en {colegio}, fecha {fecha}. Llevar {cantidad} stands.",
    "Falta la fecha pero iremos al {colegio} con {cantidad} stands." # Provocará que el Orquestador pida datos
]

casos_prueba = []
for i in range(300):
    col = random.choice(colegios)
    fec = random.choice(fechas)
    cant = random.choice(cantidades)
    plantilla = random.choice(estilos)
    
    prompt_usuario = plantilla.format(colegio=col, fecha=fec, cantidad=cant)
    casos_prueba.append({"id": i+1, "prompt": prompt_usuario, "cantidad_pedida": cant})

# =====================================================================
# 2. EJECUCIÓN AUTOMATIZADA PARA EVALUAR ACCURACY Y OBSERVABILIDAD
# =====================================================================
print(f"Iniciando evaluación de {len(casos_prueba)} casos en el Framework ADK...")
resultados = {"exitos": 0, "rechazos_reglas": 0, "errores_truncados_timeout": 0}

# Por tiempo de demostración, evaluaremos una muestra aleatoria de 10 para probar.
# (Cambia a casos_prueba completo cuando quieras correr los 300)
muestra_test = random.sample(casos_prueba, 10) 

for caso in muestra_test:
    print(f"\n--- CASO {caso['id']} ---")
    print(f"User: {caso['prompt']}")
    
    try:
        # Simulamos latencia y observabilidad (Timeouts / Límites)
        inicio = time.time()
        
        # Ejecución del agente raíz
        respuesta = root_agent(caso['prompt'])
        
        tiempo_resp = time.time() - inicio
        print(f"Agent ({tiempo_resp:.2f}s): {respuesta}")
        
        if "Éxito" in str(respuesta) or "Confirmada" in str(respuesta):
            resultados["exitos"] += 1
        elif "rechaz" in str(respuesta).lower() or "no puede exceder" in str(respuesta).lower():
            resultados["rechazos_reglas"] += 1
        else:
            resultados["errores_truncados_timeout"] += 1
            
    except Exception as e:
        print(f"Error de sistema/Timeout: {str(e)}")
        resultados["errores_truncados_timeout"] += 1
        
    time.sleep(1) # Respetar rate limits de la API

print("\n=== RESUMEN DE LA EJECUCIÓN ===")
print(f"Total evaluados: {len(muestra_test)}")
print(f"Aprobados logísticamente: {resultados['exitos']}")
print(f"Rechazados por Reglas de Negocio/Stock: {resultados['rechazos_reglas']}")
print(f"Errores (Falta info/Timeouts): {resultados['errores_truncados_timeout']}")

# Cálculo de Accuracy para el Informe (Debe ser < 95%)
fallos = resultados['errores_truncados_timeout']
accuracy = ((len(muestra_test) - fallos) / len(muestra_test)) * 100
print(f"Accuracy del sistema: {accuracy}%")

