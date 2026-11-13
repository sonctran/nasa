# Data sources

Every number shown in the app traces to a source in this table, or to `docs/ASSUMPTIONS.md` (Phase 2).
All files were fetched on **2026-11-13** (UTC) by `python -m pipeline.download`; exact timestamps are in `data/raw/fetch_log.json`. Nothing raw is committed. Re-running the pipeline downloads it again.

**Labels used in the app:** **real** = measured data, shown as is · **derived** = computed from real data with a stated method · **assumption** = uses a threshold we chose (see `config/params.yaml`) · **proxy** = coarse or indirect stand-in, qualitative only.

## Study area and grid

- **AOI:** 4 km × 4 km, from 77.3726° to 77.4438° E and 18.4241° to 18.4916° N (planetocentric). It holds the Three Forks depot, the delta front and the flat crater floor to the east.
- **Anchor / projection centre:** 77.408207° E, 18.452829° N. This is the mean rover position over the 10 Three Forks tube drops.
- **Local grid:** equirectangular on the Mars 2000 sphere (R = 3,396,190 m), with the standard parallel and central meridian at the anchor. The axes are x east and y north, in metres, with the origin at the AOI's south-west corner. The depot is at (2000, 1700).
  *Why reproject:* the USGS mosaics use standard parallel 0°. At Jezero (18.45° N), 1 projected metre east-west there is only 0.949 ground metres, which would distort slopes. On the local grid, 1 m = 1 ground metre (checked by a test to < 0.03 %).
- **Grids:** DTM 1 m (4000 × 4000) → analysis grid 2 m (2000 × 2000) → browser cost grid 10 m (400 × 400).

## Sources

