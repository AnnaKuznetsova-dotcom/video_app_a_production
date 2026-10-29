"""Анкета (video_app_a): словарь вопросов, рельса прогресса, фрагмент анкеты
и форма заявки «Записаться на показ»."""

import streamlit as st
from videoapp.landing import render_hero, render_projects, render_steps, render_values

import analytics

# ---------------------------------------------------------------------------
# СЛОВАРЬ АНКЕТЫ (video_app_a) + короткие подсказки в стиле Open Design
# ---------------------------------------------------------------------------
QUESTIONNAIRE_MAP: list[dict] = [
    {
        "feature_prefix": "bin_num__квартира_планировка",
        "question": "Какая планировка вам интересна?",
        "hint": "Выберите вариант, который лучше всего подходит под ваш образ жизни.",
        "answers": [
            "1 комната",
            "2 комнаты",
            "3 комнаты",
            "4 комнаты",
            "более 4 комнат",
            "студия",
            "иное",
        ],
    },
    {
        "feature_prefix": "bin_num__приоритеты",
        "question": "Что для вас важнее всего при выборе жилья?",
        "hint": "Главный критерий, от которого вы не готовы отступать.",
        "answers": [
            "безопасность",
            "инфраструктура",
            "контингент",
            "природа и экология",
            "транспортная доступность",
            "иное",
        ],
    },
    {
        "feature_prefix": "bin_num__отделка",
        "question": "Какой тип отделки вы рассматриваете?",
        "hint": "Отделка влияет на сроки въезда и итоговый бюджет.",
        "answers": ["white_box", "под ключ", "под отделку", "иное"],
    },
    {
        "feature_prefix": "bin_num__цель_приобретения",
        "question": "Какова цель приобретения?",
        "hint": "Решение ИИ учитывает вашу стратегию использования.",
        "answers": ["для сдачи в аренду", "дополнительное жилье", "инвестирование", "иное"],
    },
    {
        "feature_prefix": "bin_num__как_бы_предпочли_купить_жилье",
        "question": "Как планируете оплачивать покупку?",
        "hint": "Подберём посёлок с подходящими условиями ипотеки или рассрочки.",
        "answers": [
            "ипотека",
            "материнский капитал",
            "полная оплата",
            "продажа имеющегося жилья",
            "рассрочка",
            "иное",
        ],
    },
    {
        "feature_prefix": "few_cat__семейное_положение",
        "question": "Ваше семейное положение?",
        "hint": "Это помогает оценить нужную инфраструктуру рядом.",
        "answers": ["женат/замужем", "холост/не замужем"],
    },
    {
        "feature_prefix": "few_cat__есть_ли_дети",
        "question": "Есть ли у вас дети?",
        "hint": "Рядом с посёлком важны детские сады, школы и безопасная территория.",
        "answers": ["Есть", "Нет"],
    },
    {
        "feature_prefix": "few_cat__наличие_автомобиля",
        "question": "Есть ли у вас автомобиль?",
        "hint": "Наличие машины влияет на требования к парковке и транспортной доступности.",
        "answers": ["Есть", "Нет"],
    },
]

AREA_QUESTION = {
    "column_name": "ord__ранг_площади",
    "question": "Какая площадь вас интересует? (кв. м)",
    "hint": "Укажите желаемую минимальную площадь дома.",
    "answers": [float(x) for x in range(40, 260, 20)],  # как в video_app_a
}

CROSS_MAP = [
    {
        "source_prefix": "bin_num__квартира_планировка",
        "target_prefix": "few_cat__количество_комнат",
        "mapping": {
            "1 комната": "1.0",
            "2 комнаты": "2.0",
            "3 комнаты": "3.0",
            "4 комнаты": "4.0",
            "более 4 комнат": "4.0",
        },
    },
    {
        "source_prefix": "bin_num__как_бы_предпочли_купить_жилье",
        "target_prefix": "bin_num__схема",
        "mapping": {
            "ипотека": "ипотека",
            "рассрочка": "рассрочка",
            "полная оплата": "оплата",
            "продажа имеющегося жилья": "оплата",
            "материнский капитал": "оплата",
        },
    },
]

