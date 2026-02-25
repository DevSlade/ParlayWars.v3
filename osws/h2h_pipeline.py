"""
OSWS — Data Pipeline
Orchestrates fetching, parsing, and storing eBasketball data from h2hggl.com.
Runs continuously (or on-demand) and populates the OSWS SQLite database.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from osws.h2h_client import fetch_players, fetch_live_matches, fetch_scheduled_matches
from osws.h2h_database import init_db, upsert_player, upsert_match, get_all_players

log = logging.getLogger(__name__)

# ── Embedded 166-player fallback seed (used if live fetch returns < 10 players) ──
_FALLBACK_CSV = """\
1,TAAPZ,73,62.3,3100,2200,847,W,W,W,W,W,L,W,W,W,L
2,LANES,66,63.6,4000,2600,1300,L,W,L,W,L,W,W,L,W,W
3,HOGGY,64,67,4900,3100,1700,W,W,L,W,L,L,L,W,W,W
4,VISIONARY,60,59.2,323,195,128,W,W,W,W,L,W,L,L,L,L
5,ALLFATHER,60,51,299,178,121,L,W,L,L,L,L,W,L,W,L
6,HYPER,59,55.3,945,558,387,W,W,W,W,W,W,W,W,W,L
7,CURSE,59,54.1,1200,754,525,W,W,W,W,W,L,L,W,W,W
8,CLAMPS,58,64.4,1400,836,593,L,L,L,W,L,L,W,W,W,L
9,RUTHLESS,57,60.4,1500,849,649,L,W,W,L,L,W,W,L,W,L
10,CRUCIAL,57,55.6,820,465,355,L,L,L,L,W,L,W,W,W,W
11,ENDEAVOR,57,52.8,648,368,280,L,L,W,L,L,L,W,L,L,L
12,SHELL,57,47,507,288,219,L,L,L,L,W,W,L,W,L,L
13,PRODIGY,56,55.5,1600,927,714,L,L,L,W,L,W,L,W,W,W
14,SHIVER,56,52,396,223,173,L,L,L,W,W,W,W,L,W,W
15,AM,55,60,3900,2100,1700,W,W,W,W,W,W,L,W,W,W
16,BULLSEYE,55,59.5,1900,1000,882,L,W,W,W,W,L,W,L,L,W
17,DEFIANT,55,56.3,462,252,210,L,L,W,L,L,W,L,W,L,L
18,BABYLON,55,55.6,846,468,378,W,L,W,W,W,L,W,W,L,L
19,GALAXY,55,53.5,1000,576,462,L,W,W,W,L,W,W,L,W,W
20,DEPUTY,55,47.6,289,158,131,W,W,W,W,W,W,W,L,W,W
21,JACKAL,54,57.9,2600,1400,1200,L,L,L,L,L,W,L,W,L,W
22,PACIFIER,54,53.8,720,387,333,L,L,L,L,W,W,W,W,W,W
23,SONIC,54,52.5,638,345,293,W,L,L,W,W,L,W,W,L,W
24,ANSWER,54,51.6,598,321,277,W,W,W,W,W,W,L,W,W,W
25,COMMANDER,54,49.9,642,348,294,W,W,L,W,W,W,W,W,W,L
26,COMBO,53,59.5,2500,1300,1200,L,W,L,W,L,L,W,L,L,W
27,DISCORD,53,55.6,714,377,336,L,L,L,L,L,L,L,L,L,L
28,DOC,53,54.9,862,455,407,L,L,L,L,L,L,L,L,W,L
29,LAW,53,54,765,409,356,L,L,W,W,W,W,L,W,W,W
30,OCEAN,53,53.4,1500,830,728,L,W,W,L,W,W,W,W,W,W
31,MEDUSA,53,49.9,272,145,127,L,L,W,W,L,L,L,L,W,W
32,ENCORE,52,60.3,1300,712,661,W,W,W,L,W,L,L,W,W,W
33,TD24,52,60,3400,1700,1600,L,W,L,L,W,L,L,L,W,L
34,EXO,52,58.7,3000,1500,1400,L,L,W,L,W,W,L,W,W,W
35,CALAMITY,52,57.9,1700,919,855,W,L,W,W,W,L,W,L,L,L
36,HORROR,52,57.5,1000,556,518,W,L,L,W,L,W,L,L,L,W
37,THUNDER,52,57.3,709,372,337,W,W,W,L,W,W,W,W,W,L
38,HOLLOW,52,57.1,3800,2000,1800,L,L,L,L,W,L,W,W,W,L
39,NIGHTHAWK,52,55.6,931,487,444,L,W,W,W,L,W,L,L,L,W
40,FENRIR,52,55,974,511,460,L,W,L,W,L,W,L,W,W,L
41,RAPTOR,52,53.8,1700,898,833,W,W,W,W,W,L,W,W,W,L
42,GODFATHER,52,53.6,2700,1400,1300,L,L,L,L,L,L,L,W,L,L
43,SHERIFF,52,52.5,1000,557,520,W,W,L,L,W,L,W,L,L,L
44,WOLVERINE,52,52.2,548,283,265,L,L,W,W,W,L,W,L,W,W
45,MARINE,51,64.5,1300,690,648,W,W,W,L,W,L,W,W,W,L
46,KOBRA,51,58.9,2100,1100,1000,L,L,W,W,W,L,L,W,L,L
47,CYPHER,51,57.9,2100,1000,1000,W,W,L,L,L,L,L,W,W,L
48,OMEN,51,54.5,743,382,359,L,W,L,W,W,W,W,W,L,W
49,BROOK,51,54.3,843,426,417,L,W,W,L,W,W,W,L,W,L
50,FLAME,51,54.1,235,120,115,L,L,W,L,L,L,W,W,L,L
51,GRAVITY,51,53.1,1200,649,628,L,W,L,W,L,W,W,W,L,W
52,HAWK,51,51.1,726,370,355,L,L,L,W,L,L,W,L,W,L
53,ANONYMOUS,51,51,364,187,177,W,W,W,L,L,L,L,L,L,L
54,ALIEN,51,50.8,489,247,242,W,W,L,L,L,W,W,L,W,W
55,DECOY,51,50.8,261,132,129,L,W,L,L,L,W,W,L,L,L
56,INSANITY,51,50.8,1000,542,522,W,W,L,W,L,L,W,W,L,L
57,FRENZY,51,50.4,430,218,212,L,L,W,L,L,W,L,W,W,L
58,MYTH,51,48.7,1900,991,959,L,W,W,W,L,W,L,L,W,W
59,STRIKE,51,44.5,546,280,266,W,W,L,W,L,W,W,W,L,W
60,CLUTCH,51,43.4,37,19,18,L,W,L,L,W,L,W,W,W,L
61,SURGEON,50,63.8,1900,1000,987,L,L,L,W,L,W,W,W,W,W
62,ARCHITECT,50,61.3,2800,1400,1400,W,L,W,L,L,W,W,L,W,L
63,KARMA,50,60.9,3700,1800,1800,L,L,L,L,W,L,W,L,L,L
64,JUGGERNAUT,50,58.7,1100,554,552,L,W,L,L,L,L,L,L,L,W
65,OUTLAW,50,58.1,3000,1500,1500,W,W,W,L,W,W,L,L,W,W
66,SILVER,50,58,1400,718,713,W,L,W,W,L,L,W,L,W,W
67,RAIN,50,57.5,1200,650,642,W,W,L,W,L,L,L,W,L,L
68,MALICE,50,57.3,1000,502,505,L,L,W,L,W,L,L,L,W,L
69,KNIGHT,50,57.1,2400,1200,1200,W,W,W,L,L,L,L,W,W,L
70,CHIEF,50,56.8,2400,1200,1100,W,L,W,L,L,W,W,L,L,L
71,AVATAR,50,56.3,1800,908,909,W,W,L,W,W,W,W,L,L,L
72,PROTOTYPE,50,53.3,1700,892,891,L,L,W,W,W,L,W,W,W,L
73,ULTIMATE,50,52.1,408,203,205,L,W,L,W,W,L,W,W,W,W
74,ARCHER,50,51.1,1900,975,974,L,W,L,L,L,L,L,W,L,W
75,PIRATE,50,49.4,625,311,314,W,L,W,L,W,W,W,L,L,W
76,RAMZ,49,66.3,3200,1500,1600,L,L,L,W,W,W,W,L,W,L
77,VEX,49,66.2,3100,1500,1600,L,W,L,W,W,L,W,W,L,W
78,OREZ,49,65.6,3900,1900,2000,W,L,L,L,W,L,W,L,L,L
79,LAZARUS,49,65.6,2200,1000,1100,L,W,W,W,L,W,W,L,L,L
80,CARNAGE,49,64.3,4200,2000,2100,L,W,L,L,W,L,L,W,L,L
81,MIST,49,63.5,3500,1700,1800,W,W,L,L,W,L,W,W,L,L
82,DIMES,49,63.1,4600,2200,2300,W,W,L,L,W,W,L,L,L,L
83,SKYFOX,49,62.9,1500,757,772,L,W,W,L,L,W,L,L,L,L
84,GRANDMASTER,49,62.4,3300,1600,1600,W,L,L,L,L,W,L,W,L,L
85,UNDERRATED,49,62.4,3400,1700,1700,W,L,W,L,W,W,W,L,L,W
86,SPARKZ,49,62.3,5200,2500,2600,L,L,L,L,W,L,W,W,W,L
87,FIVESTAR,49,60.4,2900,1400,1500,L,L,L,L,W,L,L,W,L,L
88,JD,49,60,1600,822,860,L,W,L,W,L,L,L,W,L,L
89,AIRFORCE,49,59.9,3600,1700,1800,W,W,L,W,L,W,W,W,W,W
90,SPECTER,49,59.5,3100,1500,1500,W,W,W,W,W,W,W,W,W,W
91,QUAZAR,49,59,1000,510,516,L,W,W,L,W,W,W,L,W,L
92,PRIMAL,49,55.4,1300,686,703,W,W,W,W,L,W,L,W,W,W
93,SUPERIOR,49,54.7,311,151,160,L,W,L,L,L,L,L,L,L,L
94,BLAZER,49,51.8,653,319,334,W,L,W,L,W,W,W,L,L,W
95,GENERAL,49,51.3,418,203,215,L,L,W,L,L,L,W,L,L,W
96,SIGNAL,49,50.9,1000,503,534,L,L,L,L,L,L,L,L,L,L
97,ADMIRAL,49,50.6,694,340,353,L,W,W,L,L,W,L,L,W,L
98,EQUALIZER,49,50.6,768,378,390,L,W,W,L,L,L,W,L,L,W
99,PULSE,49,49.8,508,247,261,L,L,W,L,W,W,L,L,W,L
100,INVINCIBLE,49,47.4,926,455,471,L,L,L,L,L,L,W,L,W,L
101,STING,49,46.5,1300,655,689,W,L,W,L,L,L,W,L,L,W
102,ATOMIC,48,63.2,661,317,342,L,L,L,W,W,L,W,L,W,W
103,PUMA,48,62.4,1100,528,557,W,L,W,W,L,L,L,W,L,L
104,HERMES,48,62,2700,1300,1400,L,W,W,W,W,L,W,L,L,L
105,SCORCH,48,59.6,4500,2200,2300,L,W,L,L,L,L,L,L,L,L
106,SPOOKY,48,58,3800,1800,2000,L,L,L,L,L,L,L,W,W,W
107,BRAZEN,48,54.2,2300,1100,1200,L,L,L,W,W,W,L,L,W,W
108,MACHINE,48,54,1200,586,627,W,L,W,W,W,L,L,L,W,W
109,DOMAIN,48,53.9,1500,731,779,L,L,W,L,W,W,L,W,L,L
110,RIDER,48,52.8,1500,744,813,L,W,L,L,L,L,L,W,L,L
111,BLADE,48,52.6,1300,628,682,W,W,L,W,W,W,W,L,W,W
112,SABRE,48,52,1000,490,523,W,L,W,W,W,L,L,W,W,W
113,UNBREAKABLE,48,50.7,900,435,465,L,W,W,L,W,L,L,L,W,L
114,PROWLER,48,50.7,124,60,64,L,L,W,L,L,L,L,L,L,L
115,THOR,48,50.5,253,121,132,W,W,W,W,W,L,W,L,W,L
116,FURY,48,49.5,578,278,299,W,L,W,L,L,W,L,L,L,L
117,INFINITE,48,49.5,562,269,293,L,L,L,L,L,W,W,W,L,L
118,MARKSMAN,48,48.6,174,83,91,L,L,W,W,L,L,W,L,W,L
119,KJMR,47,66.5,4700,2200,2400,W,L,W,W,W,L,L,L,L,W
120,SAINT JR,47,58.8,4800,2200,2500,L,L,W,L,W,W,L,L,L,L
121,ENIGMA,47,58.1,394,184,208,L,W,W,L,W,L,L,L,W,L
122,HARLEM,47,56.1,1900,912,1000,L,L,L,L,L,W,W,L,L,L
123,ARACHNE,47,54.8,1800,883,1000,W,L,W,L,L,L,L,L,W,L
124,UNFORGIVEN,47,53,816,387,429,W,W,W,L,L,L,W,L,L,W
125,ORDER,47,51.6,309,144,165,W,L,W,W,L,L,W,W,W,W
126,DAGGER,47,51.5,1000,474,530,W,L,W,W,W,L,W,W,W,L
127,GODLIKE,47,51,1300,619,698,L,W,L,L,L,W,W,W,L,L
128,TERMINATOR,47,50.8,565,266,299,W,W,L,W,L,L,L,W,L,L
129,REND,47,46.1,502,234,268,W,L,L,W,L,L,L,L,L,L
130,HUNCHO,46,57.6,2700,1200,1400,L,L,L,L,L,W,L,L,L,W
131,PATIENCE,46,57.2,1200,557,658,W,W,W,L,L,W,W,W,W,L
132,JOLLY,46,51.7,512,234,272,L,L,L,L,L,W,W,L,L,W
133,ESSENCE,46,50.9,1000,472,553,L,L,L,L,L,L,L,L,W,W
134,TRANQUILITY,46,50.1,1100,520,604,L,L,L,L,L,L,W,W,L,L
135,TITANIUM,46,49.4,854,389,465,W,W,L,L,L,L,W,W,W,L
136,BLIZZARD,46,45.5,666,307,358,L,L,L,L,W,W,L,W,W,W
137,RASCAL,45,67.6,1200,551,658,W,L,L,W,L,L,L,W,W,W
138,THA KID,45,64.9,4300,1900,2300,W,L,L,W,L,L,W,W,L,W
139,CASCADE,45,57.9,739,333,402,W,L,L,L,L,W,L,W,W,L
140,TRICKSTER,45,52.7,1100,509,613,W,W,L,W,W,W,W,W,L,L
141,PHARAOH,45,51.9,693,313,380,W,W,L,W,L,L,L,W,W,W
142,BOMBARDIER,45,50.5,745,333,411,L,W,W,W,W,L,W,L,L,L
143,CLAW,45,49.5,957,435,522,L,L,L,L,W,W,L,L,L,W
144,KOBOLD,44,60.5,1700,785,976,L,W,L,L,W,L,L,W,L,W
145,ANUBIS,44,52.4,203,90,113,W,W,L,W,W,W,W,L,W,W
146,MASTER,44,50.3,310,137,173,L,L,W,L,L,L,W,L,W,L
147,ANDROID,44,50.1,260,114,145,W,L,W,L,L,L,L,L,W,W
148,EL IDOLO,43,59.9,232,100,129,W,W,L,W,W,L,W,L,W,L
149,DOUBLEFOUR,43,59.1,3000,1300,1700,L,L,L,W,L,W,L,W,W,L
150,LEGACY,43,48.5,744,322,422,W,L,W,W,L,W,L,W,L,W
151,AZURE,43,48,308,133,175,L,L,W,W,W,W,W,L,L,L
152,CHARM,42,51.4,882,372,510,W,L,W,W,L,W,W,W,W,W
153,TRINITY,42,50.4,561,236,325,L,W,L,L,L,W,L,L,W,L
154,PUNISHER,42,48.5,747,311,435,L,L,L,L,L,L,L,L,L,W
155,SCOUT,42,44.8,12,5,7,L,W,W,L,L,W,L,W,L,W
156,ABYSS,41,53.1,1600,668,960,L,W,W,L,L,L,L,W,W,W
157,BLOODHOUND,40,47.8,410,164,246,L,W,L,W,L,W,L,W,L,L
158,VANDAL,40,47.4,676,270,406,L,L,W,L,W,W,L,L,L,W
159,GUARD,36,46,376,135,241,W,L,W,W,L,W,W,L,W,W
160,ANOMALY,35,49.1,94,33,60,L,W,W,W,L,W,L,W,W,L
161,GIANT,33,45.1,193,63,130,W,L,W,W,W,W,W,L,L,L
162,UTOPIA,33,41.9,83,27,56,L,L,W,W,L,L,L,L,W,L
163,QUEEN,31,46.6,349,107,242,L,W,L,L,W,L,L,L,L,L
164,PRINCE,27,53,135,37,96,L,L,L,L,L,L,L,W,L,W
165,IMMORTAL,27,50.4,172,46,126,L,L,W,W,L,L,L,L,W,L
166,VELOCITY,19,43.4,70,13,57,L,L,L,L,W,L,L,W,L,L
"""


def _parse_fallback_csv() -> List[Dict[str, Any]]:
    """Parse the embedded fallback CSV into a list of player dicts."""
    players = []
    for line in _FALLBACK_CSV.strip().splitlines():
        parts = line.split(",")
        if len(parts) < 7:
            continue
        try:
            rank = int(parts[0])
            name = parts[1].strip()
            win_pct = float(parts[2])
            recent_win_pct = float(parts[3])
            total_games = int(parts[4])
            wins = int(parts[5])
            losses = int(parts[6])
            form = [p.strip() for p in parts[7:17] if p.strip() in ("W", "L")]
            players.append({
                "name": name,
                "rank": rank,
                "win_pct": win_pct,
                "recent_win_pct": recent_win_pct,
                "total_games": total_games,
                "wins": wins,
                "losses": losses,
                "form": form,
            })
        except Exception:
            continue
    return players


def _parse_api_player(raw: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
    """Normalise a HudStats API player dict for OSWS storage."""
    name = str(
        raw.get("nickname") or raw.get("name") or raw.get("username") or "UNKNOWN"
    ).strip().upper()
    total = int(raw.get("games") or raw.get("total_games") or raw.get("matchesPlayed") or 0)
    wins = int(raw.get("wins") or raw.get("winCount") or 0)
    losses = max(0, total - wins)
    raw_wr = raw.get("win_rate") or raw.get("winRate") or raw.get("win_pct")
    if raw_wr is not None:
        win_pct = float(raw_wr)
        if win_pct <= 1.0:
            win_pct *= 100.0
    else:
        win_pct = round(wins / total * 100.0, 1) if total > 0 else 50.0
    raw_rwr = raw.get("recent_win_rate") or raw.get("recentWinRate") or raw.get("last10_win_pct")
    if raw_rwr is not None:
        recent_win_pct = float(raw_rwr)
        if recent_win_pct <= 1.0:
            recent_win_pct *= 100.0
    else:
        recent_win_pct = win_pct
    rank = int(raw.get("rank") or raw.get("position") or (idx + 1))
    form_raw = raw.get("form") or raw.get("lastResults") or raw.get("last_results") or []
    form = []
    for r in form_raw[:10]:
        if isinstance(r, str):
            form.append("W" if r.upper() in ("W", "WIN", "1") else "L")
        elif isinstance(r, (int, float)):
            form.append("W" if int(r) == 1 else "L")
    return {
        "name": name,
        "rank": rank,
        "win_pct": round(win_pct, 1),
        "recent_win_pct": round(recent_win_pct, 1),
        "total_games": total,
        "wins": wins,
        "losses": losses,
        "form": form,
    }


def run_pipeline(force: bool = False) -> int:
    """
    Main pipeline: fetch players from HudStats API, store in OSWS DB.
    Falls back to embedded CSV if API returns < 10 players.

    Returns: number of players stored.
    """
    init_db()

    from osws.h2h_database import get_all_players as db_players
    existing = db_players()
    if not force and len(existing) >= 10:
        log.info("OSWS DB already has %d players — skipping fetch.", len(existing))
        return len(existing)

    log.info("OSWS: fetching players from HudStats API...")
    raw_players = fetch_players()
    log.info("OSWS: received %d raw player records.", len(raw_players))

    if len(raw_players) >= 10:
        players = [_parse_api_player(r, i) for i, r in enumerate(raw_players)]
    else:
        log.warning("OSWS: API returned < 10 players — using fallback CSV seed.")
        players = _parse_fallback_csv()

    for p in players:
        try:
            upsert_player(p)
        except Exception as exc:
            log.warning("OSWS: failed to store player %s: %s", p.get("name"), exc)

    # Also fetch match data (best-effort)
    log.info("OSWS: fetching live matches...")
    live = fetch_live_matches()
    for m in live:
        try:
            upsert_match({
                "api_match_id": str(m.get("id") or m.get("match_id") or ""),
                "player_a": str(m.get("players", [{}])[0].get("nickname") or "P1").upper()
                    if m.get("players") else "P1",
                "player_b": str(m.get("players", [{}])[1].get("nickname") or "P2").upper()
                    if len(m.get("players") or []) > 1 else "P2",
                "status": "live",
                "match_date": m.get("start_time") or m.get("date"),
            })
        except Exception:
            pass

    log.info("OSWS: fetching scheduled matches...")
    scheduled = fetch_scheduled_matches()
    for m in scheduled:
        try:
            upsert_match({
                "api_match_id": str(m.get("id") or m.get("match_id") or ""),
                "player_a": str(m.get("players", [{}])[0].get("nickname") or "P1").upper()
                    if m.get("players") else "P1",
                "player_b": str(m.get("players", [{}])[1].get("nickname") or "P2").upper()
                    if len(m.get("players") or []) > 1 else "P2",
                "status": "scheduled",
                "match_date": m.get("start_time") or m.get("scheduled_at") or m.get("date"),
            })
        except Exception:
            pass

    from osws.h2h_database import get_all_players as db_players2
    final_count = len(db_players2())
    log.info("OSWS pipeline complete. Players in DB: %d", final_count)
    return final_count
