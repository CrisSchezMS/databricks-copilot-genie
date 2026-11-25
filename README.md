# Databricks + GitHub Copilot + Genie

Flujo **Databricks primero**: Copilot lee y edita el notebook remoto, lo prueba en Databricks y presenta el resultado. Solo despues de tu OK copia la version aprobada al repositorio, crea una rama y propone un PR. No hay sincronizador ni proceso en segundo plano.

Genie MCP sirve para preguntas de datos y puede ayudar a generar SQL. Es de solo lectura: Copilot aplica los cambios mediante la API/CLI de Databricks con los permisos de la identidad autenticada.

## Preparacion en Windows

Requisitos: Python 3.9+, Azure CLI, Databricks CLI, permisos sobre el workspace y Copilot. La ejecucion necesita un SQL warehouse o cluster y puede generar costes.

```powershell
cd <ruta-del-repositorio>
az login
az account set --subscription <SUBSCRIPTION_ID>
$env:DATABRICKS_HOST = 'https://<workspace>.azuredatabricks.net'
$env:DATABRICKS_AUTH_TYPE = 'azure-cli'
```

Configura Genie sin credenciales en Git:

```powershell
copilot mcp add --transport http databricks-genie "$env:DATABRICKS_HOST/api/2.0/mcp/genie/<GENIE_SPACE_ID>"
```

Si se solicita, usa `/mcp auth databricks-genie`. El soporte OAuth depende del cliente y tenant; comprueba la sesion en el cliente real. En VS Code, crea `.vscode\mcp.json` usando `.mcp.example.json` como plantilla y cambiando `mcpServers` por `servers`. Estos archivos de configuracion local estan ignorados por Git. No copies tokens en archivos ni commits.

## Trabajo diario con Copilot

Abre el repositorio y pide, por ejemplo: «Modifica el resumen de eventos en Databricks, pruebalo y enseñame el resultado antes de publicar». Antes de cada nueva tarea en Databricks, Copilot te preguntara mediante `ask_user` que modo quieres usar y esperara tu respuesta:

- **Genie**: consultar datos y ayudar a generar SQL mediante el MCP `databricks-genie`, esperando el resultado final.
- **Copilot**: analizar y generar notebooks y SQL directamente con las herramientas autorizadas de Databricks, sin consultar Genie.

La eleccion solo vale para esa tarea. Si ya pides expresamente «con Genie» o «con Copilot», no se repite la pregunta. El prompt `explore-genie` selecciona Genie expresamente. Si Genie falla o no incluye las tablas necesarias, Copilot informara del bloqueo y preguntara si quieres resolverlo o continuar con Copilot; no cambiara de modo ni ampliara el alcance del espacio sin autorizacion.

En ambos modos, las escrituras y publicaciones las realiza Copilot mediante las herramientas de Databricks, no Genie. Se mantienen los mismos permisos, confirmaciones, controles de SHA y avisos de costes. Copilot debe:

1. Despues de elegir el modo, realizar la comprobacion previa de accesos descrita a continuacion. Identificar workspace, identidad, notebook, datos y compute y leer la version remota actual solo con los accesos necesarios verificados.
2. Usar el modo elegido para el analisis y las consultas. Crear o actualizar el notebook remoto en la carpeta aislada del usuario.
3. Revisar el codigo y probarlo en Databricks. Antes de ejecutar cambios de datos, permisos, borrados o afectar recursos ajenos, pedir confirmacion expresa. Solo probar sobre datos autorizados.
4. Presentar cambios, pruebas, costes potenciales y SHA-256 de la version remota. No publicar aun.
5. Tras tu OK, comprobar que el SHA sigue coincidiendo, exportar esa version a `databricks/`, revisar los cambios, crear una rama y abrir un PR. Integrar ramas solo segun las aprobaciones y politica acordadas; nunca actualizar todas indiscriminadamente.

### Comprobacion previa de accesos

Antes de consultar datos o modificar recursos, Copilot comprobara los accesos necesarios para esa tarea e informara de que esta **configurado**, **conectado**, **autenticado** y con **alcance verificado**, indicando lo que no haya podido verificar. No basta con encontrar una entrada en un archivo ni con que la conexion funcionara anteriormente.

