# Databricks notebook source
# MAGIC %md
# MAGIC # Explorar eventos sinteticos
# MAGIC Configura los widgets antes de ejecutar. Esta exploracion es de solo lectura.

# COMMAND ----------

import re

for name, default in [("catalog", "main"), ("schema", "copilot_genie_demo"), ("table", "events")]:
    dbutils.widgets.text(name, default)

parts = [dbutils.widgets.get(name) for name in ("catalog", "schema", "table")]
if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
    raise ValueError("Los nombres deben ser identificadores sencillos de Unity Catalog")
source = ".".join(f"`{part}`" for part in parts)

# COMMAND ----------

events = spark.table(source)
print(f"Tabla: {source}; filas: {events.count()}")
display(events.limit(20))