ANSWER_FRAGMENT_MAP: dict[str, dict[str, str]] = {
    "bin_num__квартира_планировка": {
        "1 комната": "1_комн",
        "2 комнаты": "2_комн",
        "3 комнаты": "3_комн",
        "4 комнаты": "4_комн",
        "более 4 комнат": "более_4_комн",
        "студия": "студия",
        "иное": "missing",
    },
    "bin_num__приоритеты": {
        "безопасность": "безопасность",
        "инфраструктура": "инфраструктура",
        "контингент": "контингент",
        "природа и экология": "природа_экология",
        "транспортная доступность": "транспортная_доступность",
        "иное": "missing",
    },
    "bin_num__отделка": {
        "white_box": "white_box",
        "под ключ": "под_ключ",
        "под отделку": "под_отделку",
        "иное": "missing",
    },
    "few_cat__есть_ли_дети": {
        "Есть": "Есть",
        "Нет": "Нет",
    },
}

EXTRA_GROUP_ANSWERS = {
    "bin_num__цель_приобретения": "для сдачи в аренду",
}

CTRL_ACTION_LABEL = "Глубокий нейросетевой анализ для элитных клиентов"


# ---------------------------------------------------------------------------
# РЕЛЬСА ПРОГРЕССА (Open Design)
# ---------------------------------------------------------------------------
def _rail_infos() -> list[dict]:
    infos = []
    for item in QUESTIONNAIRE_MAP:
        prefix = item["feature_prefix"]
        val = st.session_state.get(f"q_{prefix}")
        infos.append({"q": item["question"], "answered": val is not None})
    area_val = st.session_state.get("q_area")
    infos.append({"q": AREA_QUESTION["question"], "answered": area_val is not None})
    return infos


def _rail_html(infos: list[dict]) -> str:
    total = len(infos)
    answered = sum(1 for it in infos if it["answered"])
    rows = ""
    for i, it in enumerate(infos):
        if it["answered"]:
            state, mark = "done", "✓"
        elif i == answered:
            state, mark = "current", str(i + 1)
        else:
            state, mark = "", str(i + 1)
        rows += (
            f'<div class="k-rail-item {state}"><span class="pi">{mark}</span>'
            f'<span class="pt">{it["q"]}</span></div>'
        )
    pct = max(4, round(answered / total * 100))
    return (
        f'<div class="k-rail"><h4>Прогресс анкеты</h4>'
        f'<div class="k-track"><div style="width:{pct}%"></div></div>'
        f'<div class="k-count">{answered} из {total} · {pct}%</div>{rows}'
        f'<div style="margin-top:12px;border-top:1px solid var(--k-gray);padding-top:10px;'
        f'font-size:12px;color:var(--k-medium)">Отмечайте варианты слева — прогресс обновится автоматически</div></div>'
    )


def _clear_result():
    for _k in (
        "result",
        "vector",
        "latency_ms",
        "error",
        "generating",
        "variant",
        "video_shown_logged",
    ):
        st.session_state.pop(_k, None)


@st.fragment
def _hero_block_fragment():
    render_hero()
    render_values()
    render_steps()
    render_projects()


