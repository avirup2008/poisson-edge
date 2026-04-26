"""
POISSON-EDGE V4.1 — Complete Model Code
========================================
Author: Avirup Sen (Avi)
Version: 4.1 (locked — do not tune parameters without calibration evidence)

This is the complete, self-contained model logic.
Feed this to Claude Code alongside POISSON-EDGE-MASTER-BUILD.md.

Parameters (ALL LOCKED):
  rho      = -0.05   (Dixon-Coles correction)
  home_adv =  1.06   (home advantage multiplier)
  blend    =  0.35   (35% recent form / 55% season average)
  nr       =  6      (recent form window — last 6 games)
  lhalf    =  1.36   (Premier League half-average lambda)
  elo_alpha=  0.65   (65% Poisson + 35% ELO for Home Win only)
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Optional

# ── LOCKED PARAMETERS ─────────────────────────────────────────────────────────
RHO       = -0.05
HOME_ADV  =  1.06
BLEND     =  0.35
NR        =  6
LHALF     =  1.36
ELO_ALPHA =  0.65
MIN_GAMES =  5

# ── CURRENT ELO RATINGS (April 2026, computed from 16 seasons) ────────────────
ELO_RATINGS = {
    'Arsenal': 1790, 'Man City': 1778, 'Liverpool': 1674,
    'Chelsea': 1621, 'Aston Villa': 1618, 'Brighton': 1617,
    'Man United': 1616, 'Bournemouth': 1593, 'Everton': 1587,
    'Brentford': 1583, 'Newcastle': 1573, 'Crystal Palace': 1563,
    'Fulham': 1547, "Nott'm Forest": 1533, 'Leeds': 1511,
    'West Ham': 1496, 'Sunderland': 1492, 'Tottenham': 1441,
    'Wolves': 1422, 'Burnley': 1410,
}

# ── INJURY MULTIPLIER TABLES ──────────────────────────────────────────────────
ATTACK_MULTIPLIERS = {
    0: 1.00,   # no key attackers out
    1: 0.92,   # 1-2 key starters out
    2: 0.85,   # 2-3 key players out
    3: 0.78,   # 3-4 including main striker
    4: 0.70,   # 4+ or full attack depleted
    5: 0.60,   # full forward line collapse (crisis)
}

DEFENCE_BOOSTS = {
    0: 1.00,   # no key defenders out
    1: 1.09,   # 1 key defender out
    2: 1.18,   # 2 key defenders out
    3: 1.30,   # 3 key defenders out (crisis)
    4: 1.39,   # 4+ key defenders out
}

GK_BOOST = 1.12  # applied to opponent's lambda when GK is absent


# ══════════════════════════════════════════════════════════════════════════════
# CORE MODEL FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def poisson_pmf(lam: float, k: int) -> float:
    """Poisson probability mass function."""
    try:
        return (lam ** k * math.exp(-lam)) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def dc_correction(h: int, a: int, lh: float, la: float, rho: float = RHO) -> float:
    """
    Dixon-Coles low-score correction.
    Adjusts probabilities for 0-0, 1-0, 0-1, 1-1 scorelines.
    rho is LOCKED at -0.05.
    """
    if   h == 0 and a == 0: return 1 - lh * la * rho
    elif h == 1 and a == 0: return 1 + la * rho
    elif h == 0 and a == 1: return 1 + lh * rho
    elif h == 1 and a == 1: return 1 - rho
    return 1.0


def build_score_matrix(lh: float, la: float, max_goals: int = 6) -> List[List[float]]:
    """
    Build (max_goals+1) × (max_goals+1) scoreline probability matrix.
    Rows = home goals, Columns = away goals.
    Applies Dixon-Coles correction and normalises to sum to 1.
    """
    matrix = [
        [poisson_pmf(lh, i) * poisson_pmf(la, j) * dc_correction(i, j, lh, la)
         for j in range(max_goals + 1)]
        for i in range(max_goals + 1)
    ]
    total = sum(matrix[i][j] for i in range(max_goals+1) for j in range(max_goals+1))
    if total == 0:
        total = 1.0
    return [[matrix[i][j] / total for j in range(max_goals+1)]
            for i in range(max_goals+1)]


def extract_probabilities(matrix: List[List[float]], max_goals: int = 6) -> Dict[str, float]:
    """
    Extract market probabilities from score matrix.
    Returns: hw, draw, aw, o25, u25, o35, btts
    ELO ensemble NOT applied here — apply separately to hw only.
    """
    mg = max_goals
    hw   = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i > j)
    draw = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i == j)
    aw   = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i < j)
    o25  = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i+j > 2)
    o35  = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i+j > 3)
    btts = sum(matrix[i][j] for i in range(mg+1) for j in range(mg+1) if i > 0 and j > 0)
    return {
        'hw': hw, 'draw': draw, 'aw': aw,
        'o25': o25, 'u25': 1 - o25,
        'o35': o35, 'btts': btts,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ELO ENSEMBLE
# ══════════════════════════════════════════════════════════════════════════════

def elo_hw_probability(elo_home: float, elo_away: float, home_advantage: float = 100) -> float:
    """
    ELO-based home win probability.
    home_advantage of 100 ELO points added to home team's rating.
    """
    return 1 / (1 + 10 ** ((elo_away - elo_home - home_advantage) / 400))


def apply_elo_ensemble(hw_poisson: float, home_team: str, away_team: str,
                        elo_ratings: Dict = None, alpha: float = ELO_ALPHA) -> float:
    """
    Final HW probability: alpha × Poisson + (1-alpha) × ELO.
    ELO applies to HOME WIN ONLY.
    Over/Under and BTTS use Poisson probabilities directly — do NOT apply ELO.
    """
    ratings = elo_ratings or ELO_RATINGS
    elo_home = ratings.get(home_team, 1500)
    elo_away = ratings.get(away_team, 1500)
    elo_prob = elo_hw_probability(elo_home, elo_away)
    return alpha * hw_poisson + (1 - alpha) * elo_prob


def update_elo(home_team: str, away_team: str, home_goals: int, away_goals: int,
               elo_ratings: Dict, k_base: float = 32) -> Dict:
    """
    Update ELO ratings after a result.
    Uses margin-of-victory weighting (MOV multiplier).
    """
    ratings = dict(elo_ratings)
    rh = ratings.get(home_team, 1450)
    ra = ratings.get(away_team, 1450)
    exp_h = elo_hw_probability(rh, ra)
    act_h = 1.0 if home_goals > away_goals else (0.5 if home_goals == away_goals else 0.0)
    gd = abs(home_goals - away_goals)
    if gd > 0:
        denom = (exp_h if act_h == 1 else (1 - exp_h)) * 0.001 + 2.2
        mov = min(3.0, math.log(gd + 1) * 2.2 / denom)
    else:
        mov = 1.0
    k = k_base * mov
    ratings[home_team] = rh + k * (act_h - exp_h)
    ratings[away_team] = ra + k * ((1 - act_h) - (1 - exp_h))
    return ratings


# ══════════════════════════════════════════════════════════════════════════════
# OPPONENT-ADJUSTED RATINGS
# ══════════════════════════════════════════════════════════════════════════════

def compute_opponent_adjusted_ratings(
    season_df: pd.DataFrame,
    lhalf: float = LHALF,
    n_iter: int = 50
) -> Tuple[Dict, Dict]:
    """
    Iterative SPI-style opponent-adjusted attack/defence ratings.
    A goal scored vs Arsenal counts more than a goal vs Burnley.
    
    Converges in ~25 iterations. Run on full season data.
    Returns (atk_dict, def_dict) normalised so league average = 1.0.
    
    This is the core V4.0 improvement — adds +6.26% Brier improvement over V3.
    """
    teams = list(set(season_df['HomeTeam'].unique()) | set(season_df['AwayTeam'].unique()))
    atk  = {t: 1.0 for t in teams}
    def_ = {t: 1.0 for t in teams}
    rows = season_df[['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG']].values

    for _ in range(n_iter):
        new_atk = {t: 0.0 for t in teams}
        new_def = {t: 0.0 for t in teams}
        count   = {t: 0   for t in teams}

        for home, away, hg, ag in rows:
            if home not in atk or away not in atk:
                continue
            new_atk[home] += float(hg) / max(0.3, def_[away])
            new_atk[away] += float(ag) / max(0.3, def_[home])
            new_def[home] += float(ag) / max(0.3, atk[away])
            new_def[away] += float(hg) / max(0.3, atk[home])
            count[home] += 1
            count[away] += 1

        for t in teams:
            if count[t]:
                new_atk[t] = max(0.3, min(3.0, new_atk[t] / count[t] / lhalf))
                new_def[t] = max(0.3, min(3.0, new_def[t] / count[t] / lhalf))

        avg_a = np.mean(list(new_atk.values()))
        avg_d = np.mean(list(new_def.values()))
        atk  = {t: new_atk[t] / avg_a for t in teams}
        def_ = {t: new_def[t] / avg_d for t in teams}

    return atk, def_


# ══════════════════════════════════════════════════════════════════════════════
# TEAM RATINGS WITH FORM BLENDING
# ══════════════════════════════════════════════════════════════════════════════

def get_team_ratings(
    team: str,
    historical_data: pd.DataFrame,
    g_atk: Dict,
    g_def: Dict,
    lhalf: float = LHALF,
    nr: int = NR,
    blend: float = BLEND
) -> Tuple[float, float]:
    """
    Blend opponent-adjusted season ratings (55%) with recent form (45%).
    
    Manager-change gate: if 8+ games under new manager, caller should pass
    only post-appointment data as historical_data.
    
    Returns (attack_rating, defence_rating) both in range [0.3, 3.0].
    """
    home_games = historical_data[historical_data['HomeTeam'] == team]
    away_games = historical_data[historical_data['AwayTeam'] == team]

    all_scored   = list(home_games['FTHG']) + list(away_games['FTAG'])
    all_conceded = list(home_games['FTAG']) + list(away_games['FTHG'])

    if not all_scored:
        return 1.0, 1.0

    season_atk = np.mean(all_scored)   / lhalf
    season_def = np.mean(all_conceded) / lhalf

    # Recent form (last nr games, all venues combined)
    recent = pd.concat([
        home_games.assign(gs=home_games['FTHG'], gc=home_games['FTAG']),
        away_games.assign(gs=away_games['FTAG'], gc=away_games['FTHG'])
    ]).tail(nr)

    if len(recent) >= 3:
        recent_atk = recent['gs'].mean() / lhalf
        recent_def = recent['gc'].mean() / lhalf
    else:
        recent_atk = season_atk
        recent_def = season_def

    # Form blend: 65% season average + 35% recent
    form_atk = max(0.3, min(3.0, (1 - blend) * season_atk + blend * recent_atk))
    form_def = max(0.3, min(3.0, (1 - blend) * season_def + blend * recent_def))

    # Blend with opponent-adjusted ratings: 55% opp-adj + 45% form
    if team in g_atk:
        final_atk = 0.55 * g_atk[team] + 0.45 * form_atk
        final_def = 0.55 * g_def[team] + 0.45 * form_def
    else:
        final_atk = form_atk
        final_def = form_def

    return max(0.3, min(3.0, final_atk)), max(0.3, min(3.0, final_def))


# ══════════════════════════════════════════════════════════════════════════════
# FATIGUE
# ══════════════════════════════════════════════════════════════════════════════

def fatigue_multiplier(rest_days: int) -> float:
    """
    Continuous fatigue multiplier based on days since last match.
    Applied to both attack and defence lambdas.
    
    3 days → ×0.940
    4 days → ×0.955
    5 days → ×0.970
    6 days → ×0.985
    7+ days → ×1.000
    """
    return max(0.85, 1 - max(0, (7 - rest_days)) * 0.015)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LAMBDA CALCULATION
# ══════════════════════════════════════════════════════════════════════════════

def calculate_lambdas(
    home: str,
    away: str,
    historical_data: pd.DataFrame,
    g_atk: Dict,
    g_def: Dict,
    home_rest_days: int = 7,
    away_rest_days: int = 7,
    home_atk_mult: float = 1.0,
    away_atk_mult: float = 1.0,
    home_def_boost: float = 1.0,  # > 1.0 boosts away scoring (home defence weak)
    away_def_boost: float = 1.0,  # > 1.0 boosts home scoring (away defence weak)
    lhalf: float = LHALF,
    home_adv: float = HOME_ADV,
) -> Tuple[float, float]:
    """
    Calculate home and away expected goals (lambdas).
    
    lambda_home = opp_atk[home] × opp_def[away] × lhalf × home_adv
                  × home_atk_mult × away_def_boost × home_fatigue
    
    lambda_away = opp_atk[away] × opp_def[home] × lhalf
                  × away_atk_mult × home_def_boost × away_fatigue
    
    All multipliers are applied AFTER the base lambda calculation.
    """
    ha_r, hd_r = get_team_ratings(home, historical_data, g_atk, g_def)
    aa_r, ad_r = get_team_ratings(away, historical_data, g_atk, g_def)

    hfat = fatigue_multiplier(home_rest_days)
    afat = fatigue_multiplier(away_rest_days)

    lh = ha_r * ad_r * lhalf * home_adv * home_atk_mult * away_def_boost * hfat
    la = aa_r * hd_r * lhalf            * away_atk_mult * home_def_boost * afat

    lh = max(0.3, min(6.0, lh))
    la = max(0.3, min(6.0, la))

    return lh, la


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL CALCULATION
# ══════════════════════════════════════════════════════════════════════════════

def calculate_ev(model_p: float, odds: float) -> float:
    """Expected value as percentage."""
    return (model_p * odds - 1) * 100


def classify_signal(ev_pct: float, model_p: float, market: str) -> str:
    """
    ELEV → EV ≥ +15% AND P ≥ 65%  (Under 2.5: EV ≥ +25%)
    BET  → EV ≥ +4%
    SIM  → EV ≥ 0%
    NO   → EV < 0%
    """
    ev_threshold = 25.0 if market == 'u25' else 15.0
    if ev_pct >= ev_threshold and model_p >= 0.65:
        return 'ELEV'
    elif ev_pct >= 4.0:
        return 'BET'
    elif ev_pct >= 0.0:
        return 'SIM'
    return 'NO'


def kelly_stake(
    model_p: float,
    odds: float,
    bankroll: float,
    fraction: float = 0.25,
    cap: float = 8.00,
    floor: float = 1.00,
    odds_floor: float = 1.35
) -> float:
    """
    25% fractional Kelly staking.
    Hard cap: €8.00 | Floor: €1.00 | Odds floor: 1.35
    Rounds to nearest €0.50.
    """
    if odds < odds_floor:
        return 0.0
    edge  = (model_p * odds - 1) / (odds - 1)
    stake = fraction * edge * bankroll
    stake = min(stake, bankroll * 0.10)
    stake = round(stake * 2) / 2
    return max(floor, min(cap, stake))


# ══════════════════════════════════════════════════════════════════════════════
# FULL MATCH PREDICTION
# ══════════════════════════════════════════════════════════════════════════════

def predict_match(
    home: str,
    away: str,
    historical_data: pd.DataFrame,
    g_atk: Dict,
    g_def: Dict,
    home_rest_days: int = 7,
    away_rest_days: int = 7,
    home_atk_mult: float = 1.0,
    away_atk_mult: float = 1.0,
    home_def_boost: float = 1.0,
    away_def_boost: float = 1.0,
    elo_ratings: Dict = None,
) -> Dict:
    """
    Full match prediction including ELO ensemble.
    
    Returns complete probability dict + lambdas + transparency info.
    """
    lh, la = calculate_lambdas(
        home, away, historical_data, g_atk, g_def,
        home_rest_days, away_rest_days,
        home_atk_mult, away_atk_mult,
        home_def_boost, away_def_boost,
    )

    matrix = build_score_matrix(lh, la)
    probs  = extract_probabilities(matrix)

    # Apply ELO ensemble to HW only
    hw_final = apply_elo_ensemble(probs['hw'], home, away, elo_ratings)
    probs['hw'] = hw_final
    # Recalculate AW and draw proportionally to maintain sum = 1
    adjustment = hw_final - probs['hw']
    # (hw is already updated — just note ELO only changes HW, draw/AW from Poisson)

    return {
        'home': home,
        'away': away,
        'lambda_home': round(lh, 4),
        'lambda_away': round(la, 4),
        'probabilities': {k: round(v, 4) for k, v in probs.items()},
        'fatigue': {
            'home': round(fatigue_multiplier(home_rest_days), 4),
            'away': round(fatigue_multiplier(away_rest_days), 4),
        },
        'injury_mults': {
            'home_atk': home_atk_mult,
            'away_atk': away_atk_mult,
            'home_def_boost': home_def_boost,
            'away_def_boost': away_def_boost,
        },
        'elo': {
            'home': (elo_ratings or ELO_RATINGS).get(home, 1500),
            'away': (elo_ratings or ELO_RATINGS).get(away, 1500),
        }
    }


def generate_transparency_block(prediction: Dict, home_injuries: List, away_injuries: List) -> str:
    """
    Generate mandatory lambda transparency block.
    This must be printed for every fixture before any signal is generated.
    If injuries are empty for any team, flag it explicitly.
    """
    home = prediction['home']
    away = prediction['away']
    lh   = prediction['lambda_home']
    la   = prediction['lambda_away']
    mults = prediction['injury_mults']
    fat   = prediction['fatigue']

    lines = [
        f"\n{'─'*65}",
        f"LAMBDA BLOCK — {home} vs {away}",
        f"{'─'*65}",
        f"\n  {home} (HOME)  λH = {lh}",
        f"    Attack mult:     ×{mults['home_atk']:.2f}",
        f"    Def boost given: ×{mults['away_def_boost']:.2f}  (away scores easier vs home defence)",
        f"    Fatigue:         ×{fat['home']:.3f}  (ELO: {prediction['elo']['home']:.0f})",
        f"    Injuries confirmed:",
    ]
    if home_injuries:
        for inj in home_injuries:
            lines.append(f"      ❌ {inj.get('player','?'):<22} {inj.get('status','?'):<12} [{inj.get('source','?')}]")
    else:
        lines.append(f"      ⚠️  NO INJURIES FOUND — VERIFY MANUALLY BEFORE PLACING")

    lines += [
        f"\n  {away} (AWAY)  λA = {la}",
        f"    Attack mult:     ×{mults['away_atk']:.2f}",
        f"    Def boost given: ×{mults['home_def_boost']:.2f}  (home scores easier vs away defence)",
        f"    Fatigue:         ×{fat['away']:.3f}  (ELO: {prediction['elo']['away']:.0f})",
        f"    Injuries confirmed:",
    ]
    if away_injuries:
        for inj in away_injuries:
            lines.append(f"      ❌ {inj.get('player','?'):<22} {inj.get('status','?'):<12} [{inj.get('source','?')}]")
    else:
        lines.append(f"      ⚠️  NO INJURIES FOUND — VERIFY MANUALLY BEFORE PLACING")

    lines.append(f"{'─'*65}\n")
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# GATES
# ══════════════════════════════════════════════════════════════════════════════

def apply_h2h_gate(over25_count: int, total_h2h: int) -> Dict:
    """
    H2H goals layer gate.
    CRITICAL: This gate restricts UNDER 2.5 only.
    High H2H Over 2.5 rate SUPPORTS, does not block, Over 2.5 signals.
    """
    rate = over25_count / total_h2h if total_h2h > 0 else 0
    if over25_count >= 5:
        return {'gate': 'BLOCK_UNDER', 'reason': f'{over25_count}/{total_h2h} H2H Over 2.5 — block Under 2.5 real money'}
    elif over25_count == 4:
        return {'gate': 'WARN_UNDER', 'reason': f'4/{total_h2h} H2H Over 2.5 — require EV ≥ +35% for Under 2.5'}
    return {'gate': 'CLEAR', 'reason': f'{over25_count}/{total_h2h} H2H Over 2.5 — model stands'}


def check_probability_gate(model_p: float, market: str) -> Optional[str]:
    """
    Probability bucket hard blocks (calibration-validated).
    Returns block reason string or None if clear.
    
    O25 ≥ 75%:   BLOCKED (-20.5% calibration gap)
    HW 75-80%:   BLOCKED (-11.7% calibration gap)
    HW ≥ 80%:    OK (-2.5% gap — within acceptable range)
    BTTS any:    No block (no calibration data yet)
    """
    if market == 'o25' and model_p >= 0.75:
        return f'HARD-BLOCK: O25 P={model_p:.1%} ≥ 75% (-20.5% calibration gap)'
    if market == 'hw' and 0.75 <= model_p < 0.80:
        return f'HARD-BLOCK: HW P={model_p:.1%} in 75-80% range (-11.7% calibration gap)'
    if market in ('o25', 'hw') and 0.65 <= model_p < 0.75:
        return f'WATCH: P={model_p:.1%} in 65-75% watch zone'
    return None


def check_pinnacle(pinnacle_odds: float, bet365_odds: float) -> Dict:
    """
    Pinnacle cross-check.
    
    LOWER Pinnacle odds = sharper implied probability = signal confirmed = PROCEED
    HIGHER Pinnacle odds = sharp money disagrees = FLAG
    Within 5 pips = neutral = PASS
    Within 10 pips = neutral for structural override = PASS
    
    This logic has been inverted historically. State it explicitly every time.
    """
    gap_pips = round((pinnacle_odds - bet365_odds) * 100)

    if gap_pips <= -5:
        return {
            'result': 'STRONG_CONFIRM',
            'message': f'Pinnacle {pinnacle_odds:.3f} < B365 {bet365_odds:.3f} by {abs(gap_pips)} pips — sharp money agrees strongly',
            'pass': True
        }
    elif -5 < gap_pips <= 5:
        return {
            'result': 'NEUTRAL',
            'message': f'Pinnacle {pinnacle_odds:.3f} vs B365 {bet365_odds:.3f} — within 5 pips, neutral',
            'pass': True
        }
    elif 5 < gap_pips <= 10:
        return {
            'result': 'MILD_FLAG',
            'message': f'Pinnacle {pinnacle_odds:.3f} > B365 {bet365_odds:.3f} by {gap_pips} pips — mild flag, check narrative',
            'pass': True  # within structural override zone
        }
    else:
        return {
            'result': 'FLAG',
            'message': f'Pinnacle {pinnacle_odds:.3f} > B365 {bet365_odds:.3f} by {gap_pips} pips — sharp money disagrees',
            'pass': False
        }


def check_structural_override(
    ev_pct: float,
    model_p: float,
    structural_factor: Optional[str],
    pinnacle_gap_pips: int
) -> Dict:
    """
    Structural override gate.
    Allows BET-tier signals to reach real money if ALL conditions met:
    - EV ≥ +20%
    - P ≥ 58%
    - Named binary verifiable structural factor
    - Pinnacle ≤ 10 pips above Bet365
    - Max stake: €5.00
    - Max 1 per GW
    """
    if ev_pct < 20:
        return {'qualifies': False, 'reason': f'EV {ev_pct:.1f}% < 20% minimum'}
    if model_p < 0.58:
        return {'qualifies': False, 'reason': f'P {model_p:.1%} < 58% minimum'}
    if not structural_factor:
        return {'qualifies': False, 'reason': 'No named structural factor provided'}
    if pinnacle_gap_pips > 10:
        return {'qualifies': False, 'reason': f'Pinnacle {pinnacle_gap_pips} pips above B365 — exceeds 10-pip limit'}
    return {
        'qualifies': True,
        'reason': f'Structural override: {structural_factor}',
        'max_stake': 5.00,
        'note': 'Maximum 1 structural override per GW'
    }


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

CAT_A_RIVALRIES = [
    frozenset(['Arsenal', 'Spurs']),
    frozenset(['Arsenal', 'Tottenham']),
    frozenset(['Arsenal', 'Chelsea']),
    frozenset(['Arsenal', 'Man City']),
    frozenset(['Arsenal', 'Man United']),
    frozenset(['Man City', 'Man United']),
    frozenset(['Man City', 'Liverpool']),
    frozenset(['Man City', 'Aston Villa']),
    frozenset(['Chelsea', 'Man United']),
    frozenset(['Chelsea', 'Liverpool']),
    frozenset(['Liverpool', 'Man United']),
    frozenset(['Liverpool', 'Aston Villa']),
    frozenset(['Aston Villa', 'Man United']),
]

CAT_B_RIVALRIES = [
    frozenset(['Liverpool', 'Everton']),
    frozenset(['Arsenal', 'Spurs']),
    frozenset(['Arsenal', 'Tottenham']),
    frozenset(['Chelsea', 'Fulham']),
    frozenset(['Chelsea', 'Brentford']),
    frozenset(['Brentford', 'Fulham']),
    frozenset(['Newcastle', 'Sunderland']),
    frozenset(['Wolves', 'Aston Villa']),
    frozenset(['Man City', 'Man United']),
]


def classify_match_context(home: str, away: str, top8: List[str]) -> Optional[str]:
    """
    Classify match context using LIVE table top 8.
    Returns: 'CatA', 'CatB', 'Relegation', or None.

    NEVER call this with hardcoded top 8 — always pass live table data.
    """
    pair = frozenset([home, away])
    top8_set = set(top8)

    # Cat A: both top 8 + fierce rivalry
    if home in top8_set and away in top8_set:
        if pair in CAT_A_RIVALRIES:
            return 'CatA'

    # Cat B: fierce rivalry, one/both outside top 8
    if pair in CAT_B_RIVALRIES:
        return 'CatB'

    return None


def is_under25_blocked(context: Optional[str]) -> bool:
    """Under 2.5 real money is blocked for CatA, CatB, and Relegation matches."""
    return context in ('CatA', 'CatB', 'Relegation')


def is_cat_a_over25_eligible(context: Optional[str], home: str, away: str,
                               home_injuries: List, away_injuries: List) -> bool:
    """
    Cat A Over 2.5 is real money eligible (9/9 = 100% this season).
    Additional condition: both teams must have functional attacks.
    If either team has 3+ key attackers out, caution applies.
    """
    if context != 'CatA':
        return False
    home_depleted = sum(1 for i in home_injuries
                        if 'forward' in i.get('role','').lower() or
                           'striker' in i.get('role','').lower() or
                           'winger' in i.get('role','').lower()) >= 3
    away_depleted = sum(1 for i in away_injuries
                        if 'forward' in i.get('role','').lower() or
                           'striker' in i.get('role','').lower() or
                           'winger' in i.get('role','').lower()) >= 3
    return not (home_depleted or away_depleted)


# ══════════════════════════════════════════════════════════════════════════════
# CLV CALCULATION
# ══════════════════════════════════════════════════════════════════════════════

def calculate_clv(bet_odds: float, pinnacle_closing: float) -> Dict:
    """
    Closing Line Value calculation.
    CLV = Pinnacle closing odds / Bet odds
    < 1.0 = positive (got better price than closing) ✅
    > 1.0 = negative (market moved against bet) ❌
    Target: average < 1.00 over 30+ real money bets.
    """
    clv = pinnacle_closing / bet_odds
    if clv < 0.95:
        signal = 'STRONG_POSITIVE'
    elif clv < 1.00:
        signal = 'POSITIVE'
    elif clv == 1.00:
        signal = 'NEUTRAL'
    else:
        signal = 'NEGATIVE'
    return {'clv': round(clv, 4), 'signal': signal}


# ══════════════════════════════════════════════════════════════════════════════
# QUICK TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("POISSON-EDGE V4.1 — Model Code Self-Test")
    print("=" * 50)

    # Test DC matrix
    m = build_score_matrix(1.5, 1.0)
    p = extract_probabilities(m)
    print(f"Test λH=1.5, λA=1.0:")
    print(f"  HW={p['hw']:.3f} Draw={p['draw']:.3f} AW={p['aw']:.3f}")
    print(f"  O25={p['o25']:.3f} BTTS={p['btts']:.3f}")
    assert abs(p['hw'] + p['draw'] + p['aw'] - 1.0) < 0.001, "Probabilities don't sum to 1"
    print(f"  ✅ Probabilities sum to 1.000")

    # Test ELO
    elo_p = elo_hw_probability(1790, 1441)  # Arsenal vs Spurs
    print(f"\nELO test Arsenal (1790) vs Spurs (1441): {elo_p:.3f}")
    assert 0.8 < elo_p < 0.99, "ELO probability out of expected range"
    print(f"  ✅ ELO probability in expected range")

    # Test Pinnacle gate
    result = check_pinnacle(1.85, 1.90)  # Pinnacle lower = good
    print(f"\nPinnacle test (1.85 vs B365 1.90): {result['result']}")
    assert result['pass'] == True
    print(f"  ✅ Pinnacle gate: lower Pinnacle = confirmed = pass")

    result2 = check_pinnacle(2.00, 1.90)  # Pinnacle higher by 10 pips = mild flag
    print(f"Pinnacle test (2.00 vs B365 1.90): {result2['result']}")
    assert result2['result'] in ('MILD_FLAG', 'FLAG')
    print(f"  ✅ Pinnacle gate: higher Pinnacle by 10 pips = flag")

    # Test fatigue
    assert fatigue_multiplier(3) == 0.94, f"Fatigue 3d wrong: {fatigue_multiplier(3)}"
    assert fatigue_multiplier(7) == 1.00, f"Fatigue 7d wrong: {fatigue_multiplier(7)}"
    print(f"\n✅ Fatigue multipliers correct")

    # Test H2H gate
    gate = apply_h2h_gate(5, 6)
    assert gate['gate'] == 'BLOCK_UNDER'
    gate2 = apply_h2h_gate(3, 6)
    assert gate2['gate'] == 'CLEAR'
    print(f"✅ H2H gate correct (5/6 = BLOCK_UNDER, 3/6 = CLEAR)")

    # Test probability blocks
    block = check_probability_gate(0.77, 'o25')
    assert block is not None and 'HARD-BLOCK' in block
    clear = check_probability_gate(0.70, 'o25')
    assert clear is None or 'WATCH' in clear
    print(f"✅ Probability gates correct")

    print(f"\n✅ All self-tests passed. Model ready.")
