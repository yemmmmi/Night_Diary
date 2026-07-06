# Chat Intent LoRA Fine-tuning (PR-C)

对 `ChatIntentClassifier` 的 LLM 层进行 LoRA 微调，用本地小模型（Qwen2.5-1.5B）替代远程 API 调用，实现**零 token 成本**的意图分类。

微调后的模型可直接注入 `ChatIntentClassifier(llm=FinetunedIntentLLM(...))`，无需修改任何业务代码。

---

## 目录结构

```
server/training/finetune_intent/
├── __init__.py            # 包标记（空文件）
├── prepare_data.py        # JSONL → instruction-tuning 格式转换
├── train.py               # LoRA 微调主脚本
├── inference.py           # FinetunedIntentLLM 推理适配器
├── configs/
│   └── default.yaml       # 训练超参配置
├── README.md              # 本文件
├── data/                  # [自动生成] 转换后的训练数据
└── outputs/               # [自动生成] 训练输出（checkpoint + final）
```

---

## 硬件要求

| 配置 | 最低要求 | 推荐 |
|------|----------|------|
| GPU VRAM | 6 GB+ (FP16) | 8 GB+ |
| 系统内存 | 8 GB | 16 GB |
| 磁盘空间 | 5 GB (模型+数据) | 10 GB |
| GPU 类型 | 任意 CUDA 11.8+ | NVIDIA RTX 3060+ |

- **FP16 训练**（默认）：需要 CUDA GPU，单卡 6 GB VRAM 即可运行
- **CPU fallback**：无 GPU 时自动降级为 FP32 慢速推理，训练极度缓慢（不推荐用于训练，仅用于推理）
- Qwen2.5-1.5B 基座模型约 3 GB，LoRA 适配器仅约 12 MB

---

## 依赖安装

训练脚本需要以下额外依赖（不在 `pyproject.toml` 的运行时依赖中）：

```bash
cd server
pip install transformers peft datasets accelerate torch pyyaml
```

各依赖的版本要求：

| 依赖 | 最低版本 | 用途 |
|------|----------|------|
| `transformers` | >= 4.40 | 模型加载、Trainer |
| `peft` | >= 0.10 | LoRA 适配器 |
| `datasets` | >= 2.14 | 数据集处理 |
| `accelerate` | >= 0.30 | 分布式/混合精度加速 |
| `torch` | >= 2.0 | 深度学习框架 |
| `pyyaml` | >= 6.0 | YAML 配置解析 |

---

## 训练步骤

### 1. 准备数据

数据集位于 `server/tests/eval/intent/dataset/`：

| 文件 | 样本数 | 用途 |
|------|--------|------|
| `train.jsonl` | 600 | 训练集 |
| `val.jsonl` | 100 | 验证集（epoch 评估 + early stopping） |
| `test.jsonl` | 200 | 测试集 |

原始格式（每行一个 JSON）：

```json
{"text": "今天工作压力好大，感觉撑不住了", "intent": "emotional_vent", "source": "manual"}
```

转换后的 instruction-tuning 格式：

```json
{
  "instruction": "请分析以下用户消息的意图，返回JSON格式。",
  "input": "今天工作压力好大，感觉撑不住了",
  "output": "{\"intent_category\": \"emotional_vent\", \"confidence\": 0.9, \"need_retrieval\": false, \"need_tools\": [\"analyze_sentiment\"], \"need_entity_query\": false}"
}
```

可以单独运行数据转换：

```bash
cd server
python -m training.finetune_intent.prepare_data \
    --data-dir tests/eval/intent/dataset \
    --output-dir training/finetune_intent/data
```

### 2. 启动训练

```bash
cd server

# 使用默认配置
python -m training.finetune_intent.train

# 通过 CLI 覆盖配置
python -m training.finetune_intent.train \
    --num-train-epochs 5 \
    --learning-rate 1e-4 \
    --batch-size 4

# CPU 模式（不推荐，极慢）
python -m training.finetune_intent.train --no-fp16

# 跳过数据准备（复用已转换的数据）
python -m training.finetune_intent.train --skip-prepare
```

### 3. 训练输出

训练完成后，LoRA 适配器保存在 `outputs/final/`：

```
outputs/
├── checkpoint-XXX/        # 各 epoch 的 checkpoint
│   ├── adapter_model.safetensors
│   ├── adapter_config.json
│   └── ...
└── final/                 # 最佳模型（load_best_model_at_end）
    ├── adapter_model.safetensors
    ├── adapter_config.json
    ├── tokenizer.json
    └── ...
```

