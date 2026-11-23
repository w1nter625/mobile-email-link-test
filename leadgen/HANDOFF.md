# Overfeel 获客项目 · 完整上下文交接

这份文件汇总了之前对话里的全部决定、资料和待办，供你在本地继续开发或交给本地的 Claude Code 接着做。

---

## 1. 目标

为 **Overfeel**（网页设计工作室）每天找 10 个新加坡本地商家：

- 在 Google Maps 上**正常营业**
- **没有官网**（或只有 FB/IG/外卖平台页），或者**官网陈旧/打不开**
- 找到**公开邮箱**

然后对每家：

1. 调研实际业务
2. 生成一个**专属创意落地页**（HTML）
3. 写一封以 Overfeel 名义的**英文开发信**：诚恳语气，按“注意到你们 → 有个小点子 → 顺手做了个页面 → 不喜欢也没关系”的顺序

工具只生成草稿，**不自动发信**。

---

## 2. 代码结构（`leadgen/`）

| 文件 | 作用 |
|---|---|
| `run.py` | 主流程和命令行入口 |
| `overfeel/places.py` | Google Places API (New) Text Search |
| `overfeel/website.py` | 网站陈旧检测（sitemap lastmod > 旧的 Last-Modified > © 年份）、邮箱提取（mailto、文本、`[at]`、Cloudflare 混淆） |
| `overfeel/ai.py` | Claude（`claude-opus-5-5`）：联网调研 → 写信 → 生成落地页；开启了服务端 refusal fallback |
| `config.json` | 目标社区、行业、署名、开头方式（已改成新加坡） |
| `grok-workflow.md` | 给 Grok 用的 4 阶段 prompt（ACRA → Maps 核实 → 业务调研 → PDF） |
| `README.md` | 使用说明 |
| `../.github/workflows/daily-leads.yml` | GitHub Actions 每天自动运行 |

### 本地运行

```bash
cd leadgen
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_MAPS_API_KEY=...
export ANTHROPIC_API_KEY=...

python run.py --dry-run      # 只找商家、判断网站、抓邮箱，不调用 Claude
python run.py --count 3      # 小规模试跑
python run.py                # 跑满 daily_target
```

输出位置：

- `output/<日期>/index.html`：当日总览
- `output/<日期>/leads.csv`：表格版
- `output/<日期>/<商家>/index.html`：落地页
- `output/<日期>/<商家>/email.txt`：邮件草稿
- `data/seen.json`：已处理商家记录，用来去重

### 测试情况

- **已测：**
  - 网站检测：用本地模拟网站测过，2017 年的旧站判为 stale，较新的站判为 fresh
  - 邮箱提取和整体流程：用假数据跑通
  - Claude 请求：确认格式正确
- **未测：** 真实的 Google API 调用、真实的 Claude 调用。云端环境没有 key，也连不上外网。

---

## 3. 重要设计决定

- **邮件开头**（`opener`）：
  - `maps`（默认）：“在 Google Maps 上看到你们”，永远是真话
  - `walked_by` / `visited`：只在真的路过或去过时用。真实细节写在 `config.json` 的 `visit_notes` 里，按商家名填，例如 `{"Rosa's Tamales": "had the pork tamales on a Saturday"}`
  - AI 被要求不编造细节
- **合规**：邮件末尾自动加退订说明和通信地址。
- **邮箱来源**：AI 联网找到的邮箱必须附来源链接，不允许猜。
- **去重**：处理过的商家记在 `data/seen.json`，不会重复推。

---

## 4. Google Maps API

### 申请步骤

1. 打开 https://console.cloud.google.com ，新建项目。
2. Billing 里绑定银行卡（新账号可能有试用金）。
3. APIs & Services → Library → 启用 **Places API (New)**。
4. Credentials → 创建 API key，并限制为只能调用 Places API (New)。
5. Quotas 里给 Text Search 设**每日请求上限**（硬上限，例如 30–100）。
6. Billing → Budgets & alerts 设预算提醒（只提醒，不会停）。

### 额度（2025 年 3 月起，取代了原来每月 200 美元的赠金；以官方页面为准）

