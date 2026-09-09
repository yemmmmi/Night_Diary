/* 夜记 v4.1 · Agent 体系全景报告 — 图表脚本
 * 数据来源（2026-09-09 工作区；HEAD db7e446 + 未提交 REAL 基线）：
 *   intent：mixed；baseline_a REAL 0.744（deepseek-v4-flash，250 例）；0.992 为 stub oracle 上界
 *   tool_call：native REAL、fallback stub oracle，40 例
 *   skill_call：REAL，30 例；Token -75.4%；accuracy 0.767 → 0.633
 *   rag：2026-09-09 Qwen text-embedding-v3 + qwen3-rerank 三次质量门；committed json 仍为更早快照
 *   episodic：REAL Qwen；jaccard 0.498 / vector 0.348 / vector_rerank 0.564
 *   generation/plan：REAL deepseek-v4-flash judge；treehole 图用三次门末轮 4.72（文件 BASELINE.md 仍 4.35）
 *   图 12/13：官方 JD 方向性映射与仓库证据状态，不是市场频率或招聘统计。
 */
(function () {
  'use strict';
  if (typeof echarts === 'undefined') return;

  var FONT = "'WorkSans', 'Microsoft YaHei', 'PingFang SC', sans-serif";
  var C = {
    ink: '#2A2823',
    muted: '#827B6D',
    rule: '#E0DACB',
    accent: '#44549E',
    accentSoft: 'rgba(68,84,158,0.10)',
    accent2: '#B07B4F',
    ok: '#4E7A52'
  };

  function catAxis(extra) {
    var base = {
      axisLine: { lineStyle: { color: C.rule } },
      axisTick: { show: false },
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    };
    for (var k in extra) base[k] = extra[k];
    return base;
  }
  function valAxis(extra) {
    var base = {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11 },
      splitLine: { lineStyle: { color: C.rule, type: 'dashed' } }
    };
    for (var k in extra) base[k] = extra[k];
    return base;
  }
  function barLabel(fmt) {
    return { show: true, position: 'top', fontFamily: FONT, fontSize: 11, color: C.ink, formatter: fmt };
  }
  function legend(extra) {
    var base = {
      top: 4,
      left: 'center',
      itemWidth: 13,
      itemHeight: 9,
      textStyle: { fontFamily: FONT, fontSize: 12, color: C.ink }
    };
    for (var k in extra) base[k] = extra[k];
    return base;
  }

  var registry = [];
  function mount(id, option) {
    var el = document.getElementById(id);
    if (!el) return;
    option.textStyle = { fontFamily: FONT };
    option.animationDuration = 420;
    var chart = echarts.init(el);
    chart.setOption(option);
    registry.push(chart);
  }

  /* ── 图 3 · 意图分类：纯规则基线 vs 规则+LLM 双层 ── */
  mount('chart-intent', {
    grid: { left: 12, right: 12, top: 56, bottom: 14, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    },
    xAxis: catAxis({
      type: 'category',
      data: ['REAL baseline_a\ndeepseek-v4-flash', 'stub oracle 上界\n不参与回归'],
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 12, lineHeight: 17, interval: 0 }
    }),
    yAxis: [
      valAxis({
        type: 'value',
        name: '准确率',
        nameTextStyle: { color: C.muted, fontFamily: FONT, fontSize: 11 },
        min: 0,
        max: 1,
        axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11, formatter: function (v) { return Math.round(v * 100) + '%'; } }
      }),
      valAxis({
        type: 'value',
        name: '平均 Token/次',
        nameTextStyle: { color: C.muted, fontFamily: FONT, fontSize: 11 },
        min: 0,
        max: 250,
        splitLine: { show: false }
      })
    ],
    series: [
      {
        name: '意图准确率',
        type: 'bar',
        barWidth: 56,
        data: [0.744, 0.992],
        itemStyle: { color: C.accent, borderRadius: [4, 4, 0, 0] },
        label: barLabel(function (p) { return (p.value * 100).toFixed(1) + '%'; })
      },
      {
        name: '平均 Token/次',
        type: 'bar',
        yAxisIndex: 1,
        barWidth: 56,
        data: [225, 112],
        itemStyle: { color: C.accent2, borderRadius: [4, 4, 0, 0] },
        label: barLabel(function (p) { return p.value + ' tok'; })
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        top: 30,
        style: {
          text: '250 例 · REAL 0.744 vs oracle 0.992 · 后者不代表真实模型',
          fontSize: 11,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  /* ── 图 4 · 工具调用协议对比：native（bind_tools）vs fallback（文本协议） ── */
  mount('chart-tool', {
    grid: { left: 12, right: 12, top: 56, bottom: 8, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 },
      formatter: function (params) {
        var html = params[0].name + '<br/>';
        params.forEach(function (p) {
          html += p.marker + p.seriesName + '：' + (p.value == null ? '—' : p.value.toFixed(3)) + '<br/>';
        });
        return html;
      }
    },
    xAxis: catAxis({
      type: 'category',
      data: ['决策准确率', '工具名准确率', '参数准确率', '完全匹配\nexact', '误调用率\nFPR', '漏调用率\nFNR'],
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 11.5, lineHeight: 15, interval: 0 }
    }),
    yAxis: [
      valAxis({
        type: 'value',
        min: 0,
        max: 1,
        axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11, formatter: function (v) { return v.toFixed(1); } }
      })
    ],
    series: [
      {
        name: 'native（bind_tools · REAL · 40例）',
        type: 'bar',
        barWidth: 26,
        data: [0.75, 0.9, 0.88, 0.675, 0.6, 0.04],
        itemStyle: { color: C.accent, borderRadius: [3, 3, 0, 0] },
        label: barLabel(function (p) { return p.value.toFixed(2); })
      },
      {
        name: 'fallback（文本协议 · stub oracle）',
        type: 'bar',
        barWidth: 26,
        data: [1.0, 1.0, 1.0, 1.0, 0.0, 0.0],
        itemStyle: { color: C.accent2, borderRadius: [3, 3, 0, 0] },
        label: barLabel(function (p) { return p.value.toFixed(2); })
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        top: 30,
        style: {
          text: 'fallback 1.0 仅证明 oracle 接线；不可与 REAL native 作模型优劣比较',
          fontSize: 11,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  /* ── 图 6 · 技能注入策略：全量 vs 渐进式披露 ── */
  mount('chart-skill', {
    grid: { left: 12, right: 12, top: 56, bottom: 14, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    },
    xAxis: catAxis({
      type: 'category',
      data: ['全量注入\nfull', '渐进式披露\nprogressive'],
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 12, lineHeight: 17, interval: 0 }
    }),
    yAxis: [
      valAxis({
        type: 'value',
        name: '平均 prompt Token',
        nameTextStyle: { color: C.muted, fontFamily: FONT, fontSize: 11 },
        min: 0,
        max: 3000
      }),
      valAxis({
        type: 'value',
        name: '平均延迟 (ms)',
        nameTextStyle: { color: C.muted, fontFamily: FONT, fontSize: 11 },
        min: 0,
        max: 2500,
        splitLine: { show: false }
      })
    ],
    series: [
      {
        name: '平均 prompt Token',
        type: 'bar',
        barWidth: 62,
        data: [2763.4, 678.9],
        itemStyle: { color: C.accent, borderRadius: [4, 4, 0, 0] },
        label: barLabel(function (p) { return Math.round(p.value).toLocaleString() + ' tok'; })
      },
      {
        name: '平均延迟 (ms)',
        type: 'bar',
        yAxisIndex: 1,
        barWidth: 62,
        data: [1103, 1774],
        itemStyle: { color: C.accent2, borderRadius: [4, 4, 0, 0] },
        label: barLabel(function (p) { return Math.round(p.value) + ' ms'; })
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        top: 30,
        style: {
          text: 'REAL · 30 例 · Token -75.4%；准确率 0.767 → 0.633',
          fontSize: 11,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  /* ── 图 8 · 固定 30 文档 × 20 查询的小样本检索回归 ── */
  mount('chart-rag', {
    grid: { left: 12, right: 12, top: 56, bottom: 8, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    },
    xAxis: catAxis({
      type: 'category',
      data: ['BM25 单路', '向量单路', 'RRF 混合', '混合 + qwen3-rerank'],
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 11.5, interval: 0 }
    }),
    yAxis: [
      valAxis({
        type: 'value',
        min: 0,
        max: 1,
        axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11, formatter: function (v) { return v.toFixed(1); } }
      })
    ],
    series: [
      {
        name: 'recall@5',
        type: 'bar',
        barWidth: 24,
        data: [0.6667, 0.9667, 0.9500, 0.9667],
        itemStyle: { color: C.accent, borderRadius: [3, 3, 0, 0] },
        label: barLabel(function (p) { return p.value.toFixed(2); })
      },
      {
        name: 'MRR',
        type: 'bar',
        barWidth: 24,
        data: [0.75, 1.0, 0.9125, 0.95],
        itemStyle: { color: C.accent2, borderRadius: [3, 3, 0, 0] },
        label: barLabel(function (p) { return p.value.toFixed(2); })
      },
      {
        name: 'nDCG@5',
        type: 'bar',
        barWidth: 24,
        data: [0.6596, 0.9688, 0.9041, 0.9283],
        itemStyle: { color: C.ok, borderRadius: [3, 3, 0, 0] },
        label: barLabel(function (p) { return p.value.toFixed(2); })
      }
    ],
    graphic: [{
      type: 'text',
      right: 14,
      bottom: 8,
      style: {
        text: 'Qwen text-embedding-v3 + qwen3-rerank · 2026-09-09 REAL 质量门',
        fontSize: 10.5,
        fontFamily: FONT,
        fill: C.muted
      }
    }]
  });

  /* ── 图 10 · 生成质量：LLM-as-Judge 加权分 vs 上下文忠实度 ── */
  var genScenarios = [
    { name: '共情 empathy（15 例）', overall: 4.93, faith: null },
    { name: '对抗安全 adversarial（8 例）', overall: 4.83, faith: null },
    { name: '计划提案 plan（13 例）', overall: 4.97, faith: 5.00 },
    { name: '树洞摘要 treehole（5 例）', overall: 4.72, faith: 5.00 },
    { name: '洞察 insight（5 例）', overall: 4.64, faith: 4.60 },
    { name: '多轮对话 multiturn（3 例）', overall: 4.93, faith: 5.00 }
  ].reverse(); // category 轴自下而上，反转后共情置顶

  mount('chart-gen', {
    grid: { left: 12, right: 40, top: 52, bottom: 10, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 },
      formatter: function (params) {
        var html = params[0].name + '<br/>';
        params.forEach(function (p) {
          if (p.value == null) return;
          html += p.marker + p.seriesName + '：' + p.value.toFixed(2) + ' / 5<br/>';
        });
        return html;
      }
    },
    xAxis: valAxis({
      type: 'value',
      min: 0,
      max: 5,
      axisLabel: { color: C.muted, fontFamily: FONT, fontSize: 11, formatter: '{value}' }
    }),
    yAxis: catAxis({
      type: 'category',
      data: genScenarios.map(function (d) { return d.name; }),
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    }),
    series: [
      {
        name: 'overall 加权分',
        type: 'bar',
        barWidth: 16,
        data: genScenarios.map(function (d) { return d.overall; }),
        itemStyle: { color: C.accent, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 11, color: C.ink, formatter: function (p) { return p.value.toFixed(2); } }
      },
      {
        name: '上下文忠实度',
        type: 'bar',
        barWidth: 16,
        data: genScenarios.map(function (d) { return d.faith; }),
        itemStyle: { color: C.accent2, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 11, color: C.ink, formatter: function (p) { return p.value == null ? '' : p.value.toFixed(2); } }
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        bottom: 10,
        style: {
          text: '多轮 coherence 1.00（3/3）· 树洞 4.72 为三次门末轮（文件仍 4.35）',
          fontSize: 10.5,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  /* ── 图 12 · 官方 JD 方向与仓库证据强度（非市场频率） ── */
  var jdSkills = [
    { name: 'RAG 与检索评测', value: 3, covered: true },
    { name: '记忆与上下文', value: 3, covered: true },
    { name: '工具调用 / MCP', value: 2, covered: true },
    { name: 'LangGraph 编排', value: 2, covered: true },
    { name: '任务规划 / Skill', value: 2, covered: true },
    { name: '异常恢复 / 可观测', value: 2, covered: true },
    { name: '模型微调', value: 0, covered: false }
  ].reverse();

  mount('chart-jd', {
    grid: { left: 12, right: 52, top: 34, bottom: 10, containLabel: true },
    legend: legend(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 },
      formatter: function (params) {
        var p = params[0];
        var labels = ['无仓库证据', '基础接线', '有实现与测试', '有固定评测基线'];
        return p.name + '：' + labels[p.value];
      }
    },
    xAxis: valAxis({
      type: 'value',
      min: 0,
      max: 3,
      interval: 1,
      axisLabel: {
        color: C.muted, fontFamily: FONT, fontSize: 11,
        formatter: function (v) { return ['无', '接线', '实现+测试', '固定基线'][v] || ''; }
      }
    }),
    yAxis: catAxis({
      type: 'category',
      data: jdSkills.map(function (d) { return d.name; }),
      axisLabel: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    }),
    series: [
      {
        name: '仓库现有证据',
        type: 'bar',
        barWidth: 17,
        data: jdSkills.map(function (d) { return d.covered ? d.value : null; }),
        itemStyle: { color: C.accent, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 11, color: C.ink, formatter: function (p) { return p.value == null ? '' : ['无', '接线', '实现+测试', '固定基线'][p.value]; } }
      },
      {
        name: '未形成仓库证据',
        type: 'bar',
        barWidth: 17,
        data: jdSkills.map(function (d) { return d.covered ? null : d.value; }),
        itemStyle: { color: C.accent2, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 11, color: C.ink, formatter: function (p) { return p.value == null ? '' : '未覆盖'; } }
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        bottom: 10,
        style: {
          text: '方向来自官方 JD；0–3 为仓库证据等级，不是市场频率，也不是岗位胜任度',
          fontSize: 10.5,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  /* ── 图 13 · 架构演进证据自评（非 JD 覆盖率） ── */
  mount('chart-radar', {
    tooltip: {
      backgroundColor: '#fff',
      borderColor: C.rule,
      textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 }
    },
    legend: legend({ top: 0 }),
    radar: {
      indicator: [
        { name: '编排框架\n(LangGraph)', max: 100 },
        { name: '记忆与上下文', max: 100 },
        { name: 'RAG 全链路', max: 100 },
        { name: '任务规划', max: 100 },
        { name: '原生工具调用\n(Function Calling)', max: 100 },
        { name: 'MCP 工具生态', max: 100 },
        { name: '评估与工程化', max: 100 }
      ],
      radius: '56%',
      center: ['50%', '57%'],
      axisName: { color: C.ink, fontFamily: FONT, fontSize: 11.5, lineHeight: 15 },
      axisLine: { lineStyle: { color: C.rule } },
      splitLine: { lineStyle: { color: C.rule } },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0)', 'rgba(241,238,230,0.55)'] } }
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 4,
        data: [
          {
            name: 'v2（报告发出时）',
            value: [40, 90, 92, 72, 25, 0, 80],
            itemStyle: { color: C.muted },
            lineStyle: { color: C.muted, width: 1.5, type: 'dashed' },
            areaStyle: { color: 'rgba(130,123,109,0.06)' }
          },
          {
            name: 'v3（MCP 合入前）',
            value: [92, 90, 95, 88, 75, 0, 90],
            itemStyle: { color: C.accent2 },
            lineStyle: { color: C.accent2, width: 2 },
            areaStyle: { color: 'rgba(176,123,79,0.08)' }
          },
          {
            name: '当前分支（待交付复核）',
            value: [92, 90, 95, 90, 75, 85, 94],
            itemStyle: { color: C.accent },
            lineStyle: { color: C.accent, width: 2.5 },
            areaStyle: { color: C.accentSoft },
            label: { show: true, color: C.accent, fontFamily: FONT, fontSize: 11, formatter: function (p) { return p.value; } }
          }
        ]
      }
    ],
    graphic: [
      {
        type: 'text',
        right: 14,
        bottom: 10,
        style: {
          text: '主观证据强度，仅展示演进；不代表市场覆盖率或岗位胜任度',
          fontSize: 10.5,
          fontFamily: FONT,
          fill: C.muted
        }
      }
    ]
  });

  window.addEventListener('resize', function () {
    registry.forEach(function (c) { c.resize(); });
  });
})();
