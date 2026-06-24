
import csv, json, re, xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from collections import defaultdict, deque

APP_TITLE = "Harris Matrix Editor 4.0 BAR"
TYPE_COLORS = {
    "Deposit":"#F6E3A1", "Cut":"#E88B8B", "Fill":"#F2B66D",
    "Structural":"#9FC4E8", "Natural":"#D8D8D8",
    "Same context":"#F3B6C4", "Unknown":"#EFEFEF"
}
BOX_W, BOX_H = 108, 40

RELATION_PATTERNS = [
    (r'\b(F\d+[A-Za-z]?)\s+(?:overlejrer|ligger over|over|is above|above)\s+(F\d+[A-Za-z]?)\b', "above"),
    (r'\b(F\d+[A-Za-z]?)\s+(?:underlejrer|ligger under|under|is below|below)\s+(F\d+[A-Za-z]?)\b', "below"),
    (r'\b(F\d+[A-Za-z]?)\s+(?:skærer|skaerer|cuts|cut)\s+(F\d+[A-Za-z]?)\b', "cuts"),
    (r'\b(F\d+[A-Za-z]?)\s+(?:fylder|fills|fill of)\s+(F\d+[A-Za-z]?)\b', "fills"),
    (r'\b(F\d+[A-Za-z]?)\s*(?:=|samme som|same as)\s*(F\d+[A-Za-z]?)\b', "same"),
]

SAMPLE = {
    "nodes": [
        {"id":"T","label":"T","type":"Unknown","x":520,"y":40},
        {"id":"F1","label":"F1","type":"Deposit","x":520,"y":100},
        {"id":"F2","label":"F2","type":"Deposit","x":520,"y":160},
        {"id":"F8=F29","label":"F8=F29","type":"Same context","x":520,"y":245},
        {"id":"F21","label":"F21\n(kollaps)","type":"Deposit","x":440,"y":350,"note":"Kollapslag"},
        {"id":"F14","label":"F14\n(bygning)","type":"Structural","x":600,"y":350,"group":"Bygning F14"},
        {"id":"F22","label":"F22\n(stenrække)","type":"Structural","x":780,"y":350,"group":"F22 stenrække"},
        {"id":"Unexcavated","label":"Unexcavated","type":"Natural","x":500,"y":540,"w":190}
    ],
    "edges": [["T","F1"],["F1","F2"],["F2","F8=F29"],["F8=F29","F21"],["F21","F14"],["F21","F22"],["F14","Unexcavated"],["F22","Unexcavated"]],
    "groups": [{"name":"Bygning F14","x":390,"y":305,"w":335,"h":135},{"name":"F22 stenrække","x":750,"y":305,"w":215,"h":135}],
    "phases": [{"name":"Fase 2","y":300},{"name":"Fase 1","y":480}]
}

class HarrisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1440x930")
        self.nodes, self.edges, self.groups, self.phases = {}, [], [], []
        self.selected = None
        self.selected_group = None
        self.drag = (0, 0)
        self.resize_group = False
        self.move_group = False
        self.filename = None
        self.show_phases = tk.BooleanVar(value=True)
        self.show_groups = tk.BooleanVar(value=True)
        self._ui()
        self.load_data(SAMPLE)

    def _ui(self):
        top = tk.Frame(self); top.pack(fill=tk.X)
        buttons = [
            ("Ny", self.new_file), ("Åbn JSON", self.open_json), ("Gem", self.save_json), ("Gem som", self.save_json_as),
            ("Import CSV", self.import_csv), ("Import relationstekst", self.import_rel_text), ("Import HMCX", self.import_hmcx),
            ("Tilføj boks", self.add_node), ("Tilføj relation", self.add_edge), ("Tilføj gruppe", self.add_group), ("Tilføj fase", self.add_phase),
            ("Slet valgt", self.delete_selected), ("Auto-layout BAR/Harris", self.auto_layout),
            ("Auto-fit grupper", self.auto_fit_groups), ("Kontroller matrix", self.validate_show),
            ("Rapport", self.save_report), ("Eksport SVG", self.export_svg), ("Eksport PDF", self.export_pdf)
        ]
        for t,c in buttons:
            tk.Button(top, text=t, command=c).pack(side=tk.LEFT, padx=1, pady=2)
        tk.Checkbutton(top, text="Faser", variable=self.show_phases, command=self.draw).pack(side=tk.LEFT)
        tk.Checkbutton(top, text="Grupper", variable=self.show_groups, command=self.draw).pack(side=tk.LEFT)

        tk.Label(self, text="BAR/Harris auto-layout: kun kendte relationer kædes; usikre/ukoblede lag deles i parallelle grene; Natural nederst; topsoil øverst. Grupper kan flyttes og skaleres med blå hjørne.", anchor="w").pack(fill=tk.X, padx=6)

        self.canvas = tk.Canvas(self, bg="white", scrollregion=(0,0,2800,2200))
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview); y.pack(side=tk.RIGHT, fill=tk.Y)
        x = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview); x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Double-Button-1>", self.double)

    def load_data(self, data):
        self.nodes = {n["id"]: dict(n) for n in data.get("nodes", [])}
        self.edges = []
        for a,b in data.get("edges", []):
            if a != b and (a,b) not in self.edges:
                self.edges.append((a,b))
        self.groups = list(data.get("groups", []))
        self.phases = list(data.get("phases", []))
        self.draw()

    def data(self):
        return {"nodes": list(self.nodes.values()), "edges": [list(e) for e in self.edges], "groups": self.groups, "phases": self.phases}

    def draw(self):
        self.canvas.delete("all")
        if self.show_phases.get():
            for p in self.phases:
                y = p["y"]
                self.canvas.create_line(10, y, 2700, y, dash=(5,5), fill="#777")
                self.canvas.create_text(20, y-8, text=p.get("name","Fase"), anchor="sw", font=("Arial",12,"bold"), fill="#555")
        if self.show_groups.get():
            for i,g in enumerate(self.groups):
                outline = "red" if i == self.selected_group else "#4B7DBA"
                self.canvas.create_rectangle(g["x"], g["y"], g["x"]+g["w"], g["y"]+g["h"], outline=outline, dash=(6,4), width=2, tags=("group", str(i)))
                self.canvas.create_text(g["x"]+8, g["y"]+16, text=g.get("name",""), anchor="w", fill="#245A9A", font=("Arial",10,"bold"), tags=("group", str(i)))
                self.canvas.create_rectangle(g["x"]+g["w"]-9, g["y"]+g["h"]-9, g["x"]+g["w"]+2, g["y"]+g["h"]+2, fill="#4B7DBA", outline="", tags=("gresize", str(i)))
        for a,b in self.edges:
            if a in self.nodes and b in self.nodes:
                self.draw_edge(self.nodes[a], self.nodes[b])
        for n in self.nodes.values():
            self.draw_node(n)
        self.legend()

    def draw_edge(self, a, b):
        aw, ah = a.get("w",BOX_W), a.get("h",BOX_H)
        bw, bh = b.get("w",BOX_W), b.get("h",BOX_H)
        x1, y1 = a["x"]+aw/2, a["y"]+ah
        x2, y2 = b["x"]+bw/2, b["y"]
        mid = (y1+y2)/2
        self.canvas.create_line(x1,y1,x1,mid,x2,mid,x2,y2,width=2,fill="black")

    def draw_node(self,n):
        x,y,w,h = n["x"], n["y"], n.get("w",BOX_W), n.get("h",BOX_H)
        col = TYPE_COLORS.get(n.get("type","Unknown"), TYPE_COLORS["Unknown"])
        self.canvas.create_rectangle(x,y,x+w,y+h,fill=col,outline=("red" if n["id"]==self.selected else "black"),width=2,tags=("node",n["id"]))
        self.canvas.create_text(x+w/2,y+h/2,text=n.get("label",n["id"]),font=("Arial",10,"bold"),tags=("node",n["id"]))
        if n.get("note"):
            self.canvas.create_text(x+w+6,y+h/2,text="*",anchor="w",font=("Arial",12,"bold"),fill="#555")

    def legend(self):
        x,y=25,25
        self.canvas.create_rectangle(x-10,y-10,x+245,y+258,fill="white",outline="#ccc")
        self.canvas.create_text(x,y,text="Feature Type",anchor="nw",font=("Arial",12,"bold"))
        for i,(k,c) in enumerate(TYPE_COLORS.items()):
            yy=y+28+i*24
            self.canvas.create_rectangle(x,yy,x+24,yy+16,fill=c,outline="black")
            self.canvas.create_text(x+32,yy+8,text=k,anchor="w",font=("Arial",10))
        self.canvas.create_text(x,y+205,text="* note/kommentar",anchor="w",font=("Arial",9),fill="#555")
        self.canvas.create_text(x,y+222,text="Blå firkant = justér gruppe",anchor="w",font=("Arial",9),fill="#555")
        self.canvas.create_text(x,y+239,text="Relation: yngre → ældre",anchor="w",font=("Arial",9),fill="#555")

    def object_hit(self,e):
        x,y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        for item in reversed(self.canvas.find_overlapping(x,y,x,y)):
            tags = self.canvas.gettags(item)
            if "node" in tags:
                for t in tags:
                    if t in self.nodes: return ("node",t)
            if "gresize" in tags:
                for t in tags:
                    if t.isdigit(): return ("gresize",int(t))
            if "group" in tags:
                for t in tags:
                    if t.isdigit(): return ("group",int(t))
        return (None,None)

    def press(self,e):
        kind,val = self.object_hit(e)
        self.selected = None; self.selected_group = None; self.resize_group = False; self.move_group = False
        x,y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        if kind == "node":
            self.selected = val; n = self.nodes[val]; self.drag = (x-n["x"], y-n["y"])
        elif kind == "gresize":
            self.selected_group = val; self.resize_group = True
            g = self.groups[val]; self.drag = (x-(g["x"]+g["w"]), y-(g["y"]+g["h"]))
        elif kind == "group":
            self.selected_group = val; self.move_group = True
            g = self.groups[val]; self.drag = (x-g["x"], y-g["y"])
        self.draw()

    def motion(self,e):
        x,y = self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)
        dx,dy = self.drag
        if self.selected:
            self.nodes[self.selected]["x"] = round(x-dx)
            self.nodes[self.selected]["y"] = round(y-dy)
        elif self.selected_group is not None:
            g = self.groups[self.selected_group]
            if self.resize_group:
                g["w"] = max(60, round(x-dx-g["x"]))
                g["h"] = max(40, round(y-dy-g["y"]))
            elif self.move_group:
                g["x"] = round(x-dx); g["y"] = round(y-dy)
        self.draw()

    def release(self,e):
        self.resize_group = False; self.move_group = False

    def double(self,e):
        kind,val = self.object_hit(e)
        if kind == "node":
            n = self.nodes[val]
            label = simpledialog.askstring("Label","Label:",initialvalue=n.get("label",val),parent=self)
            if label is None: return
            typ = simpledialog.askstring("Feature Type","Deposit / Cut / Fill / Structural / Natural / Same context / Unknown:",initialvalue=n.get("type","Unknown"),parent=self)
            if typ is None: return
            note = simpledialog.askstring("Note","Note/kommentar:",initialvalue=n.get("note",""),parent=self)
            group = simpledialog.askstring("Gruppe","Gruppenavn, fx Bygning F14:",initialvalue=n.get("group",""),parent=self)
            n["label"], n["type"], n["note"], n["group"] = label, typ, note or "", group or ""
        elif kind == "group":
            g = self.groups[val]
            name = simpledialog.askstring("Gruppe","Navn:",initialvalue=g.get("name",""),parent=self)
            if name is not None: g["name"] = name
        self.draw()

    def new_file(self): self.filename=None; self.load_data({"nodes":[],"edges":[],"groups":[],"phases":[]})
    def open_json(self):
        p = filedialog.askopenfilename(filetypes=[("Harris JSON","*.json"),("All files","*.*")])
        if p:
            self.filename=p; self.load_data(json.load(open(p,encoding="utf-8")))
    def save_json(self):
        if not self.filename: return self.save_json_as()
        json.dump(self.data(), open(self.filename,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        messagebox.showinfo("Gemt", self.filename)
    def save_json_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Harris JSON","*.json")])
        if p: self.filename=p; self.save_json()

    def add_node(self):
        nid = simpledialog.askstring("Ny boks","Context ID:",parent=self)
        if not nid: return
        if nid in self.nodes: messagebox.showerror("Fejl","Context findes allerede."); return
        typ = simpledialog.askstring("Feature Type","Type:",initialvalue="Deposit",parent=self) or "Deposit"
        self.nodes[nid] = {"id":nid,"label":nid,"type":typ,"x":300,"y":300}
        self.draw()

    def ensure_node(self,nid):
        if nid not in self.nodes:
            typ = "Unknown"
            if nid.lower() in ("natural","unexcavated"): typ = "Natural"
            self.nodes[nid] = {"id":nid,"label":nid,"type":typ,"x":300,"y":300}

    def add_edge_checked(self,a,b):
        if a == b: return False, "Samme context i relation."
        self.ensure_node(a); self.ensure_node(b)
        if (a,b) in self.edges: return False, "Relation findes allerede."
        if self.would_cycle(a,b): return False, "Relationen vil skabe cirkel."
        self.edges.append((a,b)); return True, "OK"

    def add_edge(self):
        a = simpledialog.askstring("Relation","Yngre/øverst:",parent=self)
        b = simpledialog.askstring("Relation","Ældre/nederst:",parent=self)
        if not a or not b: return
        ok,msg = self.add_edge_checked(a.strip(), b.strip())
        if not ok: messagebox.showerror("Harris-regel",msg)
        self.draw()

    def add_group(self):
        name = simpledialog.askstring("Gruppe","Navn:",parent=self)
        if name:
            self.groups.append({"name":name,"x":250,"y":250,"w":320,"h":170})
            self.draw()

    def add_phase(self):
        name = simpledialog.askstring("Fase","Navn:",initialvalue="Fase",parent=self)
        if not name: return
        y = simpledialog.askinteger("Fase","Y-position:",initialvalue=400,parent=self)
        if y is not None:
            self.phases.append({"name":name,"y":y})
            self.draw()

    def delete_selected(self):
        if self.selected:
            nid = self.selected
            del self.nodes[nid]
            self.edges = [e for e in self.edges if nid not in e]
            self.selected = None
        elif self.selected_group is not None:
            del self.groups[self.selected_group]
            self.selected_group = None
        self.draw()

    def graph(self):
        g=defaultdict(list)
        for a,b in self.edges: g[a].append(b)
        return g

    def would_cycle(self,a,b):
        g = self.graph(); g[a].append(b)
        stack=[b]; seen=set()
        while stack:
            n=stack.pop()
            if n == a: return True
            if n in seen: continue
            seen.add(n); stack += g.get(n,[])
        return False

    def transitive_reduction_edges(self):
        # Keep only direct contacts for clearer Harris matrix.
        g = self.graph()
        reduced = []
        for a,b in self.edges:
            # is b reachable from a through another immediate child?
            found = False
            for mid in g.get(a,[]):
                if mid == b: continue
                stack=[mid]; seen=set()
                while stack:
                    x=stack.pop()
                    if x == b:
                        found=True; break
                    if x in seen: continue
                    seen.add(x); stack += g.get(x,[])
                if found: break
            if not found: reduced.append((a,b))
        return reduced

    def auto_layout(self):
        # BAR/Edward Harris inspired:
        # 1. Use only observed known relations.
        # 2. Contexts connected by relations form vertical narrative chains.
        # 3. Similar but unconnected layers remain separate parallel branches.
        # 4. Same-context nodes (=) stay as one horizon.
        # 5. Natural/unexcavated is forced lowest; topsoil/T forced highest.
        self.edges = self.transitive_reduction_edges()

        children = defaultdict(list); parents = defaultdict(list)
        for a,b in self.edges:
            children[a].append(b); parents[b].append(a)

        indeg = {n:0 for n in self.nodes}
        for a,b in self.edges:
            indeg[b] = indeg.get(b,0)+1
            indeg.setdefault(a,0)

        # longest path from top = stratigraphic level
        q = deque([n for n,d in indeg.items() if d==0])
        level = {n:0 for n in self.nodes}
        while q:
            n = q.popleft()
            for m in children.get(n,[]):
                level[m] = max(level.get(m,0), level[n]+1)
                indeg[m] -= 1
                if indeg[m] == 0: q.append(m)

        maxlev = max(level.values()) if level else 0
        for nid,n in self.nodes.items():
            low = nid.lower()
            if low in ("natural","unexcavated") or n.get("type") == "Natural":
                level[nid] = maxlev + 1
            if low in ("t","topsoil") or "topsoil" in n.get("label","").lower():
                level[nid] = 0

        buckets = defaultdict(list)
        for nid in self.nodes:
            buckets[level.get(nid,0)].append(nid)

        def component_key(nid):
            n = self.nodes[nid]
            # keep analytical groups together, but do not force stratigraphic equality
            return (n.get("group",""), self.primary_number(nid), nid)

        for lev in sorted(buckets):
            arr = sorted(buckets[lev], key=component_key)
            width = max(1, len(arr))
            start_x = 300
            for i,nid in enumerate(arr):
                self.nodes[nid]["x"] = start_x + i*150
                self.nodes[nid]["y"] = 80 + lev*95

        self.auto_fit_groups()
        self.make_phase_suggestions()
        self.draw()

    def primary_number(self, s):
        m = re.search(r'\d+', s)
        return int(m.group()) if m else 999999

    def make_phase_suggestions(self):
        if not self.nodes: return
        ys = [n["y"] for n in self.nodes.values()]
        miny,maxy = min(ys), max(ys)
        if maxy-miny > 250:
            self.phases = [
                {"name":"Øvre / sen fase", "y": miny + (maxy-miny)*0.33},
                {"name":"Mellem fase", "y": miny + (maxy-miny)*0.66},
            ]

    def auto_fit_groups(self):
        for g in self.groups:
            name = g.get("name","")
            members = []
            for n in self.nodes.values():
                if n.get("group") == name or (name and name.lower() in n.get("note","").lower()):
                    members.append(n)
            if not members:
                for n in self.nodes.values():
                    w,h = n.get("w",BOX_W), n.get("h",BOX_H)
                    if g["x"] <= n["x"]+w/2 <= g["x"]+g["w"] and g["y"] <= n["y"]+h/2 <= g["y"]+g["h"]:
                        members.append(n)
            if members:
                minx = min(n["x"] for n in members)-35
                miny = min(n["y"] for n in members)-45
                maxx = max(n["x"]+n.get("w",BOX_W) for n in members)+35
                maxy = max(n["y"]+n.get("h",BOX_H) for n in members)+35
                g["x"],g["y"],g["w"],g["h"] = minx,miny,maxx-minx,maxy-miny
        self.draw()

    def validate(self):
        problems=[]; warnings=[]
        for a,b in self.edges:
            if a not in self.nodes: problems.append(f"Relation fra ukendt context: {a}")
            if b not in self.nodes: problems.append(f"Relation til ukendt context: {b}")
        temp,perm=set(),set(); g=self.graph()
        def visit(n,path):
            if n in temp:
                problems.append("Cirkulær relation: "+" → ".join(path+[n])); return
            if n in perm: return
            temp.add(n)
            for m in g.get(n,[]): visit(m,path+[n])
            temp.remove(n); perm.add(n)
        for n in self.nodes: visit(n,[])
        for nid,n in self.nodes.items():
            typ=n.get("type","Unknown")
            if typ=="Fill":
                related=[a for a,b in self.edges if b==nid]+[b for a,b in self.edges if a==nid]
                if not any(self.nodes.get(r,{}).get("type")=="Cut" for r in related):
                    warnings.append(f"{nid}: Fill uden direkte relation til Cut.")
            if typ=="Cut":
                below=[b for a,b in self.edges if a==nid]
                if any(self.nodes.get(b,{}).get("type")=="Fill" for b in below):
                    warnings.append(f"{nid}: Cut ligger over Fill; kontroller om relationen er vendt forkert.")
            if typ=="Natural" and any(a==nid for a,b in self.edges):
                warnings.append(f"{nid}: Natural ligger over andre contexts.")
            if typ=="Unknown":
                warnings.append(f"{nid}: Feature Type er Unknown.")
        for a,b in self.edges:
            if a in self.nodes and b in self.nodes and self.nodes[a]["y"] > self.nodes[b]["y"]:
                warnings.append(f"{a} er yngre end {b}, men ligger grafisk lavere.")
        return problems,warnings

    def validate_show(self):
        p,w=self.validate(); msg=[]
        if not p and not w: msg=["✓ Ingen problemer fundet."]
        if p: msg.append("FEJL:"); msg += ["  • "+x for x in p]
        if w: msg.append("ADVARSLER:"); msg += ["  • "+x for x in w]
        (messagebox.showerror if p else messagebox.showwarning if w else messagebox.showinfo)("Harris-kontrol","\n".join(msg))

    def save_report(self):
        p,w=self.validate()
        out=filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Text","*.txt")])
        if not out: return
        lines=["Harris Matrix Validation Report","="*32,"",f"Kontekster: {len(self.nodes)}",f"Relationer: {len(self.edges)}",""]
        lines += ["BAR/Harris auto-layout principles:",
                  "- Link only known/observed relations.",
                  "- Keep unconnected similar layers as separate branches.",
                  "- Equals sign means direct same-context/horizon.",
                  "- Natural/unexcavated kept at the bottom.",
                  ""]
        lines.append("FEJL:"); lines += ["- "+x for x in p] if p else ["Ingen"]
        lines.append(""); lines.append("ADVARSLER:"); lines += ["- "+x for x in w] if w else ["Ingen"]
        Path(out).write_text("\n".join(lines),encoding="utf-8")
        messagebox.showinfo("Rapport gemt",out)

    def import_csv(self):
        p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not p: return
        with open(p,encoding="utf-8-sig") as f: rows=list(csv.DictReader(f))
        for i,r in enumerate(rows):
            nid=r.get("id") or r.get("Context") or r.get("context")
            if not nid: continue
            self.nodes[nid]={"id":nid,"label":r.get("label",nid),"type":r.get("type",r.get("Feature Type","Unknown")),"x":300+(i%8)*150,"y":100+(i//8)*95}
        self.draw()

    def import_rel_text(self):
        p=filedialog.askopenfilename(filetypes=[("Text","*.txt"),("All files","*.*")])
        if not p: return
        text=Path(p).read_text(encoding="utf-8",errors="ignore")
        added=[]; skipped=[]
        for line in text.splitlines():
            for pat,kind in RELATION_PATTERNS:
                for m in re.finditer(pat,line,flags=re.IGNORECASE):
                    a,b=m.group(1),m.group(2)
                    if kind=="below":
                        a,b=b,a
                    elif kind=="fills":
                        self.ensure_node(a); self.ensure_node(b)
                        if self.nodes[a].get("type")=="Unknown": self.nodes[a]["type"]="Fill"
                        if self.nodes[b].get("type")=="Unknown": self.nodes[b]["type"]="Cut"
                    elif kind=="cuts":
                        self.ensure_node(a)
                        if self.nodes[a].get("type")=="Unknown": self.nodes[a]["type"]="Cut"
                    elif kind=="same":
                        merged=f"{a}={b}"
                        if merged not in self.nodes:
                            self.nodes[merged]={"id":merged,"label":merged,"type":"Same context","x":300,"y":300}
                        added.append(f"Same context: {merged}")
                        continue
                    ok,msg=self.add_edge_checked(a,b)
                    (added if ok else skipped).append(f"{a} → {b}" if ok else f"{a} → {b}: {msg}")
        self.auto_layout()
        messagebox.showinfo("Import relationstekst",f"Tilføjet: {len(added)}\nSprunget over: {len(skipped)}\n\n"+"\n".join(added[:10]+skipped[:10]))

    def import_hmcx(self):
        p=filedialog.askopenfilename(filetypes=[("HMCX","*.hmcx"),("XML","*.xml"),("All files","*.*")])
        if not p: return
        text=Path(p).read_text(encoding="utf-8",errors="ignore")
        imported_nodes=0; imported_edges=0
        # try XML parsing first
        try:
            root=ET.fromstring(text)
            for el in root.iter():
                attrs={k.lower():v for k,v in el.attrib.items()}
                tag=el.tag.lower()
                nid=attrs.get("id") or attrs.get("context") or attrs.get("name") or attrs.get("label")
                if nid and re.match(r'^(F?\d+[A-Za-z]?|T|Natural|Unexcavated)$', nid):
                    if nid not in self.nodes:
                        self.nodes[nid]={"id":nid,"label":attrs.get("label",nid),"type":attrs.get("type","Unknown"),"x":300,"y":300}
                        imported_nodes+=1
                source=attrs.get("source") or attrs.get("from") or attrs.get("above") or attrs.get("younger")
                target=attrs.get("target") or attrs.get("to") or attrs.get("below") or attrs.get("older")
                if source and target:
                    ok,msg=self.add_edge_checked(source,target)
                    if ok: imported_edges+=1
        except Exception:
            pass
        # fallback regex for relations
        for a,b in re.findall(r'(F\d+[A-Za-z]?)[^\n\r<>]{0,40}(?:above|over|younger|source|from)[^\n\r<>]{0,40}(F\d+[A-Za-z]?)', text, re.I):
            ok,msg=self.add_edge_checked(a,b)
            if ok: imported_edges+=1
        for a,b in re.findall(r'(F\d+[A-Za-z]?)[^\n\r<>]{0,40}(?:below|under|older|target|to)[^\n\r<>]{0,40}(F\d+[A-Za-z]?)', text, re.I):
            ok,msg=self.add_edge_checked(b,a)  # "a below b" means b -> a
            if ok: imported_edges+=1
        self.auto_layout()
        messagebox.showinfo("Import HMCX", f"Importeret ca. {imported_nodes} bokse og {imported_edges} relationer.\nHMCX-formater kan variere; kontroller matrixen bagefter.")

    def export_svg(self):
        p=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG","*.svg")])
        if not p: return
        Path(p).write_text(self.to_svg(),encoding="utf-8")
        messagebox.showinfo("Eksporteret",p)

    def export_pdf(self):
        p=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")])
        if not p: return
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A3, landscape
            from reportlab.lib.colors import HexColor, black, white
            c=canvas.Canvas(p,pagesize=landscape(A3))
            page_w,page_h=landscape(A3)
            # calculate bounds
            xs=[]; ys=[]
            for n in self.nodes.values():
                xs += [n["x"], n["x"]+n.get("w",BOX_W)]
                ys += [n["y"], n["y"]+n.get("h",BOX_H)]
            for g in self.groups:
                xs += [g["x"], g["x"]+g["w"]]; ys += [g["y"], g["y"]+g["h"]]
            if not xs: xs=[0,100]; ys=[0,100]
            minx,miny,maxx,maxy=min(xs)-80,min(ys)-80,max(xs)+80,max(ys)+80
            scale=min((page_w-60)/(maxx-minx),(page_h-60)/(maxy-miny))
            def tx(x): return 30+(x-minx)*scale
            def ty(y): return page_h-(30+(y-miny)*scale)
            c.setTitle("Harris Matrix")
            # groups
            c.setDash(6,4)
            c.setStrokeColor(HexColor("#4B7DBA"))
            for g in self.groups:
                c.rect(tx(g["x"]), ty(g["y"]+g["h"]), g["w"]*scale, g["h"]*scale, fill=0, stroke=1)
                c.drawString(tx(g["x"]+8), ty(g["y"]+16), g.get("name",""))
            c.setDash()
            c.setStrokeColor(black)
            # edges
            for a,b in self.edges:
                if a in self.nodes and b in self.nodes:
                    na,nb=self.nodes[a],self.nodes[b]
                    aw,ah=na.get("w",BOX_W),na.get("h",BOX_H); bw,bh=nb.get("w",BOX_W),nb.get("h",BOX_H)
                    x1,y1=na["x"]+aw/2,na["y"]+ah; x2,y2=nb["x"]+bw/2,nb["y"]; mid=(y1+y2)/2
                    pts=[(x1,y1),(x1,mid),(x2,mid),(x2,y2)]
                    for (xA,yA),(xB,yB) in zip(pts,pts[1:]):
                        c.line(tx(xA),ty(yA),tx(xB),ty(yB))
            # nodes
            for n in self.nodes.values():
                x,y,w,h=n["x"],n["y"],n.get("w",BOX_W),n.get("h",BOX_H)
                c.setFillColor(HexColor(TYPE_COLORS.get(n.get("type","Unknown"),"#EFEFEF")))
                c.rect(tx(x),ty(y+h),w*scale,h*scale,fill=1,stroke=1)
                c.setFillColor(black)
                label=n.get("label",n["id"]).replace("\n"," ")
                c.drawCentredString(tx(x+w/2),ty(y+h/2)+3,label[:32])
            c.save()
            messagebox.showinfo("PDF eksport",p)
        except Exception as e:
            messagebox.showerror("PDF fejl",f"Kunne ikke eksportere PDF:\n{e}\n\nInstaller/medbyg reportlab.")

    def to_svg(self):
        parts=['<svg xmlns="http://www.w3.org/2000/svg" width="2800" height="2200" viewBox="0 0 2800 2200"><rect width="100%" height="100%" fill="white"/>']
        if self.show_phases.get():
            for ph in self.phases:
                y=ph["y"]; parts.append(f'<line x1="10" y1="{y}" x2="2700" y2="{y}" stroke="#777" stroke-dasharray="5 5"/>')
                parts.append(f'<text x="20" y="{y-8}" font-family="Arial" font-size="16" font-weight="bold" fill="#555">{ph.get("name","Fase")}</text>')
        if self.show_groups.get():
            for gr in self.groups:
                parts.append(f'<rect x="{gr["x"]}" y="{gr["y"]}" width="{gr["w"]}" height="{gr["h"]}" fill="none" stroke="#4B7DBA" stroke-width="2" stroke-dasharray="6 4"/>')
                parts.append(f'<text x="{gr["x"]+8}" y="{gr["y"]+18}" font-family="Arial" font-size="14" font-weight="bold" fill="#245A9A">{gr.get("name","")}</text>')
        for a,b in self.edges:
            if a in self.nodes and b in self.nodes:
                na,nb=self.nodes[a],self.nodes[b]; aw,ah=na.get("w",BOX_W),na.get("h",BOX_H); bw,bh=nb.get("w",BOX_W),nb.get("h",BOX_H)
                x1,y1=na["x"]+aw/2,na["y"]+ah; x2,y2=nb["x"]+bw/2,nb["y"]; mid=(y1+y2)/2
                parts.append(f'<polyline points="{x1},{y1} {x1},{mid} {x2},{mid} {x2},{y2}" fill="none" stroke="black" stroke-width="2"/>')
        for n in self.nodes.values():
            x,y,w,h=n["x"],n["y"],n.get("w",BOX_W),n.get("h",BOX_H); c=TYPE_COLORS.get(n.get("type","Unknown"),TYPE_COLORS["Unknown"])
            lab=n.get("label",n["id"]).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}" stroke="black" stroke-width="1.5"/>')
            lines=lab.split("\\n")
            for j,line in enumerate(lines):
                yy=y+h/2+(j-(len(lines)-1)/2)*13+4
                parts.append(f'<text x="{x+w/2}" y="{yy}" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold">{line}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

if __name__=="__main__":
    HarrisApp().mainloop()
