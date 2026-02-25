"""
ParlayWars v3 — Database Bootstrap (Live API + CSV Fallback)
Date: 2026-02-25

Fetches ALL player data live from the HudStats API and populates the
SQLite database.  If the API returns fewer than 10 players, falls back
to the embedded 166-player CSV seed data.

Usage:
    python scripts/seed_database.py              # Bootstrap / refresh from API
    python scripts/seed_database.py --force      # Force re-upsert even if DB is populated
    python scripts/seed_database.py --csv-only   # Seed from embedded CSV only (skip API)
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import init_db_sync, upsert_player_sync
from core.logger import setup_logging, get_logger
from engines.elo import DEFAULT_ELO
from engines.ratings import compute_pwr

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Embedded 166-player seed data
# Columns: rank, name, win_pct, recent_win_pct, total_games, wins, losses,
#          form_1..form_10  (W or L, most-recent first)
# ---------------------------------------------------------------------------
_SEED_CSV = """\
1,TAAPZ,73,62.3,3.1k,2.2k,847,W,W,W,W,W,L,W,W,W,L
2,LANES,66,63.6,4K,2.6k,1.3k,L,W,L,W,L,W,W,L,W,W
3,HOGGY,64,67,4.9k,3.1k,1.7k,W,W,L,W,L,L,L,W,W,W
4,VISIONARY,60,59.2,323,195,128,W,W,W,W,L,W,L,L,L,L
5,ALLFATHER,60,51,299,178,121,L,W,L,L,L,L,W,L,W,L
6,HYPER,59,55.3,945,558,387,W,W,W,W,W,W,W,W,W,L
7,CURSE,59,54.1,1.2k,754,525,W,W,W,W,W,L,L,W,W,W
8,CLAMPS,58,64.4,1.4k,836,593,L,L,L,W,L,L,W,W,W,L
9,RUTHLESS,57,60.4,1.5k,849,649,L,W,W,L,L,W,W,L,W,L
10,CRUCIAL,57,55.6,820,465,355,L,L,L,L,W,L,W,W,W,W
11,ENDEAVOR,57,52.8,648,368,280,L,L,W,L,L,L,W,L,L,L
12,SHELL,57,47,507,288,219,L,L,L,L,W,W,L,W,L,L
13,PRODIGY,56,55.5,1.6k,927,714,L,L,L,W,L,W,L,W,W,W
14,SHIVER,56,52,396,223,173,L,L,L,W,W,W,W,L,W,W
15,AM,55,60,3.9k,2.1k,1.7k,W,W,W,W,W,W,L,W,W,W
16,BULLSEYE,55,59.5,1.9k,1K,882,L,W,W,W,W,L,W,L,L,W
17,DEFIANT,55,56.3,462,252,210,L,L,W,L,L,W,L,W,L,L
18,BABYLON,55,55.6,846,468,378,W,L,W,W,W,L,W,W,L,L
19,GALAXY,55,53.5,1K,576,462,L,W,W,W,L,W,W,L,W,W
20,DEPUTY,55,47.6,289,158,131,W,W,W,W,W,W,W,L,W,W
21,JACKAL,54,57.9,2.6k,1.4k,1.2k,L,L,L,L,L,W,L,W,L,W
22,PACIFIER,54,53.8,720,387,333,L,L,L,L,W,W,W,W,W,W
23,SONIC,54,52.5,638,345,293,W,L,L,W,W,L,W,W,L,W
24,ANSWER,54,51.6,598,321,277,W,W,W,W,W,W,L,W,W,W
25,COMMANDER,54,49.9,642,348,294,W,W,L,W,W,W,W,W,W,L
26,COMBO,53,59.5,2.5k,1.3k,1.2k,L,W,L,W,L,L,W,L,L,W
27,DISCORD,53,55.6,714,377,336,L,L,L,L,L,L,L,L,L,L
28,DOC,53,54.9,862,455,407,L,L,L,L,L,L,L,L,W,L
29,LAW,53,54,765,409,356,L,L,W,W,W,W,L,W,W,W
30,OCEAN,53,53.4,1.5k,830,728,L,W,W,L,W,W,W,W,W,W
31,MEDUSA,53,49.9,272,145,127,L,L,W,W,L,L,L,L,W,W
32,ENCORE,52,60.3,1.3k,712,661,W,W,W,L,W,L,L,W,W,W
33,TD24,52,60,3.4k,1.7k,1.6k,L,W,L,L,W,L,L,L,W,L
34,EXO,52,58.7,3K,1.5k,1.4k,L,L,W,L,W,W,L,W,W,W
35,CALAMITY,52,57.9,1.7k,919,855,W,L,W,W,W,L,W,L,L,L
36,HORROR,52,57.5,1K,556,518,W,L,L,W,L,W,L,L,L,W
37,THUNDER,52,57.3,709,372,337,W,W,W,L,W,W,W,W,W,L
38,HOLLOW,52,57.1,3.8k,2K,1.8k,L,L,L,L,W,L,W,W,W,L
39,NIGHTHAWK,52,55.6,931,487,444,L,W,W,W,L,W,L,L,L,W
40,FENRIR,52,55,974,511,460,L,W,L,W,L,W,L,W,W,L
41,RAPTOR,52,53.8,1.7k,898,833,W,W,W,W,W,L,W,W,W,L
42,GODFATHER,52,53.6,2.7k,1.4k,1.3k,L,L,L,L,L,L,L,W,L,L
43,SHERIFF,52,52.5,1K,557,520,W,W,L,L,W,L,W,L,L,L
44,WOLVERINE,52,52.2,548,283,265,L,L,W,W,W,L,W,L,W,W
45,MARINE,51,64.5,1.3k,690,648,W,W,W,L,W,L,W,W,W,L
46,KOBRA,51,58.9,2.1k,1.1k,1K,L,L,W,W,W,L,L,W,L,L
47,CYPHER,51,57.9,2.1k,1K,1K,W,W,L,L,L,L,L,W,W,L
48,OMEN,51,54.5,743,382,359,L,W,L,W,W,W,W,W,L,W
49,BROOK,51,54.3,843,426,417,L,W,W,L,W,W,W,L,W,L
50,FLAME,51,54.1,235,120,115,L,L,W,L,L,L,W,W,L,L
51,GRAVITY,51,53.1,1.2k,649,628,L,W,L,W,L,W,W,W,L,W
52,HAWK,51,51.1,726,370,355,L,L,L,W,L,L,W,L,W,L
53,ANONYMOUS,51,51,364,187,177,W,W,W,L,L,L,L,L,L,L
54,ALIEN,51,50.8,489,247,242,W,W,L,L,L,W,W,L,W,W
55,DECOY,51,50.8,261,132,129,L,W,L,L,L,W,W,L,L,L
56,INSANITY,51,50.8,1K,542,522,W,W,L,W,L,L,W,W,L,L
57,FRENZY,51,50.4,430,218,212,L,L,W,L,L,W,L,W,W,L
58,MYTH,51,48.7,1.9k,991,959,L,W,W,W,L,W,L,L,W,W
59,STRIKE,51,44.5,546,280,266,W,W,L,W,L,W,W,W,L,W
60,CLUTCH,51,43.4,37,19,18,L,W,L,L,W,L,W,W,W,L
61,SURGEON,50,63.8,1.9k,1K,987,L,L,L,W,L,W,W,W,W,W
62,ARCHITECT,50,61.3,2.8k,1.4k,1.4k,W,L,W,L,L,W,W,L,W,L
63,KARMA,50,60.9,3.7k,1.8k,1.8k,L,L,L,L,W,L,W,L,L,L
64,JUGGERNAUT,50,58.7,1.1k,554,552,L,W,L,L,L,L,L,L,L,W
65,OUTLAW,50,58.1,3K,1.5k,1.5k,W,W,W,L,W,W,L,L,W,W
66,SILVER,50,58,1.4k,718,713,W,L,W,W,L,L,W,L,W,W
67,RAIN,50,57.5,1.2k,650,642,W,W,L,W,L,L,L,W,L,L
68,MALICE,50,57.3,1K,502,505,L,L,W,L,W,L,L,L,W,L
69,KNIGHT,50,57.1,2.4k,1.2k,1.2k,W,W,W,L,L,L,L,W,W,L
70,CHIEF,50,56.8,2.4k,1.2k,1.1k,W,L,W,L,L,W,W,L,L,L
71,AVATAR,50,56.3,1.8k,908,909,W,W,L,W,W,W,W,L,L,L
72,PROTOTYPE,50,53.3,1.7k,892,891,L,L,W,W,W,L,W,W,W,L
73,ULTIMATE,50,52.1,408,203,205,L,W,L,W,W,L,W,W,W,W
74,ARCHER,50,51.1,1.9k,975,974,L,W,L,L,L,L,L,W,L,W
75,PIRATE,50,49.4,625,311,314,W,L,W,L,W,W,W,L,L,W
76,RAMZ,49,66.3,3.2k,1.5k,1.6k,L,L,L,W,W,W,W,L,W,L
77,VEX,49,66.2,3.1k,1.5k,1.6k,L,W,L,W,W,L,W,W,L,W
78,OREZ,49,65.6,3.9k,1.9k,2K,W,L,L,L,W,L,W,L,L,L
79,LAZARUS,49,65.6,2.2k,1K,1.1k,L,W,W,W,L,W,W,L,L,L
80,CARNAGE,49,64.3,4.2k,2K,2.1k,L,W,L,L,W,L,L,W,L,L
81,MIST,49,63.5,3.5k,1.7k,1.8k,W,W,L,L,W,L,W,W,L,L
82,DIMES,49,63.1,4.6k,2.2k,2.3k,W,W,L,L,W,W,L,L,L,L
83,SKYFOX,49,62.9,1.5k,757,772,L,W,W,L,L,W,L,L,L,L
84,GRANDMASTER,49,62.4,3.3k,1.6k,1.6k,W,L,L,L,L,W,L,W,L,L
85,UNDERRATED,49,62.4,3.4k,1.7k,1.7k,W,L,W,L,W,W,W,L,L,W
86,SPARKZ,49,62.3,5.2k,2.5k,2.6k,L,L,L,L,W,L,W,W,W,L
87,FIVESTAR,49,60.4,2.9k,1.4k,1.5k,L,L,L,L,W,L,L,W,L,L
88,JD,49,60,1.6k,822,860,L,W,L,W,L,L,L,W,L,L
89,AIRFORCE,49,59.9,3.6k,1.7k,1.8k,W,W,L,W,L,W,W,W,W,W
90,SPECTER,49,59.5,3.1k,1.5k,1.5k,W,W,W,W,W,W,W,W,W,W
91,QUAZAR,49,59,1K,510,516,L,W,W,L,W,W,W,L,W,L
92,PRIMAL,49,55.4,1.3k,686,703,W,W,W,W,L,W,L,W,W,W
93,SUPERIOR,49,54.7,311,151,160,L,W,L,L,L,L,L,L,L,L
94,BLAZER,49,51.8,653,319,334,W,L,W,L,W,W,W,L,L,W
95,GENERAL,49,51.3,418,203,215,L,L,W,L,L,L,W,L,L,W
96,SIGNAL,49,50.9,1K,503,534,L,L,L,L,L,L,L,L,L,L
97,ADMIRAL,49,50.6,694,340,353,L,W,W,L,L,W,L,L,W,L
98,EQUALIZER,49,50.6,768,378,390,L,W,W,L,L,L,W,L,L,W
99,PULSE,49,49.8,508,247,261,L,L,W,L,W,W,L,L,W,L
100,INVINCIBLE,49,47.4,926,455,471,L,L,L,L,L,L,W,L,W,L
101,STING,49,46.5,1.3k,655,689,W,L,W,L,L,L,W,L,L,W
102,ATOMIC,48,63.2,661,317,342,L,L,L,W,W,L,W,L,W,W
103,PUMA,48,62.4,1.1k,528,557,W,L,W,W,L,L,L,W,L,L
104,HERMES,48,62,2.7k,1.3k,1.4k,L,W,W,W,W,L,W,L,L,L
105,SCORCH,48,59.6,4.5k,2.2k,2.3k,L,W,L,L,L,L,L,L,L,L
106,SPOOKY,48,58,3.8k,1.8k,2K,L,L,L,L,L,L,L,W,W,W
107,BRAZEN,48,54.2,2.3k,1.1k,1.2k,L,L,L,W,W,W,L,L,W,W
108,MACHINE,48,54,1.2k,586,627,W,L,W,W,W,L,L,L,W,W
109,DOMAIN,48,53.9,1.5k,731,779,L,L,W,L,W,W,L,W,L,L
110,RIDER,48,52.8,1.5k,744,813,L,W,L,L,L,L,L,W,L,L
111,BLADE,48,52.6,1.3k,628,682,W,W,L,W,W,W,W,L,W,W
112,SABRE,48,52,1K,490,523,W,L,W,W,W,L,L,W,W,W
113,UNBREAKABLE,48,50.7,900,435,465,L,W,W,L,W,L,L,L,W,L
114,PROWLER,48,50.7,124,60,64,L,L,W,L,L,L,L,L,L,L
115,THOR,48,50.5,253,121,132,W,W,W,W,W,L,W,L,W,L
116,FURY,48,49.5,578,278,299,W,L,W,L,L,W,L,L,L,L
117,INFINITE,48,49.5,562,269,293,L,L,L,L,L,W,W,W,L,L
118,MARKSMAN,48,48.6,174,83,91,L,L,W,W,L,L,W,L,W,L
119,KJMR,47,66.5,4.7k,2.2k,2.4k,W,L,W,W,W,L,L,L,L,W
120,SAINT JR,47,58.8,4.8k,2.2k,2.5k,L,L,W,L,W,W,L,L,L,L
121,ENIGMA,47,58.1,394,184,208,L,W,W,L,W,L,L,L,W,L
122,HARLEM,47,56.1,1.9k,912,1K,L,L,L,L,L,W,W,L,L,L
123,ARACHNE,47,54.8,1.8k,883,1K,W,L,W,L,L,L,L,L,W,L
124,UNFORGIVEN,47,53,816,387,429,W,W,W,L,L,L,W,L,L,W
125,ORDER,47,51.6,309,144,165,W,L,W,W,L,L,W,W,W,W
126,DAGGER,47,51.5,1K,474,530,W,L,W,W,W,L,W,W,W,L
127,GODLIKE,47,51,1.3k,619,698,L,W,L,L,L,W,W,W,L,L
128,TERMINATOR,47,50.8,565,266,299,W,W,L,W,L,L,L,W,L,L
129,REND,47,46.1,502,234,268,W,L,L,W,L,L,L,L,L,L
130,HUNCHO,46,57.6,2.7k,1.2k,1.4k,L,L,L,L,L,W,L,L,L,W
131,PATIENCE,46,57.2,1.2k,557,658,W,W,W,L,L,W,W,W,W,L
132,JOLLY,46,51.7,512,234,272,L,L,L,L,L,W,W,L,L,W
133,ESSENCE,46,50.9,1K,472,553,L,L,L,L,L,L,L,L,W,W
134,TRANQUILITY,46,50.1,1.1k,520,604,L,L,L,L,L,L,W,W,L,L
135,TITANIUM,46,49.4,854,389,465,W,W,L,L,L,L,W,W,W,L
136,BLIZZARD,46,45.5,666,307,358,L,L,L,L,W,W,L,W,W,W
137,RASCAL,45,67.6,1.2k,551,658,W,L,L,W,L,L,L,W,W,W
138,THA KID,45,64.9,4.3k,1.9k,2.3k,W,L,L,W,L,L,W,W,L,W
139,CASCADE,45,57.9,739,333,402,W,L,L,L,L,W,L,W,W,L
140,TRICKSTER,45,52.7,1.1k,509,613,W,W,L,W,W,W,W,W,L,L
141,PHARAOH,45,51.9,693,313,380,W,W,L,W,L,L,L,W,W,W
142,BOMBARDIER,45,50.5,745,333,411,L,W,W,W,W,L,W,L,L,L
143,CLAW,45,49.5,957,435,522,L,L,L,L,W,W,L,L,L,W
144,KOBOLD,44,60.5,1.7k,785,976,L,W,L,L,W,L,L,W,L,W
145,ANUBIS,44,52.4,203,90,113,W,W,L,W,W,W,W,L,W,W
146,MASTER,44,50.3,310,137,173,L,L,W,L,L,L,W,L,W,L
147,ANDROID,44,50.1,260,114,145,W,L,W,L,L,L,L,L,W,W
148,EL IDOLO,43,59.9,232,100,129,W,W,L,W,W,L,W,L,W,L
149,DOUBLEFOUR,43,59.1,3K,1.3k,1.7k,L,L,L,W,L,W,L,W,W,L
150,LEGACY,43,48.5,744,322,422,W,L,W,W,L,W,L,W,L,W
151,AZURE,43,48,308,133,175,L,L,W,W,W,W,W,L,L,L
152,CHARM,42,51.4,882,372,510,W,L,W,W,L,W,W,W,W,W
153,TRINITY,42,50.4,561,236,325,L,W,L,L,L,W,L,L,W,L
154,PUNISHER,42,48.5,747,311,435,L,L,L,L,L,L,L,L,L,W
155,SCOUT,42,44.8,12,5,7,L,W,W,L,L,W,L,W,L,W
156,ABYSS,41,53.1,1.6k,668,960,L,W,W,L,L,L,L,W,W,W
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


