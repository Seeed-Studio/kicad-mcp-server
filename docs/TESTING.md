# Testing Guide for KiCad MCP Server

This guide will help you test all the newly implemented features of the KiCad MCP Server.

## Test Preparation

### 1. Install Dependencies

```bash
# Navigate to project directory
cd kicad-mcp-server

# Install core dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# (Optional) Install hardware testing dependencies
pip install -r requirements-test.txt
```

### 2. Verify Installation

```bash
# Check Python version (requires 3.10+)
python --version

# Verify KiCad installation
kicad-cli --version

# Test Python environment imports
python -c "
from kicad_mcp_server.tools import validation, pin_analysis, device_tree, test_generation
print('OK All modules imported successfully')
"
```

### 3. Prepare Test Files

If you don't have existing KiCad files, you can use sample files from the project or create simple test files:

```bash
# Create test directory
mkdir -p test_files

# Check for sample files
ls -la examples/
```

## Basic Functionality Testing

### Test 1: Verify Module Imports

```python
# test_imports.py
def test_module_imports():
    """Test that all new modules can be imported correctly"""
    try:
        from kicad_mcp_server.tools import validation
        from kicad_mcp_server.tools import pin_analysis
        from kicad_mcp_server.tools import device_tree
        from kicad_mcp_server.tools import test_generation
        print("OK All modules imported successfully")
        return True
    except ImportError as e:
        print(f"X Module import failed: {e}")
        return False

if __name__ == "__main__":
    test_module_imports()
```

Run test:
```bash
python test_imports.py
```

### Test 2: Verify Tool Registration

```python
# test_tools_registration.py
def test_tools_registration():
    """Test that all MCP tools are correctly registered"""
    from kicad_mcp_server.server import mcp

    # Get all registered tools
    tools = list(mcp._tools.values())

    print(f"Total registered tools: {len(tools)}")

    # Check new feature tools
    expected_tools = [
        'run_erc', 'run_drc',  # Validation tools
        'analyze_pin_functions', 'detect_pin_conflicts',  # Pin analysis
        'generate_device_tree',  # Device tree
        'generate_hardware_tests'  # Test generation
    ]

    tool_names = [tool.name for tool in tools]
    missing_tools = []

    for expected in expected_tools:
        if expected in tool_names:
            print(f"OK {expected} registered")
        else:
            print(f"X {expected} not found")
            missing_tools.append(expected)

    if not missing_tools:
        print("OK All expected tools registered!")
        return True
    else:
        print(f"WARN Missing tools: {missing_tools}")
        return False

if __name__ == "__main__":
    test_tools_registration()
```

Run test:
```bash
python test_tools_registration.py
```

## Functional Testing (Requires KiCad Files)

### Test 3: Design Rule Checking (DRC/ERC)

Create test script `test_validation.py`:

```python
import asyncio
from kicad_mcp_server.tools import validation

async def test_erc_functionality():
    """Test ERC functionality"""
    # Replace with your schematic file path
    schematic_path = "path/to/your/schematic.kicad_sch"

    try:
        result = await validation.run_erc(schematic_path)
        print("ERC test results:")
        print(result[:500] + "..." if len(result) > 500 else result)
        return True
    except Exception as e:
        print(f"ERC test failed: {e}")
        return False

async def test_drc_functionality():
    """Test DRC functionality"""
    pcb_path = "path/to/your/pcb.kicad_pcb"

    try:
        result = await validation.run_drc(pcb_path)
        print("DRC test results:")
        print(result[:500] + "..." if len(result) > 500 else result)
        return True
    except Exception as e:
        print(f"DRC test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_erc_functionality())
    asyncio.run(test_drc_functionality())
```

### Test 4: Pin Function Analysis

Create test script `test_pin_analysis.py`:

```python
import asyncio
from kicad_mcp_server.tools import pin_analysis

async def test_pin_analysis():
    """Test pin analysis functionality"""
    schematic_path = "path/to/your/schematic.kicad_sch"

    try:
        # Analyze pin functions
        result = await pin_analysis.analyze_pin_functions(schematic_path)
        print("Pin function analysis:")
        print(result[:500] + "..." if len(result) > 500 else result)

        # Detect pin conflicts
        conflicts = await pin_analysis.detect_pin_conflicts(schematic_path)
        print("\nPin conflict detection:")
        print(conflicts[:500] + "..." if len(conflicts) > 500 else conflicts)

        return True
    except Exception as e:
        print(f"Pin analysis test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_pin_analysis())
```

### Test 5: Device Tree Generation

Create test script `test_device_tree.py`:

