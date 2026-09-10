#!/usr/bin/env python3
"""Only declared entry point for successor diagnostic and production CFD."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import internal_nozzle_qualification as gate
import launch_internal_nozzle_precursor_case as bound


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-record", type=Path)
    parser.add_argument("--inspect-binding", action="store_true")
    parser.add_argument("bound_argv", nargs=argparse.REMAINDER)
    opts = parser.parse_args(argv)
    rest = opts.bound_argv[1:] if opts.bound_argv[:1] == ["--"] else opts.bound_argv
    args = bound.parse_args(rest)
    contract = bound.build_contract(args)
    if opts.inspect_binding:
        print(json.dumps({"binding": gate.binding(contract), "contract": contract}, sort_keys=True))
        return 0
    gate.require(opts.qualification_record is not None, "missing qualification authority")
    root = Path(contract["batch_identity"]["batch_root"])
    ticket = Path(contract["cwd"]) / ("qualification-ticket." + contract["segment_id"] + ".json")
    with gate.reserve(opts.qualification_record, contract, root / "qualification-start-ledger.json", ticket):
        bound.atomic_json(args.output, contract)
        supervisor_argv = list(contract["supervisor_argv"])
        at = supervisor_argv.index("--")
        supervisor_argv[at:at] = ["--qualification-ticket", str(ticket)]
        completed = subprocess.run(supervisor_argv, cwd=contract["cwd"], check=False)
        bound.reconcile_supervision(contract, completed.returncode)
        return completed.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print("QUALIFICATION_GATE_REJECT: " + str(error), file=sys.stderr)
        raise SystemExit(2)
