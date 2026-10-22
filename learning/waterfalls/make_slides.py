"""Prints one DevTools-style waterfall slide (a <section>) for learning/waterfalls/slides.html.

The numbers are copied by hand from learning/baseline-dev-measurements.md, learning/thumbnails.md
and learning/add-observability.md 4c; see learning/waterfalls.md for which bars are measured and which
are estimated. Usage: python3 learning/waterfalls/make_slides.py j1d   (ids: the keys of S at the end)
Steps of a journey follow one another on the time axis; requests inside one step start together.
"""
import sys
W=862; COLS=[("Name",430),("Status",100),("Type",100),("Size",170),("Time",130)]
COLOR={"c":"#E8913A","t":"#3FAE6A","d":"#4C8DF0","S":"#1B6B3F","w":"#A78BFA"}
LEG={"q":'<span style="color:#9AA0A6">━</span> 排隊',"c":'<span style="color:#E8913A">■</span> 建立連線',
 "w":'<span style="color:#A78BFA">■</span> 上傳內容',"t":'<span style="color:#3FAE6A">■</span> 等伺服器回應（TTFB）',
 "S":'<span style="color:#2E9E5E">■</span> Django 實際處理（nginx log）',"d":'<span style="color:#4C8DF0">■</span> 下載',
 "u":'<span style="color:#9AA0A6">┅</span> 只有總時間，沒拆分'}
def r1(x): return round(x,1)
def seg(kind,ms,px,shown=None):
    if kind=="s": return f'<div style="flex:none;width:{r1(ms*px)}px;height:18px;background:rgba(255,255,255,0.03)"></div>'
    if kind=="B":  # (B, color_kind, real, shown)
        return None
    w=max(r1(ms*px),2)
    if kind=="q": return f'<div style="flex:none;width:{w}px;height:4px;background:#9AA0A6"></div>'
    if kind=="u": return f'<div style="flex:none;width:{r1(max(w-4,1))}px;height:14px;border:2px dashed #9AA0A6"></div>'
    if kind=="S": return f'<div style="flex:none;width:{w}px;height:18px;background:#1B6B3F;border:2px solid #2E9E5E"></div>'
    return f'<div style="flex:none;width:{w}px;height:18px;background:{COLOR[kind]}"></div>'
def seglen(s): return s[3] if s[0]=="B" else s[1]
def render_segs(segs,start,px,axis,used):
    parts=[]; pos=0
    if start>0: parts.append(seg("s",min(start,axis),px)); pos=start
    for s in segs:
        if pos>=axis: break
        if s[0]=="B":
            _,k,real,shown=s; used.add(k); half=min(shown/2,axis-pos)
            parts.append(seg(k,half,px)); parts.append('<div style="flex:none;width:10px;height:26px;background:#202124;border-left:2px solid #E8EAED;border-right:2px solid #E8EAED"></div>')
            parts.append(seg(k,max(min(shown/2,axis-pos-half)-10/px,0.1),px)); pos+=shown; continue
        k,ms=s; used.add(k); ms=min(ms,axis-pos); parts.append(seg(k,ms,px)); pos+=ms
    return "".join(parts)
def cells(vals):
    return "".join(f'<p style="width:{w}px;font-size:24px;white-space:nowrap;color:{"#E8EAED" if i==0 else "#BDC1C6"}">{v}</p>' for i,((_,w),v) in enumerate(zip(COLS,vals)))
