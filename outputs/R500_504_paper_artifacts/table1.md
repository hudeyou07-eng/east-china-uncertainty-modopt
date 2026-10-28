# Table 1 — 插补方法的点精度与区间校准（R100–R105）

两份面板各 5 折 × 20 重复 × 3 种遮蔽几何。`coverage95` 名义值 0.95，
`scaled_mae` 越小越好。**点精度与标定不是同一件事**：MICE 点误差最低但在
`province_group` 上崩溃（价格 sMAE 1.18 / 覆盖 0.733；消费 sMAE 1.000 / 覆盖 0.079）。

## price

| mask | method | n_eval | sMAE | logRMSE | cov80 | cov95 | width95 |
|---|---|---|---|---|---|---|---|
| consecutive_years | group_mean | 200 | 0.1738 | 0.1849 | 0.830 | 0.925 | 36.98 |
| consecutive_years | hierarchical_rw | 200 | 0.1675 | 0.1766 | 0.845 | 0.955 | 38.23 |
| consecutive_years | interpolation | 200 | 0.1406 | 0.1490 | 0.800 | 0.865 | 25.76 |
| consecutive_years | mice | 200 | 0.1266 | 0.1396 | 0.740 | 0.840 | 15.97 |
| province_group | group_mean | 648 | 0.1893 | 0.2158 | 0.810 | 0.919 | 37.03 |
| province_group | hierarchical_rw | 648 | 0.1776 | 0.2022 | 0.857 | 0.975 | 34.01 |
| province_group | interpolation | 648 | 0.1893 | 0.2158 | 0.702 | 0.825 | 25.60 |
| province_group | mice | 648 | 1.1821 | 0.8278 | 0.438 | 0.733 | 53.69 |
| single_cell | group_mean | 600 | 0.2082 | 0.2394 | 0.853 | 0.913 | 36.89 |
| single_cell | hierarchical_rw | 600 | 0.1746 | 0.2357 | 0.882 | 0.950 | 28.52 |
| single_cell | interpolation | 600 | 0.1667 | 0.2055 | 0.847 | 0.887 | 25.84 |
| single_cell | mice | 600 | 0.1555 | 0.3681 | 0.770 | 0.865 | 17.68 |

## consumption

| mask | method | n_eval | sMAE | logRMSE | cov80 | cov95 | width95 |
|---|---|---|---|---|---|---|---|
| consecutive_years | group_mean | 200 | 0.1785 | 0.1776 | 0.865 | 0.930 | 87.52 |
| consecutive_years | hierarchical_rw | 200 | 0.1711 | 0.1701 | 0.810 | 0.960 | 108.73 |
| consecutive_years | interpolation | 200 | 0.0612 | 0.0667 | 0.820 | 0.870 | 34.18 |
| consecutive_years | mice | 200 | 0.1307 | 0.1092 | 0.725 | 0.825 | 26.89 |
| province_group | group_mean | 900 | 0.2167 | 0.2280 | 0.857 | 0.918 | 87.46 |
| province_group | hierarchical_rw | 900 | 0.2239 | 0.2337 | 0.720 | 0.900 | 85.02 |
| province_group | interpolation | 900 | 0.2167 | 0.2280 | 0.587 | 0.691 | 34.09 |
| province_group | mice | 900 | 7.0170 | 1.3964 | 0.043 | 0.079 | 57.74 |
| single_cell | group_mean | 1300 | 0.1421 | 0.2231 | 0.852 | 0.931 | 87.46 |
| single_cell | hierarchical_rw | 1300 | 0.1496 | 0.2143 | 0.820 | 0.949 | 92.27 |
| single_cell | interpolation | 1300 | 0.0478 | 0.0673 | 0.853 | 0.937 | 34.50 |
| single_cell | mice | 1300 | 0.0367 | 0.0848 | 0.811 | 0.901 | 19.74 |
