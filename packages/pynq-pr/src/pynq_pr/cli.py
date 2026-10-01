import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="pynq-pr",
        description="PYNQ Partial Reconfiguration build tool",
    )
    sub = parser.add_subparsers(dest="command")

    build_p = sub.add_parser("build", help="Run full PR build flow")
    build_p.add_argument("-c", "--config", required=True, help="Path to pr yaml config file")
    build_p.add_argument("-f", "--force", action="store_true", help="Remove existing output directory before building")

    val_p = sub.add_parser("validate", help="Check config and source files")
    val_p.add_argument("-c", "--config", required=True, help="Path to pr yaml config file")

    sim_p = sub.add_parser("sim", help="Generate sim config and run cocotbpynq simulation")
    sim_p.add_argument("-c", "--config", required=True, help="Path to pr yaml config file")
    sim_p.add_argument("-t", "--test", required=True, help="Python test module name or path to a .py file")
    sim_p.add_argument("-f", "--force", action="store_true", help="Remove existing sim directory before generating")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "build":
        from .builder import build
        build(args.config, force=args.force)
    elif args.command == "validate":
        from .builder import validate_config
        validate_config(args.config)
    elif args.command == "sim":
        try:
            import cocotbpynq  # noqa: F401  (checked before anything is generated)
        except ImportError:
            sys.exit("pynq-pr sim needs the simulation extra: pip install 'pynq-pr[sim]'")
        from .sim import generate_sim_config
        from .run import run_simulation
        sim_config = generate_sim_config(args.config, force=args.force)
        sys.exit(run_simulation(str(sim_config), args.test))
