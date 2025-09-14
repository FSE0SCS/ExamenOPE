# main_premium_tk_final_v2.py
"""
Examen OPE - Tkinter + ttkbootstrap
- Radiobuttons para respuestas
- Ventana autoajustable (90% pantalla)
- Scroll vertical en preguntas
- Botones de navegación debajo de la ventana
- Temporizador 90 min en cuenta atrás
- PDF y gráficas de evolución
- MEJORA: Ventana adaptable al ancho del monitor
"""

import os, random, sqlite3, math
from datetime import datetime, date
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from fpdf import FPDF
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ---------------- CONFIG ----------------
APP_TITLE = "Examen OPE - Desktop"
DATA_DIR = "data"
DEFAULT_EXCEL = os.path.join(DATA_DIR, "cuestionario_procesado.xlsx")
DB_FILE = os.path.join(DATA_DIR, "exam_attempts.db")

DEFAULT_USER = "Vanessa"
DEFAULT_PASSWORD = "OPE_ Vane_01"

EXAM_SIZE = 100
QUESTIONS_PER_PAGE = 20
EXAM_DURATION_SECONDS = 90 * 60  # 90 min

# ----------------- SQLITE -----------------
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def get_db_conn():
    ensure_data_dir()
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        day TEXT,
        timestamp TEXT,
        score REAL,
        correct INTEGER,
        wrong INTEGER
    )
    """)
    conn.commit()
    return conn

DB_CONN = get_db_conn()

def record_attempt(user, score, correct, wrong):
    cur = DB_CONN.cursor()
    day = date.today().isoformat()
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    cur.execute("INSERT INTO attempts (user, day, timestamp, score, correct, wrong) VALUES (?, ?, ?, ?, ?, ?)",
                (user, day, ts, score, correct, wrong))
    DB_CONN.commit()

def get_attempts(user):
    cur = DB_CONN.cursor()
    cur.execute("SELECT * FROM attempts WHERE user=? ORDER BY timestamp", (user,))
    return cur.fetchall()

# ----------------- LOAD QUESTIONS -----------------
def load_questions_from_excel(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Excel no encontrado: {path}")
    df = pd.read_excel(path, engine="openpyxl")
    expected = ["Pregunta","Respuesta A","Respuesta B","Respuesta C","Respuesta D","Respuesta Correcta (Letra)","Respuesta Correcta (Texto)"]
    for c in expected:
        if c not in df.columns:
            raise ValueError(f"Columna faltante: {c}")
    return df.reset_index(drop=True)

# ----------------- PDF -----------------
def generate_pdf_report(output_path, user, exam_df, answers_dict, score, correct_list, wrong_list, start_time, end_time):
    """Genera PDF con mejor manejo de texto largo"""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Encabezado
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 10, f"Informe de examen - Usuario: {user}", ln=1, align="C")
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, f"Inicio: {start_time}   Fin: {end_time}", ln=1)
    pdf.cell(0, 6, f"Puntuacion: {score:.2f} puntos", ln=1)
    pdf.ln(3)
    
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(0, 8, f"Aciertos: {len(correct_list)}  Fallos: {len(wrong_list)}", ln=1)
    pdf.ln(5)
    
    if wrong_list:
        pdf.set_font("Arial", style="B", size=11)
        pdf.cell(0, 8, "PREGUNTAS FALLADAS:", ln=1)
        pdf.ln(3)
        
        pdf.set_font("Arial", size=9)
        for i in wrong_list:
            if i < len(exam_df):
                row = exam_df.iloc[i]
                q_text = str(row["Pregunta"])[:200]  # Limitar longitud
                if len(str(row["Pregunta"])) > 200:
                    q_text += "..."
                
                corr_text = str(row["Respuesta Correcta (Texto)"])[:100]
                if len(str(row["Respuesta Correcta (Texto)"])) > 100:
                    corr_text += "..."
                
                chosen = answers_dict.get(f"q_{i}", "No contestada")
                
                # Pregunta
                pdf.set_font("Arial", style="B", size=9)
                pdf.multi_cell(0, 4, f"P{i+1}: {q_text}")
                
                # Respuestas
                pdf.set_font("Arial", size=8)
                pdf.multi_cell(0, 4, f"Tu respuesta: {chosen}")
                pdf.multi_cell(0, 4, f"Correcta: {corr_text}")
                pdf.ln(3)
    else:
        pdf.set_font("Arial", style="B", size=12)
        pdf.cell(0, 10, "¡EXAMEN PERFECTO! No hay preguntas falladas.", ln=1, align="C")
    
    pdf.output(output_path)
    return output_path

# ----------------- MAIN APP -----------------
class ExamApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.style = tb.Style(theme="superhero")
        self.df_questions = None
        self.exam_indices = []
        self.answers = {}
        self.vars = {}
        self.current_page = 0
        self.pages = 0
        self.start_time = None
        self.time_left = 0
        self.last_score = 0
        self.last_correct = 0
        self.last_wrong = []
        
        # Variables para el ancho adaptable
        self.current_width = 0
        
        self._build_ui()
        
        # Configurar redimensionamiento
        self.root.bind("<Configure>", self._on_window_resize)

    def _build_ui(self):
        # Configurar grid weights para expansión
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        self.container = ttk.Frame(self.root, padding=10)
        self.container.pack(fill="both", expand=True)
        
        # Configurar container grid
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)
        
        self.frames = {n: ttk.Frame(self.container) for n in ("login","menu","exam","results")}
        for f in self.frames.values():
            f.grid(row=0, column=0, sticky="nsew")
            f.columnconfigure(0, weight=1)
            f.rowconfigure(0, weight=1)
            
        self._build_login()
        self._build_menu()
        self._build_exam()
        self._build_results()
        self.show("login")

    def show(self, name): 
        self.frames[name].tkraise()

    def _on_window_resize(self, event):
        """Maneja el redimensionamiento de la ventana"""
        if event.widget == self.root:
            new_width = event.width
            # Solo actualizar si hay un cambio significativo de ancho (>50 pixels)
            if abs(new_width - self.current_width) > 50:
                self.current_width = new_width
                # Si estamos en el examen, re-renderizar la página actual
                if hasattr(self, 'exam_indices') and self.exam_indices:
                    self.root.after(100, self._render_exam_page)  # Delay para evitar múltiples calls

    # ---------- LOGIN ----------
    def _build_login(self):
        f = self.frames["login"]
        f.columnconfigure(0, weight=1)
        
        # Frame central para centrar elementos
        center_frame = ttk.Frame(f)
        center_frame.pack(expand=True)
        
        # Título principal
        ttk.Label(center_frame, text="🎯 EXAMEN OPE 🎯", 
                 font=("Helvetica", 20, "bold")).pack(pady=10)
        
        # Frase motivadora
        ttk.Label(center_frame, text="¡Prepárate para triunfar! Cada pregunta es un paso hacia tu éxito.", 
                 font=("Helvetica", 12), foreground="#00D4AA").pack(pady=5)
        
        ttk.Label(center_frame, text="Acceso al Sistema", 
                 font=("Helvetica", 14, "bold")).pack(pady=(20,10))
        
        # Campo Usuario
        ttk.Label(center_frame, text="Usuario:", font=("Helvetica", 10)).pack(anchor="w", padx=20)
        self.entry_user = ttk.Entry(center_frame, width=30, font=("Helvetica", 10))
        self.entry_user.insert(0, DEFAULT_USER)
        self.entry_user.pack(pady=(2,8), padx=20)
        
        # Campo Contraseña
        ttk.Label(center_frame, text="Contraseña:", font=("Helvetica", 10)).pack(anchor="w", padx=20)
        self.entry_pwd = ttk.Entry(center_frame, show="*", width=30, font=("Helvetica", 10))
        self.entry_pwd.pack(pady=(2,8), padx=20)
        
        # Campo Excel
        ttk.Label(center_frame, text="Archivo de preguntas:", font=("Helvetica", 10)).pack(anchor="w", padx=20)
        self.xlsx_var = tk.StringVar(value=DEFAULT_EXCEL)
        ttk.Entry(center_frame, textvariable=self.xlsx_var, width=50, font=("Helvetica", 9)).pack(pady=(2,5), padx=20)
        ttk.Button(center_frame, text="Seleccionar Excel", command=self._select_excel, bootstyle=INFO).pack(pady=5)
        
        # Botón de acceso
        ttk.Button(center_frame, text="🚀 ENTRAR", command=self._on_login, 
                  bootstyle=SUCCESS, width=20).pack(pady=15)

    def _select_excel(self):
        p = filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if p: self.xlsx_var.set(p)

    def _on_login(self):
        if self.entry_pwd.get().strip() != DEFAULT_PASSWORD:
            messagebox.showerror("Acceso","Contraseña incorrecta."); return
        try:
            self.df_questions = load_questions_from_excel(self.xlsx_var.get())
        except Exception as e:
            messagebox.showerror("Error Excel", str(e)); return
        self.show("menu")

    # ---------- MENU ----------
    def _build_menu(self):
        f = self.frames["menu"]
        f.columnconfigure(0, weight=1)
        
        # Frame central para centrar elementos
        center_frame = ttk.Frame(f)
        center_frame.pack(expand=True)
        
        ttk.Label(center_frame, text="📚 MENÚ PRINCIPAL 📚", 
                 font=("Helvetica", 16, "bold")).pack(pady=10)
        
        ttk.Label(center_frame, text="Selecciona una opción para continuar", 
                 font=("Helvetica", 11)).pack(pady=5)
        
        ttk.Button(center_frame, text="🎯 Generar Examen (Gratuito)", 
                  command=self._generate_attempt, bootstyle=PRIMARY, width=30).pack(pady=8)
        ttk.Button(center_frame, text="⭐ Intento Extra", 
                  command=lambda:self._generate_attempt(extra=True), bootstyle=INFO, width=30).pack(pady=8)
        ttk.Button(center_frame, text="📊 Ver Historial", 
                  command=self._goto_results, bootstyle=SECONDARY, width=30).pack(pady=8)

    # ---------- EXAM ----------
    def _build_exam(self):
        f = self.frames["exam"]
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)  # La fila del scroll container se expande

        # Timer arriba
        self.timer_label = ttk.Label(f, text="Tiempo restante: --", font=("Helvetica",12,"bold"))
        self.timer_label.grid(row=0, column=0, pady=5, sticky="ew")

        # Frame contenedor para scroll - SE EXPANDE
        scroll_container = ttk.Frame(f)
        scroll_container.grid(row=1, column=0, sticky="nsew", pady=5)
        scroll_container.columnconfigure(0, weight=1)
        scroll_container.rowconfigure(0, weight=1)

        # Canvas + Scrollbar
        self.canvas = tk.Canvas(scroll_container, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # Frame interno donde van las preguntas
        self.q_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0,0), window=self.q_frame, anchor="nw")

        # Configurar eventos de scroll
        self.q_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # --- Botones de navegación DEBAJO ---
        nav = ttk.Frame(f)
        nav.grid(row=2, column=0, sticky="ew", pady=8)
        nav.columnconfigure(1, weight=1)  # Espacio central expandible

        ttk.Button(nav, text="◀ Anterior", command=self._page_prev).grid(row=0, column=0, padx=5)
        ttk.Button(nav, text="Siguiente ▶", command=self._page_next).grid(row=0, column=2, padx=5)
        ttk.Button(nav, text="✅ ENTREGAR EXAMEN", command=self._on_submit, bootstyle=DANGER).grid(row=0, column=3, padx=5)

        # Paginación
        self.lbl_page = ttk.Label(f, text="Página 0/0", font=("Helvetica", 10))
        self.lbl_page.grid(row=3, column=0, pady=5)

    def _on_frame_configure(self, event):
        """Actualiza el scroll region cuando el frame interno cambia"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Ajusta el ancho del frame interno al ancho del canvas"""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)

    def _calculate_wrap_length(self):
        """Calcula el ancho óptimo para el texto basado en el ancho actual de la ventana"""
        try:
            # Obtener ancho actual del canvas (descontando scrollbar y padding)
            canvas_width = self.canvas.winfo_width()
            if canvas_width <= 1:  # Si no está inicializado, usar ancho de ventana
                canvas_width = self.root.winfo_width() - 100  # Margen para scrollbar y padding
            
            # Descontar márgenes y espacios
            effective_width = max(canvas_width - 80, 400)  # Mínimo 400px
            return effective_width
        except:
            # Fallback en caso de error
            return max(self.root.winfo_width() - 150, 400)

    def _render_exam_page(self):
        """Renderiza la página actual del examen con texto adaptable"""
        # Limpiar contenido anterior
        for w in self.q_frame.winfo_children(): 
            w.destroy()
        
        # Configurar el frame de preguntas para expansión
        self.q_frame.columnconfigure(0, weight=1)
        
        start = self.current_page * QUESTIONS_PER_PAGE
        end = min(start + QUESTIONS_PER_PAGE, EXAM_SIZE)
        self.lbl_page.config(text=f"Página {self.current_page+1}/{self.pages}")
        
        # Calcular ancho de texto adaptable
        wrap_length = self._calculate_wrap_length()
        
        row_counter = 0
        for i in range(start, end):
            if i >= len(self.exam_indices):
                break
                
            row = self.df_questions.iloc[self.exam_indices[i]]
            
            # Frame contenedor para cada pregunta
            question_frame = ttk.Frame(self.q_frame)
            question_frame.grid(row=row_counter, column=0, sticky="ew", pady=8, padx=10)
            question_frame.columnconfigure(0, weight=1)
            
            # Pregunta con texto MÁS GRANDE
            question_text = f"P{i+1}: {row['Pregunta']}"
            question_label = ttk.Label(question_frame, text=question_text, 
                                     wraplength=wrap_length, justify="left",
                                     font=("Helvetica", 11, "bold"))  # Tamaño aumentado
            question_label.grid(row=0, column=0, sticky="ew", pady=(0,8))
            
            # Inicializar variable si no existe
            if i not in self.vars:
                self.vars[i] = tk.StringVar(value=self.answers.get(f"q_{i}", ""))
            
            # Frame para las opciones
            options_frame = ttk.Frame(question_frame)
            options_frame.grid(row=1, column=0, sticky="ew", padx=20)
            options_frame.columnconfigure(0, weight=1)
            
            # Radiobuttons para opciones con texto MÁS PEQUEÑO
            option_row = 0
            for l in "ABCD":
                opt_text = row[f"Respuesta {l}"]
                if pd.notna(opt_text) and str(opt_text).strip():
                    rb = ttk.Radiobutton(options_frame, 
                                       text=f"{l}. {opt_text}", 
                                       value=l, 
                                       variable=self.vars[i],
                                       command=lambda idx=i: self._save_choice(idx))
                    rb.configure(style="Custom.TRadiobutton")
                    rb.grid(row=option_row, column=0, sticky="w", pady=3)
                    option_row += 1
            
            # Separador visual
            separator = ttk.Separator(self.q_frame, orient="horizontal")
            separator.grid(row=row_counter+1, column=0, sticky="ew", pady=5)
            
            row_counter += 2
        
        # Aplicar estilo personalizado para radiobuttons más pequeños
        self.style.configure("Custom.TRadiobutton", font=("Helvetica", 9))
        
        # Actualizar scroll region
        self.q_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _save_choice(self, idx): 
        self.answers[f"q_{idx}"] = self.vars[idx].get()
        
    def _page_prev(self): 
        if self.current_page > 0: 
            self.current_page -= 1
            self._render_exam_page()
            
    def _page_next(self): 
        if self.current_page < self.pages - 1: 
            self.current_page += 1
            self._render_exam_page()

    # ---------- GENERATE ----------
    def _generate_attempt(self, extra=False):
        total = len(self.df_questions)
        if EXAM_SIZE > total:
            messagebox.showerror("Error","EXAM_SIZE mayor al total de preguntas."); return
        self.exam_indices = random.sample(range(total), EXAM_SIZE)
        self.answers = {f"q_{i}": None for i in range(EXAM_SIZE)}
        self.vars = {}
        self.current_page, self.pages = 0, math.ceil(EXAM_SIZE/QUESTIONS_PER_PAGE)
        
        # Timer
        self.start_time = datetime.now()
        self.time_left = EXAM_DURATION_SECONDS
        self._update_timer()
        
        self.show("exam")
        
        # Renderizar después de mostrar la ventana para tener medidas correctas
        self.root.after(100, self._render_exam_page)

    def _update_timer(self):
        mins, secs = divmod(self.time_left, 60)
        self.timer_label.config(text=f"⏰ Tiempo restante: {mins:02d}:{secs:02d}")
        if self.time_left > 0:
            self.time_left -= 1
            self.root.after(1000, self._update_timer)
        else:
            messagebox.showinfo("Tiempo agotado", "⏰ Se acabó el tiempo, entregando examen automáticamente.")
            self._on_submit()

    # ---------- SUBMIT ----------
    def _on_submit(self):
        correct, wrong = [], []
        for i in range(len(self.exam_indices)):
            real = str(self.df_questions.iloc[self.exam_indices[i]]["Respuesta Correcta (Letra)"]).strip().upper()
            ans = self.answers.get(f"q_{i}")
            if ans == real: 
                correct.append(i)
            else: 
                wrong.append(i)
        
        score = len(correct) * 0.1
        record_attempt(DEFAULT_USER, score, len(correct), len(wrong))
        
        self.last_score = score
        self.last_correct = len(correct)
        self.last_wrong = wrong
        
        # MOSTRAR VENTANA DE RESULTADOS INMEDIATOS
        self._show_immediate_results(len(correct), len(wrong), score)
        
        self._render_results_page()
        self.show("results")

    def _show_immediate_results(self, correct_count, wrong_count, score):
        """Muestra ventana inmediata con los resultados del examen"""
        # Crear ventana modal
        result_window = tk.Toplevel(self.root)
        result_window.title("🎉 Resultados del Examen")
        result_window.geometry("500x300")
        result_window.resizable(False, False)
        
        # Centrar ventana
        result_window.transient(self.root)
        result_window.grab_set()
        
        # Configurar estilo
        main_frame = ttk.Frame(result_window, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        # Título
        ttk.Label(main_frame, text="🎯 EXAMEN COMPLETADO 🎯", 
                 font=("Helvetica", 16, "bold")).pack(pady=10)
        
        # Marco con resultados
        results_frame = ttk.LabelFrame(main_frame, text=" Resultados ", padding=15)
        results_frame.pack(fill="x", pady=10)
        
        # Puntuación principal
        score_text = f"📊 PUNTUACIÓN FINAL: {score:.1f} puntos"
        ttk.Label(results_frame, text=score_text, 
                 font=("Helvetica", 14, "bold")).pack(pady=5)
        
        # Detalles
        ttk.Label(results_frame, text=f"✅ Preguntas acertadas: {correct_count}", 
                 font=("Helvetica", 12), foreground="green").pack(pady=2)
        ttk.Label(results_frame, text=f"❌ Preguntas falladas: {wrong_count}", 
                 font=("Helvetica", 12), foreground="red").pack(pady=2)
        ttk.Label(results_frame, text=f"📝 Total de preguntas: {correct_count + wrong_count}", 
                 font=("Helvetica", 12)).pack(pady=2)
        
        # Porcentaje
        percentage = (correct_count / (correct_count + wrong_count)) * 100 if (correct_count + wrong_count) > 0 else 0
        ttk.Label(results_frame, text=f"📈 Porcentaje de acierto: {percentage:.1f}%", 
                 font=("Helvetica", 12), foreground="blue").pack(pady=5)
        
        # Mensaje motivacional
        if percentage >= 80:
            message = "🎉 ¡EXCELENTE! Muy buen rendimiento"
            color = "green"
        elif percentage >= 60:
            message = "👍 ¡BIEN! Sigue mejorando"
            color = "orange"
        else:
            message = "💪 ¡ÁNIMO! La práctica hace al maestro"
            color = "red"
            
        ttk.Label(results_frame, text=message, 
                 font=("Helvetica", 11, "bold"), foreground=color).pack(pady=8)
        
        # Botón para continuar
        ttk.Button(main_frame, text="📋 Ver Detalles Completos", 
                  command=result_window.destroy, bootstyle=PRIMARY).pack(pady=15)
        
        # Centrar la ventana en la pantalla
        result_window.update_idletasks()
        x = (result_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (result_window.winfo_screenheight() // 2) - (300 // 2)
        result_window.geometry(f"500x300+{x}+{y}")

    # ---------- RESULTS ----------
    def _build_results(self):
        f = self.frames["results"]
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)  # Graph frame se expande
        
        self.res_label = ttk.Label(f, text="", font=("Helvetica",14,"bold"))
        self.res_label.grid(row=0, column=0, pady=6)
        
        # Text widget con scroll
        text_frame = ttk.Frame(f)
        text_frame.grid(row=1, column=0, sticky="ew", pady=4)
        text_frame.columnconfigure(0, weight=1)
        
        self.wrong_box = tk.Text(text_frame, width=120, height=15, wrap=tk.WORD)
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.wrong_box.yview)
        self.wrong_box.configure(yscrollcommand=text_scroll.set)
        
        self.wrong_box.grid(row=0, column=0, sticky="ew")
        text_scroll.grid(row=0, column=1, sticky="ns")
        
        ttk.Button(f, text="📄 Exportar PDF", command=self._export_pdf, bootstyle=INFO).grid(row=3, column=0, pady=6)
        
        self.graph_frame = ttk.Frame(f)
        self.graph_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        self.graph_frame.columnconfigure(0, weight=1)
        self.graph_frame.rowconfigure(0, weight=1)
        
        ttk.Button(f, text="🏠 Volver al Menú", command=lambda:self.show("menu")).grid(row=4, column=0, pady=6)

    def _render_results_page(self):
        self.res_label.config(text=f"📊 Puntuación Final: {self.last_score:.1f} puntos | ✅ {self.last_correct} aciertos | ❌ {len(self.last_wrong)} fallos")
        self.wrong_box.delete("1.0","end")
        
        if self.last_wrong:
            self.wrong_box.insert("end", "❌ PREGUNTAS FALLADAS:\n\n")
            for i in self.last_wrong:
                if i < len(self.exam_indices):
                    row = self.df_questions.iloc[self.exam_indices[i]]
                    self.wrong_box.insert("end", f"P{i+1}: {row['Pregunta']}\n")
                    self.wrong_box.insert("end", f"✅ Respuesta correcta: {row['Respuesta Correcta (Texto)']}\n")
                    chosen = self.answers.get(f"q_{i}", "No contestada")
                    self.wrong_box.insert("end", f"❌ Tu respuesta: {chosen}\n")
                    self.wrong_box.insert("end", "-" * 80 + "\n\n")
        else:
            self.wrong_box.insert("end", "🎉 ¡PERFECTO! No hay preguntas falladas. ¡Excelente trabajo!\n")
            
        self._render_graphs()

    def _render_graphs(self):
        for w in self.graph_frame.winfo_children(): w.destroy()
        data = get_attempts(DEFAULT_USER)
        if not data: return
        df = pd.DataFrame(data, columns=["id","user","day","timestamp","score","correct","wrong"])
        fig, axes = plt.subplots(1,2, figsize=(12,5))
        df.plot(x="timestamp", y="score", ax=axes[0], marker="o", legend=False, title="Evolución de puntuaciones")
        axes[0].set_ylabel("Score")
        df[["correct","wrong"]].plot(kind="bar", stacked=True, ax=axes[1], title="Aciertos vs Fallos")
        plt.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _export_pdf(self):
        try:
            start_ts = self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "N/A"
            end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            path = os.path.join(DATA_DIR, f"informe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            
            # Crear DataFrame solo con las preguntas del examen actual
            exam_questions_df = self.df_questions.iloc[self.exam_indices].reset_index(drop=True)
            
            generate_pdf_report(path, DEFAULT_USER, exam_questions_df, self.answers,
                                self.last_score, [], self.last_wrong, start_ts, end_ts)
            messagebox.showinfo("PDF Generado", f"✅ Informe guardado correctamente en:\n{path}")
        except Exception as e:
            messagebox.showerror("Error PDF", f"❌ Error al generar PDF:\n{str(e)}")

    def _goto_results(self): 
        self.show("results")

# ----------------- RUN -----------------
def main():
    ensure_data_dir()
    root = tb.Window(themename="superhero")
    # Tamaño dinámico: 90% pantalla
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{int(sw*0.9)}x{int(sh*0.9)}")
    
    # Configurar ventana para redimensionamiento
    root.minsize(800, 600)  # Tamaño mínimo
    
    ExamApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()