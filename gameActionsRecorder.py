import json
import time
import threading
import os
import shutil
import platform
import subprocess
from tkinter import Tk, Toplevel, Button, Label, Entry, Frame, messagebox, Canvas, Scrollbar, filedialog, ttk, Menu, simpledialog
from pynput import mouse, keyboard

if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

class ScratchActionRecorder:
    def __init__(self, root):
        self.root = root
        self.root.geometry("1050x110") 
        self.root.configure(bg="#f4f4f9")

        self.recorded_actions = []
        self.current_filepath = None  
        self.is_recording = False
        self.is_playing = False
        self.editor_visible = False
        
        self.selected_indices = []
        self.last_clicked_index = None
        self.last_action_time = 0.0

        # Workspace & Drag Variables
        self.workspace_dir = os.getcwd()
        self.file_map = {} 
        self.drag_data = {"items": [], "y": 0} 
        self.tree_drag_data = {"is_dragging": False, "filepath": None, "ghost": None} 

        self.mouse_listener = None
        self.keyboard_listener = None
        self.playback_listener = None
        
        self.mouse_ctrl = mouse.Controller()
        self.keyboard_ctrl = keyboard.Controller()
        
        self.mini_window = None

        self.colors = {
            "wait": "#FF9F1C",     
            "click": "#43AA8B",    
            "keypress": "#9B5DE5", 
            "key_down": "#9B5DE5", 
            "key_up": "#9B5DE5", 
            "scroll": "#F15BB5",
            "link": "#EF476F",
            "set_var": "#2C3E50",
            "if": "#8E44AD",
            "else": "#8E44AD",
            "while": "#8E44AD",
            "for": "#8E44AD",
            "end": "#95A5A6",
            "run_python": "#2980B9"
        }

        self._update_title()
        self._build_main_ui()
        self._update_middle_button_ui() 

    def _update_title(self):
        if self.current_filepath:
            name = os.path.basename(self.current_filepath)
            self.root.title(f"Macro Flow Manager - [{name}]")
        else:
            self.root.title("Macro Flow Manager - [Unsaved Flow]")

    def _auto_save(self):
        if self.current_filepath:
            try:
                with open(self.current_filepath, "w", encoding="utf-8") as f:
                    json.dump(self.recorded_actions, f, indent=2)
            except Exception as e:
                print(f"Auto-save failed: {e}")

    def _build_main_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        action_frame = Frame(self.root, bg="#f4f4f9")
        action_frame.pack(pady=20, fill="x", padx=15)

        action_frame.columnconfigure(0, weight=1, uniform="btn_group")
        action_frame.columnconfigure(1, weight=1, uniform="btn_group")
        action_frame.columnconfigure(2, weight=1, uniform="btn_group")

        self.btn_start = Button(
            action_frame, text="RECORD", bg="#e74c3c", fg="white",
            font=("Arial", 11, "bold"), relief="flat", pady=12, command=self.start_recording
        )
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_modify = Button(
            action_frame, text="", fg="white",
            font=("Arial", 11, "bold"), relief="flat", pady=12, command=self.handle_middle_button
        )
        self.btn_modify.grid(row=0, column=1, sticky="ew", padx=5)

        self.btn_play = Button(
            action_frame, text="EXECUTE", bg="#2ecc71", fg="white",
            font=("Arial", 11, "bold"), relief="flat", pady=12, command=self.start_playback
        )
        self.btn_play.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        self.editor_container = Frame(self.root, bg="#f4f4f9")

        file_frame = Frame(self.editor_container, bg="#f4f4f9")
        file_frame.pack(fill="x", padx=15, pady=5)
        
        Button(file_frame, text="New Flow", bg="#27ae60", fg="white", relief="flat", command=self.create_new_flow).pack(side="left", padx=5)
        Button(file_frame, text="Load External", bg="#8e44ad", fg="white", relief="flat", command=self.import_external_file).pack(side="left", padx=5)
        Button(file_frame, text="Workspace", bg="#bdc3c7", relief="flat", command=self.set_workspace).pack(side="left", padx=5)
        Button(file_frame, text="Close Flow", bg="#e74c3c", fg="white", relief="flat", command=self.close_current_file).pack(side="left", padx=5)
        
        self.btn_toggle_extras = Button(file_frame, text="Advanced Actions...", bg="#34495e", fg="white", relief="flat", command=self.toggle_extras)
        self.btn_toggle_extras.pack(side="right", padx=5)

        self.btn_toggle_basics = Button(file_frame, text="Basic Actions...", bg="#34495e", fg="white", relief="flat", command=self.toggle_basics)
        self.btn_toggle_basics.pack(side="right", padx=5)

        self.basics_frame = Frame(self.editor_container, bg="#ecf0f1", bd=1, relief="groove")
        self.basics_visible = False
        
        Button(self.basics_frame, text="Add Wait", width=9, command=lambda: self.insert_action({"type": "wait", "duration": 1.0})).pack(side="left", padx=5, pady=5)
        Button(self.basics_frame, text="Add Click", width=9, command=lambda: self.insert_action({"type": "click", "x": 0, "y": 0, "button": "left", "clicks": 1, "path": []})).pack(side="left", padx=5, pady=5)
        Button(self.basics_frame, text="Add Scroll", width=9, command=lambda: self.insert_action({"type": "scroll", "x": 0, "y": 0, "dx": 0, "dy": -100, "path": []})).pack(side="left", padx=5, pady=5)
        Button(self.basics_frame, text="Key Press", width=9, command=lambda: self.insert_action({"type": "keypress", "key": "Key.enter"})).pack(side="left", padx=5, pady=5)
        Button(self.basics_frame, text="Key Hold", width=9, command=lambda: self.insert_action({"type": "key_down", "key": "Key.shift"})).pack(side="left", padx=5, pady=5)
        Button(self.basics_frame, text="Key Release", width=10, command=lambda: self.insert_action({"type": "key_up", "key": "Key.shift"})).pack(side="left", padx=5, pady=5)

        self.extras_frame = Frame(self.editor_container, bg="#ecf0f1", bd=1, relief="groove")
        self.extras_visible = False
        
        Button(self.extras_frame, text="Add If", width=9, command=lambda: self.insert_action({"type": "if", "condition": "x == 1"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Add Else", width=9, command=lambda: self.insert_action({"type": "else"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Add While", width=9, command=lambda: self.insert_action({"type": "while", "condition": "x == 1"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Add For", width=9, command=lambda: self.insert_action({"type": "for", "statement": "i in range(5)"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Add End", width=9, bg="#bdc3c7", command=lambda: self.insert_action({"type": "end"})).pack(side="left", padx=2, pady=5)
        Label(self.extras_frame, text="|", bg="#ecf0f1", fg="#7f8c8d").pack(side="left", padx=5)
        Button(self.extras_frame, text="Set Variable", width=11, command=lambda: self.insert_action({"type": "set_var", "var_name": "x", "var_value": "True"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Run Python", width=11, command=lambda: self.insert_action({"type": "run_python", "filepath": "script.py"})).pack(side="left", padx=2, pady=5)
        Button(self.extras_frame, text="Linked Flow", width=11, command=self.add_linked_flow).pack(side="left", padx=2, pady=5)

        paned_window = ttk.PanedWindow(self.editor_container, orient="horizontal")
        paned_window.pack(fill="both", expand=True, padx=15, pady=10)

        sidebar_frame = Frame(paned_window, bg="white", bd=1, relief="sunken")
        self.tree = ttk.Treeview(sidebar_frame, show="tree headings")
        self.tree.heading("#0", text="Workspace Flows", anchor="w")
        tree_scroll = Scrollbar(sidebar_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.tree.bind("<B1-Motion>", self.on_tree_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_drag_release)
        
        canvas_frame = Frame(paned_window, bg="white", bd=1, relief="sunken")
        self.canvas = Canvas(canvas_frame, bg="#ffffff", highlightthickness=0)
        self.scrollbar = Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.root.bind("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-1*(event.delta/120)), "units"))

        paned_window.add(sidebar_frame, weight=1)
        paned_window.add(canvas_frame, weight=3)

    # ==========================================
    # TOGGLE PANELS LOGIC
    # ==========================================

    def toggle_basics(self):
        if self.basics_visible:
            self.basics_frame.pack_forget()
            self.btn_toggle_basics.config(text="Basic Actions...", bg="#34495e")
        else:
            self.basics_frame.pack(fill="x", padx=15, after=self.editor_container.winfo_children()[0])
            self.btn_toggle_basics.config(text="Hide Basics", bg="#2980B9")
        self.basics_visible = not self.basics_visible

    def toggle_extras(self):
        if self.extras_visible:
            self.extras_frame.pack_forget()
            self.btn_toggle_extras.config(text="Advanced Actions...", bg="#34495e")
        else:
            self.extras_frame.pack(fill="x", padx=15, after=self.editor_container.winfo_children()[0])
            self.btn_toggle_extras.config(text="Hide Advanced", bg="#2980B9")
        self.extras_visible = not self.extras_visible

    def insert_action(self, action_dict):
        idx = self.last_clicked_index + 1 if self.last_clicked_index is not None else len(self.recorded_actions)
        self.recorded_actions.insert(idx, action_dict)
        self.selected_indices = [idx]
        self.last_clicked_index = idx
        self._refresh_blocks()
        self._auto_save()

    # ==========================================
    # FILE MANAGEMENT & WORKSPACE TOOLS
    # ==========================================

    def create_new_flow(self):
        name = simpledialog.askstring("New Flow", "Enter a name for the new flow:")
        if not name: return
        if not name.endswith(".json"): name += ".json"
        
        filepath = os.path.join(self.workspace_dir, name)
        if os.path.exists(filepath):
            messagebox.showerror("Error", "A flow with that name already exists!")
            return
            
        self.recorded_actions = []
        self.current_filepath = filepath
        self._auto_save() 
        self.refresh_workspace()
        self._refresh_blocks()
        self._update_title()

    def close_current_file(self):
        if not self.current_filepath and not self.recorded_actions:
            return
        if messagebox.askyesno("Close Flow", "Are you sure you want to close the current flow?"):
            self.current_filepath = None
            self.recorded_actions.clear()
            self.selected_indices = []
            self.last_clicked_index = None
            self._update_title()
            self._refresh_blocks()

    def import_external_file(self):
        source_path = filedialog.askopenfilename(filetypes=[("JSON Flow Files", "*.json")], title="Select External Flow")
        if not source_path: return
        
        dest_path = os.path.join(self.workspace_dir, os.path.basename(source_path))
        if source_path != dest_path:
            try:
                shutil.copy(source_path, dest_path)
            except Exception as e:
                messagebox.showerror("Import Error", f"Could not copy file:\n{e}")
                return
                
        self.refresh_workspace()
        self.load_from_path(dest_path)

    def load_from_path(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f: 
                self.recorded_actions = json.load(f)
            self.current_filepath = filepath
            self.selected_indices = []
            self.last_clicked_index = None
            self._refresh_blocks()
            self._update_title()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load file:\n{e}")

    def add_linked_flow(self):
        filepath = filedialog.askopenfilename(
            initialdir=self.workspace_dir,
            filetypes=[("JSON Flow Files", "*.json")], 
            title="Select Flow to Link"
        )
        if filepath:
            self.insert_action({"type": "link", "filepath": filepath})

    # ==========================================
    # WORKSPACE DIRECTORY & CASCADING RENAME
    # ==========================================
    
    def set_workspace(self):
        folder = filedialog.askdirectory(title="Select Workspace Folder")
        if folder:
            self.workspace_dir = folder
            self.refresh_workspace()

    def refresh_workspace(self):
        self.tree.delete(*self.tree.get_children())
        self.file_map.clear()
        if not self.workspace_dir or not os.path.exists(self.workspace_dir): return
        self.tree.heading("#0", text=f"[{os.path.basename(self.workspace_dir)}]")
        self._build_tree(self.workspace_dir, "")

    def _build_tree(self, dir_path, parent_node):
        try:
            items = os.listdir(dir_path)
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))
            for item in items:
                full_path = os.path.join(dir_path, item)
                if os.path.isdir(full_path):
                    if not item.startswith("."):
                        folder_id = self.tree.insert(parent_node, "end", text=item, open=False)
                        self._build_tree(full_path, folder_id)
                elif item.endswith(".json"):
                    item_id = self.tree.insert(parent_node, "end", text=item)
                    self.file_map[item_id] = full_path
        except PermissionError: pass

    def on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if item_id in self.file_map:
            self.load_from_path(self.file_map[item_id])

    def on_tree_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            if item_id in self.file_map:
                filepath = self.file_map[item_id]
                menu = Menu(self.root, tearoff=0)
                menu.add_command(label="Rename File", command=lambda: self.rename_workspace_file(filepath))
                menu.add_separator()
                menu.add_command(label="Show in Folder", command=lambda: self.show_in_folder(filepath))
                menu.add_command(label="Delete", command=lambda: self.delete_workspace_file(filepath))
                menu.post(event.x_root, event.y_root)

    def rename_workspace_file(self, old_filepath):
        old_name = os.path.basename(old_filepath)
        new_name = simpledialog.askstring("Rename Flow", f"Rename '{old_name}' to:", initialvalue=old_name)
        if not new_name or new_name == old_name: return
        if not new_name.endswith(".json"): new_name += ".json"
        
        new_filepath = os.path.join(os.path.dirname(old_filepath), new_name)
        if os.path.exists(new_filepath):
            messagebox.showerror("Error", "A file with that name already exists!")
            return
            
        try:
            os.rename(old_filepath, new_filepath)
        except Exception as e:
            messagebox.showerror("Error", f"Could not rename file:\n{e}")
            return
            
        for item in os.listdir(self.workspace_dir):
            if item.endswith(".json"):
                fpath = os.path.join(self.workspace_dir, item)
                try:
                    with open(fpath, "r", encoding="utf-8") as f: data = json.load(f)
                    changed = False
                    for act in data:
                        if act.get("type") == "link" and act.get("filepath") == old_filepath:
                            act["filepath"] = new_filepath
                            changed = True
                    if changed:
                        with open(fpath, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
                except Exception: pass
                
        changed_in_mem = False
        for act in self.recorded_actions:
            if act.get("type") == "link" and act.get("filepath") == old_filepath:
                act["filepath"] = new_filepath
                changed_in_mem = True
                
        if changed_in_mem:
            self._refresh_blocks()
            self._auto_save()
            
        if self.current_filepath == old_filepath:
            self.current_filepath = new_filepath
            self._update_title()
            
        self.refresh_workspace()

    def show_in_folder(self, filepath):
        try:
            if platform.system() == "Windows": subprocess.Popen(rf'explorer /select,"{filepath}"')
            elif platform.system() == "Darwin": subprocess.Popen(["open", "-R", filepath])
            else: subprocess.Popen(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")

    def delete_workspace_file(self, filepath):
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete this flow?\n\n{os.path.basename(filepath)}"):
            try:
                os.remove(filepath)
                if self.current_filepath == filepath:
                    self.recorded_actions.clear()
                    self.current_filepath = None
                    self._update_title()
                    self._refresh_blocks()
                self.refresh_workspace()
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete file:\n{e}")

    # ==========================================
    # SIDEBAR DRAG TO CANVAS 
    # ==========================================

    def on_tree_drag_motion(self, event):
        if not self.tree_drag_data["is_dragging"]:
            item_id = self.tree.identify_row(event.y)
            if item_id and item_id in self.file_map:
                self.tree_drag_data["is_dragging"] = True
                self.tree_drag_data["filepath"] = self.file_map[item_id]
                
                ghost = Toplevel(self.root)
                ghost.wm_overrideredirect(True)
                ghost.attributes('-alpha', 0.8)
                ghost.attributes('-topmost', True)
                Label(ghost, text=f"LINK: {os.path.basename(self.file_map[item_id])}", bg="#EF476F", fg="white", font=("Arial", 9, "bold"), padx=10, pady=5).pack()
                self.tree_drag_data["ghost"] = ghost
            else: return 

        if self.tree_drag_data["ghost"]:
            self.tree_drag_data["ghost"].geometry(f"+{event.x_root+15}+{event.y_root+15}")
            
    def on_tree_drag_release(self, event):
        if not self.tree_drag_data["is_dragging"]: return
            
        if self.tree_drag_data["ghost"]:
            self.tree_drag_data["ghost"].destroy()
            
        cx = self.canvas.winfo_rootx()
        cy = self.canvas.winfo_rooty()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cx <= event.x_root <= cx + cw and cy <= event.y_root <= cy + ch:
            relative_y = event.y_root - cy
            canvas_y = self.canvas.canvasy(relative_y)
            
            new_idx = int((canvas_y - 10) // 40)
            if new_idx < 0: new_idx = 0
            if new_idx > len(self.recorded_actions): new_idx = len(self.recorded_actions)
            
            self.last_clicked_index = new_idx - 1
            self.insert_action({"type": "link", "filepath": self.tree_drag_data["filepath"]})
            
        self.tree_drag_data = {"is_dragging": False, "filepath": None, "ghost": None}

    # ==========================================
    # MULTI-SELECT DOUBLE CLICK & RIGHT CLICK
    # ==========================================

    def show_context_menu(self, event, idx):
        if idx not in self.selected_indices:
            self.selected_indices = [idx]
            self.last_clicked_index = idx
            self._update_selection_colors()

        menu = Menu(self.root, tearoff=0)
        menu.add_command(label="Delete Selected", command=self.delete_step)
        menu.add_separator()
        menu.add_command(label="Debug JSON", command=self.debug_json)
        menu.post(event.x_root, event.y_root)

    def debug_json(self):
        if not self.recorded_actions: return
        temp_file = "temp_debug_flow.json"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.recorded_actions, f, indent=4)
            
        try:
            if platform.system() == "Windows": os.startfile(temp_file)
            elif platform.system() == "Darwin": subprocess.Popen(["open", temp_file])
            else: subprocess.Popen(["xdg-open", temp_file])
        except Exception:
            messagebox.showerror("Error", "Could not open text editor.")
            return
            
        if messagebox.askyesno("Reload Actions", "Did you finish debugging/editing the JSON?\n\n(Make sure you hit Save in Notepad first!)\n\nClick Yes to rebuild the blocks."):
            try:
                with open(temp_file, "r", encoding="utf-8") as f:
                    self.recorded_actions = json.load(f)
                self.selected_indices = []
                self._refresh_blocks()
                self._auto_save()
            except Exception as e:
                messagebox.showerror("Error", f"Invalid JSON Syntax. Could not load.\n\nError: {e}")

    def open_edit_dialog(self, idx):
        self.selected_indices = [idx]
        self.last_clicked_index = idx
        self._update_selection_colors()
        
        action = self.recorded_actions[idx]
        dlg = Toplevel(self.root)
        dlg.title(f"Edit {action['type'].capitalize()}")
        dlg.geometry("300x250")
        dlg.configure(bg="#f4f4f9")
        dlg.attributes("-topmost", True)
        dlg.grab_set() 

        keys_to_edit = []
        if action["type"] == "wait": keys_to_edit = ["duration"]
        elif action["type"] == "click": keys_to_edit = ["x", "y", "button", "clicks"]
        elif action["type"] == "scroll": keys_to_edit = ["x", "y", "dx", "dy"]
        elif action["type"] in ["keypress", "key_down", "key_up"]: keys_to_edit = ["key"]
        elif action["type"] == "link": keys_to_edit = ["filepath"]
        elif action["type"] == "set_var": keys_to_edit = ["var_name", "var_value"]
        elif action["type"] in ["if", "while"]: keys_to_edit = ["condition"]
        elif action["type"] == "for": keys_to_edit = ["statement"]
        elif action["type"] == "run_python": keys_to_edit = ["filepath"]

        entries = {}
        row_frame = Frame(dlg, bg="#f4f4f9")
        row_frame.pack(pady=20)

        for k in keys_to_edit:
            sub_frame = Frame(row_frame, bg="#f4f4f9")
            sub_frame.pack(fill="x", pady=5)
            Label(sub_frame, text=f"{k.capitalize()}:", width=10, anchor="e", bg="#f4f4f9", font=("Arial", 9, "bold")).pack(side="left", padx=5)
            
            if k == "key":
                ent = ttk.Combobox(sub_frame, width=22, values=[
                    "Key.enter", "Key.space", "Key.cmd", "Key.esc", "Key.tab", 
                    "Key.shift", "Key.ctrl", "Key.alt", 
                    "Key.backspace", "Key.delete", 
                    "Key.up", "Key.down", "Key.left", "Key.right",
                    "Key.ctrl + c", "Key.ctrl + v", "Key.ctrl + a"
                ])
                ent.insert(0, str(action.get(k, "")))
                ent.pack(side="left")
            elif k == "button":
                ent = ttk.Combobox(sub_frame, width=22, values=["left", "right", "middle"])
                ent.insert(0, str(action.get(k, "left")))
                ent.pack(side="left")
            else:
                ent = Entry(sub_frame, width=25)
                default_val = action.get(k, 1 if k == "clicks" else "")
                ent.insert(0, str(default_val))
                ent.pack(side="left")
            
            entries[k] = ent

        def save_changes():
            try:
                for k in keys_to_edit:
                    val = entries[k].get()
                    if k in ["x", "y", "dx", "dy", "clicks"]: action[k] = int(val)
                    elif k == "duration": action[k] = float(val)
                    else: action[k] = val 
                dlg.destroy()
                self._refresh_blocks()
                self._auto_save()
            except ValueError:
                messagebox.showerror("Error", "Invalid number format.")

        Button(dlg, text="Save Changes", bg="#2ecc71", fg="white", font=("Arial", 10, "bold"), relief="flat", pady=5, command=save_changes).pack(fill="x", padx=50, pady=10)

    # ==========================================
    # DYNAMIC MIDDLE BUTTON LOGIC
    # ==========================================

    def _update_middle_button_ui(self):
        if self.editor_visible:
            self.btn_modify.config(text="CLOSE EDITOR", bg="#e67e22")
        elif len(self.recorded_actions) > 0:
            self.btn_modify.config(text="OPEN EDITOR", bg="#f39c12")
        else:
            self.btn_modify.config(text="OPEN WORKSPACE", bg="#3498db")

    def handle_middle_button(self):
        if self.editor_visible: self.hide_editor()
        else: self.show_editor()

    def show_editor(self):
        self.editor_visible = True
        self.editor_container.pack(fill="both", expand=True)
        self.root.geometry("1050x700") 
        self.refresh_workspace()
        self._update_middle_button_ui()
        self._refresh_blocks()

    def hide_editor(self):
        self.editor_visible = False
        self.editor_container.pack_forget() 
        self.root.geometry("1050x110") 
        self._update_middle_button_ui()

    # ==========================================
    # EXECUTION ENGINE (THE VIRTUAL MACHINE)
    # ==========================================

    def start_playback(self):
        if not self.recorded_actions:
            messagebox.showwarning("Empty", "There are no actions to execute!")
            return
            
        success, msg, jump_table = self._compile_syntax_jumps(self.recorded_actions)
        if not success:
            messagebox.showerror("Syntax Error", msg)
            return
            
        self.is_playing = True
        self.root.withdraw() 
        self.playback_listener = keyboard.Listener(on_press=self._check_abort)
        self.playback_listener.start()
        threading.Thread(target=self._execute_vm_loop, args=(self.recorded_actions, jump_table, {}), daemon=True).start()

    def _compile_syntax_jumps(self, actions):
        jump_table = {}
        stack = []
        for i, act in enumerate(actions):
            t = act["type"]
            if t in ["if", "while", "for"]:
                stack.append((i, t))
            elif t == "else":
                if not stack or stack[-1][1] != "if":
                    return False, f"Unexpected 'Else' block at step {i+1}. Must immediately follow an 'If' condition.", {}
                if_ip, _ = stack.pop()
                jump_table[if_ip] = i
                jump_table[i] = if_ip
                stack.append((i, "else"))
            elif t == "end":
                if not stack:
                    return False, f"Unexpected 'End' block at step {i+1}. It has no opening condition.", {}
                head_ip, head_type = stack.pop()
                jump_table[head_ip] = i
                jump_table[i] = head_ip
                
        if stack:
            bad_ip, bad_type = stack[0]
            return False, f"Missing 'End' block for the '{bad_type.capitalize()}' created at step {bad_ip+1}.", {}
            
        return True, "Success", jump_table

    def _check_abort(self, key):
        if key == keyboard.Key.esc: self.is_playing = False

    def _parse_val(self, v):
        if isinstance(v, str):
            if v.lower() == "true": return True
            if v.lower() == "false": return False
            try: return int(v)
            except: pass
            try: return float(v)
            except: pass
        return v

    def _evaluate_condition(self, cond_str, variables):
        try:
            return bool(eval(cond_str, {}, variables))
        except Exception as e:
            print(f"Condition Eval Failed [{cond_str}]: {e}")
            return False

    def _execute_vm_loop(self, actions_list, jump_table, parent_vars, depth=0):
        if depth > 10: return
        is_main_thread = (depth == 0)
        variables = parent_vars if parent_vars else {}
        loop_states = {}
        
        if is_main_thread: time.sleep(0.5)

        ip = 0
        while ip < len(actions_list):
            if not self.is_playing: break
            action = actions_list[ip]
            t = action["type"]

            try:
                if t == "wait":
                    time.sleep(action["duration"])
                    ip += 1
                    
                elif t == "click":
                    path = action.get("path", [])
                    if not path:
                        cx, cy = self.mouse_ctrl.position
                        tx, ty = action["x"], action["y"]
                        steps = 15
                        for i in range(1, steps + 1):
                            ix = cx + (tx - cx) * (i / steps)
                            iy = cy + (ty - cy) * (i / steps)
                            curr_x, curr_y = self.mouse_ctrl.position
                            self.mouse_ctrl.move(int(ix - curr_x), int(iy - curr_y))
                            time.sleep(0.01)
                    else:
                        for px, py in path:
                            cx, cy = self.mouse_ctrl.position
                            self.mouse_ctrl.move(int(px - cx), int(py - cy))
                            time.sleep(0.015)
                            
                    cx, cy = self.mouse_ctrl.position
                    self.mouse_ctrl.move(int(action["x"] - cx), int(action["y"] - cy))
                    time.sleep(0.05)
                    
                    btn = mouse.Button.right if "right" in action["button"] else mouse.Button.middle if "middle" in action["button"] else mouse.Button.left
                    self.mouse_ctrl.click(btn, action.get("clicks", 1))
                    ip += 1
                    
                elif t == "scroll":
                    path = action.get("path", [])
                    if path:
                        for px, py in path:
                            cx, cy = self.mouse_ctrl.position
                            self.mouse_ctrl.move(int(px - cx), int(py - cy))
                            time.sleep(0.015)
                            
                    cx, cy = self.mouse_ctrl.position
                    self.mouse_ctrl.move(int(action["x"] - cx), int(action["y"] - cy))
                    time.sleep(0.05)
                    self.mouse_ctrl.scroll(action["dx"], action["dy"])
                    ip += 1
                    
                elif t == "keypress":
                    keys_to_press = [k.strip() for k in action["key"].split("+")]
                    parsed_keys = []
                    for k in keys_to_press:
                        if k.startswith("Key."): parsed_keys.append(getattr(keyboard.Key, k.replace("Key.", ""), None))
                        else: parsed_keys.append(k.strip("'"))
                    
                    for k in parsed_keys:
                        if k: self.keyboard_ctrl.press(k)
                    for k in reversed(parsed_keys):
                        if k: self.keyboard_ctrl.release(k)
                    ip += 1

                elif t == "key_down":
                    keys_to_press = [k.strip() for k in action["key"].split("+")]
                    parsed_keys = []
                    for k in keys_to_press:
                        if k.startswith("Key."): parsed_keys.append(getattr(keyboard.Key, k.replace("Key.", ""), None))
                        else: parsed_keys.append(k.strip("'"))
                    for k in parsed_keys:
                        if k: self.keyboard_ctrl.press(k)
                    ip += 1

                elif t == "key_up":
                    keys_to_press = [k.strip() for k in action["key"].split("+")]
                    parsed_keys = []
                    for k in keys_to_press:
                        if k.startswith("Key."): parsed_keys.append(getattr(keyboard.Key, k.replace("Key.", ""), None))
                        else: parsed_keys.append(k.strip("'"))
                    for k in reversed(parsed_keys):
                        if k: self.keyboard_ctrl.release(k)
                    ip += 1
                    
                elif t == "set_var":
                    variables[action["var_name"]] = self._parse_val(action["var_value"])
                    ip += 1
                    
                elif t == "if":
                    if self._evaluate_condition(action["condition"], variables): ip += 1
                    else: ip = jump_table[ip] + 1
                
                elif t == "else":
                    ip = jump_table[ip] + 1

                elif t == "while":
                    if self._evaluate_condition(action["condition"], variables): ip += 1
                    else: ip = jump_table[ip] + 1
                        
                elif t == "for":
                    if ip not in loop_states:
                        stmt = action.get("statement", "").strip()
                        if stmt.startswith("for "): stmt = stmt[4:]
                        if stmt.endswith(":"): stmt = stmt[:-1]
                        stmt = stmt.strip()
                        
                        if " in " in stmt:
                            var_part, iter_part = stmt.split(" in ", 1)
                            try:
                                iterable_obj = eval(iter_part, {}, variables)
                                loop_states[ip] = {"iter": iter(iterable_obj), "vars": var_part.strip()}
                            except Exception as e:
                                print(f"For loop eval failed: {e}")
                                loop_states[ip] = {"iter": iter([]), "vars": var_part.strip()}
                        else:
                            loop_states[ip] = {"iter": iter([]), "vars": ""}
                            
                    if loop_states[ip]["vars"]:
                        try:
                            val = next(loop_states[ip]["iter"])
                            local_env = {"__val": val}
                            local_env.update(variables)
                            exec(f"{loop_states[ip]['vars']} = __val", {}, local_env)
                            del local_env["__val"]
                            variables.update(local_env)
                            ip += 1
                        except StopIteration:
                            del loop_states[ip]
                            ip = jump_table[ip] + 1
                    else:
                        del loop_states[ip]
                        ip = jump_table[ip] + 1
                        
                elif t == "end":
                    head_ip = jump_table[ip]
                    head_type = actions_list[head_ip]["type"]
                    if head_type in ["if", "else"]:
                        ip += 1
                    elif head_type in ["while", "for"]:
                        ip = head_ip 
                        
                elif t == "run_python":
                    script = action["filepath"]
                    result = subprocess.run(["python", script, json.dumps(variables)], capture_output=True, text=True)
                    for line in result.stdout.splitlines():
                        try:
                            data = json.loads(line.strip())
                            if isinstance(data, dict): variables.update(data)
                        except: pass
                    ip += 1
                    
                elif t == "link":
                    with open(action["filepath"], "r", encoding="utf-8") as sub_file:
                        sub_actions = json.load(sub_file)
                        success, _, sub_jumps = self._compile_syntax_jumps(sub_actions)
                        if success: self._execute_vm_loop(sub_actions, sub_jumps, variables, depth + 1)
                    ip += 1
                    
            except Exception as e: 
                print(f"Failed to execute at line {ip} ({t}): {e}")
                ip += 1

        if is_main_thread:
            self.is_playing = False
            if self.playback_listener: self.playback_listener.stop()
            self.root.after(0, self._finish_playback)

    def _finish_playback(self):
        self.root.deiconify()
        messagebox.showinfo("Execution Finished", "Finished executing all actions.")

    # ==========================================
    # RECORDING ENGINE 
    # ==========================================

    def _open_mini_ui(self):
        self.mini_window = Toplevel(self.root)
        self.mini_window.title("REC")
        self.mini_window.geometry("260x70+40+40")
        self.mini_window.attributes("-topmost", True)
        self.mini_window.protocol("WM_DELETE_WINDOW", self.stop_recording)
        Label(self.mini_window, text="Recording actions...", fg="red", font=("Arial", 9, "bold")).pack(pady=3)
        Button(self.mini_window, text="Stop Recording", bg="#e74c3c", fg="white", font=("Arial", 9, "bold"), relief="flat", command=self.stop_recording).pack(pady=3)
        self.mini_window.update()

    def _is_inside_mini_window(self, x, y, margin=40):
        if not self.mini_window or not self.mini_window.winfo_exists(): return False
        wx = self.mini_window.winfo_rootx()
        wy = self.mini_window.winfo_rooty()
        ww = self.mini_window.winfo_width()
        wh = self.mini_window.winfo_height()
        return (wx - margin <= x <= wx + ww + margin) and (wy - margin <= y <= wy + wh + margin)

    def start_recording(self):
        if self.current_filepath:
            ans = messagebox.askyesnocancel(
                "Record Option", 
                "You currently have a flow open. Do you want to continue recording on this existing flow?\n\nYes = Continue existing recording\nNo = Start completely new recording\nCancel = Abort"
            )
            if ans is None:
                return
            elif ans is False:
                self.recorded_actions.clear()
                self.current_filepath = None
                self._update_title()
        elif self.recorded_actions:
            if not messagebox.askyesno("Warning", "Starting a new recording will clear your unsaved canvas.\n\nProceed?"):
                return
            self.recorded_actions.clear()
                
        self.selected_indices = []
        self.current_path = []
        self.last_move_time = time.time()
        
        self.root.withdraw()
        self._open_mini_ui()
        self.is_recording = True
        self.last_action_time = time.time()
        
        self.mouse_listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll, on_move=self._on_move)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_press)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def _log_idle_wait(self):
        now = time.time()
        elapsed = round(now - self.last_action_time, 2)
        if elapsed >= 0.05: self.recorded_actions.append({"type": "wait", "duration": elapsed})
        self.last_action_time = now

    def _on_move(self, x, y):
        if not self.is_recording: return
        now = time.time()
        if now - getattr(self, 'last_move_time', 0) > 0.015:
            if not hasattr(self, 'current_path'): self.current_path = []
            self.current_path.append((int(x), int(y)))
            self.last_move_time = now

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording or not pressed or self._is_inside_mini_window(x, y): return
        self._log_idle_wait()
        
        path_copy = getattr(self, 'current_path', []).copy()
        self.current_path = []
        
        if len(path_copy) > 50:
            step = len(path_copy) / 50.0
            path_copy = [path_copy[int(i * step)] for i in range(50)]
            
        self.recorded_actions.append({"type": "click", "x": int(x), "y": int(y), "button": button.name, "clicks": 1, "path": path_copy})

    def _on_scroll(self, x, y, dx, dy):
        if not self.is_recording or self._is_inside_mini_window(x, y): return
        self._log_idle_wait()
        
        path_copy = getattr(self, 'current_path', []).copy()
        self.current_path = []
        if len(path_copy) > 50:
            step = len(path_copy) / 50.0
            path_copy = [path_copy[int(i * step)] for i in range(50)]
            
        self.recorded_actions.append({"type": "scroll", "x": int(x), "y": int(y), "dx": dx, "dy": dy, "path": path_copy})

    def _on_press(self, key):
        if not self.is_recording: return
        self._log_idle_wait()
        self.recorded_actions.append({"type": "keypress", "key": key.char if hasattr(key, 'char') and key.char else str(key)})

    def stop_recording(self):
        self.is_recording = False
        if self.mouse_listener: self.mouse_listener.stop()
        if self.keyboard_listener: self.keyboard_listener.stop()
        
        if len(self.recorded_actions) > 0 and self.recorded_actions[-1]["type"] == "click":
            if self._is_inside_mini_window(self.recorded_actions[-1]["x"], self.recorded_actions[-1]["y"], margin=60):
                self.recorded_actions.pop()
                if len(self.recorded_actions) > 0 and self.recorded_actions[-1]["type"] == "wait":
                    self.recorded_actions.pop()

        if self.mini_window: self.mini_window.destroy()
        self.root.deiconify()
        
        if not self.current_filepath and self.recorded_actions:
            name = simpledialog.askstring("Save Recording", "Enter a name for this recording:\n(Leave blank to auto-generate a name)")
            
            if not name or not name.strip():
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                name = f"RecordedFlow_{timestamp}.json"
            elif not name.endswith(".json"):
                name += ".json"
                
            filepath = os.path.join(self.workspace_dir, name)
            
            if os.path.exists(filepath) and name != f"RecordedFlow_{time.strftime('%Y%m%d_%H%M%S')}.json":
                base, ext = os.path.splitext(name)
                filepath = os.path.join(self.workspace_dir, f"{base}_{time.strftime('%H%M%S')}{ext}")
                
            self.current_filepath = filepath
            self._update_title()
            
        self._refresh_blocks()
        self._auto_save()
        self.refresh_workspace()
        
        if not self.editor_visible: self.show_editor()

    # ==========================================
    # MULTI-SELECT UI RENDERING & DRAGGING
    # ==========================================

    def on_drag_start(self, event, idx):
        ctrl = (event.state & 0x0004) != 0 or (event.state & 0x20000) != 0
        shift = (event.state & 0x0001) != 0

        if shift and self.last_clicked_index is not None:
            start = min(self.last_clicked_index, idx)
            end = max(self.last_clicked_index, idx)
            self.selected_indices = list(range(start, end + 1))
        elif ctrl:
            if idx in self.selected_indices:
                self.selected_indices.remove(idx)
            else:
                self.selected_indices.append(idx)
                self.last_clicked_index = idx
        else:
            if idx not in self.selected_indices:
                self.selected_indices = [idx]
            self.last_clicked_index = idx

        self._update_selection_colors()

        self.drag_data["items"] = sorted(self.selected_indices)
        self.drag_data["y"] = self.canvas.canvasy(event.y)
        
        for i in self.drag_data["items"]:
            self.canvas.tag_raise(f"block_{i}")
            self.canvas.tag_raise(f"poly_{i}")

    def on_drag_motion(self, event):
        if not self.drag_data["items"]: return
        cy = self.canvas.canvasy(event.y)
        dy = cy - self.drag_data["y"]
        for i in self.drag_data["items"]:
            self.canvas.move(f"block_{i}", 0, dy)
            self.canvas.move(f"poly_{i}", 0, dy)
        self.drag_data["y"] = cy

    def on_drag_release(self, event):
        if not self.drag_data["items"]: return
        cy = self.canvas.canvasy(event.y)
        new_idx = int((cy - 10) // 40)
        new_idx = max(0, min(new_idx, len(self.recorded_actions)))
        
        dragged_actions = [self.recorded_actions[i] for i in self.drag_data["items"]]
        
        for i in reversed(self.drag_data["items"]):
            self.recorded_actions.pop(i)
            
        items_before_drop = sum(1 for i in self.drag_data["items"] if i < new_idx)
        adjusted_idx = new_idx - items_before_drop
        
        for i, action in enumerate(dragged_actions):
            self.recorded_actions.insert(adjusted_idx + i, action)
            
        self.selected_indices = list(range(adjusted_idx, adjusted_idx + len(dragged_actions)))
        self.last_clicked_index = self.selected_indices[-1]
            
        self.drag_data["items"] = []
        self._refresh_blocks()
        self._auto_save()

    def _draw_scratch_block(self, idx, action, x_offset, y):
        width, height = 500, 40
        notch_x, notch_w, notch_d = 20, 15, 7
        pts = [x_offset, y, x_offset + notch_x, y, x_offset + notch_x + 5, y + notch_d, x_offset + notch_x + notch_w - 5, y + notch_d,
               x_offset + notch_x + notch_w, y, x_offset + width, y, x_offset + width, y + height, x_offset + notch_x + notch_w, y + height,
               x_offset + notch_x + notch_w - 5, y + height + notch_d, x_offset + notch_x + 5, y + height + notch_d,
               x_offset + notch_x, y + height, x_offset, y + height]
               
        color = self.colors.get(action["type"], "#888888")
        is_selected = (idx in self.selected_indices)
        outline_color = "#FFD700" if is_selected else "#2c3e50"
        line_width = 3 if is_selected else 1
        
        group_tag = f"block_{idx}"
        poly_tag = f"poly_{idx}"
        
        self.canvas.create_polygon(pts, fill=color, outline=outline_color, width=line_width, tags=(group_tag, poly_tag))
        self.canvas.create_text(x_offset + 15, y + 20, text=self._format_action(action), fill="white", font=("Segoe UI", 9, "bold"), anchor="w", tags=(group_tag,))
        
        self.canvas.tag_bind(group_tag, "<ButtonPress-1>", lambda e, i=idx: self.on_drag_start(e, i))
        self.canvas.tag_bind(group_tag, "<B1-Motion>", self.on_drag_motion)
        self.canvas.tag_bind(group_tag, "<ButtonRelease-1>", self.on_drag_release)
        self.canvas.tag_bind(group_tag, "<Double-Button-1>", lambda e, i=idx: self.open_edit_dialog(i))
        self.canvas.tag_bind(group_tag, "<Button-3>", lambda e, i=idx: self.show_context_menu(e, i))

    def _refresh_blocks(self):
        self.canvas.delete("all")
        if not self.recorded_actions:
            self.canvas.create_text(
                20, 20, 
                text="No actions loaded.\n\n- Click RECORD or New Flow to start.\n- Shift+Click to select multiple blocks.\n- Drag groups up and down to reorder.", 
                fill="#7f8c8d", font=("Segoe UI", 11, "italic"), anchor="nw"
            )
            self.canvas.config(scrollregion=self.canvas.bbox("all"))
            return

        start_y = 10
        current_depth = 0
        
        for i, action in enumerate(self.recorded_actions):
            t = action["type"]
            if t in ["end", "else"]:
                current_depth = max(0, current_depth - 1)
                
            x_offset = 20 + (current_depth * 30)
            self._draw_scratch_block(i, action, x_offset, start_y)
            start_y += 40 
            
            if t in ["if", "while", "for", "else"]:
                current_depth += 1
                
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def _update_selection_colors(self):
        for i in range(len(self.recorded_actions)):
            is_selected = (i in self.selected_indices)
            outline_color = "#FFD700" if is_selected else "#2c3e50"
            line_width = 3 if is_selected else 1
            self.canvas.itemconfig(f"poly_{i}", outline=outline_color, width=line_width)

    def _format_action(self, action):
        t = action["type"]
        if t == "wait": return f"Wait for {action['duration']}s"
        elif t == "click": 
            c_str = f" {action.get('clicks', 1)}x" if action.get('clicks', 1) > 1 else ""
            return f"Click{c_str} {action['button']} at X:{action['x']}, Y:{action['y']}"
        elif t == "scroll": return f"Scroll {'Up' if action['dy'] > 0 else 'Down'} at X:{action['x']}, Y:{action['y']}"
        elif t == "keypress": return f"Press '{action['key']}'"
        elif t == "key_down": return f"Hold '{action['key']}'"
        elif t == "key_up": return f"Release '{action['key']}'"
        elif t == "link": return f"RUN FLOW: {os.path.basename(action['filepath'])}"
        elif t == "set_var": return f"Set {action['var_name']} = {action['var_value']}"
        elif t == "if": return f"If ({action['condition']}):"
        elif t == "else": return "Else:"
        elif t == "while": return f"While ({action['condition']}):"
        elif t == "for": return f"For ({action.get('statement', '')}):"
        elif t == "end": return "End"
        elif t == "run_python": return f"RUN SCRIPT: {os.path.basename(action['filepath'])}"
        return str(action)
    
    def delete_step(self):
        if not self.selected_indices: return
        for i in sorted(self.selected_indices, reverse=True):
            del self.recorded_actions[i]
        self.selected_indices = []
        self.last_clicked_index = None
        self._refresh_blocks()
        self._auto_save()

if __name__ == "__main__":
    app_root = Tk()
    app = ScratchActionRecorder(app_root)
    app_root.mainloop()