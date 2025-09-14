import streamlit as st
import pandas as pd
import sqlite3
import os
import random
import math
from datetime import datetime, date
import matplotlib.pyplot as plt
from fpdf import FPDF
import base64
import time

# Configuración
st.set_page_config(
    page_title="Examen OPE",
    page_icon="🎯",
    layout="wide"
)

# Constantes
DATA_DIR = "data"
DEFAULT_EXCEL = os.path.join(DATA_DIR, "cuestionario_procesado.xlsx")
DB_FILE = os.path.join(DATA_DIR, "exam_attempts.db")
DEFAULT_PASSWORD = "OPE_ Vane_01"
EXAM_SIZE = 100
QUESTIONS_PER_PAGE = 20
EXAM_DURATION_SECONDS = 90 * 60

# Funciones auxiliares
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

def load_questions_from_excel(path):
    if not os.path.exists(path):
        # Crear archivo de ejemplo si no existe
        df = pd.DataFrame({
            'Pregunta': [
                '¿Cuál es la capital de España?',
                '¿2+2 es igual a?',
                '¿En qué año se descubrió América?',
                '¿Cuál es el planeta más grande del sistema solar?'
            ] * 50,  # Repetir para tener suficientes preguntas
            'Respuesta A': ['Madrid', '3', '1491', 'Júpiter'] * 50,
            'Respuesta B': ['Barcelona', '4', '1492', 'Saturno'] * 50,
            'Respuesta C': ['Valencia', '5', '1493', 'Neptuno'] * 50,
            'Respuesta D': ['Sevilla', '6', '1494', 'Urano'] * 50,
            'Respuesta Correcta (Letra)': ['A', 'B', 'B', 'A'] * 50,
            'Respuesta Correcta (Texto)': ['Madrid', '4', '1492', 'Júpiter'] * 50
        })
        ensure_data_dir()
        df.to_excel(path, index=False)
        return df
    
    df = pd.read_excel(path, engine="openpyxl")
    expected = ["Pregunta","Respuesta A","Respuesta B","Respuesta C","Respuesta D","Respuesta Correcta (Letra)","Respuesta Correcta (Texto)"]
    for c in expected:
        if c not in df.columns:
            raise ValueError(f"Columna faltante: {c}")
    return df.reset_index(drop=True)

def record_attempt(user, score, correct, wrong):
    conn = get_db_conn()
    cur = conn.cursor()
    day = date.today().isoformat()
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    cur.execute("INSERT INTO attempts (user, day, timestamp, score, correct, wrong) VALUES (?, ?, ?, ?, ?, ?)",
                (user, day, ts, score, correct, wrong))
    conn.commit()
    conn.close()

def get_attempts(user):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM attempts WHERE user=? ORDER BY timestamp", (user,))
    data = cur.fetchall()
    conn.close()
    return data

def generate_pdf_report(user, exam_df, answers_dict, score, correct_count, wrong_list, start_time, end_time):
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
    pdf.cell(0, 8, f"Aciertos: {correct_count}  Fallos: {len(wrong_list)}", ln=1)
    pdf.ln(5)
    
    if wrong_list:
        pdf.set_font("Arial", style="B", size=11)
        pdf.cell(0, 8, "PREGUNTAS FALLADAS:", ln=1)
        pdf.ln(3)
        
        pdf.set_font("Arial", size=9)
        for i in wrong_list:
            if i < len(exam_df):
                row = exam_df.iloc[i]
                q_text = str(row["Pregunta"])[:200]
                if len(str(row["Pregunta"])) > 200:
                    q_text += "..."
                
                corr_text = str(row["Respuesta Correcta (Texto)"])[:100]
                if len(str(row["Respuesta Correcta (Texto)"])) > 100:
                    corr_text += "..."
                
                chosen = answers_dict.get(f"q_{i}", "No contestada")
                
                pdf.set_font("Arial", style="B", size=9)
                pdf.multi_cell(0, 4, f"P{i+1}: {q_text}")
                
                pdf.set_font("Arial", size=8)
                pdf.multi_cell(0, 4, f"Tu respuesta: {chosen}")
                pdf.multi_cell(0, 4, f"Correcta: {corr_text}")
                pdf.ln(3)
    
    # Guardar en memoria
    return pdf.output(dest='S').encode('latin-1')

