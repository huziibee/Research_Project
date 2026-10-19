#!/usr/bin/env python3
"""Build a private-study reference archive from explicitly linked public publisher/OA PDFs.

Never generates substitute PDFs for missing citations. All source provenance is logged.
"""
import csv, datetime, hashlib, io, json, os, pathlib, re, time, urllib.error, urllib.parse, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=pathlib.Path(__file__).resolve().parent
ROWS=json.loads((ROOT/'reference_manifest.json').read_text(encoding='utf-8'))
OUT=ROOT/'out'
PDFS=OUT/'pdfs'
PDFS.mkdir(parents=True,exist_ok=True)
AGENT='Mozilla/5.0 (compatible; AcademicReferenceFetcher/1.0; research literature archival request)'
MAXSIZE=26*1024*1024

def fetch(url,limit=MAXSIZE):
    req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/pdf,*/*;q=0.8'})
    with urllib.request.urlopen(req,timeout=45) as resp:
        data=resp.read(limit+1)
        if len(data)>limit: raise ValueError('pdf_too_large')
        if not data.startswith(b'%PDF-'): raise ValueError(f'not_pdf:{resp.headers.get("Content-Type","")}:head={data[:32]!r}')
        if b'%%EOF' not in data[-16384:]: raise ValueError('missing_EOF_marker')
        return data,resp.geturl()

def fallback_urls(row):
    url=row.get('url','')
    links=[url] if url else []
    m=re.search(r'arxiv.org/pdf/(\d{4}\.\d{4,5})',url)
    if m:
        aid=m.group(1)
        links.extend([f'https://export.arxiv.org/pdf/{aid}',f'https://arxiv.org/pdf/{aid}.pdf'])
    if row['id']=='v35-16':
        try:
            req=urllib.request.Request('https://api.openalex.org/works/https://doi.org/10.1109/LRA.2025.3560864',headers={'User-Agent':AGENT})
            data=json.load(urllib.request.urlopen(req,timeout=12))
            for l in [data.get('best_oa_location'),*(data.get('locations') or [])]:
                if l and l.get('pdf_url'):links.append(l['pdf_url'])
        except Exception as e: print('OpenAlex fallback failed:',repr(e),flush=True)
    return list(dict.fromkeys([x for x in links if x]))

def attempt(row):
    if row['type'] not in {'pdf','pdf_try'}:
        return {'id':row['id'],'status':'LINK_ONLY','reason':row['type'],'url':row.get('landing','')}
    errors=[]
    for url in fallback_urls(row):
        try:
            b,final=fetch(url)
            name=row['id']+'_'+re.sub(r'[^A-Za-z0-9]+','_',row['title']).strip('_')[:70]+'.pdf'
            path=PDFS/name
            path.write_bytes(b)
            return {'id':row['id'],'status':'PDF_INCLUDED','filename':'papers/'+name,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'source_url':final}
        except Exception as e:
            errors.append(f'{url} => {type(e).__name__}:{str(e)[:100]}')
    return {'id':row['id'],'status':'PDF_UNAVAILABLE','attempt_errors':errors,'url':row.get('landing','')}

results={}
with ThreadPoolExecutor(max_workers=6) as pool:
    futures={pool.submit(attempt,row):row['id'] for row in ROWS}
    for future in as_completed(futures):
        key=futures[future]; result=future.result();results[key]=result
        print(key,result['status'],result.get('bytes',''),flush=True)

records=[]
for row in ROWS:
    status=results[row['id']]
    records.append(dict(row,**status))

with (OUT/'reference_index.csv').open('w',encoding='utf-8',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['id','title','year','role','status','filename','source_url','landing','url','reason','sha256','bytes'],extrasaction='ignore')
    writer.writeheader();writer.writerows(records)

(OUT/'reference_index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
num=sum(x['status']=='PDF_INCLUDED' for x in records)
md=['# Robot Compound Ambiguity Research - Full Reference Index','',f'Compiled: {datetime.date.today().isoformat()}','',f'**{num} verified PDFs / {len(records)} unique references (22 from paper v35 and 1 additional Bayesian clarification paper).**','', 'PDFs are from publisher repositories, preprint archives, or author-accessible sources. This archive is for personal research use. Copyright and licensing remain with original rights holders.','', '**Never substitute this index for checking the paper version, bibliography, or source permissions.**','', '| Ref | Year | Status | Paper | Role in our architecture | Link |','|---|---|---|---|---|---|']
for x in records:
    desc=x['title'].replace('|','/')
    role=x['role'].replace('|','/')
    link=x.get('source_url') or x.get('landing') or x.get('url') or ''
    md.append(f'| {x["id"]} | {x["year"]} | {x["status"]} | {desc} | {role} | {link} |')
md+=['','## What was not included','']
for x in records:
    if x['status']!='PDF_INCLUDED':
        md.append(f'- **{x["id"]}: {x["title"]}** - {x["status"]} ({x.get("reason", "download failed or unavailable")}). {x.get("landing") or x.get("url") or "No verified public link."}')
md+=['','## Recommended reading order','',
 '1. **Global Grounding** (v35-16) - global object assignment, compounding references.',
 '2. **AmbiK** (v35-01) and **CLARA** (v35-02) - task ambiguity and ambiguity-to-clarification decisions.',
 '3. **CoDraw-iCR** (v35-03) and **ClarifyVC** (v35-11) - interactive disambiguation and multi-turn evaluation.',
 '4. **Bayesian Active Learning** (extra-23) and **KnowNo** (v35-12) - query informativeness and preserved uncertainty.',
 '5. **Indirect Speech** (v35-04, v35-10) - recover what the speaker really intends.',
 '6. **SayCan** (v35-13) - grounding and execution-capability separation.',
 '7. **Qwen3/QLoRA/Gemma4** (v35-17/18/20) - implementation and model comparators.',
 '', '## Integrity','', 'PDF files were checked for %PDF signature, EOF marker and SHA-256. Empty, HTML, paywalled and broken responses are never added as paper PDFs.']
(OUT/'README_REFERENCE_INDEX.md').write_text('\n'.join(md)+'\n',encoding='utf-8')

archive=ROOT/'compound_ambiguity_all_references.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for filename in sorted(PDFS.glob('*.pdf')):
        z.write(filename,arcname='papers/'+filename.name)
    for filename in ['README_REFERENCE_INDEX.md','reference_index.json','reference_index.csv']:
        z.write(OUT/filename,arcname=filename)
    z.write(ROOT/'reference_manifest.json',arcname='reference_manifest.json')
summary={'refs_total':len(ROWS),'pdfs_included':num,'link_only':len(records)-num,'zip_bytes':archive.stat().st_size,'zip_name':archive.name,'included_ids':[x['id'] for x in records if x['status']=='PDF_INCLUDED'],'unavailable_ids':[x['id'] for x in records if x['status']!='PDF_INCLUDED']}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
print('SUMMARY_JSON '+json.dumps(summary),flush=True)