# ── Cluster Policy (limits to small serverless — Free Edition compatible) ────
resource "databricks_cluster_policy" "stock_pipeline" {
  name = "stock-pipeline-policy"

  definition = jsonencode({
    "spark_version" : {
      "type" : "unlimited",
      "defaultValue" : "auto:latest-lts"
    },
    "num_workers" : {
      "type" : "fixed",
      "value" : 0,
      "hidden" : true
    },
    "spark_conf.spark.databricks.cluster.profile" : {
      "type" : "fixed",
      "value" : "singleNode",
      "hidden" : true
    }
  })
}

# ── Notebook imports ─────────────────────────────────────────────────────────
resource "databricks_notebook" "ingest" {
  path     = "/Shared/stock-analytics/01_ingest"
  language = "PYTHON"
  source   = "${path.module}/../../../databricks/notebooks/01_ingest.py"
}

resource "databricks_notebook" "transform" {
  path     = "/Shared/stock-analytics/02_transform"
  language = "PYTHON"
  source   = "${path.module}/../../../databricks/notebooks/02_transform.py"
}

resource "databricks_notebook" "dashboard" {
  path     = "/Shared/stock-analytics/03_dashboard"
  language = "PYTHON"
  source   = "${path.module}/../../../databricks/notebooks/03_dashboard.py"
}

# ── Databricks Job (daily pipeline) ─────────────────────────────────────────
resource "databricks_job" "daily_pipeline" {
  name = "stock-analytics-daily-pipeline"

  task {
    task_key    = "ingest"
    max_retries = 1

    notebook_task {
      notebook_path = databricks_notebook.ingest.path
      base_parameters = {
        raw_bucket   = var.raw_bucket_name
        iam_role_arn = var.databricks_iam_role_arn
      }
    }

    new_cluster {
      spark_version       = "15.4.x-scala2.12"
      node_type_id        = "Standard_DS3_v2"
      num_workers         = 0
      enable_elastic_disk = true
      policy_id           = databricks_cluster_policy.stock_pipeline.id

      spark_conf = {
        "spark.master"                     = "local[*]"
        "spark.databricks.cluster.profile" = "singleNode"
      }
    }
  }

  task {
    task_key    = "transform"
    max_retries = 1
    depends_on { task_key = "ingest" }

    notebook_task {
      notebook_path = databricks_notebook.transform.path
      base_parameters = {
        raw_bucket    = var.raw_bucket_name
        silver_bucket = var.silver_bucket_name
        gold_bucket   = var.gold_bucket_name
      }
    }

    new_cluster {
      spark_version       = "15.4.x-scala2.12"
      node_type_id        = "Standard_DS3_v2"
      num_workers         = 0
      enable_elastic_disk = true
      policy_id           = databricks_cluster_policy.stock_pipeline.id

      spark_conf = {
        "spark.master"                     = "local[*]"
        "spark.databricks.cluster.profile" = "singleNode"
      }
    }
  }

  task {
    task_key    = "dashboard"
    max_retries = 1
    depends_on { task_key = "transform" }

    notebook_task {
      notebook_path = databricks_notebook.dashboard.path
      base_parameters = {
        gold_bucket = var.gold_bucket_name
      }
    }

    new_cluster {
      spark_version       = "15.4.x-scala2.12"
      node_type_id        = "Standard_DS3_v2"
      num_workers         = 0
      enable_elastic_disk = true
      policy_id           = databricks_cluster_policy.stock_pipeline.id

      spark_conf = {
        "spark.master"                     = "local[*]"
        "spark.databricks.cluster.profile" = "singleNode"
      }
    }
  }

  tags = {
    project = "lakehouse-stock-analytics"
  }
}

# ── SQL Warehouse ─────────────────────────────────────────────────────────────
# Use the existing default warehouse created by Databricks Free Edition
# rather than creating a new one (Free Edition allows only one warehouse)
data "databricks_sql_warehouse" "default" {
  name = "Serverless Starter Warehouse"
}
