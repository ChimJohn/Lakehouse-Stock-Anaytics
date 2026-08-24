output "job_id" {
  value = databricks_job.daily_pipeline.id
}

output "sql_warehouse_id" {
  value = databricks_sql_endpoint.stock_analytics.id
}
