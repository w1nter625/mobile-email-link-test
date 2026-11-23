# Overfeel 获客工具（Lead Finder）

每天从 Google Maps 找 10 个**正常营业**、但**没有官网**或**官网很久没更新/打不开**的本地商家，找到公开邮箱，用 Claude 调研业务，然后为每家生成：

1. 一个**专属创意落地页**（单文件 HTML，可直接打开/部署）
2. 一封以 **Overfeel** 名义写的**英文开发信**草稿（诚恳语气：注意到你们 → 有个小点子 → 顺手做了个页面 → 不喜欢也没关系）

> 工具只生成草稿，**不会自动发信**。每封邮件发送前请自己过一遍。

## 流程

```
Google Places API (Text Search)
  └─ 过滤 businessStatus == OPERATIONAL，跳过已处理过的商家 (data/seen.json)
      ├─ 没有网站 / 只有 Facebook、Instagram 等社交页      → no_website
      └─ 有网站 → 抓取首页 + sitemap + 联系页
            ├─ 最新更新信号（sitemap lastmod / ©年份）≤ 今年-2 → stale_website
            ├─ 打不开 / 域名停放                             → broken_website
            └─ 正常更新                                       → 跳过
  └─ 邮箱：网站上的 mailto / 文本 / Cloudflare 混淆邮箱；
           没有的话 Claude 用 web search 在 FB/IG/Yelp/目录站找公开邮箱（必须附来源链接，不允许猜）
  └─ Claude 调研业务 → 一个具体的小点子 → 写邮件 → 生成落地页
```

## 输出

```
output/2026-11-23/
  index.html          ← 当日总览：每个商家的信息、点子、邮件草稿（一键复制）、落地页链接
  leads.csv           ← 表格版
  rosa-s-tamales/
    index.html        ← 落地页
    email.txt         ← 邮件（To / Subject / 正文）
    lead.json         ← 全部原始数据与调研结果
```

没找到公开邮箱但符合条件的商家，会列在总览页底部（附电话），可以打电话或亲自上门。

## 准备

1. **Google Maps API Key**：Google Cloud Console → 启用 *Places API (New)* → 创建 API key。
   注意：要拿评论（reviews）等字段属于较高价位 SKU，每天几十次查询通常仍在免费额度内，请在控制台设好预算提醒。
2. **Anthropic API Key**：https://console.anthropic.com
3. 编辑 `config.json`：
   - `locations` / `categories`：目标城市与行业，每天会自动打乱组合顺序
   - `sender`：你的名字、职位、Overfeel 网站、邮箱、**通信地址**（美国 CAN-SPAM 要求商业邮件带真实地址和退订方式，模板已自动加上）
   - `stale_years`：多少年没更新算“陈旧”（默认 2）

## 运行

```bash
cd leadgen
pip install -r requirements.txt
export GOOGLE_MAPS_API_KEY=...
export ANTHROPIC_API_KEY=...

python run.py                 # 跑满 10 个
python run.py --count 3       # 先少量试跑
python run.py --dry-run       # 只找商家 + 判断网站 + 抓邮箱，不调用 Claude（省钱，先看质量）
python run.py --opener walked_by
```

### 每天自动跑（GitHub Actions）

已附带 `.github/workflows/daily-leads.yml`：

1. 仓库 Settings → Secrets → Actions 添加 `GOOGLE_MAPS_API_KEY`、`ANTHROPIC_API_KEY`
2. 把 workflow 合并到默认分支（定时任务只在默认分支生效）
3. 每天北京时间 22:17 自动运行；也可在 Actions 页手动 Run。结果在该次运行的 Artifacts 里下载。

## 关于邮件开头（`opener`）

| 值 | 开头 | 何时用 |
|---|---|---|
| `maps`（默认） | “在 Google Maps 上看本地小店时发现了你们……” | 永远真实，推荐 |
| `walked_by` | “最近路过你们店……” | **只在确实路过时用** |
| `visited` | “最近进店消费……” | **只在确实去过时用**；可在 `config.json` 的 `visit_notes` 里按商家名写真实细节，如 `{"Rosa's Tamales": "had the pork tamales on a Saturday"}` |

AI 被要求只使用调研中有据可查的细节，不会编造“点了什么”“看到了什么”。
如果对方去查证发现“路过/消费”是假的，信任会直接归零——真实的“在地图上看到你们评价很好”反而更打动人。

## 发送前检查清单

- [ ] 把邮件里的 `{{PREVIEW_LINK}}` 换成落地页的线上地址（可用 Netlify Drop / Vercel / GitHub Pages 托管 `index.html`）
- [ ] 核对收件邮箱来源（`email_source`）是否是商家官方公开渠道
- [ ] 读一遍落地页，把 `[占位符]` 换掉或确认合理
- [ ] 用自己的邮箱一封封发，控制每天数量，对方回复“no thanks”就不要再联系

## 文件

- `run.py` – 主流程 / CLI
- `overfeel/places.py` – Google Places API (New)
- `overfeel/website.py` – 网站陈旧检测与邮箱提取
- `overfeel/ai.py` – Claude 调研（web search）、写信、生成落地页（`claude-opus-5-5`，开启了服务端 refusal fallback）
