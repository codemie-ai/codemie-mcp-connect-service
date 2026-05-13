# Python Image

Lightweight Python 3.12 runtime with Claude Code and Node.js.

## Build

### Base (no simple-deck package)

```bash
docker build -t codemie-python images/python/
```

### With simple-deck package (requires GCP credentials)

```bash
docker build \
  --secret id=google_credentials,src=${HOME}/.config/gcloud/application_default_credentials.json \
  --build-arg INSTALL_SIMPLE_DECK=true \
  -t codemie-python images/python/
```

If you don't have GCP credentials locally, create a stub file:

```bash
touch ${HOME}/.config/gcloud/application_default_credentials.json
```

## Build Args

| ARG                  | Default      | Description                              |
|----------------------|--------------|------------------------------------------|
| `INSTALL_SIMPLE_DECK`| `false`      | Install simple-deck from GCP registry    |