def _parse_k_value(raw: str) -> int:
    """
    Parse a value that may use "k"/"K" suffix notation.

    Examples:
        "3.1k" → 3100
        "4K"   → 4000
        "1K"   → 1000
        "323"  → 323
    """
    raw = raw.strip()
    if raw.lower().endswith("k"):
        return int(round(float(raw[:-1]) * 1000))
    return int(raw)


def bootstrap_from_csv() -> list:
    """
    Parse the embedded 166-player CSV and return a list of player dicts
    ready for upsert into the database.
    """
    players = []
    for line in _SEED_CSV.strip().splitlines():
        parts = line.split(",")
        if len(parts) < 7:
            continue
        rank = int(parts[0])
        name = parts[1].strip()
        win_pct = float(parts[2])
        recent_win_pct = float(parts[3])
        total_games = _parse_k_value(parts[4])
        wins = _parse_k_value(parts[5])
        losses = _parse_k_value(parts[6])
        form = [p.strip() for p in parts[7:17] if p.strip() in ("W", "L")]

        player = {
            "rank": rank,
            "name": name,
            "win_pct": win_pct,
            "recent_win_pct": recent_win_pct,
            "total_games": total_games,
            "wins": wins,
            "losses": losses,
            "form": form,
        }
        player["elo"] = _elo_from_win_pct(win_pct, rank)
        player["pwr_rating"] = compute_pwr(player)
        players.append(player)
    return players