# Inicializar session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'login'
if 'exam_active' not in st.session_state:
    st.session_state.exam_active = False
if 'questions' not in st.session_state:
    st.session_state.questions = None
if 'exam_indices' not in st.session_state:
    st.session_state.exam_indices = []
if 'answers' not in st.session_state:
    st.session_state.answers = {}
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
if 'current_question_page' not in st.session_state:
    st.session_state.current_question_page = 0

# CSS personalizado
st.markdown("""
<style>
.big-title {
    font-size: 2.5rem;
    font-weight: bold;
    text-align: center;
    color: #1f77b4;
    margin-bottom: 1rem;
}
.motivational {
    font-size: 1.2rem;
    text-align: center;
    color: #2e8b57;
    margin-bottom: 2rem;
    font-style: italic;
}
.question-title {
    font-size: 1.1rem;
    font-weight: bold;
    color: #333;
    margin-bottom: 0.5rem;
}
.timer {
    font-size: 1.5rem;
    font-weight: bold;
    color: #ff4b4b;
    text-align: center;
    background-color: #f0f0f0;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# Función principal
def main():
    if st.session_state.current_page == 'login':
        show_login()
    elif st.session_state.current_page == 'menu':
        show_menu()
    elif st.session_state.current_page == 'exam':
        show_exam()
    elif st.session_state.current_page == 'results':
        show_results()

def show_login():
    st.markdown('<div class="big-title">🎯 EXAMEN OPE 🎯</div>', unsafe_allow_html=True)
    st.markdown('<div class="motivational">¡Prepárate para triunfar! Cada pregunta es un paso hacia tu éxito.</div>', unsafe_allow_html=True)
    
    st.subheader("Acceso al Sistema")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        user = st.text_input("Usuario:", value="Vanessa")
        password = st.text_input("Contraseña:", type="password")
        
        uploaded_file = st.file_uploader("Cargar archivo Excel (opcional)", type=['xlsx'])
        
        if st.button("🚀 ENTRAR", use_container_width=True):
            if password.strip() == DEFAULT_PASSWORD:
                st.session_state.authenticated = True
                st.session_state.user = user
                
                # Cargar preguntas
                try:
                    if uploaded_file:
                        st.session_state.questions = pd.read_excel(uploaded_file)
                    else:
                        st.session_state.questions = load_questions_from_excel(DEFAULT_EXCEL)
                    st.session_state.current_page = 'menu'
                    st.rerun()
                except Exception as e:
                    st.error(f"Error cargando preguntas: {str(e)}")
            else:
                st.error("Contraseña incorrecta")

def show_menu():
    st.markdown('<div class="big-title">📚 MENÚ PRINCIPAL 📚</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align: center; margin-bottom: 2rem;">Selecciona una opción para continuar</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🎯 Generar Examen (Gratuito)", use_container_width=True):
            generate_exam()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("⭐ Intento Extra", use_container_width=True):
            generate_exam(extra=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("📊 Ver Historial", use_container_width=True):
            st.session_state.current_page = 'results'
            st.rerun()

def generate_exam(extra=False):
    total = len(st.session_state.questions)
    if EXAM_SIZE > total:
        st.error("No hay suficientes preguntas para generar el examen")
        return
    
    st.session_state.exam_indices = random.sample(range(total), EXAM_SIZE)
    st.session_state.answers = {}
    st.session_state.start_time = datetime.now()
    st.session_state.exam_active = True
    st.session_state.current_question_page = 0
    st.session_state.current_page = 'exam'
    st.rerun()

def show_exam():
    if not st.session_state.exam_active:
        st.session_state.current_page = 'menu'
        st.rerun()
        return
    
    # Timer
    elapsed = (datetime.now() - st.session_state.start_time).total_seconds()
    remaining = max(0, EXAM_DURATION_SECONDS - elapsed)
    
    if remaining <= 0:
        submit_exam()
        return
    
    mins, secs = divmod(int(remaining), 60)
    st.markdown(f'<div class="timer">⏰ Tiempo restante: {mins:02d}:{secs:02d}</div>', unsafe_allow_html=True)
    
    # Auto-refresh cada 30 segundos para actualizar timer
    time.sleep(1)
    st.rerun()
    
    # Paginación de preguntas
    total_pages = math.ceil(EXAM_SIZE / QUESTIONS_PER_PAGE)
    current_page = st.session_state.current_question_page
    
    st.subheader(f"Página {current_page + 1} de {total_pages}")
    
    # Mostrar preguntas de la página actual
    start_idx = current_page * QUESTIONS_PER_PAGE
    end_idx = min(start_idx + QUESTIONS_PER_PAGE, EXAM_SIZE)
    
    for i in range(start_idx, end_idx):
        if i >= len(st.session_state.exam_indices):
            break
            
        row = st.session_state.questions.iloc[st.session_state.exam_indices[i]]
        
        st.markdown(f'<div class="question-title">P{i+1}: {row["Pregunta"]}</div>', unsafe_allow_html=True)
        
        options = []
        for letter in ['A', 'B', 'C', 'D']:
            option_text = row[f"Respuesta {letter}"]
            if pd.notna(option_text) and str(option_text).strip():
                options.append(f"{letter}. {option_text}")
        
        # Radio button para la pregunta
        selected = st.radio(
            f"Selecciona tu respuesta para la pregunta {i+1}:",
            options,
            key=f"q_{i}",
            index=None
        )
        
        if selected:
            st.session_state.answers[f"q_{i}"] = selected[0]  # Guardar solo la letra
        
        st.markdown("---")
    
    # Botones de navegación
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        if current_page > 0 and st.button("◀ Anterior"):
            st.session_state.current_question_page -= 1
            st.rerun()
    
    with col2:
        if current_page < total_pages - 1 and st.button("Siguiente ▶"):
            st.session_state.current_question_page += 1
            st.rerun()
    
    with col4:
        if st.button("✅ ENTREGAR EXAMEN", type="primary"):
            submit_exam()

def submit_exam():
    correct, wrong = [], []
    
    for i in range(len(st.session_state.exam_indices)):
        row = st.session_state.questions.iloc[st.session_state.exam_indices[i]]
        real = str(row["Respuesta Correcta (Letra)"]).strip().upper()
        ans = st.session_state.answers.get(f"q_{i}")
        
        if ans == real:
            correct.append(i)
        else:
            wrong.append(i)
    
    score = len(correct) * 0.1
    
    # Guardar en base de datos
    record_attempt(st.session_state.user, score, len(correct), len(wrong))
    
    # Guardar resultados en session state
    st.session_state.last_score = score
    st.session_state.last_correct = len(correct)
    st.session_state.last_wrong = wrong
    st.session_state.exam_active = False
    
    # Mostrar resultados inmediatos
    show_immediate_results(len(correct), len(wrong), score)
    
    st.session_state.current_page = 'results'

def show_immediate_results(correct_count, wrong_count, score):
    st.balloons()
    
    st.markdown('<div class="big-title">🎉 EXAMEN COMPLETADO 🎉</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.success(f"📊 PUNTUACIÓN FINAL: {score:.1f} puntos")
        
        st.metric("✅ Preguntas acertadas", correct_count)
        st.metric("❌ Preguntas falladas", wrong_count)
        st.metric("📝 Total de preguntas", correct_count + wrong_count)
        
        percentage = (correct_count / (correct_count + wrong_count)) * 100 if (correct_count + wrong_count) > 0 else 0
        st.metric("📈 Porcentaje de acierto", f"{percentage:.1f}%")
        
        # Mensaje motivacional
        if percentage >= 80:
            st.success("🎉 ¡EXCELENTE! Muy buen rendimiento")
        elif percentage >= 60:
            st.info("👍 ¡BIEN! Sigue mejorando")
        else:
            st.warning("💪 ¡ÁNIMO! La práctica hace al maestro")
        
        if st.button("📋 Ver Detalles Completos", use_container_width=True):
            st.rerun()

def show_results():
    st.title("📊 Resultados del Examen")
    
    if hasattr(st.session_state, 'last_score'):
        st.subheader(f"Puntuación Final: {st.session_state.last_score:.1f} puntos | ✅ {st.session_state.last_correct} aciertos | ❌ {len(st.session_state.last_wrong)} fallos")
        
        # Mostrar preguntas falladas
        if st.session_state.last_wrong:
            st.subheader("❌ PREGUNTAS FALLADAS:")
            
            for i in st.session_state.last_wrong:
                if i < len(st.session_state.exam_indices):
                    row = st.session_state.questions.iloc[st.session_state.exam_indices[i]]
                    
                    with st.expander(f"P{i+1}: {row['Pregunta'][:100]}..."):
                        st.write(f"**Pregunta completa:** {row['Pregunta']}")
                        st.write(f"**✅ Respuesta correcta:** {row['Respuesta Correcta (Texto)']}")
                        chosen = st.session_state.answers.get(f"q_{i}", "No contestada")
                        st.write(f"**❌ Tu respuesta:** {chosen}")
        else:
            st.success("🎉 ¡PERFECTO! No hay preguntas falladas. ¡Excelente trabajo!")
        
        # Generar PDF
        if st.button("📄 Exportar PDF"):
            try:
                start_ts = st.session_state.start_time.strftime("%Y-%m-%d %H:%M:%S")
                end_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                exam_questions_df = st.session_state.questions.iloc[st.session_state.exam_indices].reset_index(drop=True)
                
                pdf_bytes = generate_pdf_report(
                    st.session_state.user, 
                    exam_questions_df, 
                    st.session_state.answers,
                    st.session_state.last_score, 
                    st.session_state.last_correct,
                    st.session_state.last_wrong, 
                    start_ts, 
                    end_ts
                )
                
                st.download_button(
                    label="📥 Descargar Informe PDF",
                    data=pdf_bytes,
                    file_name=f"informe_examen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
                st.success("✅ PDF generado correctamente")
            except Exception as e:
                st.error(f"❌ Error al generar PDF: {str(e)}")
    
    # Mostrar historial
    st.subheader("📈 Historial de Intentos")
    data = get_attempts(st.session_state.user)
    
    if data:
        df = pd.DataFrame(data, columns=["ID", "Usuario", "Día", "Timestamp", "Score", "Correctas", "Incorrectas"])
        st.dataframe(df)
        
        # Gráfico de evolución
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Evolución de puntuaciones
        ax1.plot(range(len(df)), df['Score'], marker='o')
        ax1.set_title('Evolución de Puntuaciones')
        ax1.set_ylabel('Score')
        ax1.set_xlabel('Intento')
        
        # Aciertos vs Fallos
        ax2.bar(range(len(df)), df['Correctas'], label='Correctas', alpha=0.7)
        ax2.bar(range(len(df)), df['Incorrectas'], bottom=df['Correctas'], label='Incorrectas', alpha=0.7)
        ax2.set_title('Aciertos vs Fallos')
        ax2.set_ylabel('Número de preguntas')
        ax2.set_xlabel('Intento')
        ax2.legend()
        
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.info("No hay intentos previos registrados")
    
    if st.button("🏠 Volver al Menú"):
        st.session_state.current_page = 'menu'
        st.rerun()

if __name__ == "__main__":
    main()