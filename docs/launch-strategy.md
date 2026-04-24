# X 发布策略（forge-core v0.1.0）

*内部文档，不对外发。发 thread 前过一遍这份，避免踩坑。*

---

## 目标不是转化，是学习

发这个 thread 的目的不应该定成 "1000 星"、"500 fork"——v0.1 alpha 没这个量级。目标应该是：

1. **信号验证**：有没有人共振"context 是 asset、不能被工具锁走"这个命题？
2. **真实使用者**：有没有 5-10 个 builder 愿意真跑一下 `forge init`？
3. **刺点在哪**：评论区冒出来的最常见质疑是什么——决定 v0.2 要修什么

有 3-5 个来自目标圈子（AI builder / personal-OS 圈）的认真评论 = 成功。不需要 viral。

---

## 受众分层

| 受众 | 在哪 | 语言 | 关心什么 |
|---|---|---|---|
| 英文 AI builder / agent dev | X（twitter.com），关注 Karpathy、Anthropic、Codex 生态 | 英文 | "和 rulesync / claude-memory-compiler 差别"、"能不能 pip install"、"有没有 demo gif" |
| 中文技术圈 | X 中文、知乎想法、小红书 | 中文 | "AI 时代个人差异化"、"反平台锁定"、"dxy 的 personal OS 实践" |
| Karpathy LLM Wiki 跟随者 | X + Obsidian discord | 英文 | "这是 Karpathy wiki 的工程化吗" |
| Claude Code / Cursor 重度用户 | X + Reddit r/ClaudeAI、r/cursor | 英文+中文 | "我的 CLAUDE.md 已经 2000 行了，forge 能救我吗" |

**主战场是英文 X**——这里是 AI builder 圈讨论最活跃的地方，目标受众密度最高。中文做**单独一版 thread**，不是英文的翻译（中文读者关心点不一样）。

---

## 发布时间

### 英文 X 主发

**首选窗口：周二或周三，美东时间 9:30-11:00 AM**（GMT+8 周二/三 21:30-23:00）。

- 周二/周三是公认的 tech 内容 peak engagement day——周一人在恢复，周四周五分心
- 美东上午 = 美西早起 + 欧洲下班前 + 亚洲深夜滚动刷手机，三个时区都能覆盖
- 9:30 是 X 算法的 "prime time" 之一（流量池大）

### 中文 X / 知乎想法

**周六或周日晚上 GMT+8 20:00-22:00**——中文用户刷手机高峰。

### **避雷日期**

发布前 3 天查一下：

- [ ] Anthropic 有没有新模型 / 功能发布（检查 `@AnthropicAI`）
- [ ] OpenAI 有没有发布会（`@OpenAI` / `@sama`）
- [ ] Google / DeepMind 有没有大新闻
- [ ] 任何主流 AI 圈的 beef / drama 正在发酵

这些日子发，thread 会被淹没。如果撞上，推迟 3-7 天。

### **不要发的时间**

- 周五下午之后到周一早上（engagement 低 40%+）
- 美国重大节假日前后 3 天
- 中国春节 / 国庆长假（中文受众全度假）

---

## 配图策略

**关键原则**：X 算法对带图推文权重显著高过纯文字。但配图成本高，不值得每条推都配——**只配 3 条关键推**：

