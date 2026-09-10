"""Exercise the exact native selector, without launching a CFD binary."""
from pathlib import Path
import re
import subprocess

import pytest


@pytest.fixture(scope="module")
def selector(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    text = (root / "cases/basilisk/rectangular_internal_nozzle_convergence_visual.c").read_text()
    boolean = re.search(r"static int parse_bool_arg .*?\n}", text, re.S).group()
    assignment = re.search(r'enable_forensic_probes = !strcmp\(mode, "2"\).*?;', text).group()
    d = tmp_path_factory.mktemp("forensic-selector")
    source = d / "selector.c"
    source.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n' + boolean +
                      '\nint main(int argc,char **argv){const char *mode=argv[1];int enable_forensic_probes;'
                      + assignment + 'printf("%d\\n",enable_forensic_probes);return 0;}\n')
    subprocess.run(["cc", "-Wall", str(source), "-o", str(d / "selector")], check=True, capture_output=True)
    return d / "selector"


@pytest.mark.parametrize("arg,expected", [("0", 0), ("1", 1), ("2", 2), ("true", 1), ("false", 0)])
def test_supported_modes(selector, arg, expected):
    p = subprocess.run([str(selector), arg], capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout == f"{expected}\n"


@pytest.mark.parametrize("arg", ["3", "-1", "2bad", "", "unknown"])
def test_unsupported_modes(selector, arg):
    p = subprocess.run([str(selector), arg], capture_output=True, text=True)
    assert p.returncode == 2 and "ERROR expected boolean" in p.stderr
