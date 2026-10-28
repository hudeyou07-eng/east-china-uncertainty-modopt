# Experiment Tracker (English)

> Snapshot **2026-10-28**. Companion to `EXPERIMENT_TRACKER.md` (Chinese, with the full derivation
> narrative). This file is the **run-level ledger only**: every pre-registered run, its final status,
> and the artifact that backs it.

**All 46 pre-registered runs are closed: 42 `DONE` / 4 `DONE-conditional` / 0 `PARTIAL` / 0 `TODO`.**

## Status and evidence vocabulary

Status and evidence class are **orthogonal**: `DONE` only means "the run executed and its artifact
is on disk", not "the number may be quoted in the paper".

| Status | Meaning |
|---|---|
| `DONE` | Pre-registered question answered by a resolvable artifact. |
| `DONE-conditional` | Conclusion final, but carries a data-boundary condition that a re-run cannot remove. Must be quoted together with its disclosure. |
| `PARTIAL` | Produced, but a pre-registered condition is unmet and still fixable. |
| `TODO` | Not executed. |
| `SUPERSEDED` | Replaced by a later batch; archive only. |

| Evidence | Meaning | Usable in paper |
|---|---|---|
| `formal` | Full protocol (5 folds × 20 repeats, or full contract). | Yes |
| `formal_conditional` | Full protocol + declared data boundary. | Yes, with disclosure |
| `sensitivity` | One-factor sweep; direction usable, absolute level limited. | Direction/ranking only |
| `structural` | Mechanism diagnostics / audits. | Interpretation only |
| `smoke` | Plumbing validation. | No |

`metrics.json.evidence_status` is **not** a reliable classifier (it has 6 different values across the
44 output directories, including `None` and missing). The class below is an editorial judgement,
recorded per run, and can be reviewed line by line.

## Run ledger

