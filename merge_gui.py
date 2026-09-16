import os
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def process_merge(files, output_path, status_lbl, progress_bar, run_btn):
    try:
        total_vertex_count = 0
        all_comments = []

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="ascii") as f_pts, \
             tempfile.NamedTemporaryFile("w+", delete=False, encoding="ascii") as f_cams:
            
            temp_points = f_pts.name
            temp_cams = f_cams.name

        total_files = len(files)
        for idx, file_path in enumerate(files):
            status_lbl.config(text=f"Reading file {idx + 1} of {total_files}: {os.path.basename(file_path)}")
            progress_bar["value"] = (idx / total_files) * 50

            in_header = True
            with open(file_path, "r", encoding="ascii", errors="replace") as infile:
                for line in infile:
                    if in_header:
                        stripped = line.strip()
                        if stripped.startswith("comment"):
                            all_comments.append(stripped)
                        elif stripped == "end_header":
                            in_header = False
                        continue

                    stripped_line = line.strip()
                    if not stripped_line:
                        continue

                    if stripped_line.startswith("0 "):
                        f_pts.write(line)
                        total_vertex_count += 1
                    elif stripped_line.startswith("1 "):
                        f_cams.write(line)
                        total_vertex_count += 1

        f_pts.flush()
        f_cams.flush()

        status_lbl.config(text=f"Assembling output ({total_vertex_count:,} vertices)...")
        progress_bar["value"] = 75

        with open(output_path, "w", encoding="ascii", buffering=64 * 1024 * 1024) as outfile:
            # PLY ASCII Header
            outfile.write("ply\nformat ascii 1.0\n")
            outfile.write(f"element vertex {total_vertex_count}\n")
            outfile.write("property uint isCamera\n")
            outfile.write("property float x\nproperty float y\nproperty float z\n")
            outfile.write("property float nx\nproperty float ny\nproperty float nz\n")
            outfile.write("property uchar diffuse_red\nproperty uchar diffuse_green\nproperty uchar diffuse_blue\n")

            for comment in all_comments:
                outfile.write(f"{comment}\n")
            outfile.write("end_header\n")

            # Stream points (isCamera == 0)
            with open(temp_points, "r", encoding="ascii") as fp_in:
                shutil.copyfileobj(fp_in, outfile, length=16 * 1024 * 1024)

            # Stream cameras (isCamera == 1)
            with open(temp_cams, "r", encoding="ascii") as fc_in:
                shutil.copyfileobj(fc_in, outfile, length=16 * 1024 * 1024)

        if os.path.exists(temp_points):
            os.remove(temp_points)
        if os.path.exists(temp_cams):
            os.remove(temp_cams)

        progress_bar["value"] = 100
        status_lbl.config(text="Complete!")
        messagebox.showinfo(
            "Success",
            f"Merged successfully!\nTotal Vertices: {total_vertex_count:,}\nSaved to:\n{output_path}"
        )

    except Exception as e:
        messagebox.showerror("Error", str(e))
        status_lbl.config(text="Failed.")
    finally:
        run_btn.config(state="normal")


class PLYMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PLY Point Cloud & Camera Merger")
        self.root.geometry("540x440")
        self.root.resizable(False, False)

        self.files = []

        # File Listbox
        tk.Label(root, text="Selected Files (In Merge Sequence):", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(10, 2))
        frame_list = tk.Frame(root)
        frame_list.pack(fill="x", padx=15)

        self.listbox = tk.Listbox(frame_list, height=8, selectmode=tk.SINGLE)
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame_list, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        # Ordering Controls
        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=15, pady=5)
        tk.Button(btn_frame, text="Add Files...", command=self.add_files).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Move Up", command=self.move_up).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Move Down", command=self.move_down).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Clear", command=self.clear_files).pack(side="right", padx=2)

        # Destination selector
        out_frame = tk.Frame(root)
        out_frame.pack(fill="x", padx=15, pady=10)
        tk.Label(out_frame, text="Output File:").pack(anchor="w")
        self.out_entry = tk.Entry(out_frame)
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(out_frame, text="Browse...", command=self.browse_output).pack(side="right")

        # Progress bar
        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=15, pady=(10, 2))
        self.status_lbl = tk.Label(root, text="Ready", fg="gray")
        self.status_lbl.pack(anchor="w", padx=15)

        # Execute
        self.run_btn = tk.Button(
            root,
            text="Merge PLY Files",
            bg="#007acc",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            height=2,
            command=self.start_merge
        )
        self.run_btn.pack(fill="x", padx=15, pady=10)

    def add_files(self):
        chosen = filedialog.askopenfilenames(filetypes=[("PLY files", "*.ply"), ("All files", "*.*")])
        for f in chosen:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert(tk.END, os.path.basename(f))

    def move_up(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self.files[i], self.files[i - 1] = self.files[i - 1], self.files[i]
        val = self.listbox.get(i)
        self.listbox.delete(i)
        self.listbox.insert(i - 1, val)
        self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.files) - 1:
            return
        i = sel[0]
        self.files[i], self.files[i + 1] = self.files[i + 1], self.files[i]
        val = self.listbox.get(i)
        self.listbox.delete(i)
        self.listbox.insert(i + 1, val)
        self.listbox.selection_set(i + 1)

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, tk.END)

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".ply", filetypes=[("PLY files", "*.ply")])
        if path:
            self.out_entry.delete(0, tk.END)
            self.out_entry.insert(0, path)

    def start_merge(self):
        if not self.files:
            messagebox.showwarning("Warning", "Select at least one PLY file.")
            return
        out = self.out_entry.get().strip()
        if not out:
            messagebox.showwarning("Warning", "Specify an output file path.")
            return
        self.run_btn.config(state="disabled")
        threading.Thread(target=process_merge, args=(self.files, out, self.status_lbl, self.progress, self.run_btn), daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = PLYMergerApp(root)
    root.mainloop()
