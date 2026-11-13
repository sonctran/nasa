# Assumptions and parameters

**This file is generated from `config/params.yaml` by `python -m planner.write_docs`. Do not edit it by hand.**

Every number the planner uses is listed here, in one of three groups:

1. **Assumption**: a value we chose because no source could be verified. The app labels results that depend on these as **"assumption"** or **"modeled"**.
2. **Owner-set**: a mission-design choice made by Son (the project owner), not a fact about Mars.
3. **Sourced**: a value read from a NASA/USGS/PDS document. The source column quotes where it came from. Some sourced values are lunar or Gale-crater numbers applied to Jezero: their notes say so, and the app labels them **"proxy"** where that applies.

Tobler (1993) and Minetti et al. (2002) were blocked for automated access and were read from PDFs supplied by Son (2026-11-13). The dose-equivalent numbers of Hassler et al. (2014) could not be read and are **not used**. See DECISIONS T27.


## 1. Assumptions (no verified source) (36)

| Parameter | Value | Unit | Reason / note |
|---|---|---|---|
| `grid.analysis_cell_m` | 2.0 | m | SPEC allows 2-5 m. 2 m keeps slope detail (Horn 3x3 = 6 m baseline) and stays fast (2000 x 2000 cells). |
| `grid.web_cell_m` | 10.0 | m | Browser cost grid (400 x 400 = 160,000 cells) so A* in a Web Worker can finish in < 1 s (SPEC 5). Speed is measured in Phase 3. |
| `grid.ortho_display_cell_m` | 1.0 | m | 25 cm orthomosaic averaged 4x4 -> 1 m for the base map (keeps the site small). Sharper 25 cm crops are kept for close-ups. |
| `terrain.roughness_window_m` | 5 | m | Window for detrended RMS relief on the 1 m DTM. Small enough to catch boulder fields and scarps, big enough to average DTM noise. |
| `terrain.roughness_nogo_m` | 0.2 | m RMS | Placeholder, no source; slider in the app. Measured on this DTM: 0.095% of cells exceed 0.2 m and 84% of those are also > 20 deg slope (0.5 m flagged only 0.004%). A 1 m DTM cannot see rocks smaller than a few metres, so roughness mainly marks scarp edges and works best as a soft penalty (Phase 2). |
| `terrain.hillshade_azimuth_deg` | 315 | deg from north | Display only. Standard cartographic light from the north-west. |
| `terrain.hillshade_altitude_deg` | 45 | deg | Display only. |
| `terrain.web_aggregate_percentile` | 90 | percentile | Each 10 m web cell keeps the 90th-percentile slope and roughness of its 25 analysis cells, so a cell that is partly steep still counts as steep (conservative). |
| `human_factors.downhill_energy_credit` | 0.0 | - | Downhill costs the same energy per metre as level ground (no credit, no extra braking cost). Cautious: Minetti et al. (2002) measured walking cost on Earth at its lowest at gradient -0.10 (0.81 J/kg/m vs 1.64 level). |
| `human_factors.pacing_rule` | constant_power | - | Uphill the crew slows down so metabolic power stays at the level-walking rate; never faster than the level pace (also downhill). Checked against Apollo 14 traverse legs in METHODS.md. |
| `human_factors.alt_model_gravity_scaling` | gravity_ratio | - | Alternative model: Mars cost per metre = level cost (352 W / 2 km/h) + (Cw(i) - Cw(0)) x (g_Mars / g_Earth) x moving mass. The extra cost of a grade is mostly lifting/braking body weight, so it is scaled by gravity. |
| `human_factors.carried_kit_kg` | 10.0 | kg | Tools, sample bags and the recovered tubes. No source. |
| `consumables.o2_capacity_kg` | 0.823 | kg usable O2 per suit | No verified Mars-suit tank size. Cross-check: the Apollo -7 PLSS held 'a minimum of 1.340 pounds' (0.608 kg) usable O2, 'ample for a 5-hour EVA at 1200-Btu/hr' (Apollo EMU Operations Handbook CSD-A-789, p.2-89, https://ntrs.nasa.gov/api/citations/19730064704/downloads/19730064704.pdf). (assumption, derived: 8 h x 352 W x 0.0810 kg/MJ. 8 h = xEMU design life ('designed for 8-hour autonomous performance', NASA ICES-2026-126 p.3) and 352 W = xEMU average design rate (BVAD p.135).) |
| `consumables.o2_reserve_fraction` | 0.15 | fraction of capacity | Oxygen that must still be left when the crew gets home, even on the walk-back from the worst point. About 1 h at the design rate. No source. |
| `consumables.battery_draw_w` | 48.4 | W | 387.5 W h spread over the 8 h design life. Constant: fans, pumps and radios do not follow the crew's workload in this model. |
| `sep.shelter_time_limit_min` | 60 | min | During a solar particle event alert the crew must be able to reach the habitat (the only shelter) within this time by the fastest route. No NASA requirement found. Slider in the app. |
| `hazard.slope_caution_deg` | 10 | deg | Hazard index starts rising here and reaches 1 at the 20 deg no-go limit. Half the NASA limit; no source. |
| `hazard.roughness_caution_m` | 0.05 | m RMS | Hazard index starts rising here (about the 75th percentile of the 10 m grid) and reaches 1 at the 0.2 m no-go limit. |
| `route_options.fastest` | [1.0, 0.0, 0.0, 0.0] | weights | Minimum walking time. |
| `route_options.lowest_energy` | [0.0, 1.0, 0.0, 0.0] | weights | Minimum metabolic energy (and oxygen). Under the constant-power pacing rule, walking energy = power x time, so this gives the SAME route as Fastest (shown once as 'Fastest = lowest energy'). |
| `route_options.safest` | [0.05, 0.05, 0.9, 0.0] | weights | Minimum hazard exposure; small time/energy weights break ties and keep every edge cost > 0. |
| `route_options.balanced` | [0.3333, 0.3333, 0.3334, 0.0] | weights | Equal weights. Used for the plan of record and for the stop schedule. |
| `route_options.shortest` | [0.0, 0.0, 0.0, 1.0] | weights | Naive baseline: shortest map distance that avoids no-go cells, ignoring slope and hazard. Shows what the cost model adds. |
| `route_options.pareto_hazard_step` | 0.05 | weight step | Sweep of the hazard weight w_H from 0 to 0.95 (time weight = 1 - w_H) to draw the time-vs-hazard Pareto chart. Energy is not swept separately because it is proportional to walking time in this model. |
| `habitat.pad_size_m` | 110 | m | Neighbourhood (11 x 11 cells of 10 m) used to judge flatness. |
| `schedule.depot_pickup_min` | 50 | min | Pick up, check and stow all 10 tubes (about 5 min each). No source. |
| `schedule.dwell_fine_grained_layered_rock_min` | 45 | min | Describe, photograph, sample. No source. |
| `schedule.dwell_delta_layer_sequence_min` | 30 | min | Describe and photograph the layers. No source. |
| `schedule.dwell_transported_boulders_min` | 20 | min | Photograph and sample boulders. No source. |
| `schedule.budget_fractions` | [0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0] | fraction of EVA limit | Time budgets given to the optimizer; each budget gives one candidate plan for the robust ranking. |
| `montecarlo.runs` | 20000 | runs | SPEC asks for 2,000+. |
| `montecarlo.seed` | 20261114 | - | Fixed so results are reproducible. |
| `montecarlo.speed_sigma` | 0.15 | log-normal sigma | Whole-EVA walking-speed factor (median 1). Apollo 14 leg speeds varied from 0.69 to 5.7 km/h, so real spread is large; no fitted value. |
| `montecarlo.metabolic_sigma` | 0.2 | log-normal sigma | Whole-EVA metabolic-rate factor (median 1). Apollo station-work rates ranged 244-351 kcal/h between crew members in Waligora Table 2. |
| `montecarlo.dwell_sigma` | 0.3 | log-normal sigma | Each stop's work time varies on its own (median 1). Field tasks often run long; no source. |
| `montecarlo.tornado_quantile` | 0.1 | quantile | Tornado bars show each input at its 10th and 90th percentile. |

## 2. Owner-set mission choices (14)

| Parameter | Value | Unit | Reason / note |
|---|---|---|---|
| `mission.site` | Jezero Crater, Three Forks sample depot + delta front | - | Phase 0 interview. AOI ~4 km x 4 km, exact bounds set in Phase 1 from real data. |
| `mission.eva_time_limit` | 6.0 | h | Door to door. The ConOps is for lunar xEVA; we apply the same nominal length on Mars. (owner-set; matches NASA EVA-EXP-0042 Rev B (xEVA System ConOps, 2020) p.37: 'EVAs will be between 4 and 8 hours in length (6+/-2 hours)'. https://ntrs.nasa.gov/api/citations/20205008200/downloads/EVA-EXP-0042%20xEVA%20System%20Con%20Ops%20Rev%20B%20Final%20dtd%2010192020_REF%20DOC.pdf) |
| `mission.crew_size` | 2 | astronauts | EV1 + EV2, walk only (no rover-assisted option). |
| `mission.mobility_mode` | walk_only | - | Phase 0 interview. Buddy-rule separation distance set in Phase 2. |
| `tasks.sample_tube_pickup` | required | - | Retrieving cached tubes at Three Forks is a must-do task, not scored. |
| `science_value.fine_grained_layered_rock` | 10 | points | Best place to look for signs of ancient life. Stops chosen from real data in Phase 1-2. |
| `science_value.delta_layer_sequence` | 6 | points | Shows how the old lake and river changed over time. |
| `science_value.transported_boulders` | 4 | points | Rocks carried in by ancient rivers from outside the crater. |
| `aoi.west_m` | -2000 | m (east of anchor) | AOI 4 km x 4 km (SPEC 5). Depot sits at local (2000, 1700). Includes the delta front, the delta-top climb (sols 708-760) and flat crater floor to the east. |
| `aoi.east_m` | 2000 | m (east of anchor) | See west_m. |
| `aoi.south_m` | -1700 | m (north of anchor) | See west_m. |
| `aoi.north_m` | 2300 | m (north of anchor) | See west_m. Shifted north so the delta front and delta-top route fit. |
| `habitat.distance_from_depot_m` | [900, 1100] | m | Mission story (S3): habitat on the flat crater floor. Rule: the cell east of the depot, 900-1100 m away, whose 100 m x 100 m neighbourhood has the lowest maximum slope (DECISIONS T29). |
| `schedule.robust_p_on_time` | 0.95 | probability | Son's 'Robust plan' upgrade (S4): the recommended plan must get home within the EVA limit in at least 95% of Monte Carlo runs. |

## 3. Sourced values (21)

| Parameter | Value | Unit | Source | Note |
|---|---|---|---|---|
| `aoi.anchor_lon` | 77.408207 | deg E (planetocentric) | PDS mars2020_sample_depot_three_forks, miscellaneous/sample_metadata/sample_tube_locations.csv | Mean rover longitude over the 10 tube-drop events. Projection centre and depot reference point. |
| `aoi.anchor_lat` | 18.452829 | deg N (planetocentric) | PDS mars2020_sample_depot_three_forks, miscellaneous/sample_metadata/sample_tube_locations.csv | Mean rover latitude over the 10 tube-drop events. |
| `grid.dtm_cell_m` | 1.0 | m | USGS HiRISE DTM mosaic posting (1 m) | DTM is reprojected to the local grid at its own 1 m posting; roughness is computed here. |
| `terrain.slope_nogo_deg` | 20 | deg | NASA EVA-EXP-0042 Rev B (xEVA System ConOps, 2020) p.39: 'Walking up/down/across a slope of up to 20 deg [Note: Apollo 15 traversed on slopes of ~17 deg]'. https://ntrs.nasa.gov/api/citations/20205008200/downloads/EVA-EXP-0042%20xEVA%20System%20Con%20Ops%20Rev%20B%20Final%20dtd%2010192020_REF%20DOC.pdf | A lunar suit capability, applied to Mars (heavier suit weight there, so it may be optimistic). Applied to the P90 slope of each 10 m cell. Slider in the app. |
| `human_factors.level_speed_mps` | 0.5556 | m/s | NASA EVA-EXP-0042 Rev B (xEVA ConOps) p.40: 'Traverses assume an ~2 km/hr walking pace over relatively level regolith'. https://ntrs.nasa.gov/api/citations/20205008200/downloads/EVA-EXP-0042%20xEVA%20System%20Con%20Ops%20Rev%20B%20Final%20dtd%2010192020_REF%20DOC.pdf | 2 km/h. Lunar planning pace, applied to Mars (assumption). Apollo 14 EVA-2 measured 2.47 km/h overall (Waligora & Horrigan 1975, Table 4), so 2 km/h is cautious. |
| `human_factors.level_metabolic_rate_w` | 352 | W | NASA/TP-2015-218570 Rev 2 (BVAD, 2022) p.135: 'The xEMU average design metabolic rate is 1.27 MJ/CM-h (352 W)'. https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | Used as the level-walking rate at 2 km/h. Cross-check: Apollo 14 EVA-2 walking traverses averaged 354 W (CDR 1233, LMP 1318 x 10^3 J/h; Waligora & Horrigan 1975 Table 4). NASA reports Mars gravity needs higher rates than lunar (no numbers readable), so this may be low: the Monte Carlo spread covers part of that. |
| `human_factors.uphill_muscle_efficiency` | 0.243 | - | Minetti, Moia, Roi, Susta & Ferretti (2002), J Appl Physiol 93:1039-1046, doi:10.1152/japplphysiol.01177.2001, p.1041: mechanical efficiency 'For uphill slopes steeper than +0.15 ... 0.243 +/- 0.012 ... for walking'. Read from the PDF supplied by Son, 2026-11-13. | Share of metabolic energy that becomes lifting work when walking uphill. Extra uphill energy = mass x g_Mars x height gained / efficiency. Measured on Earth, unsuited, for slopes > +0.15; we apply it at all uphill grades on Mars (assumption). |
| `human_factors.tobler_hiking_function` | [6.0, 3.5, 0.05] | km/h, -, -  (W = a * exp(-b * /S + c/), S = dh/dx) | Tobler, W. (1993), 'Three presentations on geographical analysis and modeling', NCGIA Technical Report 93-1, p.4 (Figure II): 'W = 6 exp( -3.5 * abs(S + 0.05)) ... S is dh/dx = slope = tan(theta) ... velocity is given in km/hr'. Read from the PDF supplied by Son, 2026-11-13. | Earth, unsuited, on footpaths. Used ONLY in the alternative model check (shape of speed vs grade, rescaled to the 2 km/h suited level pace). |
| `human_factors.minetti_walk_coeffs` | [280.5, -58.7, -76.8, 51.9, 19.6, 2.5] | J kg^-1 m^-1, coefficients of i^5 ... i^0 (i = gradient) | Minetti et al. (2002), J Appl Physiol 93:1039-1046, Fig. 1 caption p.1041: 'Cw_i = 280.5i^5 - 58.7i^4 - 76.8i^3 + 51.9i^2 + 19.6i + 2.5 (R^2 = 0.999)'. Read from the PDF supplied by Son, 2026-11-13. | Earth, unsuited, treadmill, gradients -0.45 to +0.45. Used ONLY in the alternative model check. |
| `human_factors.mars_gravity_mps2` | 3.71 | m/s^2 | BVAD (NASA/TP-2015-218570 Rev 2) Table 4-66, p.132. https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | 0.379 of Earth. |
| `human_factors.earth_gravity_mps2` | 9.798 | m/s^2 | BVAD Table 4-66, p.132. https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | Only used for weight comparisons. |
| `human_factors.moon_gravity_mps2` | 1.62 | m/s^2 | BVAD Table 4-66, p.132. https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | Only used to check the walking model against Apollo 14 data. |
| `human_factors.crew_body_mass_kg` | 82.0 | kg | BVAD Table 4-68, p.132 (human mass used in NASA's suit-weight table). https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | One crew member. |
| `human_factors.suit_mass_kg` | 90.7 | kg | BVAD Table 4-67, p.132: 'Apollo Program Spacesuit, A7LB 90.7 kg' (with -7 PLSS). https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | No Mars suit mass is published that we could verify; we use the Apollo A7LB system, the suit flown for 8 h lunar EVAs. BVAD Table 4-68 gives this suit + human on Mars as 172.7 kg, 643 N. |
| `work_metabolic_rate.science_stop_w` | 283 | W | Waligora & Horrigan (1975), 'Metabolism and heat dissipation during Apollo EVA periods', Table 2, mean 'Geological station activity' 1018 x 10^3 J/hr (244 kcal/hr) over 52.47 h. https://ntrs.nasa.gov/api/citations/19760005584/downloads/19760005584.pdf | Apollo 11-17 lunar data, used for work at science stops on Mars (assumption that the work is similar). |
| `work_metabolic_rate.depot_pickup_w` | 312 | W | Waligora & Horrigan (1975) Table 2, mean 'Overhead' 1123 x 10^3 J/hr (270 kcal/hr); overhead includes 'stowage of lunar samples'. https://ntrs.nasa.gov/api/citations/19760005584/downloads/19760005584.pdf | Used for picking up and stowing the 10 depot tubes. |
| `consumables.o2_kg_per_mj` | 0.081 | kg O2 per MJ metabolic | Derived from BVAD Table 4-70, p.135: oxygen consumption 0.086 kg/CM-h at 1.062 MJ/CM-h (295 W, respiratory quotient 0.90). 0.086 / 1.062 = 0.0810. https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf | Our arithmetic on NASA numbers. Leakage is not modelled. |
| `consumables.battery_capacity_wh` | 387.5 | W h | Apollo EMU Operations Handbook CSD-A-789 Rev V: 'The minimum capacity of the -7 PLSS power supply is 387.5 watt-hours'. https://ntrs.nasa.gov/api/citations/19730064704/downloads/19730064704.pdf | Apollo backpack battery, used as a stand-in. |
| `walkback.rule` | walk_home_on_remaining_consumables | - | Apollo rule (Bellcomm, 1969, p.5): 'In event of an LRV failure, the crewmen shall be able to walk back to the LM on the consumables remaining in the PLSS.' https://ntrs.nasa.gov/api/citations/19700009560/downloads/19700009560.pdf | Checked at every 10 m cell of the route: O2 left minus O2 to walk home by the fastest route must stay above the reserve, and elapsed time plus walk-home time must stay within the EVA limit. |
| `sep.background_dose_rate_ugy_per_day` | 210 | microgray per day (absorbed dose) | NASA PIA17600 'Radiation Measurements on Mars' (2013): galactic cosmic rays 'contribute a slowly varying dose rate of about 210 micrograys per day' (Curiosity RAD, Aug 2012 - Jun 2013). https://science.nasa.gov/photojournal/radiation-measurements-on-mars/ | PROXY: measured at Gale crater, not Jezero. Absorbed dose only (the dose-equivalent figure could not be verified). |
| `sep.may2024_event_dose_ugy` | 8100 | microgray (event total) | NASA, 'What NASA Is Learning from the Biggest Geomagnetic Storm in 20 Years' (2025): 'If astronauts had been there, they would have received a radiation dose of 8,100 micrograys'. https://science.nasa.gov/science-research/heliophysics/what-nasa-is-learning-from-the-biggest-geomagnetic-storm-in-20-years/ | PROXY (Gale crater). Event of 20 May 2024 (NASA PIA26302). Shown as context in the SEP replay; the time profile is not known, so no in-EVA SEP dose is modelled. |

Source file: `config/params.yaml`. Science-stop sites and their quotes: `config/stops.yaml`.
