"use client";

import Link from 'next/link';
import { useState, useEffect, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM';
type Status = 'GREEN' | 'YELLOW' | 'RED';

interface Gap {
  type: string;
  severity: Severity;
  message: string;
}

interface ProbeResult {
  isrc: string;
  status: Status;
  song_title?: string;
  artist?: string;
  gaps: Gap[];
  estimated_loss: number;
  details?: Record<string, any>;
}

interface Recording {
  isrc: string;
  title: string;
  artist?: string;
}

interface ArtistMatch {
  id?: string;
  mbid?: string;
  name: string;
  disambiguation?: string;
  recordings?: Recording[];
}

const SEV_DOT: Record<Severity, string> = {
  CRITICAL: 'bg-red-500', HIGH: 'bg-orange-400', MEDIUM: 'bg-yellow-400',
};
const SEV_BADGE: Record<Severity, string> = {
  CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/30',
  HIGH: 'bg-orange-400/20 text-orange-400 border-orange-400/30',
  MEDIUM: 'bg-yellow-400/20 text-yellow-400 border-yellow-400/30',
};
const ACTION_MAP: Record<string, string> = {
  LINKAGE_GAP: 'Register ISRC \u2192',
  ISWC_GAP: 'Link via CWR \u2192',
  PERCENTAGE_GAP: 'Verify Splits \u2192',
  IDENTITY_GAP: 'Add IPI \u2192',
  NEIGHBORING_RIGHTS_GAP: 'Verify Registration \u2192',
};

function ProbeCard({ result }: { result: ProbeResult }) {
  const [generated, setGenerated] = useState(false);
  const [generating, setGenerating] = useState(false);
  const dotColor = result.status === 'RED' ? 'bg-red-500' : result.status === 'YELLOW' ? 'bg-yellow-400' : 'bg-green-500';
  const lossColor = result.status === 'RED' ? 'text-red-400' : result.status === 'YELLOW' ? 'text-yellow-400' : 'text-green-400';

  return (
    <div className="bg-[#111827] border border-white/10 rounded-2xl p-6 mb-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-4">
          <div className="flex flex-col gap-1.5 mt-1.5">
            <span className={`w-3 h-3 rounded-full ${dotColor}`} />
            <span className="w-3 h-3 rounded-full bg-slate-700" />
            <span className="w-3 h-3 rounded-full bg-slate-700" />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1 flex-wrap">
              <h2 className="text-xl font-black">{result.song_title || result.isrc}</h2>
              {result.status === 'RED' && <span className="px-2 py-0.5 bg-red-500/20 border border-red-500/40 text-red-400 text-xs font-bold rounded">X CRITICAL</span>}
              {result.status === 'YELLOW' && <span className="px-2 py-0.5 bg-yellow-400/20 border border-yellow-400/40 text-yellow-400 text-xs font-bold rounded">PARTIAL</span>}
              {result.status === 'GREEN' && <span className="px-2 py-0.5 bg-green-500/20 border border-green-500/40 text-green-400 text-xs font-bold rounded">CLEAN</span>}
            </div>
            <p className="text-slate-400 text-sm">{result.artist || '\u2014'}</p>
            <p className="font-mono text-xs text-slate-500 mt-0.5">{result.isrc}</p>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <p className={`text-2xl font-black ${lossColor}`}>
            {result.estimated_loss > 0 ? '$' + result.estimated_loss.toLocaleString() : '\u2014'}
          </p>
          <p className="text-xs text-slate-500 uppercase tracking-wider mt-0.5">Est. Annual Loss</p>
        </div>
      </div>

      {result.gaps.length > 0 ? (
        <>
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2 mb-4">
            <p className="text-xs font-bold text-red-400 uppercase tracking-widest">{result.gaps.length} Gap{result.gaps.length !== 1 ? 's' : ''} Detected</p>
          </div>
          <div className="space-y-3 mb-5">
            {result.gaps.map((gap, i) => (
              <div key={i} className="flex items-start gap-3 bg-[#0f172a] border border-white/5 rounded-xl p-4">
                <span className={`w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0 ${SEV_DOT[gap.severity]}`} />
                <div className="flex-1 min-w-0">
                  <span className={`inline-block px-2 py-0.5 border rounded text-[10px] font-bold mb-1.5 ${SEV_BADGE[gap.severity]}`}>
                    {gap.severity} \u2014 {gap.type.replace(/_/g, ' ')}
                  </span>
                  <p className="text-sm text-slate-300 leading-relaxed">{gap.message}</p>
                </div>
                <button className="flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-bold bg-indigo-600/80 hover:bg-indigo-600 text-white transition">
                  {ACTION_MAP[gap.type] || 'Review \u2192'}
                </button>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg px-4 py-3 mb-5">
          <p className="text-sm font-bold text-green-400">No gaps detected \u2014 ISRC appears clean in public registries.</p>
        </div>
      )}

      <button
        onClick={() => { setGenerating(true); setTimeout(() => { setGenerating(false); setGenerated(true); }, 1500); }}
        disabled={generating || generated}
        className="w-full py-3 bg-orange-500 hover:bg-orange-400 disabled:opacity-60 text-white font-black text-sm rounded-xl transition uppercase tracking-widest"
      >
        {generated ? '\u2713 Recovery Directive Generated' : generating ? 'Generating...' : 'Generate Recovery Directive \u2192'}
      </button>
    </div>
  );
}

function GapFinderInner() {
  const [query, setQuery] = useState('');
  const [directISRC, setDirectISRC] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  // Artist search results
  const [artists, setArtists] = useState<ArtistMatch[]>([]);
  const [selectedArtist, setSelectedArtist] = useState<ArtistMatch | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [loadingRecordings, setLoadingRecordings] = useState(false);

  // Per-ISRC probe results
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult | 'loading' | 'error'>>({});

  const searchParams = useSearchParams();
  const didAutoRun = useRef(false);

  useEffect(() => {
    if (didAutoRun.current) return;
    const isrc = searchParams.get('isrc');
    if (isrc) {
      didAutoRun.current = true;
      setQuery(isrc);
      runProbe(isrc.toUpperCase().replace(/-/g, ''));
    }
  }, [searchParams]);

  const isISRC = (s: string) => /^[A-Z]{2}[A-Z0-9]{3}\d{7}$/i.test(s.replace(/-/g, ''));

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearchError('');
    setArtists([]);
    setSelectedArtist(null);
    setRecordings([]);
    setProbeResults({});

    if (isISRC(q)) {
      // Direct ISRC probe
      runProbe(q.toUpperCase().replace(/-/g, ''));
      return;
    }

    setSearching(true);
    try {
      const res = await fetch('/api/royalty-finder/search/artist?query=' + encodeURIComponent(q));
      const data = await res.json();
      const list: ArtistMatch[] = (data.artists || []).slice(0, 5);
      if (list.length === 0) { setSearchError('No artists found. Try a different spelling.'); }
      else if (list.length === 1) { selectArtist(list[0]); }
      else { setArtists(list); }
    } catch {
      setSearchError('Search failed \u2014 check network.');
    } finally {
      setSearching(false);
    }
  };

  const selectArtist = async (artist: ArtistMatch) => {
    setSelectedArtist(artist);
    setArtists([]);
    setLoadingRecordings(true);
    setRecordings([]);
    try {
      const res = await fetch('/api/royalty-finder/artist/' + (artist.mbid || artist.id) + '/recordings?limit=30');
      const data = await res.json();
      setRecordings(data.recordings || []);
    } catch {
      setSearchError('Could not load tracks for this artist.');
    } finally {
      setLoadingRecordings(false);
    }
  };

  const runProbe = async (isrc: string) => {
    setProbeResults(p => ({ ...p, [isrc]: 'loading' }));
    try {
      const res = await fetch('/api/gap-finder/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isrc }),
      });
      const data = await res.json();
      if (data.error) setProbeResults(p => ({ ...p, [isrc]: 'error' }));
      else setProbeResults(p => ({ ...p, [isrc]: data }));
    } catch {
      setProbeResults(p => ({ ...p, [isrc]: 'error' }));
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      <header className="sticky top-0 z-50 bg-[#0a0f1e]/95 backdrop-blur border-b border-white/10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-xl font-bold text-indigo-300">
              TrapRoyalties<span className="text-indigo-400">Pro</span>
            </Link>
            <span className="text-slate-600">/</span>
            <span className="text-sm text-slate-400">Gap Finder</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/attorney-portal" className="text-sm text-slate-400 hover:text-white transition">Attorney Portal</Link>
            <Link href="/graph-demo" className="text-sm text-slate-400 hover:text-white transition">Identity Graph</Link>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-10">

        {/* Search */}
        <div className="bg-[#111827] border border-white/10 rounded-2xl p-6 mb-6">
          <h2 className="text-sm font-bold text-indigo-300 uppercase tracking-widest mb-1">Gap Finder</h2>
          <p className="text-xs text-slate-500 mb-4">Enter an artist name to see all their tracks and run a gap probe on any ISRC.</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSearch(); }}
              placeholder="Artist name or ISRC (e.g. GloRilla, Future, USRC17607839)"
              className="flex-1 px-4 py-3 bg-[#0a0f1e] border border-white/10 rounded-xl text-white placeholder-slate-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !query.trim()}
              className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-xl text-sm font-bold transition whitespace-nowrap"
            >
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>
          {searchError && <p className="text-xs text-red-400 mt-2">{searchError}</p>}
        </div>

        {/* Multiple artist matches */}
        {artists.length > 1 && (
          <div className="bg-[#111827] border border-white/10 rounded-2xl p-5 mb-6">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Select Artist</p>
            <div className="space-y-2">
              {artists.map(a => (
                <button
                  key={a.id}
                  onClick={() => selectArtist(a)}
                  className="w-full text-left px-4 py-3 bg-[#0a0f1e] border border-white/5 hover:border-indigo-500/50 rounded-xl text-sm transition"
                >
                  <span className="font-semibold text-white">{a.name}</span>
                  {a.disambiguation && <span className="text-slate-500 ml-2 text-xs">({a.disambiguation})</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Track list */}
        {(selectedArtist || loadingRecordings) && (
          <div className="bg-[#111827] border border-white/10 rounded-2xl p-5 mb-6">
            {selectedArtist && (
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm font-bold text-white">{selectedArtist.name}</p>
                <span className="text-xs text-slate-500">{recordings.length} tracks</span>
              </div>
            )}
            {loadingRecordings ? (
              <p className="text-sm text-slate-500 text-center py-4">Loading tracks...</p>
            ) : (
              <div className="space-y-2">
                {recordings.map((rec, i) => {
                  const isrc = (rec as any).primary_isrc || rec.isrc;
                  const probeState = probeResults[isrc];
                  return (
                    <div key={isrc + i} className="flex items-center gap-3 px-4 py-3 bg-[#0a0f1e] border border-white/5 rounded-xl">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-white truncate">{rec.title}</p>
                        <p className="font-mono text-xs text-slate-500 mt-0.5">{isrc}</p>
                      </div>
                      {probeState === 'loading' ? (
                        <span className="text-xs text-slate-500 whitespace-nowrap">Probing...</span>
                      ) : probeState === 'error' ? (
                        <span className="text-xs text-red-400 whitespace-nowrap">Error</span>
                      ) : typeof probeState === 'object' ? (
                        <span className={`text-xs font-bold whitespace-nowrap ${probeState.status === 'RED' ? 'text-red-400' : probeState.status === 'YELLOW' ? 'text-yellow-400' : 'text-green-400'}`}>
                          {probeState.status === 'RED' ? probeState.gaps.length + ' gap' + (probeState.gaps.length !== 1 ? 's' : '') : 'Clean'}
                        </span>
                      ) : (
                        <button
                          onClick={() => runProbe(isrc)}
                          className="px-3 py-1.5 bg-orange-500 hover:bg-orange-400 text-white rounded-lg text-xs font-bold transition whitespace-nowrap"
                        >
                          Run Probe
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Probe results */}
        {Object.entries(probeResults)
          .filter(([, v]) => typeof v === 'object')
          .map(([isrc, result]) => (
            <ProbeCard key={isrc} result={result as ProbeResult} />
          ))
        }

      </div>
    </div>
  );
}

export default function GapFinder() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a0f1e] text-white flex items-center justify-center"><p className="text-slate-500">Loading...</p></div>}>
      <GapFinderInner />
    </Suspense>
  );
}
