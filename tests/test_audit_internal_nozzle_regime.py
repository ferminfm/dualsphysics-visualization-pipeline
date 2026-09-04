import csv
import importlib.util
import math
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_internal_nozzle_regime.py"
SPEC = importlib.util.spec_from_file_location("audit_internal_nozzle_regime", SCRIPT)
REGIME = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REGIME)


def write_fixture(path: Path) -> None:
    names = [
        "t", "plane_label", "liquid_area", "Q_l", "J_k_liquid",
        "forcing_to_plane_pressure_drop",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerow({
            "t": "2", "plane_label": "geometric_nozzle_exit",
            "liquid_area": "2", "Q_l": "6", "J_k_liquid": "20",
            "forcing_to_plane_pressure_drop": "8",
        })
        writer.writerow({
            "t": "1", "plane_label": "other", "liquid_area": "1",
            "Q_l": "1", "J_k_liquid": "1", "forcing_to_plane_pressure_drop": "1",
        })


def test_dimensionless_formulae():
    values = REGIME.dimensionless(
        velocity=3.0, rho=2.0, mu=0.5, sigma=4.0, dh=5.0, pressure_drop=18.0
    )
    assert values == {
        "Re_h": 60.0,
        "We_h": 22.5,
        "Ca": 0.375,
        "Oh_h": 0.5 / math.sqrt(40.0),
        "Eu": 1.0,
    }


def test_audit_derives_three_velocity_conventions(tmp_path: Path):
    source = tmp_path / "hydraulic.csv"
    write_fixture(source)
    result = REGIME.audit(
        source,
        plane_label="geometric_nozzle_exit",
        rho=2.0,
        mu=0.5,
        sigma=4.0,
        dh=5.0,
        reference_velocity=10.0,
    )
    assert result["sample_count"] == 1
    row = result["last"]
    assert row["t_star"] == 4.0
    assert row["velocities"] == {
        "area_weighted": 3.0,
        "flux_weighted": 20.0 / 12.0,
        "momentum_equivalent": math.sqrt(5.0),
    }
    assert math.isclose(row["beta"], 20.0 * 2.0 / (2.0 * 36.0))
    assert math.isclose(row["flow_through_t_star"]["area_weighted"]["internal_15Dh"], 50.0)
    assert result["physical_mapping_status"] == "unresolved"


def test_rejects_nonpositive_physical_values():
    try:
        REGIME.dimensionless(
            velocity=0.0, rho=1.0, mu=1.0, sigma=1.0, dh=1.0, pressure_drop=1.0
        )
    except ValueError as error:
        assert "velocity" in str(error)
    else:
        raise AssertionError("zero velocity was accepted")
