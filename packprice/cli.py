"""
Command line interface, so a price check does not require writing Python.

    pack-price "Fc1ccccn1" --grams 7.6
    pack-price "CC1(C)CCCC(C)(C)N1[O]" --grams 26.8 --purity 99
    pack-price "[Zn]" --grams 16.3 --json

The output is a table ordered the way the library orders it: cheapest way to
end up with enough, with purity bands applied if one is asked for. The last
line reports any source that failed, because a short list and a broken
marketplace look identical otherwise.
"""

import argparse
import json
import sys

from . import __version__, _price, _purity, cache, search


def _fmt_pack(option: dict) -> str:
    amount = option.get("pack_size_amount")
    if amount is None:
        return "?"
    unit = option.get("pack_size_unit") or ""
    return f"{amount:g} {unit}".strip()


def _fmt_age(option: dict) -> str:
    days = cache.age_days(option)
    if days is None:
        return "live"
    if days < 1:
        return "today"
    return f"{int(days)}d ago"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pack-price",
        description="Which pack to buy, and what it costs, across chemical "
        "marketplaces.",
        epilog="Set MOLPORT_API_KEY, CHEMSPACE_API_KEY and MCULE_API_KEY for "
        "the sources you have. Ones without a key are skipped.",
    )
    parser.add_argument("smiles", help="structure to price, as SMILES")
    parser.add_argument(
        "--grams", "-g", type=float,
        help="how much the procedure needs; without it, offers are ranked on "
             "price alone and packs cannot be compared",
    )
    parser.add_argument(
        "--purity", "-p", type=float,
        help="minimum purity the procedure requires, as a percentage",
    )
    parser.add_argument(
        "--sources", "-s",
        help="comma separated subset, e.g. molport,chemspace",
    )
    parser.add_argument("--name", "-n", default="", help="label for the search")
    parser.add_argument("--limit", "-l", type=int, default=10,
                        help="rows to show, default 10")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    parser.add_argument("--no-cache", action="store_true",
                        help="ignore cached answers and ask every source")
    parser.add_argument("--clear-cache", action="store_true",
                        help="delete every cached answer and exit")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    if args.clear_cache:
        print(f"removed {cache.clear()} cached entries")
        return 0

    if args.no_cache:
        cache.MAX_AGE_DAYS = 0

    sources = args.sources.split(",") if args.sources else None
    result = search(
        args.smiles, args.grams, args.name, sources, min_purity=args.purity
    )

    if args.json:
        print(json.dumps(
            {"options": result.options, "errors": result.errors}, indent=2
        ))
        return 0 if result.complete else 1

    if not result.options:
        # An empty list means two very different things, and which one it is
        # decides whether you look elsewhere or try again in an hour.
        if result.complete:
            print("No supplier has this compound.")
        else:
            print("No offers, but not every source answered:")
            for source, why in result.errors.items():
                print(f"  {source}: {why}")
        return 0 if result.complete else 1

    show_purity = args.purity is not None
    header = f"{'SOURCE':10} {'SUPPLIER':26} {'PACK':>10} {'PRICE':>9} {'PURITY':>7}"
    if args.grams:
        header += f" {'TOTAL':>9}"
    header += "  AGE"
    print(header)
    print("-" * len(header))

    for option in result.options[: args.limit]:
        purity = _purity(option)
        purity_text = f"{purity:g}%" if purity is not None else "-"
        if show_purity:
            meets = option.get("meets_purity")
            purity_text += {True: "", False: " !", None: " ?"}[meets]

        row = (
            f"{option['source']:10} {str(option['supplier'])[:26]:26} "
            f"{_fmt_pack(option):>10} {str(option['price'] or '-'):>9} "
            f"{purity_text:>7}"
        )
        if args.grams:
            import math

            price, pack = _price(option), None
            scale = {"g": 1.0, "mg": 0.001, "kg": 1000.0}.get(
                str(option.get("pack_size_unit") or "").lower()
            )
            if scale and option.get("pack_size_amount"):
                pack = option["pack_size_amount"] * scale
            if price is not None and pack:
                packs = max(1, math.ceil(args.grams / pack))
                total = f"${packs * price:g}" + (f" x{packs}" if packs > 1 else "")
            else:
                total = "-"
            row += f" {total:>9}"
        row += f"  {_fmt_age(option)}"
        print(row)

    hidden = len(result.options) - args.limit
    if hidden > 0:
        print(f"\n... {hidden} more, use --limit to see them")

    if show_purity:
        print("\n! below the purity asked for   ? no purity stated")

    if not result.complete:
        print("\nIncomplete — these sources did not answer:")
        for source, why in result.errors.items():
            print(f"  {source}: {why}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
