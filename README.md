# CodeMie MCP Connect Service

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-codemie.ai-informational)](https://codemie.ai)
[![Docs](https://img.shields.io/badge/docs-docs.codemie.ai-informational)](https://docs.codemie.ai)

     ██████╗ ██████╗ ██████╗ ███████╗███╗   ███╗██╗███████╗
    ██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗ ████║██║██╔════╝
    ██║     ██║   ██║██║  ██║█████╗  ██╔████╔██║██║█████╗
    ██║     ██║   ██║██║  ██║██╔══╝  ██║╚██╔╝██║██║██╔══╝
    ╚██████╗╚██████╔╝██████╔╝███████╗██║ ╚═╝ ██║██║███████╗
     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚═╝╚══════╝

    ███╗   ███╗ ██████╗██████╗      ██████╗ ██████╗ ███╗   ██╗███╗   ██╗███████╗ ██████╗████████╗
    ████╗ ████║██╔════╝██╔══██╗    ██╔════╝██╔═══██╗████╗  ██║████╗  ██║██╔════╝██╔════╝╚══██╔══╝
    ██╔████╔██║██║     ██████╔╝    ██║     ██║   ██║██╔██╗ ██║██╔██╗ ██║█████╗  ██║        ██║
    ██║╚██╔╝██║██║     ██╔═══╝     ██║     ██║   ██║██║╚██╗██║██║╚██╗██║██╔══╝  ██║        ██║
    ██║ ╚═╝ ██║╚██████╗██║         ╚██████╗╚██████╔╝██║ ╚████║██║ ╚████║███████╗╚██████╗   ██║
    ╚═╝     ╚═╝ ╚═════╝╚═╝          ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝ ╚═════╝   ╚═╝

**Platform for AI-Native Delivery, Modernization, and Business.**

CodeMie is an open platform that lets teams build, orchestrate, and scale AI agents across the entire software lifecycle — from planning and coding to testing, deployment, and operations. It unites intelligent assistants, multi-agent workflows, deep integrations, and project knowledge in one system.

**What you can do with CodeMie:**

- 🚀 **AI-Native SDLC & Delivery** — Automate every phase of the software lifecycle: discovery, architecture, development, testing, and deployment with purpose-built AI agents.
- 🔄 **AI Migration & Modernization** — Migrate and modernize legacy systems and mainframes using AI-powered analysis, code exploration (AICE), and automated transformation workflows.
- 💼 **AI for Business & Operations** — Deploy AI agents across non-engineering functions such as finance, HR, sales, and support.

**This repository — `codemie-mcp-connect-service` — is the MCP bridge component of the CodeMie platform.** It provides HTTP/HTTPS-to-stdio protocol translation, enabling cloud-based CodeMie AI agents to communicate with locally running MCP servers over any transport (stdio, streamable-http, SSE). Deployed as a Docker container.

🌐 **Website:** [codemie.ai](https://codemie.ai)
📖 **Documentation:** [docs.codemie.ai](https://docs.codemie.ai)
🖥️ **CLI tool:** [codemie-code](https://github.com/codemie-ai/codemie-code)

A comprehensive containerized solution that bridges cloud-based AI services with local Model Context Protocol (MCP) servers.

Built with Python, FastAPI, and Docker 🐳

## Description 🗒

CodeMie MCP Connect Service solves a critical challenge in the MCP ecosystem: enabling cloud-based AI platforms like CodeMie to seamlessly interact with local MCP servers that typically use stdio transport. By providing HTTP/HTTPS to stdio protocol translation with built-in tunneling support, developers can leverage the full power of local MCP tools in cloud environments without compromising security or requiring complex setup procedures.

### Technology Stack 🛠

**Core Runtime:**
- Python 3.12+ with FastAPI 0.121.0+
- Uvicorn ASGI server
- Pydantic 2.12.0+ for validation
- MCP Python SDK v1.21.0+

**Additional Runtimes:**
- Node.js LTS (JavaScript/TypeScript MCP servers)
- OpenJDK 11, 17, 21 (Java-based MCP servers)
- Go 1.25.1 (Go-based MCP servers)
- Apache Maven 3.9.11

**Development Tools:**
- Testing: pytest + pytest-asyncio + pytest-cov
- Type Checking: mypy (strict mode)
- Code Quality: black (formatting), ruff (linting)
- Package Management: Poetry 2.1.3, uv (Python), npm (Node.js)

**Features:**
- **Cloud Integration**: Enables cloud-based AI services to interact with local stdio-based MCP servers
- **Protocol Translation**: Converts HTTP/HTTPS requests to MCP (stdio, streamable-http, SSE) communication seamlessly
- **Client Caching**: Intelligent connection reuse with 5-minute TTL and ping validation
- **Single-Usage Mode**: Immediate resource cleanup for one-time operations
- **Pre-installed MCP Servers**: Comprehensive collection of popular MCP servers ready to use
- **MCP Inspector**: Built-in support for debugging and inspecting MCP servers
- **Security**: Token-based authentication and controlled access to local resources

## Quick Start

### Building the Docker Image

```bash
docker build --platform linux/amd64 -t codemie-mcp-connect-service .
```

### Running the Container

**Basic run:**
```bash
docker run -d --restart unless-stopped --name codemie-mcp-connect-service \
  -e ACCESS_TOKEN=<YourSecretAccessToken> \
  -e PORT=3000 \
  -e LOG_LEVEL=info \
  -e LOG_FORMAT=json \
  -p 3000:3000 \
  codemie-mcp-connect-service:latest
```

**With MCP Inspector (debugging):**
```bash
docker run -d --restart unless-stopped --name codemie-mcp-connect-service \
  -e ACCESS_TOKEN=<YourSecretAccessToken> \
  -e PORT=3000 \
  -p 3000:3000 \
  -p 58080:58080 \
  -p 59000:59000 \
  codemie-mcp-connect-service:latest
```

## Development

### Local Development Setup

**Prerequisites:**
- Python 3.12+, pip, [Poetry](https://python-poetry.org/)
- Virtual environment (MANDATORY)

**Setup:**
```bash
# ALWAYS activate virtual environment first
source .venv/bin/activate

# Install dependencies
poetry install

# Run development server
poetry run uvicorn mcp_connect.main:app --reload --port 3000
```

### Testing 🧪

```bash
source .venv/bin/activate

poetry run pytest                    # Unit tests only
poetry run pytest -m integration     # Integration tests
poetry run pytest --cov=src          # With coverage
```

### Code Quality 📝

**Linting & Formatting:**
```bash
poetry run ruff format               # Format code
poetry run ruff check                # Lint code
poetry run mypy src/                 # Type check
poetry run black src/ tests/         # Black formatting
```

**Security Scanning:**
```bash
make gitleaks                        # Scan for secrets and credentials
```

**Pre-commit Quality Check (REQUIRED before commit/PR):**
```bash
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing && \
make gitleaks
```

All checks MUST pass (exit code 0).

## Client Caching and Single-Usage Mode

The service provides two operational modes for MCP client management:

### Default Caching Mode

By default, the service caches MCP client connections for optimal performance:
- **Automatic Reuse**: Clients are cached and reused for subsequent requests with the same configuration
- **Connection Validation**: Cached clients are validated with ping requests before reuse
- **TTL Management**: Clients are automatically cleaned up after 5 minutes of inactivity (configurable via `MCP_CONNECT_CLIENT_CACHE_TTL`)
- **Performance Benefits**: Eliminates connection setup overhead for repeated requests

### Single-Usage Mode

For scenarios requiring immediate resource cleanup or one-time operations, use the `single_usage` parameter:

```json
{
  "serverPath": "npx",
  "method": "tools/list",
  "args": ["-y", "@upstash/context7-mcp"],
  "params": {},
  "single_usage": true,
  "user_context": {"user": {"id": "u-1", "email": "user@example.com"}}
}
```

`user_context` is optional and opaque: the service does not inspect or validate it, and forwards it
to downstream MCP servers on `tools/call` requests as `_meta["codemie.ai/user-context"]`. Servers
that do not read `_meta` ignore it.

**When to use Single-Usage Mode:**
- **One-time operations**: Bulk processing, data migrations, testing
- **Resource-constrained environments**: Immediate memory cleanup required
- **Unique configurations**: Avoid cache pollution from specialized setups
- **Batch processing**: When client reuse is not beneficial

**Single-Usage Behavior:**
1. **No Caching**: Client is created fresh for each request
2. **Immediate Cleanup**: Client and transport are closed immediately after request completion
3. **Resource Management**: Prevents memory buildup for infrequent operations
4. **Higher Latency**: Trade-off of connection setup time for immediate resource cleanup

## Server Instructions on `tools/list`

An MCP server may return an `instructions` string in its `initialize` handshake,
describing how its tools are meant to be used. For the `tools/list` method the
bridge attaches that string to the response as a top-level `instructions` field:

```json
{
  "tools": [{ "name": "echo", "description": "Echo the given text." }],
  "instructions": "Always call the tool with sysparm_help=true before first use."
}
```

The field is additive and optional. A server that sends no instructions produces
a response with no `instructions` key, exactly as before. The field behaves the
same in cached and single-usage mode, is attached to every page of a paginated
`tools/list`, and is never attached to any other method.

If the `tools/list` result already carries an `instructions` key of its own, the
server's value is kept and the handshake value is dropped, with a warning logged.
The bridge never overwrites server-authored content.

The text comes from a third-party server and ends up in an LLM system prompt, so
the bridge cleans it once, when the handshake is captured: control characters and
invisible or bidi-reordering characters are removed (tab, newline and carriage
return survive, and zero-width joiners are kept for emoji), and the text is capped
at `MCP_CONNECT_MAX_INSTRUCTIONS_CHARS` characters. Longer text is cut at a word
boundary and ends with a `[instructions truncated by MCP Connect]` marker, and a
warning with the original length is logged once per session. An invalid or
non-positive value falls back to 8192 with a warning. Nothing else about the
wording is changed — a consumer that splices the text into a prompt still owns
escaping it for that context.

## Exposing Container to CodeMie Platform

To use your container with the CodeMie platform, it must be reachable from the CodeMie cloud
service — deploy it behind your own ingress, load balancer, or tunnel of choice.

1. **Start the container** and expose it publicly through your chosen ingress/tunnel
2. **Configure CodeMie Assistants** to use your MCP servers:
   - Navigate to your CodeMie AI Assistant configuration
   - Add a new MCP server connection or modify an existing one
   - Use your container's public URL as MCP-Connect URL
   - Include your ACCESS_TOKEN in the MCP Server configuration

```json
{
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "env": {
    "DEFAULT_MINIMUM_TOKENS": "10000"
  },
  "auth_token": "<YourSecretAccessToken>"
}
```

**Optional**: For single-usage mode (immediate cleanup after each request):
```json
{
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "env": {
    "DEFAULT_MINIMUM_TOKENS": "10000"
  },
  "auth_token": "<YourSecretAccessToken>",
  "single_usage": true
}
```

4. **Test the connection** by listing available tools or calling a specific MCP server function

## Container Security Model

The container implements a multi-layered security approach:

### Protected System Scripts

Three critical scripts are installed in `/usr/local/bin/` with root-only write permissions:

| Script | Purpose | Protection Level |
|--------|---------|------------------|
| `create_python_venv.sh` | Creates Python virtual environments | Root-owned (755) |
| `run_in_python_venv.sh` | Executes Python in virtual environments | Root-owned (755) |
| `start.sh` | Container startup | Root-owned (755) |

**Security Characteristics:**
- **Ownership**: `root:root` - only root user can modify or delete
- **Permissions**: `755` (rwxr-xr-x) - read and execute for all, write for root only
- **Immutability**: The `codemie` user (UID 1001) cannot modify or delete these scripts
- **Availability**: Scripts remain in PATH and executable from anywhere in the container

### User Workspace

The `codemie` user operates with restricted privileges:

- **Home Directory**: `/home/codemie/` - full read/write/execute permissions
- **Working Directory**: Full control over `/home/codemie/` for project files and data
- **System Scripts**: Read and execute only - cannot modify system-critical scripts
- **System Directories**: Read and execute access to `/usr/local/bin/`, `/usr/lib/jvm/`, Maven, and MCP tools

This design ensures that:
1. System-critical functionality remains intact and tamper-proof
2. Users have a safe workspace (`/home/codemie/`) for all development activities
3. Accidental or malicious script modifications are prevented
4. Container behavior remains consistent and reliable across all sessions

## MCP Inspector

The container includes built-in support for the MCP Inspector, a powerful tool for debugging and testing MCP servers.

### Running MCP Inspector

1. **Connect to the container** via docker exec:
   ```bash
   docker exec -it codemie-mcp-connect-service /bin/bash
   ```

2. **Run the MCP Inspector**:
   ```bash
   HOST=0.0.0.0 CLIENT_PORT=58080 SERVER_PORT=59000 npx @modelcontextprotocol/inspector
   ```

3. **Access the Inspector** in your browser at `http://localhost:58080`

The MCP Inspector allows you to:
- Run MCP servers and check/validate their capabilities
- Test server methods and tool calls interactively
- Debug server responses and troubleshoot issues
- Explore server schemas and documentation

## Python Virtual Environment Management

The container includes two specialized shell scripts installed system-wide in `/usr/local/bin/` for managing Python virtual environments. These scripts are globally accessible from anywhere in the container and are designed to work seamlessly with MCP CLI servers like the [CLI MCP Server](https://github.com/MladenSU/cli-mcp-server).

**Installation Location:** `/usr/local/bin/` (available in PATH)
**Execution Context:** Runs as `codemie` user (UID 1001)
**No prefix required:** Call scripts directly without `./` prefix

### create_python_venv.sh

Creates and configures Python virtual environments using the fast `uv` package manager.

**Usage:**
```bash
create_python_venv.sh <absolute_path_to_venv_folder> [absolute_path_to_requirements_file]
```

**Examples:**
```bash
# Create a basic virtual environment
create_python_venv.sh /home/codemie/myproject

# Create virtual environment and install dependencies
create_python_venv.sh /home/codemie/myproject /home/codemie/myproject/requirements.txt
```

**Features:**
- Uses `uv venv` for fast virtual environment creation
- Automatically creates target directories if they don't exist
- Validates absolute paths for security (prevents directory traversal)
- Optionally installs dependencies from requirements.txt
- Provides detailed status feedback and error handling
- Globally accessible from any directory in the container

### run_in_python_venv.sh

Executes Python scripts and commands within existing virtual environments.

**Usage:**
```bash
run_in_python_venv.sh <absolute_path_to_venv_folder> [python_script_and_arguments...]
```

**Examples:**
```bash
# Run a Python script
run_in_python_venv.sh /home/codemie/myproject script.py arg1 arg2

# Execute Python code directly
run_in_python_venv.sh /home/codemie/myproject -c "print('Hello World')"

# Run Python modules
run_in_python_venv.sh /home/codemie/myproject -m pip list

# Install packages
run_in_python_venv.sh /home/codemie/myproject -m pip install requests
```

**Features:**
- Automatic virtual environment activation and validation
- Support for environment variable expansion in arguments
- Comprehensive error handling and validation
- Security-focused with absolute path requirements
- Compatible with any Python script or module execution
- Globally accessible from any directory in the container

### Integration with MCP CLI Servers

These scripts are particularly useful when combined with MCP CLI servers, enabling AI assistants to:

1. **Create isolated Python environments** for different projects or experiments
2. **Install specific package versions** without conflicts
3. **Execute Python code safely** within controlled environments
4. **Manage multiple Python projects** with different dependency requirements

**Example MCP CLI Server Configuration:**
```json
{
  "command": "uvx",
  "args": ["cli-mcp-server"],
  "env": {
    "TIMEOUT": "3000",
    "ALLOWED_DIR": "/home/codemie",
    "ALLOWED_FLAGS": "all",
    "COMMAND_TIMEOUT": "3000",
    "ALLOWED_COMMANDS": "all",
    "MAX_COMMAND_LENGTH": "70000",
    "ALLOW_SHELL_OPERATORS": "true"
  },
  "auth_token": "<YourSecretAccessToken>"
}
```

**Complete Workflow Example:**

From anywhere inside the container, execute:

```bash
# Set project directory (recommended: /home/codemie for write permissions)
PROJECT=/home/codemie/my-python-project

# Step 1: Create virtual environment
create_python_venv.sh ${PROJECT}

# Step 2: Install dependencies (if requirements.txt exists)
create_python_venv.sh ${PROJECT} ${PROJECT}/requirements.txt

# Step 3: Run your application
run_in_python_venv.sh ${PROJECT} app.py --port 8000

# Step 4: Run tests
run_in_python_venv.sh ${PROJECT} -m pytest tests/

# Step 5: Install additional packages as needed
run_in_python_venv.sh ${PROJECT} -m pip install requests pandas numpy
```

**Key Benefits:**
- **Global Accessibility:** Scripts work from any directory in the container
- **No Navigation Required:** No need to cd to script location
- **Secure by Design:** Absolute path validation prevents directory traversal attacks
- **User Context:** Runs as `codemie` user with appropriate permissions
- **Fast Performance:** Uses `uv` package manager for rapid environment creation

This integration allows AI assistants to dynamically create Python environments, install packages, and execute Python applications with full isolation and security controls.

## Available Technologies and MCP Servers

### Runtime Environments

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.12+ | Primary runtime for MCP Connect Service (FastAPI) and Python-based MCP servers |
| **Node.js** | LTS | JavaScript/TypeScript MCP servers |
| **OpenJDK** | 11, 17, 21 | Java-based MCP servers and applications |
| **Go** | 1.25.1 | Building and running Go-based MCP servers (GitHub MCP Server) |
| **Apache Maven** | 3.9.11 | Java project build and dependency management |

### Development Tools

| Tool | Purpose |
|------|---------|
| **uv** | Fast Python package manager and project manager |
| **npm** | Node.js package manager |
| **git** | Version control system |
| **wget/curl** | HTTP clients for API testing |
| **jq** | JSON processing and manipulation |
| **gh** | GitHub CLI for GitHub integration |
| **nano/mc** | Text editors and file managers |
| **build-essential** | Compilation tools and libraries |

### Media and System Tools

| Tool | Purpose |
|------|---------|
| **FFmpeg** | Video and audio processing |
| **ExifTool** | Metadata extraction and manipulation |
| **Chromium** | Headless browser for web automation |
| **Font Packages** | International font support for various languages |

### Pre-installed MCP Servers

#### Core MCP Servers (from modelcontextprotocol/servers)
The container includes all servers from the official MCP servers repository:
- **Filesystem** - File system operations and management
- **Git** - Git repository operations and version control
- **GitHub** - GitHub API integration and repository management
- **Google Drive** - Google Drive file operations
- **Slack** - Slack workspace integration
- **PostgreSQL** - PostgreSQL database operations
- **MySQL** - MySQL database operations
- **SQLite** - SQLite database operations
- **Fetch** - HTTP request and web scraping capabilities
- **Puppeteer** - Web automation and scraping
- **Brave Search** - Web search capabilities
- **Everything** - Windows file search (Everything search engine)
- **Memory** - Persistent memory and context management

#### Archived MCP Servers (from modelcontextprotocol/servers-archived)
Additional servers from the archived repository for extended functionality.

#### Third-party MCP Servers

| Server | Version | Capabilities |
|--------|---------|--------------|
| **GitHub MCP Server** | v0.20.2 | Advanced GitHub integration built in Go, enterprise features |
| **Fetch MCP** | Latest  | Enhanced HTTP requests and web data fetching |

## Exporting Files from stdio Servers

A stdio MCP server that writes files (shell, Filesystem) can hand them to the user as downloads. The model names the files, or the server returns them as `resource_link` items; MCP-Connect reads them after the call and appends (or, for links, substitutes) embedded `resource` items in the `tools/call` result.

**Before you opt in:** deploy this service first (it accepts `conversation_id` on `/bridge`; an older one rejects the unknown field with 400), then the CodeMie backend change that publishes embedded resources as downloads and sends `conversation_id` (codemie !4252). Until then every call carries the file bytes and no Download chip appears. Plugin (enterprise) MCP tools get no chips until EPMCDME-16353.

**Opt in per server** by setting `CODEMIE_EXPORT_FILES` to `true`, `1`, `yes` or `on` (any case, string or JSON boolean) in the server's `env`. Export is off by default and applies to stdio servers only; HTTP and SSE servers never get it. The key is removed before the server starts, so it never reaches the child process or the client cache key.

```json
{
  "command": "uvx",
  "args": ["cli-mcp-server"],
  "env": {
    "ALLOWED_DIR": "/home/codemie",
    "UV_CONSTRAINT": "/etc/uv-constraints.txt",
    "CODEMIE_EXPORT_FILES": "true"
  }
}
```

`UV_CONSTRAINT` is needed for `uvx` servers: the MCP SDK passes only a short list of environment variables to the child process, so the image-wide `UV_CONSTRAINT` is not inherited and `uvx` resolves `mcp` 2.x, which `cli-mcp-server` cannot start with.

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/codemie"],
  "env": {
    "CODEMIE_EXPORT_FILES": "true"
  }
}
```

On an opted-in server, `tools/list` adds an optional `codemie_export_files` array parameter to every tool (never added to `required`). The model lists the paths the user should receive. `codemie_export_files` is stripped from every stdio `tools/call`, opted in or not, so the server never sees it. The parameter's description tells the model to write such files under `/home/codemie/codemie_export`. The assistant instructions may repeat it: "When you create files for the user, write them under /home/codemie/codemie_export and list the same paths in codemie_export_files."

**Each conversation has its own export folder.** Only files under `/home/codemie/u-<16 hex>/c-<16 hex>/` can be exported or delivered by link: the first hex is the start of the SHA-256 of the request's `user_id`, the second of its `conversation_id` (or `workflow_execution_id` for a workflow run without a conversation). A request with neither, as from an older backend, uses `/home/codemie/u-<16 hex>/`. The backend sends the person who made the call as `user_id`, also in a global assistant or workflow (codemie !4252), so runners of one workflow get separate folders. On an opted-in `tools/call`, MCP-Connect maps the path `/home/codemie/codemie_export` in every string argument (and in `codemie_export_files`) to that folder and creates it before the tool runs, so the model writes there directly; the `tools/list` description stays the same for every user because the backend caches it. Only the whole path component is mapped (`/home/codemie/codemie_export_dir` stays as written), and it is mapped in every string, file contents written through the call included. It is a path rather than a placeholder because models turned a `{...}` placeholder into a real folder of their own (round-3 re-run). A path outside the folder is refused, and the note names the folder, so the model writes the file there again and exports it. A call without `user_id` exports nothing and gets one note; its links and `/home/codemie/codemie_export` are left untouched. The folder names are plain hashes, not secrets. They keep same-named files of different users and conversations apart, so a model that lists a file before its script writes it gets "file not found" rather than an earlier conversation's report. A file from an earlier turn of the same conversation can still be exported by naming it.

**Opt-in is not an access control.** It only decides where the parameter appears. Export and links read only the caller's folder; a server that itself reaches `/home/codemie` can still read other users' folders, because every server runs as the same uid (EPMCDME-16903). Opt in only servers whose reach over `/home/codemie` you already accept. Links widen this: the same switch also resolves `resource_link` items the server returns, so a server can name files itself. Opt in only servers whose output you also trust to name files; a stdio proxy to a remote server does not meet this.

**Isolation assumes only the backend can call `/bridge`.** The folder is chosen by the `user_id` in the request body. Authentication is off when `ACCESS_TOKEN` is unset (the chart default), and the token, when set, is shared by all server configs rather than tied to a user. Anyone else who can reach the Service can therefore name any user's id and read that user's exported files. Such a caller could already run commands as the service user, so this is a precondition rather than a new exposure: restrict the Service to the backend (NetworkPolicy) or set `ACCESS_TOKEN`.

**One server process serves all users.** The client cache key has no user, so a cached stdio process handles calls from different users. Export does not depend on the process's state: the `/home/codemie/codemie_export` mapping and the checks are per call. `cli-mcp-server` runs every command in a fresh subprocess, so a `cd` does not carry into the next call (measured); a server that keeps a working folder between calls would carry it across users.

**Sizing.** Export folders are not cleaned up. They live on the `/home/codemie` volume (an `emptyDir` without `sizeLimit` when the root filesystem is read-only) until the pod restarts, so size the pod's ephemeral storage for the reports users generate between restarts. A sweep is EPMCDME-16903.

**Path rules**
- Relative paths resolve against the call's first absolute `directory`, `cwd` or `working_directory` argument, otherwise against `/home/codemie` (the server's working directory), so a bare name the server wrote there is refused rather than matched to an older file in the user's folder. Absolute paths are accepted inside the user's export folder.
- Only regular files are exported. Symlinks (in any path component), `..` segments, hidden path segments (such as `.ssh`), FIFOs, devices, directories, missing files and paths outside the user's export folder are refused.
- An empty file is refused with the reason "file is empty" (the backend does not accept an empty embedded blob).
- Every refused or over-limit file is listed with its reason in one appended text item. Nothing is dropped silently.
- When the result has `isError=true`, nothing is exported and one text item, "export skipped: the call failed", is added.
- Limits: see the `MCP_CONNECT_EXPORT_*` variables in Environment Configuration below. The in-flight budget is pod-wide only while the service runs one worker and one replica.

**Links (`resource_link`)**
- On an opted-in stdio server, each `file:///` `resource_link` in a successful `tools/call` result is read from disk and replaced in place by the embedded file. Servers already opted in gain this on deploy; no new switch.
- The server must return the link after the file is complete. A file still being written is delivered as it is.
- Links use the same per-user root, path rules and budgets as model-named paths. A refused or unreadable link (wrong scheme, query or fragment, encoded `/`, `.` or NUL, non-canonical path, over a limit, missing) becomes one text note, `<uri>: <reason>`, at the link's position.
- At most `MCP_CONNECT_EXPORT_MAX_LINKS` links are read per call; the rest are left unread and one summary note replaces them.
- A link to a file already delivered in the same call (same real path) is dropped silently. A different file with the same name is delivered too; the backend names the second one `name (2).ext`.
- Links in `isError` results, and in results of servers that are not opted-in or not stdio, are left untouched.

**Known behavior**
- A file is exported only when it is named by the model or returned by the server as a link. Nothing is inferred from file state.
- A file from an earlier turn can be exported by naming it in a later call, or delivered through `read_media_file`.
- Exporting the same file in two calls produces two chips (`name (2).ext`); duplicates are removed only within one call.
- The parameter appears only after the backend's toolkit cache expires, up to 600 s after opting in.
- The name `codemie_export_files` is reserved: a server parameter with that name loses its value on every stdio server.

## Environment Configuration 🔧

The container supports the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| **Core Configuration** |
| `ACCESS_TOKEN` | - | Bearer token for API authentication (authentication disabled if not set) |
| `PORT` | 3000 | HTTP server port (Docker and start.sh) |
| **Logging Configuration** |
| `LOG_LEVEL` | info | Logging verbosity level: debug, info, warning, error, critical |
| `LOG_FORMAT` | text | Logging output format: `json` (production, structured) or `text` (development, human-readable) |
| `DEBUG_LOG_BRIDGE_PAYLOAD` | false | Log complete bridge payload at debug level with sensitive data masking (true/false) |
| **MCP Client Configuration** |
| `MCP_CONNECT_INIT_TIMEOUT` | 30000 | MCP session initialization timeout in milliseconds (30 seconds) |
| `MCP_CONNECT_DEFAULT_TIMEOUT` | 120000 | Default timeout for MCP method invocations in milliseconds (2 minutes) |
| `MCP_CONNECT_MAX_INSTRUCTIONS_CHARS` | 8192 | Maximum length of server-supplied `instructions` relayed on `tools/list`; longer text is truncated |
| `MCP_CONNECT_CLIENT_CACHE_TTL` | 300000 | Client cache TTL in milliseconds before expiration (5 minutes) |
| `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` | 60000 | Cleanup scheduler interval for removing expired clients in milliseconds (1 minute) |
| `MCP_CONNECT_HTTP_TIMEOUT` | 30000 | HTTP connection timeout for streamable-http/SSE transports in milliseconds (30 seconds) |
| `MCP_CONNECT_SSE_READ_TIMEOUT` | 300000 | SSE read timeout for long-polling connections in milliseconds (5 minutes) |
| **File Export (EPMCDME-14735)** |
| `MCP_CONNECT_EXPORT_MAX_FILE_BYTES` | 52428800 | Maximum size of one exported file in bytes (50 MiB) |
| `MCP_CONNECT_EXPORT_MAX_CALL_BYTES` | 52428800 | Maximum total size of files exported by one call in bytes (50 MiB) |
| `MCP_CONNECT_EXPORT_MAX_FILES` | 20 | Maximum number of files exported by one call |
| `MCP_CONNECT_EXPORT_MAX_LINKS` | 50 | Maximum number of `resource_link` items resolved per call; the rest are left unread and replaced by one note |
| `MCP_CONNECT_EXPORT_MAX_INFLIGHT_BYTES` | 52428800 | Pod-wide budget of file bytes being sent at once (50 MiB). Base64 plus JSON costs about 5x the file size, so the default is about 250 MiB of memory on a 1Gi pod that also holds the warm stdio servers. Measured locally with 7 warm servers (about 550 MiB): one 50 MiB export adds about 210 MiB, and two concurrent exports under a 100 MiB budget peaked at about 910 MiB of 1 GiB. Raise it only after measuring with your own server mix |

### Volume Mounts

The Docker container supports volume mounting for persistent storage and file system access:
- **SQLite databases**: Mount for persistent database storage
- **Custom configurations**: Mount configuration files as needed
- **Project files**: Mount your project directories for development

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) for commit conventions, branch workflow, dev setup, and code standards. All participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License Compliance

**Check licenses of production dependencies**:
```bash
poetry run pip-licenses --packages $(poetry show --only main | awk '{print $1}' | tr '\n' ' ')
```
This checks licenses only for production packages (excludes dev dependencies like `pytest`, etc.).

## Documentation 📚

- **[CLAUDE.md](./CLAUDE.md)** - Comprehensive development guide for AI agents and developers
- **[API Documentation](./src/mcp_connect/)** - FastAPI application structure and modules
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)** - Official MCP SDK documentation

**Ready to bridge the gap between local MCP capabilities and cloud-based AI platforms.**
