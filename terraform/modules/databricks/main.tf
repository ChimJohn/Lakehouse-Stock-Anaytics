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

# ── Databricks Job (daily pipeline) ──────────────────────────────────────────
resource "databricks_job" "daily_pipeline" {
  name = "stock-analytics-daily-pipeline"

  task {
    task_key    = "ingest"
    max_retries = 1

    notebook_task {
      notebook_path = databricks_notebook.ingest.path
      base_parameters = {
        raw_bucket     = var.raw_bucket_name
        silver_bucket  = var.silver_bucket_name
        aws_access_key = var.aws_access_key
        aws_secret_key = var.aws_secret_key
        aws_region     = var.aws_region
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
        silver_bucket  = var.silver_bucket_name
        gold_bucket    = var.gold_bucket_name
        aws_access_key = var.aws_access_key
        aws_secret_key = var.aws_secret_key
        aws_region     = var.aws_region
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
        gold_bucket    = var.gold_bucket_name
        aws_access_key = var.aws_access_key
        aws_secret_key = var.aws_secret_key
        aws_region     = var.aws_region
      }
    }
  }

  tags = {
    project = "lakehouse-stock-analytics"
  }
}

# ── SQL Warehouse — use existing default warehouse ────────────────────────────
data "databricks_sql_warehouse" "default" {
  name = "Starter Warehouse"
}
