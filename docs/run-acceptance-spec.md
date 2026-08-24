# Forge Run v2 验收 Spec

本文是 [run-design.md](run-design.md) v2 的规范性验收条款。条款编号 `AC-<组>-<序>`,每条可测;实现期测试名应能映射回条款。术语以 [CONTEXT.md](../CONTEXT.md) 为准。

**v2 范围**:保留资产分区、编译器 gate、账本与对账;新增 evidence disposition、Observation、Candidate Asset、晋升准入、到期关闭、三张卡预算、真实使用反馈、稳定 Source Batch、provider settlement 与 Run Contract。
**v2 非目标**:无审核自动晋升、后台 LLM cron、向量检索产品、portal 写入端点、自动判断抽象是否正确。

---

## 1. 分区(AC-ZONE)

**AC-ZONE-1** 分区由 owner 持有的配置文件声明(规则区 = 路径/段类清单,其余默认状态区);内容文件不能自我声明区属。

**AC-ZONE-2** zones 配置文件本身属于规则区(改它要过 gate)。

**AC-ZONE-3** `forge doctor` 报告:未被任何区覆盖的 canonical 路径(配置漏洞告警)、规则区编译后行数与预算(默认 150,可配)的对比。

**AC-ZONE-4** bootstrap:`forge zone init` 把当前规则区内容认证为 verified 基线,显式输出基线清单;未初始化时 gate 不生效并在 doctor 中告警(不静默假装受保护)。

## 2. 编译器 gate(AC-GATE)

**AC-GATE-1** 规则区文件现内容 ≠ verified 快照时,编译该段使用 **verified 快照**,而非磁盘现内容;编译产物中 agent 读到的规则永远是 owner 批准过的版本。

**AC-GATE-2** 上述差异若没有对应 Candidate Asset,生成完整性待问项(类型 unqualified-change,含 before/after diff),进入下次 run 的问单;编译诊断中可见。

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

**AC-RUN-1** `forge run status`:距上次 run 天数、open run、Source Signal attention/类别计数、完整性问题与 Candidate 计数、Observation 状态、promotion metrics、各状态文件 freshness。freshness 不进入待问计数。

**AC-RUN-2** `forge run open`:创建 run 记录 `system/run/<id>.md`,列出 monitor 发现的 Source Batch 与上次 run 后新增的 capture 指纹,同时自动关闭到期 Observation;Source Signal 不复制外部语料库;重复 open 接续未关闭 run,可补入新的来源类别,但不得替换已有来源批次、使既有 disposition 失效或重复处理 provider-managed capture。

**AC-RUN-3** 每个新 capture input、每个 Source Batch Review Unit 必须经 `forge run disposition` 记录且只能保留一个最新去向:`covered|one-off|volatile-state|observe|candidate|closed|defer`;批次单元用 `--item <unit-id>` 独立分流,批次级非 defer disposition 必须拒绝。`defer` 仅用于尚未开始单元结算的 Source Signal 且必须有理由。存在 unclassified input/unit 时 close 必须失败。

**AC-RUN-4(问单)** `forge run ask [--budget N]` 默认 3:conflict 与 unqualified-change 全量置顶,其后最多 N 张 pending Candidate Asset。Candidate 卡携带为什么现在提出、实际发生的 Evidence Event/evidence pointer、现有资产覆盖与缺口、为什么 owner 管的长期资产是正确落点、problem、Promotion Ground 理由、proposal、scope、exclusions、未来行为影响、准确 patch、verification 与准确裁决问题;不返回超预算 Candidate,不生成 certification-due。

**AC-RUN-5(裁决执行)** `forge run decide <candidate-id> --approve|--reject|--observe [--note]`:approve 走 AC-LEDGER-5 全流水线(规则区同时更新 verified 快照);reject 关闭卡但保留 evidence;observe 回到 Observation。执行结果即时回写 run 记录。conflict/unqualified-change 只接受 approve/reject。

**AC-RUN-6** `forge run close`:先拒绝任何 unclassified input/Review Unit;对仍返回原批单元的 Source Signal,未明确 defer 同样拒绝。带 defer 的 Run 可关闭但最终状态必须为 `incomplete`;本批完成但 provider 仍有下一批时为 `batch-complete`;无剩余为 `complete`。真正无 Source Signal、capture input、完整性问题、裁决或到期处理的空 Run 删除临时记录且不 commit。其余 Run 重编译、验证、写报告并 scoped commit;close 后返回机器核验的 commit、open Run、工作树 clean/dirty、Selection Coverage、Candidate Conclusion 与剩余 Review Unit 数;持久报告必须使用同一计数。