- **MCP requeridos**: descubrir sus herramientas y esquemas y verificar una conexion real mediante inicializacion/listado de herramientas o lectura autenticada de metadatos, segun el cliente. Comprobar por separado autenticacion y alcance; una llamada REST no demuestra que el transporte MCP funcione.
- **Modo Genie**: comprobar `databricks-genie`, sus herramientas de consulta y `poll_response`, el espacio autorizado y las tablas incluidas. Si falta una tabla, no ampliar el espacio automaticamente.
- **Databricks directo**: cuando la tarea lo requiera, comprobar CLI/API, herramientas locales, workspace/perfil, identidad, permisos, catalogo, schema y compute con lecturas de metadatos. No se presupone un MCP de Databricks independiente; si se propone otro MCP, primero se descubren y validan sus capacidades. El modo Copilot no consulta ni exige Genie.

Esta comprobacion no ejecuta consultas de datos ni arranca compute, y no instala herramientas ni cambia configuracion, permisos o recursos. Si falta un acceso necesario o falla la autenticacion, Copilot se detendra, explicara el bloqueo y preguntara como proceder antes de reparar o cambiar de modo. Nunca mostrara ni guardara credenciales.

## Herramienta de workspace

`tools/workspace.py` autentica con Azure CLI y opera unicamente en `/Users/<usuario-autenticado>/copilot-databricks-genie/{notebooks,sql}`. Los nombres no llevan extension y solo permiten letras, numeros, guiones y guiones bajos. Python requiere cabecera `# Databricks notebook source`; SQL, `-- Databricks notebook source`.

```powershell
python tools\workspace.py read sql/01_events_summary
# Para actualizar, proporciona el SHA de read y el SOURCE generado; usa --expected absent para crear.
python tools\workspace.py write sql/01_events_summary --expected <SHA256> --source <archivo-temporal>
# Solo tras aprobar la version probada:
python tools\workspace.py export sql/01_events_summary --approved-sha256 <SHA256>
```

`write` tambien acepta `--source -` y contenido UTF-8 por stdin, sin crear un fichero local. Lee de nuevo el notebook despues de escribir y verifica el SHA y el contenido. La herramienta rechaza versiones remotas diferentes y exportaciones que sobrescribirian cambios locales. La comprobacion de version y la escritura no son atomicas en Workspace API: usa un solo editor y evita cambios concurrentes. El SHA no acredita por si solo que una prueba se haya ejecutado ni que el usuario haya aprobado.

Para consultas SQL autorizadas:

```powershell
python tools\workspace.py sql --warehouse-id <WAREHOUSE_ID> --statement "SELECT 1" --confirm-execution
```

El comando espera el estado final, limita la respuesta a 100 filas y puede activar el warehouse. `--confirm-execution` no sustituye la autorizacion del usuario para DDL/DML, borrados o datos ajenos. El comando admite SQL arbitrario; las instrucciones de Copilot no son un control de seguridad.

Para probar notebooks, Copilot puede usar `databricks jobs submit --json <configuracion>` con el notebook remoto y compute autorizado, y consultar el estado final con `databricks jobs get-run <RUN_ID>`. Debe inspeccionar el codigo y parametros antes de ejecutar; una ejecucion puede tener efectos secundarios. Guardar no ejecuta un notebook.

## Estructura y seguridad

- `tools/workspace.py`: lectura, escritura, exportacion y ejecucion SQL explicitas.
- `databricks/`: versiones aprobadas para Git, no una copia automaticamente sincronizada.
- `.github/`: instrucciones, agente, prompt y skill; `tests/`: pruebas locales.
- No borrar notebooks, cambiar permisos ni modificar recursos ajenos sin confirmacion. No incluir secretos ni datos sensibles en el repo.
- La configuracion local MCP puede requerir autenticacion interactiva; una llamada REST exitosa no la valida.

Validacion local: `python -m unittest discover -s tests -v`.
