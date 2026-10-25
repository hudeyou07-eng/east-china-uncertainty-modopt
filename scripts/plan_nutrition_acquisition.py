"""用贪心集合覆盖求"补多少种食物能把各组口径拉到 90%"。

对每个组，反复挑选能新覆盖最多未覆盖观测的缺失食物，直到覆盖率达到目标。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from src.mapping_audit import (  # noqa: E402
    CATEGORY_ALIASES, GROUP_PRICE_CATEGORIES, GROUP_ZH, split_tokens,
)

DATA = ROOT / "data" / "input"
OUT = ROOT / "outputs" / "mapping_audit_20261023_143000"
TARGET = 0.90


def main() -> None:
    panel = pd.read_excel(DATA / "price" / "price_panel_clean.xlsx", "年均值表")
    nutrition = pd.read_csv(DATA / "clean_tables" / "nutrition.csv")
    nut_foods = set(nutrition["food_name"].unique())
    panel["品类"] = panel["品类"].astype(str)

    print("=" * 92)
    print(f"把各组口径覆盖率拉到 {TARGET:.0%} 所需补录的食物（贪心集合覆盖）")
    print("=" * 92)

    rows = []
    global_needs: dict[str, int] = {}
    for gid, cats in GROUP_PRICE_CATEGORIES.items():
        sub = panel[panel["品类"].isin(cats)]
        n_obs = len(sub)
        if n_obs == 0:
            continue
        # 每个观测缺失的 token 集合
        missing_per_obs = []
        for _, row in sub.iterrows():
            tokens = split_tokens(row.get("口径构成"))
            aliases = CATEGORY_ALIASES.get(row["品类"], {})
            bad = {aliases.get(t, t) for t in tokens if aliases.get(t, t) not in nut_foods}
            missing_per_obs.append(bad)

        covered = sum(1 for bad in missing_per_obs if not bad)
        picked: list[str] = []
        while covered / n_obs < TARGET:
            # 统计每个候选食物能新覆盖多少观测
            gain: dict[str, int] = {}
            for bad in missing_per_obs:
                for token in bad:
                    gain[token] = gain.get(token, 0) + 1
            if not gain:
                break
            best = max(gain, key=lambda k: (gain[k], k))
            picked.append(best)
            covered += gain[best]
            for bad in missing_per_obs:
                bad.discard(best)
        for item in picked:
            global_needs[item] = global_needs.get(item, 0) + 1
        rows.append({
            "group_id": gid,
            "group_zh": GROUP_ZH[gid],
            "price_observations": n_obs,
            "baseline_mapped_ratio": round(sum(
                1 for bad in missing_per_obs
                if not bad) / n_obs, 4) if not picked else None,
            "items_needed": len(picked),
            "items": "、".join(picked) if picked else "（已达标）",
        })

    # 重算基线比例（picked 已清空，单独算一次）
    for row in rows:
        sub = panel[panel["品类"].isin(GROUP_PRICE_CATEGORIES[row["group_id"]])]
        n_obs = len(sub)
        base = 0
        for _, r in sub.iterrows():
            tokens = split_tokens(r.get("口径构成"))
            aliases = CATEGORY_ALIASES.get(r["品类"], {})
            bad = [t for t in tokens if aliases.get(t, t) not in nut_foods]
            if not bad:
                base += 1
        row["baseline_mapped_ratio"] = round(base / n_obs, 4) if n_obs else 0.0

    df = pd.DataFrame(rows)
    print(df[["group_id", "group_zh", "price_observations",
              "baseline_mapped_ratio", "items_needed", "items"]].to_string(index=False))

    union = sorted({i for row in rows for i in re.split(r"[、]", row["items"])
                    if i and not i.startswith("（")})
    print()
    print(f"合并去重后的补录清单共 {len(union)} 种食物：")
    print("  " + "、".join(union))
    print()
    print("按被几个组需要排序（越靠前越优先）：")
    need = sorted(global_needs.items(), key=lambda kv: (-kv[1], kv[0]))
    for item, cnt in need:
        print(f"  {item:8s} 被 {cnt} 个组需要")

    df.to_csv(OUT / "acquisition_plan.csv", index=False, encoding="utf-8-sig")
    print(f"\n产物已写入 {OUT / 'acquisition_plan.csv'}")


if __name__ == "__main__":
    main()
