"""Evitania optimizer CLI — dispatches per --event."""

from __future__ import annotations

import argparse
from pathlib import Path

from optimizers import summer


REPO_ROOT = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Evitania event upgrade optimizer")
    parser.add_argument(
        "--event",
        choices=["summer", "realm"],
        default="summer",
        help="Which event to optimize (default: summer)",
    )
    parser.add_argument("--budget", type=int, default=800, help="Currency available (default: 800)")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Path to the event's data.json (default: docs/<event>-event/data.json)",
    )
    parser.add_argument("--plot", action="store_true", help="Also render a staircase PNG")
    parser.add_argument(
        "--plot-out",
        type=Path,
        default=Path("optimization-curve.png"),
        help="Output PNG path for --plot",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="With --plot, display the chart interactively (blocks until closed)",
    )
    args = parser.parse_args()

    data_path = args.data or REPO_ROOT / "docs" / f"{args.event}-event" / "data.json"

    if args.event == "summer":
        upgrades = summer.load_upgrades(data_path)
        result = summer.optimize(upgrades, args.budget)
        print(summer.render(result, args.budget))
        if args.plot:
            staircase = summer.optimal_ratio_staircase(summer.enumerate_configs(upgrades))
            summer.plot_curve(staircase, result, args.budget, args.plot_out, args.show)
            print(f"\nPlot saved to {args.plot_out}")
    elif args.event == "realm":
        from optimizers import realm
        upgrades = realm.load_upgrades(data_path)
        result = realm.optimize(upgrades, args.budget)
        print(realm.render(result, args.budget))
        if args.plot:
            staircase = realm.optimal_ratio_staircase(upgrades)
            realm.plot_curve(staircase, result, args.budget, args.plot_out, args.show)
            print(f"\nPlot saved to {args.plot_out}")


if __name__ == "__main__":
    main()
