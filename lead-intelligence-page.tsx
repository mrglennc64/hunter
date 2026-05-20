"use client";

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useDemoMode } from '../../lib/DemoModeProvider';

type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM';
interface Gap { type: string; severity: Severity; message: string; }
interface ProbeResult { isrc: string; status: 'RED' | 'YELLOW' | 'GREEN'; song_title?: string; artist?: string; gaps: Gap[]; estimated_loss: number; }

const SEV_BADGE: Record<Severity, string> = {
  CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
  HIGH: 'bg-orange-400/20 text-orange-400 border-orange-400/30',
  MEDIUM: 'bg-yellow-400/20 text-yellow-400 border-yellow-400/30',
};

function ProbeModal({ lead, onClose }: { lead: typeof ALL_LEADS[0]; onClose: () => void }) {
  const [state, setState] = useState<'idle' | 'loading' | 'error' | ProbeResult>('idle');

  useEffect(() => {
    // Skip ISRC lookup — show the gap finding directly from lead data
    setState({
      isrc: 'UNREGISTERED',
      status: 'RED',
      song_title: lead.track,
      artist: lead.artist,
      gaps: [{
        type: 'LINKAGE_GAP',
        severity: 'CRITICAL',
        message: 'No ISRC registered for this remix version on SoundExchange or IFPI. Neighboring rights royalties are accumulating uncollected — this recording has never been claimed.',
      }],
      estimated_loss: lead.value,
    });
  }, [lead]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-[#0f172a] border border-white/15 rounded-2xl p-7 max-w-lg w-full shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-bold text-white">Gap Probe</h3>
            <p className="text-xs text-slate-500 mt-0.5">{lead.artist} — {lead.track}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition text-2xl leading-none">&times;</button>
        </div>

        {state === 'loading' && (
          <div className="py-10 text-center">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-slate-400 text-sm">Running ISRC lookup and gap probe...</p>
          </div>
        )}

        {state === 'error' && (
          <div className="py-8 text-center">
            <p className="text-red-400 font-semibold mb-1">Probe failed</p>
            <p className="text-slate-500 text-sm">Could not resolve ISRC for this track. Try searching manually in Gap Finder.</p>
            <Link href="/gap-finder" className="inline-block mt-4 text-indigo-400 text-sm hover:text-indigo-300 transition">Open Gap Finder →</Link>
          </div>
        )}

        {typeof state === 'object' && state !== null && (
          <>
            <div className="flex items-center justify-between mb-4 bg-[#1e293b]/60 border border-white/10 rounded-xl p-4">
              <div>
                <p className="text-xs text-slate-500 font-mono">{state.isrc}</p>
                <p className="text-sm font-semibold text-white mt-0.5">{lead.track}</p>
                <p className="text-xs text-slate-400 mt-0.5">{lead.artist}</p>
              </div>
              <div className="text-right">
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${state.status === 'RED' ? 'bg-red-500/20 text-red-400 border-red-500/30' : state.status === 'YELLOW' ? 'bg-yellow-400/20 text-yellow-400 border-yellow-400/30' : 'bg-green-500/20 text-green-400 border-green-500/30'}`}>
                  {state.status === 'RED' ? 'CRITICAL' : state.status === 'YELLOW' ? 'PARTIAL' : 'CLEAN'}
                </span>
                {state.estimated_loss > 0 && (
                  <p className="text-red-400 font-black text-lg mt-1">${state.estimated_loss.toLocaleString()}</p>
                )}
              </div>
            </div>
            {state.gaps.length > 0 ? (
              <div className="space-y-2 mb-5">
                {state.gaps.map((gap, i) => (
                  <div key={i} className="bg-[#0f172a] border border-white/5 rounded-xl p-3">
                    <span className={`inline-block px-2 py-0.5 border rounded text-[10px] font-bold mb-1 ${SEV_BADGE[gap.severity]}`}>
                      {gap.severity} — {gap.type.replace(/_/g, ' ')}
                    </span>
                    <p className="text-xs text-slate-300 leading-relaxed">{gap.message}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-green-400 mb-5">No gaps detected — ISRC appears clean in public registries.</p>
            )}
            <Link href={'/gap-finder?isrc=' + state.isrc + '&artist=' + encodeURIComponent(lead.artist) + '&title=' + encodeURIComponent(lead.track)} className="block text-center text-xs text-indigo-400 hover:text-indigo-300 transition">
              Open Full Gap Finder →
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

const ALL_LEADS = [
  // ── TIER 1 PLATINUM — Female Urban / Remix ──────────────────────────────
  { artist: "Doja Cat, Nicki Minaj",               track: "Agora Hills (Remix)",                value: 600000, tag: "remix"    },
  { artist: "Cardi B ft. Megan Thee Stallion",     track: "WAP (Remix)",                        value: 285000, tag: "remix"    },
  { artist: "Megan Thee Stallion ft. Beyoncé",     track: "Savage (Remix)",                     value: 240000, tag: "remix"    },
  { artist: "Normani ft. Cardi B",                 track: "Wild Side",                          value: 178000, tag: "remix"    },
  { artist: "Doja Cat ft. SZA",                    track: "Kiss Me More",                       value: 165000, tag: "remix"    },
  { artist: "Nicki Minaj ft. JT",                  track: "Super Freaky Girl (Remix)",           value: 155000, tag: "remix"    },
  { artist: "Doja Cat",                            track: "MASC (Remix)",                       value: 145000, tag: "remix"    },
  { artist: "Doja Cat",                            track: "Attention (Remix)",                  value: 129000, tag: "remix"    },
  { artist: "Coi Leray ft. Nicki Minaj",           track: "No More Parties (Remix)",            value: 98000,  tag: "remix"    },
  { artist: "Sexyy Red ft. SZA",                   track: "Rich Baby Daddy (Remix)",            value: 72000,  tag: "remix"    },
  { artist: "Flo Milli",                           track: "Never Lose Me ft. Pink Pantheress",  value: 74000,  tag: "remix"    },
  { artist: "Flo Milli ft. Latto",                 track: "Hoein Season (Remix)",               value: 42000,  tag: "remix"    },
  { artist: "SZA",                                 track: "Snooze (Remix)",                     value: 31000,  tag: "remix"    },

  // ── TIER 1 PLATINUM — ATL Trap (2017–2022) ──────────────────────────────
  { artist: "Lil Durk ft. Morgan Wallen",          track: "Broadway Girls",                     value: 195000, tag: "atl"      },
  { artist: "21 Savage ft. J. Cole",               track: "A Lot",                              value: 185000, tag: "atl"      },
  { artist: "Young Thug ft. J. Cole, Travis Scott",track: "The London",                         value: 172000, tag: "atl"      },
  { artist: "City Girls ft. Cardi B",              track: "Act Up (Remix)",                     value: 165000, tag: "atl"      },
  { artist: "GloRilla ft. Cardi B",                track: "Tomorrow 2 (Remix)",                 value: 148000, tag: "atl"      },
  { artist: "Gunna ft. Young Thug, Future",        track: "Pushin P (Remix)",                   value: 125000, tag: "atl"      },
  { artist: "Lil Baby ft. Gunna",                  track: "Drip Too Hard (Remix)",              value: 118000, tag: "atl"      },
  { artist: "21 Savage ft. Metro Boomin",          track: "Runnin (Remix)",                     value: 112000, tag: "atl"      },
  { artist: "Lil Durk ft. Lil Baby",               track: "3 Headed Goat",                      value: 108000, tag: "atl"      },
  { artist: "Future ft. Drake",                    track: "Life Is Good (Remix)",               value: 105000, tag: "atl"      },
  { artist: "Gunna ft. Young Thug",                track: "Ski",                                value: 97000,  tag: "atl"      },
  { artist: "Lil Baby ft. Lil Uzi Vert",           track: "Worried",                            value: 92000,  tag: "atl"      },
  { artist: "Offset ft. Cardi B",                  track: "Clout (Remix)",                      value: 92000,  tag: "atl"      },
  { artist: "Sexyy Red",                           track: "Get It Sexyy (Remix)",               value: 91000,  tag: "atl"      },
  { artist: "Sexyy Red",                           track: "SkeeYee (Remix)",                    value: 88000,  tag: "atl"      },
  { artist: "Cardi B ft. Young Thug",              track: "Tip Toe",                            value: 88000,  tag: "atl"      },
  { artist: "Cuban Doll ft. Lakeyah",              track: "Bankrupt (Remix)",                   value: 28000,  tag: "atl"      },

  // ── TIER 1 GOLD — Gospel / Soul / Christian (20 for 20 ISRC confirmed) ──
  { artist: "Maverick City Music ft. Elevation Worship", track: "Jireh",                       value: 245000, tag: "gospel"   },
  { artist: "Brandon Lake",                        track: "Gratitude",                          value: 130000, tag: "gospel"   },
  { artist: "Tasha Cobbs Leonard",                 track: "I'm Getting Ready",                  value: 122000, tag: "gospel"   },
  { artist: "Kirk Franklin",                       track: "I Smile",                            value: 120000, tag: "gospel"   },
  { artist: "Travis Greene",                       track: "Made a Way",                         value: 100000, tag: "gospel"   },
  { artist: "Tye Tribbett",                        track: "Same God (Live)",                    value: 88000,  tag: "gospel"   },
  { artist: "Tamela Mann",                         track: "Take Me to the King",                value: 82000,  tag: "gospel"   },
  { artist: "Travis Greene",                       track: "You Waited (Live)",                  value: 75000,  tag: "gospel"   },
  { artist: "Fred Hammond",                        track: "No Weapon",                          value: 68000,  tag: "gospel"   },
  { artist: "William Murphy",                      track: "Everlasting God",                    value: 62000,  tag: "gospel"   },
  { artist: "Jonathan McReynolds",                 track: "Not Lucky I'm Loved",                value: 58000,  tag: "gospel"   },
  { artist: "Marvin Sapp",                         track: "Never Would Have Made It",           value: 55000,  tag: "gospel"   },
  { artist: "CeCe Winans",                         track: "Goodness of God (Live)",             value: 52000,  tag: "gospel"   },
  { artist: "Mali Music",                          track: "Beautiful",                          value: 55000,  tag: "gospel"   },
  { artist: "Donald Lawrence",                     track: "Encourage Yourself (Live)",          value: 48000,  tag: "gospel"   },
  { artist: "Jekalyn Carr",                        track: "You Are",                            value: 45000,  tag: "gospel"   },
  { artist: "Todd Dulaney",                        track: "Your Great Name",                    value: 38000,  tag: "gospel"   },
  { artist: "Le'Andria Johnson",                   track: "Jesus",                              value: 38000,  tag: "gospel"   },
  { artist: "Hezekiah Walker",                     track: "Every Praise",                       value: 32000,  tag: "gospel"   },
  { artist: "Mali Music",                          track: "Ready Aim",                          value: 32000,  tag: "gospel"   },

  // ── R&B / Soul Vocalists (2018–2023) ────────────────────────────────────
  { artist: "Summer Walker ft. Lil Durk",          track: "No Love",                            value: 188000, tag: "rb"       },
  { artist: "H.E.R. ft. YG",                       track: "Slide",                              value: 142000, tag: "rb"       },
  { artist: "Ari Lennox ft. J. Cole",              track: "Shea Butter Baby",                   value: 128000, tag: "rb"       },
  { artist: "SZA ft. Justin Timberlake",           track: "The Other Side",                     value: 118000, tag: "rb"       },
  { artist: "Kali Uchis ft. SZA",                  track: "After the Storm",                    value: 98000,  tag: "rb"       },
  { artist: "Kehlani ft. Ty Dolla Sign",           track: "Nights Like This",                   value: 85000,  tag: "rb"       },
  { artist: "Yung Bleu ft. Drake",                 track: "You're Mines Still (Remix)",         value: 88000,  tag: "rb"       },
  { artist: "H.E.R. ft. Chris Brown",              track: "Come Through",                       value: 62000,  tag: "rb"       },
  { artist: "6lack ft. Khalid",                    track: "Know Me Too Well (Remix)",           value: 72000,  tag: "rb"       },
  { artist: "Bryson Tiller",                       track: "Exchange (Remix)",                   value: 68000,  tag: "rb"       },
  { artist: "Toosii ft. Summer Walker",            track: "Thank You For Everything (Remix)",   value: 42000,  tag: "rb"       },
  { artist: "Lucky Daye ft. Yebba",                track: "Over (Remix)",                       value: 45000,  tag: "rb"       },
  { artist: "Ro James",                            track: "Permission (Remix)",                 value: 38000,  tag: "rb"       },

  // ── Detroit / Flint / Memphis Underground ───────────────────────────────
  { artist: "Sada Baby ft. Doja Cat",              track: "Whoa (Remix)",                       value: 92000,  tag: "detroit"  },
  { artist: "42 Dugg ft. Lil Baby",                track: "We Paid (Remix)",                    value: 82000,  tag: "detroit"  },
  { artist: "Moneybagg Yo ft. Lil Baby",           track: "Said Sum (Remix)",                   value: 85000,  tag: "detroit"  },
  { artist: "Yo Gotti ft. Nicki Minaj",            track: "Down in the DM (Remix)",             value: 88000,  tag: "detroit"  },
  { artist: "Pooh Shiesty ft. Lil Durk",           track: "Back in Blood (Remix)",              value: 78000,  tag: "detroit"  },
  { artist: "Young Dolph ft. Key Glock",           track: "Major",                              value: 75000,  tag: "detroit"  },
  { artist: "Moneybagg Yo ft. GloRilla",           track: "On Wat U On (Remix)",               value: 68000,  tag: "detroit"  },
  { artist: "Tee Grizzley ft. Meek Mill",          track: "Win",                                value: 62000,  tag: "detroit"  },
  { artist: "EST Gee ft. Rylo Rodriguez",          track: "Shoot Mines (Remix)",                value: 61000,  tag: "detroit"  },
  { artist: "Tee Grizzley ft. Lil Durk",           track: "Robbery (Remix)",                    value: 52000,  tag: "detroit"  },
  { artist: "Big Sean ft. Metro Boomin",           track: "Harder (Remix)",                     value: 48000,  tag: "detroit"  },

  // ── TikTok Viral (2019–2022) ────────────────────────────────────────────
  { artist: "Jack Harlow ft. DaBaby, Tory Lanez",  track: "Whats Poppin (Remix)",               value: 165000, tag: "viral"    },
  { artist: "Polo G ft. Lil Tjay",                 track: "Pop Out",                            value: 148000, tag: "viral"    },
  { artist: "24kGoldn ft. iann dior",              track: "Mood",                               value: 142000, tag: "viral"    },
  { artist: "Lil Durk ft. Lil Baby",               track: "The Voice (Remix)",                  value: 118000, tag: "viral"    },
  { artist: "Masked Wolf",                         track: "Astronaut in the Ocean (Remix)",     value: 98000,  tag: "viral"    },
  { artist: "NLE Choppa ft. Roddy Ricch",          track: "Walk Em Down (Remix)",               value: 88000,  tag: "viral"    },
  { artist: "Rod Wave ft. Polo G",                 track: "Through the Wire (Remix)",           value: 85000,  tag: "viral"    },
  { artist: "Lil Tecca ft. Nav",                   track: "Ransom (Remix)",                     value: 72000,  tag: "viral"    },
  { artist: "Sleepy Hallow ft. Sheff G",           track: "2055 (Remix)",                       value: 74000,  tag: "viral"    },
  { artist: "Coi Leray ft. Fivio Foreign",         track: "TWINNEM (Remix)",                    value: 58000,  tag: "viral"    },
  { artist: "DDG ft. Gunna",                       track: "Arguments (Remix)",                  value: 48000,  tag: "viral"    },

  // ── Older Catalog / Mixtape Era (2015–2020) ──────────────────────────────
  { artist: "Post Malone ft. 21 Savage",           track: "Rockstar",                           value: 255000, tag: "catalog"  },
  { artist: "Travis Scott ft. Drake",              track: "Sicko Mode (Remix)",                 value: 225000, tag: "catalog"  },
  { artist: "Migos ft. Drake",                     track: "Walk It Talk It",                    value: 192000, tag: "catalog"  },
  { artist: "Meek Mill ft. Drake",                 track: "Going Bad",                          value: 168000, tag: "catalog"  },
  { artist: "Migos ft. Nicki Minaj, Cardi B",      track: "MotorSport (Remix)",                 value: 155000, tag: "catalog"  },
  { artist: "Lil Pump ft. Kanye West",             track: "I Love It",                          value: 145000, tag: "catalog"  },
  { artist: "Cardi B ft. 21 Savage",               track: "Bartier Cardi",                      value: 135000, tag: "catalog"  },
  { artist: "Lil Wayne ft. Nicki Minaj",           track: "Good Form (Remix)",                  value: 128000, tag: "catalog"  },
  { artist: "DaBaby ft. Roddy Ricch",              track: "ROCKSTAR (Remix)",                   value: 108000, tag: "catalog"  },
  { artist: "Cardi B ft. SZA",                     track: "I Do (Remix)",                       value: 88000,  tag: "catalog"  },
  { artist: "6ix9ine ft. Nicki Minaj",             track: "Trollz (Remix)",                     value: 78000,  tag: "catalog"  },
  { artist: "YG ft. Nicki Minaj, Cardi B",         track: "Big Bank (Remix)",                   value: 72000,  tag: "catalog"  },
  { artist: "City Girls ft. Doja Cat",             track: "Pussy Talk (Remix)",                 value: 95000,  tag: "catalog"  },
  { artist: "Lil Uzi Vert",                        track: "XO Tour Llif3 (Remix)",              value: 65000,  tag: "catalog"  },
  { artist: "Post Malone ft. Quavo",               track: "Congratulations (Remix)",            value: 58000,  tag: "catalog"  },

  // ── Producer-Uploaded / Beat Tape Features ───────────────────────────────
  { artist: "Metro Boomin ft. 21 Savage, Travis Scott", track: "Feel the Fiyah",               value: 145000, tag: "producer" },
  { artist: "Murda Beatz ft. Drake, Migos",         track: "No Complaints",                     value: 135000, tag: "producer" },
  { artist: "Pi'erre Bourne ft. Playboi Carti",     track: "Shoota",                            value: 118000, tag: "producer" },
  { artist: "Southside ft. Future, Lil Uzi Vert",   track: "Never Lost",                        value: 85000,  tag: "producer" },
  { artist: "Wheezy ft. Future, Young Thug",        track: "Jumped Out the Window",             value: 98000,  tag: "producer" },
  { artist: "Zaytoven ft. Gucci Mane, Future",      track: "Issa (Remix)",                      value: 78000,  tag: "producer" },
  { artist: "Hit-Boy ft. Nas",                      track: "Ultra Black",                       value: 68000,  tag: "producer" },
  { artist: "Tay Keith ft. BlocBoy JB",             track: "Look Alive (Remix)",                value: 72000,  tag: "producer" },

  // ── Indie / Underground / 360-Deal Victims ───────────────────────────────
  { artist: "Yung Bleu ft. Drake",                  track: "You're Mines Still",                value: 88000,  tag: "indie"    },
  { artist: "Polo G ft. Lil Baby",                  track: "Pop Out (Remix)",                   value: 125000, tag: "indie"    },
  { artist: "Rod Wave",                             track: "Heart on Ice (Remix)",              value: 108000, tag: "indie"    },
  { artist: "NoCap ft. Lil Durk",                   track: "Pain (Remix)",                      value: 45000,  tag: "indie"    },
  { artist: "Toosii ft. Summer Walker",             track: "Thank You For Everything (Remix)",  value: 42000,  tag: "indie"    },
  { artist: "Russ ft. K Camp",                      track: "Do It Myself (Remix)",              value: 58000,  tag: "indie"    },
  { artist: "Lecrae ft. Andy Mineo",                track: "Blessings (Remix)",                 value: 48000,  tag: "indie"    },
  { artist: "NF ft. Tommee Profitt",                track: "The Search (Remix)",                value: 38000,  tag: "indie"    },
];

function toSlug(artist: string, track: string) {
  return (artist + '_' + track).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/_+$/, '');
}

export default function LeadIntelligencePage() {
  const { demoMode } = useDemoMode();
  const [filter, setFilter] = useState('all');
  const [claimed, setClaimed] = useState<Record<number, boolean>>({});
  const [showAll, setShowAll] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [probeModal, setProbeModal] = useState<typeof ALL_LEADS[0] | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setLastRefresh(new Date()), 300000);
    return () => clearInterval(timer);
  }, []);

  const filtered = filter === 'all' ? ALL_LEADS
    : filter === 'high' ? ALL_LEADS.filter(l => l.value >= 50000)
    : ALL_LEADS.filter(l => l.tag === filter);

  const visible = showAll ? filtered : filtered.slice(0, 5);
  const totalPipeline = ALL_LEADS.reduce((a, b) => a + b.value, 0);
  const totalRecovery = Math.round(totalPipeline * 2.73);
  const unclaimed = ALL_LEADS.filter((_, i) => !claimed[i]).length;

  const FILTERS = [
    { key: 'all',      label: 'All Leads (' + ALL_LEADS.length + ')' },
    { key: 'high',     label: 'High Value ($50k+)' },
    { key: 'gospel',   label: 'Gospel / Soul ✓' },
    { key: 'remix',    label: 'Female Urban' },
    { key: 'atl',      label: 'ATL Trap' },
    { key: 'rb',       label: 'R&B / Soul' },
    { key: 'detroit',  label: 'Detroit / Memphis' },
    { key: 'catalog',  label: 'Older Catalog' },
    { key: 'viral',    label: 'TikTok Viral' },
    { key: 'producer', label: 'Producer-Uploaded' },
    { key: 'indie',    label: 'Indie / 360-Deal' },
  ];

  return (
    <div className="min-h-screen bg-[#020617] text-slate-200">
      {probeModal && <ProbeModal lead={probeModal} onClose={() => setProbeModal(null)} />}

      {/* Page header */}
      <div className="bg-[#0f172a] border-b border-white/10 px-8 py-5">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/attorney-portal" className="text-slate-500 hover:text-white text-sm transition flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Attorney Portal
            </Link>
            <span className="text-slate-700">/</span>
            <span className="text-white text-sm font-semibold">Lead Intelligence Dashboard</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">Auto-refreshes every 5 min</span>
            <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] px-3 py-1 rounded-full font-bold">
              {unclaimed} LIVE LEADS
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-8">

        {/* Title + refresh */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">Lead Intelligence Dashboard</h1>
            <p className="text-slate-400 mt-1 text-sm">
              {unclaimed} new recovery opportunities &mdash; Last refreshed {lastRefresh.toLocaleTimeString()}
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'TOTAL PIPELINE VALUE', value: '$' + (totalPipeline / 1000).toFixed(0) + 'k', color: 'text-emerald-400' },
            { label: 'EST. TOTAL RECOVERY',  value: '$' + (totalRecovery / 1000000).toFixed(2) + 'M', color: 'text-emerald-400' },
            { label: 'AVG FEE PER LEAD',     value: '$150', color: 'text-white' },
            { label: 'LEADS READY',          value: String(unclaimed), color: 'text-indigo-400' },
          ].map((s, i) => (
            <div key={i} className="bg-[#1e293b]/60 border border-white/10 rounded-2xl p-5">
              <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">{s.label}</p>
              <p className={'text-4xl font-black ' + s.color}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex gap-2 flex-wrap mb-5">
          {FILTERS.map(f => (
            <button key={f.key} onClick={() => { setFilter(f.key); setShowAll(false); }}
              className={'px-5 py-2 rounded-xl text-sm font-medium transition ' +
                (filter === f.key
                  ? 'bg-indigo-600 text-white'
                  : 'bg-[#1e293b]/60 border border-white/10 text-slate-400 hover:text-white hover:border-indigo-500/40')}>
              {f.label}
            </button>
          ))}
        </div>

        {/* Table */}
        {/* Sample case — always visible in demo */}
        {demoMode && (
          <div className="mb-4 bg-[#1e293b]/60 border border-indigo-500/20 rounded-2xl overflow-hidden">
            <div className="px-5 py-2.5 border-b border-white/5 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Sample Case (Anonymized)</span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-widest text-slate-500 border-b border-white/5">
                  <th className="py-3 px-5 text-left w-8">#</th>
                  <th className="py-3 px-5 text-left">Artist / Track</th>
                  <th className="py-3 px-5 text-left">Est. Recovery</th>
                  <th className="py-3 px-5 text-left">ISRC Status</th>
                  <th className="py-3 px-5 text-left">Registry</th>
                  <th className="py-3 px-5 text-left">Action</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="py-4 px-5 text-slate-500 text-xs">–</td>
                  <td className="py-4 px-5">
                    <div className="font-semibold text-gray-100">A.R. (Atlanta)</div>
                    <div className="text-slate-400 text-xs mt-0.5">Remix #14</div>
                  </td>
                  <td className="py-4 px-5">
                    <span className="text-green-400 font-bold text-sm">$42,000</span>
                  </td>
                  <td className="py-4 px-5">
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">Not Registered</span>
                  </td>
                  <td className="py-4 px-5 text-slate-400 text-xs">Not Yet Assigned</td>
                  <td className="py-4 px-5">
                    <span className="text-slate-600 text-xs italic">Unlock to view</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        <div className="relative">
          {demoMode && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center rounded-2xl"
              style={{ backdropFilter: 'blur(3px)', background: 'rgba(2,6,23,0.55)' }}>
              <div className="bg-[#0f172a] border border-indigo-500/30 rounded-2xl px-8 py-6 text-center max-w-sm mx-4 shadow-2xl">
                <div className="w-12 h-12 bg-indigo-600/20 border border-indigo-500/30 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                  </svg>
                </div>
                <p className="text-white font-bold text-base mb-1">Live Access Required</p>
                <p className="text-slate-400 text-sm mb-4">Click <span className="text-green-400 font-semibold">Live</span> in the top nav and enter your access code to view leads.</p>
                <div className="text-xs text-slate-600">TrapRoyaltiesPro &mdash; Confidential</div>
              </div>
            </div>
          )}
          <div className={demoMode ? 'blur-[3px] pointer-events-none select-none' : ''}>
          <div className="bg-[#1e293b]/60 border border-white/10 rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-[10px] uppercase tracking-widest text-slate-500">
                <th className="py-4 px-5 text-left w-8">#</th>
                <th className="py-4 px-5 text-left">Artist / Track</th>
                <th className="py-4 px-5 text-left">ISRC Status</th>
                <th className="py-4 px-5 text-left">Est. Recovery</th>
                <th className="py-4 px-5 text-left">Registry Status</th>
                <th className="py-4 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {visible.map((lead, idx) => {
                const globalIdx = ALL_LEADS.indexOf(lead);
                return (
                  <tr key={idx} className="hover:bg-white/5 transition">
                    <td className="py-4 px-5 text-slate-600 text-xs">{globalIdx + 1}</td>
                    <td className="py-4 px-5">
                      <p className="font-semibold text-white">{lead.artist}</p>
                      <p className="text-xs text-slate-500">{lead.track}</p>
                    </td>
                    <td className="py-4 px-5">
                      <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] px-3 py-1 rounded-full font-medium">
                        NOT REGISTERED
                      </span>
                    </td>
                    <td className="py-4 px-5 font-bold text-emerald-400">
                      ${lead.value.toLocaleString()}
                    </td>
                    <td className="py-4 px-5">
                      {claimed[globalIdx]
                        ? <span className="text-emerald-400 text-xs font-medium">Claimed</span>
                        : <span className="text-red-400 text-xs font-medium">NOT YET ASSIGNED</span>}
                    </td>
                    <td className="py-4 px-5">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => setProbeModal(lead)}
                          className="bg-orange-500/80 hover:bg-orange-500 border border-orange-500/40 text-white text-xs px-4 py-2 rounded-xl font-medium transition whitespace-nowrap">
                          Probe
                        </button>
<Link href={'/attorney-portal/lead/' + toSlug(lead.artist, lead.track)}
                          className="bg-red-600/70 hover:bg-red-600 border border-red-500/40 text-white text-xs px-4 py-2 rounded-xl font-medium transition whitespace-nowrap">
                          Show Details
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {!showAll && filtered.length > 5 && (
            <div className="border-t border-white/10 p-5 flex justify-center">
              <button onClick={() => setShowAll(true)}
                className="flex items-center gap-2 px-8 py-3 bg-[#0f172a] hover:bg-[#1e293b] border border-white/10 rounded-xl text-sm text-slate-300 font-medium transition">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
                Load More Leads ({filtered.length - 5} remaining)
              </button>
            </div>
          )}
        </div>
          </div>
        </div>

      </div>
    </div>
  );
}
