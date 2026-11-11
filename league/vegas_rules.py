"""Vegas Pit lab v1. Integer cents; fixed paylines, wilds and bounded tumbles."""
from itertools import product
import secrets

VERSION = 1
START_BALANCE = 500_000
BETS = (500, 1_000, 2_000, 2_500, 5_000, 7_500, 10_000, 15_000, 20_000, 30_000, 50_000)
DEFAULT_BET = 5_000
BONUS_BUY_MULTIPLIER = 20
BONUS_BUY_SPINS = 10
MAX_TUMBLES = 6
MAX_FREE_SPINS = 30
SYMBOLS = (
    {"key": "tyre", "name": "Bono, my tyres!", "weight": 18, "pays": (6, 18, 60)},
    {"key": "duck", "name": "GP2 Engine", "weight": 16, "pays": (6, 20, 70)},
    {"key": "banana", "name": "Разбитый кубок Норриса", "weight": 18, "pays": (8, 25, 90)},
    {"key": "berry", "name": "Банана Леклер", "weight": 16, "pays": (8, 25, 90)},
    {"key": "russell", "name": "Клубника Макс", "weight": 12, "pays": (12, 40, 140)},
    {"key": "toto", "name": "Кими с мороженым", "weight": 9, "pays": (18, 60, 200)},
    {"key": "bath", "name": "Алонсо в шезлонге", "weight": 6, "pays": (25, 100, 400)},
    {"key": "wild", "name": "Банный судья · Wild", "weight": 3, "pays": (30, 150, 600)},
    {"key": "scatter", "name": "Тото Вольф · Бонус", "weight": 2, "pays": ()},
)
BY_KEY = {item["key"]: item for item in SYMBOLS}
STRIP = tuple(item["key"] for item in SYMBOLS for _ in range(item["weight"]))


def _paylines():
    lines = [(row,) * 5 for row in range(4)]
    patterns = sorted((p for p in product(range(4), repeat=5)
                       if all(abs(a-b) <= 1 for a, b in zip(p, p[1:]))),
                      key=lambda p: (sum(abs(a-b) for a,b in zip(p,p[1:])),
                                     abs(p[0]-p[-1]), p))
    for pattern in patterns:
        for line in (pattern, tuple(3-row for row in pattern)):
            if line not in lines:
                lines.append(line)
        if len(lines) >= 40:
            return tuple(lines[:40])
    raise AssertionError("Not enough unique paylines")


PAYLINES = _paylines()


def random_grid(choice=secrets.choice):
    return [[choice(STRIP) for _ in range(4)] for _ in range(5)]


def bonus_buy_grid(choice=secrets.choice):
    """Entry animation only; no line payments or random extra awards on purchase."""
    regular = tuple(key for key in STRIP if key not in ("scatter", "wild"))
    grid = [[choice(regular) for _ in range(4)] for _ in range(5)]
    for col, row in ((0, 1), (2, 2), (4, 1)):
        grid[col][row] = "scatter"
    # This is a purchase entry, not a paid outcome. Avoid displaying unpaid
    # matching lines behind the three Scatter symbols.
    second_reel = tuple(key for key in regular if key not in grid[0])
    grid[1] = [choice(second_reel) for _ in range(4)]
    return grid


def evaluate(grid, bet, multiplier=1):
    """One highest-paying interpretation per line; scatters never substitute."""
    wins = []
    for number, line in enumerate(PAYLINES, 1):
        values = [grid[col][row] for col, row in enumerate(line)]
        best = None
        for symbol in SYMBOLS:
            if not symbol["pays"]:
                continue
            count = 0
            for value in values:
                if value not in (symbol["key"], "wild"):
                    break
                count += 1
            if count < 3:
                continue
            # Total stake covers all 40 lines. Round half a cent upwards.
            amount = (bet * symbol["pays"][count-3] * multiplier + 20) // 40
            if best is None or amount > best["amount"]:
                best = {"line": number, "symbol": symbol["key"], "count": count,
                        "amount": amount, "rows": list(line),
                        "cells": [[col, line[col]] for col in range(count)]}
        if best:
            wins.append(best)
    return wins


def outcome(bet, *, free=False, scenario="random", choice=secrets.choice):
    grid = random_grid(choice)
    # Explicit staff-lab fixtures, never exposed to public games or standings.
    if scenario == "bonus":
        for col in range(3):
            grid[col][3] = "scatter"
    elif scenario in ("bigwin", "wild"):
        for col in range(5):
            grid[col][1] = "bath" if scenario == "bigwin" else ("wild" if col % 2 else "banana")
    rounds, payout, scatters = [], 0, 0
    for cascade in range(MAX_TUMBLES):
        multiplier = (cascade+1) * (2 if free else 1)
        scatters = max(scatters, sum(column.count("scatter") for column in grid))
        wins = evaluate(grid, bet, multiplier)
        amount = sum(win["amount"] for win in wins)
        rounds.append({"grid": [column[:] for column in grid], "wins": wins,
                       "amount": amount, "multiplier": multiplier})
        payout += amount
        if not wins or cascade == MAX_TUMBLES-1:
            break
        removed = {tuple(cell) for win in wins for cell in win["cells"]}
        for col in range(5):
            kept = [value for row, value in enumerate(grid[col]) if (col, row) not in removed]
            grid[col] = [choice(STRIP) for _ in range(4-len(kept))] + kept
    awarded = ((4 if free else 8 + min(scatters-3, 2)*2) if scatters >= 3 else 0)
    return {"rounds": rounds, "payout": payout, "scatters": scatters,
            "awarded": awarded, "free": free, "bet": bet, "scenario": scenario,
            "cascade_limit": len(rounds) == MAX_TUMBLES and bool(rounds[-1]["wins"])}
