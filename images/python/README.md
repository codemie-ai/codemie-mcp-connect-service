# Python Image

Standalone Python 3.12 scripting runtime. Its base image is the `FROM` line in
`images/python/Dockerfile`.

This is a separate additional image. It is not the CodeMie MCP Connect Service — that one is
built from the `Dockerfile` at the repository root and is the image the Helm chart under
`deploy-templates/` deploys.

Packages are pinned exactly in `requirements.txt` and installed into `/opt/venv`, created as
root so it stays read-only for the unprivileged runtime user (`1001:1001`). There is no lock
file and no test suite; a rebuild is the only verification available.

## Build

### Base (no simple-deck package)

```bash
docker build -t codemie-python images/python/
```

### With the simple-deck package

```bash
docker build --build-arg INSTALL_SIMPLE_DECK=true -t codemie-python images/python/
```

`simple-deck` installs from PyPI in the same layer as `requirements.txt`. No credentials and no
extra index are required.

## Build args

| ARG                    | What it controls                                          |
|------------------------|-----------------------------------------------------------|
| `INSTALL_SIMPLE_DECK`  | Whether `simple-deck` is installed from PyPI               |
| `SIMPLE_DECK_VERSION`  | The `simple-deck` version, when the above is `true`        |
| `PIP_VERSION`          | The pip version the venv is upgraded to                    |
| `LIBCAIRO2_VERSION`    | libcairo2 apt pin, required by CairoSVG and simple-deck    |
| `LIBRAQM0_VERSION`     | libraqm0 apt pin, complex text layout for Pillow           |

Defaults are not repeated here; they change with routine version bumps. Read them from the file:

```bash
grep -n '^ARG' images/python/Dockerfile
```
