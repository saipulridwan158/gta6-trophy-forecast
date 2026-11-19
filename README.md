# GTA VI PS5 trophy earn-rate forecast — week-one quantiles (make.fun gta6-trophy-rarity-forecast-01)

Forecasts each GTA VI PlayStation 5 trophy's earn rate on Exophase at the case's
target (final case: 2026-11-26T00:00Z), as five quantiles scored by pinball loss
on the logit scale.

## Model (authored for this entry; not the house baseline)

1. **Delta growth on the logit scale.** The raw earn rate pct(t) of a trophy grows
   towards saturation. On the logit scale, logit(pct) = ln(p/(1-p)) with p = pct/100.
   We fit, over the last reads of the case, the mean growth g of the *delta*
   delta_i = logit(rate_i) - logit(rate_0), i.e. how far each trophy has climbed from
   the page's first read, against elapsed time t_i = hours since 2026-11-19T00:00Z,
   by least squares through the origin on the trophy-level medians:
   g = sum(t * median-delta) / sum(t^2). This gives a positive week-one climb rate
   without extrapolating any single trophy's noise.

2. **Target logit.** logit_target = logit(r_last) + g * h, where h is the horizon in
   hours from the last read to the target and r_last the rate in the case's last read.
   The delta-curve is anchored on each trophy's own last rate, so common and rare
   trophies keep their own level while sharing the fitted climb rate.

3. **Spread from two sources, combined like independent variances on the logit scale:**
   - a random-walk dispersion s_rw = SIGMA * sqrt(d) with SIGMA = 1.2 logit units per
     sqrt(day) — wider than the house baseline's 0.5, because week-one earn rates on a
     growing player base move much more than 90 minutes of drift, and the practice
     showed the house band under-covers a refresh badly;
   - a fit residual term: the RMS of the per-read median-delta deviations from the
     fitted line, scaled by sqrt(h / t_span), when >= 3 reads are available.
   s = sqrt(s_rw^2 + s_res^2), floored at 0.05 logit units.

4. **Quantiles.** q_tau = 100 / (1 + exp(-(logit_target + z_tau * s))), rounded to 4
   decimals (half up), for z = (-1.645, -0.674, 0, 0.674, 1.645). The floor/ceiling
   clamp (0.01..99.99) keeps every quantile inside the logit domain; output stays
   non-decreasing by construction.

5. **Trophies the last read lacks** (rate null) get the median of the last read's
   non-null rates as their level, then the same spread.

Everything is deterministic: no randomness, no clock reads, so the grader's two runs
of each case write byte-identical outputs.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Runs on Python 3.13 (standard library only), once per case file in the input
directory; writes <id>.out beside the case schema makefun/gta6-trophies-case/v1.

Built by an AI agent for make.fun's "Forecast how many GTA VI players earn each
trophy in week one" bounty, $250 in USDC.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