- 按计费档位（SKU）计算**每月**免费次数，每月初重置。
- 一次请求（最多返回 20 家）算 1 次，翻页另算。
- 一次请求按其中字段对应的**最高档**计费。

| Text Search 档位 | 每月免费 | 超出后每 1000 次 |
|---|---|---|
| Essentials (IDs Only) | 不限 | 免费 |
| Pro | 5,000 | 约 $32 |
| Enterprise（网站、电话、评分） | 1,000 | 约 $35 |
| Enterprise + Atmosphere（评论） | 1,000 | 约 $40 |

**当前工具**请求了评论，落在 Enterprise + Atmosphere 档，每月只有 1,000 次免费。最坏情况每天约 90 次请求，会超出免费额度。见第 9 节待办。

定价页：https://developers.google.com/maps/billing-and-pricing/pricing

---

## 5. 新加坡商家数据源（除 Google Maps 外）

- **ACRA 企业注册数据**（data.gov.sg，免费）
  - 字段：UEN、名称、状态、注册日期、SSIC 行业代码、注册地址
  - 没有邮箱和电话；详细资料要在 BizFile+ 付费查
  - 用法：按“近 6–24 个月新注册 + SSIC 56（餐饮）/ 47（零售）/ 96（美发美容等）”筛选，这批大概率还没有官网
  - 注意：注册地址常是秘书公司地址，需要用 Maps 核实
- **SFA 持牌食品经营场所名单**、**CDC 消费券参与商家名单**（组屋区小店，没有官网的比例高）
- **平台**：GrabFood、foodpanda、Burpple、Chope、Fresha、Instagram（#sghomebaker）、Carousell、Shopee
- **目录**：Yellow Pages SG、Streetdirectory、SGPBusiness、RecordOwl、OpenCorporates
- **商会和协会**：中华总商会（SCCCI）、中小企业协会（ASME）、新加坡餐饮业协会（RAS），会员多是老牌企业，官网常陈旧

**建议架构**：ACRA 筛选 → Places API 按名称加地址精确核实 → 现有流程。

---

## 6. 合规要点（新加坡）

- **PDPA**：商业联系信息（公司邮箱、店铺电话）大多不受 PDPA 个人数据义务约束；个体户的私人联系方式要谨慎。
- **《垃圾邮件控制法》（Spam Control Act）**：针对批量发送（约 24 小时 100 封以上，需核实最新规定）。每天 10 封远低于门槛，但仍保留退订方式和真实发件人信息。
- **DNC 拒接名单**：打电话、发短信或 WhatsApp 给个人号码前要先查。企业对企业的商务信息一般不在此列（需确认）。
- **不要用脚本抓 Google Maps 网页**，这违反服务条款，有封 IP 或账号的风险。用官方 API，或者人工浏览。

---

## 7. 其他获客渠道

1. **合作转介绍**：会计所和公司秘书（正好对上新注册公司）、装修和招牌公司、收银系统服务商、摄影师和品牌设计师、共享办公空间
2. **“刚开业或在扩张”的信号**：Eatbook、Seth Lui、Daniel Food Diary、TheSmartLocal、Burpple 的新店合集；MyCareersFuture 和 FastJobs 上的招聘；IG 上的家庭烘焙商家（HBB）；周末市集摊主
3. **政府补贴**：PSG、SMEs Go Digital。成为预批供应商后，客户可以拿补贴买你的服务（门槛需向 Enterprise Singapore 和 IMDA 确认）
4. **内容引流**：小红书、IG、TikTok 上的“改版前后”系列；行业关键词 SEO；给 Overfeel 自己建 Google Business Profile
5. **社群**：Carousell 服务类目、Facebook 小企业主群组、BNI、SCCCI 和 ASME 活动
6. **触达方式**：带 iPad 上门展示落地页（转化最高）、IG 私信、LinkedIn（B2B 客户）、WhatsApp（只发公开商务号）

**推荐的前三项**：会计所和公司秘书合作；新店开业报道加 IG 家庭烘焙商家；“改版前后”内容系列。

---

## 8. 潜在合作伙伴清单（WhatsApp 和负责人尚未核实）

