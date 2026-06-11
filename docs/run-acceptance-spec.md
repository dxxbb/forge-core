# Forge Run v1 验收 Spec

本文是 [run-design.md](run-design.md) v1 的规范性验收条款。条款编号 `AC-<组>-<序>`,每条可测;实现期测试名应能映射回条款。术语以 [CONTEXT.md](../CONTEXT.md) 为准。

**v1 范围**:资产分区与编译器 gate、账本与对账、forge run(CLI 骨架 + playbook)、认证、大赦迁移、portal 只读收缩。
**v1 非目标**:cron 离线蒸馏、外部 digest、serve 决策端点、语义级冲突/重复检测、提问学习、规则区自动瘦身。

---

## 1. 分区(AC-ZONE)

**AC-ZONE-1** 分区由 owner 持有的配置文件声明(规则区 = 路径/段类清单,其余默认状态区);内容文件不能自我声明区属。

**AC-ZONE-2** zones 配置文件本身属于规则区(改它要过 gate)。

**AC-ZONE-3** `forge doctor` 报告:未被任何区覆盖的 canonical 路径(配置漏洞告警)、规则区编译后行数与预算(默认 150,可配)的对比。

**AC-ZONE-4** bootstrap:`forge zone init` 把当前规则区内容认证为 verified 基线,显式输出基线清单;未初始化时 gate 不生效并在 doctor 中告警(不静默假装受保护)。

## 2. 编译器 gate(AC-GATE)

**AC-GATE-1** 规则区文件现内容 ≠ verified 快照时,编译该段使用 **verified 快照**,而非磁盘现内容;编译产物中 agent 读到的规则永远是 owner 批准过的版本。

**AC-GATE-2** 上述差异同时生成一条待问项(类型 rule-change,含 before/after diff 与差异来源线索),进入下次 run 的问单;编译诊断中可见。

**AC-GATE-3** 差异的解除仅两条路:run 中 owner 批准(快照更新至新内容)或驳回(磁盘文件回退至快照);二者都落账。

**AC-GATE-4** 状态区文件不受 gate 限制,正常按磁盘现内容编译;其段头/元数据携带认证日期。

## 3. 账本(AC-LEDGER)

**AC-LEDGER-1** 账本条目 `system/ledger/<id>.md`,id 形如 `led-YYYYMMDD-HHMMSS-<slug>`;frontmatter 必含:kind、id、created_at、origin(run id / 会话 / manual-reconciled)、patch(target / anchor / mode / base_digest)、evidence(可空于 manual)、commit 关联方式(trailer)。

**AC-LEDGER-2** 经 CLI 的每笔 canonical 写入产生:一条账本条目 + 一次 scoped commit(仅含目标文件、本次重编译产物、该账本条目),commit message 末行 trailer `Ledger-Id: <id>`,`git log --grep` 可反查。

**AC-LEDGER-3(对账)** `forge ledger reconcile`(run 内必跑,亦可单独跑):对照 git 状态捕获脱账编辑——状态区差异自动补账(origin=manual-reconciled);规则区差异不补账,转待问项(与 AC-GATE-2 同源去重)。

**AC-LEDGER-4(stale 守卫)** mode=replace 的写入在 apply 前校验 base_digest;漂移则拒绝写入并报告,不盲改(append/create 的 digest 仅作记录)。

**AC-LEDGER-5(原子性)** 写入流水线(apply → 重编译 → 验证 → commit)任一步失败,已写文件回滚至字节一致,条目记录失败原因,可重试;不产生半套状态。

**AC-LEDGER-6(单笔撤销)** `forge ledger revert <id>`:逆向 apply 该条目的 patch(锚点仍可定位时),产生新的账本条目与 commit;锚点已漂移则拒绝并说明,不猜测。

**AC-LEDGER-7(冲突守卫)** 新写入的目标段落与**已认证**内容重叠且内容相异 → 不落地,生成待问项(类型 conflict);冲突永不静默覆盖已认证内容。

**AC-LEDGER-8(溯源)** 给定 canonical 文件的任一行,`forge ledger blame <path> --line N` 能给出:最近一次触及该行的账本条目、出处、时间、commit。

## 4. Forge run(AC-RUN)

**AC-RUN-1** `forge run status`:距上次 run 天数、待问项计数(按类型)、最旧待问项 age、各状态文件未认证笔数/天数。零待办时明确说零。

**AC-RUN-2** `forge run open`:创建 run 记录 `system/run/<id>.md`,列出输入清单(上次 run 之后新增的 capture/记忆文件,以内容指纹为键);重复 open 接续未关闭的 run(可恢复),不重复收集。

**AC-RUN-3** run 内落账走 AC-LEDGER-2 通道,run 记录追加落账清单;同一输入指纹在多次 run 间不被重复落账(幂等)。

