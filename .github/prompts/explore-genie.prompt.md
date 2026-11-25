---
description: Investigar una pregunta sobre los datos disponibles en Genie
agent: databricks
---
Este prompt selecciona expresamente Genie solo para esta tarea; no hace falta volver a preguntar el modo. Usa el MCP de Genie autorizado para responder a esta pregunta: ${input:question:Pregunta sobre los datos}. Si la respuesta esta en progreso, consulta su estado hasta terminar. Si Genie falla, no esta disponible o no incluye las tablas necesarias, explica el bloqueo y pregunta mediante `ask_user` si se resuelve o se continua con Copilot; no cambies de modo ni amplies el alcance sin autorizacion. Indica el alcance de los datos, el SQL, las limitaciones y los costes cuando esten disponibles; no inventes resultados. No modifiques datos.

Antes de enviar la pregunta, descubre las herramientas de `databricks-genie` y verifica la conexion MCP real, la autenticacion, las herramientas de consulta y `poll_response`, el espacio y las tablas incluidas mediante las operaciones de descubrimiento y metadatos disponibles. Distingue lo configurado, conectado, autenticado y verificado; una llamada REST exitosa no valida el transporte MCP. No ejecutes consultas de datos, arranques compute ni instales o reconfigures herramientas para comprobar disponibilidad. Si falta un acceso necesario, informa del bloqueo y espera la decision del usuario.