@st.fragment
def _questionnaire_fragment():
    """Анкета (Open Design) + правый бегунок прогресса; всё в одном фрагменте.
    Клик по radio перерисовывает ТОЛЬКО этот блок (не трогает hero)."""
    q_col, rail_col = st.columns([0.78, 0.22], gap="large")
    with rail_col:
        infos = _rail_infos()
        st.html('<div class="k-rail-wrap">' + _rail_html(infos) + "</div>")
    with q_col:
        for i, item in enumerate(QUESTIONNAIRE_MAP):
            prefix = item["feature_prefix"]
            st.markdown(
                f'<div class="k-question"><h3>{i + 1}. {item["question"]}</h3>'
                f'<p class="hint">{item.get("hint", "")}</p></div>',
                unsafe_allow_html=True,
            )
            st.radio(
                item["question"],
                item["answers"],
                index=None,
                key=f"q_{prefix}",
                label_visibility="collapsed",
                on_change=_clear_result,
            )
        st.markdown(
            f'<div class="k-question"><h3>{len(QUESTIONNAIRE_MAP) + 1}. {AREA_QUESTION["question"]}</h3>'
            f'<p class="hint">{AREA_QUESTION.get("hint", "")}</p></div>',
            unsafe_allow_html=True,
        )
        st.radio(
            AREA_QUESTION["question"],
            options=AREA_QUESTION["answers"],
            index=None,
            format_func=lambda v: f"{int(v)} кв. м",
            key="q_area",
            label_visibility="collapsed",
            on_change=_clear_result,
        )

        # Кнопка генерации живёт ВНУТРИ фрагмента: её состояние обновляется
        # при каждом ответе (иначе кнопка у фрагмента остаётся неактивной).
        st.session_state["_qa_answers"] = {
            item["feature_prefix"]: st.session_state.get(f"q_{item['feature_prefix']}")
            for item in QUESTIONNAIRE_MAP
        }
        st.session_state["_qa_area"] = st.session_state.get("q_area")
        _infos = _rail_infos()
        _answered = sum(1 for it in _infos if it["answered"])
        _ready = _answered == len(_infos)
        st.markdown(f"**{CTRL_ACTION_LABEL}**")
        st.caption(
            "Глубокий нейросетевой анализ ваших ответов определит подходящий "
            "посёлок, самые важные для вас факторы и соберёт персональную "
            "видеоподборку."
        )
        _chosen = []
        for item in QUESTIONNAIRE_MAP:
            v = st.session_state.get(f"q_{item['feature_prefix']}")
            if v and item["feature_prefix"] in (
                "bin_num__приоритеты",
                "bin_num__отделка",
                "few_cat__есть_ли_дети",
            ):
                _chosen.append(v)
        if _area_val := st.session_state.get("q_area"):
            _chosen.append(f"Площадь: {int(_area_val)} кв. м")
        st.markdown("**Ваш персональный акцент:** " + (" · ".join(_chosen) if _chosen else "—"))
        if st.button(
            "Поиск идеального объекта для Вашего дома",
            type="primary",
            disabled=not _ready,
            width="stretch",
        ):
            try:
                # UTM-хелпер живёт в app.py (контракт тестов app.*); импортируем
                # лениво, чтобы не зациклить app → videoapp → app.
                from app import utm_extra  # noqa: PLC0415

                analytics.log_preview_click(utm=utm_extra())
            except Exception:
                pass
            _clear_result()
            st.session_state["generating"] = True
            st.rerun()
        if not _ready:
            st.caption(f"Осталось ответить: {len(_infos) - _answered}")


# ---------------------------------------------------------------------------
# ФОРМА ЗАЯВКИ «Записаться на показ» (ФИО + телефон → отдельный отчёт)
# ---------------------------------------------------------------------------
def render_lead_form(settlement_name: str = ""):
    # Валидаторы телефона обязаны быть определены в app.py (контракт тестов
    # app.validate_phone / app.sanitize_phone); импортируем лениво (анти-цикл).
    from app import sanitize_phone, validate_phone  # noqa: PLC0415

    with st.container():
        st.markdown('<div class="k-lead-card">', unsafe_allow_html=True)
        with st.form("lead_form_od", clear_on_submit=True):
            st.markdown("**Записаться на показ** — менеджер группы Каскад свяжется с вами.")
            fio = st.text_input("ФИО покупателя", placeholder="Иванов Иван Иванович")
            phone = st.text_input(
                "Телефон",
                key="lead_phone_input",
                placeholder="+7 (900) 123-45-67",
                help="Только цифры и символы + ( ) -. Формат: +7 (XXX) XXX-XX-XX",
            )
            consent = st.checkbox("Я согласен(-на) на обработку персональных данных")
            submitted = st.form_submit_button("Отправить заявку")
            if submitted:
                phone = sanitize_phone(phone or "")
                if not (fio or "").strip():
                    st.error("Пожалуйста, укажите ФИО покупателя.")
                elif not validate_phone(phone):
                    st.error(
                        "Пожалуйста, введите корректный номер телефона в формате +7 (900) 123-45-67."
                    )
                elif not consent:
                    st.error("Необходимо согласие на обработку персональных данных.")
                else:
                    analytics.log_lead(fio.strip(), phone)
                    analytics.log_lead_report(fio.strip(), phone, settlement_name)
                    st.success("Спасибо! Заявка принята — мы перезвоним вам в течение 15 минут.")
        st.markdown("</div>", unsafe_allow_html=True)