**AC-RUN-4(问单)** `forge run ask [--budget N]`(默认 5):按固定问序输出待问项——conflict 全量置顶(不受预算压缩)→ rule-change → 到期认证(未认证笔数/天数最高者优先);每个待问项携带:证据原文摘录、before/after diff、影响(由 audit graph 计算的 section/runtime 链)。超预算项明确标注"顺延"。**从未认证过的文件不进入问单预算**——认证自 owner 首次盖章开始,此前其新鲜度仅在 `run status` 中展示,不主动追问。

**AC-RUN-5(裁决执行)** `forge run decide <ask-id> --approve|--reject [--note]`:approve 走 AC-LEDGER-5 全流水线(规则区项同时更新 verified 快照);reject 落账留痕、規則区项回退磁盘文件。执行结果即时回写 run 记录。

**AC-RUN-6** `forge run close`:重编译全部受影响 config、验证映射、生成 run 报告(落账 N / 裁决 M / 顺延 K / 全部规则区变更显著列出)、更新 last-run 标记;close 后 run 记录不可再追加。

**AC-RUN-7** run 的语义步骤(蒸馏、拆分、patch 撰写)不在 CLI 内实现;CLI 的输入输出契约(open 的输入清单、ask 的问单、decide 的裁决)足以让 run skill/playbook 驱动整场对话。playbook 以 skill 形态交付并随 v1 发布。

## 5. 认证(AC-CERT)

**AC-CERT-1** `forge certify <path>`:更新该状态文件的认证日期(`system/certified/index.yaml`)与认证快照(`system/certified/<path>`),并产生一次 scoped commit;此后"未认证变更"基于新快照计算。run 内的认证裁决走同样的快照+commit 路径。

**AC-CERT-2** `forge state show <path>`(及 portal 对应视图):渲染文件内容,高亮认证快照之后的全部变更,每处标注出处(账本条目 / 日期);无未认证变更时明确说明。

**AC-CERT-3** 认证状态影响 AC-LEDGER-7 的冲突判定基准:守卫保护的是"已认证内容",未认证内容可被后续写入正常更新(各自留痕)。

## 6. 大赦迁移(AC-MIG)

**AC-MIG-1** `forge migrate amnesty`:对现存 system/pr 工作台与积压——状态类条目合并写入对应状态文件(逐笔落账,标记未认证);明显过期的(易变类 × 超龄)标记 expired 仅留痕不写入;规则候选生成待问项。

**AC-MIG-2** 迁移后原工作台文件标记归档(frontmatter),不再接受决策写入;迁移产物清单写入迁移报告。

**AC-MIG-3** 幂等:重复执行不重复落账、不重复生成待问项(键 = 工作台 id + 条目 id)。

**AC-MIG-4** 对真实形态数据(38 条:5 triaged + 33 untriaged)的迁移结果:进入待问项的规则候选 ≤ 5 条,其余全部落入状态文件或 expired 留痕——迁移不得再造一个 38 条的清单。

## 7. Portal 收缩(AC-PORTAL)

**AC-PORTAL-1** portal 为只读审计面:节点/段落展示区属标识、认证新鲜度(certified 日期 + 未认证笔数);不提供决策操作。账本溯源 v1 由 `forge ledger blame` 提供,portal 内联溯源链接列为 v1.1。

**AC-PORTAL-2** 待问项在 portal 以决策卡形态可浏览(复用既有卡:证据 → diff → 影响),卡上明示"裁决在 forge run 中进行"。

## 8. 验收方法

**自动化**:每条 AC 至少一个行为测试,测试名用领域术语映射条款(如 `test_rule_zone_drift_compiles_from_verified_snapshot` ↔ AC-GATE-1);git/编译/文件全部走真实 tmp 环境,不 mock 自有代码;全量回归保持绿。

**手工走查**(v1 收尾,在真实 personalOS workspace):
1. `forge zone init` → doctor 确认基线与覆盖完整;
2. `forge migrate amnesty` → 确认 38 条积压按 AC-MIG-4 收敛;
3. 让 agent 直接改一个规则区文件 → 编译,确认产物仍是 verified 版本、待问项生成;
4. 完整跑一次 forge run(含至少一个冲突、一个规则候选、一次认证)→ 确认问序、预算、裁决执行、run 报告、commit trailer;
5. `forge ledger revert` 撤销其中一笔 → 确认单笔逆向、留痕;
6. `forge ledger blame` 任取一行 → 确认 30 秒内答出"为什么在这"。

**v1 完成定义**:全部 AC 通过 + 手工走查 6 步通过 + run playbook skill 可用 + CONTEXT.md 术语在测试名中可 grep 到。
