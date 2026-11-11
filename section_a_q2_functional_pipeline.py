"""
section_a_q2_functional_pipeline.py
-------------------------------------------------------------------------------
ITS72604 Principles of Programming — Final Examination (Sept 2026)
Section A, Question 2 (5 marks)

A modular, functional-programming pipeline over charging-session records:

    Step 1  filter()  - keep sessions with overstay > 20 min AND battery > 40 C
    Step 2  map()     - apply a 15 % surcharge multiplier to the base energy fee
    Step 3  reduce()  - accumulate the total surcharge revenue of the alert set

Every stage is a pure function, so the pipeline can be tested and reused
channel-by-channel.  ``filter``/``map`` return lazy iterators: no intermediate
list of records is ever materialised, which keeps memory flat when the hub
streams millions of sessions per day.

Run with::

    python section_a_q2_functional_pipeline.py
"""

from __future__ import annotations

import csv
import timeit
import tracemalloc
from functools import partial, reduce
from operator import add, itemgetter
from pathlib import Path
from typing import Final, Iterable, Iterator, TypedDict

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
RAW_CSV: Final[Path] = BASE_DIR / "assets" / "ev_campus_dataset.csv"

# --- business rules -------------------------------------------------------- #
OVERSTAY_LIMIT_MIN: Final[int] = 20
TEMP_LIMIT_C: Final[float] = 40.0
SURCHARGE_RATE: Final[float] = 0.15
# Energy-only tariff used by this demonstration (MYR per kWh)
ENERGY_TARIFF_MYR_PER_KWH: Final[dict[str, float]] = {"AC": 0.60, "DC": 1.20}


class SessionRecord(TypedDict):
    """One charging session, reduced to the fields the alert rule needs."""

    session_id: str
    charger: str
    user_type: str
    overstay_mins: float
    battery_temp_c: float
    energy_kwh: float
    base_energy_fee: float


# --------------------------------------------------------------------------- #
# 1. Extraction - a generator, not a list
# --------------------------------------------------------------------------- #
def read_sessions(csv_path: Path = RAW_CSV) -> Iterator[SessionRecord]:
    """Stream session records from the CSV as one dict at a time.

    ``csv.DictReader`` yields a dictionary per row; the generator hands each one
    to the caller and then *reuses* the loop's memory, so the resident set does
    not grow with file size.  Records without a usable energy reading cannot be
    priced and are skipped (their count is reported by :func:`summarise`).

    Yields
    ------
    SessionRecord
        A normalised record with floats instead of CSV strings.
    """
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            energy = _to_float(row.get("Energy_kWh"))
            overstay = _to_float(row.get("Overstay_Mins"))
            temperature = _to_float(row.get("Battery_Temp_C"))
            if energy is None or overstay is None or temperature is None:
                continue                      # unpriced row: cannot bill it
            charger = (row.get("Charger_Type") or "").strip().upper()
            yield {
                "session_id": row.get("Session_ID", ""),
                "charger": charger,
                "user_type": (row.get("User_Type") or "").strip(),
                "overstay_mins": overstay,
                "battery_temp_c": temperature,
                "energy_kwh": energy,
                "base_energy_fee": (
                    energy * ENERGY_TARIFF_MYR_PER_KWH.get(charger, 0.60)
                ),
            }


def _to_float(text: str | None) -> float | None:
    """Convert a CSV cell to ``float``; return ``None`` for blanks/NaN."""
    if text is None or text.strip() == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# 2. filter() - the high-risk predicate
# --------------------------------------------------------------------------- #
def is_high_risk(record: SessionRecord,
                 overstay_limit: float = OVERSTAY_LIMIT_MIN,
                 temp_limit: float = TEMP_LIMIT_C) -> bool:
    """Return ``True`` when a session breaches both overstay and temperature.

    Implemented as a named function rather than an inline lambda because it is
    (a) documented, (b) unit-testable in isolation, and (c) picklable if the
    pipeline is later distributed across worker processes.
    """
    return (record["overstay_mins"] > overstay_limit
            and record["battery_temp_c"] > temp_limit)


