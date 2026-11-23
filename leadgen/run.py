#!/usr/bin/env python3
"""Overfeel daily lead finder.

Google Maps -> operational businesses with no website / stale website -> public email
-> Claude research -> tailored landing page concept + English outreach email draft.

Drafts only: nothing is sent. Review every email before sending it yourself.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import random
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from overfeel import places, website  # noqa: E402

SOCIAL_HOSTS = ("facebook.com", "instagram.com", "linktr.ee", "yelp.com", "business.site", "tiktok.com")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "lead"


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def queries_for_today(cfg: dict, day: dt.date) -> list[str]:
    combos = [f"{c} in {l}" for l in cfg["locations"] for c in cfg["categories"]]
    random.Random(day.toordinal()).shuffle(combos)  # different order every day, reproducible
    return combos


def qualify(p: dict, cfg: dict) -> dict | None:
    """Return the lead with lead_type set, or None if it doesn't fit."""
    if p["status"] != "OPERATIONAL":
        return None
    site = p.get("website")
    host = (urlparse(site).hostname or "") if site else ""
    if not site or any(host.endswith(h) for h in SOCIAL_HOSTS):
        p.update(lead_type="no_website", site_reasons=["no website on Google Maps" if not site else f"only a social/listing page ({host})"], emails=[])
        return p
    a = website.analyze(site, cfg.get("stale_years", 2))
    if a["verdict"] not in ("stale", "broken"):
        return None
    p.update(lead_type=f"{a['verdict']}_website", site_reasons=a["reasons"], emails=a["emails"],
             site_text=a["text"], site_check={k: v for k, v in a.items() if k not in ("text", "emails")})
    return p


def find_leads(cfg: dict, seen: dict, day: dt.date, target: int):
    for q in queries_for_today(cfg, day):
        print(f"[maps] {q}", flush=True)
        try:
            raw = places.search(q)
        except Exception as e:  # noqa: BLE001
            print(f"  search failed: {e}", flush=True)
            continue
        for r in raw:
            p = places.normalize(r)
            if not p["place_id"] or p["place_id"] in seen:
                continue
            seen[p["place_id"]] = {"name": p["name"], "checked": day.isoformat()}
            lead = qualify(p, cfg)
            if lead:
                print(f"  + {lead['name']} [{lead['lead_type']}]", flush=True)
                yield lead


def process(lead: dict, cfg: dict, outdir: Path, opener: str) -> dict:
    from overfeel import ai

    model = cfg.get("model", "claude-opus-5-5")
    info = ai.research(lead, model)
    found = (info.get("email") or {}).get("address")
    site_emails = bool(lead.get("emails"))
    emails = list(dict.fromkeys(lead.get("emails", []) + ([found.lower()] if found else [])))
    lead["emails"] = emails
    lead["email_source"] = "website" if site_emails else (info.get("email") or {}).get("source_url")
    if cfg.get("require_email", True) and not emails:
        lead["skipped"] = "no public email found"
        return lead

    d = outdir / slug(lead["name"])
    d.mkdir(parents=True, exist_ok=True)
    mail = ai.write_email(lead, info, cfg["sender"], opener, model, lead.get("visit_note") or cfg.get("visit_notes", {}).get(lead["name"], ""))
    page = ai.landing_page(lead, info, cfg["sender"], model)
    (d / "index.html").write_text(page)
    (d / "email.txt").write_text(f"To: {emails[0] if emails else '(find manually)'}\nSubject: {mail['subject']}\n\n{mail['body']}\n")
    lead.update(research=info, email_draft=mail, folder=d.name)
    (d / "lead.json").write_text(json.dumps({k: v for k, v in lead.items() if k != "site_text"}, indent=2, ensure_ascii=False))
    return lead


