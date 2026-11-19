"""gta6-trophy-rarity-forecast-01: earners-over-players forecast with a calibrated band.

Exophase prints an earn rate as 100 x (players who earned the trophy) / (players it
tracks). Its refresh changes the tracked-player count and re-prints every rate from the
same earners, so a rate is the ratio of two counts that move on different clocks: the
tracked-player count grows with installs, a trophy's earners grow with the players who
reach it. This entry forecasts the two counts separately and divides:

    rate_i(T) = 100 * E_i(T) / N(T) = 100 * s_i(T) * M(T)

with s_i = E_i / sum_j E_j the trophy's share of all earners (the page prints that sum
as trophies_earned) and M = sum_j E_j / N the mean trophies earned per tracked player.

Each factor is a trend against hours since release over the case's distinct reads (a run
of unchanged reads is one observation, dated at its first read): N and M by a power law
whose exponent is clamped, blended with a straight line through the last reads, and each
share by its own log-log slope shrunk towards the pooled slope so one noisy trophy cannot
swing its own forecast.

A page that has not changed at all on launch night is a page Exophase has not refreshed
yet: the rules' own launch-night recount (638 tracked players, then 3,868 after the
refresh) gives the jump a refresh applies, so the rates divide by it and the trophy every
player has stays at 100.

The band is on the logit scale: a common term for the level M/N, calibrated on the case's
own held-out reads and grown by the square root of the horizon ratio, plus a counting term
1/sqrt(the trophy's forecast earners) for the integer counts, plus a share-drift term.

Deterministic: no randomness and no clock reads, so the grader's two runs write the same
bytes.
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
# The jump the launch-night refresh applied to the tracked-player count: 3,868 / 638,
# the two counts RULES.txt recounts for 2026-11-18T23:48Z and 2026-11-19T04:30Z.
LAUNCH_JUMP = 3868.0 / 638.0
# Hours since release under which an unchanged page counts as launch night, unrefreshed.
LAUNCH_HOURS = 12.0
SIGMA_COMMON_DEFAULT = 0.22
SIGMA_COMMON_MIN, SIGMA_COMMON_MAX = 0.15, 0.9
SIGMA_SHARE = 0.10
SIGMA_MIN, SIGMA_MAX = 0.05, 2.0
# Exponent clamps: the tracked count and the mean trophies per player both grow, and a
# power law steeper than time itself is a fit to one jump, not to a trend.
B_N = (0.05, 1.1)
B_M = (0.0, 1.2)


def clamp(pct: float) -> float:
    return min(99.99, max(0.01, pct))


def logit(pct: float) -> float:
    p = clamp(pct)
    return math.log(p / (100 - p))


def expit(x: float) -> float:
    if x > 30:
        return 1.0
    if x < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def round4(x: float) -> float | int:
    """x rounded to 4 decimals, half up (JavaScript's Math.round(x*10000)/10000)."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def release_hours(stamp: str, release: str) -> float:
    """Hours from the release date's midnight (UTC) to an ISO 8601 UTC stamp."""
    import datetime as dt

    def parse(txt: str) -> dt.datetime:
        body = txt[:-1] if txt.endswith("Z") else txt
        date_part, _, time_part = body.partition("T")
        y, mo, d = (int(v) for v in date_part.split("-"))
        hh = mm = 0
        ss = 0.0
        if time_part:
            bits = time_part.split(":")
            hh = int(bits[0])
            if len(bits) > 1:
                mm = int(bits[1])
            if len(bits) > 2:
                ss = float(bits[2])
        return dt.datetime(y, mo, d, hh, mm, int(ss), tzinfo=dt.timezone.utc) + dt.timedelta(seconds=ss - int(ss))

    day = parse(release if "T" in release else release + "T00:00:00Z")
    return (parse(stamp) - day).total_seconds() / 3600.0


def distinct_reads(history: list) -> list:
    """One entry per change in the page: a run of unchanged reads is dated at its first read."""
    out = []
    prev = None
    for read in history:
        key = (read.get("players_tracked"), read.get("trophies_earned"), tuple(read.get("rates") or ()))
        if key == prev:
            continue
        prev = key
        out.append(read)
    return out


def build_points(history: list, release: str) -> list:
    """[{t, n, tot, rates}] with t the hours since release (floored at a quarter hour)."""
    pts = []
    for read in distinct_reads(history):
        n = float(read.get("players_tracked") or 0.0)
        rates = read.get("rates") or []
        earned = read.get("trophies_earned")
        tot = float(earned) if isinstance(earned, (int, float)) and earned and earned > 0 else 0.0
        if tot <= 0.0:
            tot = sum(r * n / 100.0 for r in rates if isinstance(r, (int, float)))
        if n <= 0.0 or tot <= 0.0 or not rates:
            continue
        t = max(release_hours(read.get("at") or "", release), 0.25)
        pts.append({"t": t, "n": n, "tot": tot, "rates": list(rates)})
    pts.sort(key=lambda p: p["t"])
    return pts


def loglog(pts: list) -> tuple[float, float]:
    """Least squares ln y = a + b ln t over (t, y), y > 0, t > 0."""
    xs = [math.log(t) for t, y in pts]
    ys = [math.log(y) for t, y in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0.0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return b, my - b * mx


def line_at(pts: list, t_star: float) -> float | None:
    """A straight line through the points, read at t_star, with a rising-only slope."""
    n = len(pts)
    if n < 2:
        return None
    mt = sum(t for t, _ in pts) / n
    my = sum(y for _, y in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    if den <= 0.0:
        return None
    k = sum((t - mt) * (y - my) for t, y in pts) / den
    k = max(k, 0.0)
    return my + k * (t_star - mt)


def predict(pts: list, t_star: float, b_lo: float, b_hi: float, window: int = 4) -> float | None:
    """Blend of a clamped power law and a straight line through the last reads."""
    if not pts:
        return None
    if len(pts) == 1:
        return pts[0][1]
    b, _ = loglog(pts)
    b = min(b_hi, max(b_lo, b))
    a = sum(math.log(y) - b * math.log(t) for t, y in pts) / len(pts)
    power = math.exp(a + b * math.log(max(t_star, 1e-6)))
    lin = line_at(pts[-window:], t_star)
    if lin is not None and lin > 0.0:
        return math.sqrt(power * lin)
    return power


def share_series(points: list, i: int) -> list:
    """[(t, s_i)] for trophy i where the read lists it."""
    out = []
    for p in points:
        if i >= len(p["rates"]):
            continue
        r = p["rates"][i]
        if not isinstance(r, (int, float)) or r <= 0.0:
            continue
        s = (r * p["n"] / 100.0) / p["tot"]
        if s <= 0.0:
            continue
        out.append((p["t"], s))
    return out


def share_slope(series: list, prior: float, k: float = 4.0) -> float:
    """Log-log slope of a trophy's share, shrunk towards the pooled slope by k pseudo-reads."""
    if len(series) < 2:
        return prior
    xs = [math.log(t) for t, _ in series]
    ys = [math.log(s) for _, s in series]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0.0:
        return prior
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    b = min(1.0, max(-1.0, b))
    return (n * b + k * prior) / (n + k)


def forecast_rates(points: list, t_star: float, count: int) -> tuple[list, list, float | None]:
    """(rates, earners, sigma_common) at t_star for the case's trophies; sigma None = calibrate."""
    last = points[-1]
    flat = len(points) == 1 and last["t"] <= LAUNCH_HOURS
    if flat:
        # The page has never been refreshed: the refresh multiplies the tracked count.
        n_pred = last["n"] * LAUNCH_JUMP
        m_pred = last["tot"] / last["n"]
        rates, earners = [], []
        for i in range(count):
            r = last["rates"][i] if i < len(last["rates"]) else None
            if not isinstance(r, (int, float)) or r <= 0.0:
                rates.append(None)
                earners.append(1.0)
                continue
            if r >= 99.5:
                rates.append(99.99)
                earners.append(n_pred)
                continue
            val = min(99.5, r * last["n"] / n_pred)
            rates.append(val)
            earners.append(val / 100.0 * n_pred)
        return rates, earners, 0.08

    n_pred = predict([(p["t"], p["n"]) for p in points], t_star, *B_N)
    m_pred = predict([(p["t"], p["tot"] / p["n"]) for p in points], t_star, *B_M)
    if n_pred is None or m_pred is None or n_pred <= 0.0 or m_pred <= 0.0:
        n_pred, m_pred = last["n"], last["tot"] / last["n"]

    series = [share_series(points, i) for i in range(count)]
    raw = []
    for s in series:
        if len(s) >= 2:
            xs = [math.log(t) for t, _ in s]
            ys = [math.log(v) for _, v in s]
            mx = sum(xs) / len(xs)
            my = sum(ys) / len(ys)
            den = sum((x - mx) ** 2 for x in xs)
            raw.append(0.0 if den <= 0.0 else min(1.0, max(-1.0, sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den)))
    prior = sorted(raw)[len(raw) // 2] if raw else 0.0
    prior = min(0.3, max(-0.3, prior))

    rates, earners = [], []
    for i in range(count):
        s = series[i]
        if not s:
            rates.append(None)
            earners.append(1.0)
            continue
        t_last, s_last = s[-1]
        beta = share_slope(s, prior)
        scale = (max(t_star, t_last) / t_last) ** beta
        share = min(0.999, max(1e-9, s_last * scale))
        val = min(99.5, 100.0 * share * m_pred)
        if i < len(last["rates"]) and isinstance(last["rates"][i], (int, float)) and last["rates"][i] >= 99.5:
            val = 99.99
        rates.append(val)
        earners.append(max(val, 1e-6) / 100.0 * n_pred)
    return rates, earners, None


def calibrate_common(points: list, t_star: float, count: int) -> float:
    """The level's logit spread: the case's own held-out reads, grown by sqrt(horizon ratio)."""
    if len(points) < 4:
        return SIGMA_COMMON_DEFAULT
    errs, ratios = [], []
    for j in range(max(2, len(points) - 3), len(points)):
        prefix, held = points[:j], points[j]
        rates, _, _ = forecast_rates(prefix, held["t"], count)
        devs = []
        for pred, obs in zip(rates, held["rates"]):
            if pred is None or not isinstance(obs, (int, float)) or obs <= 0.0:
                continue
            devs.append(logit(pred) - logit(obs))
        if not devs:
            continue
        errs.append(math.sqrt(sum(d * d for d in devs) / len(devs)))
        step = max(held["t"] - prefix[-1]["t"], 1e-6)
        ratios.append(max(t_star - prefix[-1]["t"], 0.0) / step)
    if not errs:
        return SIGMA_COMMON_DEFAULT
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    ratio = sorted(ratios)[len(ratios) // 2] if ratios else 1.0
    grown = rms * math.sqrt(max(ratio, 1.0))
    return min(SIGMA_COMMON_MAX, max(SIGMA_COMMON_MIN, 0.10 + 0.75 * grown))


def forecast_case(case: dict, name: str) -> dict:
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    history = case.get("history") or []
    if not history:
        raise ValueError(f"{name} has no history")
    trophies = case.get("trophies") or []
    release = str((case.get("game") or {}).get("release_date") or "2026-11-19")
    points = build_points(history, release)
    if not points:
        raise ValueError(f"{name} has no usable read")
    t_star = release_hours(case.get("target") or case.get("at") or "", release)
    if t_star <= points[-1]["t"]:
        t_star = points[-1]["t"] + case.get("horizon_minutes", 0) / 60.0
    rates, earners, sigma_flat = forecast_rates(points, t_star, len(trophies))
    sigma_common = sigma_flat if sigma_flat is not None else calibrate_common(points, t_star, len(trophies))
    rows = []
    for i, trophy in enumerate(trophies):
        val = rates[i]
        if val is None:
            val = points[-1]["rates"][i] if i < len(points[-1]["rates"]) else 1.0
        if not isinstance(val, (int, float)) or val <= 0.0:
            val = 1.0
        sigma = math.sqrt(sigma_common ** 2 + 1.0 / max(earners[i], 2.0) + SIGMA_SHARE ** 2)
        if val >= 99.0:
            sigma = min(sigma, 0.08)
        sigma = min(SIGMA_MAX, max(SIGMA_MIN, sigma))
        base = logit(val)
        qs = [round4(100.0 * expit(base + z * sigma)) for z in Z]
        qs = sorted(min(100.0, max(0.0, q)) for q in qs)
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
