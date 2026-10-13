"""Capture isolated fixture states through agent-browser; never use a real account."""
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

output = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/ripplesight-figma-capture')
output.mkdir(parents=True, exist_ok=True)
session = 'ripplesight-figma-matrix'
base = 'http://127.0.0.1:8668'
api = 'http://127.0.0.1:8670'
routes = {'home':'/', 'event':'/discover/stories/story-1', 'workspace':'/topics', 'daily':'/reports/daily/2026-10-06', 'leaderboard':'/leaderboard', 'discover':'/discover?mode=all', 'saved':'/discover/starred', 'login':'/login'}

def browser(*args, source=None):
    result = subprocess.run(['agent-browser','--session',session,*args], input=source, text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout

def evaluate(source):
    result = browser('eval','--stdin',source=source).strip()
    value = json.loads(result)
    return json.loads(value) if isinstance(value,str) else value

records = json.loads((output/"matrix.json").read_text()) if (output/"matrix.json").exists() else []
records = [x for x in records if (x["page"] != "login" or x["path"] == "/login") and Path(x["screenshot"]).is_file()]
browser('open',base)
for state, theme in [('normal','light'),('normal','dark'),('empty','light'),('error','light'),('forbidden','light'),('loading','light')]:
    urlopen(f'{api}/__fixture/state?value={state}').read()
    evaluate("document.cookie='hotkey_session=visual-fixture; path=/; SameSite=Lax'; localStorage.setItem('hotkey.publication.theme.v1',"+json.dumps(theme)+"); localStorage.setItem('hotkey.publication.saved.v1',"+json.dumps('[]' if state=='empty' else '["00000000-0000-4000-8000-000000000001"]')+"); localStorage.setItem('ripplesight.publication.notes.v1',JSON.stringify({'00000000-0000-4000-8000-000000000001':'隔离测试备注：只保存在本机。'})); JSON.stringify(true)")
    for width,height in [(1440,1000),(390,844)]:
        browser('set','viewport',str(width),str(height))
        for name,path in routes.items():
            if any(x['page']==name and x['state']==state and x['theme']==theme and x['width']==width for x in records):
                continue
            evaluate("document.cookie="+json.dumps('hotkey_session=; path=/; Max-Age=0' if name=='login' else 'hotkey_session=visual-fixture; path=/; SameSite=Lax')+"; JSON.stringify(true)")
            if state == 'loading':
                browser('eval','--stdin',source='setTimeout(()=>location.assign('+json.dumps(base+path)+'),50); JSON.stringify(true)')
            else:
                browser('open',base+path)
            if state != 'loading':
                browser('wait','--load','networkidle')
                # ThemeProvider restores the persisted preference after hydration.
                browser('wait','--fn',f"document.documentElement.classList.contains('dark') === {str(theme=='dark').lower()}")
            else:
                browser('wait','--fn',"location.pathname === "+json.dumps(path.split('?')[0])+" && !!document.querySelector('[aria-busy=true],[data-slot=skeleton]')")
            measurement=evaluate("JSON.stringify({path:location.pathname,theme:document.documentElement.classList.contains('dark')?'dark':'light',h1:[...document.querySelectorAll('h1,[role=heading][aria-level=\"1\"]')].map(x=>x.textContent),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,main:[...document.querySelectorAll('main,#page-content')].map(x=>({width:x.clientWidth,scroll:x.scrollWidth})),headings:[...document.querySelectorAll('h1,h2,[role=heading]')].map(x=>x.textContent),status:[...document.querySelectorAll('[role=status],[role=alert]')].map(x=>x.getAttribute('aria-label')||x.textContent),images:[...document.images].filter(x=>x.getBoundingClientRect().width).map(x=>({src:x.getAttribute('src'),valid:x.complete&&x.naturalWidth>0,width:x.clientWidth,height:x.clientHeight})),columns:[...document.querySelectorAll('.reading-columns,.workspace-columns,.edition-columns,.login-columns')].map(x=>({template:getComputedStyle(x).gridTemplateColumns,gap:getComputedStyle(x).columnGap}))})")
            screenshot=output/f'{name}-{state}-{theme}-{width}.png'
            browser('screenshot',str(screenshot))
            record={'page':name,'state':state,'theme':theme,'width':width,'screenshot':str(screenshot),**measurement}
            record['overflow']=measurement['documentWidth']>width or any(x['scroll']>x['width']+1 for x in measurement['main'])
            records.append(record)
            (output/'matrix.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
            print(name,state,theme,width,'overflow' if record['overflow'] else 'fits',' | '.join(measurement['h1']),flush=True)
urlopen(f'{api}/__fixture/state?value=normal').read()
browser('close')
print(f'Captured {len(records)} cases. Geometry failures: {sum(x["overflow"] for x in records)}.',flush=True)
