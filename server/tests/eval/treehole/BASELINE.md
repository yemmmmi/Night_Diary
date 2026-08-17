# Tree-Hole Digest Quality Baseline

由 `EVAL_UPDATE_BASELINE=1 make eval` 生成。后续改动树洞 prompt 后对照此文件做回归。


<!-- BEGIN:treehole -->
## TreeHole digest (deepseek-v4-flash, 5 cases)

- mean summary_faithfulness: **4.60** / 5
- mean temporal_correctness: **4.60** / 5
- mean overall: **4.35** / 5

| case | faithfulness | temporal | emotion | brevity | overall |
|---|---|---|---|---|---|
| th_simple_record | 5.0 | 5.0 | 5.0 | 5.0 | 5.00 |
| th_emotional_vent | 5.0 | 5.0 | 5.0 | 5.0 | 5.00 |
| th_past_reference | 4.0 | 5.0 | 2.0 | 5.0 | 3.98 |
| th_future_plan | 4.0 | 3.0 | 2.0 | 4.0 | 3.24 |
| th_mixed_day | 5.0 | 5.0 | 3.0 | 5.0 | 4.51 |
<!-- END:treehole -->
