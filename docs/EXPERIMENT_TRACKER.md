# Experiment Tracker

| Run ID | Milestone | Purpose | Variant | Split / scope | Primary metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R000 | M0 | environment check | dependency/version | local | imports, solver availability | MUST | DONE | five automated tests passed in the cloned repository |
| R001 | M0 | raw data audit | provenance/units/missing | all raw files | audit errors/warnings | MUST | DONE | 7 regions, 14 groups, 882 cells; 294 truth-eligible observations |
| R002 | M0 | food-group freeze | ontology/crosswalk | all groups | included K, rank, coverage | MUST | TODO | save hashes |
| R003 | M0 | deterministic toy | known LP solution | synthetic toy | objective, feasibility | MUST | PARTIAL | current fixture validates chance MILP; add a separate hand-checkable LP fixture |
| R004 | M0 | chance MILP toy | joint indicator | synthetic toy | feasibility, z count | MUST | DONE | optimal result; z count respects epsilon budget |
| R005 | M0 | reproducibility | same seed twice | synthetic toy | result hash | MUST | DONE | reviewed repeated toy runs produced identical hashes |
| R006 | M0 | invalid input | negative/unit/missing coeff | synthetic bad fixtures | explicit failure | MUST | DONE | invalid bounds and non-finite coefficients fail loudly |
| R100 | M1 | price MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | paired masks |
| R101 | M1 | price year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | paired masks |
| R102 | M1 | price province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | may become partial ID |
| R103 | M1 | consumption MCAR | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | paired masks |
| R104 | M1 | consumption year-block | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | paired masks |
| R105 | M1 | consumption province×group | mean/interp/MICE/main | 5×20 | sMAE, coverage | MUST | TODO | paired masks |
| R106 | M1 | interval calibration | main | aggregate | coverage-width curve | MUST | TODO | 50/80/90/95% |
| R107 | M1 | interaction gate | main ± region×group | all masks | paired error/coverage | NICE | TODO | enable only if both improve |
| R108 | M1 | MAR sensitivity | main | all masks | calibration | MUST | TODO | base model |
| R109 | M1 | MNAR shift | delta grid | blocks | error/coverage | MUST | TODO | sensitivity, not fit selection |
| R200 | M2 | deterministic baseline | D0 mean-fill | 5×20 truth | feasibility, flips, p95 regret | MUST | TODO | same K/bounds |
| R201 | M2 | posterior mean | D1 | 5×20 truth | feasibility, flips, p95 regret | MUST | TODO | no scenarios |
| R202 | M2 | scenario expected | D2 | 5×20 truth | feasibility, flips, p95 regret | MUST | TODO | no chance constraint |
| R203 | M2 | proposed method | D3 | 5×20 truth | feasibility, flips, p95 regret | MUST | TODO | primary result |
| R300 | M3 | chance deletion | D3→D2 | primary setting | delta metrics | MUST | TODO | novelty isolation |
| R301 | M3 | scenario count | 50/100/200/500 | primary setting | stability/runtime | MUST | TODO | choose plateau |
| R302 | M3 | epsilon | 0/.02/.05/.10 | primary setting | feasibility/regret | MUST | TODO | predeclared grid |
| R303 | M3 | objective weights | original/equal | primary setting | direction stability | MUST | TODO | no result-driven weights |
| R304 | M3 | W uncertainty | on/off | primary setting | flips/regret | NICE | TODO | mechanism diagnostic |
| R305 | M3 | joint vs marginal | joint/independent z | primary setting | joint feasibility | NICE | TODO | appendix |
| R306 | M3 | Big-M diagnostic | tight/global | toy only | gap/runtime | NICE | TODO | global never used formally |
| R307 | M3 | boundary gate | on/off | primary setting | conclusion labels | NICE | TODO | do not weaken final gate |
| R400 | M4 | Jiangsu scenarios | D3 | 3 scenarios | stable labels | MUST | TODO | province names in English IDs |
| R401 | M4 | Shanghai scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R402 | M4 | Zhejiang scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R403 | M4 | Shandong scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R404 | M4 | Anhui scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R405 | M4 | Jiangxi scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R406 | M4 | Fujian scenarios | D3 | 3 scenarios | stable labels | MUST | TODO |  |
| R407 | M4 | leave-one-region-out | D3 | 7 folds | direction agreement | MUST | TODO |  |
| R408 | M4 | delta sensitivity | -0.5/0/+0.5 | all regions | direction agreement | MUST | TODO |  |
| R409 | M4 | boundary grid | low/mid/high/worst | all regions | direction agreement | MUST | TODO |  |
| R500 | M5 | Table 1 | calibration | B1 | table validation | MUST | TODO | generated from raw metrics |
| R501 | M5 | Table 2 | decision result | B2 | table validation | MUST | TODO | generated from raw metrics |
| R502 | M5 | Figure 1 | stable/flip | B2 | visual QC | MUST | TODO | main memory point |
| R503 | M5 | Figure 2 | regional heatmap | B4 | visual QC | MUST | TODO |  |
| R504 | M5 | appendix pack | all | all | completeness | NICE | TODO |  |
| R505 | M5 | reproducibility rerun | selected must-runs | clean env | hash/metric tolerance | MUST | TODO | student handoff gate |
