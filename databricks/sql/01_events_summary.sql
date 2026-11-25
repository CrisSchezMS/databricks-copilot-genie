-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Resumen de eventos
-- MAGIC Sustituye `source_table` por el nombre completo autorizado antes de ejecutar.
-- MAGIC La consulta es de solo lectura y no se ejecuta al guardar.
-- MAGIC Desarrollado directamente en Databricks; Git requiere aprobacion.

-- COMMAND ----------

-- En un notebook, configura la variable de sustitucion en la sesion, por ejemplo:
-- SET source_table = catalogo.schema.events;
SELECT COUNT(*) AS event_count
FROM ${source_table};