**有正式合作计划，可以直接在官网申请**

| 公司 | 类型 | 合作方式 | 链接 |
|---|---|---|---|
| Sleek | 公司注册、秘书、会计 | 联盟计划，官网写每单 SGD 300 加批量奖金（需核实） | https://sleek.com/sg/affiliates/ |
| Osome | 公司注册、秘书、会计 | 按月返佣、给客户折扣或两者结合；有合作伙伴市场 | https://osome.com/sg/become-a-partner |
| Qashier | 收银系统 | 免费加入，按客户给佣金，有联合推广 | https://qashier.com/sg/ |
| StoreHub | 收银系统 | 经销商、代理机构、顾问、联盟 | https://www.storehub.com/ph/be-a-partner |
| iCHEF | 餐饮收银系统 | “Opening Experts” 开店服务商网络 | https://www.ichefpos.com/en-sg/opening-experts |
| Eats365 | 餐饮收银系统 | 有合作伙伴页面 | https://www.eats365pos.com/partner/ourpartners |

**中小型公司，适合直接找老板谈**

| 公司 | 类型 |
|---|---|
| 3E Accounting、Premia TNC | 会计、公司秘书 |
| JP Concept、Renovator Hub、Caseworks、Albedo Design | F&B 装修和室内设计 |
| Signarama CBD（Nalla Signs）、Signeagles、Advert & Signs | 招牌制作 |
| My Singapore Kitchen、Kith Café 创始人 Jane Hia | F&B 开店顾问 |
| RAS 新加坡餐饮业协会 | 行业协会 |

**补全联系方式**：在官网找 WhatsApp 按钮或 `wa.me/65…` 链接；在 LinkedIn 搜“公司名 + Partnerships/BD”；或者用下面这段 prompt 让 Grok 去查：

```
以下是新加坡的潜在合作公司：Sleek, Osome, Qashier, StoreHub, iCHEF Singapore, Eats365 Singapore, 3E Accounting, Premia TNC, JP Concept, Renovator Hub, Caseworks, Albedo Design, Signarama CBD, Signeagles, Advert & Signs, My Singapore Kitchen。
对每家公司查找并整理成表格：
| 公司 | 官网 | 合作/伙伴计划链接 | 公开商务 WhatsApp（wa.me 链接或号码）| 电话 | 邮箱 | 合作对接人或创始人姓名及职位（仅限官网/LinkedIn/新闻公开信息）| 每条信息的来源链接 |
规则：只用公司公开发布的商务联系方式，查不到写“未找到”，不要猜测或编造号码，不要找个人私人手机号。
```

**开口话术**

- **会计所和秘书公司**：新注册客户都需要网站。我们给你的客户专属折扣，每成交一单给你介绍费，也互相推荐客户。
- **装修和招牌公司**：店面装好了，线上门面也要跟上。可以一起打包报价，比如招牌加落地页。
- **收银系统公司**：申请成为它们的合作伙伴或代理机构，卖点是能帮它们的客户做线上点单页。

---

## 9. 待办（按优先级）

1. **控制 API 费用**：`places.search` 默认 `max_pages=1`，加一个配置项 `max_maps_requests_per_day`（例如 30），超过就停。
2. **`--from-list shops.txt`**：读取人工整理或 Grok 整理的店名、Maps 链接名单，逐个用 Places API 精确查一次，然后走现有流程。
3. **`--source acra`**：读取 data.gov.sg 的 ACRA CSV，按 SSIC 前缀和注册日期筛选，再用 Places 按“名称 + 邮编”核实。
4. **新数据源**：让 Claude 联网搜索新店开业报道（Eatbook、Seth Lui 等）和 IG 标签，自动整理候选商家。
5. **字段降档**：可选去掉 `reviews` 和 `editorialSummary`，改让 Claude 联网查，降到 Enterprise 档。
6. **邮件语境**：按国家调整邮件开头和页脚，新加坡场景不必提美国的 CAN-SPAM。
7. **实测**：用真实 key 跑 `--dry-run` 和 `--count 3`，检查网站判断和邮箱的准确率。
8. **合作伙伴清单**：核实第 8 节的联系方式。
