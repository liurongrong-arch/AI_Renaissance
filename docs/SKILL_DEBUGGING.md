# Skill 调试指南 —— 让 Agent 真正有效的最简方案

> **核心认知：Agent 是壳，Skill 是魂。**
> Agent 只是调用入口，`analyze()` 里的分析逻辑（即 Skill）才决定输出质量。
> 所以调试的重点是：**把 Skill 调好，再塞进 Agent**。

---

## 概念澄清：Agent vs Skill

```
┌─────────────────────────────────────────────┐
│  Agent（壳）                               │
│  · 继承 BaseAgent                         │
│  · 负责：接收股票代码 → 调用 Skill → 返回 Signal │
│  · 代码固定，不需要反复改                │
│                                             │
│  Skill（魂）                               │
│  · 真正的分析逻辑                          │
│  · 可以是：Prompt + LLM / 计算函数 / 规则引擎  │
│  · 需要反复调试，直到输出稳定可靠          │
└─────────────────────────────────────────────┘
```

**调试顺序：**
1. 在 **WorkBuddy / Trae** 上把 Skill（提示词/逻辑）调通
2. 把调好的 Skill 固化到 `agent.py` 的 `analyze()` 里
3. 用本地调试 UI 验证 Signal 输出
4. 提交 PR

---

## 方案一：纯 Prompt Skill（最适合小白）

如果你的 Agent 分析逻辑是用 **自然语言 + LLM** 实现的（大多数财务/新闻类 Agent 都是这样），调试流程如下：

### 第1步：在 WorkBuddy 里调试 Prompt

打开 WorkBuddy，用对话方式把你的分析思路"说清楚"：

```
我现在要做一个【现金流验证】的 Agent：

请帮我设计一套分析框架，输入是：
- 经营活动现金流量净额（CF）
- 净利润（NP）

判断规则：
- CF / NP > 1.2  → 利润质量优秀（看多）
- CF / NP < 0.8  → 利润质量存疑（看空）
- 中间          → 中性

请给我一个完整的 Prompt，让我能把这套逻辑
封装成 Skill，最终输出标准 Signal 格式。
```

把 WorkBuddy 返回的 Prompt 反复迭代，直到：
- 输出格式稳定（永远是 JSON，包含 direction/confidence/reasoning）
- 测试10个股票代码，判断都符合预期

### 第2步：把调试好的 Prompt 固化到 Skill 文件

项目里每个 Agent 可以有一个对应的 `skill.md`（提示词模板）：

```markdown
# agents/research/financial/cash_flow/skill.md

你是一个专业的财报分析专家，专注现金流验证。

## 输入数据
- 经营活动现金流量净额：{cash_flow}
- 净利润：{net_profit}
- 股票代码：{stock_code}

## 分析规则
1. 计算 现金流比率 = cash_flow / net_profit
2. 若比率 > 1.2 → direction=bullish，confidence=min(ratio/2, 0.95)
3. 若比率 < 0.8 → direction=bearish，confidence=min((1-ratio)/0.5, 0.9)
4. 否则 → direction=neutral，confidence=0.5

## 输出格式（必须严格遵守）
```json
{
  "direction": "bullish|bearish|neutral",
  "confidence": 0.0~1.0,
  "reasoning": "一句话说明判断理由",
  "signals": ["具体信号1", "具体信号2"]
}
```
```

### 第3步：Agent 中调用 Skill