def slide(sid,title,sub,axis,step,unit,steps,gap,notes):
    px=W/axis; used=set(); body=[]; t0=0; nrows=0
    for head,rows in steps:
        body.append(f'<div style="display:flex;align-items:center;height:36px;background:#2B2C30;border-bottom:1px solid #2F3033"><p style="font-size:24px;color:#F2B46B;white-space:nowrap">{head}</p></div>'); nrows+=1
        dur=0
        for name,status,typ,size,time,off,segs in rows:
            bar=render_segs(segs,t0+off,px,axis,used) if segs else ""
            body.append(f'<div style="display:flex;align-items:center;height:36px;border-bottom:1px solid #2F3033">{cells([name,status,typ,size,time])}<div style="width:{W}px;height:36px;display:flex;align-items:center">{bar}</div></div>'); nrows+=1
            dur=max(dur,off+sum(seglen(s) for s in segs))
        if rows and dur>0: t0+=dur+gap
    h=41+nrows*37; n=int(axis//step)
    lines="".join(f'<line x1="{r1(k*step*px)}" y1="0" x2="{r1(k*step*px)}" y2="{h}" stroke="#3C4043" stroke-width="2"/>' for k in range(1,n+1) if k*step<axis)
    svg=f'<svg aria-label="時間格線" width="{W}" height="{h}" viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" style="position:absolute;left:994px;top:228px;width:{W}px;height:{h}px">{lines}</svg>'
    ticks=""
    for k in range(n+1):
        if k*step>=axis: break
        v=k*step; lab=f"{v/1000:g} s" if unit=="s" else f"{v:g} ms"
        ticks+=f'<p style="width:{r1(min(step*px,W-k*step*px))}px;font-size:24px;white-space:nowrap;color:#9AA0A6">{lab}</p>'
    head="".join(f'<p style="width:{w}px;font-size:24px;font-weight:700;color:#9AA0A6">{c}</p>' for c,w in COLS)
    legend="　".join(LEG[k] for k in ["q","c","w","t","S","d","u"] if k in used)+"　≈ 推定或示意"
    return f'''<section id="{sid}" data-transition="fade" style="background:#202124;color:#E8EAED;font-family:'Noto Sans TC', Arial, sans-serif;padding:56px 64px;display:flex;flex-direction:column;gap:20px">
{svg}
<h2 style="font-size:44px;font-weight:700;line-height:1.15;color:#F1F3F4">{title}</h2>
<p style="font-size:24px;color:#9AA0A6;line-height:1.4;white-space:nowrap">{sub}</p>
<div style="display:flex;flex-direction:column">
<div style="height:48px;background:#292A2D;display:flex;align-items:center;padding:0 16px"><p style="font-size:24px;color:#9AA0A6;white-space:nowrap">●　⊘　｜　Filter　｜　<span style="color:#E8EAED">All</span>　Fetch/XHR　Doc　CSS　JS　Img　｜　□ Disable cache</p></div>
<div style="display:flex;align-items:center;height:40px;border-bottom:1px solid #3C4043">{head}<div style="width:{W}px;display:flex">{ticks}</div></div>
{chr(10).join(body)}
</div>
<p style="position:absolute;left:64px;bottom:28px;width:1792px;font-size:24px;color:#BDC1C6;white-space:nowrap">{legend}</p>
<aside>{notes}</aside>
</section>'''
R=lambda name,status,typ,size,time,off,segs:(name,status,typ,size,time,off,segs)
SEQ="步驟依序接起來，中間的操作時間省略"
# ---------- J1
J1D=[("① 開頁面（登入前）· 53 個請求，約 50 個是 Vite 開發模組",[R("（53 個請求合併成一列）","","","","498 ms",0,[("u",498)])]),
 ("② 輸入錯誤密碼",[R("login/","400","fetch","—","404 ms",0,[("u",3),("t",401)])]),
 ("③ 輸入正確密碼",[R("login/","200","fetch","—","207 ms",0,[("u",119),("t",88)])]),
 ("④ 登入後 4 個平行請求 · 其中 receipts 列表 ttfb 163 ms、10 KB",[R("session · receipts · calendar ×2","200","fetch","—","122–448 ms",0,[("u",448)])])]
J1N=[("① 開頁面（取自 4c 那次的 trace，tracing build、第一次造訪）",[
  R("<lan-ip>","200","document","—","140 ms",0,[("u",140.2)]),
  R("index-….js","200","script","154 KB","819 ms",145,[("u",818.5)]),
  R("index-….css","200","stylesheet","—","5 ms",145,[("u",5.4)]),
  R("css2?family=…（Google Fonts）","200","stylesheet","—","62 ms",152,[("u",61.5)]),
  R("telemetry-….js","200","script","—","84 ms",920,[("u",83.5)])]),
 ("② 輸入錯誤密碼 · 這次沒量",[]),
 ("③ 輸入正確密碼 · Django 48 ms",[R("login/","200","fetch","—","102 ms",0,[("u",27),("S",48),("u",27)])]),
 ("④ 登入後的平行請求 · 這次沒記",[])]
# ---------- J2
def j2d(zoom):
  rd=("B","t",34945,400) if zoom else ("t",34945)
  return [("① 上傳收據照片（2.9 MB HEIC）",[R("receipts/","201","fetch","—","1,467 ms",0,[("u",4),("c",189),("t",1274)])]),
 ("② 打開核對頁 · 4 個平行 GET，沿用已開的連線",[R(f"GET #{i}（筆記未記名稱）","200","fetch","—","≈43 ms",0,[("u",18),("t",24),("d",1)]) for i in (1,2,3,4)]),
 ("③ vLLM 讀取 · 伺服器自己記 34,713 ms"+("　· 長條中間省略" if zoom else ""),[R("receipts/48/extractions/","201","fetch","—","34,945 ms",0,[rd])]),
 ("④ 入帳",[R("receipts/48/expense/","201","fetch","—","267 ms",0,[("u",3),("c",192),("t",72)])]),
 ("⑤ 入帳後重新載入 · 6 個 GET，每個都開了新連線",[R(f"GET #{i}（筆記未記名稱）","200","fetch","—",f"≈{215+t} ms",0,[("c",215),("t",t)]) for i,t in zip(range(1,7),(21,25,28,32,36,40))])]
def j2n(zoom):
  rd=("B","S",29600,400) if zoom else ("S",29600)
  return [("① 上傳收據照片 · nginx：rt 1.826 s，其中 Django 0.406 s",[R("receipts/","201","fetch","—","2,065 ms",0,[("u",239),("w",1420),("S",406)])]),
 ("② 打開核對頁 · 這次沒記",[]),
 ("③ vLLM 讀取 · Django 29.6 s（同樣 806 個輸出 token）"+("　· 長條中間省略" if zoom else ""),[R("receipts/…/extractions/","201","fetch","—","29.7 s",0,[("u",50),rd,("u",50)])]),
 ("④ 入帳 · Django 28 ms",[R("receipts/…/expense/","201","fetch","—","202 ms",0,[("u",87),("S",28),("u",87)])]),
 ("⑤ 入帳後重新載入 · 這次沒記",[])]
# ---------- J3
J3D=[("① 換月份",[R("calendar/?month=2026-09","200","fetch","—","164 ms",0,[("q",146),("t",17),("d",1)])]),
 ("② 選一天 · 兩個請求都開了新連線（配對推定）",[R("calendar/?month=2026-09","200","fetch","—","308 ms",0,[("q",1),("c",292),("t",14),("d",1)]),R("calendar/day/?date=…","200","fetch","—","321 ms",0,[("q",1),("c",292),("t",24),("d",4)])]),
 ("③ 打開編輯表單 · 沒有請求（資料已經載入）",[]),
 ("④ 儲存",[R("expenses/31/","200","fetch","—","442 ms",0,[("q",1),("c",254),("t",185),("d",2)])]),
 ("⑤ 儲存後重新載入（只記了範圍，切法推定）",[R("session/","200","fetch","—","≈148 ms",0,[("t",146),("d",2)]),R("calendar/?month=2026-09","200","fetch","—","≈152 ms",0,[("u",140),("t",10),("d",2)]),R("calendar/day/?date=…","200","fetch","—","≈146 ms",0,[("u",135),("t",10),("d",1)])])]
J3N=[("① 換月份 · Django 4 ms",[R("calendar/?month=…","200","fetch","—","169 ms",0,[("u",82.5),("S",4),("u",82.5)])]),
 ("② 選一天 · Django 6 ms，沿用已開的連線",[R("calendar/ 月＋日","200","fetch","—","145 ms",0,[("u",69.5),("S",6),("u",69.5)])]),
 ("③ 打開編輯表單 · 沒有請求",[]),
 ("④ 儲存 · Django 9 ms，沿用已開的連線",[R("expenses/31/","200","fetch","—","62 ms",0,[("u",26.5),("S",9),("u",26.5)])]),
 ("⑤ 儲存後重新載入 · 這次沒記",[])]
# ---------- J4
J4D=[("① 打開讀取結果頁",[R("extractions/","200","fetch","18.6 KB","152 ms",0,[("u",125),("t",27)])]),
 ("② 列表小圖：35 張、12.9 MB（實際是 1200×1600 預覽圖）· 個別長條示意",[
  R("preview/ ≈","200","jpeg","≈368 KB","≈950 ms",0,[("t",50),("d",900)]),
  R("preview/ ≈","200","jpeg","≈368 KB","≈1,160 ms",0,[("t",60),("d",1100)]),
  R("preview/ ≈","200","jpeg","≈368 KB","≈1,345 ms",10,[("t",45),("d",1300)]),
  R("preview/（前 4 張裡等最久：521 ms）","200","jpeg","≈368 KB","≈1,771 ms",740,[("q",521),("t",50),("d",1200)]),
  R("preview/ ≈","200","jpeg","≈368 KB","≈1,860 ms",1340,[("q",200),("t",60),("d",1600)]),
  R("preview/（最慢一張）","200","jpeg","≈368 KB","4,300 ms",40,[("q",300),("t",70),("d",3930)]),
  R("… 其餘 29 張","","","","",0,[])])]
J4N=[("① 打開讀取結果頁 · 這次的表沒記 JSON",[]),
 ("② 列表小圖：30 張預覽圖、11.4 MB · 下面 4 列是瀏覽器 span 實測",[
  R("preview/","200","jpeg","322 KB","7,088 ms",0,[("q",6477),("t",47),("d",564)]),
  R("preview/","200","jpeg","443 KB","7,070 ms",0,[("q",6243),("t",61),("d",767)]),
  R("preview/","200","jpeg","378 KB","7,001 ms",0,[("q",5985),("t",77),("d",940)]),
  R("preview/（最快一張）","200","jpeg","487 KB","1,432 ms",0,[("q",5),("t",121),("d",1306)]),
  R("… 其餘 26 張","","","","",0,[])])]
TA=[("① 打開讀取結果頁 · 這次沒記 JSON",[]),
 ("② 列表小圖：42 張縮圖、1.08 MB · 隨捲動載入，個別長條示意",[
  R("thumbnail/ ≈","200","jpeg","≈11 KB","≈45 ms",0,[("t",40),("d",5)]),
  R("thumbnail/ ≈","200","jpeg","≈11 KB","≈52 ms",0,[("t",46),("d",6)]),
  R("thumbnail/（排隊最久）","200","jpeg","≈11 KB","≈143 ms",0,[("q",98),("t",40),("d",5)]),
  R("thumbnail/（最慢一張）","200","jpeg","≈11 KB","250 ms",0,[("u",250)]),
  R("thumbnail/（捲動後）≈","200","jpeg","≈11 KB","≈48 ms",1800,[("t",43),("d",5)]),
  R("thumbnail/（捲動後）≈","200","jpeg","≈11 KB","≈50 ms",3500,[("t",45),("d",5)]),
  R("thumbnail/（最後一張）≈","200","jpeg","≈11 KB","≈47 ms",5900,[("t",42),("d",5)]),
  R("… 其餘 35 張","","","","",0,[])])]
TB=[("① 打開讀取結果頁 · 這次沒記 JSON",[]),
 ("② 列表小圖：42 張縮圖 · 全部來自瀏覽器快取，0 個請求到伺服器",[
  R("thumbnail/","200","jpeg","(disk cache)","0 ms",0,[("d",0.5)]),
  R("thumbnail/","200","jpeg","(disk cache)","0 ms",5,[("d",0.5)]),
  R("thumbnail/","200","jpeg","(disk cache)","0 ms",60,[("d",0.5)]),
  R("thumbnail/","200","jpeg","(disk cache)","0 ms",140,[("d",0.5)]),
  R("thumbnail/（最後一張，231 ms）","200","jpeg","(disk cache)","0 ms",231,[("d",0.5)]),
  R("… 其餘 37 張","","","","",0,[])])]
S={
"j1d":("J1 登入 · dev","Vite 開發伺服器 ＋ runserver · 2026-10-16 · "+SEQ,1800,400,"ms",J1D,60,"來源：baseline-dev-measurements.md Step 5。登入後的 4 個平行請求只記了範圍 122–448 ms，所以合成一列虛線。"),
"j1n":("J1 登入 · nginx","nginx ＋ runserver · 2026-10-17 · "+SEQ,1800,400,"ms",J1N,60,"來源：開頁面取自 add-observability.md 4c（documentLoad 1,004 ms，每個檔案只有總時間）；登入取自 baseline Part 4.2（102 ms，Django 48 ms）。兩者不是同一次量測。index.js 那 819 ms 是部署後第一次造訪、沒有快取。"),
"j2d":("J2 收據照片 → 支出 · dev","Kroger 照片 · 2026-10-16 · "+SEQ+"（每段約 0.3 s）",40000,5000,"s",j2d(False),300,"來源：baseline Step 8。vLLM 讀取佔整個流程約 95%。"),
"j2n":("J2 收據照片 → 支出 · nginx","同一張照片 · 2026-10-17 · "+SEQ+"（每段約 0.3 s）",40000,5000,"s",j2n(False),300,"來源：baseline Part 4.2。這次只記了上傳、讀取、入帳三步，且有 nginx log 的 Django 時間。"),
"j2dz":("J2 放大 · dev","vLLM 讀取的長條中間省略 34.5 s，之後的刻度要加上這段",3000,500,"ms",j2d(True),40,"上傳的 1.27 s TTFB 裡，Step 9 推算約 900 ms 是 2.9 MB 經 Wi-Fi 傳送。入帳後 6 個請求各自花約 215 ms 建立新連線。"),
"j2nz":("J2 放大 · nginx","vLLM 讀取的長條中間省略 29.2 s，之後的刻度要加上這段",3000,500,"ms",j2n(True),40,"上傳：nginx 收完整個檔案才交給 Django，rt − urt ≈ 1.42 s 就是照片經 Wi-Fi 傳過去的時間；Django 只花 0.41 s。最前面的 239 ms 是瀏覽器與 nginx 之間的其他時間（沒拆分）。"),
"j3d":("J3 找到並修改一筆支出 · dev","2026-10-16 · "+SEQ,1300,200,"ms",J3D,30,"來源：baseline Step 6。伺服器只要 14–24 ms，但建立連線要約 290 ms。"),
"j3n":("J3 找到並修改一筆支出 · nginx","2026-10-17 · "+SEQ,1300,200,"ms",J3N,30,"來源：baseline Part 4.2。nginx 讓連線保持 75 秒，點擊時沿用已開的連線，不用再付約 250 ms 建立連線。剩下的等待是 Wi-Fi，不是程式。"),
"j4d":("J4 看讀取結果 · dev（預覽圖）","2026-10-16 · 沒捲動 · 圖片只記了總數、最慢一張和前 4 張",7500,1000,"s",J4D,30,"來源：baseline Step 7。實測：35 張、12.9 MB、最慢 4.3 s。521 ms 只是前 4 張裡最久的排隊，不是全部的最大值；其餘長條是推定，排隊被低估了（見 waterfalls.md）。"),
"j4n":("J4 看讀取結果 · nginx（預覽圖，縮圖前）","2026-10-17 · add-observability.md 4c 的瀏覽器 span · 沒捲動 · 同一時間點一起要求",7500,1000,"s",J4N,30,"來源：add-observability.md 4c part 2。Django 處理同一批圖每張只要 2–11 ms。最慢的幾張大多在排隊：6 條連線，30 張 ~375 KB 的圖要輪流用。"),
"j4a":("J4 看讀取結果 · Step A 縮圖","2026-10-17 · 每張約 11 KB · 圖片隨捲動載入",7500,1000,"s",TA,30,"來源：thumbnails.md §5。實測：42 列、1.08 MB、最慢 250 ms、最長排隊 98 ms；約 6 s 才全部完成，主要是手動捲動的時間。個別長條是示意。"),
"j4az":("J4 Step A 放大：第一個畫面的縮圖","同一組 · 時間軸 0–300 ms",300,50,"ms",[TA[0],(TA[1][0],TA[1][1][:4])],30,"放大後：每張只要幾十毫秒；排隊最久的一張等了 98 ms（改之前是 1,523 ms 或 6 秒以上）。"),
"j4b":("J4 看讀取結果 · Step B 再訪（快取）","2026-10-17 · 同一頁再打開一次 · 時間軸和 Step A 一樣",7500,1000,"s",TB,30,"來源：thumbnails.md §5。實測：0 個請求到伺服器，最後一張圖在 231 ms 顯示。表格是示意，實際顯示 memory 或 disk cache 看瀏覽器。"),
}
sid=sys.argv[1]; print(slide(sid,*S[sid]))
