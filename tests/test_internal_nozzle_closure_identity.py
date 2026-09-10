import importlib.util
from pathlib import Path
import pytest

P = Path(__file__).resolve().parents[1] / "scripts/compare_internal_nozzle_closure_identity.py"
S = importlib.util.spec_from_file_location("closure_identity", P)
M = importlib.util.module_from_spec(S); S.loader.exec_module(M)


def data(t=1.0, payload=None):
    if payload is None: payload = bytes(136)
    values = [b"internal_nozzle_prediction_closure_v4", 4, 3, 0x01020304, 8, 80, 56,
              1, 1, 136, 0, 0, 0, 0, t, .01, .01, .01, 0., 0., 0., 1., 1, 8,
              b"a"*64, b"synthetic", b"b"*64]
    return M.HEADER.pack(*values) + payload


def test_same_payload_different_clock(tmp_path):
    l=tmp_path/"left"; r=tmp_path/"right"; l.write_bytes(data()); r.write_bytes(data(1.0000000000000002))
    report=M.compare(l,r)
    assert report["payload_byte_identical"] and set(report["header_differences"]) == {"t"}


def test_changed_payload_not_hidden_by_equal_header(tmp_path):
    l=tmp_path/"left"; r=tmp_path/"right"; l.write_bytes(data()); r.write_bytes(data(payload=b"x"+bytes(135)))
    report=M.compare(l,r)
    assert not report["payload_byte_identical"] and report["first_differing_byte"] == 576


def test_truncated_and_symlink_fail(tmp_path):
    l=tmp_path/"left"; r=tmp_path/"right"; l.write_bytes(data()); r.write_bytes(data()[:-1])
    with pytest.raises(AssertionError): M.compare(l,r)
    link=tmp_path/"link"; link.symlink_to(l)
    with pytest.raises(AssertionError): M.compare(link,l)
