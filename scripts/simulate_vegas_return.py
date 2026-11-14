"""Reproducible Monte Carlo using production rules, not browser payouts.

Run: python scripts/simulate_vegas_return.py --cycles 100000 --bonuses 30000
Reports 95% confidence intervals; RTP is an expectation, not a player promise.
"""
import argparse
import math
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from league import vegas_rules as rules


def series(rng, remaining, bet):
    payout = 0
    while remaining:
        result = rules.outcome(bet, free=True, choice=rng.choice)
        payout += result["payout"]
        remaining = min(rules.MAX_FREE_SPINS, remaining - 1 + result["awarded"])
    return payout


def report(label, values):
    mean = statistics.mean(values)
    error = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    print(f"{label}: n={len(values)} RTP={mean:.4%}; 95% CI [{mean-error:.4%}, {mean+error:.4%}]", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=100000)
    parser.add_argument("--bonuses", type=int, default=30000)
    parser.add_argument("--seed", type=int, default=20261114)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    bet = 5000
    paid = []
    for _ in range(args.cycles):
        result = rules.outcome(bet, choice=rng.choice)
        paid.append((result["payout"] + series(rng, result["awarded"], bet)) / bet)
    report("Paid spins including all triggered free spins", paid)
    cost = bet * rules.BONUS_BUY_MULTIPLIER
    bought = [max(cost * rules.BONUS_MIN_RETURN_PERCENT // 100,
                  series(rng, rules.BONUS_BUY_SPINS, bet)) / cost
              for _ in range(args.bonuses)]
    report("Purchased bonus including retriggers and minimum return", bought)
    print(f"Purchased bonus median: {statistics.median(bought):.2%}; profitable: {sum(v>1 for v in bought)/len(bought):.2%}", flush=True)


if __name__ == "__main__":
    main()
