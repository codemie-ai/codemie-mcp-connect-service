.PHONY: gitleaks

gitleaks:
	docker run --rm -v $$(pwd):/path zricethezav/gitleaks:v8.30.0 dir --no-banner --verbose /path