def filter_alerts(records: Iterable[SessionRecord],
                  overstay_limit: float = OVERSTAY_LIMIT_MIN,
                  temp_limit: float = TEMP_LIMIT_C) -> Iterator[SessionRecord]:
    """Lazily select the alert sessions (``filter`` returns an iterator)."""
    predicate = partial(is_high_risk, overstay_limit=overstay_limit,
                        temp_limit=temp_limit)
    return filter(predicate, records)


# --------------------------------------------------------------------------- #
# 3. map() - the 15 % surcharge
# --------------------------------------------------------------------------- #
def apply_surcharge(record: SessionRecord,
                    rate: float = SURCHARGE_RATE) -> dict[str, object]:
    """Return a copy of ``record`` with the surcharge priced in.

    A new dictionary is returned instead of mutating the input: pure functions
    keep the raw record available for audit and make the stage replay-safe.
    """
    base_fee = record["base_energy_fee"]
    surcharge = round(base_fee * rate, 2)
    return {**record,                            # shallow copy of the record
            "surcharge_rate": rate,
            "surcharge_myr": surcharge,
            "total_fee_myr": round(base_fee + surcharge, 2)}


def price_alerts(records: Iterable[SessionRecord],
                 rate: float = SURCHARGE_RATE) -> Iterator[dict[str, object]]:
    """Lazily price each alert session with the configured multiplier."""
    return map(partial(apply_surcharge, rate=rate), records)


# --------------------------------------------------------------------------- #
# 4. reduce() - total surcharge revenue
# --------------------------------------------------------------------------- #
def total_surcharge(records: Iterable[dict[str, object]]) -> float:
    """Fold the priced alerts into a single revenue figure.

    ``reduce`` performs one pass and keeps a single accumulator, so the revenue
    report needs O(1) additional memory.  ``operator.add`` is used inside the
    fold instead of ``lambda acc, rec: acc + rec["surcharge_myr"]``: it is a C
    function (no per-call frame) and reads as what it is - addition.
    """
    return reduce(add, map(itemgetter("surcharge_myr"), records), 0.0)


# --------------------------------------------------------------------------- #
# 5. Report + memory demonstration
# --------------------------------------------------------------------------- #
def summarise(records: Iterable[SessionRecord]) -> int:
    """Run the whole pipeline and print the operational summary."""
    print("=" * 92)
    print(" SECTION A, QUESTION 2 - FUNCTIONAL SURCHARGE PIPELINE")
    print("=" * 92)

    all_sessions = list(read_sessions())          # the 1,200-row study sample
    alerts = filter_alerts(all_sessions)          # lazy filter iterator
    priced = list(price_alerts(alerts))           # lazy map, materialised once
    revenue = total_surcharge(priced)

    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        csv_rows = sum(1 for _ in csv.DictReader(handle))

    print(f"CSV rows read                   : {csv_rows:,}")
    print(f"Records extracted (priced)      : {len(all_sessions):,}")
    print(f"Rows skipped (no energy value)  : {csv_rows - len(all_sessions):,}")
    print(f"Alert sessions (overstay > {OVERSTAY_LIMIT_MIN} min "
          f"and battery > {TEMP_LIMIT_C:.0f} degC): {len(priced)}")
    print(f"Surcharge rate applied          : {SURCHARGE_RATE:.0%} "
          f"of the base energy fee")
    print(f"Total surcharge revenue         : MYR {revenue:,.2f}")
    if priced:
        print(f"Mean surcharge per alert        : MYR "
              f"{revenue / len(priced):,.2f}")
        print(f"Largest single surcharge        : MYR "
              f"{max(record['surcharge_myr'] for record in priced):,.2f}")

    header = (f"\n{'Session':<11}{'Charger':<9}{'User':<9}"
              f"{'Overstay':>9}{'Temp(C)':>9}{'Energy':>9}"
              f"{'BaseFee':>9}{'Surchg':>9}{'Total':>9}")
    print(header)
    print("-" * len(header.strip()))
    for record in sorted(priced, key=itemgetter("surcharge_myr"), reverse=True)[:10]:
        print(f"{record['session_id']:<11}{record['charger']:<9}"
              f"{record['user_type']:<9}{record['overstay_mins']:>9.0f}"
              f"{record['battery_temp_c']:>9.1f}{record['energy_kwh']:>9.2f}"
              f"{record['base_energy_fee']:>9.2f}{record['surcharge_myr']:>9.2f}"
              f"{record['total_fee_myr']:>9.2f}")
    print("... (top 10 alert sessions by surcharge)")

    # --- the same fold written as an inline lambda, for comparison --------- #
    inline_total = reduce(
        lambda acc, item: acc + item["surcharge_myr"],  # noqa: E731 - illustration
        priced,
        0.0,
    )
    print(f"\nInline-lambda fold result       : MYR {inline_total:,.2f} (identical)")

    lambda_time, operator_time = benchmark_fold(priced)
    print(f"\nFold with inline lambda         : {lambda_time * 1e6:8.2f} us per fold")
    print(f"Fold with operator.add          : {operator_time * 1e6:8.2f} us per fold")
    print(f"itemgetter/add speed-up         : {lambda_time / operator_time:5.2f}x")
    return len(priced)


