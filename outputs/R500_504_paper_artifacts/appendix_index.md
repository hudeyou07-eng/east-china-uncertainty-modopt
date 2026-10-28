# 附录产物清单（R504）

| 文件 | bytes | sha256（前 16） |
|---|---|---|
| `table1_price.csv` | 1793 | `4f9bb37ea8be31a8` |
| `table1_consumption.csv` | 3436 | `a997620c2745b97e` |
| `table1.md` | 2573 | `144ea612698ed12c` |
| `table2_decision.csv` | 774 | `cfa3ad3b251b19b4` |
| `table2.md` | 1066 | `2840da4517efb197` |
| `figure1_stable_flip.csv` | 114 | `941866081762a70c` |
| `figure1.svg` | 2433 | `892cdf3b98857aa1` |
| `figure2_regional_heatmap.csv` | 489 | `923be6e35c17a6db` |
| `figure2.svg` | 6882 | `a87e544b44fb6269` |

## 源 run

- B1 价格面板：`outputs\B1_formal_withmice_20261023_124906`
- B1 消费面板：`outputs\R103_105_consumption_formal_20261026_174725`
- B2 EAR：`outputs\R200_203_b2_formal_20261027_222841`；RNI：`outputs\R200_203_b2_formal_20261027_224315`
- M4 方向标签：`outputs\R400_406_provinces_20261028_183104`

## 复现

```powershell
python scripts/build_paper_artifacts.py
```