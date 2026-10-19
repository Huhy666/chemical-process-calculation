from __future__ import annotations

import pytest

from app.tools import ToolError, get_tool


def run(tool_name: str, args: dict):
    return get_tool(tool_name).run(args)


def test_molar_mass():
    result = run("molar_mass", {"formula": "C6H6"})
    assert result["molar_mass_g_mol"] == pytest.approx(78.114, abs=0.01)


def test_molar_mass_rejects_unknown_element():
    with pytest.raises(ToolError):
        run("molar_mass", {"formula": "Xx2"})


def test_substance_properties_aliases():
    result = run("get_substance_properties", {"name": "水"})
    assert result["key"] == "water"
    assert result["density_kg_m3"] == pytest.approx(997.0)
    result_by_formula = run("get_substance_properties", {"name": "C6H6"})
    assert result_by_formula["key"] == "benzene"


def test_substance_properties_unknown():
    with pytest.raises(ToolError):
        run("get_substance_properties", {"name": "不存在的物质"})


def test_stoichiometry_hydrogenation():
    result = run(
        "stoichiometry_calc",
        {
            "reaction": {"C6H6": -1, "H2": -3, "C6H12": 1},
            "feed_kmol_per_h": {"C6H6": 100, "H2": 350},
            "limiting_reactant": "C6H6",
            "conversion": 0.95,
        },
    )
    assert result["extent_kmol_per_h"] == pytest.approx(95.0)
    assert result["outlet_kmol_per_h"]["C6H12"] == pytest.approx(95.0)
    assert result["outlet_kmol_per_h"]["C6H6"] == pytest.approx(5.0)
    assert result["outlet_kmol_per_h"]["H2"] == pytest.approx(65.0)


def test_stoichiometry_detects_insufficient_reactant():
    with pytest.raises(ToolError):
        run(
            "stoichiometry_calc",
            {
                "reaction": {"C6H6": -1, "H2": -3, "C6H12": 1},
                "feed_kmol_per_h": {"C6H6": 100, "H2": 100},
                "limiting_reactant": "C6H6",
                "conversion": 1.0,
            },
        )


def test_sensible_heat_duty():
    result = run(
        "sensible_heat_duty",
        {
            "volumetric_flow_m3_h": 50,
            "density_kg_m3": 997,
            "cp_kj_kgk": 4.18,
            "t_in_c": 20,
            "t_out_c": 80,
        },
    )
    assert result["mass_flow_kg_h"] == pytest.approx(49850.0)
    assert result["duty_kw"] == pytest.approx(3472.88, abs=0.01)


def test_heat_exchanger_area():
    result = run(
        "heat_exchanger_area",
        {
            "heat_duty_kw": 3472.8833,
            "overall_coeff_w_m2k": 800,
            "hot_in_c": 120,
            "hot_out_c": 120,
            "cold_in_c": 20,
            "cold_out_c": 80,
        },
    )
    assert result["lmtd_k"] == pytest.approx(65.4814, abs=0.001)
    assert result["area_m2"] == pytest.approx(66.288, abs=0.01)


def test_heat_exchanger_rejects_crossing_temperatures():
    with pytest.raises(ToolError):
        run(
            "heat_exchanger_area",
            {
                "heat_duty_kw": 100,
                "overall_coeff_w_m2k": 800,
                "hot_in_c": 60,
                "hot_out_c": 50,
                "cold_in_c": 20,
                "cold_out_c": 80,
            },
        )


def test_pipe_velocity():
    result = run(
        "pipe_velocity", {"volumetric_flow_m3_h": 50, "diameter_mm": 100}
    )
    assert result["velocity_m_s"] == pytest.approx(1.7684, abs=0.001)


def test_pipe_diameter_selects_standard_dn():
    result = run(
        "pipe_diameter", {"volumetric_flow_m3_h": 50, "target_velocity_m_s": 1.5}
    )
    assert result["recommended_dn_mm"] >= result["calculated_diameter_mm"]
    assert result["recommended_dn_mm"] in {100, 125}


def test_pump_power():
    result = run(
        "pump_power",
        {
            "volumetric_flow_m3_h": 30,
            "head_m": 20,
            "density_kg_m3": 997,
            "efficiency": 0.7,
        },
    )
    assert result["hydraulic_power_kw"] == pytest.approx(1.6295, abs=0.001)
    assert result["shaft_power_kw"] == pytest.approx(2.3279, abs=0.001)


def test_ideal_gas_volume():
    result = run(
        "ideal_gas",
        {
            "pressure_kpa": 1200,
            "temperature_k": 523.15,
            "moles_kmol": 10,
            "volume_m3": None,
        },
    )
    assert result["solved_for"] == "volume_m3"
    assert result["volume_m3"] == pytest.approx(36.2476, abs=0.001)


def test_ideal_gas_requires_exactly_one_missing():
    with pytest.raises(ToolError):
        run("ideal_gas", {"pressure_kpa": 100, "temperature_k": 300})


def test_unit_conversion_pressure():
    result = run(
        "unit_convert", {"value": 1.2, "from_unit": "MPa", "to_unit": "bar"}
    )
    assert result["result"] == pytest.approx(12.0)


def test_unit_conversion_temperature():
    result = run(
        "unit_convert", {"value": 0, "from_unit": "°C", "to_unit": "K"}
    )
    assert result["result"] == pytest.approx(273.15)


def test_unit_conversion_rejects_mixed_categories():
    with pytest.raises(ToolError):
        run("unit_convert", {"value": 1, "from_unit": "kg", "to_unit": "kW"})