def _elo_from_win_pct(win_pct: float, rank: int) -> float:
    """
    Estimate a starting ELO from overall win percentage and rank.
    Range: ~1100 (≤19% WR) to ~2000 (≥73% WR).
    """
    elo = DEFAULT_ELO + (win_pct - 50.0) * 10.0
    # Small rank bonus for proven top players
    if rank <= 10:
        elo += 50.0
    elif rank <= 25:
        elo += 25.0
    return round(max(1100.0, min(2000.0, elo)), 1)


async def _fetch_players() -> list:
    """Fetch all players from the HudStats API and return parsed player dicts."""
    from sports.ebasketball.api_hudstats import HudStatsClient

    client = HudStatsClient()
    try:
        players = await client.get_all_players()
    finally:
        await client.close()
    return players


def bootstrap_from_api(force: bool = False) -> int:
    """
    Bootstrap the player database from the live HudStats API, with automatic
    fallback to the embedded 166-player CSV seed if the API returns < 10 players.

    Steps:
      1. Call ``GET /participant/nba`` via HudStatsClient
      2. Parse the response with ``parse_hudstats_response``
      3. Compute starting ELO and PWR ratings
      4. Upsert all players into SQLite
      5. If API returned < 10 players, fall back to embedded CSV seed data

    Args:
        force: If True, upsert all players even if the database is already
               populated (useful for a full refresh).

    Returns:
        Number of players written to the database.
    """
    setup_logging()
    init_db_sync()

    from core.database import get_all_players_sync

    if not force:
        existing = get_all_players_sync()
        if len(existing) >= 10:
            log.info(
                "Database already has %d players — skipping bootstrap "
                "(use --force to refresh).",
                len(existing),
            )
            return len(existing)

    log.info("Fetching players from HudStats API...")
    try:
        players = asyncio.run(_fetch_players())
    except Exception as exc:
        log.warning("HudStats API fetch failed: %s — falling back to CSV seed.", exc)
        players = []

    if len(players) >= 10:
        log.info("Received %d players from API. Computing ELO + PWR...", len(players))
        for i, player in enumerate(players):
            # If the API didn't supply a rank, use list position
            if not player.get("rank") or player["rank"] == 999:
                player["rank"] = i + 1

            player["elo"] = _elo_from_win_pct(
                float(player.get("win_pct") or 50.0),
                int(player.get("rank") or 83),
            )
            player["pwr_rating"] = compute_pwr(player)
            upsert_player_sync(player)

        log.info("Bootstrapped %d players from HudStats API.", len(players))
        return len(players)

    # API unavailable or returned insufficient data — use embedded CSV seed
    log.warning(
        "HudStats API returned %d players (< 10). Falling back to embedded CSV seed.",
        len(players),
    )
    return _seed_from_csv()


def _seed_from_csv() -> int:
    """Seed the database from the embedded 166-player CSV constant."""
    players = bootstrap_from_csv()
    for player in players:
        upsert_player_sync(player)
    log.info("Seeded %d players from embedded CSV.", len(players))
    return len(players)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Bootstrap player DB from HudStats API (CSV fallback if API unavailable)"
    )
    ap.add_argument("--force", action="store_true", help="Re-upsert even if DB is populated")
    ap.add_argument("--csv-only", action="store_true", help="Seed from embedded CSV only (skip API)")
    args = ap.parse_args()

    if args.csv_only:
        setup_logging()
        init_db_sync()
        count = _seed_from_csv()
        print(f"✅ Seeded {count} players from embedded CSV.")
    else:
        count = bootstrap_from_api(force=args.force)
        print(f"✅ Bootstrapped {count} players.")
