# Installation Guide for KiCad MCP Server

## Prerequisites

### System Requirements
- **Python**: 3.10 or higher
- **KiCad**: 9.0 or higher (for file compatibility)
- **Operating System**: Windows, macOS, or Linux

### KiCad Installation

**Linux:**
```bash
sudo apt install kicad  # Ubuntu/Debian
sudo dnf install kicad  # Fedora
```

**macOS:**
```bash
brew install kicad
```

**Windows:**
Download from [KiCad website](https://www.kicad.org/download/)

## Installation Methods

### Method 1: Install from PyPI (Recommended)

```bash
# Install core package
pip install kicad-mcp-server

# Or install with development dependencies
pip install kicad-mcp-server[dev]
```

### Method 2: Install from Source

```bash
# Clone repository
git clone https://github.com/yourusername/kicad-mcp-server.git
cd kicad-mcp-server

# Install in development mode
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

### Method 3: Install with requirements.txt

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Install testing dependencies (optional, for hardware testing)
pip install -r requirements-test.txt
```

## Dependency Details

### Core Dependencies (requirements.txt)

- **mcp[cli]>=1.2.0** - Model Context Protocol framework
- **fastmcp>=0.1.0** - Fast MCP server implementation
- **kicad-skip>=0.2.5** - KiCad file parsing library
- **pydantic>=2.0.0** - Data validation and parsing
- **python-dotenv>=1.0.0** - Environment variable management
- **jinja2>=3.1.0** - Template engine for code generation

### Development Dependencies (requirements-dev.txt)

- **pytest>=7.0.0** - Testing framework
- **pytest-asyncio>=0.21.0** - Async test support
- **pytest-cov>=4.0.0** - Code coverage reporting
- **black>=23.0.0** - Code formatter
- **ruff>=0.1.0** - Fast Python linter
- **mypy>=1.0.0** - Static type checker

### Testing Dependencies (requirements-test.txt)

These are optional dependencies for running hardware tests with actual hardware interaction:

- **RPi.GPIO>=0.7.0** - Raspberry Pi GPIO (ARM only)
- **smbus2>=0.4.0** - I2C communication
- **spidev>=3.5** - SPI communication (ARM only)
- **pyserial>=3.5** - Serial communication
- **mock>=4.0.0** - Mocking framework

## KiCad Integration

### Verify KiCad Installation

```bash
# Check KiCad version
kicad-cli --version

# Or check pcbnew Python module
python -c "import pcbnew; print(pcbnew.GetBuildVersion())"
```

### Path Configuration

If KiCad is not in your system PATH, you may need to add it:

**Linux/macOS:**
```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH=$PATH:/path/to/kicad/bin
export PYTHONPATH=$PYTHONPATH:/path/to/kicad/lib/python3.10/site-packages
```

**Windows:**
```cmd
REM Add to System Environment Variables
set PATH=%PATH%;C:\Program Files\KiCad\bin
set PYTHONPATH=%PYTHONPATH%;C:\Program Files\KiCad\lib\python3.10\site-packages
```

## Claude Desktop Configuration

### Linux/macOS

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "/path/to/kicad-mcp-server",
      "env": {
        "PYTHONPATH": "/path/to/kicad-mcp-server/src"
      }
    }
  }
}
```

### Windows

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "C:\\path\\to\\kicad-mcp-server",
      "env": {
        "PYTHONPATH": "C:\\path\\to\\kicad-mcp-server\\src"
      }
    }
  }
}
```

## Docker Installation

### Using Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    kicad \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app/

# Install Python dependencies
RUN pip install -r requirements.txt

# Run the server
CMD ["python", "-m", "kicad_mcp_server"]
```

### Build and Run

```bash
# Build image
docker build -t kicad-mcp-server .

# Run container
docker run -v /path/to/projects:/projects kicad-mcp-server
```

## Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Verification

### Test Installation

```bash
# Test MCP server
python -m kicad_mcp_server

# Test KiCad integration
python -c "import pcbnew; print('KiCad integration: OK')"

# Run tests
pytest tests/ -v
```

### Check Available Tools

```python
from kicad_mcp_server import server

# Get MCP server
mcp_server = server.create_server()

# List available tools
print("Available tools:")
for tool in mcp_server._tools.values():
    print(f"  - {tool.name}")
```

## Troubleshooting

### Import Errors

**Problem:** `ImportError: No module named 'pcbnew'`

**Solution:**
```bash
# Ensure KiCad is installed and in PATH
which kicad-cli

# Check Python path
python -c "import sys; print(sys.path)"

# Reinstall with proper path
export PYTHONPATH=$PYTHONPATH:/path/to/kicad/lib/python3.10/site-packages
```

### Permission Errors

**Problem:** `Permission denied` when accessing KiCad files

**Solution:**
```bash
# Fix file permissions
chmod +x /path/to/kicad/bin/kicad-cli

# Or use sudo (not recommended for development)
sudo pip install -r requirements.txt
```

### Docker Issues

**Problem:** `kicad-cli not found` in Docker

**Solution:**
```dockerfile
# Install KiCad in Dockerfile
RUN apt-get update && apt-get install -y kicad

# Or mount KiCad from host
docker run -v /usr/share/kicad:/usr/share/kicad kicad-mcp-server
```

## Updating Installation

```bash
# Update to latest version
pip install --upgrade kicad-mcp-server

# Or from source
git pull origin main
pip install -e .
```

## Uninstallation

```bash
# Uninstall package
pip uninstall kicad-mcp-server

# Clean up virtual environment
deactivate
rm -rf venv/
```

## Next Steps

After installation:

1. **Configure Claude Desktop** - See Configuration section above
2. **Test basic functionality** - Try analyzing a sample schematic
3. **Read documentation** - Check `docs/` directory for detailed guides
4. **Run examples** - See `examples/` directory for usage examples

## Support

- **Documentation**: See `docs/` directory
- **Issues**: [GitHub Issues](https://github.com/yourusername/kicad-mcp-server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/kicad-mcp-server/discussions)

---

**Last Updated**: 2025-01-09
**Python Version**: 3.10+
**KiCad Version**: 9.0+
