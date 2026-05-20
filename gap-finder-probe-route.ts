import { NextResponse } from 'next/server';

const MB_BASE = 'https://musicbrainz.org/ws/2';
const LB_BASE = 'https://api.listenbrainz.org/1';
const MB_HEADERS = {
  'User-Agent': 'TrapRoyaltiesPro/1.0 (traproyaltiespro.com)',
  Accept: 'application/json',
};

function isValidISRC(isrc: string) {
  return /^[A-Z]{2}[A-Z0-9]{3}\d{7}$/.test(isrc);
}

// Estimate monthly revenue from listen count using blended per-stream rate
function estimateRevenue(listenCount: number): number {
  const BLENDED_RATE = 0.004; // $0.004 per stream (blended Spotify/Apple/Amazon)
  return Math.round(listenCount * BLENDED_RATE * 100) / 100;
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const rawISRC = (body.isrc || '').toString().toUpperCase().replace(/-/g, '').trim();
    const estimatedRevenue: number = body.estimated_revenue || 0;
    const hintTitle: string = body.hint_title || '';
    const hintArtist: string = body.hint_artist || '';

    if (!isValidISRC(rawISRC)) {
      return NextResponse.json({ error: 'Invalid ISRC — must be 12 chars (e.g. USUM71703861)' }, { status: 400 });
    }

    const report: {
      isrc: string;
      song_title?: string;
      artist?: string;
      status: 'GREEN' | 'YELLOW' | 'RED';
      gaps: { type: string; severity: 'CRITICAL' | 'HIGH' | 'MEDIUM'; message: string }[];
      estimated_loss: number;
      details: Record<string, any>;
    } = {
      isrc: rawISRC,
      status: 'GREEN',
      gaps: [],
      estimated_loss: 0,
      details: {},
    };

    // ── CHECK A: LINKAGE GAP ────────────────────────────────────────
    let mbRecording: any = null;
    let mbWork: any = null;
    try {
      const res = await fetch(`${MB_BASE}/isrc/${rawISRC}?inc=artists+releases+recording-rels&fmt=json`, { headers: MB_HEADERS });
      if (res.ok) {
        const data = await res.json();
        const rec = data.recordings?.[0];
        if (rec) {
          mbRecording = {
            mbid: rec.id,
            title: rec.title,
            artist: rec['artist-credit']?.[0]?.name || null,
            artist_mbid: rec['artist-credit']?.[0]?.artist?.id || null,
            artist_credits: (rec['artist-credit'] || []).map((ac: any) => ({
              name: ac.name || ac.artist?.name,
              mbid: ac.artist?.id,
            })),
            releases: (rec.releases || []).slice(0, 3).map((r: any) => ({
              title: r.title, date: r.date, country: r.country,
            })),
          };
        }
      }
    } catch { /* continue */ }

    // ── ACRCloud fallback when MB has no record ──────────────────────
    let acrFallback: any = null;
    if (!mbRecording) {
      const acrToken = process.env.ACRCLOUD_TOKEN;
      if (acrToken) {
        try {
          const acrRes = await fetch(
            `https://eu-api-v2.acrcloud.com/api/external-metadata/tracks?isrc=${rawISRC}&include_works=1&platforms=spotify,deezer,youtube,applemusic`,
            {
              headers: { Authorization: acrToken.startsWith('Bearer ') ? acrToken : `Bearer ${acrToken}` },
              signal: AbortSignal.timeout(8_000),
            }
          );
          if (acrRes.ok) {
            const acrJson = await acrRes.json();
            const t = acrJson.data?.[0];
            if (t) {
              const ext = t.external_metadata ?? {};
              const w = t.works?.[0];
              acrFallback = {
                name: t.name,
                artists: (t.artists ?? []).map((a: any) => a.name),
                album: {
                  title: t.album?.title ?? null,
                  label: t.album?.label ?? null,
                  cover: t.album?.covers?.medium ?? t.album?.cover ?? null,
                  upc:   t.album?.upc ?? null,
                },
                iswc: w?.iswc ?? null,
                contributors: (w?.contributors ?? []).map((c: any) => ({ name: c.name, ipi: c.ipi ?? null, roles: c.roles ?? [] })),
                platforms: {
                  spotify:    ext.spotify?.[0]?.link    ?? null,
                  applemusic: ext.applemusic?.[0]?.link ?? null,
                  youtube:    ext.youtube?.[0]?.link    ?? null,
                  deezer:     ext.deezer?.[0]?.link     ?? null,
                },
              };
            }
          }
        } catch { /* ACRCloud fallback optional */ }
      }
    }

    if (!mbRecording && !acrFallback) {
      report.gaps.push({
        type: 'LINKAGE_GAP',
        severity: 'CRITICAL',
        message: 'ISRC not found in MusicBrainz or ACRCloud — not linked to any registered recording.',
      });
      report.status = 'RED';
    } else if (!mbRecording && acrFallback) {
      // ACRCloud knows this track but MB doesn't — linkage gap, not total dark
      report.gaps.push({
        type: 'LINKAGE_GAP',
        severity: 'HIGH',
        message: 'ISRC confirmed via ACRCloud but not registered in MusicBrainz — publishing royalty routing may be incomplete.',
      });
      report.status = 'YELLOW';
      report.details.recording = { title: acrFallback.name, artist: acrFallback.artists?.[0] ?? null, source: 'ACRCloud' };
      report.details.acr_enriched = acrFallback;
      // Check B & C using ACRCloud data
      if (!acrFallback.iswc) {
        report.gaps.push({ type: 'ISWC_GAP', severity: 'HIGH', message: 'No ISWC found — publishing royalties unroutable at PROs.' });
      }
      const contribsWithIpi = acrFallback.contributors.filter((c: any) => c.ipi);
      if (acrFallback.contributors.length > 0 && contribsWithIpi.length < acrFallback.contributors.length) {
        const missing = acrFallback.contributors.length - contribsWithIpi.length;
        report.gaps.push({ type: 'PERCENTAGE_GAP', severity: 'HIGH', message: `${missing} of ${acrFallback.contributors.length} contributors missing IPI — share of publishing may be unclaimed.` });
      }
    } else {
      report.details.recording = mbRecording;
      report.song_title = hintTitle || mbRecording.title;
      report.artist = hintArtist || mbRecording.artist;

      // ── CHECK: NEIGHBORING RIGHTS / FORMAT VARIANT ─────────────────
      const FORMAT_VARIANT_RE = /360\s*reality|atmos|dolby|binaural|spatial audio|immersive|hi-?res|lossless/i;
      const isFormatVariant = FORMAT_VARIANT_RE.test(mbRecording.title || '');
      const hasReleases = (mbRecording.releases?.length ?? 0) > 0;

      if (isFormatVariant) {
        report.gaps.push({
          type: 'NEIGHBORING_RIGHTS_GAP',
          severity: 'HIGH',
          message: `Format-specific version detected ("${mbRecording.title}"). Alternate format ISRCs often require separate neighboring rights registration — verify this ISRC is on file with SoundExchange / PPL.`,
        });
        if (report.status === 'GREEN') report.status = 'YELLOW';
      } else if (!hasReleases) {
        report.gaps.push({
          type: 'NEIGHBORING_RIGHTS_GAP',
          severity: 'HIGH',
          message: 'Recording confirmed in MusicBrainz but no commercial release detected. Neighboring rights collection status cannot be confirmed from public data — verify with your rights society.',
        });
        if (report.status === 'GREEN') report.status = 'YELLOW';
      }
    }

    // ── CHECK B: PERCENTAGE / ISWC GAP ─────────────────────────────
    // Fetch the associated work for ISWC + writer IPI data
    if (mbRecording?.mbid) {
      try {
        const workRes = await fetch(
          `${MB_BASE}/recording/${mbRecording.mbid}?inc=work-rels+artist-rels&fmt=json`,
          { headers: MB_HEADERS }
        );
        if (workRes.ok) {
          const workData = await workRes.json();
          const workRel = workData.relations?.find((r: any) => r['target-type'] === 'work');
          if (workRel?.work) {
            // Fetch full work details for ISWC + writer IPIs
            const wRes = await fetch(
              `${MB_BASE}/work/${workRel.work.id}?inc=artist-rels&fmt=json`,
              { headers: MB_HEADERS }
            );
            if (wRes.ok) {
              const wData = await wRes.json();
              const writers = (wData.relations || []).filter(
                (r: any) => r['target-type'] === 'artist' && ['writer', 'composer', 'lyricist', 'arranger'].includes(r.type)
              );
              const writersWithIpi = writers.filter((r: any) => r.artist?.ipis?.length > 0);
              const iswc = wData.iswcs?.[0] || null;

              mbWork = {
                id: wData.id,
                title: wData.title,
                iswc,
                writers: writers.map((r: any) => ({
                  name: r.artist?.name,
                  mbid: r.artist?.id,
                  ipi: r.artist?.ipis?.[0] || null,
                  role: r.type,
                })),
                total_writers: writers.length,
                writers_with_ipi: writersWithIpi.length,
              };
              report.details.work = mbWork;

              // Check B1: No ISWC = publishing not routable
              if (!iswc) {
                report.gaps.push({
                  type: 'ISWC_GAP',
                  severity: 'HIGH',
                  message: 'No ISWC linked to this recording — publishing royalties unroutable at PROs.',
                });
                if (report.status === 'GREEN') report.status = 'YELLOW';
              }

              // Check B2: Writers without IPI = percentage gap (their share is uncollected)
              const writersWithoutIpi = mbWork.total_writers - mbWork.writers_with_ipi;
              if (writersWithoutIpi > 0) {
                const gapPct = mbWork.total_writers > 0
                  ? Math.round((writersWithoutIpi / mbWork.total_writers) * 100)
                  : 0;
                report.gaps.push({
                  type: 'PERCENTAGE_GAP',
                  severity: 'HIGH',
                  message: `${writersWithoutIpi} of ${mbWork.total_writers} writers missing IPI — est. ${gapPct}% of publishing share unclaimed.`,
                });
                if (report.status === 'GREEN') report.status = 'YELLOW';
              }
            }
          } else {
            // No work linked at all
            report.gaps.push({
              type: 'PERCENTAGE_GAP',
              severity: 'HIGH',
              message: 'No music work (composition) linked to this recording — 100% of publishing share unverifiable.',
            });
            if (report.status === 'GREEN') report.status = 'YELLOW';
          }
        }
      } catch { /* continue */ }
    }

    // ── CHECK C: METADATA / IPI GAP ────────────────────────────────
    if (mbRecording?.artist_mbid) {
      try {
        const artistRes = await fetch(
          `${MB_BASE}/artist/${mbRecording.artist_mbid}?fmt=json`,
          { headers: MB_HEADERS }
        );
        if (artistRes.ok) {
          const artistData = await artistRes.json();
          const ipi = artistData.ipis?.[0] || null;
          const isni = artistData.isnis?.[0] || null;
          report.details.artist_identifiers = { ipi, isni };

          if (!ipi) {
            report.gaps.push({
              type: 'IDENTITY_GAP',
              severity: 'MEDIUM',
              message: 'No IPI number on record for the primary artist — Rights Administrator / neighboring rights claim may fail.',
            });
            if (report.status === 'GREEN') report.status = 'YELLOW';
          }
        }
      } catch { /* continue */ }
    }

    // ── LISTEN STATS + REVENUE ESTIMATE ────────────────────────────
    let listenStats: any = null;
    if (mbRecording?.mbid) {
      try {
        const lbRes = await fetch(`${LB_BASE}/popularity/recording/${mbRecording.mbid}`, {
          headers: { 'User-Agent': 'TrapRoyaltiesPro/1.0' },
        });
        if (lbRes.ok) {
          const lbData = await lbRes.json();
          listenStats = {
            total_listens: lbData.total_listen_count ?? 0,
            unique_listeners: lbData.total_user_count ?? 0,
          };
          report.details.listen_stats = listenStats;
        }
      } catch { /* bonus */ }
    }

    // ── ENRICHMENT: ACRCloud (skip if already ran as fallback above) ─
    const acrToken = process.env.ACRCLOUD_TOKEN;
    if (acrToken && !acrFallback) {
      try {
        const acrRes = await fetch(
          `https://eu-api-v2.acrcloud.com/api/external-metadata/tracks?isrc=${rawISRC}&include_works=1&platforms=spotify,deezer,youtube,applemusic`,
          {
            headers: {
              Authorization: acrToken.startsWith('Bearer ') ? acrToken : `Bearer ${acrToken}`,
            },
            signal: AbortSignal.timeout(8_000),
          }
        );
        if (acrRes.ok) {
          const acrJson = await acrRes.json();
          const acrTrack = acrJson.data?.[0];
          if (acrTrack) {
            const ext = acrTrack.external_metadata ?? {};
            const acrWork = acrTrack.works?.[0];
            const acrContribsWithIpi = (acrWork?.contributors ?? []).filter((c: any) => c.ipi);

            report.details.acr_enriched = {
              name: acrTrack.name,
              artists: (acrTrack.artists ?? []).map((a: any) => a.name),
              album: {
                title: acrTrack.album?.title ?? null,
                label: acrTrack.album?.label ?? null,
                cover: acrTrack.album?.covers?.medium ?? acrTrack.album?.cover ?? null,
              },
              iswc: acrWork?.iswc ?? null,
              contributors: (acrWork?.contributors ?? []).map((c: any) => ({
                name: c.name,
                ipi: c.ipi ?? null,
                roles: c.roles ?? [],
              })),
              platforms: {
                spotify:    ext.spotify?.[0]?.link    ?? null,
                applemusic: ext.applemusic?.[0]?.link ?? null,
                youtube:    ext.youtube?.[0]?.link    ?? null,
                deezer:     ext.deezer?.[0]?.link     ?? null,
              },
            };

            // If ACRCloud confirms ISWC that MB was missing → downgrade ISWC_GAP
            const iswcGapIdx = report.gaps.findIndex(g => g.type === 'ISWC_GAP');
            if (iswcGapIdx !== -1 && acrWork?.iswc) {
              report.gaps[iswcGapIdx] = {
                type: 'ISWC_GAP',
                severity: 'MEDIUM',
                message: `ISWC confirmed via ACRCloud (${acrWork.iswc}) — not yet linked in MusicBrainz. Register to complete the publishing chain.`,
              };
            }

            // If ACRCloud has contributors with IPI → downgrade PERCENTAGE_GAP
            if (acrContribsWithIpi.length > 0) {
              const pctGapIdx = report.gaps.findIndex(g => g.type === 'PERCENTAGE_GAP');
              if (pctGapIdx !== -1) {
                report.gaps[pctGapIdx] = {
                  type: 'PERCENTAGE_GAP',
                  severity: 'MEDIUM',
                  message: `ACRCloud confirms ${acrContribsWithIpi.length} contributor(s) with IPI — verify split registration is complete at your PRO.`,
                };
              }
            }
          }
        }
      } catch { /* ACRCloud enrichment is optional */ }
    }

    // Re-evaluate status after ACRCloud enrichment (CRITICAL may no longer apply)
    if (!report.gaps.some(g => g.severity === 'CRITICAL') && report.status === 'RED') {
      report.status = report.gaps.length > 0 ? 'YELLOW' : 'GREEN';
    }

    // Calculate estimated loss
    if (report.gaps.length > 0) {
      const baseRevenue = estimatedRevenue || estimateRevenue(listenStats?.total_listens || 0);
      const gapMultiplier = report.gaps.reduce((sum, g) => {
        if (g.severity === 'CRITICAL') return sum + 0.40;
        if (g.severity === 'HIGH') return sum + 0.25;
        return sum + 0.10;
      }, 0);
      report.estimated_loss = Math.round(baseRevenue * Math.min(gapMultiplier, 1.0) * 100) / 100;
    }

    // Final status escalation: any CRITICAL → RED
    if (report.gaps.some(g => g.severity === 'CRITICAL')) report.status = 'RED';

    return NextResponse.json(report);

  } catch (err) {
    return NextResponse.json({ error: 'Probe failed', details: String(err) }, { status: 500 });
  }
}
