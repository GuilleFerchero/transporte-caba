---
description: Auditar el proyecto entero (o el scope indicado) con el agente auditor y devolver el informe priorizado.
agent: auditor
---

Auditoría completa de este proyecto.

Scope: $ARGUMENTS

Si el scope está vacío, auditá todo lo versionado en git (`git ls-files`), con foco en:
los entrypoints de Streamlit, el módulo de datos compartidos, el script de build del
bundle de datos, la config de deploy (Docker/requirements) y la coherencia entre el
documento de instrucciones del repo y el código real.

Entregá el informe en el formato definido por tu prompt (Veredicto / Tabla de hallazgos
con severidad / Hallazgos con `archivo:línea` y evidencia / Salud por dimensión / Qué NO
está roto / Deuda técnica). Priorizá hallazgos verificables sobre opiniones.