**AC-RUN-7** 查重、分类、跨事件抽象和 patch 撰写由 agent 完成;CLI 确定性负责持久状态、准入校验、预算、expiry、apply、gate、commit 与统计。playbook 必须要求一次只向 owner 展示一张卡。

**AC-RUN-8(Source Batch)** Agent Memory 每批最多 10 个 Review Unit 且总计最多 128 KiB,Web clipping 每批最多 5 个 Review Unit;批次 digest 只由本批 unit id 与内容 digest 决定,不包含 backlog 总数。Codex Review Unit 是 `MEMORY.md` Task Group,Claude Review Unit 是非索引 memory 文件;聚合索引/raw history/archived sessions 不进入 backlog并单独报告排除计数。首次 Memory baseline/reminder 没有具体可结算 unit 时不得生成空 batch。

**AC-RUN-9(Source Settlement)** Memory 的每个非 defer Review Unit disposition 独立 stale-check 后推进 semantic checkpoint;Web clipping 的每个非 defer Review Unit disposition写回对应 marker,其中 `covered` 必须验证 sink 是 workspace 内已存在 canonical asset。provider 仍返回原批任一 unit 时 close fail closed。checkpoint 文件若已被 Git 跟踪,必须进入 close scoped commit;真正 gitignored side state 不提交。

**AC-RUN-10(Run Contract)** `forge run next [--budget N]` 每次只返回一个 action。顺序固定为:完整性问题 → 一个未分流 Review Unit → 一条未分流 capture evidence → 预算内 Candidate → close。合同包含 input/ask id、当前 Review Unit、handler、constraints、owner visibility 与候选剩余预算;Agent 不得扩大合同范围。classify action 的 owner visibility 为 background,进度只报聚合数量,不得主动展开 covered/closed/Observation 内容;decision action 才进入前台。

**AC-RUN-11** Web clipping 与 Agent Memory 由 Source Batch 独占处理,对应的 provider-managed raw capture 不能再作为 generic `capture-evidence` 重复筛选。Memory 每次只读合同列出的一个 Review Unit 及其 evidence pointer,不得顺手扫描完整源文件或下一单元;clipping 默认只查现有 canonical sink,除非 owner 明确要求,不得启动完整 knowledge-intake。

**AC-RUN-12(Selection truth)** `candidate_conclusion=available` 仅表示已有 pending Candidate;`candidate_conclusion=none` 仅允许在 `selection_coverage=complete` 且 pending Candidate 为 0 时出现;只要仍有 Source Review Unit 或 standalone capture evidence 未分流就必须为 `unknown`。status、持久 Run report、close 终态必须共用同一待筛选清单计算,不能各自计数。Observation 已有明确 disposition,计入已筛选而非 backlog。

**AC-RUN-13(Owner decision sufficiency)** `decide-candidate` 的合同要求 Agent 用简单自然语言呈现完整卡片,不得只复述 proposal。验收不匹配固定话术,而检查 owner 是否能回答:为什么现在出现、依据是哪几次独立经历、现有资产哪里不足、为什么不是 case-by-case、准确写什么、以后什么会改变、自己正在决定什么。

## 5. 资产晋升(AC-PROMOTION)

**AC-PROMOTION-1** Observation 位于 `system/observations/`,同一 theme 合并去重后的 `event_ids` 与 evidence pointer,记录 created/last_seen/expires/state;独立事件数只按 event id 计算,同一事件的多个 pointer 不增加计数;到期只关闭记录,不删除 evidence。

**AC-PROMOTION-2** Candidate Asset 位于 `system/candidates/`;`repeated` 至少两个不同 event id,`owner-directed` 至少一个 event id + owner 明确要求未来长期沉淀的原话。`high-risk` 只改变优先级与控制路径,不能单独构成 Promotion Ground。所有 Candidate 都必须包含只描述实际发生内容的 source_context、existing_coverage、asset_fit、promotion_rationale、expected_effect、decision_question、problem、proposal、scope、至少一个 exclusion、target patch 与 verification;缺失即拒绝创建。`asset_fit` 必须说明为何 owner 管的长期资产是正确落点,而不是代码/测试、易变状态、Skill、平台通用底线或 Observation。

