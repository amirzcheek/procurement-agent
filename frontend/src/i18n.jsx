import { createContext, useCallback, useContext, useMemo, useState } from 'react'

export const LANG_KEY = 'procurement_lang'
const LANGS = ['ru', 'kk', 'en']

export const i18n = {
  ru: {
    agent_name: 'Анализатор закупок',
    to_portal: 'Вернуться на портал',
    admin: 'Админка',
    tab_analyze: 'Анализ КП',
    tab_knowledge: 'База знаний',
    disclaimer:
      'Предварительный анализ. Цены найдены автоматически и требуют проверки человеком. Это помощник закупщика, а не автоматический отказ поставщику.',
    subtitle: 'Проверка цен коммерческого предложения по рынку и по истории закупок',
    pick_file: 'Выберите файл КП (.xlsx или текстовый .pdf)',
    analyze_btn: 'Анализировать',
    cancel_btn: 'Остановить',
    download_xlsx: '⬇ Скачать xlsx',
    hint_idle:
      'Позиции обрабатываются последовательно — при реальном поиске это может занять время.',
    progress_extract: 'Распознаём позиции из таблицы…',
    progress_parse: 'Извлечение и разбор позиций…',
    found_items: 'Найдено позиций',
    position: 'Позиция',
    th_name: 'Наименование',
    th_qty: 'Кол-во',
    th_kp_price: 'Цена КП',
    th_market_min: 'Мин рынка',
    th_median: 'Медиана',
    th_delta: 'Дельта %',
    th_flag: 'Флаг',
    th_links: 'Ссылки',
    flag_green: 'Норма',
    flag_yellow: 'Внимание',
    flag_red: 'Завышение',
    flag_gray: 'Проверить',
    sum_green: 'Норма',
    sum_yellow: 'Внимание',
    sum_red: 'Завышение',
    sum_gray: 'Проверить',
    sum_overpay: 'Оценочная переплата по КП:',
    market_title: 'Сравнение с рынком (сейчас)',
    // Период
    period_title: 'Период сравнения цен',
    p_3m: '3 месяца',
    p_6m: '6 месяцев',
    p_12m: '12 месяцев',
    p_all: 'за всё время',
    p_custom: 'свой диапазон',
    date_from: 'с',
    date_to: 'по',
    // Историческй анализ
    hist_title: 'Сравнение с историей закупок',
    hist_for_period: 'за период',
    hist_internal: 'Внутренняя история',
    hist_web: 'История веб-поиска',
    hist_min: 'мин',
    hist_max: 'макс',
    hist_count: 'наблюдений',
    hist_range: 'Диапазон',
    hist_trend: 'Тренд',
    hist_risk: 'Риск',
    hist_reco: 'Рекомендация',
    risk_low: 'Низкий',
    risk_medium: 'Средний',
    risk_high: 'Высокий',
    risk_unknown: 'Нет данных',
    trend_rising: 'растёт',
    trend_falling: 'снижается',
    trend_flat: 'стабильна',
    hist_disabled: 'База знаний выключена — исторический анализ недоступен.',
    hist_loading: 'Считаем исторический анализ…',
    // База знаний
    kb_title: 'Загрузка в базу знаний',
    kb_desc:
      'Загрузите ранее заключённый договор или КП. Система извлечёт позиции, вы подтвердите — и они пополнят историю закупок для будущего сравнения.',
    kb_pick: 'Выберите договор/КП (.xlsx или .pdf)',
    kb_extract: 'Извлечь позиции',
    kb_extracting: 'Извлечение…',
    kb_confirm_hint: 'Проверьте извлечённые данные и заполните реквизиты договора.',
    kb_number: 'Номер договора',
    kb_date: 'Дата',
    kb_supplier: 'Поставщик',
    kb_customer: 'Заказчик',
    kb_funding: 'Источник финансирования',
    kb_save: 'Сохранить в базу знаний',
    kb_saving: 'Сохранение…',
    kb_saved: 'Сохранено в базу знаний ✓',
    kb_items: 'позиций',
    col_unit: 'Ед.',
    col_unitprice: 'Цена/ед',
    err_prefix: 'Ошибка',
  },

  kk: {
    agent_name: 'Сатып алу талдағышы',
    to_portal: 'Порталға оралу',
    admin: 'Әкімші панелі',
    tab_analyze: 'КҰ талдау',
    tab_knowledge: 'Білім қоры',
    disclaimer:
      'Алдын ала талдау. Бағалар автоматты табылған, адам тексеруін қажет етеді. Бұл сатып алушының көмекшісі, жеткізушіден автоматты бас тарту емес.',
    subtitle: 'Коммерциялық ұсыныс бағаларын нарық және сатып алу тарихы бойынша тексеру',
    pick_file: 'КҰ файлын таңдаңыз (.xlsx немесе мәтіндік .pdf)',
    analyze_btn: 'Талдау',
    cancel_btn: 'Тоқтату',
    download_xlsx: '⬇ xlsx жүктеу',
    hint_idle: 'Позициялар кезекпен өңделеді — нақты іздеу уақыт алуы мүмкін.',
    progress_extract: 'Кестеден позицияларды танимыз…',
    progress_parse: 'Позицияларды шығару және талдау…',
    found_items: 'Табылған позициялар',
    position: 'Позиция',
    th_name: 'Атауы',
    th_qty: 'Саны',
    th_kp_price: 'КҰ бағасы',
    th_market_min: 'Нарық мин',
    th_median: 'Медиана',
    th_delta: 'Дельта %',
    th_flag: 'Белгі',
    th_links: 'Сілтемелер',
    flag_green: 'Қалыпты',
    flag_yellow: 'Назар',
    flag_red: 'Асыра баға',
    flag_gray: 'Тексеру',
    sum_green: 'Қалыпты',
    sum_yellow: 'Назар',
    sum_red: 'Асыра баға',
    sum_gray: 'Тексеру',
    sum_overpay: 'КҰ бойынша болжамды артық төлем:',
    market_title: 'Нарықпен салыстыру (қазір)',
    period_title: 'Баға салыстыру кезеңі',
    p_3m: '3 ай',
    p_6m: '6 ай',
    p_12m: '12 ай',
    p_all: 'барлық уақыт',
    p_custom: 'өз аралығы',
    date_from: 'бастап',
    date_to: 'дейін',
    hist_title: 'Сатып алу тарихымен салыстыру',
    hist_for_period: 'кезеңі',
    hist_internal: 'Ішкі тарих',
    hist_web: 'Веб-іздеу тарихы',
    hist_min: 'мин',
    hist_max: 'макс',
    hist_count: 'бақылау',
    hist_range: 'Аралық',
    hist_trend: 'Үрдіс',
    hist_risk: 'Тәуекел',
    hist_reco: 'Ұсыныс',
    risk_low: 'Төмен',
    risk_medium: 'Орташа',
    risk_high: 'Жоғары',
    risk_unknown: 'Дерек жоқ',
    trend_rising: 'өсуде',
    trend_falling: 'төмендеуде',
    trend_flat: 'тұрақты',
    hist_disabled: 'Білім қоры өшірулі — тарихи талдау қолжетімсіз.',
    hist_loading: 'Тарихи талдау есептелуде…',
    kb_title: 'Білім қорына жүктеу',
    kb_desc:
      'Бұрын жасалған шартты немесе КҰ жүктеңіз. Жүйе позицияларды шығарады, сіз растайсыз — олар салыстыру үшін тарихты толықтырады.',
    kb_pick: 'Шарт/КҰ таңдаңыз (.xlsx немесе .pdf)',
    kb_extract: 'Позицияларды шығару',
    kb_extracting: 'Шығару…',
    kb_confirm_hint: 'Шығарылған деректерді тексеріп, шарт деректемелерін толтырыңыз.',
    kb_number: 'Шарт нөмірі',
    kb_date: 'Күні',
    kb_supplier: 'Жеткізуші',
    kb_customer: 'Тапсырыс беруші',
    kb_funding: 'Қаржыландыру көзі',
    kb_save: 'Білім қорына сақтау',
    kb_saving: 'Сақталуда…',
    kb_saved: 'Білім қорына сақталды ✓',
    kb_items: 'позиция',
    col_unit: 'Бірл.',
    col_unitprice: 'Бірл. баға',
    err_prefix: 'Қате',
  },

  en: {
    agent_name: 'Procurement Analyzer',
    to_portal: 'Back to portal',
    admin: 'Admin panel',
    tab_analyze: 'Offer analysis',
    tab_knowledge: 'Knowledge base',
    disclaimer:
      'Preliminary analysis. Prices are found automatically and require human review. This is an assistant for the buyer, not an automatic rejection of a supplier.',
    subtitle: 'Check commercial-offer prices against the market and purchase history',
    pick_file: 'Choose an offer file (.xlsx or text .pdf)',
    analyze_btn: 'Analyze',
    cancel_btn: 'Stop',
    download_xlsx: '⬇ Download xlsx',
    hint_idle: 'Items are processed sequentially — a real search may take a while.',
    progress_extract: 'Recognizing items from the table…',
    progress_parse: 'Extracting and parsing items…',
    found_items: 'Items found',
    position: 'Item',
    th_name: 'Name',
    th_qty: 'Qty',
    th_kp_price: 'Offer price',
    th_market_min: 'Market min',
    th_median: 'Median',
    th_delta: 'Delta %',
    th_flag: 'Flag',
    th_links: 'Links',
    flag_green: 'Normal',
    flag_yellow: 'Attention',
    flag_red: 'Overpriced',
    flag_gray: 'Review',
    sum_green: 'Normal',
    sum_yellow: 'Attention',
    sum_red: 'Overpriced',
    sum_gray: 'Review',
    sum_overpay: 'Estimated overpayment:',
    market_title: 'Market comparison (now)',
    period_title: 'Price comparison period',
    p_3m: '3 months',
    p_6m: '6 months',
    p_12m: '12 months',
    p_all: 'all time',
    p_custom: 'custom range',
    date_from: 'from',
    date_to: 'to',
    hist_title: 'Comparison with purchase history',
    hist_for_period: 'for period',
    hist_internal: 'Internal history',
    hist_web: 'Web-search history',
    hist_min: 'min',
    hist_max: 'max',
    hist_count: 'observations',
    hist_range: 'Range',
    hist_trend: 'Trend',
    hist_risk: 'Risk',
    hist_reco: 'Recommendation',
    risk_low: 'Low',
    risk_medium: 'Medium',
    risk_high: 'High',
    risk_unknown: 'No data',
    trend_rising: 'rising',
    trend_falling: 'falling',
    trend_flat: 'flat',
    hist_disabled: 'Knowledge base is off — historical analysis unavailable.',
    hist_loading: 'Computing historical analysis…',
    kb_title: 'Upload to knowledge base',
    kb_desc:
      'Upload a past contract or offer. The system extracts items, you confirm — and they enrich the purchase history for future comparison.',
    kb_pick: 'Choose a contract/offer (.xlsx or .pdf)',
    kb_extract: 'Extract items',
    kb_extracting: 'Extracting…',
    kb_confirm_hint: 'Review the extracted data and fill in the contract details.',
    kb_number: 'Contract number',
    kb_date: 'Date',
    kb_supplier: 'Supplier',
    kb_customer: 'Customer',
    kb_funding: 'Funding source',
    kb_save: 'Save to knowledge base',
    kb_saving: 'Saving…',
    kb_saved: 'Saved to knowledge base ✓',
    kb_items: 'items',
    col_unit: 'Unit',
    col_unitprice: 'Unit price',
    err_prefix: 'Error',
  },
}

