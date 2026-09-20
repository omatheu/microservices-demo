# Isolated Cloud Billing export dataset

This stack is deliberately separate from `../terraform`. Planning or applying
the billing dataset therefore cannot create or modify the GKE cluster,
namespaces, Artifact Registry, GitHub federation, workloads, or budgets.

The write gate defaults to `false`. After explicit authorization, copy the
example variables, set it to `true`, review a saved plan and apply exactly that
plan. The result is only the BigQuery API and the protected US multi-region
dataset `online_boutique_billing`.

Cloud Billing Standard usage cost export must then be enabled separately in the
Google Cloud console for billing account `016329-9946EB-FE858E`, selecting
project `microservices-demo-tcc` and this dataset. Terraform does not activate
the billing-account export setting.