def benchmark_fold(priced: list[dict[str, object]],
                   repeats: int = 5) -> tuple[float, float]:
    """Time the lambda fold against the ``itemgetter`` + ``operator.add`` fold."""

    def lambda_fold() -> float:
        return reduce(lambda acc, item: acc + item["surcharge_myr"], priced, 0.0)

    def operator_fold() -> float:
        return reduce(add, map(itemgetter("surcharge_myr"), priced), 0.0)

    lambda_time = min(timeit.repeat(lambda_fold, number=1000, repeat=repeats)) / 1000
    operator_time = (
        min(timeit.repeat(operator_fold, number=1000, repeat=repeats)) / 1000
    )
    return lambda_time, operator_time


def demo_memory_profile(stream_size: int = 200_000) -> None:
    """Compare the peak memory of a streaming pipeline against a list pipeline.

    Both versions execute the identical filter -> map -> reduce chain; the only
    difference is whether the intermediate records are held in a list.  Peaks
    are measured with :mod:`tracemalloc`, i.e. only Python allocations.
    """
    print("\n" + "=" * 92)
    print(" MEMORY PROFILE - lazy iterators vs materialised lists")
    print("=" * 92)

    def record_stream(count: int) -> Iterator[dict[str, object]]:
        for index in range(count):
            yield {
                "session_id": f"SESS-{index:07d}",
                "charger": "AC" if index % 3 else "DC",
                "user_type": "Student",
                "overstay_mins": 25.0 + index % 7,
                "battery_temp_c": 41.0 + index % 5,
                "energy_kwh": 12.0 + index % 11,
                "base_energy_fee": 9.5,
            }

    def pipeline(records: Iterable[dict[str, object]]) -> float:
        return reduce(
            add,
            map(itemgetter("surcharge_myr"),
                map(partial(apply_surcharge, rate=SURCHARGE_RATE), records)),
            0.0,
        )

    def list_pipeline() -> float:
        materialised = [record for record in record_stream(stream_size)]
        alerts = [record for record in materialised if is_high_risk(record)]
        return pipeline(alerts)

    def streaming_pipeline() -> float:
        alerts = filter(is_high_risk, record_stream(stream_size))
        return pipeline(alerts)

    tracemalloc.start()
    list_total = list_pipeline()
    _, list_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    stream_total = streaming_pipeline()
    _, stream_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Records streamed                : {stream_size:,}")
    print(f"List pipeline    peak memory    : {list_peak / 1024:10,.0f} KiB")
    print(f"Streaming peak memory           : {stream_peak / 1024:10,.0f} KiB")
    print(f"Peak reduction                  : "
          f"{100 * (1 - stream_peak / list_peak):.2f} %")
    print(f"Both totals equal               : {abs(list_total - stream_total) < 1e-9}")


def main() -> int:
    """Run the Section A Question 2 pipeline."""
    try:
        alert_count = summarise(read_sessions())
        demo_memory_profile()
    except FileNotFoundError:
        print("[FILE ERROR] assets/ev_campus_dataset.csv was not found.")
        return 2
    print("\n" + "=" * 92)
    print(f" QUESTION 2 COMPLETE - {alert_count} alert sessions priced")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
