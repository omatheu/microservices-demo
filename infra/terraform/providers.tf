provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_client_config" "current" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.experiment.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.experiment.master_auth[0].cluster_ca_certificate)
}