```python
import asyncio
from kicad_mcp_server.tools import device_tree

async def test_device_tree_generation():
    """Test device tree generation functionality"""
    schematic_path = "path/to/your/schematic.kicad_sch"

    try:
        # Validate pin configuration
        validation = await device_tree.validate_pin_configuration(schematic_path)
        print("Pin configuration validation:")
        print(validation[:500] + "..." if len(validation) > 500 else validation)

        # Generate device tree
        if "OK" in validation:
            result = await device_tree.generate_device_tree(
                schematic_path=schematic_path,
                target_soc="stm32f4",
                output_path="test_output.dts"
            )
            print("\nDevice tree generation:")
            print(result[:500] + "..." if len(result) > 500 else result)
            return True
        else:
            print("WARN Design validation failed, skipping device tree generation")
            return False

    except Exception as e:
        print(f"Device tree generation test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_device_tree_generation())
```

### Test 6: Test Code Generation

Create test script `test_test_generation.py`:

```python
import asyncio
from kicad_mcp_server.tools import test_generation

async def test_test_generation():
    """Test code generation functionality"""
    schematic_path = "path/to/your/schematic.kicad_sch"

    try:
        # Generate hardware test suite
        result = await test_generation.generate_hardware_tests(
            schematic_path=schematic_path,
            framework="pytest",
            output_dir="test_output/"
        )
        print("Hardware test generation:")
        print(result[:500] + "..." if len(result) > 500 else result)

        # Export test framework
        framework = await test_generation.export_test_framework(
            schematic_path=schematic_path,
            framework="pytest",
            output_dir="test_framework/"
        )
        print("\nTest framework export:")
        print(framework[:500] + "..." if len(framework) > 500 else framework)

        return True
    except Exception as e:
        print(f"Test generation failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_test_generation())
```

## Complete Test Suite

Create comprehensive test script `test_complete_suite.py`:

```python
#!/usr/bin/env python3
"""
KiCad MCP Server Complete Test Suite
Tests all newly implemented features
"""

import asyncio
import sys
from pathlib import Path

# Test configuration
TEST_SCHEMATIC = "path/to/your/schematic.kicad_sch"  # Replace with actual path
TEST_PCB = "path/to/your/pcb.kicad_pcb"            # Replace with actual path

class TestSuite:
    def __init__(self):
        self.results = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "tests": []
        }

    async def test_imports(self):
        """Test 1: Module imports"""
        print("Testing module imports...")
        try:
            from kicad_mcp_server.tools import validation
            from kicad_mcp_server.tools import pin_analysis
            from kicad_mcp_server.tools import device_tree
            from kicad_mcp_server.tools import test_generation
            self._record_result("Module imports", True)
            return True
        except Exception as e:
            self._record_result("Module imports", False, str(e))
            return False

    async def test_validation_tools(self):
        """Test 2: Validation tools"""
        print("\nTesting validation tools...")
        try:
            from kicad_mcp_server.tools import validation

            if not Path(TEST_SCHEMATIC).exists():
                print("WARN Test schematic not found, skipping ERC test")
                self._record_result("ERC tool", None, "Test file does not exist")
                return False

            result = await validation.run_erc(TEST_SCHEMATIC)
            success = "run_erc" in result.lower()
            self._record_result("ERC tool", success)
            return success
        except Exception as e:
            self._record_result("Validation tools", False, str(e))
            return False

    async def test_pin_analysis(self):
        """Test 3: Pin analysis"""
        print("\nTesting pin analysis...")
        try:
            from kicad_mcp_server.tools import pin_analysis

            if not Path(TEST_SCHEMATIC).exists():
                print("WARN Test schematic not found, skipping pin analysis test")
                self._record_result("Pin analysis", None, "Test file does not exist")
                return False

            result = await pin_analysis.analyze_pin_functions(TEST_SCHEMATIC)
            success = "pin" in result.lower()
            self._record_result("Pin function analysis", success)
            return success
        except Exception as e:
            self._record_result("Pin analysis", False, str(e))
            return False

    async def test_device_tree(self):
        """Test 4: Device tree generation"""
        print("\nTesting device tree generation...")
        try:
            from kicad_mcp_server.tools import device_tree

            if not Path(TEST_SCHEMATIC).exists():
                print("WARN Test schematic not found, skipping device tree test")
                self._record_result("Device tree generation", None, "Test file does not exist")
                return False

            result = await device_tree.validate_pin_configuration(TEST_SCHEMATIC)
            success = "validation" in result.lower() or "OK" in result
            self._record_result("Device tree validation", success)
            return success
        except Exception as e:
            self._record_result("Device tree generation", False, str(e))
            return False

    async def test_test_generation(self):
        """Test 5: Test code generation"""
        print("\nTesting test code generation...")
        try:
            from kicad_mcp_server.tools import test_generation

            if not Path(TEST_SCHEMATIC).exists():
                print("WARN Test schematic not found, skipping test generation")
                self._record_result("Test code generation", None, "Test file does not exist")
                return False

            result = await test_generation.generate_gpio_test(TEST_SCHEMATIC)
            success = "gpio" in result.lower() or "test" in result.lower()
            self._record_result("GPIO test generation", success)
            return success
        except Exception as e:
            self._record_result("Test code generation", False, str(e))
            return False

    def _record_result(self, test_name, success, error=None):
        """Record test result"""
        status = "PASS" if success else ("SKIP" if success is None else "FAIL")
        result = {
            "name": test_name,
            "status": status,
            "error": error
        }
        self.results["tests"].append(result)

        if status == "PASS":
            self.results["passed"] += 1
            print(f"OK {test_name}: Passed")
        elif status == "SKIP":
            self.results["skipped"] += 1
            print(f"SKIP {test_name}: Skipped - {error}")
        else:
            self.results["failed"] += 1
            print(f"X {test_name}: Failed - {error}")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*50)
        print("Test Summary")
        print("="*50)
        print(f"Total: {self.results['passed'] + self.results['failed'] + self.results['skipped']} tests")
        print(f"OK Passed: {self.results['passed']}")
        print(f"X Failed: {self.results['failed']}")
        print(f"SKIP Skipped: {self.results['skipped']}")

        if self.results["failed"] == 0:
            print("\nOK All tests passed!")
            return 0
        else:
            print(f"\nWARN {self.results['failed']} test(s) failed")
            return 1

async def run_all_tests():
    """Run all tests"""
    print("Starting KiCad MCP Server Test Suite")
    print("="*50)

    suite = TestSuite()

    # Run all tests
    await suite.test_imports()
    await suite.test_validation_tools()
    await suite.test_pin_analysis()
    await suite.test_device_tree()
    await suite.test_test_generation()

    # Print summary
    return suite.print_summary()

if __name__ == "__main__":
    # Check test file paths
    if not Path(TEST_SCHEMATIC).exists():
        print(f"WARN Test schematic file does not exist: {TEST_SCHEMATIC}")
        print("Please edit the TEST_SCHEMATIC variable in the script to point to a valid KiCad schematic file")
        print("\nContinuing with basic module import tests...\n")

    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
```

