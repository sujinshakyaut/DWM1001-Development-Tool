import csv
import datetime
import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from concurrent.futures import ThreadPoolExecutor

import requests

API = "http://127.0.0.1:8000"


class DWM1001App:
    def __init__(self, root: tk.Tk):
        self._root = root
        self._root.title("DWM1001-DEV Configuration Tool")
        self._root.resizable(False, False)
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._streaming = False

        self._build_ui()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = tk.Frame(self._root, bg="#2b2b2b", pady=6)
        top.pack(fill="x")
        tk.Label(
            top, text="DWM1001-DEV Configuration Tool",
            bg="#2b2b2b", fg="white", font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=12)
        self._status_var = tk.StringVar(value="Disconnected")
        self._status_label = tk.Label(
            top, textvariable=self._status_var,
            bg="#2b2b2b", fg="#ff6b6b", font=("Segoe UI", 10),
        )
        self._status_label.pack(side="right", padx=12)

        self._nb = ttk.Notebook(self._root)
        self._nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_tab_scan()
        self._build_tab_info()
        self._build_tab_configure()
        self._build_tab_location()

    def _build_tab_scan(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="Scan & Connect")

        btn_frame = tk.Frame(f)
        btn_frame.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_frame, text="Scan for Devices", command=self._do_scan).pack(side="left")
        ttk.Button(btn_frame, text="Connect to Selected", command=self._do_connect).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Disconnect", command=self._do_disconnect).pack(side="left")

        list_frame = tk.Frame(f)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self._device_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            height=14, font=("Consolas", 10), selectmode="single",
        )
        scrollbar.config(command=self._device_listbox.yview)
        self._device_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._device_addresses: list[str] = []

        self._scan_status = tk.StringVar(value="")
        tk.Label(f, textvariable=self._scan_status, anchor="w").pack(fill="x", pady=(4, 0))

    def _build_tab_info(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="Device Info")

        ttk.Button(f, text="Read Info", command=self._do_read_info).pack(anchor="w", pady=(0, 10))

        grid = ttk.LabelFrame(f, text="Device Details", padding=8)
        grid.pack(fill="x")

        fields = ["Label", "Role", "Initiator", "OpMode (hex)", "PAN ID"]
        self._info_vars = {}
        for i, name in enumerate(fields):
            ttk.Label(grid, text=f"{name}:", font=("Segoe UI", 9, "bold")).grid(
                row=i, column=0, sticky="w", pady=3, padx=(0, 12)
            )
            var = tk.StringVar(value="—")
            ttk.Label(grid, textvariable=var, font=("Consolas", 9)).grid(
                row=i, column=1, sticky="w"
            )
            self._info_vars[name] = var

    def _build_tab_configure(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="Configure")

        nf = ttk.LabelFrame(f, text="Network ID", padding=8)
        nf.pack(fill="x", pady=(0, 8))
        ttk.Label(nf, text="PAN ID (hex, e.g. 1A2B):").grid(row=0, column=0, sticky="w")
        self._pan_entry = ttk.Entry(nf, width=12)
        self._pan_entry.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Button(nf, text="Write PAN ID", command=self._do_write_net_id).grid(row=0, column=2, padx=4)

        of = ttk.LabelFrame(f, text="Operating Mode", padding=8)
        of.pack(fill="x", pady=(0, 8))

        ttk.Label(of, text="Role:").grid(row=0, column=0, sticky="w", pady=3)
        self._role_var = tk.StringVar(value="tag")
        self._role_combo = ttk.Combobox(of, textvariable=self._role_var, values=["tag", "anchor"],
                                        state="readonly", width=10)
        self._role_combo.grid(row=0, column=1, sticky="w", padx=6)
        self._role_combo.bind("<<ComboboxSelected>>", self._on_role_change)

        ttk.Label(of, text="UWB Mode:").grid(row=1, column=0, sticky="w", pady=3)
        self._uwb_var = tk.StringVar(value="active")
        ttk.Combobox(of, textvariable=self._uwb_var, values=["active", "passive", "off"],
                     state="readonly", width=10).grid(row=1, column=1, sticky="w", padx=6)

        self._initiator_var = tk.BooleanVar(value=False)
        self._initiator_check = ttk.Checkbutton(of, text="Initiator", variable=self._initiator_var,
                                                 state="disabled")
        self._initiator_check.grid(row=0, column=2, padx=12)

        self._loc_engine_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(of, text="Location Engine", variable=self._loc_engine_var).grid(
            row=1, column=2, padx=12
        )

        ttk.Button(of, text="Write OpMode", command=self._do_write_opmode).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        pf = ttk.LabelFrame(f, text="Anchor Position", padding=8)
        pf.pack(fill="x")

        labels = [("X (mm):", "_pos_x"), ("Y (mm):", "_pos_y"),
                  ("Z (mm):", "_pos_z"), ("Quality (0-100):", "_pos_q")]
        for i, (lbl, attr) in enumerate(labels):
            ttk.Label(pf, text=lbl).grid(row=i, column=0, sticky="w", pady=2)
            entry = ttk.Entry(pf, width=10)
            entry.grid(row=i, column=1, sticky="w", padx=6)
            setattr(self, attr, entry)

        ttk.Button(pf, text="Set Position", command=self._do_set_position).grid(
            row=len(labels), column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

    def _build_tab_location(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="Location Stream")

        self._pos_history: list[tuple[int, int]] = []
        self._csv_data: list[tuple] = []

        cf = ttk.LabelFrame(f, text="Controls", padding=8)
        cf.pack(fill="x", pady=(0, 8))
        ttk.Label(cf, text="Duration (s):").pack(side="left")
        self._duration_spin = ttk.Spinbox(cf, from_=5, to=120, width=5)
        self._duration_spin.set(30)
        self._duration_spin.pack(side="left", padx=6)
        self._start_btn = ttk.Button(cf, text="Start Streaming", command=self._do_start_location)
        self._start_btn.pack(side="left", padx=4)
        ttk.Button(cf, text="Stop Streaming", command=self._do_stop_location).pack(side="left", padx=4)
        ttk.Button(cf, text="Clear Trail", command=self._clear_trail).pack(side="left", padx=4)
        ttk.Button(cf, text="Save CSV", command=self._save_csv).pack(side="left")

        mf = ttk.LabelFrame(f, text="Live Position Map", padding=4)
        mf.pack(fill="x", pady=(0, 8))
        self._map_canvas = tk.Canvas(mf, width=460, height=220,
                                     bg="#1e1e1e", highlightthickness=0)
        self._map_canvas.pack()

        pf = ttk.LabelFrame(f, text="Current Position", padding=8)
        pf.pack(fill="x", pady=(0, 8))
        self._loc_vars = {}
        for i, key in enumerate(["X (mm)", "Y (mm)", "Z (mm)", "Quality"]):
            ttk.Label(pf, text=f"{key}:", font=("Segoe UI", 9, "bold")).grid(
                row=i // 2, column=(i % 2) * 2, sticky="w", padx=(0, 6), pady=3
            )
            var = tk.StringVar(value="—")
            ttk.Label(pf, textvariable=var, font=("Consolas", 9), width=12).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w"
            )
            self._loc_vars[key] = var

        af = ttk.LabelFrame(f, text="Anchor Distances", padding=8)
        af.pack(fill="both", expand=True)
        cols = ("Node ID", "Distance (mm)", "Quality")
        self._anchor_tree = ttk.Treeview(af, columns=cols, show="headings", height=5)
        for col in cols:
            self._anchor_tree.heading(col, text=col)
            self._anchor_tree.column(col, width=120, anchor="center")
        tree_scroll = ttk.Scrollbar(af, orient="vertical", command=self._anchor_tree.yview)
        self._anchor_tree.configure(yscrollcommand=tree_scroll.set)
        self._anchor_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

    def _submit(self, fn, *args, on_done):
        future = self._executor.submit(fn, *args)
        future.add_done_callback(lambda f: self._root.after(0, on_done, f))

    def _set_status(self, connected: bool, address: str = ""):
        if connected:
            self._status_var.set(f"Connected: {address}")
            self._status_label.config(fg="#69db7c")
        else:
            self._status_var.set("Disconnected")
            self._status_label.config(fg="#ff6b6b")

    def _start_status_poll(self):
        def poll():
            self._submit(
                lambda: requests.get(f"{API}/status", timeout=5),
                on_done=_on_status_result,
            )

        def _on_status_result(future):
            try:
                data = future.result().json()
                connected = data.get("connected", False)
                self._set_status(connected, data.get("address", ""))
                if connected:
                    self._root.after(3000, poll)
            except Exception:
                pass

        self._root.after(3000, poll)

    def _on_role_change(self, _event=None):
        if self._role_var.get() == "anchor":
            self._initiator_check.config(state="normal")
        else:
            self._initiator_var.set(False)
            self._initiator_check.config(state="disabled")

    def _do_scan(self):
        self._scan_status.set("Scanning…")
        self._device_listbox.delete(0, "end")

        def call():
            return requests.get(f"{API}/scan", timeout=15)

        def on_done(future):
            try:
                resp = future.result()
                if resp.status_code != 200:
                    self._scan_status.set(f"Scan failed: {resp.text}")
                    return
                data = resp.json()
                devices = data.get("devices", [])
                self._device_listbox.delete(0, "end")
                self._device_addresses.clear()
                for d in devices:
                    self._device_listbox.insert("end", f"{d['address']}    {d['name']}")
                    self._device_addresses.append(d["address"])
                self._scan_status.set(f"Found {len(devices)} device(s).")
            except Exception as e:
                self._scan_status.set(f"Scan failed: {e}")

        self._submit(call, on_done=on_done)

    def _do_connect(self):
        sel = self._device_listbox.curselection()
        if not sel:
            messagebox.showerror("No selection", "Select a device from the list first.")
            return
        idx = sel[0]
        if idx >= len(self._device_addresses):
            messagebox.showerror("Error", "Device list is stale — please scan again.")
            return
        address = self._device_addresses[idx]

        def call():
            return requests.post(f"{API}/connect", json={"address": address}, timeout=40)

        def on_done(future):
            try:
                resp = future.result()
                if resp.status_code == 200:
                    data = resp.json()
                    self._set_status(data["connected"], data["address"])
                    if data["connected"]:
                        self._start_status_poll()
                else:
                    messagebox.showerror("Connect failed", resp.json().get("detail", resp.text))
            except Exception as e:
                messagebox.showerror("Connect error", str(e))

        self._submit(call, on_done=on_done)

    def _do_disconnect(self):
        def call():
            return requests.post(f"{API}/disconnect", timeout=10)

        def on_done(future):
            try:
                future.result()
            except Exception:
                pass
            self._set_status(False)

        self._submit(call, on_done=on_done)

    def _do_read_info(self):
        def call():
            return requests.get(f"{API}/info", timeout=10)

        def on_done(future):
            try:
                resp = future.result()
                if resp.status_code == 200:
                    d = resp.json()
                    self._info_vars["Label"].set(d["label"])
                    self._info_vars["Role"].set(d["role"])
                    self._info_vars["Initiator"].set(d["initiator"])
                    self._info_vars["OpMode (hex)"].set(d["opmode_hex"])
                    self._info_vars["PAN ID"].set(f"{d['pan_id_hex']}  ({d['pan_id_int']})")
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    messagebox.showerror("Read failed", detail)
            except Exception as e:
                messagebox.showerror("Read error", str(e))

        self._submit(call, on_done=on_done)

    def _do_write_net_id(self):
        raw = self._pan_entry.get().strip()
        try:
            pan_id = int(raw, 16)
        except ValueError:
            messagebox.showerror("Invalid input", "PAN ID must be a hex value (e.g. 1A2B).")
            return

        def call():
            return requests.post(f"{API}/net-id", json={"pan_id": pan_id}, timeout=10)

        def on_done(future):
            try:
                resp = future.result()
                d = resp.json()
                if d.get("success"):
                    messagebox.showinfo("Success", d["message"])
                else:
                    messagebox.showerror("Failed", d.get("message", resp.text))
            except Exception as e:
                messagebox.showerror("Error", str(e))

        self._submit(call, on_done=on_done)

    def _do_write_opmode(self):
        payload = {
            "role": self._role_var.get(),
            "uwb_mode": self._uwb_var.get(),
            "initiator": self._initiator_var.get(),
            "location_engine": self._loc_engine_var.get(),
        }

        def call():
            return requests.post(f"{API}/opmode", json=payload, timeout=10)

        def on_done(future):
            try:
                resp = future.result()
                d = resp.json()
                if d.get("success"):
                    messagebox.showinfo("Success", d["message"])
                else:
                    messagebox.showerror("Failed", d.get("message", resp.text))
            except Exception as e:
                messagebox.showerror("Error", str(e))

        self._submit(call, on_done=on_done)

    def _do_set_position(self):
        try:
            x = int(self._pos_x.get())
            y = int(self._pos_y.get())
            z = int(self._pos_z.get())
            q = int(self._pos_q.get())
        except ValueError:
            messagebox.showerror("Invalid input", "X, Y, Z and Quality must all be integers.")
            return
        if not (0 <= q <= 100):
            messagebox.showerror("Invalid input", "Quality must be between 0 and 100.")
            return

        def call():
            return requests.post(
                f"{API}/anchor-position",
                json={"x": x, "y": y, "z": z, "quality": q},
                timeout=10,
            )

        def on_done(future):
            try:
                resp = future.result()
                d = resp.json()
                if d.get("success"):
                    messagebox.showinfo("Success", d["message"])
                else:
                    messagebox.showerror("Failed", d.get("message", resp.text))
            except Exception as e:
                messagebox.showerror("Error", str(e))

        self._submit(call, on_done=on_done)

    def _do_start_location(self):
        try:
            duration = int(self._duration_spin.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Duration must be an integer.")
            return

        self._clear_trail()
        self._csv_data.clear()

        def call():
            return requests.post(f"{API}/location/start", json={"duration": duration}, timeout=10)

        def on_done(future):
            try:
                resp = future.result()
                if resp.status_code == 200:
                    self._streaming = True
                    self._start_btn.config(state="disabled")
                    self._start_poll_loop()
                else:
                    messagebox.showerror("Failed", resp.json().get("detail", resp.text))
            except Exception as e:
                messagebox.showerror("Error", str(e))

        self._submit(call, on_done=on_done)

    def _do_stop_location(self):
        def call():
            return requests.post(f"{API}/location/stop", timeout=10)

        def on_done(future):
            try:
                future.result()
            except Exception:
                pass
            self._streaming = False
            self._start_btn.config(state="normal")

        self._submit(call, on_done=on_done)

    def _start_poll_loop(self):
        def poll():
            self._submit(
                lambda: requests.get(f"{API}/location/poll", timeout=5),
                on_done=self._on_poll_result,
            )

        self._poll_fn = poll
        poll()

    def _on_poll_result(self, future):
        try:
            resp = future.result()
            data = resp.json()
            self._update_location_widgets(data.get("frames", []))
            if data.get("streaming", False):
                self._root.after(500, self._poll_fn)
            else:
                self._streaming = False
                self._start_btn.config(state="normal")
        except Exception as e:
            self._streaming = False
            self._start_btn.config(state="normal")
            messagebox.showerror("Poll error", str(e))

    def _update_location_widgets(self, frames: list):
        for frame in frames:
            pos = frame.get("position")
            if pos:
                self._loc_vars["X (mm)"].set(str(pos["x"]))
                self._loc_vars["Y (mm)"].set(str(pos["y"]))
                self._loc_vars["Z (mm)"].set(str(pos["z"]))
                self._loc_vars["Quality"].set(str(pos["quality"]))
                self._pos_history.append((pos["x"], pos["y"]))
                if len(self._pos_history) > 100:
                    self._pos_history.pop(0)
                self._csv_data.append((
                    datetime.datetime.now().isoformat(timespec="milliseconds"),
                    pos["x"], pos["y"], pos["z"], pos["quality"],
                ))
                self._redraw_map(pos["quality"])

            anchors = frame.get("anchors", [])
            if anchors:
                for row in self._anchor_tree.get_children():
                    self._anchor_tree.delete(row)
                for a in anchors:
                    self._anchor_tree.insert(
                        "", "end",
                        values=(a["node_id_hex"], a["distance_mm"], a["quality"]),
                    )

    def _clear_trail(self):
        self._pos_history.clear()
        self._map_canvas.delete("all")

    def _save_csv(self):
        if not self._csv_data:
            messagebox.showinfo("No data", "No position data recorded yet. Start streaming first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"dwm1001_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            title="Save position data",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "x_mm", "y_mm", "z_mm", "quality"])
                writer.writerows(self._csv_data)
            messagebox.showinfo("Saved", f"Saved {len(self._csv_data)} rows to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    @staticmethod
    def _nice_grid_step(world_range: float) -> int:
        for step in [100, 200, 500, 1000, 2000, 5000, 10000, 20000]:
            if world_range / step <= 8:
                return step
        return 50000

    def _redraw_map(self, quality: int = 0):
        c = self._map_canvas
        c.delete("all")

        if not self._pos_history:
            return

        W, H = 460, 220
        PAD = 36

        xs = [p[0] for p in self._pos_history]
        ys = [p[1] for p in self._pos_history]
        x_min = min(0, min(xs))
        x_max = max(0, max(xs))
        y_min = min(0, min(ys))
        y_max = max(0, max(ys))

        x_range = max(x_max - x_min, 1000)
        y_range = max(y_max - y_min, 1000)

        xp, yp = x_range * 0.12, y_range * 0.12
        wx0, wx1 = x_min - xp, x_max + xp
        wy0, wy1 = y_min - yp, y_max + yp

        draw_w = W - PAD
        draw_h = H - PAD

        def cx(x): return PAD + (x - wx0) / (wx1 - wx0) * draw_w
        def cy(y): return H - PAD - (y - wy0) / (wy1 - wy0) * draw_h

        step = self._nice_grid_step(max(wx1 - wx0, wy1 - wy0))
        gx_start = math.floor(wx0 / step) * step
        gy_start = math.floor(wy0 / step) * step

        x = gx_start
        while x <= wx1:
            px = cx(x)
            if PAD <= px <= W:
                is_origin = (x == 0)
                color = "#555555" if is_origin else "#2e2e2e"
                width = 1 if is_origin else 1
                c.create_line(px, 0, px, H - PAD, fill=color, width=width)
                label = f"{int(x/1000)}m" if abs(x) >= 1000 else f"{int(x)}"
                c.create_text(px, H - PAD + 2, text=label,
                              fill="#888888", font=("Consolas", 7), anchor="n")
            x += step

        y = gy_start
        while y <= wy1:
            py = cy(y)
            if 0 <= py <= H - PAD:
                is_origin = (y == 0)
                color = "#555555" if is_origin else "#2e2e2e"
                c.create_line(PAD, py, W, py, fill=color, width=1)
                label = f"{int(y/1000)}m" if abs(y) >= 1000 else f"{int(y)}"
                c.create_text(PAD - 2, py, text=label,
                              fill="#888888", font=("Consolas", 7), anchor="e")
            y += step

        n = len(self._pos_history)
        for i, (tx, ty) in enumerate(self._pos_history[:-1]):
            px, py = cx(tx), cy(ty)
            brightness = int(80 + 120 * i / max(n - 1, 1))
            col = f"#{brightness:02x}{brightness:02x}{brightness:02x}"
            r = 2
            c.create_oval(px - r, py - r, px + r, py + r, fill=col, outline="")

        lx, ly = self._pos_history[-1]
        px, py = cx(lx), cy(ly)
        s = 7
        c.create_polygon(px, py - s, px + s, py, px, py + s, px - s, py,
                         fill="#ff4444", outline="#ff8888", width=1)

        overlay = f"X:{lx:,} mm  Y:{ly:,} mm  Q:{quality}"
        c.create_text(W - 4, 4, text=overlay, fill="#aaaaaa",
                      font=("Consolas", 8), anchor="ne")

    def _on_close(self):
        def stop_and_disconnect():
            try:
                requests.post(f"{API}/location/stop", timeout=5)
            except Exception:
                pass
            try:
                requests.post(f"{API}/disconnect", timeout=5)
            except Exception:
                pass

        def on_done(future):
            self._executor.shutdown(wait=False)
            self._root.destroy()

        self._submit(stop_and_disconnect, on_done=on_done)
