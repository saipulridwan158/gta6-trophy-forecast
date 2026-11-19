"""gta6-trophy-rarity-forecast-01 entry: delta-growth forecast with a two-term spread.

Reads the case (makefun/gta6-trophies-case/v1), fits the mean climb of every
trophy's logit delta over the case's reads, projects each trophy's own last
logit rate to the target, and writes five quantiles widened by a random-walk
term plus a fit-residual term on the logit scale.

Deterministic: no randomness and no clock reads, so two runs write the same bytes.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module shipped
# beside this file imports after this line puts the directory first.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
# Week-one dispersion of a rate's move, logit units per square-root day. The house
# baseline's 0.5 is the 90-minute figure; a week of a growing player base, and the
# unseen refresh the practice's answer showed, move rates much more, so the band
# doubles it and lets the fit's residual add on top.
SIGMA = 1.0
# The epoch the delta curve is fitted against: hours since this instant.
EPOCH = "2026-11-19T00:00:00Z"


def clamp(x: float) -> float:
    return min(99.99, max(0.01, x))


def logit(pct: float) -> float:
    p = clamp(pct)
    return math.log(p / (100 - p))


def _epoch_hours(y: int, mo: int, d: int, hh: int = 0, mm: int = 0, ss: float = 0) -> float:
    """Hours from EPOCH (2026-11-19T00:00Z) to the stamp."""
    import datetime as dt

    epoch = dt.datetime(2026, 11, 19, tzinfo=dt.timezone.utc)
    t = dt.datetime(y, mo, d, hh, mm, int(ss), tzinfo=dt.timezone.utc) + dt.timedelta(seconds=ss - int(ss))
    return (t - epoch).total_seconds() / 3600.0


def stamp_hours(iso: str) -> float:
    """Hours from EPOCH to an ISO 8601 UTC stamp."""
    txt = iso
    frac = 0.0
    if txt.endswith("Z"):
        txt = txt[:-1]
    if "." in txt:
        txt, frac_txt = txt.split(".", 1)
        frac = float("0." + frac_txt)
    date_part, time_part = txt.split("T")
    y, mo, d = (int(v) for v in date_part.split("-"))
    hh = mm = 0
    ss = 0.0
    if ":" in time_part:
        bits = time_part.split(":")
        hh = int(bits[0])
        mm = int(bits[1]) if len(bits) > 1 else 0
        if len(bits) > 2:
            ss = float(bits[2])
    else:
        hh = int(time_part)
    return _epoch_hours(y, mo, d, hh, mm, ss + frac)


def round4(x: float) -> float | int:
    """x rounded to 4 decimals, half up (JavaScript's Math.round(x*10000)/10000)."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def fit_growth(reads: list) -> tuple[float, float]:
    """Fit the climb rate of the trophy-level median logit delta, and its residual.

    delta_i = median over trophies of (logit(rate_i) - logit(rate_0)) at read i,
    against hours t_i since EPOCH. Least squares through the origin: g = sum(t*d)/sum(t^2).
    Returns (g, rms_residual_per_hour_floor0). With fewer than 3 reads, (0, 0).
    """
    if len(reads) < 3:
        return 0.0, 0.0
    base = reads[0]["rates"]
    base_lg = [logit(r) for r in base if r is not None]
    pts = []
    for h in reads:
        t = stamp_hours(h["at"])
        lg = [logit(r) for r in h["rates"] if r is not None]
        if len(lg) != len(base_lg) or not lg:
            continue
        deltas = sorted(a - b for a, b in zip(lg, base_lg))
        med = deltas[len(deltas) // 2]
        pts.append((t, med))
    if len(pts) < 3:
        return 0.0, 0.0
    den = sum(t * t for t, _ in pts)
    if den <= 0:
        return 0.0, 0.0
    g = sum(t * dlt for t, dlt in pts) / den
    t_span = pts[-1][0] - pts[0][0]
    if t_span <= 0:
        return max(0.0, g), 0.0
    resid = math.sqrt(sum((dlt - g * t) ** 2 for t, dlt in pts) / len(pts))
    return max(0.0, g), resid / math.sqrt(t_span)


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    if not case["history"]:
        raise ValueError(f"{name} has no history")
    reads = case["history"]
    last = reads[-1]
    g, res_rate = fit_growth(reads)
    # hours from the last read to the target, and the horizon in days
    h_hours = stamp_hours(case["target"]) - stamp_hours(last["at"])
    d_days = case["horizon_minutes"] / 1440.0
    s_rw = SIGMA * math.sqrt(max(d_days, 1e-9))
    s_res = res_rate * math.sqrt(max(h_hours, 0.0))
    spread = max(math.sqrt(s_rw * s_rw + s_res * s_res), 0.05)
    last_rates = last["rates"]
    known = [r for r in last_rates if r is not None]
    fallback = sorted(logit(r) for r in known)[len(known) // 2] if known else logit(1.0)
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        rate = last_rates[i]
        lg = logit(rate) if rate is not None else fallback
        lg_target = lg + g * max(h_hours, 0.0)
        rows.append({"id": trophy["id"], "q": [round4(100 / (1 + math.exp(-(lg_target + z * spread)))) for z in Z]})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
