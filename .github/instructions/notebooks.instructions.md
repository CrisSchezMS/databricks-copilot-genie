---
applyTo: "databricks/notebooks/**/*.py"
---
# Notebooks Databricks
- Mantén el formato SOURCE de Databricks y separa celdas con `# COMMAND ----------`.
- Parametriza catalogo, schema y tabla mediante widgets; valida identificadores antes de usarlos en SQL.
- Usa DataFrames cuando sea apropiado, proyecta las columnas necesarias y limita la salida interactiva.
- Evita secretos, rutas personales y operaciones destructivas. Guardar no ejecuta el notebook.
- Mantén el ejemplo reproducible con datos sinteticos y documenta el compute requerido.