| Run ID | Milestone | Purpose | Variant | Split / scope | Primary metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R000 | M0 | environment check | dependency/version | local | imports, solver availability | MUST | DONE | `python -m unittest discover -s tests` → **69 tests OK** (2026-10-28); HiGHS solver available; no GPU |
| R001 | M0 | raw data audit | provenance/units/missing | all raw files | audit errors/warnings | MUST | DONE | 7 regions, 14 groups, **882 cells**; **294** truth-eligible observations; duplicate keys and non-positive values are hard failures |
| R002 | M0 | food-group freeze | ontology/crosswalk | all groups | included K, rank, coverage | MUST | DONE | Ontology frozen at `onto-v1.0.0`. Contract scope **K=4** (G02/G05/G06/G08); decision scope **`k6_price` K=6** (+G04 +G07), 6 provinces (Shanghai out: no G07). Contract gates **7/7 PASS**. Cite `outputs/R002_group_freeze_20261027_232440` (panel v3, `group_prices` hash `3b7ae42d…` matches disk); `outputs/R002_group_freeze_20261027_150751` is the **v1 (G06-unfixed)** rebuild — archive only, its gate report must not be cited |
| R003 | M0 | deterministic toy | known LP solution | synthetic toy | objective, feasibility | MUST | DONE | `tests/test_lp_fixture.py`, **5 hand-checkable LP tests**: interior optimum (3,2)/cost 9, two active constraints, upper-bound-tight (2.5,3)/cost 11.5, infeasible must return `success=False`, `use_chance_constraint=False` pinned as "no nutrition constraints" semantics |
| R004 | M0 | chance MILP toy | joint indicator | synthetic toy | feasibility, z count | MUST | DONE | Optimal; indicator count respects the epsilon budget |
| R005 | M0 | reproducibility | same seed twice | synthetic toy | result hash | MUST | DONE | seed=7 / 20 scenarios run twice → sha256 of `q` and `objective` both `ab9e5ed14ce2ad36`; objective 0.131221215416, q_sum 69.713256651395 |
| R006 | M0 | invalid input | negative/unit/missing coeff | synthetic bad fixtures | explicit failure | MUST | DONE | Invalid bounds and non-finite coefficients fail loudly (no silent fallback) |
| R100 | M1 | price MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | `outputs/B1_formal_withmice_20261023_124906` (1200 rows, 5 folds × 20 repeats, 0 duplicate rows) |
| R101 | M1 | price year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | Same batch; `mask_type=consecutive_years` |
| R102 | M1 | price province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | Same batch; MICE collapses (sMAE **1.182**, cov95 **0.733**). **Correction:** `interp` and `group_mean` are cell-wise identical under this geometry (1200/1200, diff < 1e-9), so the under-coverage is the group-mean's, not interpolation's |
| R103 | M1 | consumption MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | `outputs/R103_105_consumption_formal_20261026_174725`. single_cell n=1300: sMAE MICE **0.036** < interp 0.047 < group_mean 0.138 < hierarchical_rw 0.147, but **calibration error is lowest for hierarchical_rw (0.009)**. Panel has zero missingness — this is a recoverability test, not a real missingness mechanism |
| R104 | M1 | consumption year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | Same batch; sMAE interp 0.056 ≈ MICE 0.059; calibration error hierarchical_rw **0.034** lowest (slope 0.822, cov50 0.590) |
| R105 | M1 | consumption province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | DONE | Same batch; **MICE collapses** (sMAE **1.000**, cov95 **0.079**); group_mean cov95 0.918 / hierarchical_rw 0.900 closest to nominal |
| R106 | M1 | interval calibration | main | aggregate | coverage-width curve | MUST | DONE | `scripts/coverage_curve.py` recomputes from `cell_predictions.csv` (no re-run). hierarchical_rw lowest calibration error across all three geometries (0.054 / 0.037 / 0.059); coverage slope < 1 everywhere (intervals too wide) |
| R107 | M1 | interaction gate | main ± region×group | all masks | paired error/coverage | NICE | DONE | `outputs/R107_interaction_gate`. "Both improve" does **not** hold: `ir10_k1` improves on consecutive_years and single_cell but degrades slightly on province_group → strict gate fails |
| R108 | M1 | MAR sensitivity | main | all masks | calibration | MUST | DONE | `outputs/R108_109_price_formal_20261026_175443` (5493 s). **All 12 (mask × method) bias slopes are negative** (−0.188 to −0.991); main method −0.455 on single_cell; Q5 understated by 8.66 CNY/kg (~11%). **Good cov95 ≠ unbiased** |
| R109 | M1 | MNAR shift | delta grid | blocks | error/coverage | MUST | DONE | Same batch. At δ=0 main method cov95 0.940/0.955/0.954; δ=+0.5 → 0.925–0.937; δ=−0.5 → 0.955–0.980. Main method is rank 1 in all 9 (mask × δ) cells |
| R200 | M2 | deterministic baseline | D0 mean-fill | 100 protocol cells × 6 provinces | feasibility, flips, p95 regret | MUST | DONE-conditional | EAR `\|Δq\|` exactly **0.000** (≡ D1 ≡ D3); RNI change rate **0.460** — this number is a **binary-switch readout**, the province list must not be cited. Batches `R200_203_b2_formal_20261027_222841` (EAR) / `_224315` (RNI), 2400 rows each. Release condition: the three disclosures in `EXPERIMENT_TRACKER.md` §"R200–R203 的定稿条件" |
| R201 | M2 | posterior mean | D1 | 100 protocol cells × 6 provinces | feasibility, flips, p95 regret | MUST | DONE-conditional | EAR version is bit-identical across all 100 protocol cells (`\|Δq\|` 0.000); RNI change rate 0.013. Same release condition as R200 |
| R202 | M2 | scenario expected | D2 | 100 protocol cells × 6 provinces | feasibility, flips, p95 regret | MUST | DONE-conditional | The **only** method that differs from the others: `\|Δq\|` 128.65, gap −0.80, flip rate 0.194 (both bases). Red meat driven to 0 — intended semantics of "no nutrition constraint" |
| R203 | M2 | proposed method | D3 | 100 protocol cells × 6 provinces | feasibility, flips, p95 regret | MUST | DONE-conditional | EAR: D3 ≡ D1 (`\|Δq\|` 0.000) — with nutrient coefficients unperturbed the chance constraint degenerates to hard constraints. RNI change rate 0.333, p95 36.41 (Jiangxi 29.03, Fujian 36.41). Same release condition as R200 |
| R300 | M3 | chance deletion | D3→D2 | primary setting | delta metrics | MUST | DONE | `outputs/M3_all_smoke_20261026_181618` (evidence: smoke). D3 feasible(active) **100 %** vs D2 **0 %**; D2 gap −0.715 (violation arbitrage), D3 +0.123. Net effect of the chance constraint: feasibility 0→100 % at the cost of 17 % of instances (Jiangsu) being infeasible |
| R301 | M3 | scenario count | 25/50/100/200/400 | primary setting | stability/runtime | MUST | DONE | Same batch. Feasibility is **constant at 83 % from S=25**, refuting "too few scenarios causes Jiangsu failure"; runtime 0.04→20.15 s. **S=200 is the plateau** |
| R302 | M3 | epsilon | 0/.02/.05/.10 | primary setting | feasibility/regret | MUST | DONE | Same batch. Solve success 56 %→72 %→**83 %→83 %** (saturates after 0.05); flip rate 0.60→0.20; gap 0.190→0.099. Jiangsu needs ε≈0.30 (selenium headroom only 6.0 %) |
| R303 | M3 | objective weights | original/equal | primary setting | direction stability | MUST | DONE | Same batch. Feasibility 83 %/83 %, gap 0.123/0.128, max `\|Δq\|` **18.23 g/day** (Shanghai); Anhui/Zhejiang 0. No result-driven weight selection |
| R304 | M3 | W uncertainty | on/off | primary setting | flips/regret | NICE | DONE | `outputs/R304_weight_uncertainty_20261027_143003`. Dirichlet(κ·w0), 200 draws per province per level. κ=20: mean regret **0.06 %**, flip 1.2 %; κ=5: 0.28 %, 4.3 %. Weights are not the dominant uncertainty source; Zhejiang is the exception (κ=5: 15.0 % regret, 23.5 % flips) |
| R305 | M3 | joint vs marginal | joint/independent z | primary setting | joint feasibility | NICE | DONE | `R305_chance_mode_20261027_142626` + `R305_high_eps_20261027_143744`. Joint violation rate equals ε **exactly** (5/5 grid points); marginal is 1.5–1.8× ε. Jiangsu needs ε=0.30 (joint) / 0.20 (marginal) → root cause is **nutrient headroom, not jointness**. Marginal has 1800 binaries → 117 s at ε=0.30, not tractable |
| R306 | M3 | Big-M diagnostic | tight/global | toy only | gap/runtime | NICE | DONE | `outputs/R306_big_m_20261026_181747`. Self-check first: M span 2.4–2.6×. Solutions bit-identical (`Δq`=0), runtime difference < 2 % → tight Big-M buys nothing at toy scale, kept as a defensive default |
| R307 | M3 | boundary gate | on/off | primary setting | conclusion labels | NICE | DONE | `outputs/R307_gate_20261027_142902`. Relaxing to coverage 0.90 gives K=6: price transmission 0/6→**3/6** (Jiangsu 54.0 g/day); **Shandong becomes hard-feasible** (carbon offset 275.75→39.55); Shanghai drops out (no G07). Common-group shifts 39.5–171.6 g/day |
| R307b | M3 | gate factorial | 2×2: trace × coverage | primary setting | attribution | NICE | DONE | `outputs/R307b_gate_factorial_20261027_145412`. Four scopes A/B/C/D. **G04 fixes Shandong's hard infeasibility; G07 restores price transmission (0/7→3/6)**; neither is caused by K itself (scope D with K=5 is still 0/7) |
| R400 | M4 | Jiangsu scenarios | D3/D1 direction labels | 6 provinces × 3 scenarios (merged batch) | direction labels, agreement | MUST | DONE | **R400/R402–R406 are one batch**: `outputs/R400_406_provinces_20261028_183104`. 15/18 cells solvable (3 EAT cells hard-infeasible: Shandong/Jiangsu/Zhejiang). **Mean agreement 0.956**; 90 group-cells = up 36 / down 49 / neutral 1 / **data-sensitive 4**. Jiangsu agreement **1.000** in all three scenarios |
| R401 | M4 | Shanghai availability (redefined) | data audit, no solve | Shanghai × 12 groups × 9 years | coverage, scope gap | MUST | DONE | **Re-specified by revision `R-2026-10-28-c`.** Shanghai cannot enter `k6_price` (G07 has **0/9** priced years; the wholesale bridge table has 9 categories and **no aquatic**) → moved to a data-availability report: `outputs/R401_shanghai_availability_20261028_180508`. `k4_official` is assemblable (G02 3 yrs / G05 1 yr / G06 7 yrs / G08 3 yrs) but appears **only as an appendix single point**. Also documents a trap: `clean_tables/prices.csv` holds a Shanghai aquatic price of 30.26 CNY/kg (P023) **with no year field** — unusable |
| R402 | M4 | Zhejiang scenarios | D3/D1 direction labels | 3 scenarios | direction labels | MUST | DONE | Same merged batch. Zhejiang: HEAL_base **1.000** / CDG **1.000** / EAT **hard-infeasible** (carbohydrate + thiamine) |
| R403 | M4 | Shandong scenarios | D3/D1 direction labels | 3 scenarios | direction labels | MUST | DONE | Same batch. Shandong: HEAL_base **1.000** / CDG **1.000** / EAT **hard-infeasible** |
| R404 | M4 | Anhui scenarios | D3/D1 direction labels | 3 scenarios | direction labels | MUST | DONE | Same batch. Anhui: HEAL_base **1.000** / CDG **1.000** / **EAT 0.667 (below the 90 % gate)**; the two data-sensitive groups are G07 (+8.17 vs −35.30) and G08 (−39.25 vs +302.47) |
| R405 | M4 | Jiangxi scenarios | D3/D1 direction labels | 3 scenarios | direction labels | MUST | DONE | Same batch. Jiangxi: HEAL_base **1.000** / CDG **1.000** / **EAT 0.667**; data-sensitive groups are again G07 and G08 |
| R406 | M4 | Fujian scenarios | D3/D1 direction labels | 3 scenarios | direction labels | MUST | DONE | Same batch. Fujian: agreement **1.000** in all three scenarios |
| R407 | M4 | leave-one-province-out | D0 pooled price, one province dropped | 6 folds × 5 provinces × 3 scenarios | `max\|Δq\|`, #direction changes | MUST | DONE | `outputs/R407_looro_20261028_183054`. 75 cells all solved; **6 cells flip, all in EAT** (Anhui/Jiangxi/Fujian; folds Shandong/Zhejiang), **339.3–341.7 g/day**, touching G04/G06/G07/G08; the other 69 cells are 0. Pooled price moves 15.7–24.1 % → the perturbation is real, and CDG/HEAL_base simply do not cross a constraint face |
| R408 | M4 | delta sensitivity | δ on multiplicative residual, log domain | δ ∈ {−0.5,0,+0.5} × 6 provinces × 3 scenarios | `max\|Δq\|` vs δ=0 | MUST | DONE | `outputs/R408_delta_20261028_183131` (1.2 min). 45 cells solved (9 EAT cells hard-infeasible). **δ=±0.5 vs δ=0: median `max\|Δq\|` 1.4e-11, max 2.3e-9 g/day** — machine precision. Same mechanism as M2: price enters only the objective, and scaling residual spread does not move the first moment |
| R409 | M4 | boundary grid | low/mid/high/worst | 6 provinces × 4 variants | `max\|Δq\|` vs mid | MUST | DONE | `outputs/R409_bounds_20261028_183421`. 24 cells: **12 solved** (mid 6 + high 6), **`low` 6 cells solver-infeasible** (HiGHS `Status 8: model_status is Infeasible`), **`worst` 6 cells empty box**. `high` moves **43.7 (median) – 92.05 (max) g/day** from `mid`. Boundary variants change the feasible region itself, not the reaction to uncertainty — report separately |
| R500 | M5 | Table 1 | calibration | B1, both panels | table validation | MUST | DONE | Merged with R501–R504 in `outputs/R500_504_paper_artifacts`. `table1_price.csv` / `table1_consumption.csv` / `table1.md`: 3 masks × 4 methods × 8 metrics, read-only from `calibration_summary.csv` |
| R501 | M5 | Table 2 | decision result | B2, both bases | table validation | MUST | DONE | Same batch. `table2_decision.csv` / `table2.md`: 2 bases × 4 methods = 8 rows, primary metric `dq_change_rate`. **`feasible_all` is structurally 0** (calcium unreachable in all 18 cells) → report `feasible_active` only; `gap` is not comparable across panel versions |
| R502 | M5 | Figure 1 | stable/flip | B2/M4 | visual QC | MUST | DONE | Same batch. `figure1_stable_flip.csv` + `figure1.svg` — **English labels**, dependency-free SVG. Three scenarios: CDG 36 / EAT 18 / HEAL_base 36 = 90 group-cells; **all 4 data-sensitive cells are in EAT** |
| R503 | M5 | Figure 2 | regional heatmap | B4 | visual QC | MUST | DONE | Same batch. `figure2_regional_heatmap.csv` + `figure2.svg` — **English labels**. CDG direction-label matrix, **6 decision provinces × 6 groups** (Shanghai is not a decision province, see R401) |
| R504 | M5 | appendix pack | all | all | completeness | NICE | DONE | Same batch. `artifact_manifest.json` (bytes + sha256 per artifact) and `appendix_index.md` (inventory + source runs + reproduce command) |
| R505 | M5 | reproducibility rerun | selected must-runs | clean env | hash/metric tolerance | MUST | DONE | `outputs/R505_reproducibility`. **Automated part PASS**: contract hashes 10/10 zero drift, 13 key run dirs present with `DONE`, unittest green, tracker 15/15. **Clean-environment rerun NOT executed** (needs an out-of-repo clone + fresh venv + network); commands and tolerances are in `RUNBOOK.md` and the report lists it under `not_verified` |

