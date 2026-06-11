# Forge Run Playbook(agent 会话协议)

这是驱动一场 forge run 的 skill 内容(AC-RUN-7)。CLI 提供确定性骨架,本协议规定 agent 在会话里怎么把它开成一场结算对话。安装方式:并入 personalOS 的 forge skill(`~/.claude/skills/forge/SKILL.md`)的 run 章节。

## 触发

owner 说"做一次 forge / forge run / 结算一下"。**只能由 owner 发起**;agent 永不在工作会话里主动提治理话题(可以回答 owner 的主动询问,如"有什么待审的" → `forge run status`)。

## 流程

```
1. forge run status          → 开场白:距上次 N 天、待问几条、状态新鲜度
2. forge run open            → 拿到新输入清单(capture 指纹去重)
3. 蒸馏落账(语义工作,agent 在会话内做):
   - 逐个读 inputs 里的 capture,拆成原子事实(一笔一个事实)
   - 状态类 → forge 写入:每笔走 ledger(带 origin=run:<id>、evidence=capture 路径)
     ※ 写入被 held(冲突)是正常结果,留给问单,不要绕过
   - 规则候选 → 直接写进规则区文件(gate 会扣住它,自动成为待问项)
   - 拿不准放哪的 → 不写,如实告诉 owner
4. forge run ask --budget 5  → 逐条用人话呈现:一句话讲清"为什么改/改成什么/影响谁",
                                证据和 diff 念重点,不要倾倒原文
5. owner 一句话裁决 → forge run decide <id> --approve/--reject [--note]
   立即报执行结果(commit / 回退 / 仍冲突)
6. 认证项:owner 说"念重点" → 念 uncertified diff;说"盖章" → decide approve
7. forge run close           → 复述报告:落账 N · 裁决 M · 顺延 K
```

## 行为铁律

- **预算神圣**:owner 说"只有 1 分钟"→ `--budget 0`(只剩冲突);顺延项一句话带过,不展开;
- **冲突先行**:问单顺序是固定的,不重排;
- **不硬凑**:没有待问项就说"没有",没有可落账的就说"没有"——空 run 是合法结果;
- **裁决即执行**:decide 之后立刻报结果,不留"我稍后处理";
- **绝不代替 owner 决策**:规则区与冲突项,任何"显然该批"的判断都只能作为建议语气出现;
- **结束即干净**:close 之后不留尾巴,顺延项属于下一次 run,不在本次追问。

## 失败处理

- decide 报 stale / failed → 如实报错误原因,把该项标记为下次 run 重备,继续下一项;
- 蒸馏中发现 capture 信息与 canonical 矛盾但写入未被 held(未认证内容)→ 正常落账即可,认证机制会让 owner 在读时看到;
- run 中断 → 下次 `forge run open` 自动续上,已落账的不会重做。