| Layer | Provider | Exact URL fetched | Resolution | Accessed | Credit line | Processing |
|---|---|---|---|---|---|---|
| **Elevation (DTM)** · real | USGS Astrogeology. Fergason, R., Galuszka, D., Hare, T. (2020). *HiRISE Digital Terrain Model Mosaic for Mars 2020 Terrain Relative Navigation*. doi:[10.5066/P9REJ9JN](https://doi.org/10.5066/P9REJ9JN) | `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif` (+ `.xml` metadata) | 1 m posting | 2026-11-13 | DTM mosaic: Fergason, Galuszka & Hare 2020, USGS. HiRISE data: NASA/JPL-Caltech/University of Arizona | Windowed HTTP read of the AOI + 100 m margin (source pixels cols 8768-13195, rows 10432-14632; 40 s). The 1.8 GB file is never downloaded whole. Bilinear reprojection to the 1 m local grid, then 2 × 2 mean to 2 m. |
| Slope · derived | from DTM | - | 2 m | - | as DTM | Horn (1981) 3 × 3 method (same as GDAL `gdaldem slope`). Tested on synthetic tilted planes (0-60°): exact to 1e-6°. |
| Roughness · derived | from DTM | - | 2 m | - | as DTM | Detrended RMS relief: residual = z − 5 m window mean; roughness = √(window mean of residual²), on the 1 m DTM, then averaged to 2 m. Zero on any plane (tested). |
| Hillshade · derived | from DTM | - | 2 m | - | as DTM | Lambertian; sun azimuth 315°, altitude 45° (display only). |
| No-go mask · assumption | from slope + roughness | - | 2 m | - | as DTM | slope > 20° OR roughness > 0.2 m OR no data. Both limits are **placeholders** (`params.yaml`), and the app shows them as sliders. |
| **Base image (orthomosaic)** · real | USGS Astrogeology. Fergason, Galuszka, Hare (2020). *HiRISE Orthorectified Image Mosaic for Mars 2020 Surface Operations*. doi:[10.5066/P9QJDP48](https://doi.org/10.5066/P9QJDP48) | `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_007_orthoMosaic_25cm_Ortho_blend120.tif` (+ `.xml`) | 25 cm source → 1 m display; 25 cm depot close-up | 2026-11-13 | Orthomosaic: Fergason, Galuszka & Hare 2020, USGS. HiRISE data: NASA/JPL-Caltech/University of Arizona | Windowed read (16404 × 16400 source px, 55 s). 4 × 4 block mean → 1 m. Reprojected from orthographic (centre 18.4663° N, 77.4298° E) to the local grid. Linear 0.5-99.5 % display stretch. A 100 m × 100 m crop around the depot is kept at 25 cm. |
| Elevation check (CTX DTM) · real | USGS Astrogeology. *Context Camera DTM Mosaic for Mars 2020 TRN*. doi:[10.5066/P906QQT8](https://doi.org/10.5066/P906QQT8) | `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif` | 20 m | 2026-11-13 | CTX DTM mosaic: USGS. CTX data: NASA/JPL-Caltech/MSSS | Used only as an independent cross-check of the HiRISE DTM (below). |
| **Thermal (THEMIS day / night IR)** · proxy | NASA Mars Trek WMTS (JPL); THEMIS on Mars Odyssey (ASU) | `https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/9/203/732.png` and the same path with `THEMIS_NightIR_...` | ~81 m/px at zoom 9 (layer is nominally 100 m) | 2026-11-13 | THEMIS IR mosaic: NASA/JPL-Caltech/Arizona State University, via NASA Mars Trek | Layer ID and tile matrix read from the layer's `WMTSCapabilities.xml`, not guessed. One 256 px tile covers the AOI. Georeferenced from the tile matrix, then bilinear to 20 m. **Qualitative brightness, not calibrated temperature or thermal inertia.** |
| **Rover traverse** · real | NASA/JPL-Caltech, Mars 2020 MMGIS | `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json` | rover-localised | 2026-11-13 | Perseverance traverse: NASA/JPL-Caltech | Lon/lat (CRS84) → local metres, clipped to the AOI: 130 segments. |
| **Rover waypoints** · real | NASA/JPL-Caltech, Mars 2020 MMGIS | `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json` | rover-localised | 2026-11-13 | Perseverance waypoints: NASA/JPL-Caltech | 181 of 708 waypoints are inside the AOI (sols 199-763). Our DTM is sampled at each one (check below). |
| **Three Forks depot** · real | NASA PDS Geosciences Node, bundle `urn:nasa:pds:mars2020_sample_depot_three_forks` | `https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_sample_depot_three_forks/miscellaneous/sample_metadata/sample_tube_locations.csv` (+ `.xml` label, `sample_tube_event_sols.csv`, `sample_tube_identifiers.csv`, `../depot/campaign_sols.csv`) | rover-localised | 2026-11-13 | Three Forks depot data: NASA PDS Geosciences Node | 10 tubes, dropped sols 653-690. **The positions are the rover's location at each drop, not the tube's own position** (PDS label: "Locations of the rover during sample tube drop events"). Labeled so in the app. |
| **Rover photos ("what you'll see")** · real | NASA/JPL-Caltech, Mars 2020 raw images | API: `https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&sol=<sol>`. Each photo's own URL is in `site/assets/data/vectors.json` | 800 px browse JPEGs | 2026-11-13 | Per image, from the API: Mastcam-Z "NASA/JPL-Caltech/ASU"; Navcam "NASA/JPL-Caltech" | One photo per rover site in the AOI (22 of 24 sites). Rule: same site number, full frame ≥ 1200 × 900, colour Mastcam-Z first, then Navcam, mast elevation −20° to +3°, closest to −8°. **Raw, uncalibrated** frames (the Navcam ones look greenish). |
| **Solar particle events** · proxy | NASA CCMC DONKI via api.nasa.gov | `https://api.nasa.gov/DONKI/SEP?startDate=2024-05-01&endDate=2024-06-29` (DEMO_KEY) | event list | 2026-11-13 | Space weather events: NASA CCMC DONKI | Cached as is in `site/assets/data/donki_sep_2024-05-01_2024-06-29.json` (27 events). These are **near-Earth detections, not measurements at Mars**. Used only for the SEP-alert replay (Phase 2-3). |

## Phase 2 sources (planning engine)

Read on 2026-11-13. Each value used is quoted in `config/params.yaml` / `config/stops.yaml` and listed in `docs/ASSUMPTIONS.md`.

| Used for | Source | Exact URL read | What we took |
|---|---|---|---|
| **Science stop locations** · real | NASA PDS Geosciences Node, *Mars 2020 Initial Reports* Vol. 2 (Delta Front) and Vol. 3 (Upper Fan), bundle `urn:nasa:pds:mars2020_sample_dossier` | `https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_sample_dossier/initial_reports/initial_reports_volume2.pdf` (and `..._volume3.pdf`) | Core-site latitude, longitude, elevation and lithology text for Skinner Ridge (Swift Run), Wildcat Ridge (Hazeltop), Amalik (Shuyak), Hidden Harbor (Kukaklek), Berea (Melyn). Our 1 m DTM matches the published elevations within 0.03-0.28 m. |
| Boulder-field stop · real | NASA Science blog, "Look at All Those Boulders!" (2023-04-17), image sol 754 | `https://science.nasa.gov/blog/look-at-all-those-boulders/` | The quote that the boulders were "likely sourced from outside of Jezero crater". Position = rover waypoint on sol 754 (MMGIS). |
| Slope limit, walking pace, EVA length | NASA EVA-EXP-0042 Rev B, *Exploration EVA System Concept of Operations* (2020), NTRS 20205008200 | `https://ntrs.nasa.gov/api/citations/20205008200/downloads/EVA-EXP-0042%20xEVA%20System%20Con%20Ops%20Rev%20B%20Final%20dtd%2010192020_REF%20DOC.pdf` | "slope of up to 20°" (p.39); "~2 km/hr walking pace" (p.40); "6±2 hours" (p.37) |
| Metabolic rates, O2 per MJ, gravity, suit masses | NASA/TP-2015-218570 Rev 2, *Life Support Baseline Values and Assumptions Document* (BVAD, 2022), NTRS 20210024855 | `https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf` | xEMU 352 W (p.135); Table 4-70 O2 0.086 kg per 1.062 MJ; Table 4-66 gravity; Tables 4-67/4-68 masses |
| Apollo metabolic data | Waligora & Horrigan (1975), "Metabolism and heat dissipation during Apollo EVA periods", NTRS 19760005584 | `https://ntrs.nasa.gov/api/citations/19760005584/downloads/19760005584.pdf` | Table 2 means (geology 283 W, overhead 312 W); Table 4 Apollo 14 traverses (`config/apollo14_table4.csv`) |
| Battery, O2 cross-check | *Apollo Operations Handbook, Extravehicular Mobility Unit*, CSD-A-789-(1) Rev V, NTRS 19730064704 | `https://ntrs.nasa.gov/api/citations/19730064704/downloads/19730064704.pdf` | 387.5 Wh battery; 1.340 lb usable O2 |
| Walkback rule | Bellcomm (1969), NTRS 19700009560 | `https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf` | "shall be able to walk back to the LM on the consumables remaining" |
| 8 h suit design life | Ogilvie et al., "Mars Portable Life Support System Status and Plan", ICES-2026-126, NTRS 20260003024 | `https://ntrs.nasa.gov/api/citations/20260003024/downloads/Final_ICES2026_Mars_PLSS_Plan.pdf` | xEMU "designed for 8-hour autonomous performance" |
| **Radiation baseline** · proxy | NASA PIA17600, "Radiation Measurements on Mars" (2013) | `https://science.nasa.gov/photojournal/radiation-measurements-on-mars/` | "about 210 micrograys per day" (Curiosity RAD, Gale, Aug 2012 - Jun 2013), absorbed dose |
| **May 2024 solar event** · proxy | NASA Science, "What NASA Is Learning from the Biggest Geomagnetic Storm in 20 Years" (2025) and PIA26302 | `https://science.nasa.gov/science-research/heliophysics/what-nasa-is-learning-from-the-biggest-geomagnetic-storm-in-20-years/` | "8,100 micrograys" event dose at Gale; event date 20 May 2024 (sol 4190) |

### Tried and not usable (bot checks): not used anywhere
- Tobler (1993) hiking function (escholarship.org), Minetti et al. (2002) *J Appl Physiol* 93:1039 (journals.physiology.org), Hassler et al. (2014) *Science* 343 (science.org). The ADS and PubMed copies show captchas. The two dose-equivalent figures seen only in search snippets are **not** used.
- DONKI SEP for 15-25 May 2024: api.nasa.gov returned HTTP 429 (DEMO_KEY rate limit), and the kauai mirror reset the connection. The cached May-June 2024 file has no 20 May entry.

### Not yet fetched (planned)
- **Atmosphere** (ESA/LMD Mars Climate Database). Reachable in Phase 0; not used yet. Cut item #2.
- **Geology / spectral layer.** Cut item #1, not attempted.

## Cross-checks on the elevation data (from `data/processed/checks.json`)

| Check | Result | What it means |
|---|---|---|
| Our DTM minus rover elevation at 181 waypoints | mean +0.002 m, RMS **0.059 m**, worst 0.35 m | Our crop, reprojection and lon/lat → grid conversion put every point in the right place. A shift of even a few metres on these slopes would show as decimetre-to-metre errors. **Not an independent accuracy test:** rover positions are localised against orbital maps, very likely this same DTM (inference, not checked). |
| Our DTM minus rover elevation at the 10 depot drops | mean +0.004 m, RMS 0.015 m | Same as above, at the depot. |
| HiRISE (2 m, averaged to 20 m) minus CTX 20 m DTM | mean −1.33 m, median −1.30 m, std 3.91 m (40,000 cells) | Two independent stereo DTMs agree within a few metres. USGS reports a median offset of ~0.4 m over the whole mosaic, with CTX above HiRISE. Our area shows the same sign but a larger offset (1.3 m). |
| USGS stated accuracy (FGDC metadata `.xml`) | HiRISE orthoimages co-registered to better than 1.1 m (most pairs, 99th percentile) and better than 3 m (all pairs). HiRISE vs CTX median vertical offset ~0.4 m. | Quoted from the USGS metadata. These are relative/registration figures, not absolute accuracy. |

## Limits worth knowing (summary; full text in METHODS.md, Phase 2)
- The DTM's real detail is coarser than its 1 m posting, so rocks smaller than a few metres are invisible. "Roughness" here mainly marks scarp edges and broken ground.
- Mosaic seams (the "blend40" in the file name) can create small artificial steps. None were checked in Phase 1.
- THEMIS is ~81 m per pixel: about 50 pixels across the whole AOI. Use it as broad context only.
