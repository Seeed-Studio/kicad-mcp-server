"""Self-validation tests for KiCad MCP Server.

These tests verify that the tools work correctly by:
1. Creating a KiCad project
2. Analyzing what was created
3. Validating correctness
4. Comparing results
"""

import asyncio


async def test_self_validate_simple_project():
    """Test basic self-validation with a simple project."""
    from kicad_mcp_server.tools.e2e_test import _self_validate_design_creation_impl

    result = await _self_validate_design_creation_impl(
        design_spec="Simple test project",
        test_path="/tmp/kicad_self_test_simple",
        project_name="test_simple",
    )

    print(result)
    assert "PASS" in result or "✅" in result
    assert "Project created" in result


async def test_self_validate_esp32_design():
    """Test self-validation with ESP32 design spec."""
    from kicad_mcp_server.tools.e2e_test import _self_validate_design_creation_impl

    result = await _self_validate_design_creation_impl(
        design_spec="ESP32S3 main controller with OLED display",
        test_path="/tmp/kicad_self_test_esp32",
        project_name="test_esp32",
    )

    print(result)
    assert "Project created" in result
    assert "Analysis" in result or "analyze" in result.lower()


if __name__ == "__main__":
    # Run tests manually
    print("Running self-validation test...\n")

    async def run_test():
        from kicad_mcp_server.tools.core import create_kicad_project_impl

        # Test project creation directly
        result = create_kicad_project_impl(
            project_path="/tmp/kicad_self_test_manual",
            project_name="manual_test",
            title="Manual Test Project",
        )

        return result

    result = asyncio.run(run_test())
    print(result)

    # Check result
    if "✅" in result or "successfully" in result.lower():
        print("\n✅ Self-validation test PASSED")
    else:
        print("\n❌ Self-validation test FAILED")
