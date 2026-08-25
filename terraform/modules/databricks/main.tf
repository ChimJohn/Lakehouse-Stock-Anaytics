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
    task_key = "ingest"

    notebook_task {
      notebook_path = databricks_notebook.ingest.path
      base_parameters = {
        raw_bucket    = var.raw_bucket_name
        iam_role_arn  = var.databricks_iam_role_arn
      }
    }

    new_cluster {
      spark_version           = "15.4.x-scala2.12"
      node_type_id            = "Standard_DS3_v2"
      num_workers             = 0
      enable_elastic_disk     = true
      policy_id               = databricks_cluster_policy.stock_pipeline.id

      spark_conf = {
        "spark.master"                                  = "local[*]"
        "spark.databricks.cluster.profile"              = "singleNode"
        "spark.hadoop.fs.s3a.aws.credentials.provider" = "com.amazonaws.auth.InstanceProfileCredentialsProvider"
      }
    }
  }

  task {
    task_key = "transform"
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
    task_key = "dashboard"
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

  # Retry once on failure
  max_retries = 1

  tags = {
    project = "lakehouse-stock-analytics"
  }
}

# ── SQL Warehouse (for Databricks SQL dashboard) ─────────────────────────────
resource "databricks_sql_endpoint" "stock_analytics" {
  name             = "stock-analytics-warehouse"
  cluster_size     = "2X-Small"  # Smallest available — free tier compatible
  max_num_clusters = 1
  auto_stop_mins   = 5

  tags {
    custom_tags {
      key   = "project"
      value = "lakehouse-stock-analytics"
    }
  }
}
