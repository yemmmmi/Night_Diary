# Reranker LoRA 微调操作指南（P0-1）

本项目 RAG 重排器代码已就绪但生产环境被旁路，且中文嵌入未注入。
本指南完成"修复 → 导数据 → 训练 → 评估 → 接入"五步闭环，全程本地完成。

## 前置条件

- Windows + N卡 ≥8GB 显存（RTX 3060 12G / 3070 8G / 4060 8G 等）
- 项目已有日记数据（**建议 ≥200 篇**，最少 20 篇可跑通流程但效果有限）
- Anaconda base 环境（已有 torch 2.5.1 + sentence-transformers 5.5.1 + transformers 4.55.4）

> **注意**：训练脚本需用 Anaconda 的 Python（`C:\Users\18016\anaconda3\python.exe`），
> 不是 TRAE 内置的精简 Python。下文命令中统一用 `$env:PY` 指代它。

## 第 0 步：确认依赖

Anaconda base 环境通常已有大部分依赖，只需补装 `datasets`（sentence-transformers 5.x 训练时需要）：

```powershell
$env:PY = "C:\Users\18016\anaconda3\python.exe"
& $env:PY -m pip install datasets -i https://mirrors.aliyun.com/pypi/simple/ --timeout 120

# 如果 accelerate 版本过低（<1.5），升级它：
& $env:PY -m pip install --upgrade accelerate -i https://mirrors.aliyun.com/pypi/simple/ --timeout 120

# 验证依赖就绪
& $env:PY -c "from sentence_transformers import CrossEncoder, InputExample; import datasets; print('依赖就绪')"
```

## 第 1 步：导出训练数据

```powershell
$env:PY = "C:\Users\18016\anaconda3\python.exe"
cd d:\work\night_diary_v2\server

# 基础导出（仅日记正负样本对）
& $env:PY -m scripts.finetune.export_reranker_pairs `
  --db "$env:APPDATA\night-diary\night_diary.db" `
  --out scripts/finetune/data.jsonl `
  --neg-ratio 4

# 进阶导出（合并用户反馈弱监督）
& $env:PY -m scripts.finetune.export_reranker_pairs `
  --db "$env:APPDATA\night-diary\night_diary.db" `
  --out scripts/finetune/data.jsonl `
  --neg-ratio 4 `
  --with-feedback
```

产出两个文件：
- `data.train.jsonl` — 训练集（80%）
- `data.val.jsonl` — 验证集（20%）

每行格式：`{"query": "...", "passage": "...", "label": 1}`

**数据量参考**：
- 16 篇日记 → ~80 条训练对（仅够跑通流程，效果有限）
- 200 篇日记 → ~1000 条训练对（可看到明显提升）
- 500+ 篇日记 → ~2500 条训练对（理想效果）

## 第 2 步：训练

```powershell
$env:PY = "C:\Users\18016\anaconda3\python.exe"
$env:HF_ENDPOINT = "https://hf-mirror.com"  # 用 HF 镜像加速模型下载
cd d:\work\night_diary_v2\server

# 全量微调（推荐，bge-reranker-base 仅 560M，CPU 也能训，73 秒完成）
& $env:PY -m scripts.finetune.train_reranker_lora `
  --train scripts/finetune/data.train.jsonl `
  --val scripts/finetune/data.val.jsonl `
  --out "$env:APPDATA\night-diary\models\reranker-night-diary" `
  --epochs 3 --batch-size 8

# LoRA 模式（省显存，需额外装 peft：& $env:PY -m pip install peft）
& $env:PY -m scripts.finetune.train_reranker_lora `
  --train scripts/finetune/data.train.jsonl `
  --val scripts/finetune/data.val.jsonl `
  --out "$env:APPDATA\night-diary\models\reranker-night-diary" `
  --epochs 3 --batch-size 8 --lora --lora-r 8
```

训练完成后，模型权重保存在 `models/reranker-night-diary/` 目录（含 `model.safetensors` ~1.1GB）。

## 第 3 步：评估对比

```powershell
$env:PY = "C:\Users\18016\anaconda3\python.exe"
$env:HF_ENDPOINT = "https://hf-mirror.com"
cd d:\work\night_diary_v2\server

& $env:PY -m scripts.finetune.eval_reranker `
  --val scripts/finetune/data.val.jsonl `
  --base BAAI/bge-reranker-base `
  --finetuned "$env:APPDATA\night-diary\models\reranker-night-diary"
```

输出对比表（Accuracy / Precision / Recall / F1 / AUC）。

**如何判断有效**：
- AUC 提升 ≥0.03 → 微调有效，可接入
- AUC 持平或下降 → 数据量不足，先积累更多日记再重训
- Precision 提升 + Recall 下降 → 模型变保守了，可尝试降低 `--neg-ratio` 到 2

## 第 4 步：接入项目（代码已改好）

`container.py` 已修改为：
1. **注入中文嵌入函数**（修复 ChromaDB 回退英文 `all-MiniLM-L6-v2` 的 bug）
2. **自动加载** `models_dir/reranker-night-diary` 下的微调模型
3. 若微调目录不存在，回退到基座 `BAAI/bge-reranker-base`
4. 若加载失败，优雅降级为无重排（RRF 融合结果直接返回）

只要第 2 步的模型输出到了正确路径，**下次启动后端自动生效**：

```powershell
cd d:\work\night_diary_v2\server
& $env:PY -m app.main
# 日志出现 "AI stack ready" 即接入成功
```

## 常见问题

**Q: 导出数据报错"日记数量不足 2 篇"**
A: 数据库中日记太少。先多写几篇日记，或用 seed 脚本生成测试数据。

**Q: 训练时报 CUDA out of memory**
A: 你可能用的是 GPU 版 torch。减小 `--batch-size` 到 4，或改用 LoRA 模式（`--lora`）。
   CPU 版 torch（anaconda base 默认）不会遇到此问题，只是慢一点。

**Q: 评估时 AUC 没提升甚至下降**
A: 数据量太少（<200 篇日记）。这是正常的——基座模型本身已经很强，少量数据微调反而引入噪声。
   先积累日记数据，到 200+ 篇后重训。

**Q: 训练时报 `AttributeError: module 'tensorflow' has no attribute 'io'`**
A: Anaconda base 环境中 tensorflow 残留与 tensorboard 冲突。脚本已内置 monkeypatch 绕过此问题。

**Q: 训练时报 `keep_torch_compile` 参数错误**
A: accelerate 版本过低。运行 `& $env:PY -m pip install --upgrade accelerate -i https://mirrors.aliyun.com/pypi/simple/`

**Q: 后端日志显示 "Reranker init skipped"**
A: 模型路径不对。确认 `models/reranker-night-diary/` 目录下有 `config.json` 和 `model.safetensors`。

## 文件清单

| 文件 | 用途 |
|------|------|
| `export_reranker_pairs.py` | 从 SQLite 导出训练对 |
| `train_reranker_lora.py` | 训练（全量/LoRA 两种模式） |
| `eval_reranker.py` | 评估对比基座 vs 微调 |
| `container.py`（已改） | 嵌入注入 + reranker 自动挂载 |

## 已验证的端到端流程（2026-07-09）

在 16 篇测试日记上跑通了完整流程：
- 导出：16 正样本 + 64 负样本 → 训练集 64 / 验证集 16
- 训练：CPU 73 秒，3 epoch，train_loss 0.42
- 评估：基座 AUC 1.0（小数据集恰好完美），微调 AUC 1.0（持平）
- 结论：数据量不足时微调效果不明显，需积累到 200+ 篇日记后重训