---

## 配置说明

配置文件 `configs/default.yaml` 的关键字段：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `base_model` | `Qwen/Qwen2.5-1.5B` | 基座模型 |
| `lora.r` | 16 | LoRA 秩 |
| `lora.alpha` | 32 | LoRA 缩放因子（通常为 r 的 2 倍） |
| `lora.dropout` | 0.05 | LoRA dropout |
| `learning_rate` | 2e-4 | 学习率 |
| `num_train_epochs` | 3 | 训练轮数 |
| `per_device_train_batch_size` | 8 | 单卡 batch size |
| `gradient_accumulation_steps` | 4 | 梯度累积步数（等效 batch=32） |
| `warmup_ratio` | 0.1 | 预热比例 |
| `max_seq_length` | 512 | 最大序列长度 |
| `metric_for_best_model` | `macro_f1` | 选优指标 |
| `load_best_model_at_end` | true | 训练结束加载最优 checkpoint |

---

## 推理使用

### 基本用法

```python
from training.finetune_intent.inference import FinetunedIntentLLM

llm = FinetunedIntentLLM(model_path="training/finetune_intent/outputs/final")

# 直接调用
response = llm.invoke("请分析以下用户消息的意图...")
print(response.content)
# {"intent_category": "emotional_vent", "confidence": 0.9, ...}

# 异步调用
response = await llm.ainvoke("请分析以下用户消息的意图...")
```

### 注入 ChatIntentClassifier

```python
from training.finetune_intent.inference import FinetunedIntentLLM
from app.domain.agents.chat_intent_classifier import ChatIntentClassifier

# 创建微调模型 LLM 客户端
llm = FinetunedIntentLLM(
    model_path="training/finetune_intent/outputs/final",
    device="auto",          # auto / cuda / cpu
)

# 直接注入 ChatIntentClassifier（无需修改任何业务代码）
classifier = ChatIntentClassifier(llm=llm, model="qwen2.5-1.5b-lora")

# 异步分类（生产路径）
result = await classifier.classify("今天工作压力好大，感觉撑不住了")
print(result.intent_category)  # "emotional_vent"
print(result.confidence)       # 0.9

# 同步分类（eval 路径）
result = classifier.classify_sync("不想活了")
print(result.intent_category)  # "crisis_signal"
```

### 命令行快速测试

```bash
cd server
python -m training.finetune_intent.inference training/finetune_intent/outputs/final
```

---

## 设计要点

### 训练-推理对齐

`prepare_data.py` 中的 `PROMPT_TEMPLATE` 与 `ChatIntentClassifier._CHAT_INTENT_PROMPT` 完全一致，确保微调模型在训练时看到的 prompt 格式与推理时一致。

### 6 类意图

| 意图 | 路由 | need_tools |
|------|------|------------|
| `casual_chat` | light | [] |
| `emotional_vent` | medium | ["analyze_sentiment"] |
| `retrospective_query` | heavy | ["search_diary"] |
| `advice_seeking` | heavy | ["search_diary", "analyze_sentiment"] |
| `crisis_signal` | crisis | [] |
| `entity_query` | medium | ["query_entity_graph"] |

训练数据的 `output` 字段包含完整的路由信息（`need_retrieval` / `need_tools` / `need_entity_query`），模型学习生成完整 JSON，`ChatIntentClassifier._parse_llm_output` 可直接解析。

### CPU Fallback

- 无 GPU 时自动降级为 FP32 推理
- 生成速度约 5-10 tokens/s（1.5B 模型，CPU）
- 适合开发调试，不适合生产环境

### 降级安全

`FinetunedIntentLLM.invoke` 在生成失败时返回安全的 fallback JSON（`casual_chat` + `confidence=0.5`），`ChatIntentClassifier` 的 `classify` / `classify_sync` 方法已有 try/except 包裹，会回退到规则层分类。

---

## 与 eval 流程集成

训练完成后，可在 intent eval 中 A/B 对比微调模型 vs 规则层 vs 远程 LLM：

```bash
# 运行 intent eval（需先完成训练）
make eval-intent
```

intent eval 的 baseline 在 `server/tests/eval/intent/` 下维护，使用 `EVAL_UPDATE_BASELINE=1` 可刷新基线。
