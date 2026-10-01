#!/usr/bin/env python3
"""Convert Confluence HTML space exports (EN + FR) into a bilingual Quarto website.

Usage: python3 tools/confluence2quarto.py <EN_export_dir> <FR_export_dir> <quarto_project_dir>
Requires: python3, beautifulsoup4, pandoc.
Regenerates <project>/en, <project>/fr, _sidebar.generated.yml and MIGRATION_REPORT.md.
"""
import sys, os, re, json, shutil, subprocess, unicodedata, urllib.parse
from bs4 import BeautifulSoup

EN_DIR, FR_DIR, OUT = sys.argv[1:4]
SPACES = {'en': EN_DIR, 'fr': FR_DIR}
SPACE_KEYS = {'EN': 'en', 'FRAN': 'fr', 'FR': 'fr'}
report = {'en': [], 'fr': []}
# pandoc >= 2.11 required (Quarto's bundled one works: PANDOC="quarto pandoc")
PANDOC = os.environ.get('PANDOC', 'quarto pandoc').split()


def slugify(s, maxlen=70):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()
    return s[:maxlen].rstrip('-') or 'page'


def anchor(s):
    return slugify(urllib.parse.unquote(s), 120)


def safe_filename(name):
    base, ext = os.path.splitext(name)
    return slugify(base, 60) + ext.lower()


def num_of(title):
    m = re.match(r'\s*(\d+(?:\.\d+)*)\.?\s', title)
    return m.group(1) if m else None


def pair_key(title, is_root):
    if is_root:
        return 'root'
    n = num_of(title)
    if n:
        return 'num:' + n
    m = re.match(r'\s*(Appendix|Annexe)\s+(\d+)', title, re.I)
    if m:
        return 'app:' + m.group(2)
    if re.match(r'\s*(Acknowledgements|Remerciements)', title, re.I):
        return 'ack'
    return 'title:' + slugify(title)


def sort_key(title):
    n = num_of(title)
    if n:
        return (0, tuple(int(x) for x in n.split('.')))
    m = re.match(r'\s*(Appendix|Annexe)\s+(\d+)', title, re.I)
    if m:
        return (1, (int(m.group(2)),))
    return (-1, ())


def strip_num(t):
    return re.sub(r'^\s*\d+(?:\.\d+)*\.?\s*', '', t)


# ---------- 1. page trees ----------
pages = {}
trees = {}
for lang, d in SPACES.items():
    s = BeautifulSoup(open(os.path.join(d, 'index.html'), encoding='utf-8').read(), 'html.parser')

    def walk(ul, parent, depth):
        out = []
        for li in ul.find_all('li', recursive=False):
            a = li.find('a', recursive=False)
            href = a['href']
            pid = re.search(r'(\d+)\.html$', href).group(1)
            title = re.sub(r'\s+', ' ', a.get_text()).strip()
            node = {'id': pid, 'title': title, 'file': href,
                    'lang': lang, 'parent': parent, 'depth': depth, 'children': []}
            pages[(lang, pid)] = node
            for sub in li.find_all('ul', recursive=False):
                node['children'] += walk(sub, pid, depth + 1)
            node['children'].sort(key=lambda c: sort_key(c['title']))
            out.append(node)
        return out
    trees[lang] = walk(s.select_one('.pageSection ul'), None, 0)

for lang in SPACES:
    used = set()
    for (l, pid), p in pages.items():
        if l != lang:
            continue
        sl = 'index' if p['depth'] == 0 else slugify(p['title'])
        while sl in used:
            sl += '-' + pid
        p['slug'] = sl
        used.add(sl)
        p['key'] = pair_key(p['title'], p['depth'] == 0)

by_key = {(p['lang'], p['key']): p for p in pages.values()}
title_index = {(p['lang'], slugify(strip_num(p['title']))): p for p in pages.values()}

# ---------- 2. attachments index ----------
att_alias = {}
for lang, d in SPACES.items():
    for fn in os.listdir(d):
        if not fn.endswith('.html'):
            continue
        s = BeautifulSoup(open(os.path.join(d, fn), encoding='utf-8').read(), 'html.parser')
        for a in s.select('div.greybox a[href^="attachments/"]'):
            m = re.match(r'attachments/(\d+)/(\d+)', a['href'])
            if m:
                att_alias[(m.group(1), m.group(2))] = a.get_text().strip()


def find_attachment(cid, attid):
    for d in (SPACES['en'], SPACES['fr']):
        folder = os.path.join(d, 'attachments', cid)
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                if os.path.splitext(fn)[0] == attid:
                    return os.path.join(folder, fn)
    return None


def find_attachment_by_alias(cid, alias):
    for (c, a), al in att_alias.items():
        if c == cid and al == alias:
            return find_attachment(c, a), a
    return None, None


