# 写入压测 · 测试报告（gb-4102）

日期：2026-11-18。本环境无 Docker/MySQL/Redis，全栈验证需在 `docker compose up -d --build` 后复核。

## 已执行

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全部 Python 语法 | `python3 -m py_compile $(find backend -name '*.py')` | 通过 |
| 前端全部 JS 语法（ESM） | `node --check`（逐个 .mjs 副本） | 通过 |
| 压测纯逻辑单测 | `python3 -I test-artifacts/gb-4102/stress_math_test.py` | 19/19 通过 |
| 压测页面渲染冒烟 | `node test-artifacts/gb-4102/stress_page_test.mjs` | 19/19 通过 |

纯逻辑覆盖：写入计划偏移确定性、分位数、从计划到达时刻起算的超时判定、积压窗口、
排队深度、时间线分桶、对账恒等式（计划=到达=入账、落库缺失/多余检测）、错误与未完结计数。
渲染冒烟覆盖：完成/排队/失败/空列表四态、尾延迟与超时对照、建索引窗口对账、样本一致性、
隔离与清理证据、结论文案、导出入口。

## 待全栈复核（需容器环境）

1. `docker compose up -d --build && docker compose exec -T backend python -m scripts.seed_demo`
2. operator 登录 → 「写入压测」发起默认参数压测 → 等待完成（约 1 分钟）。
3. 核对：两轮各 600 笔对账平衡；第二轮 p99 与超时数高于第一轮；超时后落库可查出；
   压测表已删除、telemetry 行数前后一致；审计含 stress.queue / stress.completed。
