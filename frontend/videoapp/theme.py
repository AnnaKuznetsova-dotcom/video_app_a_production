"""Тема оформления (Open Design): CSS, подписи признаков, ассеты и сегменты.

Нижний слой пакета videoapp: от него зависят все остальные модули,
а сам он не импортирует ничего из проекта (только Streamlit).
"""

import base64
import os

import streamlit as st

# Каталог ассетов лежит в frontend/, т.е. на уровень выше пакета videoapp.
_FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(_FRONTEND_DIR, "assets")


def asset(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


@st.cache_data(show_spinner=False)
def _b64_uri(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "jpeg"
        uri = f"data:image/{ext};base64,{data}"
    except Exception:
        uri = ""
    return uri


_TOKEN_RU = {
    "missing": "без ответа",
    "white_box": "white box",
}


def _feature_label(name: str) -> str:
    if "__" in name:
        mid = name.split("__", 1)[1]
    else:
        mid = name
    for k, v in _TOKEN_RU.items():
        if k in mid:
            mid = mid.replace(k, v)
    label = mid.replace("_", " ").strip()
    return label[:1].upper() + label[1:] if label else label


def _hourglass_html() -> str:
    bg = "bg_05.jpg"
    for cand in (bg, "bg_04.jpg", "kaskad_1.jpg", "bg_01.jpg"):
        if os.path.exists(asset(cand)):
            bg = cand
            break
    uri = _b64_uri(asset(bg))
    return (
        f'<div class="hourglass" style="background-image:url(\'{uri}\')">'
        f'<div class="overlay"></div>'
        f'<div class="glass">⏳</div>'
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Сегменты ролика: стандартные длительности по категориям (см. video_views).
# ---------------------------------------------------------------------------
_SEGMENT_DUR_S = {
    "общий вид": 5,
    "few_cat__есть_ли_дети": 4,  # наличие детей
    "bin_num__отделка": 4,  # отделка
    "bin_num__квартира_планировка": 5,  # планировка
    "bin_num__приоритеты": 5,  # приоритеты
}
_OVERALL_DUR_S = 5


# ---------------------------------------------------------------------------
# DESIGN: CSS Open Design
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');

:root {
  --k-green: #168e38; --k-green-deep: #26512d; --k-green-dark: #137922;
  --k-gold: #ffb13e; --k-base: #373737; --k-dark: #3a3b3f;
  --k-light: #f2f4f7; --k-gray: #e7ebf0; --k-medium: #697180; --k-white: #ffffff;
  --ink: #2d2f33; --muted: #6a6f78; --line: #e7ebf0;
}
html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
section.main > div.block-container { padding-top: 1.1rem; max-width: 1200px; }
.stApp { background: #ffffff; }

/* Hero */
.k-hero {
  border-radius: 32px; overflow: hidden; position: relative;
  color: #fff; padding: 64px 52px 56px; margin-bottom: 8px;
  background-size: cover; background-position: center;
}
.k-hero .overlay {
  position: absolute; inset: 0;
  background: linear-gradient(105deg, rgba(38,81,45,0.94) 0%, rgba(22,142,56,0.72) 55%, rgba(22,142,56,0.30) 100%);
}
.k-hero .inner { position: relative; z-index: 2; }
.k-hero h1 { font-size: clamp(30px, 4.2vw, 48px); font-weight: 700; line-height: 1.08;
             letter-spacing: -0.02em; margin: 18px 0; color: #fff !important; }
.k-hero h1 em { font-style: normal; color: var(--k-gold); }
.k-hero p.lead { font-size: 17px; line-height: 1.55; opacity: 0.94; max-width: 640px; }
.k-badge {
  display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 16px;
  border-radius: 100px; background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.35);
  font-size: 12.5px; font-weight: 500; color: #fff;
}
.k-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--k-gold); }
.k-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; margin-top: 36px; max-width: 520px; }
.k-stat .num { font-size: 27px; font-weight: 700; color: var(--k-gold); }
.k-stat .label { font-size: 13px; opacity: 0.85; }

/* Section titles */
.k-section-title { text-align: center; margin: 44px 0 26px; }
.k-section-title h2 { font-size: clamp(24px, 3.2vw, 36px); font-weight: 700; color: var(--k-green-deep); margin-bottom: 8px; }
.k-section-title .underline { display: block; width: 64px; height: 5px; margin: 12px auto 14px; border-radius: 100px; background: var(--k-gold); }
.k-section-title p { color: var(--k-medium); font-size: 15.5px; }

/* Values */
.k-value { background: #fff; border-radius: 16px; padding: 0 0 20px; border: 1px solid var(--k-gray);
           box-shadow: 0 2px 8px rgba(58,59,63,0.06); height: 100%; overflow: hidden; }
.k-value img.card-img { width: 100%; height: 148px; object-fit: cover; display: block; }
.k-value .v-body { padding: 16px 20px 0; }
.k-value h3 { font-size: 17px; font-weight: 700; color: var(--k-green-deep); margin-bottom: 6px; }
.k-value p { font-size: 14px; color: var(--k-base); opacity: 0.85; line-height: 1.5; margin: 0; }

/* Steps */
.k-step { background: #fff; border-radius: 16px; border: 1px solid var(--k-gray);
          box-shadow: 0 2px 8px rgba(58,59,63,0.06); height: 100%; overflow: hidden; }
.k-step img.step-img { width: 100%; height: 138px; object-fit: cover; display: block; }
.k-step .step-body { padding: 18px 22px 22px; }
.k-step .step-num {
  width: 34px; height: 34px; border-radius: 50%; background: var(--k-green); color: #fff;
  font-weight: 700; display: grid; place-items: center; font-size: 15px; margin-bottom: 10px;
  box-shadow: 0 4px 12px rgba(22,142,56,0.35);
}
.k-step h3 { font-size: 17px; font-weight: 700; color: var(--k-green-deep); margin-bottom: 6px; }
.k-step p { font-size: 14px; color: var(--k-base); opacity: 0.85; line-height: 1.5; margin: 0; }

/* Projects */
.proj-card-od { background: #fff; border-radius: 16px; border: 1px solid var(--k-gray);
  box-shadow: 0 2px 8px rgba(58,59,63,0.06); height: 100%; overflow: hidden;
  display: flex; flex-direction: column; transition: transform .18s ease, box-shadow .18s ease; }
.proj-link:hover .proj-card-od { transform: translateY(-3px); box-shadow: 0 14px 30px rgba(23,32,46,0.16); }
.proj-card-od img.p-img { width: 100%; height: 138px; object-fit: cover; display: block; }
.proj-card-od .p-body { padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 7px; flex: 1; }
.proj-card-od h4 { margin: 0; font-size: 15.5px; font-weight: 700; color: var(--k-green-deep); }
.proj-card-od .p-loc { font-size: 12.5px; color: var(--k-green); margin: 0; font-weight: 600; }
.proj-card-od .p-features { font-size: 11px; color: var(--k-green); opacity: .92; margin: 0; line-height: 1.45; }
.proj-card-od .p-chip {
  display: inline-flex; align-items: center; gap: 6px; align-self: flex-start;
  padding: 5px 11px; border-radius: 100px; background: rgba(255,177,62,0.12);
  border: 1px solid rgba(255,177,62,0.35); color: #b37516;
  font-size: 12px; font-weight: 700; margin-top: auto;
}
.proj-card-od .p-chip.k-alt { background: rgba(255,177,62,0.12); border-color: rgba(255,177,62,0.35); color: #b37516; }

/* Quiz */
.k-quiz-shell { background: rgba(22,142,56,0.06); border-radius: 28px; padding: 28px 24px; }
.k-question h3 { font-size: clamp(19px, 2.6vw, 24px); font-weight: 700; color: var(--k-green-deep); margin-bottom: 4px; }
.k-question .hint { color: var(--k-medium); font-size: 13.5px; margin-bottom: 10px; }

/* Right progress rail — sticky (ancestors stretched) */
div[data-testid="stColumn"]:has(div.k-rail) { display: flex; flex-direction: column; }
div[data-testid="stColumn"]:has(div.k-rail) > div { display: flex; flex-direction: column; flex: 1 1 auto; }
div[data-testid="stColumn"]:has(div.k-rail) div[data-testid="stElementContainer"] { flex: 1 1 auto; display: flex; flex-direction: column; }
div[data-testid="stColumn"]:has(div.k-rail) div[data-testid="stHtml"] { flex: 1 1 auto; display: flex; flex-direction: column; }
.k-rail-wrap { position: sticky; top: max(84px, calc(50vh - 230px)); }
.k-rail { background: #fff; border-radius: 18px; border: 1px solid var(--k-gray);
          box-shadow: 0 8px 24px rgba(58,59,63,0.10); padding: 18px 16px;
          max-height: calc(100vh - 130px); overflow: auto; }
.k-rail h4 { margin: 0 0 10px; font-size: 14px; color: var(--k-green-deep); font-weight: 700; }
.k-rail .k-track { height: 7px; background: var(--k-gray); border-radius: 100px; overflow: hidden; margin-bottom: 5px; }
.k-rail .k-track > div { height: 100%; background: linear-gradient(90deg, var(--k-green), var(--k-green-dark)); border-radius: 100px; }
.k-rail .k-count { font-size: 11.5px; color: var(--k-medium); margin-bottom: 10px; }
.k-rail-item { display: flex; align-items: center; gap: 9px; padding: 3px 0; }
.k-rail-item .pi {
  flex: none; width: 21px; height: 21px; border-radius: 50%; display: grid; place-items: center;
  font-size: 10.5px; font-weight: 700; border: 2px solid #cccedb; color: var(--k-medium); background: #fff;
}
.k-rail-item.current .pi { border-color: var(--k-gold); color: #b37516; background: rgba(255,177,62,0.15); box-shadow: 0 0 0 3px rgba(255,177,62,0.15); }
.k-rail-item.done .pi { border-color: var(--k-green); background: var(--k-green); color: #fff; }
.k-rail-item .pt { font-size: 12px; color: var(--k-medium); }
.k-rail-item.done .pt { color: var(--k-green-deep); font-weight: 600; }
.k-rail-item.current .pt { color: var(--k-dark); font-weight: 600; }

/* Result hero */
.k-result-hero {
  background: linear-gradient(105deg, rgba(38,81,45,0.96), rgba(22,142,56,0.85)), var(--k-green-deep);
  color: #fff; border-radius: 22px; padding: 34px; margin-bottom: 28px; overflow: hidden;
}
.k-result-hero h2 { font-size: clamp(21px, 2.6vw, 30px); font-weight: 700; color: #fff; margin-bottom: 10px; }
.k-result-hero h2 .village { color: var(--k-gold); }
.k-result-hero p { opacity: 0.9; font-size: 15px; margin-bottom: 0; }
.k-chips { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 0; }
.k-chip {
  padding: 8px 14px; border-radius: 100px; background: rgba(255,255,255,0.14);
  border: 1px solid rgba(255,255,255,0.25); font-size: 12.5px; font-weight: 500; color: #fff;
}

/* SHAP cards */
.k-shap-card { background: #fff; border-radius: 18px; padding: 22px; border: 1px solid var(--k-gray); box-shadow: 0 8px 22px rgba(58,59,63,0.08); height: 100%; }
.k-shap-card h3 { font-size: 19px; font-weight: 700; color: var(--k-green-deep); margin-bottom: 4px; }
.k-shap-card .sub { color: var(--k-medium); font-size: 13px; margin-bottom: 16px; }
.k-shap-row { display: grid; grid-template-columns: 170px 1fr 56px; gap: 10px; align-items: center; margin: 9px 0; }
.k-shap-label { font-size: 12.5px; font-weight: 600; color: var(--k-dark); text-align: right; }
.k-shap-track { height: 22px; background: var(--k-gray); border-radius: 100px; overflow: hidden; }
.k-shap-bar { height: 100%; border-radius: 100px; background: linear-gradient(90deg, var(--k-green), #7bad83); min-width: 4px; }
.k-shap-value { font-size: 12px; font-weight: 700; color: var(--k-green-deep); }
.k-cmp-name-w { color: var(--k-green); font-size: 13.5px; font-weight: 700; }
.k-cmp-name-r { color: #b37516; font-size: 13.5px; font-weight: 700; text-align: right; }
.k-cmp-label { font-size: 12px; font-weight: 600; color: var(--k-dark); text-align: center; }
.k-cmp-track { position: relative; height: 26px; background: var(--k-gray); border-radius: 100px; overflow: hidden; }
.k-cmp-center { position: absolute; top: 0; bottom: 0; left: 50%; width: 2px; background: var(--k-dark); opacity: 0.2; }
.k-cmp-bar { position: absolute; top: 4px; bottom: 4px; border-radius: 100px; }
.k-cmp-bar.winner { left: 50%; background: linear-gradient(90deg, var(--k-green), #7bad83); }
.k-cmp-bar.runner { right: 50%; background: linear-gradient(270deg, var(--k-gold), #ffd58a); }

/* Video card */
.k-video-tag { display: inline-block; padding: 5px 12px; border-radius: 100px; font-size: 12px; font-weight: 700;
  background: var(--k-green); color: #fff; margin: 0 0 8px; }
.k-imp-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px; }
.k-chip-imp { padding: 6px 13px; border-radius: 100px; background: rgba(22,142,56,0.08);
  border: 1px solid rgba(22,142,56,0.25); color: var(--k-green-deep); font-size: 12.5px; font-weight: 600; }

/* Hourglass */
.hourglass {
  position: relative; border-radius: 14px; overflow: hidden; height: 92px;
  background-size: cover; background-position: center;
  display: flex; align-items: center; justify-content: center; margin: 8px 0;
}
.hourglass .overlay { position: absolute; inset: 0; background: linear-gradient(120deg, rgba(13,40,22,0.52) 0%, rgba(22,142,56,0.30) 100%); }
.hourglass .glass {
  position: relative; z-index: 2; font-size: 34px; line-height: 1;
  filter: drop-shadow(0 3px 8px rgba(0,0,0,0.45));
  animation: spinHourglass 2.6s ease-in-out infinite;
}
@keyframes spinHourglass { 0% { transform: rotate(0deg); } 50% { transform: rotate(180deg); } 100% { transform: rotate(360deg); } }

/* CTA */
.k-cta {
  background: linear-gradient(100deg, rgba(38,81,45,0.96), rgba(22,142,56,0.88)), var(--k-green-deep);
  color: #fff; border-radius: 22px; padding: 46px 32px; text-align: center; margin: 38px 0 20px;
}
.k-cta h2 { font-size: clamp(22px, 2.7vw, 31px); font-weight: 700; color: #fff; margin-bottom: 10px; }
.k-cta p { opacity: 0.9; max-width: 640px; margin: 0 auto 22px; }
.k-lead-card { max-width: 560px; margin: 0 auto 26px; background: #fff; border-radius: 18px;
  border: 1px solid var(--k-gray); box-shadow: 0 14px 34px rgba(23,32,46,0.14); padding: 24px 26px; }

/* Footer */
.k-footer {
  text-align: center; color: var(--k-medium); font-size: 13px; padding: 22px 0;
  border-top: 3px solid var(--k-green); margin-top: 6px;
}

/* ---- Streamlit widget restyling (green/gold) ---- */
.stButton>button {
  background: linear-gradient(135deg, #168e38, #137922);
  color: #fff; border: none; border-radius: 100px;
  padding: 11px 26px; font-weight: 600; font-size: 14.5px;
  transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
}
.stButton>button:hover {
  transform: translateY(-1px); background: #137922;
  box-shadow: 0 8px 24px rgba(22,142,56,0.40);
}
.stButton>button:focus { box-shadow: 0 0 0 3px rgba(22,142,56,0.25); }
.stButton>button[kind="secondary"] { background: #fff; color: var(--k-green-deep); border: 1.6px solid #cccedb; }
.stButton>button[kind="secondary"]:hover { background: var(--k-light); box-shadow: none; transform: none; }

[data-testid="stRadioGroup"] [data-testid="stRadioOption"] {
  border: 1.6px solid var(--k-gray); background: #fff; border-radius: 13px;
  padding: 8px 15px; margin: 3px 0; cursor: pointer; transition: all .18s ease; font-weight: 500;
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"] > div { color: var(--ink); }
[data-testid="stRadioGroup"] [data-testid="stRadioOption"]:hover {
  border-color: var(--k-green); background: rgba(22,142,56,0.08);
  transform: translateX(4px); box-shadow: 0 4px 14px rgba(22,142,56,0.18);
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"]:has(input:checked) {
  border-color: var(--k-green); background: linear-gradient(135deg, rgba(22,142,56,0.16), rgba(22,142,56,0.06));
  font-weight: 700;
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"]:has(input:checked) > div { color: var(--k-green-deep); }
[data-testid="stRadioGroup"] [data-testid="stRadioOption"] > div > div:first-child > div:first-child {
  width: 18px; height: 18px; background: #fff; border: 2px solid var(--muted); box-sizing: border-box;
}
[data-testid="stRadioGroup"] [data-testid="stRadioOption"]:has(input:checked) > div > div:first-child > div:first-child {
  width: 18px; height: 18px; background: #fff; border: 3px solid var(--k-gold); box-sizing: border-box;
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stForm"] [data-testid="stWidgetLabel"] { color: var(--k-green); font-weight: 700; }
[data-testid="stForm"] .stTextInput > div > div > input {
  border: 2px solid var(--k-green) !important; background: #fff !important;
  color: var(--ink) !important; border-radius: 10px !important; padding: 11px 14px !important; font-size: 15px !important;
}
[data-testid="stForm"] .stFormSubmitButton > button {
  background: #168e38 !important; color: #fff !important; border: none !important;
  border-radius: 100px !important; font-weight: 700 !important; padding: 11px 26px !important;
}
[data-testid="stForm"] .stFormSubmitButton > button:hover { background: #0d2816 !important; }
</style>
"""
