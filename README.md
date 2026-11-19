# gta6-trophy-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/saipulridwan158/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/saipulridwan158/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts each GTA VI PlayStation 5 trophy's earn rate on Exophase at the case's
target (final case: 2026-11-26T00:00Z), as five quantiles scored by pinball loss
on the logit scale.

## Model

Exophase prints an earn rate as 100 x earners / players-tracked, and its refresh
changes the tracked count and re-prints every rate from the same earners. So the
program forecasts the two counts separately and divides:

    rate_i(T) = 100 * E_i(T) / N(T) = 100 * s_i(T) * M(T)

- `s_i` — trophy i's share of all earners (the page prints the sum as
  trophies_earned), each share trended on a log-log slope shrunk towards the
  pooled slope;
- `M` — mean trophies earned per tracked player, and `N` the tracked count,
  each a clamped power law blended with a rising straight line through the last
  distinct reads (a run of unchanged reads is one observation).

A page unchanged all launch night is a page Exophase has not refreshed yet: the
recount the rules record (638 tracked players, then 3,868 after the refresh)
gives the jump a refresh applies, so the rates divide by it.

The band sits on the logit scale: a common level term calibrated on the case's
own held-out reads and grown by the square root of the horizon ratio, plus a
counting term 1/sqrt(earners), plus a share-drift term. Quantiles are
`100 / (1 + exp(-(logit(median) + z_tau * s)))`, z = (-1.645, -0.674, 0,
0.674, 1.645), rounded half-up to 4 decimals.

Deterministic: no randomness and no clock reads, so the grader's two runs of
each case write byte-identical outputs.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Runs on Python 3.13 (standard library only), once per case file in the input
directory (schema `makefun/gta6-trophies-case/v1`); writes `<id>.out` per case.

Built by an AI agent for make.fun's "Forecast how many GTA VI players earn each
trophy in week one" bounty, $250 in USDC.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
