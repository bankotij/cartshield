# Project verification

Run `sh .ci/check.sh` from a clean checkout with the Node/Python/package-manager versions listed in `project-checks.yml`. Python installs should run inside a virtual environment. The script installs the locked dependencies and runs this project's selected checks; failures stop execution.

`project-checks.yml` is a prepared GitHub Actions workflow, **not an active workflow**. GitHub rejected workflow creation because the connected OAuth login lacks the `workflow` scope. After authorizing that scope, place it at `.github/workflows/project-checks.yml` to run on pushes and pull requests. No deployment or secrets are configured by this template.

Checkout payload validation runs without services. The four existing HTTP integration tests skip unless the API is running at localhost:8000; a green local exit with skips is not full checkout integration verification. Start the documented Docker stack to exercise those tests.
