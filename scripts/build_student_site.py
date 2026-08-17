import os,re,json,zipfile,subprocess,tempfile,shutil,urllib.request,sys,math
from pathlib import Path

PRE=2.4
SCENE_CFG={
 'mustafar': dict(title='Mustafar: High Ground',subtitle='Star Wars · Revenge of the Sith',url='https://pub-d3643445511f4a59b7c1923785cafa51.r2.dev/mods/dub/star-wars-i-have-the-high-ground/download/star-wars-i-have-the-high-ground.zip'),
 'obsession': dict(title='Obsession — Diner Scene',subtitle='Nikki & Bear',url='https://pub-d3643445511f4a59b7c1923785cafa51.r2.dev/mods/dub/obsession-diner-scene-dub-696743/download/obsession-diner-scene-dub-696743.zip'),
 'apex': dict(title='Apex',subtitle='Ben',url='https://pub-d3643445511f4a59b7c1923785cafa51.r2.dev/mods/dub/apex-movie-dance-scene-702670/download/apex-movie-dance-scene-702670.zip'),
 'twilight': dict(title='I Know What You Are',subtitle='Twilight · Bella & Edward',url='https://pub-d3643445511f4a59b7c1923785cafa51.r2.dev/mods/dub/twilight-i-know-what-you-are-dub-696453/download/twilight-i-know-what-you-are-dub-696453.zip'),
 'shrek': dict(title='Shrek 1 — Muffin Man',subtitle='Gingy, Farquaad & the Magic Mirror',url='https://pub-d3643445511f4a59b7c1923785cafa51.r2.dev/mods/dub/shrek-movie-1-the-muffin-man-mirror-700345/download/shrek-movie-1-the-muffin-man-mirror-700345.zip'),
}

def run(cmd,capture=False):
    kw={'check':True}
    if capture: kw.update(stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    else: kw.update(stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return subprocess.run(cmd,**kw)

def dur(p):
    try:return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],True).stdout.strip())
    except:return 0.0

def val(text,key):
    m=re.search(rf'(?mi)^\s*{re.escape(key)}\s*=\s*(.+?)\s*$',text)
    return m.group(1).strip() if m else None

def uq(s):
    if s is None:return ''
    s=s.strip()
    if s.startswith('[') and s.endswith(']'):s=s[1:-1].strip()
    return s.strip().strip('"').strip("'")

def char_norm(s):
    s=re.sub(r'\s+',' ',uq(s).replace('_',' ')).strip()
    aliases={'obi wan':'Obi-Wan','obi-wan':'Obi-Wan','anakin':'Anakin','ben':'Ben','nikki':'Nikki','bear':'Bear','bella':'Bella','edward':'Edward','gingerbread man':'Gingerbread Man','lord farquaad':'Lord Farquaad','guard':'Guard','mirror':'Mirror','thelonius':'Thelonius'}
    return aliases.get(s.lower(),s.title())

def cue_meta(txt):
    cap=uq(val(txt,'caption') or val(txt,'dialogue'))
    ts=val(txt,'dub_timestamps') or val(txt,'timestamp') or '0'
    ch=val(txt,'dub_characters') or val(txt,'character') or ''
    try:t=float(re.findall(r'-?\d+(?:\.\d+)?',ts)[0])
    except:t=0.0
    return cap,char_norm(ch),t

def safe_id(stem):
    s=stem.lower().replace(' - copy','')
    return re.sub(r'[^a-z0-9]+','_',s).strip('_')

def activity(audio):
    length=dur(audio)
    try:
        p=subprocess.run(['ffmpeg','-v','error','-i',str(audio),'-f','f32le','-ac','1','-ar','16000','-'],check=True,stdout=subprocess.PIPE)
        import array
        a=array.array('f');a.frombytes(p.stdout)
        frame=320;vals=[]
        for i in range(0,len(a),frame):
            x=a[i:i+frame]
            if not x:break
            vals.append(math.sqrt(sum(v*v for v in x)/len(x)))
        peak=max(vals or [0]);threshold=max(.006,peak*.12);active=[i for i,v in enumerate(vals) if v>=threshold]
        if not active:return length,0.0,max(.08,length)
        first=max(0,active[0]*.02-.02);last=min(length,(active[-1]+1)*.02+.02)
        return length,round(first,3),round(max(.08,last-first),3)
    except:return length,0.0,max(.08,length)