Run complete test:
```bash
python test_complete_suite.py
```

## Debugging Tests

If you encounter issues, use the debug script:

```python
# debug_test.py
import sys
import traceback

def debug_import(module_name):
    """Debug module imports"""
    try:
        module = __import__(module_name)
        print(f"OK {module_name} imported successfully")
        return True
    except Exception as e:
        print(f"X {module_name} import failed:")
        print(f"   Error: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Debugging KiCad MCP Server Imports")
    print("="*50)

    modules = [
        "kicad_mcp_server",
        "kicad_mcp_server.tools.validation",
        "kicad_mcp_server.tools.pin_analysis",
        "kicad_mcp_server.tools.device_tree",
        "kicad_mcp_server.tools.test_generation"
    ]

    results = []
    for module in modules:
        results.append(debug_import(module))

    if all(results):
        print("\nOK All modules imported successfully!")
    else:
        print(f"\nWARN {sum(not r for r in results)} module(s) failed to import")
        sys.exit(1)
```

## Quick Verification Checklist

Use this quick checklist to verify all functionality:

```bash
# 1. Verify Python environment
python --version  # Should be >= 3.10

# 2. Verify dependency installation
pip list | grep -E "mcp|kicad|pydantic|jinja2"

# 3. Verify module imports
python -c "from kicad_mcp_server.tools import validation, pin_analysis, device_tree, test_generation; print('OK Import successful')"

# 4. Verify KiCad installation
kicad-cli --version

# 5. Run basic tests
python test_imports.py
python test_tools_registration.py

# 6. If test files exist, run complete test suite
python test_complete_suite.py
```

## Testing Recommendations

### If you have KiCad files:

1. **Start Small**: Test with simple schematics first
2. **Incremental Testing**: Test each functional module incrementally
3. **Verify Output**: Check generated code and reports

### If you don't have KiCad files:

1. **Basic Tests**: Run module import and tool registration tests
2. **Template Tests**: Verify template files exist
3. **Documentation Tests**: Check documentation completeness

### Create Minimal Test Files:

```python
# create_minimal_test.py
import asyncio
from kicad_mcp_server.tools import validation

async def minimal_test():
    """Minimal functionality test"""
    print("Running minimal functionality test...")

    # Test ERC functionality (can test basic logic even if file doesn't exist)
    try:
        result = await validation.run_erc("nonexistent.kicad_sch")
        if "X" in result and "not found" in result.lower():
            print("OK ERC basic functionality normal (correctly handled non-existent file)")
            return True
        else:
            print("WARN ERC response not as expected")
            return False
    except Exception as e:
        print(f"X ERC test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(minimal_test())
    print(f"\n{'OK Success' if success else 'X Failed'}")
```

## Expected Test Results

If successful, you should see:

```
Starting KiCad MCP Server Test Suite
==================================================
Testing module imports...
OK Module imports: Passed

Testing validation tools...
OK ERC tool: Passed

Testing pin analysis...
OK Pin function analysis: Passed

Testing device tree generation...
OK Device tree validation: Passed

Testing test code generation...
OK GPIO test generation: Passed

==================================================
Test Summary
==================================================
Total: 5 tests
OK Passed: 5
X Failed: 0
SKIP Skipped: 0

OK All tests passed!
```

Start testing! If you encounter any issues, let me know the specific error messages.