**AC-PROMOTION-3** Candidate 状态仅 `pending → promoted|rejected|observing`;promoted 必有 ledger entry。已决定 Candidate 默认不再进入 ask。

**AC-PROMOTION-4** 正式资产可记录 `effective|revise|retire` 的真实使用 feedback,每条必须有 evidence receipt。`run status` 报 decided、acceptance_rate、average_review_seconds、used_assets 与 feedback distribution。

## 6. 认证(AC-CERT)

**AC-CERT-1** `forge certify <path>`:更新该状态文件的认证日期(`system/certified/index.yaml`)与认证快照(`system/certified/<path>`),并产生一次 scoped commit;此后"未认证变更"基于新快照计算。run 内的认证裁决走同样的快照+commit 路径。

**AC-CERT-2** `forge state show <path>`(及 portal 对应视图):渲染文件内容,高亮认证快照之后的全部变更,每处标注出处(账本条目 / 日期);无未认证变更时明确说明。

**AC-CERT-3** 认证状态影响 AC-LEDGER-7 的冲突判定基准:守卫保护的是"已认证内容",未认证内容可被后续写入正常更新(各自留痕)。

## 7. 大赦迁移(AC-MIG)

**AC-MIG-1** `forge migrate amnesty`:对现存 system/pr 工作台与积压——状态类条目合并写入对应状态文件(逐笔落账,标记未认证);明显过期的(易变类 × 超龄)标记 expired 仅留痕不写入;规则候选生成待问项。

**AC-MIG-2** 迁移后原工作台文件标记归档(frontmatter),不再接受决策写入;迁移产物清单写入迁移报告。

**AC-MIG-3** 幂等:重复执行不重复落账、不重复生成待问项(键 = 工作台 id + 条目 id)。

**AC-MIG-4** 对真实形态数据(38 条:5 triaged + 33 untriaged)的迁移结果:进入待问项的规则候选 ≤ 5 条,其余全部落入状态文件或 expired 留痕——迁移不得再造一个 38 条的清单。

## 8. Portal 收缩(AC-PORTAL)

**AC-PORTAL-1** portal 为只读审计面:节点/段落展示区属标识、认证新鲜度(certified 日期 + 未认证笔数);不提供决策操作。账本溯源由 `forge ledger blame` 提供。

**AC-PORTAL-2** Candidate 在 portal 以只读卡浏览,显示完整 AC-RUN-4 owner decision context;卡上明示“一次只审一张,裁决在 forge run 中进行”。

## 9. 验收方法

**自动化**:每条 AC 至少一个行为测试,测试名用领域术语映射条款(如 `test_rule_zone_drift_compiles_from_verified_snapshot` ↔ AC-GATE-1);git/编译/文件全部走真实 tmp 环境,不 mock 自有代码;全量回归保持绿。

**手工走查**(v2 收尾,在真实 personalOS workspace):
1. `forge zone init` → doctor 确认基线与覆盖完整;
2. `forge migrate amnesty` → 确认 38 条积压按 AC-MIG-4 收敛;
3. 准备同一事件的两个 evidence pointer 与第二个独立 event;确认两个 pointer 仍只算一个事件、repeated Candidate 被拒绝,加入第二 event id 后才可建卡;
4. 完整跑一次 Forge Run:循环 `run next`,给全部 input disposition,确认稳定批次、最多三张卡、approve/reject/observe、三种 close 状态、最终机器事实和 commit trailer;
5. 让 agent 绕过 Candidate 直接改规则区 → 编译产物仍是 verified 版本,问单显示 unqualified-change;
6. 对 promoted asset 记录 effective/revise/retire feedback,再用 `ledger blame/revert` 验证溯源与单笔撤销。
7. 新建真实隔离任务,唯一 prompt 使用自然用户短句(如“forge 一下”);按来源可追溯、准入成立、抽象质量、资产协调、决策可理解、状态真实性、治理边界、运行成本逐项留证,任何维度证据不足都不得称为符合预期。

**v2 完成定义**:全部 AC 通过 + 手工走查 6 步通过 + packaged run playbook 可用 + CONTEXT.md 术语在测试名中可 grep 到。