def first(root,patterns):
    fs=[p for p in root.rglob('*') if p.is_file()]
    for pat in patterns:
        for p in fs:
            if re.search(pat,p.name,re.I):return p

def download(url,dest):
    print('Downloading',url,flush=True)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=240) as r,open(dest,'wb') as f:shutil.copyfileobj(r,f)

def mix(out,inputs,total,bitrate='128k'):
    if len(inputs)==1:
        run(['ffmpeg','-y','-i',str(inputs[0]),'-t',f'{total:.3f}','-c:a','libmp3lame','-b:a',bitrate,str(out)]);return
    cmd=['ffmpeg','-y']
    for p in inputs:cmd+=['-i',str(p)]
    filt=''.join(f'[{i}:a]' for i in range(len(inputs)))+f'amix=inputs={len(inputs)}:normalize=0:dropout_transition=0,alimiter=limit=0.97[out]'
    cmd+=['-filter_complex',filt,'-map','[out]','-t',f'{total:.3f}','-c:a','libmp3lame','-b:a',bitrate,str(out)]
    run(cmd)

def build_scene(scene_id,cfg,outroot):
    work=Path(tempfile.mkdtemp(prefix='dublab_'))
    try:
        zp=work/'pack.zip';download(cfg['url'],zp)
        src=work/'src';src.mkdir()
        with zipfile.ZipFile(zp) as z:z.extractall(src)
        video=first(src,[r'^dub_video\.(ogv|mp4|webm|mkv)$']);backing=first(src,[r'^_backing_track\.(mp3|ogg|wav|m4a)$'])
        if not video or not backing:raise RuntimeError(f'{scene_id}: missing video/backing')
        scene_dur=dur(video);total=scene_dur+PRE;dest=outroot/scene_id;refs=dest/'refs';refs.mkdir(parents=True,exist_ok=True)
        print(scene_id,'duration',scene_dur,'source',video.name,flush=True)
        vf=f'tpad=start_duration={PRE}:start_mode=clone,scale=1280:-2:force_original_aspect_ratio=decrease,format=yuv420p'
        run(['ffmpeg','-y','-i',str(video),'-an','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','29','-movflags','+faststart',str(dest/'video.mp4')])
        icon=first(src,[r'^icon\.(png|jpg|jpeg|webp)$'])
        if icon:run(['ffmpeg','-y','-i',str(icon),'-frames:v','1',str(dest/'icon.png')])
        else:run(['ffmpeg','-y','-ss','1','-i',str(video),'-frames:v','1',str(dest/'icon.png')])
        backingwav=work/'backing.wav'
        run(['ffmpeg','-y','-i',str(backing),'-af',f'adelay={int(PRE*1000)}:all=1,apad','-t',f'{total:.3f}','-ac','2','-ar','44100','-c:a','pcm_s16le',str(backingwav)])
        cues=[];seen=set()
        configs=sorted([p for p in src.rglob('*') if p.is_file() and p.suffix.lower() in ('.ini','.txt') and '_pack_info' not in p.name.lower()])
        for cp in configs:
            txt=cp.read_text(errors='ignore');cap,ch,t=cue_meta(txt)
            if not ch or (not cap and 'dub_timestamp' not in txt.lower()):continue
            stem=cp.stem.replace(' - Copy','').replace(' - copy','');key=(stem.lower(),round(t,3),ch)
            if key in seen:continue
            seen.add(key);audio=None
            for ext in ('.mp3','.ogg','.wav','.m4a'):
                q=cp.with_name(stem+ext)
                if q.exists():audio=q;break
            if not audio:
                for ext in ('.mp3','.ogg','.wav','.m4a'):
                    q=cp.with_suffix(ext)
                    if q.exists():audio=q;break
            if not audio:continue
            lid=safe_id(stem);ref=refs/f'{lid}.mp3';run(['ffmpeg','-y','-i',str(audio),'-c:a','libmp3lame','-b:a','112k',str(ref)])
            d,vo,vd=activity(audio);cues.append(dict(id=lid,t=round(t,3),d=round(d,3),c=ch,text=cap,ref=f'assets/scenes/{scene_id}/refs/{lid}.mp3',vo=vo,vd=vd,_audio=str(audio)))
        cues.sort(key=lambda x:(x['t'],x['id']));roles=[]
        for c in cues:
            if c['c'] not in roles:roles.append(c['c'])
        stems={}
        for role in roles:
            rc=[c for c in cues if c['c']==role];rw=work/(safe_id(role)+'.wav')
            cmd=['ffmpeg','-y','-f','lavfi','-t',f'{total:.3f}','-i','anullsrc=r=44100:cl=stereo']
            for c in rc:cmd+=['-i',c['_audio']]
            chains=[];labels=['[0:a]']
            for i,c in enumerate(rc,1):
                ms=int(round((PRE+c['t'])*1000));lab=f'd{i}';chains.append(f'[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={ms}:all=1[{lab}]');labels.append(f'[{lab}]')
            chains.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0:dropout_transition=0[out]')
            cmd+=['-filter_complex',';'.join(chains),'-map','[out]','-t',f'{total:.3f}','-c:a','pcm_s16le',str(rw)];run(cmd);stems[role]=rw
        mix(dest/'original.mp3',[backingwav]+list(stems.values()),total);mix(dest/'no_everyone.mp3',[backingwav],total)
        beds={'Everyone':f'assets/scenes/{scene_id}/no_everyone.mp3'}
        for role in roles:
            out=dest/f'no_{safe_id(role)}.mp3';mix(out,[backingwav]+[p for r,p in stems.items() if r!=role],total);beds[role]=f'assets/scenes/{scene_id}/{out.name}'
        for c in cues:c.pop('_audio',None)
        return dict(id=scene_id,title=cfg['title'],subtitle=cfg['subtitle'],duration=round(scene_dur,3),preRoll=PRE,video=f'assets/scenes/{scene_id}/video.mp4',icon=f'assets/scenes/{scene_id}/icon.png',original=f'assets/scenes/{scene_id}/original.mp3',beds=beds,roles=roles,lines=cues,_packReady=True)
    finally:shutil.rmtree(work,ignore_errors=True)

def patch_index(scenes):
    src=Path('index.html').read_text()
    payload=json.dumps(scenes,ensure_ascii=False,separators=(',',':'))
    start=src.index('const SCENES=');end=src.index('\nconst $=',start)
    src=src[:start]+'const SCENES='+payload+';'+src[end:]
    src=src.replace('Your teacher provides the scene-pack files separately. The first time you open a scene, choose its pack file. DubLab stores it privately in this browser for later sessions.','Choose a scene and start dubbing. Scenes load automatically and are cached by your browser after the first play.')
    Path('site').mkdir(exist_ok=True);Path('site/index.html').write_text(src)
    for name in ('.nojekyll',):
        Path('site/'+name).write_text('')

def main():
    out=Path('site/assets/scenes');out.mkdir(parents=True,exist_ok=True);meta=Path('site/scenes.generated.json')
    if meta.exists():
        scenes=json.loads(meta.read_text());print('Using cached converted scene library',flush=True)
    else:
        scenes={sid:build_scene(sid,cfg,out) for sid,cfg in SCENE_CFG.items()};meta.write_text(json.dumps(scenes,ensure_ascii=False,separators=(',',':')))
    patch_index(scenes)
if __name__=='__main__':main()
