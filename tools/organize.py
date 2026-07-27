#!/usr/bin/env python3
"""Normalize categories, fill missing logos, dedupe, and sort the playlists.

Categories come from the iptv-org global channel database where a channel name
matches; otherwise they fall back to keyword rules over the channel's existing
group-title and name. Output is sorted by category then name so diffs stay readable.

Usage:
    python3 tools/organize.py            # rewrite channels.m3u and bdix.m3u in place
    python3 tools/organize.py --dry-run  # report only

Needs the iptv-org channel db; it is downloaded to /tmp on first run.
"""
import json, os, re, subprocess, sys, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["channels.m3u", "bdix.m3u"]
CH_DB = "/tmp/iptvorg_channels.json"
LOGO_DB = "/tmp/iptvorg_logos.json"
DB_URL = "https://iptv-org.github.io/api/channels.json"
LOGO_URL = "https://iptv-org.github.io/api/logos.json"

# Final taxonomy — keep this list short; every channel maps into exactly one.
CATS = ["News", "Sports", "General", "Entertainment", "Movies", "Music", "Religious",
        "Kids", "Documentary", "Lifestyle", "Business", "Education", "Radio", "Other"]

# iptv-org category id -> our category
FROM_IPTVORG = {
    "news": "News", "weather": "News", "politics": "News",
    "sports": "Sports", "outdoor": "Sports",
    "movies": "Movies", "series": "Entertainment",
    "general": "General", "family": "General", "culture": "General",
    "entertainment": "Entertainment", "comedy": "Entertainment", "classic": "Entertainment",
    "animation": "Kids", "kids": "Kids",
    "music": "Music",
    "religious": "Religious",
    "documentary": "Documentary", "science": "Documentary", "history": "Documentary",
    "nature": "Documentary", "travel": "Lifestyle", "food": "Lifestyle",
    "lifestyle": "Lifestyle", "auto": "Lifestyle", "shop": "Lifestyle", "health": "Lifestyle",
    "business": "Business", "education": "Education", "legislative": "News",
    "relax": "Lifestyle", "cooking": "Lifestyle",
}

# fallback: keyword found in existing group-title or channel name -> our category
KEYWORDS = [
    ("Radio",       ["radio", "redio", " fm", "fm "]),
    ("Religious",   ["islam", "quran", "religio", "relagion", "madani", "peace", "azan",
                     "makkah", "medina", "hadi", "dawah", "naat"]),
    ("Kids",        ["kids", "cartoon", "toon", "baby", "duronto", "nick", "pogo", "chutti"]),
    ("Sports",      ["sport", "cricket", "football", "star sports", "ten sports", "willow",
                     "t sports", "geo super", "supersport"]),
    ("Movies",      ["movie", "cinema", "film", "picture", "bioscope", "jalsha movies"]),
    ("Music",       ["music", "mtv", "9xm", "gaan", "song", "b4u", "sangeet"]),
    ("News",        ["news", "khobor", "somoy", "jamuna", "ekattor", "dbc", "atn news",
                     "channel 24", "independent", "24/7 news", "internasional"]),
    ("Documentary", ["discovery", "nat geo", "national geographic", "history", "animal planet",
                     "documentar", "infotainment", "information", "science", "earth"]),
    ("Lifestyle",   ["travel", "food", "lifestyle", "fashion", "health", "cooking"]),
    ("Business",    ["business", "bloomberg", "cnbc", "ekhon"]),
    ("Education",   ["education", "learn", "school"]),
]


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\b(fhd|uhd|hd|sd|4k)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_db():
    # curl, not urllib: this python has no CA bundle so TLS verification fails
    for url, path in ((DB_URL, CH_DB), (LOGO_URL, LOGO_DB)):
        if not os.path.exists(path):
            subprocess.run(["curl", "-sSL", "-m", "90", url, "-o", path], check=True)

    # channel id -> logo url (prefer in-use, landscape-ish, first wins otherwise)
    by_id = {}
    for l in json.load(open(LOGO_DB)):
        cid, u = l.get("channel"), l.get("url")
        if not cid or not u:
            continue
        if cid not in by_id or (l.get("in_use") and not by_id[cid][1]):
            by_id[cid] = (u, bool(l.get("in_use")))

    cats, logos = {}, {}
    for c in json.load(open(CH_DB)):
        n = norm(c.get("name"))
        if not n:
            continue
        is_bd = c.get("country") == "BD"
        cs = c.get("categories") or []
        mapped = next((FROM_IPTVORG[x] for x in cs if x in FROM_IPTVORG), None)
        # prefer a BD entry, else first seen
        if mapped and (n not in cats or is_bd):
            cats[n] = mapped
        logo = c.get("logo") or (by_id.get(c["id"]) or ("",))[0]
        if logo and (n not in logos or is_bd):
            logos[n] = logo
    return cats, logos


def categorize(name, old_group, db_cats):
    n = norm(name)
    if n in db_cats:
        return db_cats[n]
    hay = f"{old_group} {name}".lower()
    for cat, words in KEYWORDS:
        if any(w in hay for w in words):
            return cat
    og = norm(old_group)
    for c in CATS:
        if norm(c) and norm(c) in og:
            return c
    return "Entertainment" if og else "Other"


def parse(path):
    out = []
    lines = open(path, encoding="utf-8", errors="ignore").read().split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#EXTINF") and "," in ln:
            name = ln.split(",", 1)[1].strip()
            logo = (re.search(r'tvg-logo="([^"]*)"', ln) or [None, ""])[1]
            grp = (re.search(r'group-title="([^"]*)"', ln) or [None, ""])[1]
            url = ""
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s and not s.startswith("#"):
                    url = s
                    break
                j += 1
            if name and url:
                out.append({"name": name, "url": url, "logo": logo, "group": grp})
            i = j + 1
            continue
        i += 1
    return out


def main():
    dry = "--dry-run" in sys.argv
    db_cats, db_logos = load_db()
    for fname in FILES:
        path = os.path.join(REPO, fname)
        if not os.path.exists(path):
            continue
        rows = parse(path)
        seen, clean = set(), []
        for r in rows:
            key = (norm(r["name"]), r["url"])
            if key in seen:                     # exact duplicate entry
                continue
            seen.add(key)
            r["group"] = categorize(r["name"], r["group"], db_cats)
            if not r["logo"]:
                r["logo"] = db_logos.get(norm(r["name"]), "")
            clean.append(r)
        clean.sort(key=lambda r: (CATS.index(r["group"]) if r["group"] in CATS else 99,
                                  r["name"].lower()))
        dist = {}
        for r in clean:
            dist[r["group"]] = dist.get(r["group"], 0) + 1
        logos = sum(1 for r in clean if r["logo"])
        print(f"\n{fname}: {len(rows)} -> {len(clean)} entries ({len(rows)-len(clean)} dupes removed), "
              f"{logos} with logos")
        for c in CATS:
            if dist.get(c):
                print(f"    {c:14s} {dist[c]}")
        if dry:
            continue
        out = ["#EXTM3U", f"# {fname} — organized by tools/organize.py", "# Do not hand-sort; re-run the script."]
        for r in clean:
            logo = f' tvg-logo="{r["logo"]}"' if r["logo"] else ""
            out.append(f'#EXTINF:-1{logo} group-title="{r["group"]}",{r["name"]}')
            out.append(r["url"])
        open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("\ndry run — nothing written" if dry else "\nwritten")


if __name__ == "__main__":
    main()
