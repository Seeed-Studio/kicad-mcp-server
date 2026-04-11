"""Round-trip validation tests for KiCad MCP Server.

These tests verify that components can be added to a schematic
and then successfully parsed back, ensuring the create → parse → verify loop works.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, 'src')


async def test_component_round_trip_simple():
    """Test that a single component can be added and parsed."""

    from kicad_mcp_server.tools.core import create_kicad_project_impl

    from kicad_mcp_server.parsers.schematic_parser import SchematicParser
    from kicad_mcp_server.tools import schematic_editor as se

    print("=" * 70)
    print("🔄 Round-Trip Test: Single Component")
    print("=" * 70)

    # Step 1: Create project
    test_path = "/tmp/round_trip_test_single"
    project_name = "test_single_component"

    create_result = create_kicad_project_impl(
        project_path=test_path,
        project_name=project_name,
        title="Round-Trip Test - Single Component"
    )

    assert "Project created" in create_result or "✅" in create_result
    print("\n✅ Step 1: Project created")

    # Step 2: Add a resistor
    schematic_path = Path(test_path) / f"{project_name}.kicad_sch"
    add_comp_fn = se.add_component_from_library.fn

    result = await add_comp_fn(
        file_path=str(schematic_path),
        library_name="Device",
        symbol_name="R",
        reference="R1",
        value="1k",
        footprint="Resistor_SMD:R_0805_2012Metric",
        x=100,
        y=100
    )

    assert "added successfully" in result.lower() or "✅" in result
    print(f"✅ Step 2: Component added\n{result}")

    # Step 3: Parse and verify
    parser = SchematicParser(str(schematic_path))
    components = parser.get_components()

    print("\n✅ Step 3: Parsing schematic")
    print(f"Components found: {len(components)}")

    # Verify component is found
    assert len(components) > 0, f"Expected at least 1 component, got {len(components)}"

    # Find our R1
    r1 = None
    for comp in components:
        if comp.reference == "R1":
            r1 = comp
            break

    assert r1 is not None, "R1 not found in parsed components"
    assert r1.value == "1k", f"Expected value '1k', got '{r1.value}'"

    print("\n✅ Verification Results:")
    print(f"  - Reference: {r1.reference}")
    print(f"  - Value: {r1.value}")
    print(f"  - Library: {r1.library_id}")

    print("\n" + "=" * 70)
    print("✅ ROUND-TRIP TEST PASSED!")
    print("=" * 70)

    return True


async def test_component_round_trip_multiple():
    """Test that multiple components can be added and parsed."""

    from kicad_mcp_server.tools.core import create_kicad_project_impl

    from kicad_mcp_server.parsers.schematic_parser import SchematicParser
    from kicad_mcp_server.tools import schematic_editor as se

    print("\n" + "=" * 70)
    print("🔄 Round-Trip Test: Multiple Components")
    print("=" * 70)

    # Step 1: Create project
    test_path = "/tmp/round_trip_test_multiple"
    project_name = "test_multiple_components"

    create_result = create_kicad_project_impl(
        project_path=test_path,
        project_name=project_name,
        title="Round-Trip Test - Multiple Components"
    )

    assert "Project created" in create_result or "✅" in create_result
    print("\n✅ Step 1: Project created")

    # Step 2: Add multiple components
    schematic_path = Path(test_path) / f"{project_name}.kicad_sch"
    add_comp_fn = se.add_component_from_library.fn

    components_to_add = [
        {
            "library_name": "Device",
            "symbol_name": "R",
            "reference": "R1",
            "value": "220",
            "footprint": "Resistor_SMD:R_0805_2012Metric",
            "x": 100,
            "y": 100
        },
        {
            "library_name": "Device",
            "symbol_name": "LED",
            "reference": "D1",
            "value": "LED",
            "footprint": "LED_SMD:LED_0805_2012Metric",
            "x": 150,
            "y": 100
        },
        {
            "library_name": "Device",
            "symbol_name": "C",
            "reference": "C1",
            "value": "100nF",
            "footprint": "Capacitor_SMD:C_0805_2012Metric",
            "x": 200,
            "y": 100
        },
    ]

    added_count = 0
    for comp in components_to_add:
        result = await add_comp_fn(file_path=str(schematic_path), **comp)
        if "added successfully" in result.lower() or "✅" in result:
            added_count += 1
            print(f"  ✅ Added {comp['reference']}: {comp['value']}")

    assert added_count == len(components_to_add), f"Only added {added_count}/{len(components_to_add)} components"
    print(f"\n✅ Step 2: Added {added_count} components")

    # Step 3: Parse and verify
    parser = SchematicParser(str(schematic_path))
    components = parser.get_components()

    print("\n✅ Step 3: Parsing schematic")
    print(f"Components found: {len(components)}")

    assert len(components) >= len(components_to_add), \
        f"Expected at least {len(components_to_add)} components, got {len(components)}"

    print("\n✅ Verification Results:")
    for comp in components:
        print(f"  - {comp.reference}: {comp.value} ({comp.library_id})")

    print("\n" + "=" * 70)
    print("✅ ROUND-TRIP TEST PASSED!")
    print("=" * 70)

    return True


async def test_esp32s3_real_round_trip():
    """Test the actual ESP32S3 + OLED + LED + Button design."""

    from kicad_mcp_server.tools.core import create_kicad_project_impl

    from kicad_mcp_server.parsers.schematic_parser import SchematicParser
    from kicad_mcp_server.tools import schematic_editor as se

    print("\n" + "=" * 70)
    print("🔄 Round-Trip Test: ESP32S3 + OLED + LED + Button")
    print("=" * 70)

    # Step 1: Create project
    test_path = "/tmp/round_trip_esp32s3_real"
    project_name = "esp32s3_real_test"

    create_result = create_kicad_project_impl(
        project_path=test_path,
        project_name=project_name,
        title="ESP32S3 Real Round-Trip Test",
        company="MCP Server Test"
    )

    assert "Project created" in create_result or "✅" in create_result
    print("\n✅ Step 1: Project created")

    # Step 2: Add all components
    schematic_path = Path(test_path) / f"{project_name}.kicad_sch"
    add_comp_fn = se.add_component_from_library.fn

    components_to_add = [
        {
            "library_name": "MCU_ESP32_S3",
            "symbol_name": "ESP32-S3-WROOM-1",
            "reference": "U1",
            "value": "ESP32-S3-WROOM-1",
            "footprint": "Module:ESP32-S3-WROOM-1",
            "x": 100,
            "y": 100
        },
        {
            "library_name": "Display",
            "symbol_name": "SSD1306",
            "reference": "U2",
            "value": "SSD1306",
            "footprint": "Display:OLED-0.96-128x64",
            "x": 200,
            "y": 100
        },
        {
            "library_name": "Device",
            "symbol_name": "LED",
            "reference": "D1",
            "value": "LED",
            "footprint": "LED_SMD:LED_0805_2012Metric",
            "x": 100,
            "y": 200
        },
        {
            "library_name": "Device",
            "symbol_name": "R",
            "reference": "R1",
            "value": "220",
            "footprint": "Resistor_SMD:R_0805_2012Metric",
            "x": 150,
            "y": 200
        },
        {
            "library_name": "Device",
            "symbol_name": "R",
            "reference": "R2",
            "value": "10k",
            "footprint": "Resistor_SMD:R_0805_2012Metric",
            "x": 200,
            "y": 200
        },
        {
            "library_name": "Switch",
            "symbol_name": "SW_Push",
            "reference": "SW1",
            "value": "Button",
            "footprint": "Button_SMD:Button_Polygon_4.5x4.5mm",
            "x": 250,
            "y": 200
        },
    ]

    added_count = 0
    for comp in components_to_add:
        result = await add_comp_fn(file_path=str(schematic_path), **comp)
        if "added successfully" in result.lower() or "✅" in result:
            added_count += 1
            print(f"  ✅ Added {comp['reference']}: {comp['value']}")

    assert added_count == len(components_to_add), f"Only added {added_count}/{len(components_to_add)} components"
    print(f"\n✅ Step 2: Added {added_count} components")

    # Step 3: Parse and verify
    parser = SchematicParser(str(schematic_path))
    components = parser.get_components()

    print("\n✅ Step 3: Parsing schematic")
    print(f"Components found: {len(components)}")

    assert len(components) >= len(components_to_add), \
        f"Expected at least {len(components_to_add)} components, got {len(components)}"

    # Verify specific components
    component_refs = {c.reference: c for c in components}

    # Check for each expected component
    expected = {
        "U1": "ESP32",
        "U2": "SSD1306",
        "D1": "LED",
        "R1": "220",
        "R2": "10k",
        "SW1": "Button"
    }

    print("\n✅ Verification Results:")
    all_found = True
    for ref, expected_substring in expected.items():
        if ref in component_refs:
            actual_value = component_refs[ref].value
            if expected_substring in actual_value:
                print(f"  ✅ {ref}: {actual_value}")
            else:
                print(f"  ⚠️  {ref}: {actual_value} (expected {expected_substring})")
                all_found = False
        else:
            print(f"  ❌ {ref}: NOT FOUND")
            all_found = False

    print("\n" + "=" * 70)
    if all_found and len(components) >= len(components_to_add):
        print("✅ ROUND-TRIP TEST PASSED!")
        print("=" * 70)
        print("\n🎉 This proves:")
        print("  ✅ Components can be added")
        print("  ✅ Parser can find the components")
        print("  ✅ Round-trip validation works!")
        print("\n📊 Real Analysis:")
        print(f"  - Main MCU: {component_refs.get('U1', {}).value if 'U1' in component_refs else 'Not found'}")
        print(f"  - Display: {component_refs.get('U2', {}).value if 'U2' in component_refs else 'Not found'}")
        print(f"  - Total: {len(components)} components")
    else:
        print("⚠️  ROUND-TRIP TEST PARTIAL")
        print("=" * 70)
        print(f"Components found: {len(components)}")
        print(f"Expected: {len(components_to_add)}")
        print(f"All found: {all_found}")

    return len(components) >= len(components_to_add) and all_found


if __name__ == "__main__":
    # Run all tests
    async def run_all_tests():
        tests = [
            ("Single Component", test_component_round_trip_simple),
            ("Multiple Components", test_component_round_trip_multiple),
            ("ESP32S3 Real", test_esp32s3_real_round_trip),
        ]

        results = {}

        for test_name, test_func in tests:
            print(f"\n{'='*70}")
            print(f"Running: {test_name}")
            print(f"{'='*70}\n")

            try:
                result = await test_func()
                results[test_name] = result
                print(f"\n✅ {test_name}: PASSED")
            except Exception:
                results[test_name] = False
                print(f"\n❌ {test_name}: FAILED")
                import traceback
                traceback.print_exc()

        # Summary
        print(f"\n\n{'='*70}")
        print("📊 FINAL RESULTS")
        print(f"{'='*70}\n")

        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status}: {test_name}")

        all_passed = all(results.values())
        print(f"\n{'='*70}")
        if all_passed:
            print("✅ ALL TESTS PASSED!")
        else:
            print("⚠️  SOME TESTS FAILED")
        print(f"{'='*70}\n")

        return all_passed

    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
