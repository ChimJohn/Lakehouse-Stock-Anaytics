output "job_id" {
  value = databricks_job.daily_pipeline.id
}

output "sql_warehouse_id" {
  value = data.databricks_sql_warehouse.default.id
}