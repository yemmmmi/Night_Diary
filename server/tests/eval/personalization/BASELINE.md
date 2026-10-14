# Personalization A/B Baseline

同一批用例跑「注入画像+记忆（arm A）」vs「冷启动空画像（arm B）」两遍，由同一 judge
对照同一份画像 ground truth 打分，量化记忆系统带来的个性化增益（lift = pers_A − pers_B）。

由 `EVAL_UPDATE_BASELINE=1 make eval-personalization` 生成。后续改动画像生产源/
消费通路（P0-B/C、P2-A/B）后对照此文件验证 lift 是否提升。
