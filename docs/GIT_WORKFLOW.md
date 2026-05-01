# Git 协作工作流（超简单版）

> 目标：**你只管写你的 Agent，永远不影响别人的代码**
> 核心思路：`main` ← `develop` ← `你的功能分支`

---

## 分支结构

```
main        ← 生产分支，永远可直接运行
 └─ develop ← 集成分支，所有 Agent 在这里汇合
      └─ agent/你的名字-你的agent  ← 你自己的分支（随便改）
```

---

## 三步提交代码（记住这3条命令就够了）

### 第1步：切换到 develop 并创建你自己的分支

```bash
# 只需第一次做
git clone git@github.com:duolongworld/AI_Renaissance.git
cd AI_Renaissance

# 每次开发前做
git checkout develop
git pull origin develop
git checkout -b agent/你的名字-你的agent名
```

> 例子：`git checkout -b agent/duolong-现金流验证`

### 第2步：写代码，提交到你自己的分支

```bash
# 写代码...
# 写完提交
git add agents/research/financial/你的agent目录/
git commit -m "feat: 添加现金流验证Agent"
git push origin agent/你的名字-你的agent名
```

### 第3步：开一个 PR（Pull Request）到 develop

1. 推送后会看到 GitHub 提示：**"Compare & pull request"**
2. 点进去，确保 **base: develop** ← **compare: agent/你的分支**
3. 填写 PR 模板（见下）
4. 点 **Create pull request**
5. 等 Review 通过后，你的代码就合入了

✅ **永远不需要直接碰 `main` 或 `develop` 分支**

---

## PR 模板（直接抄）

```markdown
## Agent 名称
现金流验证 Agent

## 负责人
@你的GitHub用户名

## 做了什么
- 实现了 analyze() 方法
- 使用经营现金流 / 净利润 比率判断利润质量

## 如何测试
```python
from agents.research.financial.cash_flow.agent import CashFlowAgent
agent = CashFlowAgent(config={})
signal = agent.analyze("600519")
print(signal)
```

## 截图/输出
（粘贴终端输出或 Signal 对象）

## Checklist
- [ ] 代码可以运行
- [ ] 返回的是标准 Signal 对象
- [ ] 有异常处理（try/except）
```

---

## 常用命令速查

| 场景 | 命令 |
|------|------|
| 更新 develop | `git checkout develop && git pull` |
| 新建功能分支 | `git checkout -b agent/名字-功能` |
| 切回 develop | `git checkout develop` |
| 删除已合并的分支 | `git branch -d agent/名字-功能` |
| 强制同步远程 develop | `git checkout develop && git reset --hard origin/develop` |

---

## ❌ 千万不要这样做

```bash
# ❌ 不要直接往 main 或 develop 提交
git push origin main
git push origin develop

# ❌ 不要在没有 PR 的情况下修改别人的文件
# ❌ 不要把测试数据、日志文件提交上来
```

---

## ✅ 你应该这样做

```bash
# ✅ 永远从 develop 拉取最新代码
git checkout develop
git pull origin develop
git checkout -b agent/你的功能

# ✅ 提交前先 pull develop，解决冲突（如果有）
git checkout develop
git pull
git checkout agent/你的功能
git rebase develop

# ✅ 一个 Agent 一个分支，保持 PR 小而清晰
```

---

## 遇到问题？

在群里 @ 管理员，或创建 GitHub Issue。

*最后更新：2026-05-01*
