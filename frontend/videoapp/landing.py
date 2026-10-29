"""Лендинг: HERO / ЦЕННОСТИ / ШАГИ / ПРОЕКТЫ (Open Design)."""

import os

import streamlit as st
from videoapp.settings import PROJECTS_SHOWCASE
from videoapp.theme import _b64_uri, asset


# ---------------------------------------------------------------------------
# ЗАГРУЗКА ВЕКТОРА ПРИЗНАКОВ И РАЗДЕЛ ДИЗАЙНА: HERO / VALUES / STEPS / PROJECTS
# ---------------------------------------------------------------------------
def render_hero():
    bg = "kaskad_1.jpg" if os.path.exists(asset("kaskad_1.jpg")) else "bg_01.jpg"
    bg_uri = _b64_uri(asset(bg))
    st.markdown(
        f"""
        <div class="k-hero" style="background-image:url('{bg_uri}')">
            <div class="overlay"></div>
            <div class="inner">
                <div class="k-badge"><span class="dot"></span> Новый ИИ-сервис от группы Каскад
                &nbsp;·&nbsp; <strong>ТЕСТОВАЯ ВЕРСИЯ ПРИЛОЖЕНИЯ В ПРОЦЕССЕ РАЗРАБОТКИ</strong></div>
                <h1>ИИ найдёт <em>ваш</em> идеальный таунхаус в Подмосковье</h1>
                <p class="lead">Ответьте на 9 простых вопросов — искусственный интеллект проанализирует
                Ваши предпочтения и подберёт недвижимость, идеально подходящую Вам и Вашей семье.</p>
                <div class="k-stats">
                    <div class="k-stat"><div class="num">9</div><div class="label">вопросов</div></div>
                    <div class="k-stat"><div class="num">30</div><div class="label">секунд на выбор</div></div>
                    <div class="k-stat"><div class="num">100%</div><div class="label">прозрачность</div></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_VALUES_DATA = [
    (
        "ИИ вместо рутины.jpg",
        "ИИ вместо рутины",
        "Не нужно часами листать каталоги. Нейросеть анализирует ваши ответы и сразу выдаёт лучший вариант.",
    ),
    (
        "Прозрачный выбор.png",
        "Прозрачный выбор",
        "Вы видите, какие характеристики посёлка повлияли на решение больше всего — никакого «чёрного ящика».",
    ),
    (
        "Экономия времени.jpg",
        "Экономия времени",
        "То, что раньше занимало вечер, теперь занимает полминуты. Выбирайте осознанно, но быстро.",
    ),
    (
        "Персональное видео.jpg",
        "Персональное видео",
        "ИИ монтирует ролик специально для вас: сначала важные факторы, затем дополнительные детали.",
    ),
]


def render_values():
    st.markdown(
        """
<div class="k-section-title">
  <h2>Почему это меняет выбор недвижимости</h2>
  <span class="underline"></span>
  <p>Первый в России ИИ-сервис персонализированного подбора элитных таунхаусов с прозрачной логикой решения.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    for pair in (_VALUES_DATA[:2], _VALUES_DATA[2:]):
        cols = st.columns(2)
        for col, (img, title, text) in zip(cols, pair, strict=False):
            with col:
                src = _b64_uri(asset(img)) if os.path.exists(asset(img)) else ""
                st.markdown(
                    f'<div class="k-value"><img class="card-img" src="{src}" alt="">'
                    f'<div class="v-body"><h3>{title}</h3><p>{text}</p></div></div>',
                    unsafe_allow_html=True,
                )


_STEPS_DATA = [
    (
        "1",
        "Отвечаете на вопросы.jpg",
        "Отвечаете на вопросы",
        "Рассказываете о планировке, бюджете, семье, цели покупки и важных критериях.",
    ),
    (
        "2",
        "ИИ анализирует данные.jpg",
        "ИИ анализирует данные",
        "Модель сопоставляет ваши ответы с характеристиками посёлков и выбирает лучший.",
    ),
    (
        "3",
        "Получаете результат.jpg",
        "Получаете результат",
        "Смотрите персональное видео, график важности факторов и заявку на просмотр.",
    ),
]


def render_steps():
    st.markdown(
        """
<div class="k-section-title">
  <h2>Как работает KASKAD AI</h2>
  <span class="underline"></span>
  <p>Три простых шага от ваших пожеланий — к готовому предложению.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    for col, (num, img, title, text) in zip(cols, _STEPS_DATA, strict=False):
        with col:
            src = _b64_uri(asset(img)) if os.path.exists(asset(img)) else ""
            st.markdown(
                f'<div class="k-step"><img class="step-img" src="{src}" alt="">'
                f'<div class="step-body"><div class="step-num">{num}</div>'
                f"<h3>{title}</h3><p>{text}</p></div></div>",
                unsafe_allow_html=True,
            )


def render_projects():
    heading_html = (
        '<div class="k-section-title"><h2>Проекты вокруг Москвы</h2>'
        '<span class="underline"></span>'
        "<p>Посёлки в 7–30 км от МКАД с готовой инфраструктурой и благоустройством."
        " Нажмите на посёлок, чтобы открыть его сайт.</p></div>"
    )
    st.markdown(heading_html, unsafe_allow_html=True)
    pcols = st.columns(4)
    for i, (col, p) in enumerate(zip(pcols, PROJECTS_SHOWCASE, strict=False)):
        with col:
            src = _b64_uri(asset(p["img"])) if os.path.exists(asset(p["img"])) else ""
            chip_cls = "k-alt" if i % 2 == 1 else ""
            feats = ", ".join(p["features"][:3])
            card = (
                '<a class="proj-link" href="%s" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;display:block"><div class="proj-card-od"><img class="p-img" src="%s" alt=""><div class="p-body"><h4>%s</h4><p class="p-loc">%s · %s</p><p class="p-features">%s. Особенности: %s</p><span class="p-chip %s">%s</span></div></div></a>'  # noqa: UP031
                % (
                    p["url"],
                    src,
                    p["name"],
                    p["highway"],
                    p["distance"],
                    p["meta"],
                    feats,
                    chip_cls,
                    p["price"],
                )
            )  # noqa: UP031 — большой HTML-шаблон, %-формат осознанно оставлен
            st.markdown(card, unsafe_allow_html=True)
