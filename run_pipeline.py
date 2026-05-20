"""
Bounty Hunter — Main Pipeline Runner
100% free. No Spotify. No paid APIs.

Data flow:
  1. COLLECT   — Billboard Year-End 2024+2025 + Weekly + YouTube Trending
  2. RESOLVE   — ISRC via MusicBrainz → Deezer fallback (free)
  3. ENRICH    — Chartmetric popularity filter (>60 = real cash)
  4. SCORE     — Sniper score: indie label / remix / recent / tier-2 artist
  5. PROBE     — Stealth SoundExchange async scraper (Playwright + proxy)
  6. OUTREACH  — Hunter.io finds buyer email for every UNCLAIMED/CONFLICT lead

Batch sizes:
  --batch 50   Start mode  (default — start here)
  --batch 100  Daily full mode

Usage:
  python run_pipeline.py                    # full run, 50 targets
  python run_pipeline.py --batch 100        # full run, 100 targets
  python run_pipeline.py --stage collect    # collect only
  python run_pipeline.py --stage probe      # probe only
  python run_pipeline.py --stage outreach   # find buyer emails for existing leads
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime

from collectors.billboard_collector import pull_all
from collectors.youtube_trending import pull_youtube_trending
from collectors.remix_collector import pull_remix_leads
from collectors.tier2_collector import pull_tier2_leads
from collectors.youtube_remix_collector import pull_youtube_remix_leads
from collectors.atlanta_collector import pull_atlanta_leads
from collectors.isrc_resolver import resolve_batch
from collectors.batch_re_resolve import re_resolve
from collectors.chartmetric_scorer import score_with_chartmetric
from collectors.sniper_filters import filter_top_targets
from probe.sx_scraper import run_probe
from outreach.email_finder import find_buyers_for_leads

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MASTER_CSV = os.path.join(DATA_DIR, "master_targets.csv")
LEADS_CSV = os.path.join(DATA_DIR, "leads.csv")


def load_csv(path: str) -> list:
    return pd.read_csv(path).to_dict("records")


def save_csv(records: list, path: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    pd.DataFrame(records).to_csv(path, index=False)
    print(f"[SAVE] {len(records)} records → {path}")


# ── Stages ────────────────────────────────────────────────────────────────────

def stage_collect(weekly_limit: int) -> list:
    print("\n=== STAGE 1: COLLECT ===")
    print("  Sources: Billboard (multi-chart 2022-2025), YouTube Trending, Remix Leads")

    billboard    = pull_all(weekly_limit=weekly_limit)
    youtube      = pull_youtube_trending(limit=50)
    remixes      = pull_remix_leads()
    tier2        = pull_tier2_leads()
    yt_remixes   = pull_youtube_remix_leads()

    combined = billboard + youtube + remixes + tier2 + yt_remixes

    # Deduplicate
    seen = set()
    deduped = []
    for t in combined:
        key = f"{t['artist'].lower()}|{t['track'].lower()}"
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    print(f"[COLLECT] {len(deduped)} unique tracks (Billboard + YouTube)")
    save_csv(deduped, os.path.join(DATA_DIR, "raw_collected.csv"))
    return deduped


def stage_resolve(tracks: list) -> list:
    print("\n=== STAGE 2: RESOLVE ISRCs (MusicBrainz → Deezer) ===")
    resolved = resolve_batch(tracks)
    with_isrc = [t for t in resolved if t.get("isrc")]
    print(f"[RESOLVE] {len(with_isrc)} with ISRC | {len(resolved)-len(with_isrc)} dropped")
    save_csv(resolved, os.path.join(DATA_DIR, "resolved.csv"))
    return with_isrc


def stage_enrich(tracks: list) -> list:
    print("\n=== STAGE 3: ENRICH (Chartmetric popularity filter > 60) ===")
    enriched = score_with_chartmetric(tracks, min_popularity=60)
    save_csv(enriched, os.path.join(DATA_DIR, "enriched.csv"))
    return enriched


def stage_score(tracks: list, batch_size: int) -> list:
    print(f"\n=== STAGE 4: SNIPER SCORE (top {batch_size} targets) ===")
    top = filter_top_targets(tracks, limit=batch_size)
    save_csv(top, MASTER_CSV)
    print(f"\n  Top 5 targets queued for probe:")
    for t in top[:5]:
        print(f"    {t['artist']} — {t['track']} | sniper: {t.get('sniper_score')} | label: {t.get('label','?')}")
    return top


def stage_probe(targets: list, batch_size: int):
    print(f"\n=== STAGE 5: PROBE SoundExchange ({batch_size} searches) ===")
    run_probe(targets, max_per_session=batch_size)


def stage_outreach():
    print("\n=== STAGE 6: OUTREACH (Hunter.io buyer emails) ===")
    if not os.path.exists(LEADS_CSV):
        print(f"[OUTREACH] No leads.csv yet — run probe first.")
        return
    leads = load_csv(LEADS_CSV)
    actionable = [l for l in leads if l.get("status") in ("UNCLAIMED", "CONFLICT")]
    print(f"[OUTREACH] {len(actionable)} actionable leads (UNCLAIMED + CONFLICT)")
    find_buyers_for_leads(actionable)


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary():
    """Print a quick count of what's been found so far."""
    if not os.path.exists(LEADS_CSV):
        return
    df = pd.read_csv(LEADS_CSV)
    total = len(df)
    unclaimed = len(df[df["status"] == "UNCLAIMED"])
    conflicts = len(df[df["status"] == "CONFLICT"])
    print(f"\n{'='*50}")
    print(f"  LEADS SUMMARY")
    print(f"  Total probed : {total}")
    print(f"  Unclaimed    : {unclaimed}  ← highest priority")
    print(f"  Conflicts    : {conflicts}  ← legal leads")
    print(f"  Est. value   : ${(unclaimed * 10000 + conflicts * 5000):,} (rough floor)")
    print(f"{'='*50}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bounty Hunter Pipeline")
    parser.add_argument(
        "--batch", type=int, default=50,
        help="Targets per session: 50 (start) or 100 (daily)"
    )
    parser.add_argument(
        "--stage",
        choices=["collect", "collect-atlanta", "resolve", "re-resolve", "enrich", "score", "probe", "outreach", "all"],
        default="all",
    )
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  BOUNTY HUNTER | {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Batch: {args.batch} | Stage: {args.stage}")
    print(f"{'='*50}")

    os.makedirs(DATA_DIR, exist_ok=True)

    if args.stage == "all":
        tracks = stage_collect(weekly_limit=args.batch)
        tracks = stage_resolve(tracks)
        tracks = stage_enrich(tracks)
        targets = stage_score(tracks, batch_size=args.batch)
        stage_probe(targets, batch_size=args.batch)
        stage_outreach()
        print_summary()

    elif args.stage == "collect":
        stage_collect(weekly_limit=args.batch)

    elif args.stage == "collect-atlanta":
        print("\n=== ATLANTA MARKET COLLECT ===")
        leads = pull_atlanta_leads()
        save_csv(leads, os.path.join(DATA_DIR, "atlanta_targets.csv"))
        import shutil
        shutil.copy(os.path.join(DATA_DIR, "atlanta_targets.csv"), MASTER_CSV)
        print(f"[ATLANTA] master_targets.csv updated with {len(leads)} leads")
        print("  Next: python run_pipeline.py --stage resolve")

    elif args.stage == "resolve":
        raw = load_csv(os.path.join(DATA_DIR, "raw_collected.csv"))
        stage_resolve(raw)

    elif args.stage == "re-resolve":
        print("\n=== SPOTIFY RE-RESOLVE (recovering missed ISRCs) ===")
        re_resolve(input_csv=os.path.join(DATA_DIR, "raw_collected.csv"), limit=args.batch)
        print("  Next: python run_pipeline.py --stage enrich")

    elif args.stage == "enrich":
        resolved = load_csv(os.path.join(DATA_DIR, "resolved.csv"))
        stage_enrich([t for t in resolved if t.get("isrc")])

    elif args.stage == "score":
        enriched = load_csv(os.path.join(DATA_DIR, "enriched.csv"))
        stage_score([t for t in enriched if t.get("isrc")], batch_size=args.batch)

    elif args.stage == "probe":
        if not os.path.exists(MASTER_CSV):
            print("[ERROR] Run collect/resolve/score first.")
            sys.exit(1)
        targets = load_csv(MASTER_CSV)
        stage_probe(targets, batch_size=args.batch)

    elif args.stage == "outreach":
        stage_outreach()
        print_summary()


if __name__ == "__main__":
    main()
