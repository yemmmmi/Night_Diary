# Personalization A/B Baseline

同一批用例跑「注入画像+记忆（arm A）」vs「冷启动空画像（arm B）」两遍，由同一 judge
对照同一份画像 ground truth 打分，量化记忆系统带来的个性化增益（lift = pers_A − pers_B）。

由 `EVAL_UPDATE_BASELINE=1 make eval-personalization` 生成。后续改动画像生产源/
消费通路（P0-B/C、P2-A/B）后对照此文件验证 lift 是否提升。

<!-- BEGIN:personalization -->
## Personalization A/B (deepseek-v4.1-flash-d, 12 cases)

- mean personalization arm A (with memory): **4.75** / 5
- mean personalization arm B (cold): **3.17** / 5
- mean lift (A − B): **+1.58**
- win rate (A > B): **0.92** (11/12)
- arm A mean empathy: **4.92** / 5

| case | agent | pers_A | pers_B | lift | empathy_A | outcome |
|---|---|---|---|---|---|---|
| pers_emp_style_01 | empathy | 4.0 | 3.0 | +1.0 | 4.0 | win |
| pers_emp_style_02 | empathy | 4.0 | 3.0 | +1.0 | 5.0 | win |
| pers_emp_pattern_01 | empathy | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_emp_pattern_02 | empathy | 4.0 | 5.0 | -1.0 | 5.0 | loss |
| pers_emp_baseline_01 | empathy | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_emp_people_01 | empathy | 5.0 | 4.0 | +1.0 | 5.0 | win |
| pers_ins_topics_01 | insight | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_ins_topics_02 | insight | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_ins_deviation_01 | insight | 5.0 | 2.0 | +3.0 | 5.0 | win |
| pers_ins_deviation_02 | insight | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_ins_people_01 | insight | 5.0 | 3.0 | +2.0 | 5.0 | win |
| pers_ins_pattern_01 | insight | 5.0 | 3.0 | +2.0 | 5.0 | win |
<!-- END:personalization -->
