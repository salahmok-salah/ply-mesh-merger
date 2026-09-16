import os
import re
import shutil
import tempfile
import threading
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def process_pipeline(parts, output_path, reindex_enabled, status_lbl, progress_bar, run_btn):
    temp_points = None
    temp_cams = None
    try:
        total_vertex_count = 0
        all_comments = []

        if os.path.isdir(output_path):
            output_path = os.path.join(output_path, "merged_output.ply")

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="ascii") as f_pts, \
             tempfile.NamedTemporaryFile("w+", delete=False, encoding="ascii") as f_cams:
            
            temp_points = f_pts.name
            temp_cams = f_cams.name

            current_max_id = -1
            global_step = 6
            total_parts = len(parts)

            for idx, part in enumerate(parts):
                ply_path = part["ply"]
                img_dir = part.get("img_folder")

                status_lbl.config(text=f"Reading Part {idx + 1}/{total_parts}: {os.path.basename(ply_path)}")
                progress_bar["value"] = (idx / total_parts) * 50

                part_comments = []
                in_header = True

                with open(ply_path, "r", encoding="ascii", errors="replace") as infile:
                    for line in infile:
                        if in_header:
                            s = line.strip()
                            if s.startswith("comment") and s != "comment user 0":
                                part_comments.append(s)
                            elif s == "end_header":
                                in_header = False
                            continue

                        s_line = line.strip()
                        if not s_line:
                            continue

                        if s_line.startswith("0 "):
                            f_pts.write(line)
                            total_vertex_count += 1
                        elif s_line.startswith("1 "):
                            f_cams.write(line)
                            total_vertex_count += 1

                # If NOT reindexing: keep comments as they are (or update to new folder if provided)
                if not reindex_enabled:
                    for c in part_comments:
                        if img_dir and os.path.isdir(img_dir):
                            fname = os.path.basename(c[7:].strip())
                            all_comments.append(f"comment {os.path.join(img_dir, fname)}")
                        else:
                            all_comments.append(c)
                    continue

                # If Reindexing: compute ID shifts and rename disk files
                id_list = []
                pattern = re.compile(r"^(\d+)(_(?:left|right)_.*\.jpg)$")
                for c in part_comments:
                    fname = os.path.basename(c[7:].strip())
                    m = pattern.match(fname)
                    if m:
                        id_list.append(int(m.group(1)))

                if id_list:
                    part_min_id = min(id_list)
                    part_max_id = max(id_list)
                    unique_sorted = sorted(list(set(id_list)))

                    if len(unique_sorted) > 1:
                        diffs = [b - a for a, b in zip(unique_sorted[:-1], unique_sorted[1:])]
                        global_step = min(diffs)

                    offset = 0
                    if current_max_id >= 0:
                        offset = (current_max_id + global_step) - part_min_id

                    # Rename disk files
                    if img_dir and os.path.exists(img_dir):
                        rename_pairs = []
                        for filename in os.listdir(img_dir):
                            m = pattern.match(filename)
                            if m:
                                old_id = int(m.group(1))
                                suffix = m.group(2)
                                new_id = old_id + offset
                                new_name = f"{new_id}{suffix}"
                                orig_full = os.path.join(img_dir, filename)
                                temp_full = os.path.join(img_dir, f"temp_{uuid.uuid4().hex}{suffix}")
                                final_full = os.path.join(img_dir, new_name)
                                rename_pairs.append((orig_full, temp_full, final_full))

                        for orig, temp, _ in rename_pairs:
                            os.rename(orig, temp)
                        for _, temp, final in rename_pairs:
                            os.rename(temp, final)

                    # Update comment paths
                    target_dir = img_dir if (img_dir and os.path.isdir(img_dir)) else None
                    for c in part_comments:
                        full_img_path = c[7:].strip()
                        dir_path = target_dir if target_dir else os.path.dirname(full_img_path)
                        base_name = os.path.basename(full_img_path)
                        m = pattern.match(base_name)
                        if m:
                            new_id = int(m.group(1)) + offset
                            updated_path = os.path.join(dir_path, f"{new_id}{m.group(2)}")
                            all_comments.append(f"comment {updated_path}")
                        else:
                            all_comments.append(c)

                    current_max_id = part_max_id + offset

            f_pts.flush()
            f_cams.flush()

        # Build output file
        status_lbl.config(text=f"Assembling merged PLY ({total_vertex_count:,} vertices)...")
        progress_bar["value"] = 80

        with open(output_path, "w", encoding="ascii", buffering=64 * 1024 * 1024) as outfile:
            outfile.write("ply\nformat ascii 1.0\n")
            outfile.write(f"element vertex {total_vertex_count}\n")
            outfile.write("property uint isCamera\n")
            outfile.write("property float x\nproperty float y\nproperty float z\n")
            outfile.write("property float nx\nproperty float ny\nproperty float nz\n")
            outfile.write("property uchar diffuse_red\nproperty uchar diffuse_green\nproperty uchar diffuse_blue\n")
            outfile.write("comment user 0\n")

            for comment in all_comments:
                outfile.write(f"{comment}\n")
            outfile.write("end_header\n")

            with open(temp_points, "r", encoding="ascii") as fp_in:
                shutil.copyfileobj(fp_in, outfile, length=16 * 1024 * 1024)
            with open(temp_cams, "r", encoding="ascii") as fc_in:
                shutil.copyfileobj(fc_in, outfile, length=16 * 1024 * 1024)

        progress_bar["value"] = 100
        status_lbl.config(text="Complete!")
        msg = "Merged & Renamed successfully!" if reindex_enabled else "Merged successfully (IDs unchanged)!"
        messagebox.showinfo("Success", f"{msg}\nVertices: {total_vertex_count:,}\nFile: {output_path}")

    except Exception as e:
        messagebox.showerror("Error", str(e))
        status_lbl.config(text="Failed.")
    finally:
        if temp_points and os.path.exists(temp_points):
            try: os.remove(temp_points)
            except Exception: pass
        if temp_cams and os.path.exists(temp_cams):
            try: os.remove(temp_cams)
            except Exception: pass
        run_btn.config(state="normal")


class PLYMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PLY Point Cloud & Camera Merger")
        self.root.geometry("620x520")

        self.parts = []
        self.reindex_var = tk.BooleanVar(value=False)

        tk.Label(root, text="Selected Files / Parts (In Sequence):", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(10, 2))
        
        frame_list = tk.Frame(root)
        frame_list.pack(fill="both", expand=True, padx=15)

        self.listbox = tk.Listbox(frame_list, height=8, selectmode=tk.SINGLE)
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame_list, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=15, pady=5)
        tk.Button(btn_frame, text="Add Files...", command=self.add_files).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Move Up", command=self.move_up).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Move Down", command=self.move_down).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Clear", command=self.clear_all).pack(side="right", padx=2)

        # Toggle Checkbox
        opt_frame = tk.Frame(root)
        opt_frame.pack(fill="x", padx=15, pady=5)
        self.chk = tk.Checkbutton(
            opt_frame, 
            text="Rename physical images and re-index image IDs consecutively", 
            variable=self.reindex_var,
            font=("Segoe UI", 9)
        )
        self.chk.pack(anchor="w")

        out_frame = tk.Frame(root)
        out_frame.pack(fill="x", padx=15, pady=5)
        tk.Label(out_frame, text="Destination Merged PLY:").pack(anchor="w")
        self.out_entry = tk.Entry(out_frame)
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(out_frame, text="Browse...", command=self.browse_output).pack(side="right")

        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=15, pady=(5, 2))
        self.status_lbl = tk.Label(root, text="Ready", fg="gray")
        self.status_lbl.pack(anchor="w", padx=15)

        self.run_btn = tk.Button(root, text="Execute Merge", bg="#007acc", fg="white", font=("Segoe UI", 10, "bold"), height=2, command=self.start_pipeline)
        self.run_btn.pack(fill="x", padx=15, pady=10)

    def add_files(self):
        if self.reindex_var.get():
            # In re-index mode, prompt for matching image folder
            ply = filedialog.askopenfilename(title="Select Part PLY File", filetypes=[("PLY files", "*.ply")])
            if not ply: return
            folder = filedialog.askdirectory(title="Select Matching Images Folder for this Part")
            if not folder: return
            self.parts.append({"ply": ply, "img_folder": folder})
            self.listbox.insert(tk.END, f"{os.path.basename(ply)}  -->  [{folder}]")
        else:
            # Simple merge: multi-select PLY files directly
            chosen = filedialog.askopenfilenames(filetypes=[("PLY files", "*.ply")])
            for f in chosen:
                if not any(p["ply"] == f for p in self.parts):
                    self.parts.append({"ply": f, "img_folder": None})
                    self.listbox.insert(tk.END, os.path.basename(f))

    def move_up(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.parts[i], self.parts[i - 1] = self.parts[i - 1], self.parts[i]
        val = self.listbox.get(i)
        self.listbox.delete(i)
        self.listbox.insert(i - 1, val)
        self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.parts) - 1: return
        i = sel[0]
        self.parts[i], self.parts[i + 1] = self.parts[i + 1], self.parts[i]
        val = self.listbox.get(i)
        self.listbox.delete(i)
        self.listbox.insert(i + 1, val)
        self.listbox.selection_set(i + 1)

    def clear_all(self):
        self.parts.clear()
        self.listbox.delete(0, tk.END)

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".ply", filetypes=[("PLY files", "*.ply")])
        if path:
            self.out_entry.delete(0, tk.END)
            self.out_entry.insert(0, path)

    def start_pipeline(self):
        if not self.parts:
            messagebox.showwarning("Warning", "Add at least one PLY file.")
            return
        out = self.out_entry.get().strip()
        if not out:
            messagebox.showwarning("Warning", "Specify an output file destination.")
            return
        self.run_btn.config(state="disabled")
        threading.Thread(
            target=process_pipeline, 
            args=(self.parts, out, self.reindex_var.get(), self.status_lbl, self.progress, self.run_btn), 
            daemon=True
        ).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = PLYMergerApp(root)
    root.mainloop()