copied = {}
used_paths = set()


def copy_att(lang, src, cid, alias):
    key = (lang, src)
    if key in copied:
        return copied[key]
    name = safe_filename(alias or os.path.basename(src))
    rel = f'files/{cid}/{name}'
    if (lang, rel) in used_paths:
        b, e = os.path.splitext(name)
        rel = f'files/{cid}/{b}-{os.path.splitext(os.path.basename(src))[0]}{e}'
    used_paths.add((lang, rel))
    dst = os.path.join(OUT, lang, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    copied[key] = rel
    return rel


EMO = {'warning': '⚠️', 'yellow-star': '⭐', 'star': '⭐', 'tick': '✅', 'cross': '❌',
       'information': 'ℹ️', 'smile': '🙂', 'light-on': '💡', 'thumbs-up': '👍', 'question': '❓'}
CALLOUT = {'note': 'warning', 'warning': 'important', 'information': 'note', 'info': 'note', 'tip': 'tip'}
COLORS = ['red', 'blue', 'orange', 'yellow', 'green', 'purple', 'teal', 'gray']


def page_link(lang, target_lang, pid, frag=None):
    p = pages.get((target_lang, pid))
    if not p:
        return None
    href = (p['slug'] + '.qmd') if target_lang == lang else f"../{target_lang}/{p['slug']}.qmd"
    if frag:
        href += '#' + anchor(frag)
    return href


# ---------- 3. convert each page ----------
def convert(p):
    lang = p['lang']
    d = SPACES[lang]
    issues = []
    soup = BeautifulSoup(open(os.path.join(d, p['file']), encoding='utf-8').read(), 'html.parser')
    mc = soup.find(id='main-content')
    if mc is None:
        issues.append('pas de contenu')
        mc = soup.new_tag('div')

    for t in mc.select('div.toc-macro, img.wysiwyg-unknown-macro, style, script'):
        t.decompose()
    for img in mc.select('img.emoticon'):
        img.replace_with(EMO.get(img.get('data-emoticon-name', ''), img.get('alt', '')))

    # info/note/warning/tip macros -> Quarto callouts
    for m in mc.select('div.confluence-information-macro'):
        kind = 'note'
        for c in m.get('class', []):
            if c.startswith('confluence-information-macro-') and c != 'confluence-information-macro-body':
                kind = CALLOUT.get(c.split('-')[-1], 'note')
        title = m.find('p', class_='title', recursive=False)
        ttext = title.get_text().strip() if title else None
        if title:
            title.decompose()
        for ic in m.select('span.confluence-information-macro-icon'):
            ic.decompose()
        body = m.select_one('div.confluence-information-macro-body')
        new = soup.new_tag('div')
        new['class'] = [f'callout-{kind}']
        if ttext:
            new['title'] = ttext
        for ch in list((body or m).contents):
            new.append(ch.extract())
        m.replace_with(new)

    # code panels
    for panel in mc.select('div.code.panel, div.preformatted.panel'):
        pre = panel.find('pre')
        params = pre.get('data-syntaxhighlighter-params', '') if pre else ''
        mm = re.search(r'brush:\s*([\w+-]+)', params)
        newpre = soup.new_tag('pre')
        code = soup.new_tag('code')
        if mm and mm.group(1) not in ('java', 'text', 'plain', 'none'):
            code['class'] = [mm.group(1)]
        code.string = pre.get_text() if pre else panel.get_text()
        newpre.append(code)
        panel.replace_with(newpre)
    for pre in mc.find_all('pre'):
        pre.attrs = {}
        code = pre.find('code')
        if code is None:
            code = soup.new_tag('code')
            code.string = pre.get_text()
            pre.clear()
            pre.append(code)
        if not code.get('class'):
            txt = code.get_text()
            code['class'] = ['yaml'] if re.search(r'^(version|services):', txt, re.M) else ['text']

    # generic panels -> callout-note ; expand -> collapsible callout
    for panel in mc.select('div.panel'):
        new = soup.new_tag('div')
        new['class'] = ['callout-note']
        src = panel.select_one('.panelContent') or panel
        for ch in list(src.contents):
            new.append(ch.extract())
        panel.replace_with(new)
    for ex in mc.select('div.expand-container'):
        ttl = ex.select_one('.expand-control-text')
        body = ex.select_one('.expand-content')
        new = soup.new_tag('div')
        new['class'] = ['callout-note']
        new['collapse'] = 'true'
        new['title'] = ttl.get_text().strip() if ttl else 'Details'
        for ch in list(body.contents if body else []):
            new.append(ch.extract())
        ex.replace_with(new)

    # images
    for img in mc.find_all('img'):
        src = img.get('data-image-src') or img.get('src', '')
        cid = img.get('data-linked-resource-container-id')
        attid = img.get('data-linked-resource-id')
        alias = img.get('data-linked-resource-default-alias')
        local = None
        m = re.match(r'attachments/(\d+)/(\d+)', src)
        if m:
            cid, attid = m.group(1), m.group(2)
            local = find_attachment(cid, attid)
        elif cid and attid:
            local = find_attachment(cid, attid)
        if not local:
            m2 = re.search(r'/(?:thumbnails|attachments)/(\d+)/([^?]+)', src)
            if m2:
                cid = m2.group(1)
                alias = urllib.parse.unquote(m2.group(2))
                local, attid = find_attachment_by_alias(cid, alias)
        if alias and alias.lower().endswith('.pdf') and img.find_parent('a'):
            a = img.find_parent('a')
            img.replace_with('📄 ' + alias)
            continue
        if not local:
            issues.append(f'image introuvable : {src[:100]}')
            img.decompose()
            continue
        alias = alias or att_alias.get((cid, attid))
        rel = copy_att(lang, local, cid, alias)
        w = img.get('width')
        img.attrs = {'src': rel, 'alt': img.get('alt') or ''}
        if w:
            img['width'] = w

    # links
    for a in mc.find_all('a'):
        href = a.get('href', '')
        u = urllib.parse.unquote(href)
        new = None
        if 'createpage.action' in href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            t = q.get('title', [''])[0]
            tgt = title_index.get((lang, slugify(strip_num(t)))) or title_index.get(('en', slugify(strip_num(t))))
            if not tgt:  # fuzzy: "Installation of X" -> page titled "X"
                st = re.sub(r'^(installation-of|installation-de|installation-d)-', '', slugify(strip_num(t)))
                for (l2, k2), p2 in title_index.items():
                    if l2 == lang and (k2 == st or k2.endswith(st) or st.endswith(k2)):
                        tgt = p2
                        break
            if tgt:
                new = page_link(lang, tgt['lang'], tgt['id'])
                issues.append(f'lien « {t} » (page inexistante dans Confluence) redirigé vers {new}, à vérifier')
            else:
                issues.append(f'lien vers page inexistante « {t} » (converti en texte)')
                a.unwrap()
                continue
        elif href.startswith('#'):
            new = '#' + anchor(href[1:])
        elif re.match(r'^attachments/(\d+)/(\d+)', href):
            m = re.match(r'^attachments/(\d+)/(\d+)', href)
            local = find_attachment(m.group(1), m.group(2))
            if local:
                al = a.get('data-linked-resource-default-alias') or att_alias.get((m.group(1), m.group(2)))
                new = copy_att(lang, local, m.group(1), al)
            else:
                issues.append(f'pièce jointe introuvable : {href}')
        elif re.match(r'^[^/:]*?(\d+)\.html(#.*)?$', u):
            m = re.match(r'^[^/:]*?(\d+)\.html(?:#(.*))?$', u)
            new = page_link(lang, lang, m.group(1), m.group(2))
            if not new:
                issues.append(f'lien interne non résolu : {href}')
        elif 'atlassian.net/wiki' in href or href.startswith('/wiki/'):
            m = re.search(r'/spaces/([A-Z]+)(?:/pages/(\d+))?', href)
            if m and m.group(1) in SPACE_KEYS:
                tl = SPACE_KEYS[m.group(1)]
                if m.group(2):
                    new = page_link(lang, tl, m.group(2))
                if not new:
                    new = 'index.qmd' if tl == lang else f'../{tl}/index.qmd'
            else:
                issues.append(f'lien Confluence non résolu : {href}')
        a.attrs = {}
        if new:
            a['href'] = new
        elif href:
            a['href'] = href

    # headings
    for h in mc.find_all(re.compile(r'^h[1-6]$')):
        hid = h.get('id')
        h.attrs = {}
        if hid:
            h['id'] = anchor(hid)
    if mc.find('h1'):
        for h in mc.find_all(re.compile(r'^h[1-6]$')):
            h.name = 'h' + str(min(6, int(h.name[1]) + 1))

    # colored text spans
    for sp in mc.find_all('span'):
        mcol = re.search(r'legacy-color-text-([a-z]+)', ' '.join(sp.get('class', [])))
        if mcol and mcol.group(1) in COLORS:
            sp.attrs = {'class': ['c-' + mcol.group(1)]}
        else:
            sp.unwrap()

    # unwrap layout divs, strip attributes
    for t in mc.find_all('div'):
        if not any(c.startswith('callout-') for c in t.get('class', [])):
            t.unwrap()
    for t in mc.find_all(['colgroup']):
        t.decompose()
    for t in mc.find_all(['table', 'tr', 'td', 'th', 'tbody', 'thead', 'p', 'ul', 'ol', 'li', 'code', 'strong', 'em', 'u', 'sup', 'sub']):
        keep = {k: t[k] for k in ('colspan', 'rowspan') if k in t.attrs}
        if t.name == 'code' and t.get('class'):
            keep['class'] = t['class']
        t.attrs = keep
    for pnode in mc.find_all('p'):
        if not pnode.get_text(strip=True) and not pnode.find('img'):
            pnode.decompose()
    if mc.select('[rowspan], [colspan]'):
        issues.append('tableau avec cellules fusionnées (vérifier le rendu)')
    mc.attrs = {}
    html = mc.decode_contents()

    md = subprocess.run(PANDOC + ['-f', 'html', '-t',
                         'markdown-simple_tables-multiline_tables-smart-raw_attribute',
                         '--wrap=none', '--markdown-headings=atx'],
                        input=html, capture_output=True, text=True, check=True).stdout
    md = re.sub(r'\n{3,}', '\n\n', md)
    if re.search(r'<table|<div|<span|<img', md):
        issues.append('HTML brut résiduel dans le Markdown (tableau complexe ?)')

    other = 'fr' if lang == 'en' else 'en'
    twin = by_key.get((other, p['key']))
    fm = ['---', 'title: ' + json.dumps(p['title'], ensure_ascii=False)]
    if twin:
        label = 'Version française' if other == 'fr' else 'English version'
        fm += ['other-links:', f'  - text: {json.dumps(label, ensure_ascii=False)}',
               f'    href: ../{other}/{twin["slug"]}.qmd', '    icon: translate']
    else:
        issues.append(f"pas d'équivalent {other.upper()}")
    fm += ['---', '']
    out = '\n'.join(fm) + '\n' + md.strip() + '\n'
    if p['children']:
        out += '\n' + ('## Contenu de cette section' if lang == 'fr' else '## In this section') + '\n\n'
        for c in p['children']:
            out += f"- [{c['title']}]({c['slug']}.qmd)\n"
    open(os.path.join(OUT, lang, p['slug'] + '.qmd'), 'w', encoding='utf-8').write(out)
    report[lang].append((p, issues))


for lang in SPACES:
    d = os.path.join(OUT, lang)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, '_metadata.yml'), 'w').write(f'lang: {lang}\nformat-links: false\n')
