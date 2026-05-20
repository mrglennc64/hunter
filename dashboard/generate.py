"""
Dashboard Generator — TrapRoyalties Lead List
Reads unlock_catalog.json and writes a static HTML dashboard to /var/www/html/index.html
Run after every probe to refresh the page.

Usage:
    python dashboard/generate.py
"""

import os, sys, json, datetime, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG     = os.path.join(DATA_DIR, "unlock_catalog.json")
LEADS_CSV   = os.path.join(DATA_DIR, "leads.csv")
OUTPUT_FILE = "/var/www/html/dashboard.html"

TIER_COLORS = {
    "TIER 1": "#00c851",
    "TIER 2": "#3b82f6",
    "TIER 3": "#f59e0b",
    "TIER 4": "#94a3b8",
}


def tier_color(priority: str) -> str:
    for k, v in TIER_COLORS.items():
        if k in priority:
            return v
    return "#94a3b8"


def load_catalog():
    if not os.path.exists(CATALOG):
        return {}
    with open(CATALOG) as f:
        return json.load(f)


def load_probe_results() -> dict:
    """Load leads.csv and return {isrc: status, 'artist|track': status} lookup."""
    probe = {}
    if not os.path.exists(LEADS_CSV):
        return probe
    with open(LEADS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            status = row.get("status", "").strip()
            isrc   = row.get("isrc", "").strip()
            key    = f"{row.get('artist','').lower()}|{row.get('track','').lower()[:40]}"
            if isrc:
                probe[isrc] = status
            probe[key] = status
    return probe


def generate():
    catalog = load_catalog()
    if not catalog:
        print("[DASH] No leads in catalog — run generate_catalog.py first")
        return

    probe = load_probe_results()
    probed_count = len([v for v in probe.values() if v in ("JACKPOT","REGISTERED","GUEST_UNCLAIMED")])
    print(f"[DASH] Probe results loaded: {probed_count} entries from leads.csv")

    def get_probe_status(l):
        isrc_k = l.get("isrc", "")
        nk = f"{l.get('artist','').lower()}|{l.get('track','').lower()[:40]}"
        return probe.get(isrc_k) or probe.get(nk) or ""

    import re as _re

    GOSPEL_ARTISTS = {"kirk franklin","maverick city music","elevation worship","lecrae","andy mineo",
        "jonathan mcreynolds","koryn hawthorne","kierra sheard","erica campbell","mary mary",
        "tamela mann","le'andria johnson","mali music","travis greene","brandon lake",
        "chandler moore","naomi raine","cece winans","deitrick haddon","william mcdowell",
        "hezekiah walker","fred hammond","donald lawrence","jekalyn carr","doe"}
    ATL_ARTISTS = {"glorilla","glorrilla","latto","anycia","karrahbooo","monaleo","babydrill",
        "hunxho","sexyy red","flo milli","ice spice","doja cat","cardi b","nicki minaj",
        "megan thee stallion","doechii","bia","kali","yung miami","jt","city girls",
        "yung miami","cuban doll","maliibu miitch","ykniece","jt"}

    def classify(lead):
        artist_l = lead.get("artist", "").lower()
        track_l  = lead.get("track", "").lower()
        tags = []
        if artist_l in GOSPEL_ARTISTS or any(a in artist_l for a in GOSPEL_ARTISTS):
            tags.append("gospel")
        if artist_l in ATL_ARTISTS or any(a in artist_l for a in ATL_ARTISTS):
            tags.append("atl")
        if _re.search(r'remix|live|version', track_l):
            tags.append("remix")
        return tags

    # Only show confirmed jackpots + unprobed leads (hide REGISTERED)
    all_leads = []
    for aid, lead in catalog.items():
        status = get_probe_status(lead)
        if status == "REGISTERED":
            continue
        hi_str = lead.get("bounty_high", "$0").replace("$", "").replace(",", "")
        try:
            hi = float(hi_str)
        except ValueError:
            hi = 0
        tags = classify(lead)
        all_leads.append((hi, aid, lead, tags))
    all_leads.sort(reverse=True)

    # Pick top 10 per category, merge with dedup, preserve rank order
    CAP = 10
    buckets = {"gospel": [], "atl": [], "remix": [], "high": []}
    for hi, aid, lead, tags in all_leads:
        if "gospel" in tags and len(buckets["gospel"]) < CAP:
            buckets["gospel"].append(aid)
        if "atl" in tags and len(buckets["atl"]) < CAP:
            buckets["atl"].append(aid)
        if "remix" in tags and len(buckets["remix"]) < CAP:
            buckets["remix"].append(aid)
        if hi >= 10000 and len(buckets["high"]) < CAP:
            buckets["high"].append(aid)

    selected_ids = set()
    for ids in buckets.values():
        selected_ids.update(ids)

    leads = [(hi, aid, lead) for hi, aid, lead, tags in all_leads if aid in selected_ids]
    leads.sort(reverse=True)

    # Store tags per aid for row rendering
    _tags_map = {aid: tags for hi, aid, lead, tags in all_leads}

    contacts_found = sum(
        1 for _, _, l in leads
        if l.get("attorney_email") or l.get("manager_email") or l.get("artist_email")
    )

    jackpot_count = sum(
        1 for _, aid, l in leads
        if get_probe_status(l) in ("JACKPOT", "GUEST_UNCLAIMED")
    )

    total_lo = sum(
        float(l.get("bounty_low",  "$0").replace("$","").replace(",",""))
        for _, _, l in leads
    )
    total_hi = sum(
        float(l.get("bounty_high", "$0").replace("$","").replace(",",""))
        for _, _, l in leads
    )

    now = datetime.datetime.utcnow().strftime("%B %d, %Y — %H:%M UTC")

    # Per-category counts for sidebar badges
    cnt_high   = len(buckets["high"])
    cnt_remix  = len(buckets["remix"])
    cnt_atl    = len(buckets["atl"])
    cnt_gospel = len(buckets["gospel"])

    # ── Build lead rows ────────────────────────────────────────────────────────
    rows_html = ""
    for rank, (hi_val, aid, lead) in enumerate(leads, 1):
        filter_tags = list(_tags_map.get(aid, []))
        if hi_val >= 10000 and "high" not in filter_tags:
            filter_tags.append("high")
        filter_attr = " ".join(filter_tags) if filter_tags else "other"
        artist   = lead.get("artist", "")
        track    = lead.get("track",  "")
        streams  = lead.get("streams", 0)
        lo_fmt   = lead.get("bounty_low",  "$0")
        hi_fmt   = lead.get("bounty_high", "$0")
        priority = lead.get("priority", "TIER 4 - MICRO").replace("\u2014", "-")
        color    = tier_color(priority)

        # Look up actual SoundExchange probe result
        isrc = lead.get("isrc", "")
        name_key = f"{artist.lower()}|{track.lower()[:40]}"
        probe_status = probe.get(isrc) or probe.get(name_key) or lead.get("status", "")

        streams_fmt = f"{int(streams):,}" if streams else "—"
        if probe_status == "JACKPOT":
            status_label = "JACKPOT — UNREGISTERED"
            status_css   = "status-jackpot"
        elif probe_status == "GUEST_UNCLAIMED":
            status_label = "UNREGISTERED FEATURED ARTIST"
            status_css   = "status-jackpot"
        elif probe_status == "REGISTERED":
            status_label = "REGISTERED"
            status_css   = "status-registered"
        elif probe_status == "UNKNOWN":
            status_label = "PROBE INCONCLUSIVE"
            status_css   = "status-unknown"
        else:
            status_label = "NOT YET PROBED"
            status_css   = "status-pending"

        atty_name = lead.get("attorney_name", "")
        atty_firm = lead.get("attorney_firm", "")
        mgr_name  = lead.get("manager_name", "")
        mgr_firm  = lead.get("manager_firm", "")

        atty_email = lead.get("attorney_email", "")
        mgr_email  = lead.get("manager_email",  "")
        artist_email = lead.get("artist_email", "")
        artist_email_src = lead.get("artist_email_source", "")

        atty_email_html = f'<div class="rep-email"><a href="mailto:{atty_email}">{atty_email}</a></div>' if atty_email else ''
        mgr_email_html  = f'<div class="rep-email"><a href="mailto:{mgr_email}">{mgr_email}</a></div>'  if mgr_email  else ''

        atty_html = f'<div class="rep-name">{atty_name}</div><div class="rep-firm">{atty_firm}</div>{atty_email_html}' if atty_name else '<span class="rep-none">—</span>'
        mgr_html  = f'<div class="rep-name">{mgr_name}</div><div class="rep-firm">{mgr_firm}</div>{mgr_email_html}'   if mgr_name  else '<span class="rep-none">—</span>'

        artist_email_html = f'<div class="rep-email artist-email"><a href="mailto:{artist_email}">{artist_email}</a> <span class="email-src">{artist_email_src}</span></div>' if artist_email else ''

        # Build contact cell (attorney first, then manager)
        contact_cell = ""
        if atty_name:
            contact_cell += f'<div class="font-medium text-gray-200 text-xs">{atty_name}</div>'
            if atty_firm:
                contact_cell += f'<div class="text-gray-500 text-xs">{atty_firm}</div>'
            if atty_email:
                contact_cell += f'<div><a href="mailto:{atty_email}" class="text-purple-400 text-xs hover:underline">{atty_email}</a></div>'
        elif mgr_name:
            contact_cell += f'<div class="font-medium text-gray-200 text-xs">{mgr_name}</div>'
            if mgr_firm:
                contact_cell += f'<div class="text-gray-500 text-xs">{mgr_firm}</div>'
            if mgr_email:
                contact_cell += f'<div><a href="mailto:{mgr_email}" class="text-purple-400 text-xs hover:underline">{mgr_email}</a></div>'
        else:
            contact_cell = '<span class="text-gray-600 text-xs">—</span>'

        rows_html += f"""
        <tr class="lead-row {'hidden-row' if rank > 5 else ''}" data-rank="{rank}" data-filter="{filter_attr}" style="border-top:1px solid #1a1a1a;">
          <td class="py-4 px-5 text-gray-500 text-xs">#{rank}</td>
          <td class="py-4 px-5">
            <div class="font-semibold text-gray-100">{artist}</div>
            <div class="text-gray-400 text-xs mt-0.5">{track}</div>
            {artist_email_html}
          </td>
          <td class="py-4 px-5 whitespace-nowrap">
            <span class="text-green-400 font-bold text-sm">{hi_fmt}</span>
            <span class="text-gray-600 text-xs ml-1">/ {lo_fmt} min</span>
          </td>
          <td class="py-4 px-5"><span class="{status_css}">{status_label}</span></td>
          <td class="py-4 px-5">{contact_cell}</td>
          <td class="py-4 px-5 text-right">
            <a href="/lawyer/{aid}" class="bg-purple-800 hover:bg-purple-700 text-white text-xs px-4 py-2 rounded-xl font-semibold transition-colors">View &amp; Unlock</a>
          </td>
        </tr>"""

    # ── Build email list rows ──────────────────────────────────────────────────
    email_rows_html = ""
    for _, aid, lead in leads:
        atty_e = lead.get("attorney_email", "")
        mgr_e  = lead.get("manager_email",  "")
        art_e  = lead.get("artist_email",   "")
        if not atty_e and not mgr_e and not art_e:
            continue
        artist_n = lead.get("artist", "")
        track_n  = lead.get("track",  "")
        hi_fmt   = lead.get("bounty_high", "")
        contacts_html = ""
        if atty_e:
            contacts_html += f'<span class="email-tag tag-atty">ATTORNEY</span><span class="email-addr"><a href="mailto:{atty_e}">{atty_e}</a></span> &nbsp; '
        if mgr_e:
            contacts_html += f'<span class="email-tag tag-mgr">MANAGER</span><span class="email-addr"><a href="mailto:{mgr_e}">{mgr_e}</a></span> &nbsp; '
        if art_e:
            contacts_html += f'<span class="email-tag tag-art">ARTIST</span><span class="email-addr"><a href="mailto:{art_e}">{art_e}</a></span>'
        email_rows_html += f"""
        <div class="email-row">
          <div class="email-row-artist">{artist_n}</div>
          <div class="email-row-track">{track_n}</div>
          <div>{contacts_html}</div>
          <div class="email-row-bounty">{hi_fmt}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lead Intelligence Dashboard • TrapRoyalties Pro</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <style>
    body {{ background-color: #0a0a0a; color: #e0e0e0; font-family: 'Inter', system-ui, sans-serif; }}
    .card {{ background-color: #111111; border: 1px solid #222222; }}
    .neon-purple {{ color: #c026d3; text-shadow: 0 0 10px #c026d3; }}
    .lead-row {{ transition: all 0.2s ease; cursor: pointer; }}
    .lead-row:hover {{ background-color: #1a1a1a; transform: translateX(3px); }}
    .hidden-row {{ display: none !important; }}
    .status-jackpot {{ background: rgba(0,200,81,0.15); color: #00c851; border: 1px solid rgba(0,200,81,0.3); border-radius: 4px; padding: 3px 8px; font-size: 10px; font-weight: 700; letter-spacing: 0.06em; }}
    .status-pending  {{ background: rgba(192,38,211,0.15); color: #c026d3; border: 1px solid rgba(192,38,211,0.3); border-radius: 4px; padding: 3px 8px; font-size: 10px; font-weight: 700; letter-spacing: 0.06em; }}
    .status-unknown  {{ background: rgba(245,158,11,0.12); color: #f59e0b; border-radius: 4px; padding: 3px 8px; font-size: 10px; font-weight: 700; }}
    .rep-email a {{ color: #a78bfa; font-size: 11px; text-decoration: none; }}
    .rep-email a:hover {{ text-decoration: underline; }}
    .rep-firm {{ color: #6b7280; font-size: 11px; }}
    .sidebar-link {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 16px; color: #9ca3af; transition: all 0.15s; cursor: pointer; }}
    .sidebar-link:hover {{ background: #1a1a1a; color: #e0e0e0; }}
    .sidebar-link.active {{ background: #2d1b69; color: #fff; font-weight: 600; }}
  </style>
</head>
<body class="min-h-screen">

<!-- Top Nav -->
<div class="bg-black border-b border-purple-800 px-8 py-4 flex items-center justify-between">
  <div class="flex items-center gap-4">
    <h1 class="text-2xl font-black neon-purple tracking-widest">TRAPROYALTIES PRO</h1>
    <span class="text-xs bg-purple-700 text-white px-3 py-1 rounded-full font-semibold tracking-wide">ATTORNEY PORTAL</span>
  </div>
  <div class="flex items-center gap-6 text-sm text-gray-400">
    <div class="flex items-center gap-2">
      <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
      <span>Live</span>
    </div>
    <span>{now}</span>
  </div>
</div>

<div class="flex" style="min-height: calc(100vh - 57px)">

  <!-- Sidebar -->
  <div class="w-64 bg-black border-r border-gray-900 p-5 flex-shrink-0">
    <div class="text-xs uppercase tracking-widest text-gray-500 mb-4 px-2">Lead Intelligence</div>
    <div class="sidebar-link active" onclick="filterLeads('all', this)">
      <i class="fas fa-chart-line w-4"></i>
      <span>All Recovery Leads</span>
      <span class="ml-auto bg-green-500 text-black text-xs px-2 py-0.5 rounded-full font-bold">{len(leads)}</span>
    </div>
    <div class="sidebar-link" onclick="filterLeads('high', this)">
      <i class="fas fa-dollar-sign w-4"></i>
      <span>High Value</span>
      <span class="ml-auto bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">{cnt_high}</span>
    </div>
    <div class="sidebar-link" onclick="filterLeads('remix', this)">
      <i class="fas fa-music w-4"></i>
      <span>Remixes Only</span>
      <span class="ml-auto bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">{cnt_remix}</span>
    </div>
    <div class="sidebar-link" onclick="filterLeads('atl', this)">
      <i class="fas fa-microphone w-4"></i>
      <span>ATL / Female Rappers</span>
      <span class="ml-auto bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">{cnt_atl}</span>
    </div>
    <div class="sidebar-link" onclick="filterLeads('gospel', this)">
      <i class="fas fa-church w-4"></i>
      <span>Gospel / Soul</span>
      <span class="ml-auto bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">{cnt_gospel}</span>
    </div>
    <div class="mt-8 border-t border-gray-900 pt-6 text-xs text-gray-600 px-2">
      <div>Audit Fee: $150/report</div>
      <div class="mt-1">Protocol: SMPT V1</div>
      <div class="mt-1">Contacts: {contacts_found} ready</div>
    </div>
  </div>

  <!-- Main -->
  <div class="flex-1 p-8 overflow-auto">

    <!-- Header -->
    <div class="flex justify-between items-start mb-8">
      <div>
        <h2 class="text-3xl font-bold mb-1">Lead Intelligence Dashboard</h2>
        <p class="text-gray-500 text-sm">{len(leads)} recovery opportunities · ranked by estimated recovery value</p>
      </div>
      <input type="text" id="searchInput" placeholder="Search artist or track..."
        class="bg-gray-900 border border-gray-700 focus:border-purple-500 rounded-2xl px-4 py-2 w-72 outline-none text-sm text-gray-200"
        oninput="searchLeads(this.value)">
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-4 gap-4 mb-8">
      <div class="card p-5 rounded-2xl">
        <div class="text-xs text-gray-500 uppercase tracking-widest mb-2">Min Recovery</div>
        <div class="text-3xl font-black text-green-400">${total_lo:,.0f}</div>
      </div>
      <div class="card p-5 rounded-2xl">
        <div class="text-xs text-gray-500 uppercase tracking-widest mb-2">Max Recovery</div>
        <div class="text-3xl font-black text-green-400">${total_hi:,.0f}</div>
      </div>
      <div class="card p-5 rounded-2xl">
        <div class="text-xs text-gray-500 uppercase tracking-widest mb-2">Leads Ready</div>
        <div class="text-3xl font-black text-purple-400">{len(leads)}</div>
      </div>
      <div class="card p-5 rounded-2xl">
        <div class="text-xs text-gray-500 uppercase tracking-widest mb-2">Confirmed Jackpots</div>
        <div class="text-3xl font-black text-green-400">{jackpot_count}</div>
      </div>
    </div>

    <!-- Table -->
    <div class="card rounded-2xl overflow-hidden">
      <table class="w-full" style="font-size:13px; border-collapse:collapse;">
        <thead>
          <tr style="background:#0d0d0d;">
            <th class="py-4 px-5 text-left text-xs uppercase tracking-widest text-gray-500">#</th>
            <th class="py-4 px-5 text-left text-xs uppercase tracking-widest text-gray-500">Artist / Track</th>
            <th class="py-4 px-5 text-left text-xs uppercase tracking-widest text-gray-500">Est. Recovery</th>
            <th class="py-4 px-5 text-left text-xs uppercase tracking-widest text-gray-500">Status</th>
            <th class="py-4 px-5 text-left text-xs uppercase tracking-widest text-gray-500">Contact</th>
            <th class="py-4 px-5 text-right text-xs uppercase tracking-widest text-gray-500">Action</th>
          </tr>
        </thead>
        <tbody style="divide-y: #1f1f1f;">
          {rows_html}
        </tbody>
      </table>
    </div>

    <!-- Load More -->
    <div class="text-center mt-6" id="load-more-wrap">
      <button onclick="loadMore()"
        class="bg-gray-900 hover:bg-gray-800 border border-gray-700 hover:border-purple-500 text-gray-300 hover:text-purple-400 px-8 py-3 rounded-2xl text-sm font-semibold transition-all">
        Load More Leads
      </button>
    </div>

    {"" if not email_rows_html else f'''
    <div class="mt-10">
      <h3 class="text-xs uppercase tracking-widest text-gray-500 mb-4">{contacts_found} Contacts Ready</h3>
      <div class="card rounded-2xl p-6 flex flex-col gap-3">
        {email_rows_html}
      </div>
    </div>
    '''}

    <div class="text-center mt-8 text-xs text-gray-700">
      TrapRoyaltiesPro &nbsp;·&nbsp; Confidential &nbsp;·&nbsp; Authorized for Legal Representation Only &nbsp;·&nbsp; {now}
    </div>

  </div>
</div>

<script>
// Poll Flask API every 30s and update engagement cells
async function refreshEvents() {{
  try {{
    const res = await fetch('/api/email-events');
    const events = await res.json();
    for (const [aid, ev] of Object.entries(events)) {{
      const cell = document.getElementById('ev-' + aid);
      if (!cell) continue;
      const opens  = ev.opens  || [];
      const clicks = ev.clicks || [];
      const openEl  = cell.querySelector('.ev-open');
      const clickEl = cell.querySelector('.ev-click');
      if (openEl) {{
        openEl.textContent = opens.length ? opens.length + ' open' + (opens.length > 1 ? 's' : '') : '— opens';
        openEl.classList.toggle('active', opens.length > 0);
        if (opens.length) openEl.title = 'Last: ' + opens[opens.length-1].replace('T',' ').slice(0,16) + ' UTC';
      }}
      if (clickEl) {{
        clickEl.textContent = clicks.length ? clicks.length + ' click' + (clicks.length > 1 ? 's' : '') : '— clicks';
        clickEl.classList.toggle('active', clicks.length > 0);
        if (clicks.length) clickEl.title = 'Last: ' + clicks[clicks.length-1].replace('T',' ').slice(0,16) + ' UTC';
      }}
    }}
  }} catch(e) {{ /* API not reachable from static view */ }}
}}
refreshEvents();
setInterval(refreshEvents, 30000);

let currentFilter = 'all';
let visibleCount = 5;

function filterLeads(tag, el) {{
  currentFilter = tag;
  visibleCount = 30;
  document.querySelectorAll('.sidebar-link').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilter();
}}

function searchLeads(val) {{
  const q = val.toLowerCase();
  document.querySelectorAll('.lead-row').forEach(row => {{
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(q) ? '' : 'none';
  }});
}}

function applyFilter() {{
  let shown = 0;
  document.querySelectorAll('.lead-row').forEach(row => {{
    const tags = row.dataset.filter || '';
    const match = currentFilter === 'all' || tags.includes(currentFilter);
    if (match && shown < visibleCount) {{
      row.style.display = '';
      shown++;
    }} else {{
      row.style.display = 'none';
    }}
  }});
  const loadMoreWrap = document.getElementById('load-more-wrap');
  const hiddenMatching = [...document.querySelectorAll('.lead-row')].filter(r => {{
    const tags = r.dataset.filter || '';
    return (currentFilter === 'all' || tags.includes(currentFilter)) && r.style.display === 'none';
  }});
  loadMoreWrap.style.display = hiddenMatching.length > 0 ? '' : 'none';
}}

function loadMore() {{
  visibleCount += 25;
  applyFilter();
}}
</script>

</body>
</html>"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[DASH] Dashboard written → {OUTPUT_FILE}")
    print(f"[DASH] {len(leads)} leads | Portfolio: ${total_lo:,.0f} - ${total_hi:,.0f}")
    print(f"[DASH] View at: http://187.77.111.16/")


if __name__ == "__main__":
    generate()
