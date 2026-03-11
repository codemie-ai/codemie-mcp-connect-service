# CodeMie MCP Connect Service

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
- **Built-in Tunneling**: Integrated ngrok support for easy public access
- **MCP Inspector**: Built-in support for debugging and inspecting MCP servers
- **Security**: Token-based authentication and controlled access to local resources

## Quick Start

### Prerequisites

The Docker build requires the `ai-run-mcp-servers` repository which contains EPAM MCP servers (postgres, puppeteer):

```bash
# Clone via SSH (recommended)
git clone git@gitbud.epam.com:epm-cdme/ai-run-mcp-servers.git ai-run-mcp-servers

# Or clone via HTTPS
git clone https://gitbud.epam.com/epm-cdme/ai-run-mcp-servers.git ai-run-mcp-servers
```

### Building the Docker Image

**Option 1: Using the build script (recommended)**

```bash
# Build with default tag (mcp-connect:latest)
./build.sh

# Build with custom tag
./build.sh codemie-mcp-connect-service:v1.0

# Build without Docker cache
./build.sh --no-cache

# Custom tag + no cache
./build.sh codemie-mcp-connect-service:v1.0 --no-cache
```

**Option 2: Manual build**

```bash
docker build --platform linux/amd64 -t codemie-mcp-connect-service .
```

### Running the Container

**Without ngrok (local network only):**
```bash
docker run -d --restart unless-stopped --name codemie-mcp-connect-service \
  -e ACCESS_TOKEN=<YourSecretAccessToken> \
  -e PORT=3000 \
  -e LOG_LEVEL=info \
  -e LOG_FORMAT=json \
  -p 3000:3000 \
  codemie-mcp-connect-service:latest
```

**With ngrok tunnel (for cloud platforms like CodeMie):**
```bash
docker run -d --restart unless-stopped --name codemie-mcp-connect-service \
  -e ACCESS_TOKEN=<YourSecretAccessToken> \
  -e PORT=3000 \
  -e LOG_LEVEL=info \
  -e LOG_FORMAT=json \
  -e NGROK_AUTHTOKEN=<your_ngrok_token_here> \
  -e NGROK_DOMAIN=<optional_reserved_domain> \
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

### Getting the Public URL

After starting the container with ngrok, retrieve the tunnel URL from the container logs:

```bash
docker logs codemie-mcp-connect-service
```

Look for output similar to:
```
ngrok: url=https://19c8c59a0579.ngrok-free.app
```

Use this URL as the MCP-Connect URL when configuring MCP Servers in CodeMie.

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

**Pre-commit Quality Check (REQUIRED before commit/PR):**
```bash
source .venv/bin/activate && \
poetry run ruff format && \
poetry run ruff check && \
poetry run mypy src/ && \
poetry run black --check src/ tests/ && \
poetry run pytest tests/ --cov=src --cov-report=term-missing && \
poetry run pytest tests/ -m integration --cov=src --cov-report=term-missing
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
  "single_usage": true
}
```

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

## Exposing Container to CodeMie Platform

To use your locally running container with the CodeMie platform:

1. **Start the container** with the ngrok tunnel enabled (as shown above)
2. **Retrieve the Tunnel URL** from the container logs
3. **Configure CodeMie Assistants** to use your MCP servers:
   - Navigate to your CodeMie AI Assistant configuration
   - Add a new MCP server connection or modify an existing one
   - Use the Tunnel URL as MCP-Connect URL
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
| `start-with-ngrok.sh` | Container startup with optional ngrok | Root-owned (755) |

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

## Environment Configuration 🔧

The container supports the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| **Core Configuration** |
| `ACCESS_TOKEN` | - | Bearer token for API authentication (authentication disabled if not set) |
| `PORT` | 3000 | HTTP server port (Docker and start-with-ngrok.sh) |
| **Logging Configuration** |
| `LOG_LEVEL` | info | Logging verbosity level: debug, info, warning, error, critical |
| `LOG_FORMAT` | text | Logging output format: `json` (production, structured) or `text` (development, human-readable) |
| `DEBUG_LOG_BRIDGE_PAYLOAD` | false | Log complete bridge payload at debug level with sensitive data masking (true/false) |
| **MCP Client Configuration** |
| `MCP_CONNECT_INIT_TIMEOUT` | 30000 | MCP session initialization timeout in milliseconds (30 seconds) |
| `MCP_CONNECT_DEFAULT_TIMEOUT` | 120000 | Default timeout for MCP method invocations in milliseconds (2 minutes) |
| `MCP_CONNECT_CLIENT_CACHE_TTL` | 300000 | Client cache TTL in milliseconds before expiration (5 minutes) |
| `MCP_CONNECT_CACHE_CLEANUP_INTERVAL` | 60000 | Cleanup scheduler interval for removing expired clients in milliseconds (1 minute) |
| `MCP_CONNECT_HTTP_TIMEOUT` | 30000 | HTTP connection timeout for streamable-http/SSE transports in milliseconds (30 seconds) |
| `MCP_CONNECT_SSE_READ_TIMEOUT` | 300000 | SSE read timeout for long-polling connections in milliseconds (5 minutes) |
| **Ngrok Tunnel (Docker Deployment)** |
| `NGROK_AUTHTOKEN` | - | Ngrok authentication token for public tunnel (start-with-ngrok.sh) |
| `NGROK_DOMAIN` | - | Optional reserved ngrok domain (e.g., https://my-app.ngrok.app) |

### Volume Mounts

The Docker container supports volume mounting for persistent storage and file system access:
- **SQLite databases**: Mount for persistent database storage
- **Custom configurations**: Mount configuration files as needed
- **Project files**: Mount your project directories for development

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