def write_report(leads: list[dict], outdir: Path, day: dt.date):
    rows = [l for l in leads if l.get("folder")]
    with open(outdir / "leads.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "category", "lead_type", "email", "email_source", "phone", "address", "website", "maps_url", "idea", "subject", "landing_page"])
        for l in rows:
            w.writerow([l["name"], l["category"], l["lead_type"], ";".join(l["emails"]), l.get("email_source") or "", l.get("phone") or "",
                        l["address"], l.get("website") or "", l.get("maps_url") or "", l["research"]["idea"]["title"],
                        l["email_draft"]["subject"], f"{l['folder']}/index.html"])
    e = html.escape
    cards = []
    for l in rows:
        mail = l["email_draft"]
        cards.append(f"""<article class="card">
<header><h2>{e(l['name'])}</h2><span class="tag {e(l['lead_type'])}">{e(l['lead_type'].replace('_', ' '))}</span></header>
<p class="meta">{e(l['category'])} · ★ {l.get('rating') or '–'} ({l.get('review_count') or 0}) · {e(l['address'])}</p>
<p class="meta">{e('; '.join(l.get('site_reasons') or []))}</p>
<p><b>Email:</b> {e(', '.join(l['emails']))} <small>{e(l.get('email_source') or '')}</small><br><b>Phone:</b> {e(l.get('phone') or '–')}</p>
<p><b>Idea:</b> {e(l['research']['idea']['title'])} — {e(l['research']['idea']['one_liner'])}</p>
<p class="links"><a href="{e(l['folder'])}/index.html" target="_blank">Landing page ↗</a>
<a href="{e(l.get('maps_url') or '#')}" target="_blank">Google Maps ↗</a>{f' <a href="{e(l["website"])}" target="_blank">Current site ↗</a>' if l.get('website') else ''}</p>
<details><summary>Email draft — {e(mail['subject'])}</summary><pre>{e(mail['body'])}</pre>
<button onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent)">Copy body</button></details>
</article>""")
    skipped = [l for l in leads if l.get("skipped")]
    sk = "".join(f"<li>{e(l['name'])} — {e(l.get('phone') or '')} — {e(l['skipped'])}</li>" for l in skipped)
    (outdir / "index.html").write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Overfeel leads {day}</title><style>
:root{{--bg:#f6f4ef;--fg:#1d1b18;--mut:#6b655c;--card:#fff;--ac:#d9480f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151412;--fg:#eee9e0;--mut:#a39c90;--card:#201e1b}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:24px 16px}}
main{{max-width:880px;margin:auto}}h1{{font-size:28px}}.card{{background:var(--card);border-radius:14px;padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px #0002}}
.card header{{display:flex;justify-content:space-between;gap:8px;align-items:center}}h2{{margin:0;font-size:19px}}
.meta{{color:var(--mut);margin:4px 0}}.tag{{font-size:12px;padding:2px 8px;border-radius:99px;background:#ffe8cc;color:#8a3b00;white-space:nowrap}}
.tag.no_website{{background:#d3f9d8;color:#1b5e20}}.links a{{margin-right:14px;color:var(--ac)}}pre{{white-space:pre-wrap;font:14px/1.5 ui-monospace,monospace}}
button{{border:0;background:var(--ac);color:#fff;border-radius:8px;padding:6px 12px;cursor:pointer}}</style></head>
<body><main><h1>Overfeel · {len(rows)} leads · {day}</h1>
<p class="meta">Drafts only — check each email and visit note before sending. Replace {{{{PREVIEW_LINK}}}} with the hosted landing page URL.</p>
{''.join(cards) or '<p>No qualified leads today.</p>'}
{f'<h3>Qualified but no public email (call / visit instead)</h3><ul>{sk}</ul>' if sk else ''}
</main></body></html>""")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--count", type=int, help="leads to produce (default: config daily_target)")
    ap.add_argument("--opener", choices=["maps", "walked_by", "visited"], help="email opening style")
    ap.add_argument("--dry-run", action="store_true", help="only find & qualify leads, no Claude calls")
    ap.add_argument("--sample", help="skip Google Maps; process a lead JSON file instead (for testing)")
    args = ap.parse_args()

    cfg = load_json(Path(args.config), None) or load_json(ROOT / "config.example.json", {})
    day = dt.date.today()
    target = args.count or cfg.get("daily_target", 10)
    opener = args.opener or cfg.get("opener", "maps")
    outdir = ROOT / "output" / day.isoformat()
    outdir.mkdir(parents=True, exist_ok=True)
    seen_path = ROOT / "data" / "seen.json"
    seen_path.parent.mkdir(exist_ok=True)
    seen = load_json(seen_path, {})

    source = iter(load_json(Path(args.sample), [])) if args.sample else find_leads(cfg, seen, day, target)
    done, all_leads, checked = 0, [], 0
    try:
        for lead in source:
            checked += 1
            if checked > cfg.get("max_candidates_per_run", 120):
                break
            if args.dry_run:
                all_leads.append(lead)
                print(f"    emails={lead.get('emails')} reasons={lead.get('site_reasons')}")
                done += 1
            else:
                try:
                    lead = process(lead, cfg, outdir, opener)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    continue
                all_leads.append(lead)
                if lead.get("folder"):
                    done += 1
                    print(f"  ✓ {done}/{target} {lead['name']} -> {lead['emails'][0]}", flush=True)
            if done >= target:
                break
    finally:
        seen_path.write_text(json.dumps(seen, indent=1))
    if args.dry_run:
        (outdir / "dry-run.json").write_text(json.dumps(all_leads, indent=2, ensure_ascii=False, default=str))
    else:
        write_report(all_leads, outdir, day)
    print(f"\nDone: {done} leads -> {outdir}")


if __name__ == "__main__":
    main()