| 推 # | 内容 | 图 | 怎么做 |
|---|---|---|---|
| 1 | Hook（"AI 拉平，差异化从哪来"） | **对比图**：左边散乱的图标（Claude / Cursor / OpenAI memory / ChatGPT / Codex 的 logo），右边一个 forge 的 unified 结构 | Excalidraw 手绘风格，或 Figma 10 分钟搞定。可以复用 README 里那张 ASCII 图的视觉化版本 |
| 4 | "context 当数据 asset 管" | **一张真实 screenshot**：`sp/section/` 目录树 + 一段 section 的 frontmatter（可理解）+ `.forge/changelog.md` 的几行（可解释）+ `forge diff` 的输出（可控制）| 直接在你自己的 dxyOS 上截图 |
| 8 | CTA | **demo GIF 或截图**：`forge diff` 的真实输出（源改动 + compiled 预览）| 用 [asciinema](https://asciinema.org) 录 30 秒，或者 iTerm 截图 |

### 配图技术规格

- **宽高比 16:9 或 1:1**——X 预览裁切友好
- **分辨率 ≥ 1920×1080**（手机端不糊）
- **不要嵌 meme**——AI builder 圈子不吃浮夸的 meme 文化
- **字体要大**——X 默认缩略展示，文字太小看不清会被跳过
- **如果配代码截图，使用深色 terminal 主题 + syntax highlighting**（视觉更 "dev"）

### 图的风格

整个 thread 建议**统一手绘/极简风格**——Excalidraw 或 TLDraw 的风格最契合这类 builder-to-builder 内容。避免用 Figma 的 corporate 风（显得像 SaaS 营销）。

---

## 链接策略

### X 算法对外链降权。主推**不放任何外链**。

操作上：

1. **前 7 条推全部纯文字**——保证算法正常分发
2. **第 8 条（CTA）放 GitHub repo 链接**——到那时读者已经看到 "有点意思" 才会点
3. **不要放短链接（bit.ly / t.co）**——现在的 X 会额外惩罚第三方短链
4. **repo URL 要短**：`github.com/dxxbb/forge-core` 比 `github.com/dxxbb/forge-core/tree/main/docs` 好

### 后续补充链接（eval-report / article-draft 长文）放哪

**回复里放**——发完主 thread 之后，自己在第 8 条下面追一个 reply：

> "补几个链接：
>  - 完整设计文档：[link]
>  - 行为 A/B eval 报告（2-2 打平 + 位置偏见讨论）：[link]
>  - 给 personal-OS 用户的迁移指南：[link]"

这样：
- 主 thread 的算法分数不被稀释
- 认真想了解的人会往下翻 reply，他们才是你真想要的人

---

## Hashtag 和 @ mention

### Hashtag 慎用、宁少勿多

X 的 hashtag 算法和 Instagram 不一样——**多了反而降权**，被视为 spam 信号。

**推荐 0-2 个高度相关的**，放在最后一条推：

- `#ClaudeCode`（让 Claude Code 用户搜到）
- `#AIagents`（泛一点但相关）

**不推荐**：

- `#AI`（太泛，噪音比信号大）
- `#MachineLearning`（不匹配内容）
- 中文 hashtag（X 上没用）

### @ mention 策略

**不要硬 tag 大 V**（`@karpathy`、`@AnthropicAI`、`@elonmusk`——反感，也会被当 spam 信号）。

**正确姿势**：

- 在**合适时机**可以引用相关推文（quote tweet）——比如 Karpathy 当初发 LLM Wiki 的那条推，可以在你的 thread 某条里 quote 一下，作为 "顺着这个方向做了件事" 的衔接
- **回复竞品工具作者**：`rulesync` / `claude-memory-compiler` 的作者（如果他们在 X）——不是 "看看我比你强"，是 "我补了你刻意不做的那半，可以组合用"。这种姿态被 builder 圈尊重

---

## Follow-up 节奏

### 发出去的头 2 小时

**守着手机**。X 在第一个 90 分钟决定会不会进 "bigger pool"（推给更多人）。这窗口：

- **立刻回复**有实质内容的评论（"agree"、"cool" 这种点赞不用回，问具体问题或挑战定位的必须回）
- **不回复**负能量评论（不要给它们 engagement 涨权重）
- **每 15-20 分钟主动转发或 quote tweet 自己的 thread**（提高 early velocity——但别刷屏）

### 24 小时内

- 回复所有来自**目标受众**的问题
- 如果某条推意外出圈（> 2000 views），抓住势头 quote tweet 加一个 "补个 context：…"
- 邀请认真评论者去 GitHub 开 Issue 继续讨论——让讨论沉淀到 repo 里

### 48-72 小时

- 评估信号：有没有 5+ 个 builder 真的 pip 安装试用？如果有，收集他们的 feedback
- 写一条 **"发帖后 48 小时观察"** 跟进推：最常问的问题、最大误解、最意外的 use case

### 一周后

- 如果还有人讨论：发 **"一周回顾"** —— 可以引用 GitHub issues / stars 的增长 / 某个用户的实际 migration 报告
- 如果没人讨论：**不要装热闹**。安静 iterate v0.2，三周后再 ship 第二轮 thread

---

## 前置准备 checklist

发 thread 之前，把下面清单全部打钩：

### GitHub repo

- [ ] repo 已 push 到 public GitHub（`github.com/dxxbb/forge-core`）
- [ ] README 第一屏中英文版本**一致**的关键信息（star 数、核心价值主张）
- [ ] `v0.1.0` 的 git tag + GitHub Release（包含简短的 changelog）
- [ ] `LICENSE` 文件在根目录（MIT）
- [ ] `pip install` 能一行装上（先在干净环境验证）

### Demo 资产

- [ ] 录一个 30-60 秒的 `forge diff → approve` 演示 gif 或 asciinema cast
- [ ] 配图（至少首推 + 末推的两张）做完，存在本机随手能调

### 文案准备

- [ ] 8 条推 **英文版** 写好（不是直译中文，是英文读者关心的角度重写——重点在"不是替代 rulesync，是补它不做的那半"）
- [ ] 8 条推 **中文版** 写好（参考 `article-short-thread.md`）
- [ ] 每条推字数 **≤ 280**（中文约 140 汉字，英文约 250 字符——留缓冲）
- [ ] 链接 / CTA 在第 8 条，不在前面
- [ ] 前 1-2 条的 **hook 可以被截屏作为首屏**（即使不点开 thread 也能引起兴趣）

### 心态准备

- [ ] 想好如果**没人看**怎么办（默念：目标是学习，不是转化；大多数 thread 都没人看）
- [ ] 想好如果**被喷**怎么办（不回负能量；只回实质问题）
- [ ] 时间守护：发完 2 小时内不要开会 / 出门——要能回评论

---

## Worst case 处理

### 场景 1：发完 24 小时 < 500 views

**不要删**。发 follow-up 的 meta thread："发了一个 thread，24 小时不到 500 views——可能是 hook 不对，也可能是时机不对。分析一下 3 个原因"。这种诚实 meta 有时反而能出圈。

或者：**一周后用相同内容换个开头重发**。X 算法允许这种 replay，只要间隔 ≥ 7 天。

### 场景 2：某条推出圈到 50k+ views，评论区 1000+

**不要试图回所有**。挑 10-20 个最有营养的回。大多数在 X 上出圈的推文，70% 的回复是没营养的——那部分留着别理。

### 场景 3：被大 V 引用 / 批评

**回应，但不服软也不挑衅**。如果大 V 说得对，承认 + 给出你的反思。如果说错了，用数据反驳（比如引用 eval-report 的数字）。这是 builder 圈尊敬的姿态。

### 场景 4：被"营销号"或"AI 水号"转发 / 截取

不管。那些账号用算法乱抓，不是你的目标受众，也不会对真实采用率有帮助。

---

## 发布 day 的小流程

按顺序：

1. **发布前 30 分钟**：再通读一遍 8 条推，确认字数、typo、链接能打开
2. **发首推**：观察 first 15 min 的 impressions——如果 < 100，可能时机不对（但很少会立刻明朗）
3. **每条推间隔 2-5 分钟**连发——别一次发 8 条让读者疲劳，也别间隔 30 分钟让 thread 线被打断
4. **发完后 1 小时**：在第 8 条下面 reply 一条"补链接"（design.md / eval-report / migration guide）
5. **发完后 2 小时**：开始回有营养的评论
6. **发完后 24 小时**：写观察记录——不是推，是给自己看的——哪条推 engagement 最高、收到最多哪类问题、哪些人转发了

---

## 同步到知乎想法 / 小红书

**不是同时发**——中文平台读者和英文 X 读者几乎不重叠，**错开 1-2 天**：

- X 发完隔 1-2 天，发中文版到知乎想法（对应 `article-short-thread.md`）
- 再隔 3-5 天，发**长版**中文文章到知乎正式文章 / 公众号（对应 `article-draft.md`）
- 小红书：考虑**完全不同的内容切入**——AI builder 圈在小红书不大，发"我怎么管理我的 personal AI context"这种 lifestyle-ish 切入更合适（不是这份 strategy 覆盖的范围）

中文平台的算法和 X 不同：

- **知乎想法**：不抗外链，放 GitHub 链接没事
- **知乎文章**：可以放所有链接，长文格式欢迎
- 小红书：放 GitHub 链接没有转化（小红书用户基本不用 GitHub），放"我的个人 AI 工作流"这类软性内容更有效

---

## 内容版权 / 署名

- [ ] 首推前放一次署名 / repo 链接，方便截图传播时有出处（但不是 CTA，CTA 在末尾）
- [ ] 如果在某条推里引用了 Karpathy / 其他作者的话，明确 attribute
- [ ] 不要在 thread 里骂竞品——`rulesync` / `claude-memory-compiler` 是同路人不是敌人，对标时保持尊重

---

## 一句话总结

**目标**：找 5-10 个真用户 + 验证"context 是 asset"这个命题有没有共振。

**手段**：周二美东上午 / 周末中文晚上发 X + 知乎；首推和末推配图；前 7 条无链接第 8 条 repo；Hashtag ≤ 2；发完守 2 小时；一周后回顾。

**心态**：不指望 viral，指望学习。

---

*英文版待写：`launch-strategy.en.md`（如果需要跨团队协作才做）。*