function detectLang() {
  const saved = localStorage.getItem(LANG_KEY)
  if (saved && i18n[saved]) return saved
  const b = (navigator.language || 'ru').toLowerCase()
  if (b.startsWith('kk')) return 'kk'
  if (b.startsWith('en')) return 'en'
  return 'ru'
}

const LangCtx = createContext(null)

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(detectLang)
  const setLang = useCallback((l) => {
    if (!i18n[l]) return
    localStorage.setItem(LANG_KEY, l)
    document.documentElement.lang = l
    setLangState(l)
  }, [])
  const t = useCallback(
    (key, vars = {}) => {
      const tpl = i18n[lang]?.[key] ?? i18n.ru[key] ?? key
      return tpl.replace(/\{(\w+)\}/g, (_, n) => String(vars[n] ?? ''))
    },
    [lang]
  )
  const locale = lang === 'kk' ? 'kk-KZ' : lang === 'en' ? 'en-US' : 'ru-RU'
  const value = useMemo(() => ({ lang, setLang, t, locale }), [lang, setLang, t, locale])
  return <LangCtx.Provider value={value}>{children}</LangCtx.Provider>
}

export function useI18n() {
  const ctx = useContext(LangCtx)
  if (!ctx) throw new Error('useI18n must be used within <LangProvider>')
  return ctx
}

export function LangSwitcher() {
  const { lang, setLang } = useI18n()
  return (
    <div className="lang-switch">
      {[
        ['ru', 'RU'],
        ['kk', 'KZ'],
        ['en', 'EN'],
      ].map(([code, label]) => (
        <button
          key={code}
          type="button"
          className={'lang-btn' + (lang === code ? ' active' : '')}
          onClick={() => setLang(code)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