## Progress summary

| Milestone | DONE | DONE-conditional | PARTIAL | TODO | Note |
|---|---|---|---|---|---|
| M0 data audit and freeze | 7 | 0 | 0 | 0 | Complete; includes 5 hand-checkable LP fixtures |
| M1 calibration | 10 | 0 | 0 | 0 | Complete on both panels (price and consumption) |
| M2 decision reliability | 0 | 4 | 0 | 0 | Clean null result, released as `DONE-conditional` |
| M3 sensitivity grid | 9 | 0 | 0 | 0 | R300–R303 are `smoke`-class evidence |
| M4 regional scenarios | 10 | 0 | 0 | 0 | Includes the redefined Shanghai report and three sensitivity blocks |
| M5 figures and delivery | 6 | 0 | 0 | 0 | Figures in English; R505 is automated-only |
| **Total** | **42** | **4** | **0** | **0** | 46 pre-registered runs; 20 `DIAG_*` diagnostics + 1 legacy dir are not counted |

## Artifact index

| run | Directory | Key artifacts | Evidence level |
|---|---|---|---|
| R000 | — (no run dir; `python -m unittest`) | `tests/test_smoke.py`, `tests/test_b2.py` | formal |
| R001 | — (audit folded into this ledger and `EXPERIMENT_PLAN.md`) | `data/processed/model_manifest.json` | formal |
| R002 | `outputs/R002_group_freeze_20261027_232440` | `contract_gate_report.json`, `metrics.json` | formal |
| R003–R006 | — (toy fixtures, no run dir) | `tests/test_lp_fixture.py`, `tests/test_smoke.py` | formal |
| R100–R102, R106 | `outputs/B1_formal_withmice_20261023_124906` | `calibration_summary.csv`, `cell_predictions.csv`, `coverage_curve_summary.csv` | formal |
| R103–R105 | `outputs/R103_105_consumption_formal_20261026_174725` | `calibration_summary.csv`, `cell_predictions.csv` | formal |
| R106 (consumption) | same as above | `coverage_curve_summary.csv`, `coverage_curve_by_fold.csv` | formal |
| R107 | `outputs/R107_interaction_gate` | `interaction_gate.json`, `interaction_gate.csv` | sensitivity |
| R108–R109 | `outputs/R108_109_price_formal_20261026_175443` | `mar_summary.csv`, `mnar_delta_summary.csv`, `mnar_rank_stability.csv` | formal |
| R200–R203 | `outputs/R200_203_b2_formal_20261027_222841` (EAR), `outputs/R200_203_b2_formal_20261027_224315` (RNI) | `b2_results.csv`, `metrics.json`, `protocol_shift.csv` | formal_conditional |
| R300–R303 | `outputs/M3_all_smoke_20261026_181618` | `m3_grid_results.csv`, `m3_grid_summary.csv`, `r303_weight_stability.csv` | smoke |
| R304 | `outputs/R304_weight_uncertainty_20261027_143003` | `weight_uncertainty_summary.csv` | sensitivity |
| R305 | `outputs/R305_chance_mode_20261027_142626`, `outputs/R305_high_eps_20261027_143744` | `chance_mode_summary.csv` | sensitivity |
| R306 | `outputs/R306_big_m_20261026_181747` | `big_m_summary.csv`, `big_m_spread.csv` | structural |
| R307 | `outputs/R307_gate_20261027_142902` | `gate_sensitivity.csv`, `common_group_compare.csv` | sensitivity |
| R307b | `outputs/R307b_gate_factorial_20261027_145412` | `gate_factorial.csv`, `common_group_compare.csv` | sensitivity |
| R400, R402–R406 | `outputs/R400_406_provinces_20261028_183104` | `m4_direction_labels.csv`, `m4_province_scenario.csv` | formal |
| R401 | `outputs/R401_shanghai_availability_20261028_180508` | `report.md`, `coverage_matrix.csv`, `scope_gap.csv` | structural |
| R407 | `outputs/R407_looro_20261028_183054` | `m4_looro.csv` | sensitivity |
| R408 | `outputs/R408_delta_20261028_183131` | `m4_delta.csv` | sensitivity |
| R409 | `outputs/R409_bounds_20261028_183421` | `m4_bounds.csv` | sensitivity |
| R500–R504 | `outputs/R500_504_paper_artifacts` | `table1_price.csv`, `table2_decision.csv`, `figure1.svg`, `figure2.svg`, `artifact_manifest.json` | formal |
| R505 | `outputs/R505_reproducibility` | `reproducibility_report.json`, `RUNBOOK.md` | formal |