for p in pages.values():
    convert(p)


# ---------- 4. _quarto.yml ----------
def sidebar_items(nodes, indent):
    lines = []
    sp = ' ' * indent
    for n in nodes:
        if n['children']:
            lines += [f"{sp}- section: {json.dumps(n['title'], ensure_ascii=False)}",
                      f"{sp}  href: {n['lang']}/{n['slug']}.qmd",
                      f"{sp}  contents:"]
            lines += sidebar_items(n['children'], indent + 4)
        else:
            lines += [f"{sp}- text: {json.dumps(n['title'], ensure_ascii=False)}",
                      f"{sp}  href: {n['lang']}/{n['slug']}.qmd"]
    return lines


sb = []
for lang in SPACES:
    root = trees[lang][0]
    sb += [f'    - id: {lang}',
           f'      title: {json.dumps(root["title"], ensure_ascii=False)}',
           '      style: docked',
           '      collapse-level: 1',
           '      contents:',
           f'        - text: {json.dumps("Accueil" if lang == "fr" else "Home")}',
           f'          href: {lang}/index.qmd']
    sb += sidebar_items(root['children'], 8)

head = open(os.path.join(OUT, 'tools', '_quarto.head.yml'), encoding='utf-8').read()
tail = open(os.path.join(OUT, 'tools', '_quarto.tail.yml'), encoding='utf-8').read()
open(os.path.join(OUT, '_quarto.yml'), 'w', encoding='utf-8').write(
    head.rstrip() + '\n  sidebar:\n' + '\n'.join(sb) + '\n\n' + tail)

# ---------- 5. report ----------
lines = ['# Rapport de migration Confluence → Quarto', '',
         f"Pages converties : EN {len(report['en'])}, FR {len(report['fr'])}.", '',
         'Pages signalées pour relecture :', '']
for lang in SPACES:
    lines += [f'## {lang.upper()}', '']
    for p, iss in sorted(report[lang], key=lambda x: (sort_key(x[0]['title']), x[0]['title'])):
        if iss:
            lines.append(f"- **{p['title']}** (`{lang}/{p['slug']}.qmd`)")
            lines += [f'    - {i}' for i in sorted(set(iss))]
    lines.append('')
open(os.path.join(OUT, 'MIGRATION_REPORT.md'), 'w', encoding='utf-8').write('\n'.join(lines))
print('ok', len(pages), 'pages')
