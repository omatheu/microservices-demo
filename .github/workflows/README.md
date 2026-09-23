# GitHub Actions Workflows

This page describes the CI/CD workflows for the Online Boutique app, which run in [Github Actions](https://github.com/GoogleCloudPlatform/microservices-demo/actions).

## Infrastructure

The CI/CD pipelines for Online Boutique run on standard GitHub-hosted runners (Ubuntu). 

We also host a test GKE cluster, which is where the deploy tests run. Every PR has its own namespace in the cluster.

## Workflows

### TCC experiment workflows

- `tcc-pr-ci.yaml` runs the complete local conventional gate set for every
  non-draft pull request targeting `main`. It has no Google Cloud identity;
- `tcc-pr-experiment.yaml` is chained with `workflow_run` and can run staging
  plus the PDT only for same-repository PRs that passed the first workflow and
  satisfy the protected-environment, label and financial gates documented in
  `experiment/pipeline/README.md`.

The second workflow does not deploy to the operational namespace. It is not
active until both workflow files exist on the default branch and the
`tcc-experiment` GitHub Environment has been configured.

The upstream `Deploy Staging - Pull Request`, `Clean up deployment` and manual
release workflows were retired in this fork because they referenced the
upstream `online-boutique-ci` project. The `deployment-tests` job was also
removed from the main-branch workflow. The guarded TCC workflow above is the
only GitHub Actions path with a Google Cloud identity; the main-branch workflow
retains code tests and has no cloud identity.

**Note**: In order for the current CI/CD setup to work on your pull request, you must branch directly off the repo (no forks). This is because the Github secrets necessary for these tests aren't copied over when you fork.

### Code Tests - [ci-pr.yaml](ci-pr.yaml)

These tests run on every commit for every open PR. The upstream workflow runs
the repository's Go and C# unit tests without a cloud identity.


### Main/release tests - [ci-main.yaml](ci-main.yaml)

This workflow repeats the Go and C# unit tests after a push to `main` or a
`release/*` branch. It deliberately has no image publication, GKE deployment,
Google Cloud credential or operational mutation.