Structural diagnostics (not counted in the 46 runs):

`outputs/DIAG_binding_20261026_193238`, `outputs/DIAG_decision_sensitivity_20261026_181347`,
`outputs/DIAG_objective_20261026_193437`, `outputs/DIAG_scope_activation_20261027_151305`,
`outputs/DIAG_heal_bound_scale_20261027_151753`, `outputs/DIAG_calcium_gap_20261027_163714`,
`outputs/DIAG_cvar_channel_20261027_163855`, `outputs/DIAG_cvar_angle_spike_20261027_164753`,
`outputs/DIAG_vertex_stability_20261027_164615`, `outputs/DIAG_vertex_radius_20261027_164952`,
`outputs/DIAG_feasible_width_20261027_164140`, `outputs/DIAG_price_radius_20261027_174014`,
`outputs/DIAG_price_panel_20261027_180334`, `outputs/DIAG_price_panel_20261027_232721`,
`outputs/DIAG_price_panel_20261027_232756`, `outputs/DIAG_tail_angle_20261027_192248`,
`outputs/DIAG_lambda_curve_20261027_191751`, `outputs/DIAG_lambda_curve_fine_20261027_191956`,
`outputs/DIAG_price_coverage_20261027_193323`, `outputs/DIAG_d0_bistability_20261027_231703`,
plus one legacy directory `outputs/R307_binding_20261026_193215` and one appendix
`outputs/APPENDIX_shanghai_k4_official_20261028_181254`.

## Five traps that must survive into the paper

1. `interpolation ≡ group_mean` under province×group masking (1200/1200 identical) — the
   under-coverage there is the group-mean's, not a method difference.
2. Under RNI, D0 is a **binary switch**; the "which provinces differ" list flips wholesale with the
   price construction. Report the rate (0.460–0.498), never the province names.
3. `objective_gap` is normalized by per-objective payoff ranges — **not comparable across panel versions**.
4. `use_chance_constraint=False` removes **all** nutrition constraints (that is D2's definition).
   Deterministic solves must pass `use_chance_constraint=True, epsilon=0` — the wrong call yields a
   silent "all zeros" optimum (see `CHANGELOG` §36.2).
5. The main metric is `|Δq|` change rate, not `flips` (pre-registration deviation, declared).

## How to verify this ledger

```powershell
python scripts/check_tracker.py --file docs/EXPERIMENT_TRACKER_EN.md   # structure / citations / counts
python -m unittest discover -s tests                                   # 69 tests
python scripts/verify_reproducibility.py                               # contract hashes, run dirs, gates
```

`check_tracker.py` asserts: every cited `outputs/` directory exists, every directory on disk is
mentioned, every `DONE` row cites a resolvable artifact, and the summary totals equal the per-run
status column.
