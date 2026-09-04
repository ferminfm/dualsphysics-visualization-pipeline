import importlib.util
import json
import math
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rectangular_poiseuille_reference.py"
SPEC = importlib.util.spec_from_file_location("rectangular_poiseuille_reference", SCRIPT)
REF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REF)


def test_two_to_one_reference_constants():
    result = REF.reference_metrics(modes=256, quadrature_order=256)
    assert result["modes"] == 256
    assert result["conductance_modes"] == 1024
    assert math.isclose(result["conductance_factor"], 0.6860450313587123, rel_tol=0, abs_tol=2e-14)
    assert math.isclose(result["bulk_velocity"], 0.05717041927989269, rel_tol=0, abs_tol=2e-11)
    assert math.isclose(result["centerline_to_bulk"], 1.991796344360972, rel_tol=0, abs_tol=3e-9)
    assert math.isclose(result["beta"], 1.3474586595767, rel_tol=0, abs_tol=3e-9)
    assert math.isclose(result["alpha"], 2.0389181724236, rel_tol=0, abs_tol=4e-9)
    assert math.isclose(result["momentum_equivalent_to_bulk"], 1.1608008699069, rel_tol=0, abs_tol=2e-9)
    assert math.isclose(result["darcy_f_re"], 62.1922245864, rel_tol=0, abs_tol=5e-11)
    assert math.isclose(result["fanning_f_re"], 15.5480561466, rel_tol=0, abs_tol=2e-11)
    assert result["relative_flow_quadrature_error"] < 4e-10


def test_conductance_uses_independent_high_mode_series():
    rows = REF.conductance_convergence_study([128, 256, 512, 1024])
    assert [row["modes"] for row in rows] == [128, 256, 512, 1024]
    assert abs(rows[-1]["conductance_factor"] - 0.6860450313587123) < 2e-14
    assert abs(rows[-1]["delta"]) < abs(rows[-2]["delta"])
    # The high-mode conductance check must not increase the velocity tensor.
    metrics = REF.reference_metrics(modes=64, quadrature_order=192)
    assert metrics["modes"] == 64
    assert metrics["conductance_modes"] == 1024


def test_cli_artifact_is_strict_json_without_nonfinite_tokens(
    tmp_path, monkeypatch, capsys,
):
    output = tmp_path / "reference"
    monkeypatch.setattr(
        "sys.argv",
        [
            str(SCRIPT), "--output-dir", str(output), "--modes", "64",
            "--quadrature-order", "64", "--cut-points", "17",
            "--fd-levels", "16,32",
        ],
    )
    assert REF.main() == 0
    text = (output / "reference.json").read_text(encoding="utf-8")

    def reject_nonfinite(value):
        raise ValueError(f"nonfinite JSON token: {value}")

    payload = json.loads(text, parse_constant=reject_nonfinite)
    assert "NaN" not in text and "Infinity" not in text
    assert payload["series_convergence"][0]["delta_beta"] is None
    assert payload["series_convergence"][0]["delta_alpha"] is None
    assert payload["conductance_series_convergence"][0]["delta"] is None
    stdout = capsys.readouterr().out
    assert json.loads(stdout, parse_constant=reject_nonfinite)["schema"] == (
        "rectangular_poiseuille_reference_v1"
    )


def test_symmetry_and_no_slip():
    points = np.linspace(-0.45, 0.45, 17)
    values = REF.velocity(points, 0.21, modes=160)
    assert np.allclose(values, REF.velocity(-points, 0.21, modes=160), rtol=0, atol=3e-14)
    assert np.allclose(values, REF.velocity(points, -0.21, modes=160), rtol=0, atol=3e-14)
    assert np.all(REF.velocity(np.array([-1.0, 1.0]), 0.0, modes=160) == 0.0)
    assert np.all(REF.velocity(0.0, np.array([-0.5, 0.5]), modes=160) == 0.0)


def test_forcing_and_viscosity_scaling():
    base = float(REF.velocity(0.21, 0.13, modes=128))
    scaled = float(
        REF.velocity(
            0.21,
            0.13,
            pressure_gradient=6.0,
            viscosity=3.0,
            modes=128,
        )
    )
    assert math.isclose(scaled, 2.0 * base, rel_tol=0, abs_tol=2e-14)


def test_series_satisfies_poisson_equation_away_from_walls():
    y, z, h = 0.23, -0.11, 2.0e-4
    center = float(REF.velocity(y, z, modes=256))
    dyy = (
        float(REF.velocity(y + h, z, modes=256))
        - 2.0 * center
        + float(REF.velocity(y - h, z, modes=256))
    ) / h**2
    dzz = (
        float(REF.velocity(y, z + h, modes=256))
        - 2.0 * center
        + float(REF.velocity(y, z - h, modes=256))
    ) / h**2
    assert math.isclose(dyy + dzz, -1.0, rel_tol=0, abs_tol=2e-6)


def test_series_convergence_and_independent_poisson():
    low = REF.reference_metrics(modes=64, quadrature_order=192)
    high = REF.reference_metrics(modes=256, quadrature_order=256)
    assert abs(low["beta"] - high["beta"]) < 2e-7
    assert abs(low["alpha"] - high["alpha"]) < 5e-7
    fd128 = REF.finite_difference_metrics(128)
    fd256 = REF.finite_difference_metrics(256)
    fd512 = REF.finite_difference_metrics(512)
    assert abs(fd512["beta"] - high["beta"]) < abs(fd256["beta"] - high["beta"])
    assert abs(fd256["beta"] - high["beta"]) < abs(fd128["beta"] - high["beta"])
    assert abs(fd512["alpha"] - high["alpha"]) < 2e-6


def test_finite_difference_requires_even_simpson_grid():
    with np.testing.assert_raises_regex(ValueError, "must be even"):
        REF.finite_difference_metrics(127)


def test_parallel_plate_limit():
    result = REF.reference_metrics(
        width=80.0,
        height=1.0,
        modes=192,
        quadrature_order=240,
    )
    assert abs(result["beta"] - 6.0 / 5.0) < 0.02
    assert abs(result["alpha"] - 54.0 / 35.0) < 0.04


def test_rotation_invariance_of_integrated_constants():
    normal = REF.reference_metrics(width=2.0, height=1.0, modes=256, quadrature_order=256)
    rotated = REF.reference_metrics(width=1.0, height=2.0, modes=256, quadrature_order=256)
    assert math.isclose(normal["flow_rate"], rotated["flow_rate"], rel_tol=0, abs_tol=3e-10)
    assert math.isclose(normal["beta"], rotated["beta"], rel_tol=0, abs_tol=3e-9)
    assert math.isclose(normal["alpha"], rotated["alpha"], rel_tol=0, abs_tol=5e-9)