```python
# agents/research/financial/cash_flow/agent.py

class CashFlowAgent(BaseAgent):

    def analyze(self, stock_code: str) -> Signal:
        # 1. 获取数据
        data = self._get_data(stock_code)

        # 2. 读取 Skill（Prompt 模板）
        skill_prompt = self._load_skill()

        # 3. 调用 LLM（或直接计算）
        result = self._call_skill(skill_prompt, data)

        # 4. 转成标准 Signal
        return self._to_signal(result, stock_code)

    def _load_skill(self) -> str:
        skill_path = Path(__file__).parent / "skill.md"
        return skill_path.read_text(encoding="utf-8")

    def _call_skill(self, prompt: str, data: dict) -> dict:
        """
        Skill 调用入口 —— 这里是调试重点！

        方式A：纯计算（无需 LLM，最快最稳）
        方式B：调用 LLM（适合复杂判断）
        方式C：调用 WorkBuddy API（远程调试好的 Skill）
        """
        # 方式A：纯计算（推荐，不依赖外部 API）
        ratio = data["cash_flow"] / data["net_profit"] if data["net_profit"] else 0
        if ratio > 1.2:
            return {"direction":"bullish","confidence":min(ratio/2,0.95),"reasoning":f"现金流比率{ratio:.2f}，利润质量优秀","signals":[f"现金流比率{ratio:.2f}"]}
        # ...

        # 方式B：调用 LLM（需要 API Key）
        # import os, requests
        # response = requests.post("https://api.openai.com/v1/chat/completions",
        #     headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
        #     json={"model":"gpt-4o","messages":[{"role":"system","content":prompt},{"role":"user","content":str(data)}]}
        # )
        # return json.loads(response.json()["choices"][0]["message"]["content"])

    def _to_signal(self, result: dict, stock_code: str) -> Signal:
        return Signal(
            direction=result["direction"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            signals=result.get("signals", []),
            source=self.name,
            stock_code=stock_code,
            signal_type="financial",
        )
```

---

## 方案二：在 Trae 里调试（适合有研发经验的）

Trae 是字节跳动的 AI IDE，可以直接在里面：

1. 打开 `AIRenaissance/` 项目
2. 直接对话让 Trae 帮你写 `analyze()` 逻辑
3. 实时运行、实时看 Signal 输出
4. 调好了直接 Commit

**Trae 调试技巧：**
- 用 `#` 选中 `agent.py` 和 `signal.py`，让 Trae 只关注这两个文件
- 让 Trae 先写单元测试：`test_cash_flow.py`，用真实数据验证
- 反复让 Trae 迭代，直到所有测试用例通过

---

## 方案三：WorkBuddy 远程调试 Skill（最推荐）

如果你已经在 WorkBuddy 里把分析思路说清楚了，可以让 WorkBuddy **直接生成可运行的 Python 代码**：

```
我在做 AI Renaissance 项目的现金流验证 Agent，
我已经搞清楚了分析逻辑：

现金流比率 = 经营现金流 / 净利润
> 1.2 → 看多，置信度 = min(ratio/2, 0.95)
< 0.8 → 看空，置信度 = min((1-ratio)/0.5, 0.9)
否则 → 中性

请直接帮我生成 analyze() 方法的完整代码，
要求返回标准 Signal 对象，包含 direction/confidence/reasoning/signals 字段。
```

把 WorkBuddy 生成的代码直接复制进 `agent.py`，然后用本地调试 UI 验证。

---

## 调试检查清单

提交 PR 前，确认以下每一项：

| 检查项 | 怎么检查 |
|--------|---------|
| Signal 格式正确 | 用调试 UI 运行，看输出是否包含 direction/confidence/reasoning |
| 置信度在 0~1 之间 | 调试 UI 的置信度显示应为 0%~100% |
| 推理说明清晰 | reasoning 字段应该是一句人话，不是乱码 |
| 异常处理 | 故意传一个错误股票代码，看是否返回 neutral（而不是报错崩溃）|
| 边界条件 | 净利润=0 时会不会报错？用调试 UI 测一下 |

---

## 常见问题

### Q：我的 Agent 需要调用 LLM，API Key 怎么处理？

**A：** 不要把 API Key 写进代码！用环境变量：

```python
# config.py
import os
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("MODEL_NAME", "gpt-4o")

# .gitignore 里确保 .env 不会被提交
```

### Q：Skill 和 Agent 的代码都写在一个文件里吗？

**A：** 推荐分开，方便独立调试：

```
agents/research/financial/cash_flow/
├── agent.py      # Agent 壳（固定）
├── skill.md      # Skill Prompt（经常改）
├── config.py     # 配置参数
└── __init__.py
```

### Q：我怎么知道我的 Agent 效果好不好？

**A：** 三个标准：
1. **格式稳定**：10次运行，Signal 格式永远正确
2. **判断合理**：拿3只你熟悉的股票手动验证，Agent 结论和你判断一致
3. **置信度区分度**：好股票 confidence>0.7，差股票 confidence<0.3，不要永远输出 0.5

---

*最后更新：2026-05-01*
