
(function() {
  const componentStateMap = new Map();
  let seenComponentKeys = new Set();
  let currentCompKey = 'root';
  let currentHookIdx = 0;
  let rootComponent = null;
  let rootContainer = null;
  let pendingEffects = [];
  let isRendering = false;
  let renderQueued = false;
  let contextStack = new Map();

  function getHooksBucket() {
    let bucket = componentStateMap.get(currentCompKey);
    if (!bucket) {
      bucket = [];
      componentStateMap.set(currentCompKey, bucket);
    }
    return bucket;
  }

  function scheduleRender() {
    if (isRendering) {
      renderQueued = true;
      return;
    }
    renderRoot();
  }

  function createElement(type, props, ...children) {
    const flatChildren = [];
    const pushChild = (c) => {
      if (Array.isArray(c)) {
        c.forEach(pushChild);
      } else if (c === null || c === undefined || c === false || c === true) {
        // skip booleans/nullish
      } else {
        flatChildren.push(typeof c === 'object' ? c : String(c));
      }
    };
    children.forEach(pushChild);
    return { type, props: props || {}, children: flatChildren };
  }

  function Fragment(props) {
    return props.children || [];
  }

  function depsChanged(oldDeps, newDeps) {
    if (!oldDeps || !newDeps || oldDeps.length !== newDeps.length) return true;
    for (let i = 0; i < newDeps.length; i++) {
      if (!Object.is(oldDeps[i], newDeps[i])) return true;
    }
    return false;
  }

  function useState(initialValue) {
    const compKey = currentCompKey;
    const idx = currentHookIdx++;
    const bucket = getHooksBucket();
    if (bucket[idx] === undefined) {
      bucket[idx] = typeof initialValue === 'function' ? initialValue() : initialValue;
    }
    const setState = (updater) => {
      const b = componentStateMap.get(compKey);
      if (!b) return;
      const nextVal = typeof updater === 'function' ? updater(b[idx]) : updater;
      if (!Object.is(b[idx], nextVal)) {
        b[idx] = nextVal;
        scheduleRender();
      }
    };
    return [bucket[idx], setState];
  }

  function useReducer(reducer, initialArg, init) {
    const [state, setState] = useState(() => (typeof init === 'function' ? init(initialArg) : initialArg));
    const dispatch = (action) => {
      setState((prev) => reducer(prev, action));
    };
    return [state, dispatch];
  }

  function useRef(initialValue) {
    const idx = currentHookIdx++;
    const bucket = getHooksBucket();
    if (bucket[idx] === undefined) {
      bucket[idx] = { current: initialValue };
    }
    return bucket[idx];
  }

  function useMemo(factory, deps) {
    const idx = currentHookIdx++;
    const bucket = getHooksBucket();
    const prev = bucket[idx];
    if (!prev || depsChanged(prev.deps, deps)) {
      const val = factory();
      bucket[idx] = { val, deps };
      return val;
    }
    return prev.val;
  }

  function useCallback(fn, deps) {
    return useMemo(() => fn, deps);
  }

  function useEffect(effect, deps) {
    const compKey = currentCompKey;
    const idx = currentHookIdx++;
    const bucket = getHooksBucket();
    const prev = bucket[idx];
    if (!prev || depsChanged(prev.deps, deps)) {
      pendingEffects.push(() => {
        if (prev && typeof prev.cleanup === 'function') {
          try { prev.cleanup(); } catch {}
        }
        const cleanup = effect();
        const b = componentStateMap.get(compKey);
        if (b) {
          b[idx] = { deps, cleanup };
        }
      });
    }
  }

  const useLayoutEffect = useEffect;

  let nextContextId = 1;
  function createContext(defaultValue) {
    const ctxId = 'ctx_' + (nextContextId++);
    const Provider = function ContextProvider(props) {
      const prevHas = contextStack.has(ctxId);
      const prevVal = contextStack.get(ctxId);
      contextStack.set(ctxId, props.value);
      return {
        __isContextBoundary: true,
        ctxId,
        prevHas,
        prevVal,
        children: props.children || []
      };
    };
    return { _id: ctxId, _defaultValue: defaultValue, Provider };
  }

  function useContext(ctx) {
    if (!ctx) return undefined;
    return contextStack.has(ctx._id) ? contextStack.get(ctx._id) : ctx._defaultValue;
  }

  function useSyncExternalStore(subscribe, getSnapshot) {
    const compKey = currentCompKey;
    const idx = currentHookIdx++;
    const bucket = getHooksBucket();
    const snap = getSnapshot();
    const prev = bucket[idx];
    if (!prev) {
      const unsub = subscribe(() => {
        const b = componentStateMap.get(compKey);
        const latest = getSnapshot();
        if (b && b[idx] && !Object.is(b[idx].snap, latest)) {
          b[idx].snap = latest;
          scheduleRender();
        }
      });
      bucket[idx] = { snap, unsub, isExternalSub: true };
    } else {
      prev.snap = snap;
    }
    return snap;
  }

  function memo(Comp) {
    return Comp;
  }

  function forwardRef(renderFn) {
    return function ForwardRefWrapper(props) {
      return renderFn(props, props.ref || null);
    };
  }

  const SVG_TAGS = new Set(['svg', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'text', 'g', 'defs', 'ellipse', 'tspan', 'linearGradient', 'radialGradient', 'stop', 'clipPath']);
  const SVG_ATTR_MAP = {
    strokeWidth: 'stroke-width',
    strokeDasharray: 'stroke-dasharray',
    strokeLinecap: 'stroke-linecap',
    strokeLinejoin: 'stroke-linejoin',
    fillOpacity: 'fill-opacity',
    strokeOpacity: 'stroke-opacity',
    textAnchor: 'text-anchor',
    dominantBaseline: 'dominant-baseline',
    fontSize: 'font-size',
    fontWeight: 'font-weight',
    fontFamily: 'font-family',
    clipPath: 'clip-path',
    stopColor: 'stop-color',
    stopOpacity: 'stop-opacity',
    tabIndex: 'tabindex',
  };

  function ensureDelegatedListener(dom, evt) {
    if (!dom.__boundEvts) dom.__boundEvts = {};
    if (dom.__boundEvts[evt]) return;
    dom.__boundEvts[evt] = true;
    dom.addEventListener(evt, (e) => {
      const fn = dom.__handlers && dom.__handlers[evt];
      if (typeof fn === 'function') fn(e);
    });
    if (evt === 'change' && (dom.tagName === 'INPUT' || dom.tagName === 'TEXTAREA' || dom.tagName === 'SELECT')) {
      dom.__boundEvts.input = true;
      dom.addEventListener('input', (e) => {
        const fn = dom.__handlers && (dom.__handlers.input || dom.__handlers.change);
        if (typeof fn === 'function') fn(e);
      });
    }
  }

  function applyProps(dom, newProps, isSvg) {
    dom.__handlers = {};
    for (const [k, val] of Object.entries(newProps || {})) {
      if (k === 'key' || k === 'children') continue;
      if (k === 'ref') {
        if (typeof val === 'function') {
          dom.__refFn = val;
          val(dom);
        } else if (val && typeof val === 'object') {
          dom.__refObj = val;
          val.current = dom;
        }
        continue;
      }
      if (k.startsWith('on') && typeof val === 'function') {
        const evt = k.slice(2).toLowerCase();
        dom.__handlers[evt] = val;
        ensureDelegatedListener(dom, evt);
      } else if (k === 'className') {
        if (isSvg) dom.setAttribute('class', val || '');
        else dom.className = val || '';
      } else if (k === 'htmlFor') {
        dom.setAttribute('for', val || '');
      } else if (k === 'dangerouslySetInnerHTML' && val && typeof val.__html === 'string') {
        dom.__hasRawHtml = true;
        dom.innerHTML = val.__html;
      } else if (k === 'style' && typeof val === 'object' && val !== null) {
        Object.assign(dom.style, val);
      } else if (k === 'value' && (dom.tagName === 'INPUT' || dom.tagName === 'SELECT' || dom.tagName === 'TEXTAREA')) {
        const strVal = val === undefined || val === null ? '' : String(val);
        dom.__controlledValue = strVal;
        dom.value = strVal;
        dom.setAttribute('value', strVal);
      } else if (k === 'checked' && dom.tagName === 'INPUT') {
        dom.__controlledChecked = Boolean(val);
        dom.checked = Boolean(val);
      } else if (k === 'disabled') {
        dom.disabled = Boolean(val);
        if (val) dom.setAttribute('disabled', '');
      } else if (k === 'autoFocus') {
        if (val) {
          dom.__autoFocus = true;
          dom.setAttribute('autofocus', '');
        }
      } else if (val === undefined || val === null || val === false) {
        // omit
      } else {
        const attrName = isSvg && SVG_ATTR_MAP[k] ? SVG_ATTR_MAP[k] : k;
        dom.setAttribute(attrName, val === true ? 'true' : String(val));
      }
    }
  }

  function morphDomNode(oldNode, newNode) {
    if (!oldNode || !newNode) return newNode;
    if (
      oldNode.nodeType !== newNode.nodeType ||
      oldNode.nodeName !== newNode.nodeName ||
      oldNode.namespaceURI !== newNode.namespaceURI
    ) {
      oldNode.replaceWith(newNode);
      return newNode;
    }
    if (oldNode.nodeType === 3) {
      if (oldNode.nodeValue !== newNode.nodeValue) {
        oldNode.nodeValue = newNode.nodeValue;
      }
      return oldNode;
    }
    if (oldNode.nodeType === 1) {
      oldNode.__handlers = newNode.__handlers || {};
      for (const evt of Object.keys(oldNode.__handlers)) {
        ensureDelegatedListener(oldNode, evt);
      }

      const oldAttrs = Array.from(oldNode.attributes);
      for (const attr of oldAttrs) {
        if (!newNode.hasAttribute(attr.name)) {
          oldNode.removeAttribute(attr.name);
        }
      }
      const newAttrs = Array.from(newNode.attributes);
      for (const attr of newAttrs) {
        if (oldNode.getAttribute(attr.name) !== attr.value) {
          oldNode.setAttribute(attr.name, attr.value);
        }
      }

      if (newNode.__hasRawHtml) {
        if (oldNode.innerHTML !== newNode.innerHTML) {
          oldNode.innerHTML = newNode.innerHTML;
        }
      } else {
        morphChildList(oldNode, newNode);
      }

      if (oldNode.tagName === 'INPUT' || oldNode.tagName === 'TEXTAREA' || oldNode.tagName === 'SELECT') {
        if (newNode.__controlledValue !== undefined && oldNode.value !== newNode.__controlledValue) {
          oldNode.value = newNode.__controlledValue;
        }
        if (oldNode.tagName === 'INPUT' && newNode.__controlledChecked !== undefined) {
          oldNode.checked = newNode.__controlledChecked;
        }
      }
      if ('disabled' in oldNode) {
        oldNode.disabled = Boolean(newNode.disabled);
      }
      if (newNode.__autoFocus) {
        oldNode.__autoFocus = true;
      }
      if (newNode.__refFn) newNode.__refFn(oldNode);
      else if (newNode.__refObj) newNode.__refObj.current = oldNode;
    }
    return oldNode;
  }

  function morphChildList(oldParent, newParent) {
    const newKids = Array.from(newParent.childNodes);
    let idx = 0;
    while (idx < newKids.length) {
      const oldChild = oldParent.childNodes[idx];
      const newChild = newKids[idx];
      if (!oldChild) {
        oldParent.appendChild(newChild);
      } else {
        morphDomNode(oldChild, newChild);
      }
      idx++;
    }
    while (oldParent.childNodes.length > newKids.length) {
      oldParent.removeChild(oldParent.lastChild);
    }
  }

  function createDomNode(vnode, inSvg, treePath) {
    if (Array.isArray(vnode)) {
      const frag = document.createDocumentFragment();
      for (let i = 0; i < vnode.length; i++) {
        const item = vnode[i];
        const keyPart = (item && item.props && item.props.key != null) ? 'k_' + item.props.key : String(i);
        frag.appendChild(createDomNode(item, inSvg, treePath + '/' + keyPart));
      }
      return frag;
    }
    if (typeof vnode === 'string' || typeof vnode === 'number') {
      return document.createTextNode(String(vnode));
    }
    if (!vnode) return document.createTextNode('');
    if (vnode.__isContextBoundary) {
      const node = createDomNode(vnode.children, inSvg, treePath + '/ctx');
      if (vnode.prevHas) contextStack.set(vnode.ctxId, vnode.prevVal);
      else contextStack.delete(vnode.ctxId);
      return node;
    }
    if (typeof vnode.type === 'function') {
      const compName = vnode.type.displayName || vnode.type.name || 'Anon';
      const explicitKey = vnode.props && vnode.props.key != null ? ':' + vnode.props.key : '';
      const compKey = treePath + ':' + compName + explicitKey;
      seenComponentKeys.add(compKey);
      const prevCompKey = currentCompKey;
      const prevHookIdx = currentHookIdx;
      currentCompKey = compKey;
      currentHookIdx = 0;
      let sub;
      try {
        sub = vnode.type({ ...vnode.props, children: vnode.children });
      } finally {
        currentCompKey = prevCompKey;
        currentHookIdx = prevHookIdx;
      }
      return createDomNode(sub, inSvg, compKey);
    }
    const isSvg = inSvg || SVG_TAGS.has(vnode.type);
    const el = isSvg
      ? document.createElementNS('http://www.w3.org/2000/svg', vnode.type)
      : document.createElement(vnode.type);
    applyProps(el, vnode.props, isSvg);
    for (let i = 0; i < vnode.children.length; i++) {
      const child = vnode.children[i];
      const cKey = (child && child.props && child.props.key != null) ? 'k_' + child.props.key : String(i);
      el.appendChild(createDomNode(child, isSvg, treePath + '/' + cKey));
    }
    if (vnode.props && vnode.props.value !== undefined && el.tagName === 'SELECT') {
      el.value = String(vnode.props.value);
    }
    return el;
  }

  function renderRoot() {
    if (!rootComponent || !rootContainer) return;
    isRendering = true;
    seenComponentKeys = new Set();
    pendingEffects = [];

    // Preserve active input focus across re-renders
    const activeEl = document.activeElement;
    let activeMeta = null;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'SELECT')) {
      const allInputs = Array.from(rootContainer.querySelectorAll('input, textarea, select'));
      activeMeta = {
        id: activeEl.id || '',
        placeholder: activeEl.getAttribute('placeholder') || '',
        idx: allInputs.indexOf(activeEl),
        selStart: activeEl.selectionStart,
        selEnd: activeEl.selectionEnd,
      };
    }

    const domTree = createDomNode(createElement(rootComponent, {}), false, 'root');
    if (rootContainer.childNodes.length === 0) {
      rootContainer.appendChild(domTree);
    } else {
      const holder = document.createElement('div');
      holder.appendChild(domTree);
      morphChildList(rootContainer, holder);
    }

    const autoFocusCandidates = Array.from(rootContainer.querySelectorAll('[autofocus]'));
    let didTriggerAutoFocus = false;
    for (const candidate of autoFocusCandidates) {
      if (!candidate.__didAutoFocus) {
        candidate.__didAutoFocus = true;
        try {
          candidate.focus();
          didTriggerAutoFocus = true;
        } catch {}
      }
    }

    // Cleanup unmounted component hooks & subscriptions
    for (const [key, bucket] of componentStateMap.entries()) {
      if (!seenComponentKeys.has(key)) {
        for (const slot of bucket) {
          if (slot && typeof slot.cleanup === 'function') {
            try { slot.cleanup(); } catch {}
          }
          if (slot && slot.isExternalSub && typeof slot.unsub === 'function') {
            try { slot.unsub(); } catch {}
          }
        }
        componentStateMap.delete(key);
      }
    }

    if (activeMeta && !didTriggerAutoFocus) {
      let target = null;
      if (activeMeta.id) {
        target = rootContainer.querySelector('#' + CSS.escape(activeMeta.id));
      }
      if (!target && activeMeta.placeholder) {
        target = Array.from(rootContainer.querySelectorAll('input, textarea')).find(
          (el) => el.getAttribute('placeholder') === activeMeta.placeholder
        );
      }
      if (!target && activeMeta.idx >= 0) {
        const allInputs = Array.from(rootContainer.querySelectorAll('input, textarea, select'));
        target = allInputs[activeMeta.idx] || null;
      }
      if (target) {
        try {
          target.focus();
          if (typeof activeMeta.selStart === 'number' && target.setSelectionRange) {
            target.setSelectionRange(activeMeta.selStart, activeMeta.selEnd);
          }
        } catch {}
      }
    }

    isRendering = false;
    const effectsToRun = pendingEffects.slice();
    pendingEffects = [];
    for (const eff of effectsToRun) {
      eff();
    }
    if (renderQueued) {
      renderQueued = false;
      renderRoot();
    }
  }

  window.__MiniReact = {
    createElement,
    Fragment,
    useState,
    useReducer,
    useRef,
    useMemo,
    useCallback,
    useEffect,
    useLayoutEffect,
    createContext,
    useContext,
    useSyncExternalStore,
    memo,
    forwardRef,
    mount(Comp, container) {
      rootComponent = Comp;
      rootContainer = container;
      renderRoot();
    }
  };

  window.addEventListener('message', (evt) => {
    const msg = evt && evt.data;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'PORTFOLIO_SET_STATE' && typeof msg.state === 'string') {
      if (typeof window.__PIPELINE_SET_VIEW_STATE__ === 'function') {
        window.__PIPELINE_SET_VIEW_STATE__(msg.state);
      } else {
        const btn = document.querySelector('[data-state-trigger="' + msg.state + '"]');
        if (btn && typeof btn.click === 'function') btn.click();
      }
    } else if (msg.type === 'PORTFOLIO_SET_SCREEN' && typeof msg.index === 'number') {
      if (typeof window.__PIPELINE_SET_VIEW_STATE__ === 'function') {
        window.__PIPELINE_SET_VIEW_STATE__('Ideal');
      }
      const triggers = document.querySelectorAll('[data-screen-trigger]');
      const target = triggers[msg.index];
      if (target && typeof target.click === 'function') target.click();
    }
  });

  document.addEventListener('click', (evt) => {
    if (!window.parent || window.parent === window) return;
    const t = evt.target && evt.target.closest ? evt.target.closest('[data-screen-trigger], [data-primary-action="true"]') : null;
    if (!t) return;
    setTimeout(() => {
      const triggers = Array.from(document.querySelectorAll('[data-screen-trigger]'));
      const activeIdx = triggers.findIndex((b) => b.getAttribute('aria-current') === 'page');
      window.parent.postMessage({
        type: 'PORTFOLIO_SYNC',
        screenIndex: activeIdx >= 0 ? activeIdx : 0,
        state: 'Ideal'
      }, '*');
    }, 30);
  });
})();

(function() {
  globalThis.__VITE_ENV__ = globalThis.__VITE_ENV__ || { MODE: 'production', PROD: true, DEV: false };
  const React = window.__MiniReact;
  const uxSpecData = {
  "projectMeta": {
    "name": "Запас-Навигатор: Рабочая тетрадь закупок и габаритов склада",
    "domain": "Supply Chain Replenishment, Warehouse Capacity Solver & Supplier Order Specification",
    "locale": "ru-RU"
  },
  "productValue": {
    "craftVersion": "8.2",
    "spatialParadigm": "editorial-notebook",
    "humanLanguageFirst": true,
    "deliverableFormat": "csv-and-memo",
    "scenarioPresets": [
      {
        "id": "preset-seasonal-peak",
        "label": "Осенний пик спроса",
        "summary": "Рост отгрузок со склада, риск дефицита датчиков и перегруз ячеек приемки по паллетам"
      },
      {
        "id": "preset-port-delay",
        "label": "Задержка на границе",
        "summary": "Сдвиг транзитных партий на 9 дней, перевод критичных позиций на резервный канал"
      },
      {
        "id": "preset-tight-warehouse",
        "label": "Сжатый лимит склада",
        "summary": "Свободно лишь 34 паллетоместа в зоне приемки при жестком потолке закупочного бюджета"
      }
    ]
  },
  "jobStories": [
    {
      "id": "JS-1",
      "statement": "Когда перед отправкой недельной заявки сумма партий превышает вместимость зоны приемки по паллетам и массе, я хочу одной кнопкой сбалансировать заказ по складу с защитой критичных позиций, чтобы уложиться в габаритный лимит склада без дефицита.",
      "situation": "Формирование сводной закупочной ведомости при ограниченном числе свободных паллетомест и весовом пороге рампы",
      "motivation": "Сразу видеть влияние каждой коробки на паллеты, килограммы и бюджет волны без ручного пересчета в разрозненных таблицах",
      "outcome": "Снижение загрузки приемки с 49,3 до 39,8 паллет и устранение риска пустых полок по ключевым комплектующим"
    },
    {
      "id": "JS-2",
      "statement": "Когда складская служба временно сокращает доступные паллетоместа под плановую инвентаризацию, я хочу подвинуть потолки паллет, массы и бюджета с пересчетом ведомости, чтобы заранее отсечь избыточный объем второстепенных партий.",
      "situation": "Согласование окна приемки со старшим кладовщиком и финансовым контролером",
      "motivation": "Быстрая проверка выполнимости заказа при ужесточении складских и бюджетных рамок",
      "outcome": "Прозрачный запас по емкости ячеек и точное соблюдение лимита закупочной волны до 3 650,0 тыс. ₽"
    },
    {
      "id": "JS-3",
      "statement": "Когда основной поставщик поднимает отпускную цену или растягивает отгрузку, я хочу наглядно сравнить индекс надежности поставщика и сроки доставки по альтернативным площадкам, чтобы переключить комплектацию без срыва графика сборки.",
      "situation": "Выбор контрагента между региональными заводами и быстрыми распределительными базами",
      "motivation": "Сопоставление закупочной стоимости, минимальной кратности партии и фактической пунктуальности отгрузок",
      "outcome": "Сокращение среднего плеча поставки на 4,2 дня при сохранении плановой себестоимости комплектации"
    },
    {
      "id": "JS-4",
      "statement": "Когда ведомость закупки выверена по габаритам и срокам, я хочу мгновенно скачать чистую спецификацию заказа .csv или скопировать пояснительную записку для руководителя, чтобы передать документ поставщику и на склад приемки.",
      "situation": "Утверждение итоговой закупочной волны на утренней планерке отдела снабжения",
      "motivation": "Готовый к отправке табличный файл и краткое обоснование без ручного переноса артикулов и сумм",
      "outcome": "Выгрузка актуальной спецификации .csv со всеми правками, новыми строками и историей согласования"
    }
  ],
  "archetypeSelection": {
    "archetype": "B",
    "name": "Editorial Swiss Grid (Stripe Press / Read.cv)",
    "rationale": "Рабочая тетрадь закупщика опирается на строгую швейцарскую журнальную сетку нейтрального архитектурного листа OKLCH (Hue 245) с открытыми разделительными линиями 1px, геометрией углов 2px, гротескным табличным набором цифр и лаконичным киноварным акцентом на главном действии балансировки.",
    "geometryContract": {
      "cardRadiusPx": 2,
      "borderWidthPx": 1,
      "surfaceStrategy": "exposed-grid"
    },
    "signatureElement": {
      "id": "swiss-replenishment-solver-ledger",
      "name": "Editorial Replenishment Ledger with Live Warehouse Constraint Solver & Counterfactual Balance",
      "selector": "[data-signature=\"swiss-replenishment-solver-ledger\"]",
      "description": "Журнальная ведомость пополнения запасов с живой панелью габаритных ограничений склада по паллетам, массе и бюджету, прямым шагом партий и карточкой сравнения «Было → Стало»."
    }
  },
  "screenGraph": [
    {
      "screenId": "screen-replenishment-notebook",
      "title": "Расчет партий дозаказа и емкости склада",
      "route": "/notebook",
      "primaryAction": {
        "id": "balance-order-to-warehouse",
        "label": "Сбалансировать заказ по складу",
        "shortcut": "⌘↵"
      },
      "secondaryActions": [
        {
          "id": "open-add-sku-modal",
          "label": "+ Позиция в заказ",
          "hierarchy": "secondary"
        },
        {
          "id": "open-csv-export",
          "label": "Выгрузка CSV",
          "hierarchy": "ghost"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Рабочая ведомость пополнения с контролем точки дозаказа и габаритного лимита склада",
          "description": "Переключайте жизненные сценарии снабжения, меняйте партии прямо в строках таблицы и балансируйте загрузку ячеек.",
          "visibleComponents": [
            "swiss-replenishment-solver-ledger",
            "warehouse-constraint-solver-strip",
            "before-after-balance-card",
            "active-sku-supplier-inspector"
          ]
        },
        "Empty": {
          "headline": "В текущей закупочной волне пока нет позиций к заказу",
          "description": "Загрузите типовой сценарий осеннего спроса или добавьте первую номенклатурную позицию вручную.",
          "onboardingCtaLabel": "Загрузить ведомость пикового спроса"
        },
        "Loading": {
          "skeletonBlocks": 5,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_LEDGER_SNAPSHOT_CORRUPTED",
          "userMessage": "Локальный черновик закупочной ведомости был прерван при обновлении браузера.",
          "recoveryActionLabel": "Восстановить эталонную ведомость",
          "technicalHint": "Исходные нормативы страхового запаса и емкости склада сохранены без потерь"
        }
      }
    },
    {
      "screenId": "screen-supply-map",
      "title": "Карта входящих поставок и клиентских отгрузок",
      "route": "/map",
      "primaryAction": {
        "id": "reconcile-network-flows",
        "label": "Выровнять потоки сети",
        "shortcut": "⌘M"
      },
      "secondaryActions": [
        {
          "id": "switch-express-corridor",
          "label": "Ускоренный авторейс",
          "hierarchy": "secondary"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Двуплечевая карта входящего снабжения заводов и исходящих отгрузок заказчикам через центральный склад",
          "description": "Выберите узел поставщика, распределительный центр или площадку получателя на карте, чтобы проверить состав партий и устранить риск срыва отгрузки.",
          "visibleComponents": [
            "swiss-supply-flow-map",
            "flow-corridor-inspector",
            "inbound-outbound-ledger"
          ]
        },
        "Empty": {
          "headline": "Маршрутная сеть поставок и отгрузок еще не заполнена",
          "description": "Загрузите базовый сценарий закупочной волны для построения входящих и исходящих потоков на карте.",
          "onboardingCtaLabel": "Загрузить ведомость пикового спроса"
        },
        "Loading": {
          "skeletonBlocks": 4,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_FLOW_TOPOLOGY_SYNC",
          "userMessage": "Сводка транзитных плеч и окон отгрузки была прервана при обновлении вкладки.",
          "recoveryActionLabel": "Восстановить эталонную ведомость",
          "technicalHint": "Координаты площадок, квоты ворот и заказы получателей сохранены в локальном контуре"
        }
      }
    },
    {
      "screenId": "screen-warehouse-limits",
      "title": "Ограничения паллетомест, массы и бюджета",
      "route": "/limits",
      "primaryAction": {
        "id": "apply-warehouse-limits",
        "label": "Применить габаритные лимиты",
        "shortcut": "⌘L"
      },
      "secondaryActions": [
        {
          "id": "append-custom-sku-row",
          "label": "Добавить строку",
          "hierarchy": "secondary"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Настройка доступных паллетомест зоны приемки, предельной массы и бюджета закупочной волны",
          "description": "Задайте реальные потолки склада и добавьте нестандартные позиции с мгновенной проверкой остатка места.",
          "visibleComponents": [
            "warehouse-ceiling-controls",
            "custom-sku-order-composer",
            "pallet-weight-share-breakdown"
          ]
        },
        "Empty": {
          "headline": "Складские ограничения еще не привязаны к товарам",
          "description": "Вернитесь к ведомости или загрузите базовый набор комплектующих для расчета нагрузки на ячейки.",
          "onboardingCtaLabel": "Заполнить складские нормативы"
        },
        "Loading": {
          "skeletonBlocks": 4,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_CAPACITY_CONFLICT",
          "userMessage": "Заданный потолок паллетомест меньше минимального страхового объема критичных комплектующих.",
          "recoveryActionLabel": "Вернуть стандартный лимит 46 паллет",
          "technicalHint": "Для бесперебойной отгрузки требуется минимум 28 свободных паллетомест"
        }
      }
    },
    {
      "screenId": "screen-supplier-choice",
      "title": "Сравнение поставщиков по цене и срокам",
      "route": "/suppliers",
      "primaryAction": {
        "id": "assign-best-suppliers",
        "label": "Назначить лучших поставщиков",
        "shortcut": "⌘S"
      },
      "secondaryActions": [
        {
          "id": "bind-selected-supplier",
          "label": "Закрепить за выбранной позицией",
          "hierarchy": "secondary"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Сопоставление контрагентов по индексу надежности поставщика, плечу доставки и отпускной цене",
          "description": "Нажмите на столбец поставщика на графике, чтобы проверить условия отгрузки и переключить комплектацию.",
          "visibleComponents": [
            "supplier-reliability-svg-chart",
            "supplier-terms-comparison-card"
          ]
        },
        "Empty": {
          "headline": "Список аккредитованных поставщиков не выбран",
          "description": "Восстановите справочник площадок для сравнения сроков и цен по текущей заявке.",
          "onboardingCtaLabel": "Открыть справочник поставщиков"
        },
        "Loading": {
          "skeletonBlocks": 4,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_SUPPLIER_QUOTA_EXCEEDED",
          "userMessage": "Минимальная партия выбранного завода превышает остаток бюджета закупочной волны.",
          "recoveryActionLabel": "Переключить на региональную базу",
          "technicalHint": "Площадка в Санкт-Петербурге отгружает кратно 10 штукам без перегруза склада"
        }
      }
    },
    {
      "screenId": "screen-delivery-buffer",
      "title": "Страховка сроков при задержках в пути",
      "route": "/buffer",
      "primaryAction": {
        "id": "reinforce-delivery-buffer",
        "label": "Усилить страховой запас",
        "shortcut": "⌘B"
      },
      "secondaryActions": [
        {
          "id": "switch-backup-channel",
          "label": "Резервный канал доставки",
          "hierarchy": "secondary"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Матрица транзитных рисков, точка дозаказа и выбор резервного канала при сдвиге поставок",
          "description": "Проверьте запас дней до исчерпания полки при задержках на маршруте и подключите ускоренный обход.",
          "visibleComponents": [
            "transit-coverage-risk-matrix",
            "backup-channel-selector-card",
            "active-sku-runout-readout"
          ]
        },
        "Empty": {
          "headline": "Маршрутные буферы для текущих позиций не рассчитаны",
          "description": "Выберите сценарий поставки, чтобы увидеть запас дней на случай дорожных сбоев.",
          "onboardingCtaLabel": "Рассчитать страховой буфер"
        },
        "Loading": {
          "skeletonBlocks": 4,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_TRANSIT_GAP_DETECTED",
          "userMessage": "При задержке в пути на 9 дней остаток датчиков закончится раньше прибытия основного вагона.",
          "recoveryActionLabel": "Включить региональный склад",
          "technicalHint": "Переход на резервный канал сокращает ожидание поставки на 5 суток"
        }
      }
    },
    {
      "screenId": "screen-order-export",
      "title": "Спецификация заказа поставщику CSV и записка",
      "route": "/export",
      "primaryAction": {
        "id": "download-order-csv",
        "label": "Скачать спецификацию .csv",
        "shortcut": "⌘E"
      },
      "secondaryActions": [
        {
          "id": "copy-order-memo",
          "label": "Скопировать текст",
          "hierarchy": "secondary"
        }
      ],
      "states": {
        "Ideal": {
          "headline": "Готовая таблица заказа .csv для поставщика и краткая пояснительная записка для согласования",
          "description": "Все изменения партий, габаритных лимитов и новые позиции сразу попадают в итоговый документ и журнал решений.",
          "visibleComponents": [
            "order-csv-memo-switcher",
            "live-order-artifact-preview",
            "procurement-decision-audit-log"
          ]
        },
        "Empty": {
          "headline": "Спецификация к отправке пока пуста",
          "description": "Добавьте позиции в рабочую ведомость перед выгрузкой файла поставщику.",
          "onboardingCtaLabel": "Вернуться к ведомости заказа"
        },
        "Loading": {
          "skeletonBlocks": 4,
          "loadingStrategy": "structural-shimmer"
        },
        "Error": {
          "errorCode": "ERR_CLIPBOARD_PERMISSION",
          "userMessage": "Браузер запросил подтверждение перед копированием текста спецификации в буфер обмена.",
          "recoveryActionLabel": "Скачать готовый файл .csv",
          "technicalHint": "Прямая выгрузка файла .csv работает автономно без ограничений буфера"
        }
      }
    }
  ],
  "datasets": {
    "metrics": [
      {
        "id": "metric-pallet-load",
        "label": "Занято ячеек",
        "value": 39.8,
        "formattedValue": "39,8 из 42,0 паллет",
        "deltaPercent": -19.3,
        "contextNote": "Загрузка зоны приемки после выравнивания объемных партий с учетом резерва ворот"
      },
      {
        "id": "metric-weight-load",
        "label": "Масса груза",
        "value": 10624.5,
        "formattedValue": "10 624,5 кг",
        "deltaPercent": -19.1,
        "contextNote": "Суммарный тоннаж поставки в пределах несущего лимита складской рампы"
      },
      {
        "id": "metric-wave-budget",
        "label": "Бюджет волны",
        "value": 3418.6,
        "formattedValue": "3 418,6 тыс. ₽",
        "deltaPercent": -14.2,
        "contextNote": "Итоговая сумма закупочной заявки после оптимизации кратности коробок"
      },
      {
        "id": "metric-safety-cover",
        "label": "Запас в днях",
        "value": 16.4,
        "formattedValue": "16,4 дня покрытия",
        "deltaPercent": 22.8,
        "contextNote": "Средний страховой запас по критичной автоматике с поправкой на плечо доставки"
      },
      {
        "id": "metric-supplier-reliability",
        "label": "Пунктуальность",
        "value": 96.4,
        "formattedValue": "96,4% в срок",
        "deltaPercent": 4.7,
        "contextNote": "Средневзвешенный индекс надежности поставщика по назначенному пулу заводов"
      },
      {
        "id": "metric-lead-days",
        "label": "Срок в пути",
        "value": 7.8,
        "formattedValue": "7,8 сут. до склада",
        "deltaPercent": -26.4,
        "contextNote": "Ожидаемое время прихода партии с подключением регионального резервного канала"
      }
    ],
    "records": [
      {
        "id": "sku-power-ctrl",
        "entityName": "Контроллеры питания распределительного шкафа с резервным вводом 24В",
        "summary": "Ключевой узел сборки щитов автоматики, точка дозаказа 48 шт., приоритетная приемка",
        "amount": 888.4,
        "status": "settled",
        "timestamp": "Поставка 6 сут."
      },
      {
        "id": "sku-pressure-sens",
        "entityName": "Датчики давления контура",
        "summary": "Повышенный расход на осенних заказах, требуется усиленный страховой запас на 12 дней",
        "amount": 752.6,
        "status": "flagged",
        "timestamp": "Поставка 6 сут."
      },
      {
        "id": "sku-terminal-blk",
        "entityName": "Клеммные колодки силовые",
        "summary": "Объемная позиция высокой паллетной плотности, допускает сжатие партии под лимит склада",
        "amount": 648.2,
        "status": "pending",
        "timestamp": "Поставка 11 сут."
      },
      {
        "id": "sku-line-relay",
        "entityName": "Реле защиты линии",
        "summary": "Стабильное потребление сборочного участка, отгрузка с ярославской площадки",
        "amount": 672.8,
        "status": "settled",
        "timestamp": "Поставка 5 сут."
      },
      {
        "id": "sku-cable-gland",
        "entityName": "Кабельные вводы герметичные",
        "summary": "Стандартная монтажная позиция, гибкая корректировка объема при нехватке паллетомест",
        "amount": 456.6,
        "status": "pending",
        "timestamp": "Поставка 14 сут."
      }
    ]
  },
  "productArchitecture": {
    "storageKey": "inventory_notebook_v7_store",
    "targetScreenCount": 6,
    "entityLifecycleStates": [
      "pending",
      "settled",
      "flagged"
    ],
    "crossScreenWorkflows": [
      {
        "id": "WF-MAP-TO-EXPORT",
        "name": "Выравнивание входящих и исходящих потоков на карте с пересчетом комплектности отгрузок и записки",
        "sourceScreenId": "screen-supply-map",
        "targetScreenId": "screen-order-export",
        "mutationAction": "RECONCILE_NETWORK_FLOWS",
        "auditEventLabel": "Выровнены входящие коридоры и защищены клиентские отгрузки",
        "entityIdField": "id",
        "mutatesKpiIds": [
          "metric-lead-days",
          "metric-pallet-load"
        ]
      },
      {
        "id": "WF-BALANCE-TO-EXPORT",
        "name": "Балансировка партий под емкость склада с мгновенным обновлением спецификации CSV и журнала решений",
        "sourceScreenId": "screen-replenishment-notebook",
        "targetScreenId": "screen-order-export",
        "mutationAction": "BALANCE_ORDER_TO_WAREHOUSE",
        "auditEventLabel": "Заказ сбалансирован по паллетам, массе и страховому запасу",
        "entityIdField": "id",
        "mutatesKpiIds": [
          "metric-pallet-load",
          "metric-wave-budget"
        ]
      },
      {
        "id": "WF-LIMITS-TO-NOTEBOOK",
        "name": "Изменение габаритного лимита склада и потолка бюджета с пересчетом допустимых партий ведомости",
        "sourceScreenId": "screen-warehouse-limits",
        "targetScreenId": "screen-replenishment-notebook",
        "mutationAction": "APPLY_WAREHOUSE_LIMITS",
        "auditEventLabel": "Обновлены ограничения паллетомест, массы и бюджета волны",
        "entityIdField": "id",
        "mutatesKpiIds": [
          "metric-pallet-load",
          "metric-weight-load"
        ]
      },
      {
        "id": "WF-BUFFER-TO-NOTEBOOK",
        "name": "Переключение резервного канала и усиление страхового запаса при задержках в пути",
        "sourceScreenId": "screen-delivery-buffer",
        "targetScreenId": "screen-replenishment-notebook",
        "mutationAction": "REINFORCE_DELIVERY_BUFFER",
        "auditEventLabel": "Пересчитан страховой запас и подключен резервный канал доставки",
        "entityIdField": "id",
        "mutatesKpiIds": [
          "metric-safety-cover",
          "metric-lead-days"
        ]
      }
    ]
  }
}
;
  const moduleFactories = {};
  const moduleCache = {};

  moduleFactories["App"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = App;
const react_1 = __importStar(require("react"));
const presets_1 = require("./data/presets");
const domainStore_1 = require("./store/domainStore");
const replenishmentEngine_1 = require("./store/replenishmentEngine");
const useGlobalWorkbenchShortcuts_1 = require("./hooks/useGlobalWorkbenchShortcuts");
const ShellModals_1 = require("./components/ShellModals");
const WhatIfSandboxModal_1 = require("./components/WhatIfSandboxModal");
const Icons_1 = require("./components/Icons");
const ScreenReplenishmentNotebook_1 = require("./screens/ScreenReplenishmentNotebook");
const ScreenSupplyMap_1 = require("./screens/ScreenSupplyMap");
const ScreenWarehouseLimits_1 = require("./screens/ScreenWarehouseLimits");
const ScreenSupplierChoice_1 = require("./screens/ScreenSupplierChoice");
const ScreenDeliveryBuffer_1 = require("./screens/ScreenDeliveryBuffer");
const ScreenOrderExport_1 = require("./screens/ScreenOrderExport");
function renderNavIcon(screenId) {
    switch (screenId) {
        case 'screen-replenishment-notebook':
            return react_1.default.createElement(Icons_1.LedgerGridIcon, { size: 14 });
        case 'screen-supply-map':
            return react_1.default.createElement(Icons_1.RouteMapIcon, { size: 14 });
        case 'screen-warehouse-limits':
            return react_1.default.createElement(Icons_1.WarehouseBoxIcon, { size: 14 });
        case 'screen-supplier-choice':
            return react_1.default.createElement(Icons_1.SupplierTruckIcon, { size: 14 });
        case 'screen-delivery-buffer':
            return react_1.default.createElement(Icons_1.ShieldClockIcon, { size: 14 });
        case 'screen-order-export':
            return react_1.default.createElement(Icons_1.CsvExportIcon, { size: 14 });
    }
}
function App() {
    const state = (0, domainStore_1.useInventoryStore)();
    const [viewState, setViewState] = (0, react_1.useState)('Ideal');
    const [addModalOpen, setAddModalOpen] = (0, react_1.useState)(false);
    const [cmdkOpen, setCmdkOpen] = (0, react_1.useState)(false);
    const [whatIfOpen, setWhatIfOpen] = (0, react_1.useState)(false);
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const palletsOk = summary.totalPallets <= summary.effectivePalletLimit + 0.05;
    const budgetOk = summary.totalBudgetKrub <= state.constraints.maxBudgetKrub + 0.05;
    (0, react_1.useEffect)(() => {
        const activeScr = presets_1.SCREEN_DEFINITIONS.find((s) => s.id === state.activeScreenId);
        if (activeScr) {
            document.title = `${activeScr.label}: Запас-Навигатор`;
        }
    }, [state.activeScreenId]);
    (0, react_1.useEffect)(() => {
        window.__PIPELINE_SET_VIEW_STATE__ = (next) => {
            if (next === 'Ideal' || next === 'Empty' || next === 'Loading' || next === 'Error') {
                setViewState(next);
            }
        };
        return () => {
            delete window.__PIPELINE_SET_VIEW_STATE__;
        };
    }, []);
    const handleToggleCmdk = (0, react_1.useCallback)(() => setCmdkOpen((prev) => !prev), []);
    const handleToggleWhatIf = (0, react_1.useCallback)(() => setWhatIfOpen((prev) => !prev), []);
    const handleCloseAllModals = (0, react_1.useCallback)(() => {
        setCmdkOpen(false);
        setAddModalOpen(false);
        setWhatIfOpen(false);
    }, []);
    (0, useGlobalWorkbenchShortcuts_1.useGlobalWorkbenchShortcuts)({
        onToggleCmdk: handleToggleCmdk,
        onToggleWhatIf: handleToggleWhatIf,
        onCloseAllModals: handleCloseAllModals,
        onSetViewState: setViewState
    });
    return (react_1.default.createElement("div", { "data-active-entity": state.activeSkuId, className: "min-h-screen bg-canvas text-primary font-sans app-shell-rail" },
        react_1.default.createElement("a", { href: "#main-content", className: "skip-link" }, "\u041F\u0435\u0440\u0435\u0439\u0442\u0438 \u043A \u0440\u0430\u0431\u043E\u0447\u0435\u0439 \u043E\u0431\u043B\u0430\u0441\u0442\u0438"),
        react_1.default.createElement("header", { "data-ui": "topbar", className: "app-rail-header" },
            react_1.default.createElement("div", { className: "flex items-center gap-2 min-w-0 shrink-0" },
                react_1.default.createElement(Icons_1.LedgerGridIcon, { size: 16, className: "text-accent-primary shrink-0" }),
                react_1.default.createElement("span", { className: "text-sm font-semibold tracking-tight text-primary whitespace-nowrap" }, "\u0417\u0430\u043F\u0430\u0441-\u041D\u0430\u0432\u0438\u0433\u0430\u0442\u043E\u0440"),
                react_1.default.createElement("span", { "data-breadcrumb": "true", className: "sr-only" }, "\u0417\u0430\u043F\u0430\u0441-\u041D\u0430\u0432\u0438\u0433\u0430\u0442\u043E\u0440 / \u0421\u043D\u0430\u0431\u0436\u0435\u043D\u0438\u0435")),
            react_1.default.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: () => setCmdkOpen(true), "aria-label": "\u0411\u044B\u0441\u0442\u0440\u044B\u0439 \u043F\u043E\u0438\u0441\u043A \u043A\u043E\u043C\u0430\u043D\u0434 \u0438 \u0440\u0430\u0437\u0434\u0435\u043B\u043E\u0432", className: "btn-ghost radius-control shrink-0" },
                react_1.default.createElement(Icons_1.SearchCmdIcon, { size: 14 }),
                react_1.default.createElement("kbd", { className: "text-xs text-muted tabular-nums" }, "\u2318K"))),
        react_1.default.createElement("nav", { "data-ui": "screen-nav", "data-nav-count": presets_1.SCREEN_DEFINITIONS.length, "aria-label": "\u0420\u0430\u0437\u0434\u0435\u043B\u044B \u0440\u0430\u0431\u043E\u0447\u0435\u0439 \u0442\u0435\u0442\u0440\u0430\u0434\u0438 \u0437\u0430\u043A\u0443\u043F\u043E\u043A", className: "app-screen-nav app-rail-nav" },
            presets_1.SCREEN_DEFINITIONS.map((scr) => {
                const isActive = state.activeScreenId === scr.id;
                return (react_1.default.createElement("button", { key: scr.id, type: "button", "data-ui": "nav-tab", "data-screen-trigger": scr.id, "aria-current": isActive ? 'page' : undefined, onClick: () => {
                        setViewState('Ideal');
                        domainStore_1.inventoryStore.setScreen(scr.id);
                    }, className: "app-nav-tab" },
                    renderNavIcon(scr.id),
                    react_1.default.createElement("span", { className: "hidden lg:inline" }, scr.label),
                    react_1.default.createElement("span", { className: "lg:hidden" }, scr.shortLabel)));
            }),
            react_1.default.createElement("div", { className: "app-rail-telemetry text-xs tabular-nums" },
                react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                    react_1.default.createElement("span", { className: "text-muted" }, "\u0412\u043E\u0440\u043E\u0442\u0430 \u0420\u0426"),
                    react_1.default.createElement("span", { className: "font-semibold text-primary" }, "\u0421\u043C\u0435\u043D\u0430 \u0410 \u00B7 1\u20134")),
                react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                    react_1.default.createElement("span", { className: "text-muted" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                    react_1.default.createElement("span", { className: palletsOk ? 'font-semibold text-status-success' : 'font-semibold text-status-danger' },
                        summary.totalPallets.toFixed(1),
                        "/",
                        summary.effectivePalletLimit,
                        " \u043F\u0430\u043B\u043B.")),
                react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                    react_1.default.createElement("span", { className: "text-muted" }, "\u0411\u044E\u0434\u0436\u0435\u0442"),
                    react_1.default.createElement("span", { className: budgetOk ? 'font-semibold text-primary' : 'font-semibold text-status-danger' },
                        Math.round(summary.totalBudgetKrub),
                        "/",
                        state.constraints.maxBudgetKrub,
                        " \u0442\u044B\u0441. \u20BD")),
                react_1.default.createElement("button", { type: "button", "data-ui": "btn-secondary", "data-open-whatif": "true", onClick: () => setWhatIfOpen(true), "aria-label": "\u041E\u0442\u043A\u0440\u044B\u0442\u044C \u0441\u0438\u043C\u0443\u043B\u044F\u0442\u043E\u0440 What-If \u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0435\u0432", className: "btn-secondary w-full radius-control justify-between" },
                    react_1.default.createElement("span", null, "What-If"),
                    react_1.default.createElement("kbd", { className: "text-xs text-muted tabular-nums" }, "Alt+S")))),
        react_1.default.createElement("main", { id: "main-content", tabIndex: -1, className: "app-main-shell app-rail-main" }, viewState !== 'Ideal' ? (react_1.default.createElement(ShellModals_1.StateFallbackView, { state: state, summary: summary, viewState: viewState, onRecoverToIdeal: () => setViewState('Ideal') })) : (react_1.default.createElement(react_1.default.Fragment, null,
            state.activeScreenId === 'screen-replenishment-notebook' && (react_1.default.createElement(ScreenReplenishmentNotebook_1.ScreenReplenishmentNotebook, { state: state, onOpenAddModal: () => setAddModalOpen(true) })),
            state.activeScreenId === 'screen-supply-map' && react_1.default.createElement(ScreenSupplyMap_1.ScreenSupplyMap, { state: state }),
            state.activeScreenId === 'screen-warehouse-limits' && (react_1.default.createElement(ScreenWarehouseLimits_1.ScreenWarehouseLimits, { state: state })),
            state.activeScreenId === 'screen-supplier-choice' && (react_1.default.createElement(ScreenSupplierChoice_1.ScreenSupplierChoice, { state: state })),
            state.activeScreenId === 'screen-delivery-buffer' && (react_1.default.createElement(ScreenDeliveryBuffer_1.ScreenDeliveryBuffer, { state: state })),
            state.activeScreenId === 'screen-order-export' && react_1.default.createElement(ScreenOrderExport_1.ScreenOrderExport, { state: state })))),
        react_1.default.createElement(ShellModals_1.AddSkuModal, { open: addModalOpen, onClose: () => setAddModalOpen(false) }),
        react_1.default.createElement(ShellModals_1.CmdKPalette, { open: cmdkOpen, onClose: () => setCmdkOpen(false), onOpenCreate: () => setAddModalOpen(true), onOpenWhatIf: () => {
                setCmdkOpen(false);
                setWhatIfOpen(true);
            } }),
        react_1.default.createElement(ShellModals_1.LiveUndoToast, { message: state.toastMessage, canUndo: Boolean(state.toastCanUndo) }),
        react_1.default.createElement(WhatIfSandboxModal_1.WhatIfSandboxModal, { open: whatIfOpen, onClose: () => setWhatIfOpen(false), state: state })));
}

  };

  moduleFactories["components/AddSkuModal"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.AddSkuModal = AddSkuModal;
const react_1 = __importStar(require("react"));
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
function AddSkuModal({ open, onClose }) {
    const [name, setName] = (0, react_1.useState)('');
    const [titleError, setTitleError] = (0, react_1.useState)('');
    const [category, setCategory] = (0, react_1.useState)('Автоматика');
    const [qtyStr, setQtyStr] = (0, react_1.useState)('40');
    const [costStr, setCostStr] = (0, react_1.useState)('6.8');
    const [bufferStr, setBufferStr] = (0, react_1.useState)('8');
    const [supplierId, setSupplierId] = (0, react_1.useState)('balt-komplekt');
    const [priority, setPriority] = (0, react_1.useState)('critical');
    const titleInputRef = (0, react_1.useRef)(null);
    const dialogRef = (0, a11yDialog_1.useDialogFocusTrap)(open);
    (0, react_1.useEffect)(() => {
        setTitleError('');
        if (open) {
            titleInputRef.current?.focus();
        }
    }, [open]);
    if (!open)
        return null;
    const handleClose = () => {
        setTitleError('');
        onClose();
    };
    const handleSubmit = (e) => {
        e.preventDefault();
        const clean = name.trim();
        if (!clean) {
            setTitleError('Укажите наименование номенклатуры');
            titleInputRef.current?.focus();
            return;
        }
        const parsedQty = Number(String(qtyStr).replace(',', '.'));
        const parsedCost = Number(String(costStr).replace(',', '.'));
        const parsedBuf = Number(String(bufferStr).replace(',', '.'));
        domainStore_1.inventoryStore.addCustomSku({
            name: clean,
            category,
            orderQty: Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty : 40,
            unitCostKrub: Number.isFinite(parsedCost) && parsedCost > 0 ? parsedCost : 6.8,
            safetyDays: Number.isFinite(parsedBuf) && parsedBuf > 0 ? parsedBuf : 8,
            supplierId,
            priority
        });
        setName('');
        handleClose();
    };
    return (react_1.default.createElement("div", { ref: dialogRef, role: "dialog", "aria-modal": "true", "aria-label": "\u0414\u043E\u0431\u0430\u0432\u0438\u0442\u044C \u043F\u043E\u0437\u0438\u0446\u0438\u044E \u0432 \u0437\u0430\u043A\u0443\u043F\u043E\u0447\u043D\u0443\u044E \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C", onClick: (e) => {
            if (e.target === e.currentTarget)
                handleClose();
        }, className: "fixed inset-0 z-50 flex items-center justify-center p-4 bg-canvas/80" },
        react_1.default.createElement("div", { "data-ui": "surface", className: "surface-card p-4 w-full max-w-md space-y-3" },
            react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                react_1.default.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u041D\u043E\u0432\u0430\u044F \u043F\u043E\u0437\u0438\u0446\u0438\u044F \u043A \u0437\u0430\u043A\u0430\u0437\u0443"),
                react_1.default.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: handleClose, "aria-label": "\u0417\u0430\u043A\u0440\u044B\u0442\u044C \u043E\u043A\u043D\u043E \u0434\u043E\u0431\u0430\u0432\u043B\u0435\u043D\u0438\u044F \u043F\u043E\u0437\u0438\u0446\u0438\u0438", className: "btn-ghost radius-control" }, "\u0417\u0430\u043A\u0440\u044B\u0442\u044C")),
            react_1.default.createElement("form", { noValidate: true, "data-mutation-form": "true", onSubmit: handleSubmit, className: "space-y-2.5" },
                react_1.default.createElement("div", { className: "space-y-1" },
                    react_1.default.createElement("label", { htmlFor: "sku-name-input", className: "block text-xs font-medium text-secondary" }, "\u041D\u0430\u0438\u043C\u0435\u043D\u043E\u0432\u0430\u043D\u0438\u0435 \u043A\u043E\u043C\u043F\u043B\u0435\u043A\u0442\u0443\u044E\u0449\u0438\u0445"),
                    react_1.default.createElement("input", { ref: titleInputRef, id: "sku-name-input", type: "text", autoFocus: true, value: name, "aria-invalid": titleError ? 'true' : undefined, "aria-describedby": titleError ? 'inv-modal-title-err' : undefined, onChange: (e) => {
                            setName(e.target.value);
                            if (titleError)
                                setTitleError('');
                        }, placeholder: "\u041D\u0430\u043F\u0440\u0438\u043C\u0435\u0440: \u041C\u043E\u0434\u0443\u043B\u0438 \u043F\u043B\u0430\u0432\u043D\u043E\u0433\u043E \u043F\u0443\u0441\u043A\u0430 \u043A\u043E\u043D\u0432\u0435\u0439\u0435\u0440\u0430", className: "w-full field-compact" }),
                    titleError ? (react_1.default.createElement("p", { id: "inv-modal-title-err", role: "alert", className: "text-xs text-status-danger mt-0.5" }, titleError)) : null),
                react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-12 gap-2 items-end" },
                    react_1.default.createElement("div", { className: "sm:col-span-7 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-category-select", className: "block text-xs font-medium text-secondary" }, "\u0422\u043E\u0432\u0430\u0440\u043D\u0430\u044F \u0433\u0440\u0443\u043F\u043F\u0430"),
                        react_1.default.createElement("select", { id: "sku-category-select", value: category, onChange: (e) => setCategory(e.target.value), className: "w-full field-compact" },
                            react_1.default.createElement("option", { value: "\u0410\u0432\u0442\u043E\u043C\u0430\u0442\u0438\u043A\u0430" }, "\u0410\u0432\u0442\u043E\u043C\u0430\u0442\u0438\u043A\u0430"),
                            react_1.default.createElement("option", { value: "\u0418\u0437\u043C\u0435\u0440\u0435\u043D\u0438\u044F" }, "\u0418\u0437\u043C\u0435\u0440\u0435\u043D\u0438\u044F"),
                            react_1.default.createElement("option", { value: "\u041A\u043E\u043C\u043C\u0443\u0442\u0430\u0446\u0438\u044F" }, "\u041A\u043E\u043C\u043C\u0443\u0442\u0430\u0446\u0438\u044F"),
                            react_1.default.createElement("option", { value: "\u041C\u043E\u043D\u0442\u0430\u0436" }, "\u041C\u043E\u043D\u0442\u0430\u0436"))),
                    react_1.default.createElement("div", { className: "sm:col-span-5 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-qty-input", className: "block text-xs font-medium text-secondary" }, "\u041F\u0430\u0440\u0442\u0438\u044F, \u0448\u0442."),
                        react_1.default.createElement("input", { id: "sku-qty-input", type: "number", min: "1", max: "5000", step: "1", required: true, value: qtyStr, onChange: (e) => setQtyStr(e.target.value), className: "w-full field-compact tabular-nums" }))),
                react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-12 gap-2 items-end" },
                    react_1.default.createElement("div", { className: "sm:col-span-7 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-supplier-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A"),
                        react_1.default.createElement("select", { id: "sku-supplier-select", value: supplierId, onChange: (e) => setSupplierId(e.target.value), className: "w-full field-compact" }, presets_1.SUPPLIER_LIST.map((sup) => (react_1.default.createElement("option", { key: sup.id, value: sup.id },
                            sup.name,
                            ", ",
                            sup.leadDays,
                            "\u0434"))))),
                    react_1.default.createElement("div", { className: "sm:col-span-5 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-cost-input", className: "block text-xs font-medium text-secondary" }, "\u0426\u0435\u043D\u0430, \u0442\u044B\u0441. \u20BD"),
                        react_1.default.createElement("input", { id: "sku-cost-input", type: "number", min: "0.1", max: "2500", step: "0.01", required: true, value: costStr, onChange: (e) => setCostStr(e.target.value), className: "w-full field-compact tabular-nums" }))),
                react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-12 gap-2 items-end" },
                    react_1.default.createElement("div", { className: "sm:col-span-7 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-priority-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u0440\u0438\u043E\u0440\u0438\u0442\u0435\u0442 \u0437\u0430\u0449\u0438\u0442\u044B"),
                        react_1.default.createElement("select", { id: "sku-priority-select", value: priority, onChange: (e) => setPriority(e.target.value), className: "w-full field-compact" },
                            react_1.default.createElement("option", { value: "critical" }, "\u041A\u0440\u0438\u0442\u0438\u0447\u043D\u044B\u0439"),
                            react_1.default.createElement("option", { value: "standard" }, "\u0421\u0442\u0430\u043D\u0434\u0430\u0440\u0442\u043D\u044B\u0439"))),
                    react_1.default.createElement("div", { className: "sm:col-span-5 flex flex-col justify-end gap-1 min-w-0" },
                        react_1.default.createElement("label", { htmlFor: "sku-buffer-input", className: "block text-xs font-medium text-secondary" }, "\u0411\u0443\u0444\u0435\u0440, \u0441\u0443\u0442."),
                        react_1.default.createElement("input", { id: "sku-buffer-input", type: "number", min: "4", max: "24", step: "1", required: true, value: bufferStr, onChange: (e) => setBufferStr(e.target.value), className: "w-full field-compact tabular-nums" }))),
                react_1.default.createElement("div", { className: "flex flex-wrap items-center justify-end gap-2 pt-1" },
                    react_1.default.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: handleClose, className: "btn-ghost radius-control" }, "\u041E\u0442\u043C\u0435\u043D\u0430"),
                    react_1.default.createElement("button", { type: "submit", "data-ui": "btn-primary", "data-form-submit": "true", className: "btn-primary radius-control" }, "\u0412\u043A\u043B\u044E\u0447\u0438\u0442\u044C \u0432 \u0437\u0430\u043A\u0430\u0437"))))));
}

  };

  moduleFactories["components/CapacityHorizonChart"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CapacityHorizonChart = CapacityHorizonChart;
const react_1 = require("react");
const CapacityHorizonGauges_1 = require("./CapacityHorizonGauges");
const capacityHorizonModel_1 = require("./capacityHorizonModel");
function CapacityHorizonChart({ state, onSelectSku }) {
    const [activeIdx, setActiveIdx] = (0, react_1.useState)(1);
    const { summary, activeSku, activeLead, activeCoverDays } = (0, capacityHorizonModel_1.computeActiveSkuTelemetry)(state);
    const points = (0, capacityHorizonModel_1.buildHorizonPoints)(state, summary);
    const gauges = (0, capacityHorizonModel_1.buildCapacityGauges)(state, summary);
    const safeIdx = Math.max(0, Math.min(points.length - 1, activeIdx));
    const activePt = points[safeIdx] || points[0];
    const maxPalletScale = Math.max(60, state.constraints.maxPallets + 10);
    const plotTop = 22;
    const plotBottom = 132;
    const plotHeight = plotBottom - plotTop;
    const mapY = (pallets) => {
        const clamped = Math.max(0, Math.min(maxPalletScale, pallets));
        return Math.round(plotBottom - (clamped / maxPalletScale) * plotHeight);
    };
    const limitY = mapY(summary.effectivePalletLimit);
    const ceilingY = mapY(state.constraints.maxPallets);
    const linePath = points
        .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.cx} ${mapY(pt.totalPallets)}`)
        .join(' ');
    return (React.createElement("div", { className: "space-y-1.5" },
        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 text-sm" },
            React.createElement("span", { "data-chart-context": "true", className: "text-secondary font-medium tabular-nums" }, activeSku
                ? `${activeSku.name}: покрытие ${activeCoverDays} сут., плечо ${activeLead} сут., окно ${activePt.dayLabel}`
                : `Горизонт загрузки РЦ ${activePt.dayLabel}`),
            React.createElement("span", { className: "hidden md:inline text-xs text-muted tabular-nums" },
                "\u0417\u043E\u043D\u044B \u0445\u0440\u0430\u043D\u0435\u043D\u0438\u044F \u0414+1..\u0414+14, \u043F\u043E\u0440\u043E\u0433 \u0432\u043E\u0440\u043E\u0442 ",
                summary.effectivePalletLimit,
                " \u043F\u0430\u043B\u043B.")),
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-2.5 items-center" },
            React.createElement("div", { className: "xl:col-span-8 min-w-0" },
                React.createElement("svg", { "data-chart": "true", width: "600", height: "168", viewBox: "0 0 600 168", style: { width: '100%', height: 'auto', maxHeight: '138px' }, className: "w-full block", role: "img", "aria-label": "\u0413\u043E\u0440\u0438\u0437\u043E\u043D\u0442 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438 \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442 \u0414+1..\u0414+14 \u043F\u043E \u0437\u043E\u043D\u0430\u043C \u0445\u0440\u0430\u043D\u0435\u043D\u0438\u044F \u0438 \u0440\u0435\u0437\u0435\u0440\u0432\u0443 \u0432\u043E\u0440\u043E\u0442" },
                    React.createElement("rect", { x: "46", y: plotTop, width: "548", height: Math.max(6, limitY - plotTop), fill: "var(--status-warning-bg)", fillOpacity: "0.62" }),
                    React.createElement("line", { x1: "46", y1: plotTop, x2: "594", y2: plotTop, stroke: "var(--border-subtle)", strokeWidth: "1" }),
                    React.createElement("line", { x1: "46", y1: "77", x2: "594", y2: "77", stroke: "var(--border-subtle)", strokeWidth: "1" }),
                    React.createElement("line", { x1: "46", y1: plotBottom, x2: "594", y2: plotBottom, stroke: "var(--border-subtle)", strokeWidth: "1" }),
                    React.createElement("text", { x: "4", y: "26", fill: "var(--text-muted)", fontSize: "11", fontFamily: "var(--font-sans)" },
                        maxPalletScale,
                        "\u043F"),
                    React.createElement("text", { x: "4", y: "81", fill: "var(--text-muted)", fontSize: "11", fontFamily: "var(--font-sans)" },
                        Math.round(maxPalletScale / 2),
                        "\u043F"),
                    React.createElement("text", { x: "4", y: "135", fill: "var(--text-muted)", fontSize: "11", fontFamily: "var(--font-sans)" }, "0\u043F"),
                    React.createElement("line", { x1: "46", y1: ceilingY, x2: "594", y2: ceilingY, stroke: "var(--border-strong)", strokeWidth: "1", strokeOpacity: "0.35" }),
                    React.createElement("line", { x1: "46", y1: limitY, x2: "594", y2: limitY, stroke: "var(--status-warning-fg)", strokeWidth: "1.25", strokeDasharray: "4 4" }),
                    React.createElement("text", { x: "590", y: Math.max(14, limitY - 4), textAnchor: "end", fill: "var(--status-warning-fg)", fontSize: "11", fontFamily: "var(--font-sans)", fontWeight: "600" },
                        "\u041F\u043E\u0440\u043E\u0433 \u0432\u043E\u0440\u043E\u0442 ",
                        summary.effectivePalletLimit,
                        " \u043F\u0430\u043B\u043B"),
                    React.createElement("line", { "data-chart-crosshair": "true", x1: activePt.cx, y1: plotTop, x2: activePt.cx, y2: plotBottom, stroke: "var(--accent-primary)", strokeWidth: "1.25", strokeDasharray: "3 3" }),
                    React.createElement("path", { d: linePath, fill: "none", stroke: "var(--text-primary)", strokeWidth: "1.4", strokeOpacity: "0.45" }),
                    points.map((pt, idx) => {
                        const isSelected = idx === safeIdx;
                        const overGate = pt.totalPallets > summary.effectivePalletLimit + 0.05;
                        const totalTop = mapY(pt.totalPallets);
                        const totalH = Math.max(6, plotBottom - totalTop);
                        const dryH = Math.max(3, Math.round((pt.dryPallets / Math.max(0.1, pt.totalPallets)) * totalH));
                        const coldH = Math.max(2, Math.round((pt.coldPallets / Math.max(0.1, pt.totalPallets)) * totalH));
                        const quarH = Math.max(2, totalH - dryH - coldH);
                        return (React.createElement("g", { key: pt.dayLabel, "data-chart-point": pt.dayLabel, "data-chart-node": pt.linkedSkuId, "data-canvas-node": pt.linkedSkuId, tabIndex: 0, role: "button", "aria-label": `Горизонт ${pt.dayLabel}: занято ${pt.totalPallets} паллет, резерв ворот ${pt.freeGateReserve} паллет`, onMouseEnter: () => setActiveIdx(idx), onFocus: () => setActiveIdx(idx), onClick: () => { setActiveIdx(idx); onSelectSku(pt.linkedSkuId); }, onKeyDown: (e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    setActiveIdx(idx);
                                    onSelectSku(pt.linkedSkuId);
                                }
                            }, className: "cursor-pointer" },
                            React.createElement("rect", { x: pt.cx - 52, y: "14", width: "104", height: "142", fill: "transparent" }),
                            React.createElement("rect", { x: pt.cx - 15, y: plotBottom - dryH, width: "30", height: dryH, rx: "1", fill: (0, capacityHorizonModel_1.resolvePointBarColor)(isSelected, overGate), fillOpacity: isSelected ? '0.92' : '0.68' }),
                            React.createElement("rect", { x: pt.cx - 15, y: plotBottom - dryH - coldH, width: "30", height: coldH, fill: isSelected ? 'var(--accent-primary)' : 'var(--text-secondary)', fillOpacity: isSelected ? '0.62' : '0.42' }),
                            React.createElement("rect", { x: pt.cx - 15, y: totalTop, width: "30", height: quarH, rx: "1", fill: "var(--status-warning-fg)", fillOpacity: isSelected ? '0.82' : '0.52' }),
                            React.createElement("circle", { cx: pt.cx, cy: totalTop, r: isSelected ? 3.5 : 2.5, fill: isSelected ? 'var(--accent-primary)' : 'var(--surface-1)', stroke: isSelected ? 'var(--surface-1)' : 'var(--text-primary)', strokeWidth: "1.25" }),
                            React.createElement("text", { x: pt.cx, y: Math.max(14, totalTop - 6), textAnchor: "middle", fill: isSelected ? 'var(--accent-primary)' : 'var(--text-primary)', fontSize: "11", fontFamily: "var(--font-sans)", fontWeight: "600" }, pt.totalPallets.toFixed(1)),
                            React.createElement("text", { x: pt.cx, y: "151", textAnchor: "middle", fill: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)', fontSize: "11", fontFamily: "var(--font-sans)", fontWeight: isSelected ? '700' : '500' }, pt.dayLabel)));
                    }))),
            React.createElement(CapacityHorizonGauges_1.CapacityHorizonGauges, { gauges: gauges })),
        React.createElement("div", { "data-chart-readout": "true", className: "chart-readout text-sm" },
            React.createElement("span", { className: "font-semibold text-primary" },
                "\u0413\u043E\u0440\u0438\u0437\u043E\u043D\u0442: ",
                activePt.dayLabel),
            React.createElement("span", null,
                "\u0421\u0443\u0445\u043E\u0439: ",
                React.createElement("strong", { className: "text-primary" },
                    activePt.dryPallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("span", null,
                "\u0425\u043E\u043B\u043E\u0434: ",
                React.createElement("strong", { className: "text-primary" },
                    activePt.coldPallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("span", null,
                "\u041A\u0430\u0440\u0430\u043D\u0442\u0438\u043D: ",
                React.createElement("strong", { className: "text-primary" },
                    activePt.quarantinePallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("span", null,
                "\u0420\u0435\u0437\u0435\u0440\u0432 \u0432\u043E\u0440\u043E\u0442: ",
                React.createElement("strong", { className: "text-primary" },
                    activePt.freeGateReserve.toFixed(1),
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("span", null,
                "\u0414\u043E\u043A\u0438 \u0420\u0426: ",
                React.createElement("strong", { className: "text-primary" },
                    activePt.dockLoadPct,
                    "%")))));
}

  };

  moduleFactories["components/CapacityHorizonGauges"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CapacityHorizonGauges = CapacityHorizonGauges;
function CapacityHorizonGauges({ gauges }) {
    return (React.createElement("div", { className: "xl:col-span-4 min-w-0" },
        React.createElement("div", { className: "surface-inset p-3 space-y-2.5 tabular-nums" }, gauges.map((g) => {
            const fillPct = Math.max(4, Math.min(100, Math.round(g.ratio * 84)));
            return (React.createElement("div", { key: g.id, className: "space-y-1" },
                React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-1 text-sm" },
                    React.createElement("span", { className: "text-secondary font-medium" }, g.label),
                    React.createElement("span", { className: g.over ? 'font-semibold text-status-danger' : 'font-semibold text-primary' }, g.valueText)),
                React.createElement("div", { className: "w-full h-2 bg-surface-2 radius-control overflow-hidden" },
                    React.createElement("div", { style: { width: `${fillPct}%` }, className: `h-full ${g.over ? 'bg-status-danger' : 'bg-accent-primary'}` }))));
        }))));
}

  };

  moduleFactories["components/capacityHorizonModel"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.HORIZON_DAYS = void 0;
exports.resolvePointBarColor = resolvePointBarColor;
exports.buildHorizonPoints = buildHorizonPoints;
exports.buildCapacityGauges = buildCapacityGauges;
exports.computeActiveSkuTelemetry = computeActiveSkuTelemetry;
const replenishmentEngine_1 = require("../store/replenishmentEngine");
exports.HORIZON_DAYS = [1, 4, 7, 10, 14];
function resolvePointBarColor(isSelected, overGate) {
    if (isSelected)
        return 'var(--accent-primary)';
    if (overGate)
        return 'var(--status-danger-fg)';
    return 'var(--border-strong)';
}
function buildHorizonPoints(state, summary) {
    return exports.HORIZON_DAYS.map((day, idx) => {
        let dryRaw = 0;
        let coldRaw = 0;
        let quarantineRaw = 0;
        let inboundArrivingPallets = 0;
        for (const item of state.items) {
            const lead = (0, replenishmentEngine_1.computeEffectiveLeadDays)(item, state.transitDelayDays, state.backupChannel);
            const shelfUnits = Math.max(0, item.currentStock - item.dailyDemand * (day - 1) * 0.62);
            const orderLanded = day >= lead ? item.orderQty : item.orderQty * Math.min(0.86, day / Math.max(2, lead + 1));
            const postArrivalDrain = day > lead ? item.dailyDemand * (day - lead) * 0.52 : 0;
            const units = Math.max(6, shelfUnits + orderLanded - postArrivalDrain);
            const itemPallets = units / Math.max(1, item.unitsPerPallet);
            const isArrivalWindow = Math.abs(day - lead) <= 2;
            if (isArrivalWindow) {
                inboundArrivingPallets += (item.orderQty / Math.max(1, item.unitsPerPallet)) * 0.45;
            }
            const qShare = isArrivalWindow ? 0.18 : 0.09;
            quarantineRaw += itemPallets * qShare;
            if (item.category === 'Измерения' || item.category === 'Автоматика') {
                coldRaw += itemPallets * (1 - qShare) * 0.72;
                dryRaw += itemPallets * (1 - qShare) * 0.28;
            }
            else {
                dryRaw += itemPallets * (1 - qShare) * 0.88;
                coldRaw += itemPallets * (1 - qShare) * 0.12;
            }
        }
        const rawSum = Math.max(1, dryRaw + coldRaw + quarantineRaw);
        const waveAnchor = day === 4 || day === 7 ? Math.max(rawSum, summary.totalPallets) : rawSum;
        const scale = waveAnchor / rawSum;
        const dryPallets = Number((dryRaw * scale).toFixed(1));
        const coldPallets = Number((coldRaw * scale).toFixed(1));
        const quarantinePallets = Number(Math.max(0.8, quarantineRaw * scale).toFixed(1));
        const totalPallets = Number((dryPallets + coldPallets + quarantinePallets).toFixed(1));
        const freeGateReserve = Number(Math.max(0, state.constraints.maxPallets - totalPallets).toFixed(1));
        const dockLoadPct = Math.min(116, Math.max(42, Math.round((totalPallets / Math.max(1, summary.effectivePalletLimit)) * 82 +
            inboundArrivingPallets * 1.4)));
        const linkedItem = state.items[idx % Math.max(1, state.items.length)];
        return {
            day,
            dayLabel: `Д+${day}`,
            cx: 98 + idx * 112,
            totalPallets,
            dryPallets,
            coldPallets,
            quarantinePallets,
            freeGateReserve,
            dockLoadPct,
            linkedSkuId: linkedItem ? linkedItem.id : 'sku-power-ctrl'
        };
    });
}
function buildCapacityGauges(state, summary) {
    return [
        {
            id: 'g-pallet',
            label: 'Паллеты приемки',
            valueText: `${summary.totalPallets.toFixed(1)} / ${summary.effectivePalletLimit}`,
            ratio: summary.totalPallets / Math.max(1, summary.effectivePalletLimit),
            over: summary.totalPallets > summary.effectivePalletLimit + 0.05
        },
        {
            id: 'g-weight',
            label: 'Тоннаж рампы',
            valueText: `${(summary.totalWeightKg / 1000).toFixed(1)} / ${(state.constraints.maxWeightKg / 1000).toFixed(1)} т`,
            ratio: summary.totalWeightKg / Math.max(1, state.constraints.maxWeightKg),
            over: summary.totalWeightKg > state.constraints.maxWeightKg
        },
        {
            id: 'g-budget',
            label: 'Бюджет волны',
            valueText: `${Math.round(summary.totalBudgetKrub)} / ${state.constraints.maxBudgetKrub} тыс.`,
            ratio: summary.totalBudgetKrub / Math.max(1, state.constraints.maxBudgetKrub),
            over: summary.totalBudgetKrub > state.constraints.maxBudgetKrub + 0.05
        }
    ];
}
function computeActiveSkuTelemetry(state) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const activeSku = state.items.find((i) => i.id === state.activeSkuId) || state.items[0];
    const activeLead = activeSku
        ? (0, replenishmentEngine_1.computeEffectiveLeadDays)(activeSku, state.transitDelayDays, state.backupChannel)
        : 6;
    const activeCoverDays = activeSku
        ? Number(((activeSku.currentStock + activeSku.orderQty) / Math.max(1, activeSku.dailyDemand)).toFixed(1))
        : 0;
    return { summary, activeSku, activeLead, activeCoverDays };
}

  };

  moduleFactories["components/CmdKPalette"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.CmdKPalette = CmdKPalette;
const react_1 = __importStar(require("react"));
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
const Icons_1 = require("./Icons");
function CmdKPalette({ open, onClose, onOpenCreate, onOpenWhatIf }) {
    const [query, setQuery] = (0, react_1.useState)('');
    const [selectedIndex, setSelectedIndex] = (0, react_1.useState)(0);
    const searchInputRef = (0, react_1.useRef)(null);
    const dialogRef = (0, a11yDialog_1.useDialogFocusTrap)(open);
    (0, react_1.useEffect)(() => {
        if (open) {
            setQuery('');
            setSelectedIndex(0);
            searchInputRef.current?.focus();
        }
    }, [open]);
    if (!open)
        return null;
    const q = query.trim().toLowerCase();
    const actions = [
        {
            id: 'cmd-balance',
            label: 'Сбалансировать заказ по складу',
            hint: 'Уложить паллеты',
            run: () => domainStore_1.inventoryStore.balanceOrder()
        },
        {
            id: 'cmd-reconcile-map',
            label: 'Выровнять потоки сети на карте поставок',
            hint: 'Вход и отгрузки',
            run: () => {
                domainStore_1.inventoryStore.setScreen('screen-supply-map');
                domainStore_1.inventoryStore.reconcileNetworkFlows();
            }
        },
        {
            id: 'cmd-create',
            label: 'Добавить позицию в закупочную ведомость',
            hint: 'Новая строка',
            run: () => onOpenCreate()
        },
        {
            id: 'cmd-whatif',
            label: 'What-If симулятор сценариев (Alt+S)',
            hint: 'Alt+S',
            run: () => onOpenWhatIf()
        },
        ...presets_1.SCENARIO_PRESETS.map((p) => ({
            id: `cmd-${p.id}`,
            label: `Сценарий: ${p.label}`,
            hint: `${p.constraints.maxPallets} палл.`,
            run: () => domainStore_1.inventoryStore.loadPreset(p.id)
        })),
        ...presets_1.SCREEN_DEFINITIONS.map((s) => ({
            id: `cmd-nav-${s.id}`,
            label: `Раздел: ${s.label}`,
            hint: s.shortcut,
            run: () => domainStore_1.inventoryStore.setScreen(s.id)
        }))
    ].filter((item) => !q || item.label.toLowerCase().includes(q));
    const safeIdx = actions.length > 0 ? Math.min(selectedIndex, actions.length - 1) : 0;
    const handleInputKeyDown = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (actions.length > 0)
                setSelectedIndex((prev) => (prev + 1) % actions.length);
        }
        else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (actions.length > 0)
                setSelectedIndex((prev) => (prev - 1 + actions.length) % actions.length);
        }
        else if (e.key === 'Enter') {
            e.preventDefault();
            const target = actions[safeIdx];
            if (target) {
                target.run();
                onClose();
            }
        }
    };
    return (react_1.default.createElement("div", { ref: dialogRef, "data-cmdk-palette": "true", role: "dialog", "aria-modal": "true", "aria-label": "\u0411\u044B\u0441\u0442\u0440\u044B\u0435 \u043A\u043E\u043C\u0430\u043D\u0434\u044B \u0417\u0430\u043F\u0430\u0441-\u041D\u0430\u0432\u0438\u0433\u0430\u0442\u043E\u0440", onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, className: "fixed inset-0 z-50 flex items-start justify-center pt-14 p-4 bg-canvas/80" },
        react_1.default.createElement("div", { "data-ui": "surface", className: "surface-card p-3 w-full max-w-lg space-y-2" },
            react_1.default.createElement("div", { className: "flex items-center gap-2" },
                react_1.default.createElement(Icons_1.SearchCmdIcon, { size: 15, className: "text-muted" }),
                react_1.default.createElement("input", { ref: searchInputRef, "data-cmdk-input": "true", id: "cmdk-search-input", type: "search", role: "combobox", "aria-expanded": "true", "aria-controls": "cmdk-listbox", "aria-activedescendant": actions.length > 0 ? `cmdk-opt-${actions[safeIdx]?.id}` : undefined, autoFocus: true, value: query, onChange: (e) => {
                        setQuery(e.target.value);
                        setSelectedIndex(0);
                    }, onKeyDown: handleInputKeyDown, "aria-label": "\u041F\u043E\u0438\u0441\u043A \u043A\u043E\u043C\u0430\u043D\u0434\u044B \u0438\u043B\u0438 \u0440\u0430\u0437\u0434\u0435\u043B\u0430", placeholder: "\u0421\u0446\u0435\u043D\u0430\u0440\u0438\u0439, \u0440\u0430\u0437\u0434\u0435\u043B \u0438\u043B\u0438 \u043A\u043E\u043C\u0430\u043D\u0434\u0430...", className: "flex-1 field-compact" }),
                react_1.default.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: onClose, className: "btn-ghost radius-control" },
                    react_1.default.createElement("kbd", { className: "text-xs text-muted tabular-nums" }, "Esc"))),
            react_1.default.createElement("div", { id: "cmdk-listbox", role: "listbox", "aria-label": "\u0414\u043E\u0441\u0442\u0443\u043F\u043D\u044B\u0435 \u043A\u043E\u043C\u0430\u043D\u0434\u044B", className: "max-h-64 overflow-y-auto space-y-0.5" }, actions.length === 0 ? (react_1.default.createElement("div", { className: "px-2.5 py-3 text-sm text-muted" }, "\u041A\u043E\u043C\u0430\u043D\u0434\u044B \u043F\u043E \u0437\u0430\u043F\u0440\u043E\u0441\u0443 \u043D\u0435 \u043D\u0430\u0439\u0434\u0435\u043D\u044B, \u043D\u0430\u0436\u043C\u0438\u0442\u0435 Esc \u0434\u043B\u044F \u0437\u0430\u043A\u0440\u044B\u0442\u0438\u044F")) : (actions.map((act, idx) => {
                const isSelected = idx === safeIdx;
                return (react_1.default.createElement("button", { key: act.id, id: `cmdk-opt-${act.id}`, type: "button", role: "option", "aria-selected": isSelected, onMouseEnter: () => setSelectedIndex(idx), onClick: () => {
                        act.run();
                        onClose();
                    }, className: `btn-ghost w-full justify-between radius-control px-2.5 h-8 text-left ${isSelected ? 'surface-inset text-primary' : ''}` },
                    react_1.default.createElement("span", { className: "text-sm font-medium text-primary" }, act.label),
                    react_1.default.createElement("kbd", { className: "text-xs text-muted tabular-nums shrink-0" }, act.hint)));
            }))))));
}

  };

  moduleFactories["components/CorridorSlaMatrixCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CorridorSlaMatrixCard = CorridorSlaMatrixCard;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
const CORRIDOR_META = {
    'balt-komplekt': { corridorName: 'Северо-Западный коридор', hubRoute: 'СПб Шушары – ворота РЦ', slaTargetPct: 98.0, normBufferDays: 6 },
    'ural-privod': { corridorName: 'Уральский магистральный ход', hubRoute: 'Екатеринбург – сортировка РЦ', slaTargetPct: 94.5, normBufferDays: 8 },
    'volga-pribor': { corridorName: 'Волжское направление', hubRoute: 'Казань – транзитный терминал', slaTargetPct: 91.0, normBufferDays: 10 },
    'sever-snab': { corridorName: 'Северный экспресс-канал', hubRoute: 'Ярославль – прямая рампа РЦ', slaTargetPct: 98.5, normBufferDays: 6 }
};
function CorridorSlaMatrixCard({ items, activeSkuId, transitDelayDays, backupChannel, channelLabel, channelLeadDeltaDays, channelCostSurchargePct }) {
    return (React.createElement("article", { "data-card": "corridor-sla-matrix", className: "surface-card p-3.5 space-y-2.5" },
        React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2" },
            React.createElement("div", null,
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u041C\u0430\u0442\u0440\u0438\u0446\u0430 \u0441\u043E\u0431\u043B\u044E\u0434\u0435\u043D\u0438\u044F SLA \u043A\u043E\u0440\u0438\u0434\u043E\u0440\u043E\u0432 \u0438 \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u044B\u0445 \u0431\u0443\u0444\u0435\u0440\u043E\u0432 \u043F\u043E \u043D\u0430\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u044F\u043C"),
                React.createElement("p", { className: "text-xs text-muted" },
                    "\u0421\u043E\u0431\u043B\u044E\u0434\u0435\u043D\u0438\u0435 \u043A\u043E\u0440\u0438\u0434\u043E\u0440\u043E\u0432 \u043F\u043E \u043A\u0430\u043D\u0430\u043B\u0443 \u00AB",
                    channelLabel,
                    "\u00BB")),
            React.createElement("span", { className: "text-xs text-secondary tabular-nums" },
                "\u041D\u0430\u0434\u0431\u0430\u0432\u043A\u0430 \u043B\u043E\u0433\u0438\u0441\u0442\u0438\u043A\u0438: +",
                channelCostSurchargePct,
                "%")),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041D\u0430\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u0435 \u0438 \u043F\u043B\u043E\u0449\u0430\u0434\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041C\u0430\u0440\u0448\u0440\u0443\u0442\u043D\u044B\u0439 \u0443\u0437\u0435\u043B"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041D\u043E\u0440\u043C\u0430 SLA"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u043B\u0435\u0447\u043E \u0444\u0430\u043A\u0442"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041D\u043E\u0440\u043C\u0430\u0442\u0438\u0432 \u0431\u0443\u0444\u0435\u0440\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0418\u043D\u0434\u0435\u043A\u0441 OTIF"))),
                React.createElement("tbody", null, presets_1.SUPPLIER_LIST.map((sup, idx) => {
                    const meta = CORRIDOR_META[sup.id];
                    const effectiveCorridorDays = Math.max(2, sup.leadDays + transitDelayDays + channelLeadDeltaDays);
                    const linkedSku = items.find((it) => it.supplierId === sup.id) || items[0];
                    const isSelected = Boolean(linkedSku && linkedSku.id === activeSkuId);
                    const effectiveOtif = Number(Math.max(82, sup.reliabilityPct - transitDelayDays * 0.6 + (backupChannel === 'direct_rail' ? 0 : 1.8)).toFixed(1));
                    return (React.createElement("tr", { key: sup.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: 0, "aria-current": isSelected ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => { if (linkedSku)
                            domainStore_1.inventoryStore.selectSku(linkedSku.id); }, onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => { if (linkedSku)
                            domainStore_1.inventoryStore.selectSku(linkedSku.id); }), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left text-sm font-semibold text-primary" },
                            meta.corridorName,
                            ", ",
                            sup.name),
                        React.createElement("td", { className: "text-left text-sm text-secondary" }, meta.hubRoute),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            sup.leadDays,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: `text-right text-sm font-semibold whitespace-nowrap tabular-nums ${effectiveCorridorDays > sup.leadDays + 2 ? 'text-status-warning' : 'text-primary'}` },
                            effectiveCorridorDays,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            meta.normBufferDays,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                            effectiveOtif.toFixed(1),
                            "%")));
                }))))));
}

  };

  moduleFactories["components/ErpDispatchLedgerCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ErpDispatchLedgerCard = ErpDispatchLedgerCard;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const a11yDialog_1 = require("../utils/a11yDialog");
function ErpDispatchLedgerCard({ items, activeSkuId, transitDelayDays, backupChannel, avgReliabilityPct }) {
    return (React.createElement("article", { "data-card": "erp-dispatch-ledger", className: "surface-card p-3.5 space-y-2.5" },
        React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2" },
            React.createElement("div", null,
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0412\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C \u0441\u0442\u0440\u043E\u043A \u0437\u0430\u043A\u0430\u0437\u0430 \u043A \u043F\u0435\u0440\u0435\u0434\u0430\u0447\u0435 \u0432 \u043A\u043E\u043D\u0442\u0443\u0440 ERP \u0438 \u043F\u0440\u0438\u0435\u043C\u043A\u0438 \u0420\u0426"),
                React.createElement("p", { className: "text-sm text-secondary" }, "\u041A\u043E\u043D\u0442\u0440\u043E\u043B\u044C\u043D\u044B\u0439 \u0440\u0435\u0435\u0441\u0442\u0440 \u043F\u0430\u0440\u0442\u0438\u0439, \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442 \u0438 \u0441\u0443\u043C\u043C \u043F\u0435\u0440\u0435\u0434 \u043E\u0442\u043F\u0440\u0430\u0432\u043A\u043E\u0439")),
            React.createElement("span", { className: "text-sm font-medium text-secondary tabular-nums" },
                "\u041D\u0430\u0434\u0435\u0436\u043D\u043E\u0441\u0442\u044C \u043F\u0443\u043B\u0430: ",
                avgReliabilityPct.toFixed(1),
                "%")),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041D\u043E\u043C\u0435\u043D\u043A\u043B\u0430\u0442\u0443\u0440\u0430 \u0437\u0430\u043A\u0430\u0437\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u0440\u0442\u0438\u044F"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041C\u0430\u0441\u0441\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0421\u0440\u043E\u043A"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0421\u0443\u043C\u043C\u0430"))),
                React.createElement("tbody", null, items.map((item, idx) => {
                    const sup = (0, presets_1.getSupplier)(item.supplierId);
                    const pallets = (0, replenishmentEngine_1.computeItemPallets)(item);
                    const weight = (0, replenishmentEngine_1.computeItemWeightKg)(item);
                    const cost = (0, replenishmentEngine_1.computeItemCostKrub)(item, backupChannel);
                    const lead = (0, replenishmentEngine_1.computeEffectiveLeadDays)(item, transitDelayDays, backupChannel);
                    const isSelected = item.id === activeSkuId;
                    return (React.createElement("tr", { key: item.id, "data-entity-id": item.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: 0, "aria-current": isSelected ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSku(item.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSku(item.id)), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left text-sm font-semibold text-primary" }, item.name),
                        React.createElement("td", { className: "text-left text-sm text-secondary whitespace-nowrap" }, sup.name),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            item.orderQty,
                            " \u0448\u0442."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            pallets.toFixed(1),
                            " \u043F\u0430\u043B\u043B."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            weight,
                            " \u043A\u0433"),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            lead,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                            cost.toFixed(1),
                            " \u0442\u044B\u0441. \u20BD")));
                }))))));
}

  };

  moduleFactories["components/FlowCorridorInspector"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FlowCorridorInspector = FlowCorridorInspector;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const Icons_1 = require("./Icons");
const FlowCorridorSubpanels_1 = require("./FlowCorridorSubpanels");
function FlowCorridorInspector({ state, summary, lens, activeSku, selectedNodeId, selectedInbound, selectedOutbound, outbound, dependentCustomers, outboundPallets, outboundValueKrub }) {
    const renderInspectorBody = () => {
        if (lens === 'sku_peg') {
            return React.createElement(FlowCorridorSubpanels_1.SkuPeggingPanel, { state: state, activeSku: activeSku, outbound: outbound });
        }
        if (selectedInbound) {
            return (React.createElement(FlowCorridorSubpanels_1.InboundCorridorPanel, { selectedInbound: selectedInbound, dependentCustomers: dependentCustomers }));
        }
        if (selectedOutbound) {
            return React.createElement(FlowCorridorSubpanels_1.OutboundCorridorPanel, { selectedOutbound: selectedOutbound });
        }
        return (React.createElement(FlowCorridorSubpanels_1.CentralHubPanel, { state: state, summary: summary, outbound: outbound, outboundPallets: outboundPallets, outboundValueKrub: outboundValueKrub }));
    };
    return (React.createElement("article", { "data-card": "flow-corridor-inspector", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-2.5" },
        React.createElement("div", { className: "space-y-2.5" },
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("div", { className: "flex items-center gap-1.5" },
                    React.createElement(Icons_1.RouteMapIcon, { size: 15, className: "text-accent-primary" }),
                    React.createElement("span", { className: "text-xs font-medium text-secondary" }, (0, FlowCorridorSubpanels_1.resolveHeaderTitle)(lens, selectedInbound, selectedOutbound))),
                lens === 'sku_peg' ? (React.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: () => domainStore_1.inventoryStore.setMapLens('all'), className: "btn-ghost radius-control text-xs" }, "\u0412\u0441\u0435 \u043F\u043E\u0442\u043E\u043A\u0438")) : (selectedNodeId !== 'dc-moscow' && (React.createElement("button", { type: "button", "data-ui": "btn-ghost", onClick: () => domainStore_1.inventoryStore.selectMapNode('dc-moscow'), className: "btn-ghost radius-control text-xs" }, "\u0421\u0432\u043E\u0434\u043A\u0430 \u0420\u0426")))),
            renderInspectorBody()),
        React.createElement("div", { className: "space-y-2 pt-0.5" },
            React.createElement("div", { className: "space-y-1" },
                React.createElement("label", { htmlFor: "map-channel-select", className: "block text-xs font-medium text-secondary" }, "\u041A\u0430\u043D\u0430\u043B \u043F\u043E\u0434\u0432\u043E\u0437\u0430 \u0434\u043E \u0420\u0426"),
                React.createElement("select", { id: "map-channel-select", value: state.backupChannel, onChange: (e) => domainStore_1.inventoryStore.setTransitScenario(state.transitDelayDays, e.target.value), className: "w-full field-compact" }, Object.values(presets_1.BACKUP_CHANNELS).map((ch) => (React.createElement("option", { key: ch.id, value: ch.id },
                    ch.label,
                    " (",
                    ch.leadDeltaDays === 0 ? 'база' : `${ch.leadDeltaDays}д`,
                    ")"))))),
            React.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => domainStore_1.inventoryStore.reconcileNetworkFlows(), className: "btn-primary w-full radius-control" }, "\u0412\u044B\u0440\u043E\u0432\u043D\u044F\u0442\u044C \u043F\u043E\u0442\u043E\u043A\u0438 \u0441\u0435\u0442\u0438"))));
}

  };

  moduleFactories["components/FlowCorridorPeggingPanel"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SkuPeggingPanel = SkuPeggingPanel;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
function renderPegStatusText(shortfall, late, leadDays) {
    if (shortfall)
        return 'Дефицит шт.';
    if (late)
        return `Приход Д+${leadDays}`;
    return 'Обеспечено';
}
function SkuPeggingPanel({ state, activeSku, outbound }) {
    const activeSup = (0, presets_1.getSupplier)(activeSku.supplierId);
    const skuLeadDays = (0, replenishmentEngine_1.computeEffectiveLeadDays)(activeSku, state.transitDelayDays, state.backupChannel);
    const availableAfterOrder = activeSku.currentStock + activeSku.orderQty;
    const peggedCustomerArcs = outbound
        .map((out) => ({ out, line: out.lines.find((ln) => ln.skuId === activeSku.id) }))
        .filter((entry) => Boolean(entry.line));
    const totalPeggedDemand = peggedCustomerArcs.reduce((acc, entry) => acc + entry.line.requiredQty, 0);
    return (React.createElement("div", { className: "space-y-2.5", "data-sku-pegging-panel": "true" },
        React.createElement("div", null,
            React.createElement("h2", { className: "text-base font-semibold text-primary" }, activeSku.name),
            React.createElement("p", { className: "text-xs text-muted tabular-nums" },
                "\u0417\u0430\u0432\u043E\u0434: ",
                activeSup.name,
                " (",
                activeSup.city,
                "), \u043F\u0440\u0438\u0445\u043E\u0434 \u0414+",
                skuLeadDays)),
        React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041F\u043E\u043B\u043A\u0430 + \u043F\u0440\u0438\u0445\u043E\u0434 \u0432 \u0420\u0426"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    activeSku.currentStock,
                    " + ",
                    activeSku.orderQty,
                    " = ",
                    availableAfterOrder,
                    " \u0448\u0442.")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0421\u043F\u0440\u043E\u0441 \u0437\u0430\u043A\u0430\u0437\u043E\u0432 \u043A\u043B\u0438\u0435\u043D\u0442\u043E\u0432"),
                React.createElement("span", { className: `font-semibold ${availableAfterOrder < totalPeggedDemand ? 'text-status-danger' : 'text-status-success'}` },
                    totalPeggedDemand,
                    " \u0448\u0442. (",
                    peggedCustomerArcs.length,
                    " \u043D\u0430\u043F\u0440.)")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041E\u0431\u044A\u0435\u043C \u043F\u043B\u0435\u0447\u0430 \u043E\u0442 \u0437\u0430\u0432\u043E\u0434\u0430"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    (0, replenishmentEngine_1.computeItemPallets)(activeSku).toFixed(1),
                    " \u043F\u0430\u043B\u043B., \u043F\u043B\u0435\u0447\u043E ",
                    skuLeadDays,
                    " \u0441\u0443\u0442."))),
        React.createElement("div", { className: "space-y-1" },
            React.createElement("div", { className: "text-xs font-medium text-secondary" }, "\u0421\u0432\u044F\u0437\u0430\u043D\u043D\u044B\u0435 \u043A\u043B\u0438\u0435\u043D\u0442\u0441\u043A\u0438\u0435 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438:"),
            peggedCustomerArcs.length === 0 ? (React.createElement("div", { className: "surface-inset p-2 text-xs text-muted" }, "\u041F\u043E\u0437\u0438\u0446\u0438\u044F \u0444\u043E\u0440\u043C\u0438\u0440\u0443\u0435\u0442 \u0432\u043D\u0443\u0442\u0440\u0435\u043D\u043D\u0438\u0439 \u0440\u0435\u0437\u0435\u0440\u0432 \u0446\u0435\u043D\u0442\u0440\u0430\u043B\u044C\u043D\u043E\u0433\u043E \u0420\u0426 \u041F\u043E\u0434\u043E\u043B\u044C\u0441\u043A.")) : (React.createElement("div", { className: "space-y-1" }, peggedCustomerArcs.map(({ out, line }) => {
                const late = skuLeadDays > out.dispatchWindowDays;
                const blocked = late || line.shortfall;
                return (React.createElement("button", { key: `peg-${out.id}`, type: "button", onClick: () => domainStore_1.inventoryStore.selectMapNode(out.id), className: "w-full surface-inset px-2.5 py-2 flex items-center justify-between gap-2 text-left text-xs tabular-nums" },
                    React.createElement("span", { className: "font-medium text-primary" },
                        out.city,
                        ", \u043E\u043A\u043D\u043E ",
                        out.dispatchWindowLabel,
                        ": ",
                        line.requiredQty,
                        " \u0448\u0442."),
                    React.createElement("span", { className: blocked ? 'font-semibold text-status-danger' : 'font-semibold text-status-success' }, renderPegStatusText(line.shortfall, late, skuLeadDays))));
            }))))));
}

  };

  moduleFactories["components/FlowCorridorSubpanels"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SkuPeggingPanel = void 0;
exports.resolveHeaderTitle = resolveHeaderTitle;
exports.resolveOutboundStatusColor = resolveOutboundStatusColor;
exports.InboundCorridorPanel = InboundCorridorPanel;
exports.OutboundCorridorPanel = OutboundCorridorPanel;
exports.CentralHubPanel = CentralHubPanel;
const flowNetwork_1 = require("../data/flowNetwork");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
var FlowCorridorPeggingPanel_1 = require("./FlowCorridorPeggingPanel");
Object.defineProperty(exports, "SkuPeggingPanel", { enumerable: true, get: function () { return FlowCorridorPeggingPanel_1.SkuPeggingPanel; } });
function resolveHeaderTitle(lens, selectedInbound, selectedOutbound) {
    if (lens === 'sku_peg')
        return 'Сквозная трасса позиции';
    if (selectedInbound)
        return 'Входящий коридор';
    if (selectedOutbound)
        return 'Поставка заказчику';
    return 'Узел консолидации';
}
function resolveOutboundStatusColor(status) {
    if (status === 'ready')
        return 'text-status-success';
    if (status === 'gate_wait')
        return 'text-status-warning';
    return 'text-status-danger';
}
function InboundCorridorPanel({ selectedInbound, dependentCustomers }) {
    return (React.createElement("div", { className: "space-y-2.5" },
        React.createElement("div", null,
            React.createElement("h2", { className: "text-base font-semibold text-primary" },
                selectedInbound.supplierName,
                ", ",
                selectedInbound.city),
            React.createElement("p", { className: "text-xs text-muted tabular-nums" },
                selectedInbound.geo.highwayLabel,
                ", ",
                selectedInbound.geo.distanceKm,
                " \u043A\u043C,",
                ' ',
                selectedInbound.geo.gateLabel)),
        React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041E\u0431\u044A\u0435\u043C \u0432 \u0432\u043E\u043B\u043D\u0435"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    selectedInbound.pallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B., ",
                    selectedInbound.weightKg,
                    " \u043A\u0433")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0421\u0440\u043E\u043A \u0434\u043E \u0432\u043E\u0440\u043E\u0442 \u0420\u0426"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    selectedInbound.leadDays,
                    " \u0441\u0443\u0442., OTIF ",
                    selectedInbound.reliabilityPct,
                    "%")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0421\u0443\u043C\u043C\u0430 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    selectedInbound.budgetKrub.toFixed(1),
                    " \u0442\u044B\u0441. \u20BD"))),
        React.createElement("div", { className: "space-y-1" },
            React.createElement("div", { className: "text-xs font-medium text-secondary" },
                "\u041D\u043E\u043C\u0435\u043D\u043A\u043B\u0430\u0442\u0443\u0440\u0430 \u0432 \u043F\u0443\u0442\u0438, ",
                selectedInbound.skuCount,
                " \u043F\u043E\u0437.:"),
            selectedInbound.items.length === 0 ? (React.createElement("div", { className: "surface-inset p-2 text-xs text-muted" }, "\u0417\u0430\u043A\u0430\u0437\u044B \u0432\u043E\u043B\u043D\u044B \u0440\u0430\u0441\u043F\u0440\u0435\u0434\u0435\u043B\u0435\u043D\u044B \u043D\u0430 \u0441\u043E\u0441\u0435\u0434\u043D\u0438\u0435 \u043F\u043B\u043E\u0449\u0430\u0434\u043A\u0438")) : (React.createElement("div", { className: "space-y-1" }, selectedInbound.items.map((it) => (React.createElement("div", { key: it.id, className: "surface-inset px-2.5 py-1.5 flex items-center justify-between gap-2 text-xs tabular-nums" },
                React.createElement("span", { className: "font-medium text-primary" }, it.name),
                React.createElement("span", { className: "text-secondary shrink-0" },
                    it.orderQty,
                    " \u0448\u0442., ",
                    (0, replenishmentEngine_1.computeItemPallets)(it).toFixed(1),
                    " \u043F."))))))),
        React.createElement("div", { className: "space-y-1" },
            React.createElement("div", { className: "text-xs font-medium text-secondary" }, "\u0421\u0432\u044F\u0437\u0430\u043D\u043D\u044B\u0435 \u043F\u043E\u043B\u0443\u0447\u0430\u0442\u0435\u043B\u0438:"),
            React.createElement("div", { className: "flex flex-wrap gap-1.5" }, dependentCustomers.length === 0 ? (React.createElement("span", { className: "text-xs text-muted" }, "\u041F\u0440\u044F\u043C\u044B\u0445 \u0431\u043B\u043E\u043A\u0438\u0440\u043E\u0432\u043E\u043A \u043D\u0435\u0442")) : (dependentCustomers.map((dc) => (React.createElement("button", { key: dc.id, type: "button", onClick: () => domainStore_1.inventoryStore.selectMapNode(dc.id), className: "btn-row text-xs" },
                dc.city,
                ", ",
                dc.dispatchWindowLabel))))))));
}
function OutboundCorridorPanel({ selectedOutbound }) {
    return (React.createElement("div", { className: "space-y-2.5" },
        React.createElement("div", null,
            React.createElement("h2", { className: "text-base font-semibold text-primary" }, selectedOutbound.customerName),
            React.createElement("p", { className: "text-xs text-muted tabular-nums" },
                selectedOutbound.city,
                ", ",
                selectedOutbound.geo.highwayLabel,
                ", ",
                selectedOutbound.geo.distanceKm,
                " \u043A\u043C")),
        React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0421\u0442\u0430\u0442\u0443\u0441 \u043A\u043E\u043C\u043F\u043B\u0435\u043A\u0442\u0430\u0446\u0438\u0438"),
                React.createElement("span", { className: `font-semibold ${resolveOutboundStatusColor(selectedOutbound.status)}` }, selectedOutbound.statusLabel)),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041E\u043A\u043D\u043E \u0438 \u043E\u0431\u044A\u0435\u043C \u0432\u044B\u0432\u043E\u0437\u0430"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    selectedOutbound.dispatchWindowLabel,
                    ", ",
                    selectedOutbound.pallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0422\u043E\u0432\u0430\u0440\u043D\u0430\u044F \u0441\u0442\u043E\u0438\u043C\u043E\u0441\u0442\u044C"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    selectedOutbound.valueKrub.toFixed(1),
                    " \u0442\u044B\u0441. \u20BD"))),
        React.createElement("div", { className: "space-y-1" },
            React.createElement("div", { className: "text-xs font-medium text-secondary" }, "\u0421\u043E\u0441\u0442\u0430\u0432 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438 \u0438 \u0437\u0430\u0432\u043E\u0434\u044B:"),
            React.createElement("div", { className: "space-y-1" }, selectedOutbound.lines.map((ln) => (React.createElement("div", { key: `${selectedOutbound.id}-${ln.skuId}`, className: "surface-inset px-2.5 py-1.5 space-y-0.5 text-xs tabular-nums" },
                React.createElement("div", { className: "flex items-center justify-between gap-2" },
                    React.createElement("span", { className: "font-medium text-primary" }, ln.skuName),
                    React.createElement("span", { className: ln.shortfall ? 'font-semibold text-status-danger' : 'text-secondary' },
                        ln.requiredQty,
                        " \u0438\u0437 ",
                        ln.availableAfterOrder,
                        " \u0448\u0442.")),
                React.createElement("div", { className: "flex items-center justify-between gap-2 text-muted" },
                    React.createElement("span", null,
                        "\u0417\u0430\u0432\u043E\u0434: ",
                        ln.supplierCity,
                        ", ",
                        ln.leadDays,
                        " \u0441\u0443\u0442."),
                    React.createElement("button", { type: "button", onClick: () => domainStore_1.inventoryStore.selectMapNode(ln.supplierId), className: "btn-row text-xs" }, "\u041A \u0437\u0430\u0432\u043E\u0434\u0443")))))))));
}
function CentralHubPanel({ state, summary, outbound, outboundPallets, outboundValueKrub }) {
    return (React.createElement("div", { className: "space-y-2.5" },
        React.createElement("div", null,
            React.createElement("h2", { className: "text-base font-semibold text-primary" }, flowNetwork_1.CENTRAL_HUB_META.title),
            React.createElement("p", { className: "text-xs text-muted tabular-nums" },
                "\u041F\u043E\u0434\u043E\u043B\u044C\u0441\u043A, ",
                flowNetwork_1.CENTRAL_HUB_META.gateLabel)),
        React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041F\u0440\u0438\u0435\u043C\u043A\u0430 \u043E\u0442 \u0437\u0430\u0432\u043E\u0434\u043E\u0432"),
                React.createElement("span", { className: `font-semibold ${summary.overLimitCount === 0 ? 'text-status-success' : 'text-status-danger'}` },
                    summary.totalPallets.toFixed(1),
                    " / ",
                    summary.effectivePalletLimit,
                    " \u043F\u0430\u043B\u043B.")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u0422\u043E\u043D\u043D\u0430\u0436 \u043D\u0430 \u0440\u0430\u043C\u043F\u0435"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    summary.totalWeightKg,
                    " / ",
                    state.constraints.maxWeightKg,
                    " \u043A\u0433")),
            React.createElement("div", { className: "flex items-center justify-between gap-2" },
                React.createElement("span", { className: "text-secondary" }, "\u041E\u0442\u0433\u0440\u0443\u0437\u043A\u0438 \u0441\u043E \u0441\u043A\u043B\u0430\u0434\u0430"),
                React.createElement("span", { className: "font-semibold text-primary" },
                    outboundPallets.toFixed(1),
                    " \u043F\u0430\u043B\u043B., ",
                    outboundValueKrub.toFixed(0),
                    " \u0442\u044B\u0441. \u20BD"))),
        React.createElement("div", { className: "space-y-1" },
            React.createElement("div", { className: "text-xs font-medium text-secondary" }, "\u041E\u0447\u0435\u0440\u0435\u0434\u044C \u0432\u043E\u0440\u043E\u0442 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438:"),
            React.createElement("div", { className: "space-y-1" }, outbound.map((out) => (React.createElement("button", { key: out.id, type: "button", onClick: () => domainStore_1.inventoryStore.selectMapNode(out.id), className: "w-full surface-inset px-2.5 py-2 flex items-center justify-between gap-2 text-left text-xs tabular-nums" },
                React.createElement("span", { className: "font-medium text-primary" },
                    out.city,
                    ", ",
                    out.dispatchWindowLabel),
                React.createElement("span", { className: `${resolveOutboundStatusColor(out.status)} font-semibold` },
                    out.pallets.toFixed(1),
                    " \u043F."))))))));
}

  };

  moduleFactories["components/Icons"] = function(exports, module, require) {
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.LedgerGridIcon = LedgerGridIcon;
exports.ScaleBalanceIcon = ScaleBalanceIcon;
exports.WarehouseBoxIcon = WarehouseBoxIcon;
exports.SupplierTruckIcon = SupplierTruckIcon;
exports.ShieldClockIcon = ShieldClockIcon;
exports.CsvExportIcon = CsvExportIcon;
exports.PlusIcon = PlusIcon;
exports.UndoIcon = UndoIcon;
exports.SearchCmdIcon = SearchCmdIcon;
exports.RouteMapIcon = RouteMapIcon;
const react_1 = __importDefault(require("react"));
function LedgerGridIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("rect", { x: "3", y: "3", width: "18", height: "18", rx: "1" }),
        react_1.default.createElement("line", { x1: "3", y1: "9", x2: "21", y2: "9" }),
        react_1.default.createElement("line", { x1: "3", y1: "15", x2: "21", y2: "15" }),
        react_1.default.createElement("line", { x1: "9", y1: "9", x2: "9", y2: "21" })));
}
function ScaleBalanceIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("line", { x1: "12", y1: "3", x2: "12", y2: "21" }),
        react_1.default.createElement("line", { x1: "5", y1: "7", x2: "19", y2: "7" }),
        react_1.default.createElement("path", { d: "M5 7l-2 6h4l-2-6z" }),
        react_1.default.createElement("path", { d: "M19 7l-2 6h4l-2-6z" }),
        react_1.default.createElement("line", { x1: "8", y1: "21", x2: "16", y2: "21" })));
}
function WarehouseBoxIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("path", { d: "M3 9.5L12 4l9 5.5V20H3V9.5z" }),
        react_1.default.createElement("path", { d: "M9 20v-6h6v6" })));
}
function SupplierTruckIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("rect", { x: "2", y: "6", width: "13", height: "10", rx: "1" }),
        react_1.default.createElement("path", { d: "M15 9h4l3 3v4h-7V9z" }),
        react_1.default.createElement("circle", { cx: "7", cy: "18", r: "2" }),
        react_1.default.createElement("circle", { cx: "18", cy: "18", r: "2" })));
}
function ShieldClockIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("path", { d: "M12 3l7 3v6c0 4.5-3 7.8-7 9-4-1.2-7-4.5-7-9V6l7-3z" }),
        react_1.default.createElement("polyline", { points: "12 8 12 12 14.5 13.5" })));
}
function CsvExportIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("path", { d: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" }),
        react_1.default.createElement("polyline", { points: "14 3 14 9 20 9" }),
        react_1.default.createElement("path", { d: "M12 12v6" }),
        react_1.default.createElement("polyline", { points: "9.5 15.5 12 18 14.5 15.5" })));
}
function PlusIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("line", { x1: "12", y1: "5", x2: "12", y2: "19" }),
        react_1.default.createElement("line", { x1: "5", y1: "12", x2: "19", y2: "12" })));
}
function UndoIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("polyline", { points: "9 14 4 9 9 4" }),
        react_1.default.createElement("path", { d: "M20 20v-5a6 6 0 0 0-6-6H4" })));
}
function SearchCmdIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("circle", { cx: "11", cy: "11", r: "7" }),
        react_1.default.createElement("line", { x1: "16.5", y1: "16.5", x2: "21", y2: "21" })));
}
function RouteMapIcon({ size = 16, className = '' }) {
    return (react_1.default.createElement("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", className: className, "aria-hidden": "true" },
        react_1.default.createElement("circle", { cx: "5", cy: "7", r: "2.2" }),
        react_1.default.createElement("rect", { x: "10", y: "10", width: "4", height: "4", rx: "0.8" }),
        react_1.default.createElement("circle", { cx: "19", cy: "17", r: "2.2" }),
        react_1.default.createElement("path", { d: "M7.1 7.8C8.8 8.4 9.5 9.3 10.2 10.3" }),
        react_1.default.createElement("path", { d: "M13.8 13.7C14.8 14.9 15.8 15.8 16.9 16.3" }),
        react_1.default.createElement("circle", { cx: "19", cy: "6.5", r: "1.8" }),
        react_1.default.createElement("path", { d: "M13.9 10.4L17.3 7.7" })));
}

  };

  moduleFactories["components/InlineOrderQtyInput"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.InlineOrderQtyInput = InlineOrderQtyInput;
const react_1 = __importStar(require("react"));
const domainStore_1 = require("../store/domainStore");
function InlineOrderQtyInput({ item, step }) {
    const [draft, setDraft] = (0, react_1.useState)(String(item.orderQty));
    (0, react_1.useEffect)(() => {
        setDraft(String(item.orderQty));
    }, [item.orderQty]);
    const commit = () => {
        const parsed = Number(draft.replace(',', '.').trim());
        if (!Number.isFinite(parsed) || parsed <= 0) {
            setDraft(String(item.orderQty));
            return;
        }
        const clamped = Math.max(10, Math.min(990, Math.round(parsed)));
        setDraft(String(clamped));
        if (clamped !== item.orderQty) {
            domainStore_1.inventoryStore.setOrderQty(item.id, clamped);
        }
    };
    return (react_1.default.createElement("input", { type: "number", min: 10, max: 990, step: step, value: draft, "data-inline-qty-input": item.id, "aria-label": `Партия дозаказа ${item.name}, штук`, onChange: (e) => setDraft(e.target.value), onFocus: () => domainStore_1.inventoryStore.selectSku(item.id), onBlur: commit, onClick: (e) => {
            domainStore_1.inventoryStore.selectSku(item.id);
            e.stopPropagation();
        }, onKeyDown: (e) => {
            e.stopPropagation();
            if (e.key === 'Enter') {
                e.preventDefault();
                commit();
                e.currentTarget.blur();
            }
            else if (e.key === 'Escape') {
                e.preventDefault();
                setDraft(String(item.orderQty));
                e.currentTarget.blur();
            }
        }, className: "field-compact text-right font-semibold tabular-nums", style: { width: '68px', height: '26px', padding: '0 6px' } }));
}

  };

  moduleFactories["components/ReplenishmentInspectorColumn"] = function(exports, module, require) {
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReplenishmentInspectorColumn = ReplenishmentInspectorColumn;
const react_1 = __importDefault(require("react"));
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const Icons_1 = require("./Icons");
const SawtoothProjectionChart_1 = require("./SawtoothProjectionChart");
function ReplenishmentInspectorColumn({ state, activeSku, activeRecommendedQty }) {
    const activeSupplier = (0, presets_1.getSupplier)(activeSku.supplierId);
    const previewDiff = (0, replenishmentEngine_1.balanceOrderToWarehouse)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const beforeMetrics = state.lastBalanceDiff ? state.lastBalanceDiff.before : previewDiff.before;
    const afterMetrics = state.lastBalanceDiff ? state.lastBalanceDiff.after : previewDiff.after;
    const activeLineDiffs = state.lastBalanceDiff?.lineDiffs || previewDiff.lineDiffs;
    const isAlreadyBalanced = state.lastBalanceDiff !== null &&
        previewDiff.adjustedLinesCount === 0 &&
        previewDiff.after.overLimitCount === 0 &&
        previewDiff.after.stockoutRiskCount === 0;
    return (react_1.default.createElement("div", { className: "xl:col-span-4 flex flex-col justify-between gap-2.5 min-w-0" },
        react_1.default.createElement("article", { "data-card": "before-after-balance", "data-before-after-card": "true", className: "surface-card p-2.5 space-y-1.5" },
            react_1.default.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                react_1.default.createElement("div", { className: "flex items-center gap-1.5" },
                    react_1.default.createElement(Icons_1.ScaleBalanceIcon, { size: 15, className: "text-accent-primary" }),
                    react_1.default.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0411\u044B\u043B\u043E \u2192 \u0421\u0442\u0430\u043B\u043E")),
                react_1.default.createElement("span", { className: "text-xs text-muted tabular-nums" }, state.lastBalanceDiff
                    ? `Применено: ${state.lastBalanceDiff.adjustedLinesCount}`
                    : `Прогноз: ${previewDiff.adjustedLinesCount}`)),
            react_1.default.createElement("div", { className: "surface-inset p-2 space-y-1 tabular-nums text-sm" },
                react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                    react_1.default.createElement("span", { className: "text-secondary" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442\u0430"),
                    react_1.default.createElement("span", { "data-numeric": "true", className: "font-semibold text-primary" },
                        beforeMetrics.totalPallets.toFixed(1),
                        " \u2192 ",
                        afterMetrics.totalPallets.toFixed(1),
                        " \u043F.")),
                react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                    react_1.default.createElement("span", { className: "text-secondary" }, "\u0414\u0435\u0444\u0438\u0446\u0438\u0442 \u0438 \u043C\u0430\u0441\u0441\u0430"),
                    react_1.default.createElement("span", { "data-numeric": "true", className: "font-semibold text-primary" },
                        beforeMetrics.stockoutRiskCount,
                        " \u2192 ",
                        afterMetrics.stockoutRiskCount,
                        " \u043F\u043E\u0437.,",
                        ' ',
                        afterMetrics.totalWeightKg,
                        " \u043A\u0433")),
                activeLineDiffs.length > 0 && (react_1.default.createElement("div", { className: "pt-0.5 text-xs text-secondary", "data-diff-lines-summary": "true" },
                    activeLineDiffs.slice(0, 1).map((d) => {
                        const shortReason = (0, replenishmentEngine_1.formatShortBalanceReason)(d.reason);
                        return (react_1.default.createElement("div", { key: d.skuId, className: "space-y-0.5" },
                            react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                                react_1.default.createElement("span", null, d.skuName),
                                react_1.default.createElement("span", { className: "font-medium text-primary" },
                                    d.beforeQty,
                                    " \u2192 ",
                                    d.afterQty,
                                    " \u0448\u0442.")),
                            shortReason && react_1.default.createElement("div", { className: "text-muted leading-tight" }, shortReason)));
                    }),
                    activeLineDiffs.length > 1 && (react_1.default.createElement("div", { className: "text-muted" },
                        "+",
                        activeLineDiffs.length - 1,
                        " \u0441\u0442\u0440."))))),
            react_1.default.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => domainStore_1.inventoryStore.balanceOrder(), className: "btn-primary w-full radius-control" }, isAlreadyBalanced ? 'Сбалансировано, сверить' : 'Сбалансировать склад')),
        react_1.default.createElement("article", { "data-card": "active-sku-inspector", className: "surface-card p-2.5 space-y-1.5" },
            react_1.default.createElement("div", { className: "flex flex-wrap items-start justify-between gap-2" },
                react_1.default.createElement("h2", { className: "text-sm font-semibold text-primary min-w-0" }, activeSku.name),
                react_1.default.createElement("div", { className: "flex flex-wrap items-center gap-1" },
                    (activeSku.manualOverride || activeSku.orderQty !== activeRecommendedQty) && (react_1.default.createElement("button", { type: "button", "data-reset-recommended": "true", onClick: () => domainStore_1.inventoryStore.resetSkuToRecommended(activeSku.id), className: "btn-row tabular-nums" },
                        "\u041D\u043E\u0440\u043C\u0430 ",
                        activeRecommendedQty)),
                    react_1.default.createElement("button", { type: "button", "data-align-stochastic": "true", onClick: () => domainStore_1.inventoryStore.alignSkuToStochasticBuffer(activeSku.id), className: "btn-row tabular-nums" }, "\u03C3-\u043D\u043E\u0440\u043C\u0430"),
                    react_1.default.createElement("button", { type: "button", "data-open-sku-map": "true", onClick: () => domainStore_1.inventoryStore.openSkuTraceOnMap(activeSku.id), className: "btn-row" },
                        react_1.default.createElement(Icons_1.RouteMapIcon, { size: 12 }),
                        react_1.default.createElement("span", null, "\u041D\u0430 \u043A\u0430\u0440\u0442\u0435")))),
            react_1.default.createElement(SawtoothProjectionChart_1.SawtoothProjectionChart, { item: activeSku, transitDelayDays: state.transitDelayDays, backupChannel: state.backupChannel, compact: true }),
            react_1.default.createElement("div", { className: "space-y-1" },
                react_1.default.createElement("label", { htmlFor: "inspector-supplier-select", className: "block text-xs font-medium text-secondary" },
                    "\u041F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A, ",
                    activeSupplier.city),
                react_1.default.createElement("select", { id: "inspector-supplier-select", value: activeSku.supplierId, onChange: (e) => domainStore_1.inventoryStore.updateSkuSupplier(activeSku.id, e.target.value), className: "w-full field-compact" }, presets_1.SUPPLIER_LIST.map((sup) => (react_1.default.createElement("option", { key: sup.id, value: sup.id },
                    sup.name,
                    ", ",
                    sup.leadDays,
                    "\u0434"))))))));
}

  };

  moduleFactories["components/ReplenishmentLedgerRow"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReplenishmentLedgerRow = ReplenishmentLedgerRow;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const InlineOrderQtyInput_1 = require("./InlineOrderQtyInput");
function resolveCoverPillClass(atRisk, status) {
    if (atRisk)
        return 'bg-status-danger';
    if (status === 'overstock')
        return 'surface-inset text-secondary';
    return 'bg-status-success';
}
function ReplenishmentLedgerRow({ item, idx, isSelected, transitDelayDays, backupChannel, appliedDiff, onRowKeyDown }) {
    const atRisk = (0, replenishmentEngine_1.isSkuAtStockoutRisk)(item, transitDelayDays, backupChannel);
    const cover = (0, replenishmentEngine_1.computeDaysOfCover)(item, transitDelayDays, backupChannel);
    const pallets = (0, replenishmentEngine_1.computeItemPallets)(item);
    const lineCost = (0, replenishmentEngine_1.computeItemCostKrub)(item, backupChannel);
    const sup = (0, presets_1.getSupplier)(item.supplierId);
    const nonMultiple = item.orderQty % sup.minBatchQty !== 0;
    const coi = (0, replenishmentEngine_1.computeCostOfInaction)(item, transitDelayDays, backupChannel);
    return (React.createElement("tr", { "data-entity-id": item.id, "data-canvas-node": item.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: isSelected ? 0 : -1, "aria-selected": isSelected, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSku(item.id), onKeyDown: (e) => onRowKeyDown(e, item.id), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
        React.createElement("td", { className: "text-left" },
            React.createElement("div", { className: "flex flex-wrap items-center gap-1.5" },
                React.createElement("span", { className: "text-sm font-semibold text-primary" }, item.name),
                item.manualOverride && (React.createElement("span", { "data-manual-override": item.id, className: "px-1.5 py-0.5 radius-control text-xs font-medium bg-status-warning" }, "\u0440\u0443\u0447\u043D.")),
                coi.riskKrub > 0 && (React.createElement("span", { "data-sku-inaction-risk": item.id, className: "px-1.5 py-0.5 radius-control text-xs font-medium bg-status-danger tabular-nums" },
                    "\u0420\u0438\u0441\u043A ",
                    Math.round(coi.riskKrub),
                    "\u043A"))),
            appliedDiff ? (React.createElement("div", { "data-row-diff": item.id, className: "text-xs font-medium text-accent-primary tabular-nums" },
                "\u0411\u044B\u043B\u043E ",
                appliedDiff.beforeQty,
                " \u2192 ",
                appliedDiff.afterQty,
                " \u0448\u0442., ",
                (0, replenishmentEngine_1.formatShortBalanceReason)(appliedDiff.reason))) : (React.createElement("div", { className: "text-xs text-muted tabular-nums" },
                sup.name,
                ", \u043F\u043E\u043B\u043A\u0430 ",
                cover.runoutDays,
                "\u0434",
                nonMultiple ? `, шаг ${sup.minBatchQty}` : ''))),
        React.createElement("td", { className: "whitespace-nowrap text-right text-sm tabular-nums" },
            React.createElement("span", { "data-cover-pill": item.id, className: `px-2 py-0.5 radius-control text-sm font-semibold ${resolveCoverPillClass(atRisk, cover.status)}` },
                cover.totalCoverDays.toFixed(1),
                " \u0441\u0443\u0442.")),
        React.createElement("td", { "data-numeric": "true", className: "whitespace-nowrap text-right text-sm font-semibold text-primary tabular-nums" },
            React.createElement(InlineOrderQtyInput_1.InlineOrderQtyInput, { item: item, step: sup.minBatchQty })),
        React.createElement("td", { className: "whitespace-nowrap text-right text-sm text-secondary tabular-nums" },
            pallets.toFixed(1),
            " \u043F."),
        React.createElement("td", { className: "whitespace-nowrap text-right text-sm font-medium text-primary tabular-nums" },
            lineCost.toFixed(1),
            " \u0442\u044B\u0441."),
        React.createElement("td", { className: "whitespace-nowrap text-right tabular-nums" },
            React.createElement("div", { className: "inline-flex items-center justify-end gap-1" },
                React.createElement("button", { type: "button", "data-inline-control": `dec-${item.id}`, "aria-label": `-10: уменьшить партию ${item.name}`, onClick: (e) => { e.stopPropagation(); domainStore_1.inventoryStore.adjustOrderQty(item.id, -10); }, className: "btn-row tabular-nums" }, "-10"),
                React.createElement("button", { type: "button", "data-inline-control": `inc-${item.id}`, "aria-label": `+10: увеличить партию ${item.name}`, onClick: (e) => { e.stopPropagation(); domainStore_1.inventoryStore.adjustOrderQty(item.id, 10); }, className: "btn-row tabular-nums" }, "+10"),
                React.createElement("button", { type: "button", "data-inline-control": `buf-${item.id}`, "aria-label": `${item.safetyDays}д: страховой запас ${item.name}`, onClick: (e) => { e.stopPropagation(); domainStore_1.inventoryStore.cycleSafetyDays(item.id); }, className: "btn-row tabular-nums" },
                    item.safetyDays,
                    "\u0434")))));
}

  };

  moduleFactories["components/ReplenishmentLedgerTable"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReplenishmentLedgerTable = ReplenishmentLedgerTable;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const ReplenishmentLedgerRow_1 = require("./ReplenishmentLedgerRow");
function ReplenishmentLedgerTable({ state, summary, activeSku, activeRecommendedQty, triageFilter, onChangeTriageFilter }) {
    const tbodyRef = (0, react_1.useRef)(null);
    const handleRowKeyDown = (0, react_1.useCallback)((e, itemId) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const rows = tbodyRef.current
                ? Array.from(tbodyRef.current.querySelectorAll('tr[data-entity-id]'))
                : [];
            const currentIdx = rows.findIndex((r) => r.dataset.entityId === itemId);
            const nextIdx = e.key === 'ArrowDown' ? currentIdx + 1 : currentIdx - 1;
            if (nextIdx >= 0 && nextIdx < rows.length) {
                const nextId = rows[nextIdx].dataset.entityId;
                if (nextId) {
                    domainStore_1.inventoryStore.selectSku(nextId);
                    rows[nextIdx].focus();
                }
            }
        }
        else if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
            e.preventDefault();
            domainStore_1.inventoryStore.selectSku(itemId);
        }
    }, []);
    const appliedDiffMap = new Map((state.lastBalanceDiff?.lineDiffs || []).map((d) => [d.skuId, d]));
    const manualCount = state.items.filter((it) => Boolean(it.manualOverride)).length;
    const filteredItems = state.items.filter((it) => {
        if (triageFilter === 'deficit') {
            return (0, replenishmentEngine_1.isSkuAtStockoutRisk)(it, state.transitDelayDays, state.backupChannel);
        }
        if (triageFilter === 'manual')
            return Boolean(it.manualOverride);
        return true;
    });
    const activeSupplier = (0, presets_1.getSupplier)(activeSku.supplierId);
    const activeLeadDays = (0, replenishmentEngine_1.computeEffectiveLeadDays)(activeSku, state.transitDelayDays, state.backupChannel);
    const activeSafetyUnits = Math.round(activeSku.dailyDemand * activeSku.safetyDays);
    const activeTargetStock = activeSku.dailyDemand * activeLeadDays + activeSafetyUnits;
    const stoch = (0, replenishmentEngine_1.computeStochasticBuffer)(activeSku, state.transitDelayDays, state.backupChannel);
    const meterBars = [
        { label: 'Емкость', val: summary.totalPallets, max: summary.effectivePalletLimit },
        { label: 'Бюджет', val: summary.totalBudgetKrub, max: state.constraints.maxBudgetKrub },
        { label: 'Рампа', val: summary.totalWeightKg, max: state.constraints.maxWeightKg }
    ];
    return (React.createElement("article", { "data-card": "sku-replenishment-ledger", className: "surface-card p-3 flex flex-col gap-2.5" },
        React.createElement("div", { className: "space-y-2" },
            React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                React.createElement("div", { className: "flex flex-wrap items-center gap-2" },
                    React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0412\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C \u043F\u043E\u043F\u043E\u043B\u043D\u0435\u043D\u0438\u044F"),
                    React.createElement("span", { className: `px-2 py-0.5 radius-control text-xs font-medium tabular-nums ${summary.isFeasible ? 'bg-status-success' : 'bg-status-warning'}` }, summary.isFeasible
                        ? 'В допуске склада'
                        : `Дефицит ${summary.stockoutRiskCount}, перегруз ${summary.overLimitCount}`)),
                React.createElement("div", { className: "flex flex-wrap items-center gap-1.5" },
                    React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0422\u0440\u0438\u0430\u0436 \u043F\u043E\u0437\u0438\u0446\u0438\u0439 \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u0438" },
                        React.createElement("button", { type: "button", "data-triage-filter": "all", "aria-pressed": triageFilter === 'all', onClick: () => onChangeTriageFilter('all'), className: "seg-btn tabular-nums" },
                            "\u0412\u0441\u0435 ",
                            state.items.length),
                        React.createElement("button", { type: "button", "data-triage-filter": "deficit", "aria-pressed": triageFilter === 'deficit', onClick: () => onChangeTriageFilter('deficit'), className: "seg-btn tabular-nums" },
                            "\u0414\u0435\u0444\u0438\u0446\u0438\u0442 ",
                            summary.stockoutRiskCount),
                        React.createElement("button", { type: "button", "data-triage-filter": "manual", "aria-pressed": triageFilter === 'manual', onClick: () => onChangeTriageFilter('manual'), className: "seg-btn tabular-nums" },
                            "\u041F\u0440\u0430\u0432\u043A\u0438 ",
                            manualCount)),
                    React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0420\u0435\u0437\u0435\u0440\u0432 \u0432\u043E\u0440\u043E\u0442 \u043F\u0440\u0438\u0435\u043C\u043A\u0438" }, [2, 4].map((gateReserve) => (React.createElement("button", { key: gateReserve, type: "button", "aria-pressed": state.constraints.reserveGatePallets === gateReserve, onClick: () => domainStore_1.inventoryStore.updateConstraints({ reserveGatePallets: gateReserve }), className: "seg-btn tabular-nums" },
                        "\u0412\u043E\u0440\u043E\u0442\u0430 ",
                        gateReserve,
                        " \u043F.")))))),
            React.createElement("div", { className: "overflow-x-auto" },
                React.createElement("table", { className: "ledger-table tabular-nums" },
                    React.createElement("thead", null,
                        React.createElement("tr", null,
                            React.createElement("th", { scope: "col", className: "text-left" }, "\u041A\u043E\u043C\u043F\u043B\u0435\u043A\u0442\u0443\u044E\u0449\u0438\u0435"),
                            React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u041F\u043E\u043A\u0440\u044B\u0442\u0438\u0435"),
                            React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u041F\u0430\u0440\u0442\u0438\u044F, \u0448\u0442."),
                            React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                            React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0421\u0443\u043C\u043C\u0430"),
                            React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0428\u0430\u0433 \u0438 \u0431\u0443\u0444\u0435\u0440"))),
                    React.createElement("tbody", { ref: tbodyRef }, filteredItems.length === 0 ? (React.createElement("tr", null,
                        React.createElement("td", { colSpan: 6, className: "text-left" },
                            React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 py-1" },
                                React.createElement("span", { className: "text-sm text-secondary" }, "\u041F\u043E \u0432\u044B\u0431\u0440\u0430\u043D\u043D\u043E\u043C\u0443 \u0441\u0440\u0435\u0437\u0443 \u043E\u0442\u043A\u043B\u043E\u043D\u0435\u043D\u0438\u0439 \u0441\u0435\u0439\u0447\u0430\u0441 \u043D\u0435\u0442."),
                                React.createElement("button", { type: "button", onClick: () => onChangeTriageFilter('all'), className: "btn-secondary radius-control" }, "\u041F\u043E\u043A\u0430\u0437\u0430\u0442\u044C \u0432\u0441\u0435 \u043F\u043E\u0437\u0438\u0446\u0438\u0438"))))) : (filteredItems.map((item, idx) => (React.createElement(ReplenishmentLedgerRow_1.ReplenishmentLedgerRow, { key: item.id, item: item, idx: idx, isSelected: item.id === state.activeSkuId, transitDelayDays: state.transitDelayDays, backupChannel: state.backupChannel, appliedDiff: appliedDiffMap.get(item.id), onRowKeyDown: handleRowKeyDown })))))))),
        React.createElement("div", { className: "surface-inset px-3 py-2.5 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm tabular-nums" }, meterBars.map((bar) => {
            const pct = Math.round((bar.val / Math.max(1, bar.max)) * 100);
            return (React.createElement("div", { key: bar.label, className: "space-y-1" },
                React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("span", { className: "text-secondary" }, bar.label),
                    React.createElement("span", { className: "font-semibold text-primary" },
                        pct,
                        "%")),
                React.createElement("div", { className: "h-2 w-full rounded-full", style: { background: 'var(--surface-1)' } },
                    React.createElement("div", { className: "h-2 rounded-full", style: {
                            width: `${Math.min(100, pct)}%`,
                            background: bar.val > bar.max ? 'var(--accent-primary)' : 'oklch(0.36 0.068 248)'
                        } }))));
        })),
        React.createElement("div", { className: "surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-sm tabular-nums" },
            React.createElement("div", null,
                React.createElement("div", { className: "text-muted" }, "ROP + SS"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    activeSku.dailyDemand,
                    "\u00D7",
                    activeLeadDays,
                    "+",
                    activeSafetyUnits,
                    " = ",
                    activeTargetStock)),
            React.createElement("div", null,
                React.createElement("div", { className: "text-muted" }, "\u041D\u043E\u0440\u043C\u0430 / \u0448\u0430\u0433"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    "\u041D\u043E\u0440\u043C\u0430 ",
                    activeRecommendedQty,
                    ", \u0448\u0430\u0433 ",
                    activeSupplier.minBatchQty)),
            React.createElement("div", { "data-stochastic-readout": "true" },
                React.createElement("div", { className: "text-muted" }, "\u0411\u0443\u0444\u0435\u0440 \u03C3-SS"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    "SL ",
                    stoch.serviceLevelPct,
                    "%, \u03C3L ",
                    stoch.sigmaLeadDays.toFixed(1),
                    "\u0434, SS ",
                    stoch.stochasticSafetyUnits)))));
}

  };

  moduleFactories["components/SawtoothProjectionChart"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.SawtoothProjectionChart = SawtoothProjectionChart;
const react_1 = __importStar(require("react"));
const replenishmentEngine_1 = require("../store/replenishmentEngine");
function formatSawtoothStatus(proj, hasGapRisk) {
    if (proj.stockoutGapDays > 0) {
        return `Разрыв ${proj.stockoutGapDays} сут. до Д+${proj.leadDays}`;
    }
    if (hasGapRisk) {
        return `Пробой буфера SS (${proj.preArrivalStock} < ${proj.safetyUnits} шт.)`;
    }
    return `Защищено: пик ${proj.arrivalPeakStock} шт. в Д+${proj.leadDays}`;
}
function SawtoothProjectionChart({ item, transitDelayDays, backupChannel, compact = false }) {
    const [focusKey, setFocusKey] = (0, react_1.useState)('arrival');
    const proj = (0, replenishmentEngine_1.computeSawtoothProjection)(item, transitDelayDays, backupChannel, 21);
    const plotLeft = 40;
    const plotRight = 352;
    const plotTop = 14;
    const plotBottom = 82;
    const plotW = plotRight - plotLeft;
    const plotH = plotBottom - plotTop;
    const toX = (day) => Number((plotLeft + (day / proj.horizonDays) * plotW).toFixed(1));
    const toY = (stock) => Number((plotBottom - (Math.min(proj.maxStock, Math.max(0, stock)) / proj.maxStock) * plotH).toFixed(1));
    const ySafety = toY(proj.safetyUnits);
    const xArrival = toX(proj.leadDays);
    const yPreArrival = toY(proj.preArrivalStock);
    const yPeak = toY(proj.arrivalPeakStock);
    const yStart = toY(item.currentStock);
    const yEnd = toY(proj.endStock);
    const polylinePoints = proj.vertices.map((v) => `${toX(v.day)},${toY(v.stock)}`).join(' ');
    const areaPoints = `${plotLeft},${plotBottom} ${polylinePoints} ${plotRight},${plotBottom}`;
    const arrivalLabelX = Math.max(118, Math.min(256, xArrival));
    const hasGapRisk = proj.stockoutGapDays > 0 || proj.preArrivalStock < proj.safetyUnits;
    const milestones = [
        {
            key: 'start',
            cx: plotLeft,
            cy: yStart,
            hitX: plotLeft + 14,
            label: `Старт Д0: остаток ${item.currentStock} шт., расход ${item.dailyDemand} шт./сут.`,
            readout: `Д0 старт: ${item.currentStock} шт., расход ${item.dailyDemand} шт./сут.`
        },
        {
            key: 'arrival',
            cx: xArrival,
            cy: yPeak,
            hitX: Math.max(plotLeft + 92, Math.min(plotRight - 92, xArrival)),
            label: `Приход Д+${proj.leadDays}: до разгрузки ${proj.preArrivalStock} шт., скачок +${item.orderQty} до ${proj.arrivalPeakStock} шт.`,
            readout: proj.stockoutGapDays > 0
                ? `Д+${proj.leadDays} приход: провал ${proj.stockoutGapDays} сут., затем ${proj.arrivalPeakStock} шт.`
                : `Д+${proj.leadDays} приход: минимум ${proj.preArrivalStock} шт., пик ${proj.arrivalPeakStock} шт.`
        },
        {
            key: 'end',
            cx: plotRight,
            cy: yEnd,
            hitX: plotRight - 14,
            label: `Горизонт Д+${proj.horizonDays}: прогноз остатка ${proj.endStock} шт. при буфере ${proj.safetyUnits} шт.`,
            readout: `Д+${proj.horizonDays} прогноз: ${proj.endStock} шт. (буфер SS ${proj.safetyUnits} шт.)`
        }
    ];
    const activeMilestone = milestones.find((m) => m.key === focusKey) || milestones[1];
    const handleKey = (e, idx) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            setFocusKey(milestones[(idx + 1) % milestones.length].key);
        }
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            setFocusKey(milestones[(idx - 1 + milestones.length) % milestones.length].key);
        }
        else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setFocusKey(milestones[idx].key);
        }
    };
    return (react_1.default.createElement("div", { className: "space-y-1.5 tabular-nums", "data-sawtooth-widget": "true" },
        react_1.default.createElement("div", { className: "flex flex-wrap items-center justify-between gap-1.5 text-xs" },
            react_1.default.createElement("span", { className: "font-medium text-secondary" }, "\u041F\u0440\u043E\u0433\u043D\u043E\u0437 \u043E\u0441\u0442\u0430\u0442\u043A\u0430 21 \u0441\u0443\u0442. (\u043F\u0438\u043B\u0430 \u0437\u0430\u043F\u0430\u0441\u0430)"),
            react_1.default.createElement("span", { "data-chart-context": "true", className: `font-semibold ${hasGapRisk ? 'text-status-danger' : 'text-status-success'}` }, formatSawtoothStatus(proj, hasGapRisk))),
        react_1.default.createElement("div", { className: "surface-inset p-1.5 radius-control" },
            react_1.default.createElement("svg", { "data-chart": "sawtooth-projection", viewBox: "0 0 360 104", role: "group", "aria-label": `Пилообразный прогноз остатка ${item.name} на 21 сутки`, className: "w-full h-auto block select-none", style: { maxHeight: compact ? '80px' : '104px' } },
                react_1.default.createElement("g", { "aria-hidden": "true" },
                    react_1.default.createElement("rect", { x: plotLeft, y: ySafety, width: plotW, height: Math.max(2, plotBottom - ySafety), fill: hasGapRisk ? 'var(--status-danger-bg)' : 'var(--surface-2)', opacity: hasGapRisk ? 0.68 : 0.75 }),
                    react_1.default.createElement("line", { x1: plotLeft, y1: plotTop, x2: plotRight, y2: plotTop, stroke: "var(--border-subtle)", strokeWidth: 0.85 }),
                    react_1.default.createElement("line", { x1: plotLeft, y1: ySafety, x2: plotRight, y2: ySafety, stroke: hasGapRisk ? 'var(--accent-primary)' : 'var(--text-muted)', strokeWidth: 1, strokeDasharray: "3 3" }),
                    react_1.default.createElement("line", { x1: plotLeft, y1: plotBottom, x2: plotRight, y2: plotBottom, stroke: "var(--border-subtle)", strokeWidth: 1 }),
                    react_1.default.createElement("polygon", { points: areaPoints, fill: "oklch(0.36 0.068 248)", opacity: 0.09 }),
                    react_1.default.createElement("polyline", { points: polylinePoints, fill: "none", stroke: "oklch(0.36 0.068 248)", strokeWidth: 1.9, strokeLinejoin: "round", strokeLinecap: "round" }),
                    react_1.default.createElement("line", { x1: xArrival, y1: yPreArrival, x2: xArrival, y2: yPeak, stroke: "var(--accent-primary)", strokeWidth: 2.4, strokeLinecap: "round" }),
                    react_1.default.createElement("text", { x: 4, y: 18, fontSize: 11, fill: "var(--text-muted)" }, proj.maxStock),
                    react_1.default.createElement("text", { x: 4, y: 82, fontSize: 11, fill: "var(--text-muted)" }, "0"),
                    react_1.default.createElement("text", { x: plotLeft, y: 99, textAnchor: "start", fontSize: 11, fill: "var(--text-muted)" }, "\u04140"),
                    react_1.default.createElement("text", { x: arrivalLabelX, y: 99, textAnchor: "middle", fontSize: 11, fontWeight: 600, fill: "var(--text-primary)" },
                        "\u041F\u0440\u0438\u0445\u043E\u0434 \u0414+",
                        proj.leadDays),
                    react_1.default.createElement("text", { x: plotRight, y: 99, textAnchor: "end", fontSize: 11, fill: "var(--text-muted)" },
                        "\u0414+",
                        proj.horizonDays)),
                milestones.map((ms, idx) => {
                    const isSelected = ms.key === activeMilestone.key;
                    return (react_1.default.createElement("g", { key: ms.key, "data-chart-point": `sawtooth-${ms.key}`, role: "button", tabIndex: 0, "aria-label": ms.label, onMouseEnter: () => setFocusKey(ms.key), onFocus: () => setFocusKey(ms.key), onClick: () => setFocusKey(ms.key), onKeyDown: (e) => handleKey(e, idx), className: "cursor-pointer" },
                        react_1.default.createElement("rect", { x: ms.hitX - 36, y: 6, width: 72, height: 90, fill: "transparent" }),
                        isSelected && (react_1.default.createElement("circle", { cx: ms.cx, cy: ms.cy, r: 6.5, fill: "none", stroke: "var(--accent-primary)", strokeWidth: 1.4 })),
                        react_1.default.createElement("circle", { cx: ms.cx, cy: ms.cy, r: 3.6, fill: ms.key === 'arrival' ? 'var(--accent-primary)' : 'oklch(0.36 0.068 248)', stroke: "var(--surface-1)", strokeWidth: 1.2 })));
                }))),
        react_1.default.createElement("div", { className: "chart-readout text-xs", "aria-live": "polite" },
            react_1.default.createElement("span", { className: "font-medium text-primary" }, activeMilestone.readout),
            react_1.default.createElement("span", { className: "text-muted" },
                "\u0411\u0443\u0444\u0435\u0440 SS: ",
                proj.safetyUnits,
                " \u0448\u0442."))));
}

  };

  moduleFactories["components/ShellModals"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StateFallbackView = exports.CmdKPalette = exports.AddSkuModal = void 0;
exports.LiveUndoToast = LiveUndoToast;
const react_1 = require("react");
const domainStore_1 = require("../store/domainStore");
const Icons_1 = require("./Icons");
var AddSkuModal_1 = require("./AddSkuModal");
Object.defineProperty(exports, "AddSkuModal", { enumerable: true, get: function () { return AddSkuModal_1.AddSkuModal; } });
var CmdKPalette_1 = require("./CmdKPalette");
Object.defineProperty(exports, "CmdKPalette", { enumerable: true, get: function () { return CmdKPalette_1.CmdKPalette; } });
var StateFallbackView_1 = require("./StateFallbackView");
Object.defineProperty(exports, "StateFallbackView", { enumerable: true, get: function () { return StateFallbackView_1.StateFallbackView; } });
function LiveUndoToast({ message, canUndo = false }) {
    const hasUndo = Boolean(canUndo && domainStore_1.inventoryStore.canUndo());
    (0, react_1.useEffect)(() => {
        if (!message)
            return;
        const duration = hasUndo ? 8000 : 5000;
        const timer = window.setTimeout(() => {
            domainStore_1.inventoryStore.dismissToast();
        }, duration);
        return () => window.clearTimeout(timer);
    }, [message, hasUndo]);
    return (React.createElement("div", { role: "status", "aria-live": "polite", className: "fixed bottom-16 md:bottom-4 right-3 z-40" }, message && (React.createElement("div", { "data-ui": "surface", "data-toast-status": "true", style: { maxWidth: 'min(520px, calc(100vw - 24px))' }, className: "surface-card px-3 py-2 flex flex-wrap items-center justify-between gap-2" },
        React.createElement("span", { className: "text-sm font-medium text-primary" }, message),
        React.createElement("div", { className: "inline-flex items-center gap-1.5 shrink-0" },
            hasUndo && (React.createElement("button", { type: "button", "data-ui": "btn-secondary", "data-toast-undo": "true", onClick: () => domainStore_1.inventoryStore.undo(), className: "btn-secondary radius-control" },
                React.createElement(Icons_1.UndoIcon, { size: 13 }),
                React.createElement("span", null, "\u041E\u0442\u043C\u0435\u043D\u0438\u0442\u044C"))),
            React.createElement("button", { type: "button", "data-ui": "btn-ghost", "data-toast-dismiss": "true", "aria-label": "\u0417\u0430\u043A\u0440\u044B\u0442\u044C \u0443\u0432\u0435\u0434\u043E\u043C\u043B\u0435\u043D\u0438\u0435", onClick: () => domainStore_1.inventoryStore.dismissToast(), className: "btn-ghost radius-control text-muted" }, "\u00D7"))))));
}

  };

  moduleFactories["components/StateFallbackView"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StateFallbackView = StateFallbackView;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const SCREEN_TITLES = {
    'screen-replenishment-notebook': 'Расчет партий дозаказа и емкости склада',
    'screen-supply-map': 'Карта входящих поставок и клиентских отгрузок',
    'screen-warehouse-limits': 'Ограничения паллетомест, массы и бюджета',
    'screen-supplier-choice': 'Сравнение поставщиков по цене и срокам',
    'screen-delivery-buffer': 'Страховка сроков при задержках в пути',
    'screen-order-export': 'Спецификация заказа поставщику CSV и записка'
};
function StateFallbackView({ state, summary, viewState, onRecoverToIdeal }) {
    const screenTitle = SCREEN_TITLES[state.activeScreenId] || SCREEN_TITLES['screen-replenishment-notebook'];
    const channel = presets_1.BACKUP_CHANNELS[state.backupChannel];
    return (React.createElement("section", { "data-screen-view": state.activeScreenId, "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5" },
        React.createElement("article", { "data-card": "inframe-screen-header", className: "surface-card p-3.5 flex flex-wrap items-center justify-between gap-2" },
            React.createElement("div", null,
                React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, screenTitle),
                React.createElement("p", { className: "text-sm text-secondary" }, state.waveLabel)),
            React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0421\u0446\u0435\u043D\u0430\u0440\u0438\u0438 \u0441\u043D\u0430\u0431\u0436\u0435\u043D\u0438\u044F" }, presets_1.SCENARIO_PRESETS.map((preset) => (React.createElement("button", { key: preset.id, type: "button", "aria-pressed": state.activePresetId === preset.id, onClick: () => {
                    domainStore_1.inventoryStore.loadPreset(preset.id);
                    onRecoverToIdeal();
                }, className: "seg-btn" }, preset.label))))),
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start" },
            React.createElement("div", { className: "xl:col-span-8 min-w-0" },
                viewState === 'Loading' && (React.createElement("article", { "data-card": "loading-skeleton", role: "status", "aria-live": "polite", "aria-busy": "true", className: "surface-card p-4 space-y-3" },
                    React.createElement("span", { className: "sr-only" }, "\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430 \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u0438 \u0437\u0430\u043F\u0430\u0441\u043E\u0432..."),
                    React.createElement("div", { className: "text-sm font-medium text-secondary" }, "\u0421\u0438\u043D\u0445\u0440\u043E\u043D\u0438\u0437\u0430\u0446\u0438\u044F \u043E\u0441\u0442\u0430\u0442\u043A\u043E\u0432 \u044F\u0447\u0435\u0435\u043A \u043F\u0440\u0438\u0435\u043C\u043A\u0438 \u0438 \u0433\u0440\u0430\u0444\u0438\u043A\u043E\u0432 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u043E\u0432..."),
                    React.createElement("div", { className: "h-6 w-72 skeleton-bar" }),
                    React.createElement("div", { className: "h-16 w-full skeleton-bar" }),
                    React.createElement("div", { className: "h-16 w-full skeleton-bar" }),
                    React.createElement("div", { className: "h-16 w-full skeleton-bar" }))),
                viewState === 'Empty' && (React.createElement("article", { "data-card": "empty-ledger", className: "surface-card p-5 space-y-3.5" },
                    React.createElement("div", { className: "space-y-2" },
                        React.createElement("span", { className: "inline-flex px-2 py-0.5 radius-control surface-inset text-xs font-medium text-secondary" }, "\u041F\u0443\u0441\u0442\u0430\u044F \u0437\u0430\u043A\u0443\u043F\u043E\u0447\u043D\u0430\u044F \u0432\u043E\u043B\u043D\u0430"),
                        React.createElement("h2", { className: "text-base font-semibold text-primary" }, "\u0412 \u0442\u0435\u043A\u0443\u0449\u0435\u0439 \u0437\u0430\u043A\u0443\u043F\u043E\u0447\u043D\u043E\u0439 \u0432\u043E\u043B\u043D\u0435 \u043F\u043E\u043A\u0430 \u043D\u0435\u0442 \u043F\u043E\u0437\u0438\u0446\u0438\u0439 \u043A \u0437\u0430\u043A\u0430\u0437\u0443"),
                        React.createElement("p", { className: "text-sm text-secondary" }, "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0442\u0438\u043F\u043E\u0432\u043E\u0439 \u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0439 \u0441\u043F\u0440\u043E\u0441\u0430 \u0434\u043B\u044F \u0440\u0430\u0441\u0447\u0435\u0442\u0430 \u043F\u0430\u043B\u043B\u0435\u0442 \u0438 \u0431\u044E\u0434\u0436\u0435\u0442\u0430.")),
                    React.createElement("div", { className: "surface-inset p-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-secondary tabular-nums" },
                        React.createElement("div", null, "\u0428\u0430\u0431\u043B\u043E\u043D 1: \u041E\u0441\u0435\u043D\u043D\u0438\u0439 \u043F\u0438\u043A, 46 \u043F\u0430\u043B\u043B."),
                        React.createElement("div", null, "\u0428\u0430\u0431\u043B\u043E\u043D 2: \u0413\u0440\u0430\u043D\u0438\u0446\u0430, \u0441\u0434\u0432\u0438\u0433 +9 \u0441\u0443\u0442."),
                        React.createElement("div", null, "\u0428\u0430\u0431\u043B\u043E\u043D 3: \u0421\u0436\u0430\u0442\u044B\u0439 \u0441\u043A\u043B\u0430\u0434, 34 \u043F\u0430\u043B\u043B.")),
                    React.createElement("div", null,
                        React.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => {
                                domainStore_1.inventoryStore.loadPreset('preset-seasonal-peak');
                                onRecoverToIdeal();
                            }, className: "btn-primary radius-control" }, "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C \u043F\u0438\u043A\u043E\u0432\u043E\u0433\u043E \u0441\u043F\u0440\u043E\u0441\u0430")))),
                viewState === 'Error' && (React.createElement("article", { "data-card": "error-ledger", role: "alert", className: "surface-card p-5 space-y-3.5" },
                    React.createElement("div", { className: "space-y-2" },
                        React.createElement("div", { className: "inline-flex px-2 py-0.5 radius-control bg-status-danger text-xs font-semibold" }, "\u0427\u0435\u0440\u043D\u043E\u0432\u0438\u043A \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u0438 \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0432\u043E\u0441\u0441\u0442\u0430\u043D\u043E\u0432\u043B\u0435\u043D\u0438\u044F"),
                        React.createElement("h2", { className: "text-base font-semibold text-primary" }, "\u041B\u043E\u043A\u0430\u043B\u044C\u043D\u0430\u044F \u043A\u043E\u043F\u0438\u044F \u0437\u0430\u043A\u0443\u043F\u043E\u0447\u043D\u043E\u0433\u043E \u0440\u0430\u0441\u0447\u0435\u0442\u0430 \u043F\u0440\u0435\u0440\u0432\u0430\u043D\u0430 \u043F\u0440\u0438 \u043E\u0431\u043D\u043E\u0432\u043B\u0435\u043D\u0438\u0438 \u0432\u043A\u043B\u0430\u0434\u043A\u0438"),
                        React.createElement("p", { className: "text-sm text-secondary" }, "\u041D\u043E\u0440\u043C\u0430\u0442\u0438\u0432\u044B \u0441\u043A\u043B\u0430\u0434\u0430 \u0441\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u044B, \u0432\u043E\u0441\u0441\u0442\u0430\u043D\u043E\u0432\u0438\u0442\u0435 \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C \u043E\u0434\u043D\u0438\u043C \u043D\u0430\u0436\u0430\u0442\u0438\u0435\u043C.")),
                    React.createElement("div", { className: "surface-inset p-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-secondary tabular-nums" },
                        React.createElement("div", null, "\u041A\u043E\u0434: ERR_LEDGER_SNAPSHOT"),
                        React.createElement("div", null,
                            "\u0420\u0435\u0437\u0435\u0440\u0432: ",
                            summary.effectivePalletLimit,
                            " \u043F\u0430\u043B\u043B."),
                        React.createElement("div", null,
                            "\u041A\u0430\u043D\u0430\u043B: ",
                            channel.label)),
                    React.createElement("div", null,
                        React.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => {
                                domainStore_1.inventoryStore.resetToSeed();
                                onRecoverToIdeal();
                            }, className: "btn-primary radius-control" }, "\u0412\u043E\u0441\u0441\u0442\u0430\u043D\u043E\u0432\u0438\u0442\u044C \u044D\u0442\u0430\u043B\u043E\u043D\u043D\u0443\u044E \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C"))))),
            React.createElement("div", { className: "xl:col-span-4 min-w-0" },
                React.createElement("article", { "data-card": "inframe-warehouse-parameters", className: "surface-card p-4 space-y-2.5" },
                    React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0414\u0435\u0439\u0441\u0442\u0432\u0443\u044E\u0449\u0438\u0435 \u043D\u043E\u0440\u043C\u0430\u0442\u0438\u0432\u044B \u0437\u043E\u043D\u044B \u043F\u0440\u0438\u0435\u043C\u043A\u0438"),
                    React.createElement("div", { className: "surface-inset p-3 space-y-2 text-sm tabular-nums" },
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041B\u0438\u043C\u0438\u0442 \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442"),
                            React.createElement("span", { className: "font-semibold text-primary" },
                                summary.effectivePalletLimit,
                                " \u043F\u0430\u043B\u043B.")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041D\u0435\u0441\u0443\u0449\u0438\u0439 \u043F\u043E\u0440\u043E\u0433 \u0440\u0430\u043C\u043F\u044B"),
                            React.createElement("span", { className: "font-semibold text-primary" },
                                state.constraints.maxWeightKg,
                                " \u043A\u0433")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041F\u043E\u0442\u043E\u043B\u043E\u043A \u0431\u044E\u0434\u0436\u0435\u0442\u0430 \u0432\u043E\u043B\u043D\u044B"),
                            React.createElement("span", { className: "font-semibold text-primary" },
                                state.constraints.maxBudgetKrub,
                                " \u0442\u044B\u0441. \u20BD")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041B\u043E\u0433\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043A\u0438\u0439 \u043A\u0430\u043D\u0430\u043B"),
                            React.createElement("span", { className: "font-semibold text-primary" }, channel.label))),
                    React.createElement("p", { className: "text-xs text-muted" }, "\u041F\u0430\u0440\u0430\u043C\u0435\u0442\u0440\u044B \u043F\u0440\u0438\u0435\u043C\u043A\u0438 \u0438 \u0436\u0443\u0440\u043D\u0430\u043B \u0430\u043A\u0442\u0438\u0432\u043D\u044B \u0432 \u0441\u0435\u0441\u0441\u0438\u0438."))))));
}

  };

  moduleFactories["components/SupplierContractMatrixCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SupplierContractMatrixCard = SupplierContractMatrixCard;
const presets_1 = require("../data/presets");
const supplierContracts_1 = require("../data/supplierContracts");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const a11yDialog_1 = require("../utils/a11yDialog");
function SupplierContractMatrixCard({ items, backupChannel, selectedSupplierId, selectedSupplierName }) {
    return (React.createElement("article", { "data-card": "supplier-contract-matrix", className: "surface-card p-3.5 space-y-2.5" },
        React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2" },
            React.createElement("div", null,
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0421\u0440\u0430\u0432\u043D\u0438\u0442\u0435\u043B\u044C\u043D\u0430\u044F \u043C\u0430\u0442\u0440\u0438\u0446\u0430 \u0443\u0441\u043B\u043E\u0432\u0438\u0439 \u043F\u043E\u0441\u0442\u0430\u0432\u043A\u0438 \u0438 \u043E\u0442\u0441\u0440\u043E\u0447\u043A\u0438"),
                React.createElement("p", { className: "text-xs text-muted" }, "\u0414\u043E\u0433\u043E\u0432\u043E\u0440\u043D\u044B\u0435 \u043A\u0432\u043E\u0442\u044B MOQ, \u043E\u0442\u0441\u0440\u043E\u0447\u043A\u0430 \u043E\u043F\u043B\u0430\u0442\u044B \u0438 \u0440\u0430\u0441\u043F\u0440\u0435\u0434\u0435\u043B\u0435\u043D\u0438\u0435 \u0432\u043E\u043B\u043D\u044B")),
            React.createElement("span", { className: "text-xs text-secondary tabular-nums" },
                "\u0410\u043A\u0442\u0438\u0432\u043D\u044B\u0439 \u043A\u043E\u043D\u0442\u0440\u0430\u0433\u0435\u043D\u0442: ",
                selectedSupplierName)),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041F\u043B\u043E\u0449\u0430\u0434\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u0411\u0430\u0437\u0438\u0441 \u043F\u043E\u0441\u0442\u0430\u0432\u043A\u0438 \u0438 \u0443\u043F\u0430\u043A\u043E\u0432\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041E\u0442\u0441\u0440\u043E\u0447\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041A\u0440\u0430\u0442\u043D\u043E\u0441\u0442\u044C MOQ"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0428\u0442\u0440\u0430\u0444 SLA"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0421\u0443\u043C\u043C\u0430 \u0432 \u0432\u043E\u043B\u043D\u0435"))),
                React.createElement("tbody", null, presets_1.SUPPLIER_LIST.map((sup, idx) => {
                    const terms = supplierContracts_1.SUPPLIER_CONTRACT_TERMS[sup.id];
                    const isSelected = sup.id === selectedSupplierId;
                    const assignedSum = items
                        .filter((it) => it.supplierId === sup.id)
                        .reduce((acc, it) => acc + (0, replenishmentEngine_1.computeItemCostKrub)(it, backupChannel), 0);
                    return (React.createElement("tr", { key: sup.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: 0, "aria-current": isSelected ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSupplier(sup.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSupplier(sup.id)), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left text-sm font-semibold text-primary" },
                            sup.name,
                            ", ",
                            sup.city),
                        React.createElement("td", { className: "text-left text-sm text-secondary" }, terms.incoterms),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            terms.deferralDays,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            terms.moqStepQty,
                            " \u0448\u0442."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            terms.slaPenaltyPct,
                            " / \u0434\u043D."),
                        React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                            assignedSum.toFixed(1),
                            " \u0442\u044B\u0441. \u20BD")));
                }))))));
}

  };

  moduleFactories["components/SupplierReliabilityChartCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SupplierReliabilityChartCard = SupplierReliabilityChartCard;
const presets_1 = require("../data/presets");
const supplierContracts_1 = require("../data/supplierContracts");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
const Icons_1 = require("./Icons");
function SupplierReliabilityChartCard({ activeSku, selectedSupplier, selectedSupplierId, summary }) {
    return (React.createElement("article", { "data-card": "supplier-reliability-chart", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-2.5" },
        React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2 min-w-0" },
            React.createElement("div", null,
                React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u0421\u0440\u0430\u0432\u043D\u0435\u043D\u0438\u0435 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u043E\u0432 \u043F\u043E \u0446\u0435\u043D\u0435 \u0438 \u0441\u0440\u043E\u043A\u0430\u043C"),
                React.createElement("p", { className: "text-sm text-secondary tabular-nums" },
                    "\u041F\u043E\u0437\u0438\u0446\u0438\u044F: ",
                    activeSku.name,
                    ", \u043F\u0430\u0440\u0442\u0438\u044F ",
                    activeSku.orderQty,
                    " \u0448\u0442.")),
            React.createElement("span", { className: "text-sm font-semibold text-secondary tabular-nums" },
                "\u041F\u0443\u043B: ",
                summary.avgReliabilityPct.toFixed(1),
                "%, \u0441\u0440\u043E\u043A ",
                summary.avgLeadDays.toFixed(1),
                " \u0441\u0443\u0442.")),
        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
            React.createElement("div", { className: "flex items-center gap-1.5" },
                React.createElement(Icons_1.SupplierTruckIcon, { size: 15, className: "text-accent-primary" }),
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0418\u043D\u0434\u0435\u043A\u0441 \u043D\u0430\u0434\u0435\u0436\u043D\u043E\u0441\u0442\u0438 \u0438 \u043F\u043B\u0435\u0447\u043E \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438")),
            React.createElement("span", { "data-chart-context": "true", className: "text-sm text-secondary tabular-nums" },
                selectedSupplier.name,
                ": ",
                selectedSupplier.reliabilityPct.toFixed(1),
                "%, ",
                selectedSupplier.leadDays,
                " \u0441\u0443\u0442.")),
        React.createElement("div", { className: "surface-inset p-2.5" },
            React.createElement("svg", { "data-chart": "true", width: "620", height: "164", viewBox: "0 0 620 164", style: { width: '100%', height: 'auto', maxHeight: '172px' }, role: "img", "aria-label": "\u0413\u0440\u0430\u0444\u0438\u043A \u0438\u043D\u0434\u0435\u043A\u0441\u0430 \u043D\u0430\u0434\u0435\u0436\u043D\u043E\u0441\u0442\u0438 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u043E\u0432", className: "w-full block" },
                React.createElement("line", { x1: "54", y1: "22", x2: "596", y2: "22", stroke: "var(--border-subtle)", strokeWidth: "1" }),
                React.createElement("line", { x1: "54", y1: "76", x2: "596", y2: "76", stroke: "var(--border-subtle)", strokeWidth: "1" }),
                React.createElement("line", { x1: "54", y1: "130", x2: "596", y2: "130", stroke: "var(--border-subtle)", strokeWidth: "1" }),
                React.createElement("text", { x: "6", y: "26", fontSize: "11", fontFamily: "var(--font-sans)", fill: "var(--text-muted)" }, "100%"),
                React.createElement("text", { x: "6", y: "80", fontSize: "11", fontFamily: "var(--font-sans)", fill: "var(--text-muted)" }, "92%"),
                React.createElement("text", { x: "6", y: "134", fontSize: "11", fontFamily: "var(--font-sans)", fill: "var(--text-muted)" }, "84%"),
                presets_1.SUPPLIER_LIST.map((sup, idx) => {
                    const cx = 132 + idx * 134;
                    const barWidth = 52;
                    const clamped = Math.max(84, Math.min(100, sup.reliabilityPct));
                    const barHeight = Math.round(((clamped - 84) / 16) * 98) + 10;
                    const barTop = 130 - barHeight;
                    const isSelected = sup.id === selectedSupplierId;
                    return (React.createElement("g", { key: sup.id, "data-chart-node": sup.id, "data-canvas-node": sup.id, onClick: () => domainStore_1.inventoryStore.selectChartSupplier(sup.id), className: "cursor-pointer" },
                        React.createElement("rect", { x: cx - barWidth / 2, y: barTop, width: barWidth, height: barHeight, rx: "2", fill: isSelected ? 'var(--accent-primary)' : 'var(--border-strong)', fillOpacity: isSelected ? '0.94' : '0.62' }),
                        React.createElement("text", { x: cx, y: barTop - 6, textAnchor: "middle", fontSize: "11", fontFamily: "var(--font-sans)", fontWeight: "600", fill: "var(--text-primary)" },
                            sup.reliabilityPct.toFixed(1),
                            "%"),
                        React.createElement("text", { x: cx, y: "151", textAnchor: "middle", fontSize: "11", fontFamily: "var(--font-sans)", fontWeight: isSelected ? '600' : '400', fill: "var(--text-secondary)" }, supplierContracts_1.SHORT_SUPPLIER_NAMES[sup.id] || sup.name)));
                }))),
        React.createElement("div", { className: "seg-group flex-wrap", role: "group", "aria-label": "\u041F\u043B\u043E\u0449\u0430\u0434\u043A\u0438 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u043E\u0432" }, presets_1.SUPPLIER_LIST.map((sup) => (React.createElement("button", { key: sup.id, type: "button", "aria-pressed": sup.id === selectedSupplierId, onClick: () => domainStore_1.inventoryStore.selectSupplier(sup.id), className: "seg-btn tabular-nums" },
            sup.name,
            ", ",
            sup.leadDays,
            "\u0434")))),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", null,
                        React.createElement("th", { scope: "col", className: "text-left" }, "\u041F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A"),
                        React.createElement("th", { scope: "col", className: "text-left" }, "\u0413\u043E\u0440\u043E\u0434"),
                        React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0421\u0440\u043E\u043A"),
                        React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u041C\u0438\u043D. \u043F\u0430\u0440\u0442\u0438\u044F"),
                        React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0418\u043D\u0434\u0435\u043A\u0441 \u0446\u0435\u043D\u044B"))),
                React.createElement("tbody", null, presets_1.SUPPLIER_LIST.map((sup, idx) => {
                    const isSelected = sup.id === selectedSupplierId;
                    return (React.createElement("tr", { key: sup.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: 0, "aria-current": isSelected ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSupplier(sup.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSupplier(sup.id)), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left font-semibold text-primary text-sm" }, sup.name),
                        React.createElement("td", { className: "text-left text-secondary text-sm" }, sup.city),
                        React.createElement("td", { className: "text-right text-sm tabular-nums whitespace-nowrap" },
                            sup.leadDays,
                            " \u0441\u0443\u0442."),
                        React.createElement("td", { className: "text-right text-sm tabular-nums whitespace-nowrap" },
                            sup.minBatchQty,
                            " \u0448\u0442."),
                        React.createElement("td", { className: "text-right text-sm font-medium text-primary tabular-nums whitespace-nowrap" },
                            "\u00D7",
                            sup.priceFactor.toFixed(2))));
                }))))));
}

  };

  moduleFactories["components/SupplyCorridorLedger"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SupplyCorridorLedger = SupplyCorridorLedger;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
function getInboundBadge(flow) {
    if (flow.atRisk)
        return { cls: 'bg-status-danger', text: 'Риск срока' };
    if (flow.skuCount === 0)
        return { cls: 'surface-inset text-secondary', text: 'Резерв' };
    return { cls: 'bg-status-success', text: 'По графику' };
}
function getOutboundBadgeClass(status) {
    if (status === 'ready')
        return 'bg-status-success';
    if (status === 'gate_wait')
        return 'bg-status-warning';
    return 'bg-status-danger';
}
function SupplyCorridorLedger({ inbound, outbound, selectedNodeId }) {
    const [ledgerFilter, setLedgerFilter] = (0, react_1.useState)('all');
    return (React.createElement("article", { "data-card": "inbound-outbound-ledger", className: "surface-card p-3 space-y-2" },
        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
            React.createElement("div", null,
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0420\u0435\u0435\u0441\u0442\u0440 \u043D\u0430\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u0439: \u043F\u043E\u0441\u0442\u0430\u0432\u043A\u0438 \u0432 \u0420\u0426 \u0438 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438 \u043A\u043B\u0438\u0435\u043D\u0442\u0430\u043C"),
                React.createElement("p", { className: "text-xs text-muted" }, "\u0412\u044B\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0442\u0440\u043E\u043A\u0443 \u043C\u0430\u0440\u0448\u0440\u0443\u0442\u0430 \u0434\u043B\u044F \u0444\u043E\u043A\u0443\u0441\u0430 \u043D\u0430 \u043A\u0430\u0440\u0442\u0435")),
            React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0424\u0438\u043B\u044C\u0442\u0440 \u0442\u0430\u0431\u043B\u0438\u0446\u044B \u043F\u043B\u0435\u0447" },
                React.createElement("button", { type: "button", "aria-pressed": ledgerFilter === 'all', onClick: () => setLedgerFilter('all'), className: "seg-btn" }, "\u0412\u0441\u0435 8 \u043F\u043B\u0435\u0447"),
                React.createElement("button", { type: "button", "aria-pressed": ledgerFilter === 'inbound', onClick: () => setLedgerFilter('inbound'), className: "seg-btn" }, "\u0412\u0445\u043E\u0434 \u0432 \u0420\u0426"),
                React.createElement("button", { type: "button", "aria-pressed": ledgerFilter === 'outbound', onClick: () => setLedgerFilter('outbound'), className: "seg-btn" }, "\u041A\u043B\u0438\u0435\u043D\u0442\u0430\u043C"))),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041C\u0430\u0440\u0448\u0440\u0443\u0442"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041A\u043E\u043D\u0442\u0440\u0430\u0433\u0435\u043D\u0442 \u0438 \u0433\u0440\u0443\u0437"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u0421\u0442\u0430\u0442\u0443\u0441"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u043B\u0435\u0447\u043E"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041C\u0430\u0441\u0441\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0421\u0440\u043E\u043A"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0421\u0443\u043C\u043C\u0430"))),
                React.createElement("tbody", null,
                    ledgerFilter !== 'outbound' &&
                        inbound.map((f, idx) => {
                            const isSel = selectedNodeId === f.id;
                            const badge = getInboundBadge(f);
                            return (React.createElement("tr", { key: `row-in-${f.id}`, "data-selected": isSel ? 'true' : undefined, tabIndex: 0, "aria-current": isSel ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectMapNode(f.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectMapNode(f.id)), className: `cursor-pointer ${!isSel && idx % 2 === 1 ? 'surface-inset' : ''}` },
                                React.createElement("td", { className: "text-left text-sm font-semibold text-primary" },
                                    "\u0412\u0445\u043E\u0434: ",
                                    f.city),
                                React.createElement("td", { className: "text-left text-sm text-secondary" },
                                    f.supplierName,
                                    ", ",
                                    f.skuCount,
                                    " \u043F\u043E\u0437."),
                                React.createElement("td", { className: "text-left whitespace-nowrap" },
                                    React.createElement("span", { className: `px-2 py-0.5 radius-control text-xs font-medium ${badge.cls}` }, badge.text)),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    f.geo.distanceKm,
                                    " \u043A\u043C"),
                                React.createElement("td", { className: "text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums" },
                                    f.pallets.toFixed(1),
                                    " \u043F\u0430\u043B\u043B."),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    f.weightKg,
                                    " \u043A\u0433"),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    f.leadDays,
                                    " \u0441\u0443\u0442."),
                                React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                                    f.budgetKrub.toFixed(1),
                                    " \u0442\u044B\u0441. \u20BD")));
                        }),
                    ledgerFilter !== 'inbound' &&
                        outbound.map((o, idx) => {
                            const isSel = selectedNodeId === o.id;
                            const firstSup = o.peggedSuppliers[0] ? (0, presets_1.getSupplier)(o.peggedSuppliers[0]).city : 'РЦ';
                            return (React.createElement("tr", { key: `row-out-${o.id}`, "data-selected": isSel ? 'true' : undefined, tabIndex: 0, "aria-current": isSel ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectMapNode(o.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectMapNode(o.id)), className: `cursor-pointer ${!isSel && idx % 2 === 0 ? 'surface-inset' : ''}` },
                                React.createElement("td", { className: "text-left text-sm font-semibold text-primary" },
                                    "\u0412\u044B\u0432\u043E\u0437: ",
                                    o.city),
                                React.createElement("td", { className: "text-left text-sm text-secondary" },
                                    o.customerName,
                                    ", \u0431\u0430\u0437\u0430 ",
                                    firstSup),
                                React.createElement("td", { className: "text-left whitespace-nowrap" },
                                    React.createElement("span", { className: `px-2 py-0.5 radius-control text-xs font-medium ${getOutboundBadgeClass(o.status)}` }, o.statusLabel)),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    o.geo.distanceKm,
                                    " \u043A\u043C"),
                                React.createElement("td", { className: "text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums" },
                                    o.pallets.toFixed(1),
                                    " \u043F\u0430\u043B\u043B."),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    o.weightKg,
                                    " \u043A\u0433"),
                                React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                    o.dispatchWindowDays,
                                    " \u0441\u0443\u0442."),
                                React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                                    o.valueKrub.toFixed(1),
                                    " \u0442\u044B\u0441. \u20BD")));
                        }))))));
}

  };

  moduleFactories["components/SupplyFlowMap"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.SupplyFlowMap = SupplyFlowMap;
const react_1 = __importStar(require("react"));
const flowNetwork_1 = require("../data/flowNetwork");
const SupplyFlowMapCanvas_1 = require("./SupplyFlowMapCanvas");
const REGION_VIEWBOX = {
    all: '0 0 760 220',
    west_center: '44 14 440 198',
    volga_ural: '216 12 532 200'
};
const SHORT_CITY = {
    'Санкт-Петербург': 'Санкт-Петербург',
    'Ярославль': 'Ярославль',
    'Москва (Подольск)': 'РЦ Москва',
    'Тула': 'Тула',
    'Нижний Новгород': 'Н. Новгород',
    'Воронеж': 'Воронеж',
    'Казань': 'Казань',
    'Самара': 'Самара',
    'Екатеринбург': 'Екатеринбург'
};
const MOBILE_HIT_SHIFT = {
    'sever-snab': [24, -20],
    'out-tula': [-24, 24],
    'volga-pribor': [-16, -20],
    'out-samara': [16, 20]
};
function renderNodeGlyph(kind, x, y, fillColor) {
    if (kind === 'hub') {
        return (react_1.default.createElement("g", null,
            react_1.default.createElement("rect", { x: x - 8, y: y - 8, width: 16, height: 16, rx: 2, fill: fillColor, stroke: "var(--surface-1)", strokeWidth: 1.5 }),
            react_1.default.createElement("rect", { x: x - 3, y: y - 3, width: 6, height: 6, rx: 1, fill: "var(--surface-1)" })));
    }
    if (kind === 'supplier') {
        return (react_1.default.createElement("rect", { x: x - 5.5, y: y - 5.5, width: 11, height: 11, rx: 1.5, fill: fillColor, stroke: "var(--surface-1)", strokeWidth: 1.4 }));
    }
    return react_1.default.createElement("circle", { cx: x, cy: y, r: 6, fill: fillColor, stroke: "var(--surface-1)", strokeWidth: 1.4 });
}
function SupplyFlowMap({ inbound, outbound, selectedNodeId, lens, metric, region, effectivePalletLimit, totalPallets, peggedSku, onSelectNode }) {
    const [hoveredId, setHoveredId] = (0, react_1.useState)(null);
    const [isCompactViewport, setIsCompactViewport] = (0, react_1.useState)(() => typeof window !== 'undefined' ? window.innerWidth < 768 : false);
    (0, react_1.useEffect)(() => {
        if (typeof window === 'undefined')
            return undefined;
        const onResize = () => setIsCompactViewport(window.innerWidth < 768);
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);
    const focusId = hoveredId || selectedNodeId;
    const orderedNodes = [
        ...inbound.map((f) => ({
            id: f.id,
            label: f.city,
            x: f.geo.x,
            y: f.geo.y,
            kind: 'supplier',
            readoutText: `Вход в РЦ: ${f.supplierName}, ${f.city}, ${f.pallets.toFixed(1)} палл., плечо ${f.leadDays} сут.`
        })),
        {
            id: 'dc-moscow',
            label: flowNetwork_1.CENTRAL_HUB_META.city,
            x: flowNetwork_1.CENTRAL_HUB_META.x,
            y: flowNetwork_1.CENTRAL_HUB_META.y,
            kind: 'hub',
            readoutText: `Центральный РЦ Подольск: приемка ${totalPallets.toFixed(1)} из ${effectivePalletLimit} палл., отгрузка 4 заказчикам`
        },
        ...outbound.map((o) => ({
            id: o.id,
            label: o.city,
            x: o.geo.x,
            y: o.geo.y,
            kind: 'customer',
            readoutText: `Отгрузка: ${o.customerName}, окно ${o.dispatchWindowLabel}, ${o.pallets.toFixed(1)} палл., ${o.statusLabel}`
        }))
    ];
    const activeNodeInfo = orderedNodes.find((n) => n.id === focusId) || orderedNodes[4] || orderedNodes[0];
    const selectedOutbound = outbound.find((o) => o.id === focusId);
    const handlePointKeyDown = (e, idx, nodeId) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelectNode(nodeId);
        }
        else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault();
            onSelectNode(orderedNodes[(idx + 1) % orderedNodes.length].id);
        }
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault();
            onSelectNode(orderedNodes[(idx - 1 + orderedNodes.length) % orderedNodes.length].id);
        }
    };
    return (react_1.default.createElement("div", { className: "space-y-1.5" },
        react_1.default.createElement("div", { className: "surface-inset p-1.5 radius-control overflow-hidden" },
            react_1.default.createElement("svg", { "data-chart": "supply-flow-map", viewBox: REGION_VIEWBOX[region], role: "group", "aria-label": "\u0413\u0435\u043E\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043A\u0430\u044F \u043A\u0430\u0440\u0442\u0430 \u0432\u0445\u043E\u0434\u044F\u0449\u0438\u0445 \u043F\u043E\u0441\u0442\u0430\u0432\u043E\u043A \u043D\u0430 \u0446\u0435\u043D\u0442\u0440\u0430\u043B\u044C\u043D\u044B\u0439 \u0441\u043A\u043B\u0430\u0434 \u0438 \u0438\u0441\u0445\u043E\u0434\u044F\u0449\u0438\u0445 \u043E\u0442\u0433\u0440\u0443\u0437\u043E\u043A \u0437\u0430\u043A\u0430\u0437\u0447\u0438\u043A\u0430\u043C", className: "w-full h-auto block select-none", style: { maxHeight: '202px' } },
                react_1.default.createElement(SupplyFlowMapCanvas_1.SupplyFlowMapBackdrop, null),
                react_1.default.createElement(SupplyFlowMapCanvas_1.SupplyFlowArcLayers, { inbound: inbound, outbound: outbound, focusId: focusId, lens: lens, metric: metric, peggedSku: peggedSku, selectedOutbound: selectedOutbound }),
                orderedNodes.map((node, idx) => {
                    const isSelected = selectedNodeId === node.id;
                    const inArc = inbound.find((i) => i.id === node.id);
                    const outArc = outbound.find((o) => o.id === node.id);
                    const geo = inArc?.geo || outArc?.geo || flowNetwork_1.CENTRAL_HUB_META;
                    const hasRisk = Boolean((inArc && inArc.atRisk) || (outArc && outArc.status === 'at_risk'));
                    const fillColor = (0, SupplyFlowMapCanvas_1.resolveNodeFillColor)(node.kind, hasRisk);
                    const hitHalf = isCompactViewport ? 68 : 24;
                    const [shiftX, shiftY] = isCompactViewport
                        ? MOBILE_HIT_SHIFT[node.id] || [0, 0]
                        : [0, 0];
                    return (react_1.default.createElement("g", { key: node.id, "data-chart-point": node.id, role: "button", tabIndex: 0, "aria-label": node.readoutText, onMouseEnter: () => setHoveredId(node.id), onMouseLeave: () => setHoveredId(null), onFocus: () => setHoveredId(node.id), onBlur: () => setHoveredId(null), onClick: () => onSelectNode(node.id), onKeyDown: (e) => handlePointKeyDown(e, idx, node.id), className: "cursor-pointer" },
                        react_1.default.createElement("rect", { x: node.x + shiftX - hitHalf, y: node.y + shiftY - hitHalf, width: hitHalf * 2, height: hitHalf * 2, fill: "transparent" }),
                        isSelected && (react_1.default.createElement("circle", { cx: node.x, cy: node.y, r: node.kind === 'hub' ? 14 : 11, fill: "none", stroke: "var(--accent-primary)", strokeWidth: 1.6 })),
                        renderNodeGlyph(node.kind, node.x, node.y, fillColor),
                        react_1.default.createElement("text", { x: node.x + geo.labelDx, y: node.y + geo.labelDy, textAnchor: geo.labelAnchor, fontSize: 11.5, fontWeight: isSelected ? 700 : 600, fill: "var(--text-primary)" }, SHORT_CITY[geo.city] || geo.city)));
                }))),
        react_1.default.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 text-xs text-secondary" },
            react_1.default.createElement("div", { className: "flex flex-wrap items-center gap-3" },
                react_1.default.createElement("span", { className: "inline-flex items-center gap-1.5" },
                    react_1.default.createElement("span", { "aria-hidden": "true", style: { width: 9, height: 9, borderRadius: 1, backgroundColor: 'oklch(0.36 0.068 248)', display: 'inline-block' } }),
                    react_1.default.createElement("span", null, "\u0412\u0445\u043E\u0434 \u043E\u0442 \u0437\u0430\u0432\u043E\u0434\u043E\u0432")),
                react_1.default.createElement("span", { className: "inline-flex items-center gap-1.5" },
                    react_1.default.createElement("span", { "aria-hidden": "true", style: { width: 9, height: 9, borderRadius: 1, backgroundColor: 'var(--text-primary)', display: 'inline-block' } }),
                    react_1.default.createElement("span", null, "\u0426\u0435\u043D\u0442\u0440\u0430\u043B\u044C\u043D\u044B\u0439 \u0420\u0426")),
                react_1.default.createElement("span", { className: "inline-flex items-center gap-1.5" },
                    react_1.default.createElement("span", { "aria-hidden": "true", style: { width: 9, height: 9, borderRadius: 999, backgroundColor: 'var(--status-success-fg)', display: 'inline-block' } }),
                    react_1.default.createElement("span", null, "\u041E\u0442\u0433\u0440\u0443\u0437\u043A\u0430 \u043A\u043B\u0438\u0435\u043D\u0442\u0443")),
                react_1.default.createElement("span", { className: "inline-flex items-center gap-1.5" },
                    react_1.default.createElement("span", { "aria-hidden": "true", style: { width: 9, height: 9, borderRadius: 999, backgroundColor: 'var(--accent-primary)', display: 'inline-block' } }),
                    react_1.default.createElement("span", null, "\u0420\u0438\u0441\u043A \u0441\u0440\u043E\u043A\u0430"))),
            react_1.default.createElement("span", { className: "text-muted" }, "\u0421\u0442\u0440\u0435\u043B\u043A\u0438 \u2190/\u2192 \u043F\u043E \u0443\u0437\u043B\u0430\u043C")),
        react_1.default.createElement("div", { "data-chart-context": "true", className: "chart-readout text-sm", role: "status", "aria-live": "polite" },
            react_1.default.createElement("span", { className: "font-medium text-primary" }, activeNodeInfo.readoutText))));
}

  };

  moduleFactories["components/SupplyFlowMapBackdrop"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.formatFlowValue = formatFlowValue;
exports.computeStrokeWidth = computeStrokeWidth;
exports.resolveInboundColor = resolveInboundColor;
exports.resolveOutboundColor = resolveOutboundColor;
exports.resolveArcOpacity = resolveArcOpacity;
exports.resolveNodeFillColor = resolveNodeFillColor;
exports.SupplyFlowMapBackdrop = SupplyFlowMapBackdrop;
const MERIDIANS = [112, 266, 420, 562, 696];
const MERIDIAN_LABELS = ['30°В', '38°В', '44°В', '50°В', '60°В'];
const PARALLELS = [44, 120, 192];
const PARALLEL_LABELS = ['60°С', '55°С', '52°С'];
function formatFlowValue(pallets, weightKg, moneyKrub, metric) {
    if (metric === 'weight')
        return `${(weightKg / 1000).toFixed(1)} т`;
    if (metric === 'budget')
        return `${Math.round(moneyKrub)} тыс.`;
    return `${pallets.toFixed(1)} п.`;
}
function computeStrokeWidth(pallets, weightKg, moneyKrub, metric) {
    let ratio = pallets / 22;
    if (metric === 'weight')
        ratio = weightKg / 6500;
    else if (metric === 'budget')
        ratio = moneyKrub / 1600;
    return Number(Math.max(1.6, Math.min(5.6, 1.6 + ratio * 3.8)).toFixed(2));
}
function resolveInboundColor(isEmpty, atRisk) {
    if (isEmpty)
        return 'var(--border-subtle)';
    if (atRisk)
        return 'var(--accent-primary)';
    return 'oklch(0.36 0.068 248)';
}
function resolveOutboundColor(status) {
    if (status === 'at_risk')
        return 'var(--accent-primary)';
    if (status === 'gate_wait')
        return 'var(--status-warning-fg)';
    return 'var(--status-success-fg)';
}
function resolveArcOpacity(dimmed, isSelected, idleOpacity) {
    if (dimmed)
        return 0.16;
    if (isSelected)
        return 1;
    return idleOpacity;
}
function resolveNodeFillColor(kind, hasRisk) {
    if (kind === 'hub')
        return 'var(--text-primary)';
    if (hasRisk)
        return 'var(--accent-primary)';
    if (kind === 'supplier')
        return 'oklch(0.36 0.068 248)';
    return 'var(--status-success-fg)';
}
function SupplyFlowMapBackdrop() {
    return (React.createElement("g", { "aria-hidden": "true" },
        React.createElement("path", { d: "M 56 28 L 218 22 L 386 26 L 590 30 L 736 50 L 742 138 L 634 198 L 468 208 L 254 210 L 146 188 L 78 126 L 48 64 Z", fill: "var(--surface-1)", stroke: "var(--border-subtle)", strokeWidth: 1 }),
        MERIDIANS.map((gx, i) => (React.createElement("g", { key: `mer-${gx}` },
            React.createElement("line", { x1: gx, y1: 10, x2: gx, y2: 212, stroke: "var(--border-subtle)", strokeWidth: 0.75, strokeDasharray: "2 4" }),
            React.createElement("text", { x: gx + 4, y: 18, fontSize: 11, fill: "var(--text-muted)" }, MERIDIAN_LABELS[i])))),
        PARALLELS.map((gy, i) => (React.createElement("g", { key: `par-${gy}` },
            React.createElement("line", { x1: 18, y1: gy, x2: 744, y2: gy, stroke: "var(--border-subtle)", strokeWidth: 0.75, strokeDasharray: "2 4" }),
            React.createElement("text", { x: 20, y: gy - 5, fontSize: 11, fill: "var(--text-muted)" }, PARALLEL_LABELS[i])))),
        React.createElement("path", { d: "M 218 72 Q 278 54 322 58 T 420 128 Q 486 118 536 110 Q 556 146 562 176 L 538 204", fill: "none", stroke: "oklch(0.84 0.028 240)", strokeWidth: 1.4, strokeLinecap: "round" }),
        React.createElement("path", { d: "M 536 110 Q 608 92 654 74", fill: "none", stroke: "oklch(0.84 0.028 240)", strokeWidth: 1.1, strokeLinecap: "round" }),
        React.createElement("path", { d: "M 668 34 L 662 150", fill: "none", stroke: "var(--border-subtle)", strokeWidth: 1.1, strokeDasharray: "3 3" }),
        React.createElement("g", { transform: "translate(64, 198)" },
            React.createElement("line", { x1: 0, y1: 8, x2: 72, y2: 8, stroke: "var(--text-muted)", strokeWidth: 1.2 }),
            React.createElement("line", { x1: 0, y1: 4, x2: 0, y2: 11, stroke: "var(--text-muted)", strokeWidth: 1.2 }),
            React.createElement("line", { x1: 72, y1: 4, x2: 72, y2: 11, stroke: "var(--text-muted)", strokeWidth: 1.2 }),
            React.createElement("text", { x: 12, y: 2, fontSize: 11, fill: "var(--text-muted)" }, "500 \u043A\u043C"))));
}

  };

  moduleFactories["components/SupplyFlowMapCanvas"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SupplyFlowMapBackdrop = exports.resolveNodeFillColor = void 0;
exports.SupplyFlowArcLayers = SupplyFlowArcLayers;
const SupplyFlowMapBackdrop_1 = require("./SupplyFlowMapBackdrop");
var SupplyFlowMapBackdrop_2 = require("./SupplyFlowMapBackdrop");
Object.defineProperty(exports, "resolveNodeFillColor", { enumerable: true, get: function () { return SupplyFlowMapBackdrop_2.resolveNodeFillColor; } });
Object.defineProperty(exports, "SupplyFlowMapBackdrop", { enumerable: true, get: function () { return SupplyFlowMapBackdrop_2.SupplyFlowMapBackdrop; } });
function SupplyFlowArcLayers({ inbound, outbound, focusId, lens, metric, peggedSku, selectedOutbound }) {
    return (React.createElement(React.Fragment, null,
        React.createElement("g", { "aria-hidden": "true" }, inbound.map((arc) => {
            const isEmpty = arc.skuCount === 0;
            const isPeggedToCustomer = Boolean(selectedOutbound && selectedOutbound.peggedSuppliers.includes(arc.id));
            const isSkuInboundMatch = Boolean(lens === 'sku_peg' && peggedSku && arc.id === peggedSku.supplierId);
            const isSelected = lens === 'sku_peg'
                ? isSkuInboundMatch
                : focusId === arc.id || focusId === 'dc-moscow' || isPeggedToCustomer;
            let dimmed = false;
            if (lens === 'outbound')
                dimmed = !isPeggedToCustomer;
            if (lens === 'at_risk' && !arc.atRisk)
                dimmed = true;
            if (lens === 'sku_peg')
                dimmed = !isSkuInboundMatch;
            const strokeColor = (0, SupplyFlowMapBackdrop_1.resolveInboundColor)(isEmpty, arc.atRisk);
            const width = isEmpty ? 1.2 : (0, SupplyFlowMapBackdrop_1.computeStrokeWidth)(arc.pallets, arc.weightKg, arc.budgetKrub, metric);
            const badgeVal = isSkuInboundMatch && peggedSku
                ? `+${peggedSku.orderQty} шт.`
                : (0, SupplyFlowMapBackdrop_1.formatFlowValue)(arc.pallets, arc.weightKg, arc.budgetKrub, metric);
            return (React.createElement("g", { key: `in-${arc.id}`, opacity: (0, SupplyFlowMapBackdrop_1.resolveArcOpacity)(dimmed, isSelected, 0.78) },
                React.createElement("path", { d: arc.arcPath, fill: "none", stroke: strokeColor, strokeWidth: isSelected && !isEmpty ? width + 0.7 : width, strokeDasharray: isEmpty ? '3 4' : undefined, strokeLinecap: "round" }),
                !isEmpty && (React.createElement("g", { transform: `translate(${arc.midX}, ${arc.midY})` },
                    React.createElement("rect", { x: -27, y: -8.5, width: 54, height: 17, rx: 2, fill: "var(--surface-1)", stroke: strokeColor, strokeWidth: 0.9 }),
                    React.createElement("text", { x: 0, y: 3.5, textAnchor: "middle", fontSize: 11, fontWeight: 600, fill: "var(--text-primary)" }, badgeVal)))));
        })),
        React.createElement("g", { "aria-hidden": "true" }, outbound.map((arc) => {
            const isPeggedToSupplier = arc.peggedSuppliers.includes(focusId);
            const matchedSkuLine = lens === 'sku_peg' && peggedSku ? arc.lines.find((ln) => ln.skuId === peggedSku.id) : undefined;
            const isSelected = lens === 'sku_peg'
                ? Boolean(matchedSkuLine)
                : focusId === arc.id || focusId === 'dc-moscow' || isPeggedToSupplier;
            let dimmed = false;
            if (lens === 'inbound')
                dimmed = !isPeggedToSupplier;
            if (lens === 'at_risk' && arc.status === 'ready')
                dimmed = true;
            if (lens === 'sku_peg')
                dimmed = !matchedSkuLine;
            const strokeColor = (0, SupplyFlowMapBackdrop_1.resolveOutboundColor)(arc.status);
            const width = (0, SupplyFlowMapBackdrop_1.computeStrokeWidth)(arc.pallets, arc.weightKg, arc.valueKrub, metric);
            const badgeVal = matchedSkuLine
                ? `-${matchedSkuLine.requiredQty} шт.`
                : (0, SupplyFlowMapBackdrop_1.formatFlowValue)(arc.pallets, arc.weightKg, arc.valueKrub, metric);
            return (React.createElement("g", { key: `out-${arc.id}`, opacity: (0, SupplyFlowMapBackdrop_1.resolveArcOpacity)(dimmed, isSelected, 0.82) },
                React.createElement("path", { d: arc.arcPath, fill: "none", stroke: strokeColor, strokeWidth: isSelected ? width + 0.6 : width, strokeDasharray: "7 3.5", strokeLinecap: "round" }),
                React.createElement("g", { transform: `translate(${arc.midX}, ${arc.midY})` },
                    React.createElement("rect", { x: -27, y: -8.5, width: 54, height: 17, rx: 2, fill: "var(--surface-1)", stroke: strokeColor, strokeWidth: 0.9 }),
                    React.createElement("text", { x: 0, y: 3.5, textAnchor: "middle", fontSize: 11, fontWeight: 600, fill: "var(--text-primary)" }, badgeVal))));
        }))));
}

  };

  moduleFactories["components/TransitBufferInspectorColumn"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.TransitBufferInspectorColumn = TransitBufferInspectorColumn;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const SawtoothProjectionChart_1 = require("./SawtoothProjectionChart");
const DELAY_OPTIONS = [
    { days: 0, label: 'По графику 0д' },
    { days: 4, label: 'Задержка +4д' },
    { days: 9, label: 'Граница +9д' }
];
function formatChannelOptionLabel(ch) {
    if (ch.id === 'express_auto')
        return `Ускоренный авто (+${ch.costSurchargePct}%)`;
    if (ch.id === 'regional_hub')
        return `Региональный хаб (+${ch.costSurchargePct}%)`;
    return `${ch.label} (+${ch.costSurchargePct}%)`;
}
function TransitBufferInspectorColumn({ state, activeSku }) {
    const activeLeadDays = (0, replenishmentEngine_1.computeEffectiveLeadDays)(activeSku, state.transitDelayDays, state.backupChannel);
    const activeRunoutDays = Number((activeSku.currentStock / Math.max(1, activeSku.dailyDemand)).toFixed(1));
    const activeTotalCoverDays = Number(((activeSku.currentStock + activeSku.orderQty) / Math.max(1, activeSku.dailyDemand)).toFixed(1));
    const activeTarget = (0, replenishmentEngine_1.computeRequiredTargetStock)(activeSku, state.transitDelayDays, state.backupChannel);
    const activeStoch = (0, replenishmentEngine_1.computeStochasticBuffer)(activeSku, state.transitDelayDays, state.backupChannel);
    const activeCoi = (0, replenishmentEngine_1.computeCostOfInaction)(activeSku, state.transitDelayDays, state.backupChannel);
    return (React.createElement("div", { className: "xl:col-span-5 flex flex-col gap-3.5 min-w-0" },
        React.createElement("article", { "data-card": "backup-channel-controls", className: "surface-card p-3.5 space-y-3" },
            React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0421\u0446\u0435\u043D\u0430\u0440\u0438\u0439 \u0437\u0430\u0434\u0435\u0440\u0436\u043A\u0438 \u043D\u0430 \u043C\u0430\u0440\u0448\u0440\u0443\u0442\u0435 \u0438 \u0440\u0435\u0437\u0435\u0440\u0432\u043D\u044B\u0439 \u043A\u0430\u043D\u0430\u043B"),
            React.createElement("div", { className: "seg-group flex-wrap", role: "group", "aria-label": "\u041F\u043E\u043F\u0440\u0430\u0432\u043A\u0430 \u0437\u0430\u0434\u0435\u0440\u0436\u043A\u0438" }, DELAY_OPTIONS.map((opt) => (React.createElement("button", { key: opt.days, type: "button", "aria-pressed": state.transitDelayDays === opt.days, onClick: () => domainStore_1.inventoryStore.setTransitScenario(opt.days, state.backupChannel), className: "seg-btn tabular-nums" }, opt.label)))),
            React.createElement("div", { className: "space-y-1" },
                React.createElement("label", { htmlFor: "backup-channel-select", className: "block text-xs font-medium text-secondary" }, "\u041B\u043E\u0433\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043A\u0438\u0439 \u043A\u0430\u043D\u0430\u043B \u0434\u043E\u0441\u0442\u0430\u0432\u043A\u0438"),
                React.createElement("select", { id: "backup-channel-select", value: state.backupChannel, onChange: (e) => domainStore_1.inventoryStore.setTransitScenario(state.transitDelayDays, e.target.value), className: "w-full field-compact" }, Object.values(presets_1.BACKUP_CHANNELS).map((ch) => (React.createElement("option", { key: ch.id, value: ch.id }, formatChannelOptionLabel(ch)))))),
            React.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => domainStore_1.inventoryStore.reinforceDeliveryBuffer(), className: "btn-primary w-full radius-control" }, "\u0423\u0441\u0438\u043B\u0438\u0442\u044C \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u043E\u0439 \u0437\u0430\u043F\u0430\u0441")),
        React.createElement("article", { "data-card": "active-sku-runout-readout", className: "surface-card p-3.5 space-y-2.5" },
            React.createElement("div", { className: "space-y-0.5" },
                React.createElement("div", { className: "text-xs text-muted" }, "\u0420\u0430\u0441\u0447\u0435\u0442 \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u043A\u0438 \u043F\u043E \u0430\u043A\u0442\u0438\u0432\u043D\u043E\u0439 \u043F\u043E\u0437\u0438\u0446\u0438\u0438"),
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, activeSku.name)),
            React.createElement("div", { className: "surface-inset p-2.5 space-y-1 text-sm tabular-nums" },
                React.createElement("div", { className: "flex items-center justify-between gap-2" },
                    React.createElement("span", { className: "text-secondary" }, "\u041F\u043E\u043B\u043A\u0430 \u0434\u043E \u043E\u0431\u043D\u0443\u043B\u0435\u043D\u0438\u044F / \u0412 \u043F\u0443\u0442\u0438"),
                    React.createElement("span", { className: "font-semibold text-primary" },
                        activeRunoutDays,
                        " \u0441\u0443\u0442. / \u043F\u0440\u0438\u0445\u043E\u0434 \u0414+",
                        activeLeadDays)),
                React.createElement("div", { className: "flex items-center justify-between gap-2" },
                    React.createElement("span", { className: "text-secondary" }, "\u041F\u043E\u043A\u0440\u044B\u0442\u0438\u0435 \u0441 \u0443\u0447\u0435\u0442\u043E\u043C \u0434\u043E\u0437\u0430\u043A\u0430\u0437\u0430"),
                    React.createElement("span", { className: "font-semibold text-primary" },
                        activeTotalCoverDays,
                        " \u0441\u0443\u0442. (",
                        activeSku.currentStock + activeSku.orderQty,
                        " \u0438\u0437 ",
                        activeTarget,
                        " \u0448\u0442.)")),
                React.createElement("div", { className: "flex items-center justify-between gap-2" },
                    React.createElement("span", { className: "text-secondary" }, "\u0421\u0442\u043E\u0445\u0430\u0441\u0442\u0438\u0447\u0435\u0441\u043A\u0438\u0439 \u0431\u0443\u0444\u0435\u0440 \u03C3-SS"),
                    React.createElement("span", { className: "font-semibold text-primary tabular-nums" },
                        "SL ",
                        activeStoch.serviceLevelPct,
                        "%, Z=",
                        activeStoch.zScore,
                        ", \u03C3L=",
                        activeStoch.sigmaLeadDays.toFixed(1),
                        " \u0441\u0443\u0442.")),
                activeCoi.riskKrub > 0 && (React.createElement("div", { className: "flex items-center justify-between gap-2" },
                    React.createElement("span", { className: "text-secondary" }, "\u0420\u0438\u0441\u043A \u043F\u0440\u043E\u0441\u0442\u043E\u044F (\u043D\u0435 \u0437\u0430\u043A\u0430\u0437\u044B\u0432\u0430\u0442\u044C)"),
                    React.createElement("span", { className: "font-semibold text-status-danger tabular-nums" },
                        Math.round(activeCoi.riskKrub),
                        " \u0442\u044B\u0441. \u20BD")))),
            React.createElement(SawtoothProjectionChart_1.SawtoothProjectionChart, { item: activeSku, transitDelayDays: state.transitDelayDays, backupChannel: state.backupChannel, compact: true }))));
}

  };

  moduleFactories["components/WarehouseGateScheduleCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WarehouseGateScheduleCard = WarehouseGateScheduleCard;
const react_1 = require("react");
const domainStore_1 = require("../store/domainStore");
const a11yDialog_1 = require("../utils/a11yDialog");
function buildShiftWindows(items, summary) {
    return [
        {
            id: 'gate-a1',
            shift: 'A',
            gateLabel: 'Смена А, ворота №1',
            cargoNote: 'Приоритетная автоматика, БалтКомплект',
            timeSlot: '08:00–11:30',
            pallets: Number((summary.totalPallets * 0.28).toFixed(1)),
            weightKg: Math.round(summary.totalWeightKg * 0.27),
            gateCap: Math.round(summary.effectivePalletLimit * 0.3),
            skuId: items[0]?.id || 'sku-power-ctrl'
        },
        {
            id: 'gate-a2',
            shift: 'A',
            gateLabel: 'Смена А, ворота №2',
            cargoNote: 'Силовая коммутация, УралПривод',
            timeSlot: '11:30–15:00',
            pallets: Number((summary.totalPallets * 0.34).toFixed(1)),
            weightKg: Math.round(summary.totalWeightKg * 0.35),
            gateCap: Math.round(summary.effectivePalletLimit * 0.34),
            skuId: items[2]?.id || items[0]?.id || 'sku-terminal-blk'
        },
        {
            id: 'gate-b3',
            shift: 'B',
            gateLabel: 'Смена Б, ворота №3',
            cargoNote: 'Датчики и реле защиты, СеверСнаб',
            timeSlot: '15:30–19:00',
            pallets: Number((summary.totalPallets * 0.2).toFixed(1)),
            weightKg: Math.round(summary.totalWeightKg * 0.19),
            gateCap: Math.round(summary.effectivePalletLimit * 0.22),
            skuId: items[1]?.id || items[0]?.id || 'sku-pressure-sens'
        },
        {
            id: 'gate-b4',
            shift: 'B',
            gateLabel: 'Смена Б, ворота №4',
            cargoNote: 'Кабельный монтаж и карантин, ВолгаПрибор',
            timeSlot: '19:00–22:00',
            pallets: Number((summary.totalPallets * 0.18).toFixed(1)),
            weightKg: Math.round(summary.totalWeightKg * 0.19),
            gateCap: Math.max(6, Math.round(summary.effectivePalletLimit * 0.2)),
            skuId: items[4]?.id || items[0]?.id || 'sku-cable-gland'
        }
    ];
}
function WarehouseGateScheduleCard({ items, activeSkuId, summary }) {
    const [shiftFilter, setShiftFilter] = (0, react_1.useState)('all');
    const shiftWindows = buildShiftWindows(items, summary);
    const visibleShiftRows = shiftFilter === 'all' ? shiftWindows : shiftWindows.filter((row) => row.shift === shiftFilter);
    const hasSelectedInShift = visibleShiftRows.some((s) => s.skuId === activeSkuId);
    return (React.createElement("article", { "data-card": "dock-gate-shift-schedule", className: "surface-card p-3.5 space-y-2.5" },
        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
            React.createElement("div", null,
                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0420\u0430\u0441\u043F\u0438\u0441\u0430\u043D\u0438\u0435 \u043E\u043A\u043E\u043D \u0440\u0430\u0437\u0433\u0440\u0443\u0437\u043A\u0438 \u0432\u043E\u0440\u043E\u0442 \u0420\u0426 \u043F\u043E \u0441\u043C\u0435\u043D\u0430\u043C (\u0421\u043C\u0435\u043D\u0430 \u0410 / \u0411)"),
                React.createElement("p", { className: "text-xs text-muted" }, "\u0420\u0430\u0441\u043F\u0440\u0435\u0434\u0435\u043B\u0435\u043D\u0438\u0435 \u043F\u0430\u043B\u043B\u0435\u0442 \u0438 \u0442\u043E\u043D\u043D\u0430\u0436\u0430 \u0442\u0435\u043A\u0443\u0449\u0435\u0439 \u0432\u043E\u043B\u043D\u044B \u043F\u043E \u0441\u043B\u043E\u0442\u0430\u043C \u0440\u0430\u043C\u043F\u044B")),
            React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0424\u0438\u043B\u044C\u0442\u0440 \u0441\u043C\u0435\u043D \u0440\u0430\u0437\u0433\u0440\u0443\u0437\u043A\u0438" }, [
                { id: 'all', label: 'Все смены' },
                { id: 'A', label: 'Смена А' },
                { id: 'B', label: 'Смена Б' }
            ].map((tab) => (React.createElement("button", { key: tab.id, type: "button", "aria-pressed": shiftFilter === tab.id, onClick: () => setShiftFilter(tab.id), className: "seg-btn" }, tab.label))))),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u0421\u043C\u0435\u043D\u0430 \u0438 \u0432\u043E\u0440\u043E\u0442\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041D\u0430\u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435 \u043F\u043E\u0442\u043E\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041E\u043A\u043D\u043E \u043F\u0440\u0438\u0435\u043C\u043A\u0438"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0422\u043E\u043D\u043D\u0430\u0436"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041A\u0432\u043E\u0442\u0430 \u0432\u043E\u0440\u043E\u0442"))),
                React.createElement("tbody", null, visibleShiftRows.map((slot, idx) => {
                    const isSelected = slot.skuId === activeSkuId;
                    const overSlot = slot.pallets > slot.gateCap + 0.2;
                    return (React.createElement("tr", { key: slot.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: isSelected || (!hasSelectedInShift && idx === 0) ? 0 : -1, "aria-selected": isSelected, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSku(slot.skuId), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSku(slot.skuId)), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left text-sm font-semibold text-primary whitespace-nowrap" }, slot.gateLabel),
                        React.createElement("td", { className: "text-left text-sm text-secondary" }, slot.cargoNote),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" }, slot.timeSlot),
                        React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                            slot.pallets.toFixed(1),
                            " \u043F\u0430\u043B\u043B."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            slot.weightKg,
                            " \u043A\u0433"),
                        React.createElement("td", { className: `text-right text-sm font-semibold whitespace-nowrap tabular-nums ${overSlot ? 'text-status-warning' : 'text-status-success'}` },
                            "\u0434\u043E ",
                            slot.gateCap,
                            " \u043F\u0430\u043B\u043B.")));
                }))))));
}

  };

  moduleFactories["components/WarehousePalletShareCard"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WarehousePalletShareCard = WarehousePalletShareCard;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const a11yDialog_1 = require("../utils/a11yDialog");
function WarehousePalletShareCard({ state, summary, discreteRampSlots }) {
    return (React.createElement("article", { "data-card": "pallet-share-breakdown", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-2.5" },
        React.createElement("div", { className: "flex items-center justify-between gap-2" },
            React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0414\u043E\u043B\u044F \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442 \u0438 \u043C\u0430\u0441\u0441\u044B \u043F\u043E \u0441\u0442\u0440\u043E\u043A\u0430\u043C"),
            React.createElement("span", { className: "text-sm font-semibold text-primary tabular-nums" },
                "\u0418\u0442\u043E\u0433\u043E ",
                summary.totalPallets.toFixed(1),
                " \u043F\u0430\u043B\u043B., ",
                summary.totalWeightKg,
                " \u043A\u0433")),
        React.createElement("div", { className: "overflow-x-auto" },
            React.createElement("table", { className: "ledger-table tabular-nums" },
                React.createElement("thead", null,
                    React.createElement("tr", { className: "surface-inset" },
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-left" }, "\u041F\u043E\u0437\u0438\u0446\u0438\u044F \u0438 \u043F\u043B\u043E\u0449\u0430\u0434\u043A\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u0440\u0442\u0438\u044F"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041C\u0430\u0441\u0441\u0430"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        React.createElement("th", { scope: "col", style: { borderBottomWidth: 0 }, className: "text-right tabular-nums" }, "\u0414\u043E\u043B\u044F \u0420\u0426"))),
                React.createElement("tbody", null, state.items.map((item, idx) => {
                    const pallets = (0, replenishmentEngine_1.computeItemPallets)(item);
                    const weight = (0, replenishmentEngine_1.computeItemWeightKg)(item);
                    const sharePct = Math.round((pallets / Math.max(0.1, summary.effectivePalletLimit)) * 100);
                    const sup = (0, presets_1.getSupplier)(item.supplierId);
                    const isActive = item.id === state.activeSkuId;
                    return (React.createElement("tr", { key: item.id, "data-entity-id": item.id, "data-selected": isActive ? 'true' : undefined, tabIndex: isActive ? 0 : -1, "aria-selected": isActive, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSku(item.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSku(item.id)), className: `cursor-pointer ${!isActive && idx % 2 === 1 ? 'surface-inset' : ''}` },
                        React.createElement("td", { className: "text-left" },
                            React.createElement("div", { className: "text-sm font-semibold text-primary" }, item.name),
                            React.createElement("div", { className: "text-xs text-muted" },
                                sup.name,
                                ", ",
                                item.category)),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            item.orderQty,
                            " \u0448\u0442."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            weight,
                            " \u043A\u0433"),
                        React.createElement("td", { className: "text-right text-sm font-semibold text-primary whitespace-nowrap tabular-nums" },
                            pallets.toFixed(1),
                            " \u043F\u0430\u043B\u043B."),
                        React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                            sharePct,
                            "%")));
                })))),
        React.createElement("div", { className: "surface-inset px-3 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs tabular-nums" },
            React.createElement("span", { className: "text-secondary" }, "\u0421\u0442\u0430\u043D\u0434\u0430\u0440\u0442 \u043F\u0430\u043B\u043B\u0435\u0442\u0438\u0440\u043E\u0432\u0430\u043D\u0438\u044F \u0420\u0426: EUR 1200\u00D7800 \u043C\u043C, \u0434\u043E 1,8 \u043C"),
            React.createElement("span", { className: "font-semibold text-primary tabular-nums" },
                "\u0412\u043E\u0440\u043E\u0442\u0430 1\u20134, ",
                discreteRampSlots,
                " \u0441\u043B\u043E\u0442. WMS")),
        React.createElement("div", { className: "surface-inset px-3 py-2.5 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs tabular-nums" },
            React.createElement("div", null,
                React.createElement("div", { className: "text-muted" }, "\u0421\u0443\u0445\u043E\u0439 \u0441\u0435\u043A\u0442\u043E\u0440 \u0420\u0426"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    (summary.totalPallets * 0.62).toFixed(1),
                    " \u043F\u0430\u043B\u043B. \u0441\u0442\u0435\u043B\u043B\u0430\u0436\u0438")),
            React.createElement("div", null,
                React.createElement("div", { className: "text-muted" }, "\u041A\u043B\u0438\u043C\u0430\u0442 \u0438 \u043A\u0430\u0440\u0430\u043D\u0442\u0438\u043D \u041E\u0422\u041A"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    (summary.totalPallets * 0.38).toFixed(1),
                    " \u043F\u0430\u043B\u043B. \u043A\u043E\u043D\u0442\u0440\u043E\u043B\u044C")),
            React.createElement("div", null,
                React.createElement("div", { className: "text-muted" }, "\u0411\u0443\u0444\u0435\u0440 \u043C\u0430\u043D\u0435\u0432\u0440\u0430 \u0440\u0430\u043C\u043F\u044B"),
                React.createElement("div", { className: "font-semibold text-primary" },
                    state.constraints.reserveGatePallets,
                    " \u043F\u0430\u043B\u043B. \u043F\u043E\u0434 \u0440\u0430\u0437\u0433\u0440\u0443\u0437\u043A\u0443")))));
}

  };

  moduleFactories["components/WhatIfSandboxModal"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.WhatIfSandboxModal = WhatIfSandboxModal;
const react_1 = __importStar(require("react"));
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const a11yDialog_1 = require("../utils/a11yDialog");
const DELAY_OPTIONS = [
    { days: 0, label: '0 сут.' },
    { days: 4, label: '+4 сут.' },
    { days: 9, label: '+9 сут.' }
];
const CHANNEL_OPTIONS = [
    { id: 'direct_rail', label: 'Ж/д' },
    { id: 'regional_hub', label: 'Хаб' },
    { id: 'express_auto', label: 'Авто' }
];
const PALLET_OPTIONS = [36, 42, 48];
function WhatIfSandboxModal({ open, onClose, state }) {
    const defaultStressDelay = state.transitDelayDays === 9 ? 4 : 9;
    const [stressDelay, setStressDelay] = (0, react_1.useState)(defaultStressDelay);
    const [stressChannel, setStressChannel] = (0, react_1.useState)('regional_hub');
    const [stressMaxPallets, setStressMaxPallets] = (0, react_1.useState)(42);
    const dialogRef = (0, a11yDialog_1.useDialogFocusTrap)(open);
    (0, react_1.useEffect)(() => {
        if (open) {
            setStressDelay(state.transitDelayDays === 9 ? 4 : 9);
        }
    }, [open, state.transitDelayDays]);
    if (!open)
        return null;
    const { baseline, stress, verdict } = (0, replenishmentEngine_1.computeWhatIfComparison)(state, stressDelay, stressChannel, stressMaxPallets);
    const palletDelta = stress.totalPallets - baseline.totalPallets;
    const handleApply = () => {
        domainStore_1.inventoryStore.setTransitScenario(stressDelay, stressChannel);
        domainStore_1.inventoryStore.updateConstraints({ maxPallets: stressMaxPallets });
        domainStore_1.inventoryStore.balanceOrder();
        onClose();
    };
    return (react_1.default.createElement("div", { ref: dialogRef, role: "dialog", "aria-modal": "true", "aria-labelledby": "whatif-modal-title", "data-whatif-modal": "true", onClick: (e) => {
            if (e.target === e.currentTarget)
                onClose();
        }, className: "fixed inset-0 z-50 flex items-start justify-center pt-10 p-3 bg-canvas/80" },
        react_1.default.createElement("div", { "data-ui": "surface", className: "surface-card p-4 w-full max-w-2xl space-y-3" },
            react_1.default.createElement("div", { className: "flex items-center justify-between gap-2" },
                react_1.default.createElement("h2", { id: "whatif-modal-title", className: "text-sm font-semibold text-primary" }, "What-If \u0441\u0438\u043C\u0443\u043B\u044F\u0442\u043E\u0440 \u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0435\u0432"),
                react_1.default.createElement("button", { type: "button", onClick: onClose, className: "btn-ghost radius-control", "aria-label": "\u0417\u0430\u043A\u0440\u044B\u0442\u044C \u0441\u0438\u043C\u0443\u043B\u044F\u0442\u043E\u0440" },
                    react_1.default.createElement("kbd", { className: "text-xs text-muted tabular-nums" }, "Esc"))),
            react_1.default.createElement("div", { className: "flex flex-wrap gap-2 items-center" },
                react_1.default.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0417\u0430\u0434\u0435\u0440\u0436\u043A\u0430 \u043F\u043B\u0435\u0447\u0430" }, DELAY_OPTIONS.map((opt) => (react_1.default.createElement("button", { key: opt.days, type: "button", "aria-pressed": stressDelay === opt.days, onClick: () => setStressDelay(opt.days), className: "seg-btn tabular-nums" }, opt.label)))),
                react_1.default.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u041B\u043E\u0433\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043A\u0438\u0439 \u043A\u0430\u043D\u0430\u043B" }, CHANNEL_OPTIONS.map((opt) => (react_1.default.createElement("button", { key: opt.id, type: "button", "aria-pressed": stressChannel === opt.id, onClick: () => setStressChannel(opt.id), className: "seg-btn" }, opt.label)))),
                react_1.default.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u041F\u043E\u0442\u043E\u043B\u043E\u043A \u043F\u0430\u043B\u043B\u0435\u0442 \u0420\u0426" }, PALLET_OPTIONS.map((cap) => (react_1.default.createElement("button", { key: cap, type: "button", "aria-pressed": stressMaxPallets === cap, onClick: () => setStressMaxPallets(cap), className: "seg-btn tabular-nums" },
                    cap,
                    " \u043F."))))),
            react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-3 tabular-nums" },
                react_1.default.createElement("div", { className: "surface-inset p-3 space-y-1.5 text-sm" },
                    react_1.default.createElement("div", { className: "text-xs font-semibold text-secondary" }, "\u0422\u0435\u043A\u0443\u0449\u0430\u044F \u0432\u043E\u043B\u043D\u0430 (\u0431\u0430\u0437\u0430)"),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        react_1.default.createElement("span", { className: "font-semibold text-primary whitespace-nowrap" }, baseline.totalPallets.toFixed(1))),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0411\u044E\u0434\u0436\u0435\u0442"),
                        react_1.default.createElement("span", { className: "font-semibold text-primary whitespace-nowrap" },
                            baseline.totalBudgetKrub.toFixed(1),
                            " \u0442\u044B\u0441. \u20BD")),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0414\u0435\u0444\u0438\u0446\u0438\u0442 SKU"),
                        react_1.default.createElement("span", { className: "font-semibold text-primary whitespace-nowrap" }, baseline.stockoutRiskCount)),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0426\u0435\u043D\u0430 \u0431\u0435\u0437\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044F"),
                        react_1.default.createElement("span", { className: `font-semibold whitespace-nowrap ${baseline.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'}` },
                            Math.round(baseline.totalCostOfInactionKrub),
                            " \u0442\u044B\u0441. \u20BD"))),
                react_1.default.createElement("div", { className: "surface-inset p-3 space-y-1.5 text-sm" },
                    react_1.default.createElement("div", { className: "text-xs font-semibold text-secondary" }, "\u0421\u0442\u0440\u0435\u0441\u0441-\u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0439 (\u0431\u0430\u043B\u0430\u043D\u0441)"),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u044B"),
                        react_1.default.createElement("span", { className: "font-semibold text-primary whitespace-nowrap" },
                            stress.totalPallets.toFixed(1),
                            ' ',
                            react_1.default.createElement("span", { className: "text-xs text-muted" },
                                "(",
                                palletDelta >= 0 ? '+' : '',
                                palletDelta.toFixed(1),
                                ")"))),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0411\u044E\u0434\u0436\u0435\u0442"),
                        react_1.default.createElement("span", { className: "font-semibold text-primary whitespace-nowrap" },
                            stress.totalBudgetKrub.toFixed(1),
                            " \u0442\u044B\u0441. \u20BD")),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0414\u0435\u0444\u0438\u0446\u0438\u0442 SKU"),
                        react_1.default.createElement("span", { className: `font-semibold whitespace-nowrap ${stress.stockoutRiskCount > 0 ? 'text-status-danger' : 'text-status-success'}` }, stress.stockoutRiskCount)),
                    react_1.default.createElement("div", { className: "flex items-baseline justify-between gap-2" },
                        react_1.default.createElement("span", { className: "text-secondary" }, "\u0426\u0435\u043D\u0430 \u0431\u0435\u0437\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044F"),
                        react_1.default.createElement("span", { className: `font-semibold whitespace-nowrap ${stress.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'}` },
                            Math.round(stress.totalCostOfInactionKrub),
                            " \u0442\u044B\u0441. \u20BD")))),
            react_1.default.createElement("div", { className: "surface-inset px-3 py-2 text-xs text-secondary" }, verdict),
            react_1.default.createElement("div", { className: "flex items-center justify-end gap-2" },
                react_1.default.createElement("button", { type: "button", onClick: onClose, className: "btn-ghost radius-control" }, "\u041E\u0442\u043C\u0435\u043D\u0430"),
                react_1.default.createElement("button", { type: "button", "data-apply-whatif": "true", onClick: handleApply, className: "btn-primary radius-control" }, "\u041F\u0440\u0438\u043C\u0435\u043D\u0438\u0442\u044C \u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0439 \u043A \u0432\u043E\u043B\u043D\u0435")))));
}

  };

  moduleFactories["data/flowNetwork"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OUTBOUND_SPECS = exports.SUPPLIER_GEO = exports.CENTRAL_HUB_META = void 0;
exports.computeSupplyNetwork = computeSupplyNetwork;
const presets_1 = require("./presets");
const flowNetworkGeo_1 = require("./flowNetworkGeo");
Object.defineProperty(exports, "CENTRAL_HUB_META", { enumerable: true, get: function () { return flowNetworkGeo_1.CENTRAL_HUB_META; } });
Object.defineProperty(exports, "OUTBOUND_SPECS", { enumerable: true, get: function () { return flowNetworkGeo_1.OUTBOUND_SPECS; } });
Object.defineProperty(exports, "SUPPLIER_GEO", { enumerable: true, get: function () { return flowNetworkGeo_1.SUPPLIER_GEO; } });
const flowNetworkOutbound_1 = require("./flowNetworkOutbound");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
function resolveInboundRiskReason(riskySkus, leadDays, assignedCount) {
    if (riskySkus.length > 0)
        return `Дефицит буфера: ${riskySkus[0].name}`;
    if (leadDays > 12)
        return `Длинное плечо ${leadDays} сут. по каналу`;
    if (assignedCount === 0)
        return 'Резервная площадка без активных строк';
    return 'Поставка в графике ворот РЦ';
}
function computeSupplyNetwork(state) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const ch = presets_1.BACKUP_CHANNELS[state.backupChannel];
    const inbound = presets_1.SUPPLIER_LIST.map((sup) => {
        const geo = flowNetworkGeo_1.SUPPLIER_GEO[sup.id];
        const [cx, cy] = flowNetworkGeo_1.INBOUND_CONTROL_POINTS[sup.id];
        const { path, midX, midY } = (0, flowNetworkOutbound_1.quadBezier)(geo.x, geo.y, cx, cy, flowNetworkGeo_1.CENTRAL_HUB_META.x, flowNetworkGeo_1.CENTRAL_HUB_META.y);
        const assigned = state.items.filter((it) => it.supplierId === sup.id);
        const totalUnits = assigned.reduce((s, it) => s + it.orderQty, 0);
        const pallets = Number(assigned.reduce((s, it) => s + (0, replenishmentEngine_1.computeItemPallets)(it), 0).toFixed(1));
        const weightKg = assigned.reduce((s, it) => s + (0, replenishmentEngine_1.computeItemWeightKg)(it), 0);
        const budgetKrub = Number(assigned.reduce((s, it) => s + (0, replenishmentEngine_1.computeItemCostKrub)(it, state.backupChannel), 0).toFixed(1));
        const leadDays = Math.max(2, sup.leadDays + state.transitDelayDays + ch.leadDeltaDays);
        const riskySkus = assigned.filter((it) => (0, replenishmentEngine_1.isSkuAtStockoutRisk)(it, state.transitDelayDays, state.backupChannel));
        const atRisk = riskySkus.length > 0 || (assigned.length > 0 && leadDays > 12);
        return {
            id: sup.id,
            supplierName: sup.name,
            city: sup.city,
            geo,
            items: assigned,
            skuCount: assigned.length,
            totalUnits,
            pallets,
            weightKg,
            budgetKrub,
            leadDays,
            reliabilityPct: sup.reliabilityPct,
            atRisk,
            riskReason: resolveInboundRiskReason(riskySkus, leadDays, assigned.length),
            arcPath: path,
            midX,
            midY
        };
    });
    const outbound = (0, flowNetworkOutbound_1.buildOutboundArcs)(state, summary);
    const inboundPallets = Number(inbound.reduce((s, f) => s + f.pallets, 0).toFixed(1));
    const outboundPallets = Number(outbound.reduce((s, f) => s + f.pallets, 0).toFixed(1));
    const outboundValueKrub = Number(outbound.reduce((s, f) => s + f.valueKrub, 0).toFixed(1));
    const readyCustomersCount = outbound.filter((o) => o.status === 'ready').length;
    const riskCorridorsCount = inbound.filter((i) => i.atRisk).length + outbound.filter((o) => o.status === 'at_risk').length;
    const otifNetworkPct = Number(Math.min(99.6, Math.max(74.0, summary.avgReliabilityPct - riskCorridorsCount * 2.4 - (summary.overLimitCount > 0 ? 1.8 : 0))).toFixed(1));
    return {
        inbound,
        outbound,
        inboundPallets,
        outboundPallets,
        outboundValueKrub,
        readyCustomersCount,
        riskCorridorsCount,
        otifNetworkPct
    };
}

  };

  moduleFactories["data/flowNetworkGeo"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OUTBOUND_CONTROL_POINTS = exports.INBOUND_CONTROL_POINTS = exports.OUTBOUND_SPECS = exports.SUPPLIER_GEO = exports.CENTRAL_HUB_META = void 0;
exports.CENTRAL_HUB_META = {
    id: 'dc-moscow',
    kind: 'hub',
    city: 'Москва (Подольск)',
    title: 'Центральный РЦ консолидации',
    coordsLabel: '55.4° с.ш., 37.6° в.д.',
    highwayLabel: 'ЦКАД / Южный терминал',
    distanceKm: 0,
    gateLabel: 'Смена А, ворота 1–4',
    x: 266,
    y: 120,
    labelAnchor: 'end',
    labelDx: -14,
    labelDy: 4
};
exports.SUPPLIER_GEO = {
    'balt-komplekt': {
        id: 'balt-komplekt',
        kind: 'supplier',
        city: 'Санкт-Петербург',
        title: 'БалтКомплект (Шушары)',
        coordsLabel: '59.8° с.ш., 30.4° в.д.',
        highwayLabel: 'М-11 Нева',
        distanceKm: 680,
        gateLabel: 'Ворота №1',
        x: 112,
        y: 44,
        labelAnchor: 'start',
        labelDx: 12,
        labelDy: -6
    },
    'sever-snab': {
        id: 'sever-snab',
        kind: 'supplier',
        city: 'Ярославль',
        title: 'СеверСнаб (Тутаевское)',
        coordsLabel: '57.6° с.ш., 39.9° в.д.',
        highwayLabel: 'М-8 Холмогоры',
        distanceKm: 270,
        gateLabel: 'Ворота №1',
        x: 322,
        y: 58,
        labelAnchor: 'start',
        labelDx: 11,
        labelDy: -5
    },
    'volga-pribor': {
        id: 'volga-pribor',
        kind: 'supplier',
        city: 'Казань',
        title: 'ВолгаПрибор (Химград)',
        coordsLabel: '55.8° с.ш., 49.1° в.д.',
        highwayLabel: 'М-12 Восток',
        distanceKm: 820,
        gateLabel: 'Ворота №3',
        x: 536,
        y: 110,
        labelAnchor: 'middle',
        labelDx: 0,
        labelDy: -14
    },
    'ural-privod': {
        id: 'ural-privod',
        kind: 'supplier',
        city: 'Екатеринбург',
        title: 'УралПривод (Уралмаш)',
        coordsLabel: '56.9° с.ш., 60.6° в.д.',
        highwayLabel: 'Транссиб / Р-242',
        distanceKm: 1780,
        gateLabel: 'Ворота №2',
        x: 696,
        y: 84,
        labelAnchor: 'end',
        labelDx: -4,
        labelDy: 18
    }
};
exports.OUTBOUND_SPECS = [
    {
        id: 'out-tula',
        customerName: 'Тульский завод щитовой сборки',
        contractCode: 'Спецификация отгрузки №104',
        dispatchWindowDays: 7,
        dispatchWindowLabel: 'Д+7',
        vehicleLabel: 'Прямой пятитонник, ворота №1',
        geo: {
            id: 'out-tula',
            kind: 'customer',
            city: 'Тула',
            title: 'Тульский завод щитовой сборки',
            coordsLabel: '54.2° с.ш., 37.6° в.д.',
            highwayLabel: 'М-2 Крым',
            distanceKm: 165,
            gateLabel: 'Отгрузка №1',
            x: 214,
            y: 168,
            labelAnchor: 'end',
            labelDx: -12,
            labelDy: 5
        },
        allocations: [
            { skuId: 'sku-power-ctrl', fallbackCategory: 'Автоматика', requiredQty: 42 },
            { skuId: 'sku-terminal-blk', fallbackCategory: 'Коммутация', requiredQty: 180 }
        ]
    },
    {
        id: 'out-nn',
        customerName: 'Нижегородский контур Сормово',
        contractCode: 'Спецификация отгрузки №108',
        dispatchWindowDays: 9,
        dispatchWindowLabel: 'Д+9',
        vehicleLabel: 'Контурный евроборт, ворота №2',
        geo: {
            id: 'out-nn',
            kind: 'customer',
            city: 'Нижний Новгород',
            title: 'Нижегородский контур Сормово',
            coordsLabel: '56.3° с.ш., 44.0° в.д.',
            highwayLabel: 'М-7 Волга',
            distanceKm: 430,
            gateLabel: 'Отгрузка №2',
            x: 420,
            y: 128,
            labelAnchor: 'start',
            labelDx: 11,
            labelDy: 4
        },
        allocations: [
            { skuId: 'sku-pressure-sens', fallbackCategory: 'Измерения', requiredQty: 38 },
            { skuId: 'sku-cable-gland', fallbackCategory: 'Монтаж', requiredQty: 160 }
        ]
    },
    {
        id: 'out-voronezh',
        customerName: 'Воронежский узел энергомонтажа',
        contractCode: 'Спецификация отгрузки №112',
        dispatchWindowDays: 10,
        dispatchWindowLabel: 'Д+10',
        vehicleLabel: 'Паллетный фургон, ворота №3',
        geo: {
            id: 'out-voronezh',
            kind: 'customer',
            city: 'Воронеж',
            title: 'Воронежский узел энергомонтажа',
            coordsLabel: '51.7° с.ш., 39.2° в.д.',
            highwayLabel: 'М-4 Дон',
            distanceKm: 505,
            gateLabel: 'Отгрузка №3',
            x: 306,
            y: 196,
            labelAnchor: 'start',
            labelDx: 12,
            labelDy: 4
        },
        allocations: [
            { skuId: 'sku-line-relay', fallbackCategory: 'Защита', requiredQty: 44 },
            { skuId: 'sku-power-ctrl', fallbackCategory: 'Автоматика', requiredQty: 24 }
        ]
    },
    {
        id: 'out-samara',
        customerName: 'Поволжский технопарк Самара',
        contractCode: 'Спецификация отгрузки №119',
        dispatchWindowDays: 12,
        dispatchWindowLabel: 'Д+12',
        vehicleLabel: 'Магистральная фура, ворота №4',
        geo: {
            id: 'out-samara',
            kind: 'customer',
            city: 'Самара',
            title: 'Поволжский технопарк Самара',
            coordsLabel: '53.2° с.ш., 50.2° в.д.',
            highwayLabel: 'М-5 Урал',
            distanceKm: 1040,
            gateLabel: 'Отгрузка №4',
            x: 562,
            y: 176,
            labelAnchor: 'start',
            labelDx: 12,
            labelDy: 5
        },
        allocations: [
            { skuId: 'sku-terminal-blk', fallbackCategory: 'Коммутация', requiredQty: 160 },
            { skuId: 'sku-pressure-sens', fallbackCategory: 'Измерения', requiredQty: 26 },
            { skuId: 'sku-cable-gland', fallbackCategory: 'Монтаж', requiredQty: 140 }
        ]
    }
];
exports.INBOUND_CONTROL_POINTS = {
    'balt-komplekt': [174, 88],
    'sever-snab': [296, 80],
    'volga-pribor': [404, 66],
    'ural-privod': [488, 28]
};
exports.OUTBOUND_CONTROL_POINTS = {
    'out-tula': [222, 144],
    'out-nn': [346, 134],
    'out-voronezh': [282, 180],
    'out-samara': [448, 184]
};

  };

  moduleFactories["data/flowNetworkOutbound"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.quadBezier = quadBezier;
exports.buildOutboundArcs = buildOutboundArcs;
const presets_1 = require("./presets");
const flowNetworkGeo_1 = require("./flowNetworkGeo");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
function quadBezier(x0, y0, cx, cy, x1, y1) {
    const path = `M ${x0} ${y0} Q ${cx} ${cy} ${x1} ${y1}`;
    const midX = Math.round(0.25 * x0 + 0.5 * cx + 0.25 * x1);
    const midY = Math.round(0.25 * y0 + 0.5 * cy + 0.25 * y1);
    return { path, midX, midY };
}
function buildOutboundArcs(state, summary) {
    const customSkus = state.items.filter((it) => it.id.startsWith('sku-custom-'));
    return flowNetworkGeo_1.OUTBOUND_SPECS.map((spec) => {
        const [cx, cy] = flowNetworkGeo_1.OUTBOUND_CONTROL_POINTS[spec.id];
        const { path, midX, midY } = quadBezier(flowNetworkGeo_1.CENTRAL_HUB_META.x, flowNetworkGeo_1.CENTRAL_HUB_META.y, cx, cy, spec.geo.x, spec.geo.y);
        const lines = [];
        let palletsAcc = 0;
        let weightAcc = 0;
        let valueAcc = 0;
        const supplierSet = new Set();
        const effectiveAllocations = spec.id === 'out-samara' && customSkus.length > 0
            ? [
                ...spec.allocations,
                ...customSkus.map((cs) => ({
                    skuId: cs.id,
                    fallbackCategory: cs.category,
                    requiredQty: Math.max(20, Math.round(cs.orderQty * 0.5))
                }))
            ]
            : spec.allocations;
        for (const alloc of effectiveAllocations) {
            const matched = state.items.find((it) => it.id === alloc.skuId) ||
                state.items.find((it) => it.category === alloc.fallbackCategory) ||
                state.items[0];
            if (!matched)
                continue;
            const sup = (0, presets_1.getSupplier)(matched.supplierId);
            supplierSet.add(matched.supplierId);
            const leadDays = (0, replenishmentEngine_1.computeEffectiveLeadDays)(matched, state.transitDelayDays, state.backupChannel);
            const availableAfterOrder = matched.currentStock + matched.orderQty;
            const skuRisk = (0, replenishmentEngine_1.isSkuAtStockoutRisk)(matched, state.transitDelayDays, state.backupChannel);
            const lateArrival = matched.currentStock < alloc.requiredQty && leadDays > spec.dispatchWindowDays + 2;
            const shortfall = availableAfterOrder < alloc.requiredQty || skuRisk || lateArrival;
            palletsAcc += alloc.requiredQty / Math.max(1, matched.unitsPerPallet);
            weightAcc += Math.round(alloc.requiredQty * matched.unitWeightKg);
            valueAcc += Number((alloc.requiredQty * matched.unitCostKrub * 1.14).toFixed(1));
            lines.push({
                skuId: matched.id,
                skuName: matched.name,
                supplierId: matched.supplierId,
                supplierCity: sup.city,
                requiredQty: alloc.requiredQty,
                availableAfterOrder,
                leadDays,
                shortfall
            });
        }
        const bottleneckLine = lines.find((l) => l.shortfall);
        let status = 'ready';
        let statusLabel = 'Готово к отгрузке';
        let bottleneckNote = 'Комплект обеспечен складским запасом и волной';
        if (bottleneckLine) {
            status = 'at_risk';
            statusLabel = 'Риск недокомплекта';
            bottleneckNote = `Узкое место: ${bottleneckLine.skuName} (${bottleneckLine.supplierCity}, ${bottleneckLine.leadDays} сут.)`;
        }
        else if (summary.overLimitCount > 0) {
            status = 'gate_wait';
            statusLabel = 'Ждет укладку РЦ';
            bottleneckNote = 'Перегруз приемки РЦ задерживает комплектацию ворот';
        }
        return {
            id: spec.id,
            customerName: spec.customerName,
            city: spec.geo.city,
            contractCode: spec.contractCode,
            vehicleLabel: spec.vehicleLabel,
            dispatchWindowDays: spec.dispatchWindowDays,
            dispatchWindowLabel: spec.dispatchWindowLabel,
            geo: spec.geo,
            lines,
            peggedSuppliers: Array.from(supplierSet),
            pallets: Number(palletsAcc.toFixed(1)),
            weightKg: weightAcc,
            valueKrub: Number(valueAcc.toFixed(1)),
            status,
            statusLabel,
            bottleneckNote,
            arcPath: path,
            midX,
            midY
        };
    });
}

  };

  moduleFactories["data/presets"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BACKUP_CHANNELS = exports.SUPPLIER_LIST = exports.SUPPLIERS = exports.SCREEN_DEFINITIONS = exports.SCENARIO_PRESETS = void 0;
exports.getSupplier = getSupplier;
exports.getSupplierBatchStep = getSupplierBatchStep;
const scenarioPresets_1 = require("./scenarioPresets");
Object.defineProperty(exports, "SCENARIO_PRESETS", { enumerable: true, get: function () { return scenarioPresets_1.SCENARIO_PRESETS; } });
exports.SCREEN_DEFINITIONS = [
    { id: 'screen-replenishment-notebook', label: 'Ведомость заказа', shortLabel: 'Заказ', shortcut: 'Alt+1' },
    { id: 'screen-supply-map', label: 'Карта потоков', shortLabel: 'Карта', shortcut: 'Alt+2' },
    { id: 'screen-warehouse-limits', label: 'Габариты склада', shortLabel: 'Склад', shortcut: 'Alt+3' },
    { id: 'screen-supplier-choice', label: 'Поставщики', shortLabel: 'Базы', shortcut: 'Alt+4' },
    { id: 'screen-delivery-buffer', label: 'Страховой буфер', shortLabel: 'Буфер', shortcut: 'Alt+5' },
    { id: 'screen-order-export', label: 'Спецификация CSV', shortLabel: 'Файл', shortcut: 'Alt+6' }
];
exports.SUPPLIERS = {
    'balt-komplekt': {
        id: 'balt-komplekt',
        name: 'БалтКомплект',
        city: 'Санкт-Петербург',
        leadDays: 6,
        reliabilityPct: 97.8,
        priceFactor: 1.03,
        minBatchQty: 10,
        termsNote: 'Быстрая отгрузка паллетами с терминала Шушары'
    },
    'ural-privod': {
        id: 'ural-privod',
        name: 'УралПривод',
        city: 'Екатеринбург',
        leadDays: 11,
        reliabilityPct: 94.2,
        priceFactor: 0.95,
        minBatchQty: 20,
        termsNote: 'Заводская цена на силовую коммутацию и шкафную сборку'
    },
    'volga-pribor': {
        id: 'volga-pribor',
        name: 'ВолгаПрибор',
        city: 'Казань',
        leadDays: 14,
        reliabilityPct: 89.4,
        priceFactor: 0.91,
        minBatchQty: 20,
        termsNote: 'Минимальная отпускная цена при плановом плече 2 недели'
    },
    'sever-snab': {
        id: 'sever-snab',
        name: 'СеверСнаб',
        city: 'Ярославль',
        leadDays: 5,
        reliabilityPct: 98.4,
        priceFactor: 1.06,
        minBatchQty: 10,
        termsNote: 'Приоритетный резерв для позиций с риском остановки линии'
    }
};
function getSupplier(supplierId) {
    return exports.SUPPLIERS[supplierId] || exports.SUPPLIERS['balt-komplekt'];
}
function getSupplierBatchStep(supplierId) {
    return Math.max(10, getSupplier(supplierId).minBatchQty || 10);
}
exports.SUPPLIER_LIST = [
    exports.SUPPLIERS['balt-komplekt'],
    exports.SUPPLIERS['ural-privod'],
    exports.SUPPLIERS['volga-pribor'],
    exports.SUPPLIERS['sever-snab']
];
exports.BACKUP_CHANNELS = {
    direct_rail: {
        id: 'direct_rail',
        label: 'Прямой ж/д вагон',
        leadDeltaDays: 0,
        costSurchargePct: 0,
        note: 'Базовый тариф без ускорения в пути'
    },
    regional_hub: {
        id: 'regional_hub',
        label: 'Региональный склад',
        leadDeltaDays: -3,
        costSurchargePct: 3.5,
        note: 'Перегрузка через распределительный хаб с экономией 3 суток'
    },
    express_auto: {
        id: 'express_auto',
        label: 'Ускоренный авторейс',
        leadDeltaDays: -5,
        costSurchargePct: 7.5,
        note: 'Прямая машина до ворот склада при угрозе дефицита'
    }
};

  };

  moduleFactories["data/scenarioPresets"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SCENARIO_PRESETS = void 0;
function makeSku(id, name, category, currentStock, dailyDemand, reorderPoint, safetyDays, orderQty, unitCostKrub, unitWeightKg, unitsPerPallet, supplierId, priority) {
    return {
        id,
        name,
        category,
        currentStock,
        dailyDemand,
        reorderPoint,
        safetyDays,
        orderQty,
        unitCostKrub,
        unitWeightKg,
        unitsPerPallet,
        supplierId,
        priority
    };
}
exports.SCENARIO_PRESETS = [
    {
        id: 'preset-seasonal-peak',
        label: 'Осенний пик спроса',
        summary: 'Рост отгрузок со склада, риск дефицита датчиков и перегруз ячеек приемки по паллетам',
        waveLabel: 'Закупочная волна №46 (Ноябрь)',
        transitDelayDays: 0,
        backupChannel: 'direct_rail',
        constraints: { maxPallets: 46, reserveGatePallets: 4, maxWeightKg: 11800, maxBudgetKrub: 3650 },
        items: [
            makeSku('sku-power-ctrl', 'Контроллеры питания шкафа', 'Автоматика', 34, 6, 48, 8, 60, 14.4, 12.5, 12, 'balt-komplekt', 'critical'),
            makeSku('sku-pressure-sens', 'Датчики давления контура', 'Измерения', 22, 7, 56, 10, 50, 9.2, 8.4, 15, 'ural-privod', 'critical'),
            makeSku('sku-terminal-blk', 'Клеммные колодки силовые', 'Коммутация', 140, 9, 90, 8, 440, 3.1, 14.2, 20, 'ural-privod', 'standard'),
            makeSku('sku-line-relay', 'Реле защиты линии', 'Защита', 28, 5, 45, 8, 40, 11.6, 9.5, 16, 'volga-pribor', 'critical'),
            makeSku('sku-cable-gland', 'Кабельные вводы герметичные', 'Монтаж', 190, 10, 110, 6, 420, 2.3, 11.4, 25, 'volga-pribor', 'standard')
        ]
    },
    {
        id: 'preset-port-delay',
        label: 'Задержка на границе',
        summary: 'Сдвиг транзитных партий на 9 дней, перевод критичных позиций на резервный канал',
        waveLabel: 'Транзитная волна (сдвиг 9 сут.)',
        transitDelayDays: 9,
        backupChannel: 'regional_hub',
        constraints: { maxPallets: 48, reserveGatePallets: 4, maxWeightKg: 12400, maxBudgetKrub: 3900 },
        items: [
            makeSku('sku-power-ctrl', 'Контроллеры питания шкафа', 'Автоматика', 26, 6, 54, 10, 50, 14.4, 12.5, 12, 'ural-privod', 'critical'),
            makeSku('sku-pressure-sens', 'Датчики давления контура', 'Измерения', 18, 7, 62, 12, 60, 9.2, 8.4, 15, 'volga-pribor', 'critical'),
            makeSku('sku-terminal-blk', 'Клеммные колодки силовые', 'Коммутация', 155, 8, 85, 6, 400, 3.1, 14.2, 20, 'ural-privod', 'standard'),
            makeSku('sku-line-relay', 'Реле защиты линии', 'Защита', 24, 5, 50, 10, 40, 11.6, 9.5, 16, 'sever-snab', 'critical'),
            makeSku('sku-cable-gland', 'Кабельные вводы герметичные', 'Монтаж', 210, 9, 100, 6, 380, 2.3, 11.4, 25, 'volga-pribor', 'standard')
        ]
    },
    {
        id: 'preset-tight-warehouse',
        label: 'Сжатый лимит склада',
        summary: 'Свободно лишь 34 паллетоместа в зоне приемки при жестком потолке закупочного бюджета',
        waveLabel: 'Инвентаризация сектора Б (сжатая приемка)',
        transitDelayDays: 0,
        backupChannel: 'direct_rail',
        constraints: { maxPallets: 34, reserveGatePallets: 2, maxWeightKg: 9600, maxBudgetKrub: 3150 },
        items: [
            makeSku('sku-power-ctrl', 'Контроллеры питания шкафа', 'Автоматика', 36, 6, 48, 8, 60, 14.4, 12.5, 12, 'balt-komplekt', 'critical'),
            makeSku('sku-pressure-sens', 'Датчики давления контура', 'Измерения', 30, 6, 50, 8, 60, 9.2, 8.4, 15, 'balt-komplekt', 'critical'),
            makeSku('sku-terminal-blk', 'Клеммные колодки силовые', 'Коммутация', 130, 8, 80, 6, 360, 3.1, 14.2, 20, 'ural-privod', 'standard'),
            makeSku('sku-line-relay', 'Реле защиты линии', 'Защита', 32, 5, 45, 8, 50, 11.6, 9.5, 16, 'sever-snab', 'critical'),
            makeSku('sku-cable-gland', 'Кабельные вводы герметичные', 'Монтаж', 185, 9, 100, 6, 320, 2.3, 11.4, 25, 'volga-pribor', 'standard')
        ]
    }
];

  };

  moduleFactories["data/supplierContracts"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SUPPLIER_CONTRACT_TERMS = exports.SHORT_SUPPLIER_NAMES = void 0;
exports.SHORT_SUPPLIER_NAMES = {
    'balt-komplekt': 'БалтКомплект',
    'ural-privod': 'УралПривод',
    'volga-pribor': 'ВолгаПрибор',
    'sever-snab': 'СеверСнаб'
};
exports.SUPPLIER_CONTRACT_TERMS = {
    'balt-komplekt': {
        incoterms: 'DAP Шушары, европаллет',
        deferralDays: 30,
        moqStepQty: 10,
        slaPenaltyPct: '0,15%',
        leadVariance: '±0,5 сут.',
        packaging: 'Кратность 10 шт., термоусадка'
    },
    'ural-privod': {
        incoterms: 'FCA Екатеринбург, ж/д',
        deferralDays: 45,
        moqStepQty: 20,
        slaPenaltyPct: '0,10%',
        leadVariance: '±1,5 сут.',
        packaging: 'Кратность 20 шт., силовой короб'
    },
    'volga-pribor': {
        incoterms: 'CPT РЦ, сборный груз',
        deferralDays: 60,
        moqStepQty: 20,
        slaPenaltyPct: '0,08%',
        leadVariance: '±2,0 сут.',
        packaging: 'Кратность 20 шт., заводская тара'
    },
    'sever-snab': {
        incoterms: 'DAP РЦ, экспресс-борт',
        deferralDays: 21,
        moqStepQty: 10,
        slaPenaltyPct: '0,20%',
        leadVariance: '±0,4 сут.',
        packaging: 'Кратность 10 шт., спецконтейнер'
    }
};

  };

  moduleFactories["hooks/useAnimatedNumber"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.useAnimatedNumber = useAnimatedNumber;
const react_1 = require("react");
function shouldSkipAnimation() {
    if (typeof window === 'undefined')
        return true;
    if (typeof navigator !== 'undefined' && navigator.webdriver)
        return true;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
        return true;
    return false;
}
function useAnimatedNumber(target, durationMs = 160) {
    const [displayValue, setDisplayValue] = (0, react_1.useState)(target);
    const currentRef = (0, react_1.useRef)(target);
    (0, react_1.useEffect)(() => {
        if (shouldSkipAnimation() || durationMs <= 0) {
            currentRef.current = target;
            setDisplayValue(target);
            return;
        }
        const startValue = currentRef.current;
        const delta = target - startValue;
        if (Math.abs(delta) < 0.001) {
            currentRef.current = target;
            setDisplayValue(target);
            return;
        }
        let rafId = 0;
        const startTime = performance.now();
        const tick = (now) => {
            const elapsed = now - startTime;
            const progress = Math.min(1, Math.max(0, elapsed / durationMs));
            const eased = 1 - Math.pow(1 - progress, 3);
            const next = startValue + delta * eased;
            currentRef.current = next;
            setDisplayValue(next);
            if (progress < 1) {
                rafId = window.requestAnimationFrame(tick);
            }
            else {
                currentRef.current = target;
                setDisplayValue(target);
            }
        };
        rafId = window.requestAnimationFrame(tick);
        return () => {
            if (rafId) {
                window.cancelAnimationFrame(rafId);
            }
        };
    }, [target, durationMs]);
    if (shouldSkipAnimation()) {
        return target;
    }
    return displayValue;
}

  };

  moduleFactories["hooks/useGlobalWorkbenchShortcuts"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.useGlobalWorkbenchShortcuts = useGlobalWorkbenchShortcuts;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
function useGlobalWorkbenchShortcuts({ onToggleCmdk, onToggleWhatIf, onCloseAllModals, onSetViewState }) {
    (0, react_1.useEffect)(() => {
        const onKeyDown = (e) => {
            const target = e.target;
            const isEditableField = Boolean(target &&
                (target.tagName === 'INPUT' ||
                    target.tagName === 'TEXTAREA' ||
                    target.tagName === 'SELECT' ||
                    target.isContentEditable));
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                onToggleCmdk();
                return;
            }
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
                if (isEditableField)
                    return;
                e.preventDefault();
                domainStore_1.inventoryStore.undo();
                return;
            }
            if (e.altKey && !e.metaKey && !e.ctrlKey && !isEditableField) {
                if (e.code === 'KeyS' || e.key.toLowerCase() === 's') {
                    e.preventDefault();
                    onToggleWhatIf();
                    return;
                }
                if (e.code === 'KeyB' || e.key.toLowerCase() === 'b') {
                    e.preventDefault();
                    domainStore_1.inventoryStore.balanceOrder();
                    return;
                }
                const codeDigit = e.code?.startsWith('Digit') ? Number(e.code.slice(5)) - 1 : -1;
                const digitIdx = codeDigit >= 0 ? codeDigit : Number(e.key) - 1;
                if (digitIdx >= 0 && digitIdx < presets_1.SCREEN_DEFINITIONS.length) {
                    e.preventDefault();
                    onSetViewState('Ideal');
                    domainStore_1.inventoryStore.setScreen(presets_1.SCREEN_DEFINITIONS[digitIdx].id);
                    return;
                }
            }
            if (e.key === 'Escape') {
                onCloseAllModals();
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onToggleCmdk, onToggleWhatIf, onCloseAllModals, onSetViewState]);
}

  };

  moduleFactories["main"] = function(exports, module, require) {
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const react_1 = __importDefault(require("react"));
const client_1 = require("react-dom/client");
require("../tokens.css");
require("./styles/utilities.css");
const App_1 = __importDefault(require("./App"));
const rootElement = document.getElementById('root');
if (rootElement) {
    (0, client_1.createRoot)(rootElement).render(react_1.default.createElement(react_1.default.StrictMode, null,
        react_1.default.createElement(App_1.default, null)));
}

  };

  moduleFactories["screens/ScreenDeliveryBuffer"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenDeliveryBuffer = ScreenDeliveryBuffer;
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const Icons_1 = require("../components/Icons");
const CorridorSlaMatrixCard_1 = require("../components/CorridorSlaMatrixCard");
const TransitBufferInspectorColumn_1 = require("../components/TransitBufferInspectorColumn");
const a11yDialog_1 = require("../utils/a11yDialog");
function ScreenDeliveryBuffer({ state }) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
    const activeLeadDays = (0, replenishmentEngine_1.computeEffectiveLeadDays)(activeSku, state.transitDelayDays, state.backupChannel);
    const channelInfo = presets_1.BACKUP_CHANNELS[state.backupChannel];
    const channelShiftLabel = channelInfo.leadDeltaDays <= 0 ? `${channelInfo.leadDeltaDays}` : `+${channelInfo.leadDeltaDays}`;
    return (React.createElement("section", { "data-screen-view": "screen-delivery-buffer", "data-shell": "transit-buffer-matrix", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5" },
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start" },
            React.createElement("div", { className: "xl:col-span-7 min-w-0" },
                React.createElement("article", { "data-card": "transit-risk-matrix", className: "surface-card p-3.5 space-y-2.5" },
                    React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2 min-w-0" },
                        React.createElement("div", null,
                            React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u0421\u0442\u0440\u0430\u0445\u043E\u0432\u043A\u0430 \u0441\u0440\u043E\u043A\u043E\u0432 \u043F\u0440\u0438 \u0437\u0430\u0434\u0435\u0440\u0436\u043A\u0430\u0445 \u0432 \u043F\u0443\u0442\u0438"),
                            React.createElement("p", { className: "text-sm text-secondary tabular-nums" },
                                "\u041A\u0430\u043D\u0430\u043B: ",
                                channelInfo.label,
                                ", \u0437\u0430\u0434\u0435\u0440\u0436\u043A\u0430 \u043C\u0430\u0440\u0448\u0440\u0443\u0442\u0430 +",
                                state.transitDelayDays,
                                " \u0441\u0443\u0442.")),
                        React.createElement("span", { className: "text-sm font-semibold text-secondary tabular-nums" },
                            "\u0420\u0438\u0441\u043A \u0434\u0435\u0444\u0438\u0446\u0438\u0442\u0430: ",
                            summary.stockoutRiskCount,
                            " \u043F\u043E\u0437., \u043F\u043B\u0435\u0447\u043E ",
                            summary.avgLeadDays.toFixed(1),
                            " \u0441\u0443\u0442.")),
                    React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                        React.createElement("div", { className: "flex items-center gap-1.5" },
                            React.createElement(Icons_1.ShieldClockIcon, { size: 15, className: "text-accent-primary" }),
                            React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u041C\u0430\u0442\u0440\u0438\u0446\u0430 \u043F\u043E\u043A\u0440\u044B\u0442\u0438\u044F \u043F\u043E\u043B\u043A\u0438 \u0438 \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u043E\u0433\u043E \u0437\u0430\u043F\u0430\u0441\u0430")),
                        React.createElement("span", { className: "text-xs text-muted" }, "\u041D\u0430\u0436\u043C\u0438\u0442\u0435 \u043D\u0430 \u0431\u0443\u0444\u0435\u0440 \u0434\u043B\u044F \u0441\u0434\u0432\u0438\u0433\u0430 \u0434\u043D\u0435\u0439")),
                    React.createElement("div", { className: "overflow-x-auto" },
                        React.createElement("table", { className: "ledger-table tabular-nums" },
                            React.createElement("thead", null,
                                React.createElement("tr", null,
                                    React.createElement("th", { scope: "col", className: "text-left" }, "\u041F\u043E\u0437\u0438\u0446\u0438\u044F"),
                                    React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u041F\u043E\u043B\u043A\u0430"),
                                    React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0412 \u043F\u0443\u0442\u0438"),
                                    React.createElement("th", { scope: "col", className: "text-left" }, "\u0421\u0442\u0430\u0442\u0443\u0441"),
                                    React.createElement("th", { scope: "col", className: "text-right tabular-nums" }, "\u0411\u0443\u0444\u0435\u0440"))),
                            React.createElement("tbody", null, state.items.map((item, idx) => {
                                const lead = (0, replenishmentEngine_1.computeEffectiveLeadDays)(item, state.transitDelayDays, state.backupChannel);
                                const shelfDays = Number((item.currentStock / Math.max(1, item.dailyDemand)).toFixed(1));
                                const target = (0, replenishmentEngine_1.computeRequiredTargetStock)(item, state.transitDelayDays, state.backupChannel);
                                const atRisk = (0, replenishmentEngine_1.isSkuAtStockoutRisk)(item, state.transitDelayDays, state.backupChannel);
                                const sup = (0, presets_1.getSupplier)(item.supplierId);
                                const isSelected = item.id === state.activeSkuId;
                                return (React.createElement("tr", { key: item.id, "data-entity-id": item.id, "data-selected": isSelected ? 'true' : undefined, tabIndex: 0, "aria-current": isSelected ? 'true' : undefined, style: { borderBottomWidth: 0 }, onClick: () => domainStore_1.inventoryStore.selectSku(item.id), onKeyDown: (e) => (0, a11yDialog_1.handleSelectableKeyDown)(e, () => domainStore_1.inventoryStore.selectSku(item.id)), className: `cursor-pointer ${!isSelected && idx % 2 === 1 ? 'surface-inset' : ''}` },
                                    React.createElement("td", { className: "text-left" },
                                        React.createElement("div", { className: "text-sm font-semibold text-primary" }, item.name),
                                        React.createElement("div", { className: "text-xs text-muted" },
                                            sup.name,
                                            ", \u0446\u0435\u043B\u044C ",
                                            target,
                                            " \u0448\u0442.")),
                                    React.createElement("td", { className: "text-right text-sm text-secondary whitespace-nowrap tabular-nums" },
                                        shelfDays.toFixed(1),
                                        " \u0441\u0443\u0442."),
                                    React.createElement("td", { className: "text-right text-sm font-medium text-primary whitespace-nowrap tabular-nums" },
                                        lead,
                                        " \u0441\u0443\u0442."),
                                    React.createElement("td", { className: "text-left whitespace-nowrap" },
                                        React.createElement("span", { className: `px-2 py-0.5 radius-control text-xs font-medium ${atRisk ? 'bg-status-danger' : 'bg-status-success'}` }, atRisk ? 'Дозаказ' : 'Покрыто')),
                                    React.createElement("td", { className: "text-right whitespace-nowrap tabular-nums", onClick: (e) => e.stopPropagation() },
                                        React.createElement("button", { type: "button", "aria-label": `${item.safetyDays} сут.: изменить страховой буфер ${item.name}`, onClick: () => domainStore_1.inventoryStore.cycleSafetyDays(item.id), className: "btn-row tabular-nums" },
                                            item.safetyDays,
                                            " \u0441\u0443\u0442."))));
                            })))),
                    React.createElement("div", { className: "surface-inset p-3 space-y-2 text-sm tabular-nums" },
                        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                            React.createElement("span", { className: "font-semibold text-primary" }, "\u0411\u0430\u043B\u0430\u043D\u0441 \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u043E\u0433\u043E \u0433\u043E\u0440\u0438\u0437\u043E\u043D\u0442\u0430 \u0420\u0426 \u041C\u043E\u0441\u043A\u0432\u0430"),
                            React.createElement("span", { className: "text-secondary" },
                                "\u0421\u0434\u0432\u0438\u0433 \u043A\u0430\u043D\u0430\u043B\u0430: ",
                                channelShiftLabel,
                                " \u0441\u0443\u0442., \u0442\u0430\u0440\u0438\u0444 +",
                                channelInfo.costSurchargePct,
                                "%")),
                        React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-3 gap-2.5" },
                            React.createElement("div", null,
                                React.createElement("div", { className: "text-secondary" }, "\u0417\u0430\u0449\u0438\u0449\u0435\u043D\u043E \u0431\u0443\u0444\u0435\u0440\u043E\u043C"),
                                React.createElement("div", { className: "font-semibold text-primary" },
                                    state.items.length - summary.stockoutRiskCount,
                                    " \u0438\u0437 ",
                                    state.items.length,
                                    " \u043F\u043E\u0437.")),
                            React.createElement("div", null,
                                React.createElement("div", { className: "text-secondary" }, "\u0421\u0440\u0435\u0434\u043D\u0435\u0435 \u043F\u043B\u0435\u0447\u043E \u043F\u0443\u043B\u0430"),
                                React.createElement("div", { className: "font-semibold text-primary" },
                                    summary.avgLeadDays.toFixed(1),
                                    " \u0441\u0443\u0442. (\u043E\u0442\u043A\u043B. +",
                                    state.transitDelayDays,
                                    " \u0441\u0443\u0442.)")),
                            React.createElement("div", null,
                                React.createElement("div", { className: "text-secondary" }, "\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430 \u043F\u0440\u0438\u0435\u043C\u043A\u0438"),
                                React.createElement("div", { className: "font-semibold text-primary" },
                                    summary.totalPallets.toFixed(1),
                                    " \u0438\u0437 ",
                                    summary.effectivePalletLimit,
                                    " \u043F\u0430\u043B\u043B."))),
                        React.createElement("div", { className: "text-secondary" },
                            "\u0420\u0435\u0433\u043B\u0430\u043C\u0435\u043D\u0442 \u0441\u043C\u0435\u043D\u044B: \u043F\u0440\u0438 \u0437\u0430\u0434\u0435\u0440\u0436\u043A\u0435 \u043E\u0442 +4 \u0441\u0443\u0442\u043E\u043A \u043F\u043E\u0437\u0438\u0446\u0438\u0438 \u0441 \u043F\u043E\u043B\u043A\u043E\u0439 \u043C\u0435\u043D\u0435\u0435 ",
                            activeLeadDays,
                            " \u0441\u0443\u0442. \u043F\u0435\u0440\u0435\u0432\u043E\u0434\u044F\u0442\u0441\u044F \u043D\u0430 \u0443\u0441\u043A\u043E\u0440\u0435\u043D\u043D\u044B\u0439 \u043A\u043E\u0440\u0438\u0434\u043E\u0440 \u0438\u043B\u0438 \u043F\u043E\u043B\u0443\u0447\u0430\u044E\u0442 +2 \u0441\u0443\u0442. \u0441\u0442\u0440\u0430\u0445\u043E\u0432\u043E\u0433\u043E \u0437\u0430\u043F\u0430\u0441\u0430.")))),
            React.createElement(TransitBufferInspectorColumn_1.TransitBufferInspectorColumn, { state: state, activeSku: activeSku })),
        React.createElement(CorridorSlaMatrixCard_1.CorridorSlaMatrixCard, { items: state.items, activeSkuId: state.activeSkuId, transitDelayDays: state.transitDelayDays, backupChannel: state.backupChannel, channelLabel: channelInfo.label, channelLeadDeltaDays: channelInfo.leadDeltaDays, channelCostSurchargePct: channelInfo.costSurchargePct })));
}

  };

  moduleFactories["screens/ScreenOrderExport"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenOrderExport = ScreenOrderExport;
const react_1 = require("react");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const orderExport_1 = require("../utils/orderExport");
const ErpDispatchLedgerCard_1 = require("../components/ErpDispatchLedgerCard");
const Icons_1 = require("../components/Icons");
const ARTIFACT_PRE_CLASS = 'surface-inset p-3 font-mono text-sm text-primary tabular-nums'; /* taste-skill-ignore */
function resolveDockStatus(summary) {
    if (summary.overLimitCount > 0) {
        return { text: 'Требует укладки', cls: 'text-status-danger' };
    }
    if (summary.stockoutRiskCount > 0) {
        return { text: `Габарит ОК, дефицит ${summary.stockoutRiskCount}`, cls: 'text-status-warning' };
    }
    return { text: 'Подтвержден РЦ', cls: 'text-status-success' };
}
function ScreenOrderExport({ state }) {
    const [copied, setCopied] = (0, react_1.useState)(false);
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const artifactText = state.exportFormat === 'csv' ? (0, orderExport_1.buildOrderCsv)(state) : (0, orderExport_1.buildProcurementMemo)(state);
    const budgetReserve = Number((state.constraints.maxBudgetKrub - summary.totalBudgetKrub).toFixed(1));
    const totalUnits = state.items.reduce((acc, it) => acc + it.orderQty, 0);
    const dockStatus = resolveDockStatus(summary);
    const handleCopyText = () => {
        if (typeof navigator !== 'undefined' &&
            navigator.clipboard &&
            typeof navigator.clipboard.writeText === 'function') {
            void navigator.clipboard.writeText(artifactText).catch(() => undefined);
        }
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
        domainStore_1.inventoryStore.recordArtifactExport(state.exportFormat === 'csv'
            ? 'Текст спецификации .csv скопирован'
            : 'Пояснительная записка скопирована');
    };
    const handleDownloadCsv = () => {
        (0, orderExport_1.triggerBrowserCsvDownload)('zapas-navigator-order.csv', (0, orderExport_1.buildOrderCsv)(state));
        domainStore_1.inventoryStore.recordArtifactExport('Выгружен файл спецификации .csv');
    };
    return (React.createElement("section", { "data-screen-view": "screen-order-export", "data-shell": "order-specification-export", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5" },
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch" },
            React.createElement("div", { className: "xl:col-span-7 min-w-0" },
                React.createElement("article", { "data-card": "order-artifact-preview", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-3" },
                    React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                        React.createElement("div", null,
                            React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u0421\u043F\u0435\u0446\u0438\u0444\u0438\u043A\u0430\u0446\u0438\u044F \u0437\u0430\u043A\u0430\u0437\u0430 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u0443 CSV \u0438 \u0437\u0430\u043F\u0438\u0441\u043A\u0430"),
                            React.createElement("p", { className: "text-sm text-secondary tabular-nums" },
                                state.waveLabel,
                                ", \u043F\u043E\u0437\u0438\u0446\u0438\u0439 ",
                                state.items.length,
                                ", \u043F\u0430\u043B\u043B\u0435\u0442 ",
                                summary.totalPallets.toFixed(1))),
                        React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0424\u043E\u0440\u043C\u0430\u0442 \u0432\u044B\u0433\u0440\u0443\u0437\u043A\u0438" },
                            React.createElement("button", { type: "button", "aria-pressed": state.exportFormat === 'csv', onClick: () => domainStore_1.inventoryStore.setExportFormat('csv'), className: "seg-btn" }, "\u0422\u0430\u0431\u043B\u0438\u0446\u0430 .csv"),
                            React.createElement("button", { type: "button", "aria-pressed": state.exportFormat === 'memo', onClick: () => domainStore_1.inventoryStore.setExportFormat('memo'), className: "seg-btn" }, "\u0417\u0430\u043F\u0438\u0441\u043A\u0430"))),
                    React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                        React.createElement("div", { className: "space-y-0.5 min-w-0" },
                            React.createElement("div", { className: "flex items-center gap-1.5" },
                                React.createElement(Icons_1.CsvExportIcon, { size: 15, className: "text-accent-primary" }),
                                React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0418\u0442\u043E\u0433\u043E\u0432\u044B\u0439 \u0434\u043E\u043A\u0443\u043C\u0435\u043D\u0442 \u0434\u043B\u044F \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u0430 \u0438 \u0441\u043A\u043B\u0430\u0434\u0430")),
                            React.createElement("div", { className: "text-sm text-secondary" }, state.exportNotice)),
                        React.createElement("button", { type: "button", "data-artifact-copy": "true", "data-export-copy": "true", onClick: handleCopyText, className: "btn-secondary radius-control shrink-0" }, copied ? 'Скопировано' : 'Скопировать текст')),
                    React.createElement("pre", { "data-artifact-preview": "true", "data-code-token": "true", style: {
                            margin: 0,
                            whiteSpace: 'pre-wrap',
                            overflowWrap: 'anywhere',
                            wordBreak: 'break-word',
                            maxWidth: '100%'
                        }, className: ARTIFACT_PRE_CLASS }, artifactText),
                    React.createElement("div", { className: "surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm tabular-nums" },
                        React.createElement("div", null,
                            React.createElement("span", { className: "text-secondary" }, "\u0428\u043B\u044E\u0437 WMS: "),
                            React.createElement("strong", { className: "text-primary" }, "\u0413\u043E\u0442\u043E\u0432, UTF-8")),
                        React.createElement("div", null,
                            React.createElement("span", { className: "text-secondary" }, "\u0412\u043E\u0440\u043E\u0442\u0430: "),
                            React.createElement("strong", { className: "text-primary" },
                                summary.totalPallets.toFixed(1),
                                " / ",
                                summary.effectivePalletLimit,
                                " \u043F\u0430\u043B\u043B.")),
                        React.createElement("div", null,
                            React.createElement("span", { className: "text-secondary" }, "\u0420\u0435\u0437\u0435\u0440\u0432: "),
                            React.createElement("strong", { className: budgetReserve >= 0 ? 'text-status-success' : 'text-status-danger' },
                                budgetReserve.toFixed(1),
                                " \u0442\u044B\u0441. \u20BD"))),
                    React.createElement("div", { className: "surface-inset px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs tabular-nums" },
                        React.createElement("span", { className: "text-secondary" }, "\u0420\u0430\u0437\u0434\u0435\u043B\u0438\u0442\u0435\u043B\u044C \u043A\u043E\u043B\u043E\u043D\u043E\u043A: \u0442\u043E\u0447\u043A\u0430 \u0441 \u0437\u0430\u043F\u044F\u0442\u043E\u0439, \u0447\u0438\u0441\u043B\u0430 \u0441 \u0442\u043E\u0447\u043A\u043E\u0439"),
                        React.createElement("span", { className: "font-semibold text-primary" }, "\u0421\u043E\u0432\u043C\u0435\u0441\u0442\u0438\u043C\u043E \u0441 1\u0421:ERP \u0438 WMS")),
                    React.createElement("button", { type: "button", "data-primary-action": "true", "data-artifact-download": "true", "data-export-download": "true", onClick: handleDownloadCsv, className: "btn-primary w-full radius-control" }, "\u0421\u043A\u0430\u0447\u0430\u0442\u044C \u0441\u043F\u0435\u0446\u0438\u0444\u0438\u043A\u0430\u0446\u0438\u044E .csv"))),
            React.createElement("div", { className: "xl:col-span-5 min-w-0" },
                React.createElement("article", { "data-card": "order-audit-log", "data-audit-log": "true", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-2.5" },
                    React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                        React.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0416\u0443\u0440\u043D\u0430\u043B \u0441\u043E\u0433\u043B\u0430\u0441\u043E\u0432\u0430\u043D\u0438\u044F \u0438 \u043F\u0440\u0430\u0432\u043E\u043A"),
                        React.createElement("button", { type: "button", disabled: !domainStore_1.inventoryStore.canUndo(), onClick: () => domainStore_1.inventoryStore.undo(), className: "btn-ghost radius-control" },
                            React.createElement(Icons_1.UndoIcon, { size: 13 }),
                            React.createElement("span", null, "\u041E\u0442\u043C\u0435\u043D\u0438\u0442\u044C \u0448\u0430\u0433"))),
                    React.createElement("div", { className: "space-y-1.5 tabular-nums" }, state.history.slice(0, 4).map((entry) => (React.createElement("div", { key: entry.id, className: "surface-inset px-2.5 py-2 space-y-0.5" },
                        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-sm font-semibold text-primary" }, entry.summary),
                            React.createElement("span", { className: "text-xs text-muted tabular-nums" }, entry.timeLabel)),
                        React.createElement("div", { className: "text-sm text-secondary" }, entry.detail))))),
                    React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
                        React.createElement("div", { className: "font-semibold text-primary" }, "\u041A\u043E\u043D\u0442\u0440\u043E\u043B\u044C \u043E\u0442\u043F\u0440\u0430\u0432\u043A\u0438 \u0432 ERP \u0438 \u044D\u0444\u0444\u0435\u043A\u0442 \u0441\u043C\u0435\u043D\u044B"),
                        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0421\u0442\u0430\u0442\u0443\u0441 \u0433\u0430\u0431\u0430\u0440\u0438\u0442\u043D\u043E\u0433\u043E \u0434\u043E\u043F\u0443\u0441\u043A\u0430"),
                            React.createElement("span", { className: `font-semibold ${dockStatus.cls}` }, dockStatus.text)),
                        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0418\u0442\u043E\u0433\u043E\u0432\u0430\u044F \u0441\u0443\u043C\u043C\u0430 \u0437\u0430\u044F\u0432\u043A\u0438"),
                            React.createElement("span", { className: "font-semibold text-primary" },
                                summary.totalBudgetKrub.toFixed(1),
                                " \u0442\u044B\u0441. \u20BD")),
                        React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0421\u0443\u043C\u043C\u0430\u0440\u043D\u044B\u0439 \u043E\u0431\u044A\u0435\u043C \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438"),
                            React.createElement("span", { className: "font-semibold text-primary" },
                                totalUnits,
                                " \u0448\u0442., ",
                                summary.totalWeightKg,
                                " \u043A\u0433")))))),
        React.createElement(ErpDispatchLedgerCard_1.ErpDispatchLedgerCard, { items: state.items, activeSkuId: state.activeSkuId, transitDelayDays: state.transitDelayDays, backupChannel: state.backupChannel, avgReliabilityPct: summary.avgReliabilityPct })));
}

  };

  moduleFactories["screens/ScreenReplenishmentNotebook"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenReplenishmentNotebook = ScreenReplenishmentNotebook;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const useAnimatedNumber_1 = require("../hooks/useAnimatedNumber");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const CapacityHorizonChart_1 = require("../components/CapacityHorizonChart");
const ReplenishmentInspectorColumn_1 = require("../components/ReplenishmentInspectorColumn");
const ReplenishmentLedgerTable_1 = require("../components/ReplenishmentLedgerTable");
const Icons_1 = require("../components/Icons");
function ScreenReplenishmentNotebook({ state, onOpenAddModal }) {
    const [triageFilter, setTriageFilter] = (0, react_1.useState)('all');
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const animatedPallets = (0, useAnimatedNumber_1.useAnimatedNumber)(summary.totalPallets, 160);
    const animatedBudget = (0, useAnimatedNumber_1.useAnimatedNumber)(summary.totalBudgetKrub, 160);
    const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
    const activeRecommendedQty = (0, replenishmentEngine_1.computeRecommendedOrderQty)(activeSku, state.transitDelayDays, state.backupChannel);
    const waveFin = (0, replenishmentEngine_1.computeWaveFinancialSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    return (React.createElement("section", { "data-screen-view": "screen-replenishment-notebook", "data-paradigm": "editorial-notebook", "data-signature": "swiss-replenishment-solver-ledger", "data-shell": "replenishment-ledger", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3 space-y-3" },
        React.createElement("article", { "data-card": "constraint-solver-strip", "data-constraint-solver": "warehouse-capacity", className: "surface-card p-3 space-y-2" },
            React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 min-w-0" },
                React.createElement("div", { className: "min-w-0" },
                    React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u0420\u0430\u0441\u0447\u0435\u0442 \u043F\u0430\u0440\u0442\u0438\u0439 \u0434\u043E\u0437\u0430\u043A\u0430\u0437\u0430 \u0438 \u0435\u043C\u043A\u043E\u0441\u0442\u0438 \u0441\u043A\u043B\u0430\u0434\u0430"),
                    React.createElement("p", { className: "text-sm text-secondary" }, state.waveLabel)),
                React.createElement("div", { className: "flex flex-wrap items-center gap-1.5 min-w-0" },
                    React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u0421\u0446\u0435\u043D\u0430\u0440\u0438\u0438 \u0441\u043D\u0430\u0431\u0436\u0435\u043D\u0438\u044F" }, presets_1.SCENARIO_PRESETS.map((preset) => (React.createElement("button", { key: preset.id, type: "button", "data-scenario-preset": preset.id, "aria-pressed": state.activePresetId === preset.id, onClick: () => domainStore_1.inventoryStore.loadPreset(preset.id), className: "seg-btn" }, preset.label)))),
                    React.createElement("button", { type: "button", "data-open-create-modal": "true", "data-create-trigger": "true", onClick: onOpenAddModal, className: "btn-secondary radius-control shrink-0" },
                        React.createElement(Icons_1.PlusIcon, { size: 13 }),
                        React.createElement("span", null, "\u041F\u043E\u0437\u0438\u0446\u0438\u044F")),
                    React.createElement("button", { type: "button", "data-export-artifact": "true", onClick: () => domainStore_1.inventoryStore.setScreen('screen-order-export'), className: "btn-ghost radius-control shrink-0" },
                        React.createElement(Icons_1.CsvExportIcon, { size: 13 }),
                        React.createElement("span", null, "CSV")))),
            React.createElement("div", { className: "surface-inset px-3 py-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 items-center tabular-nums" },
                React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-1.5 min-w-0" },
                    React.createElement("div", null,
                        React.createElement("div", { className: "text-sm text-secondary" }, "\u041F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442\u0430"),
                        React.createElement("div", { "data-hero-metric": "true", className: "hero-metric" },
                            animatedPallets.toFixed(1),
                            " \u043F\u0430\u043B\u043B.")),
                    React.createElement("span", { className: "text-sm text-secondary font-medium" },
                        "\u043B\u0438\u043C\u0438\u0442 ",
                        summary.effectivePalletLimit,
                        React.createElement("span", { className: "text-muted" },
                            ", ",
                            waveFin.discreteRampSlots,
                            " \u0441\u043B\u043E\u0442."))),
                React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-1.5 min-w-0" },
                    React.createElement("div", null,
                        React.createElement("div", { className: "text-sm text-secondary" }, "\u0411\u044E\u0434\u0436\u0435\u0442 \u0437\u0430\u044F\u0432\u043A\u0438"),
                        React.createElement("div", { className: "text-base font-bold text-primary" },
                            animatedBudget.toFixed(1),
                            " \u0442\u044B\u0441. \u20BD")),
                    React.createElement("span", { className: "text-sm text-secondary" },
                        "\u0438\u0437 ",
                        state.constraints.maxBudgetKrub,
                        " \u0442\u044B\u0441.")),
                React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-1.5 min-w-0" },
                    React.createElement("div", null,
                        React.createElement("div", { className: "text-sm text-secondary" }, "\u041C\u0430\u0441\u0441\u0430 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438"),
                        React.createElement("div", { className: "text-base font-bold text-primary" },
                            summary.totalWeightKg,
                            " \u043A\u0433")),
                    React.createElement("span", { className: "text-sm text-secondary" },
                        "\u0440\u0430\u043C\u043F\u0430 ",
                        state.constraints.maxWeightKg,
                        " \u043A\u0433")),
                React.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-1.5 min-w-0" },
                    React.createElement("div", null,
                        React.createElement("div", { className: "text-sm text-secondary" }, "\u0426\u0435\u043D\u0430 \u0431\u0435\u0437\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044F"),
                        React.createElement("div", { "data-cost-of-inaction-total": "true", className: `text-base font-bold ${waveFin.totalCostOfInactionKrub > 0 ? 'text-status-danger' : 'text-status-success'}` }, waveFin.totalCostOfInactionKrub > 0
                            ? `Риск ${Math.round(waveFin.totalCostOfInactionKrub)}к ₽`
                            : 'Риск 0 ₽, защищено')),
                    React.createElement("span", { className: "text-sm text-secondary" },
                        "SLA ",
                        summary.avgReliabilityPct.toFixed(1),
                        "%, ",
                        summary.avgLeadDays.toFixed(1),
                        "\u0434"))),
            React.createElement(CapacityHorizonChart_1.CapacityHorizonChart, { state: state, onSelectSku: (id) => domainStore_1.inventoryStore.selectChartSku(id) })),
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-start" },
            React.createElement("div", { className: "xl:col-span-8 min-w-0" },
                React.createElement(ReplenishmentLedgerTable_1.ReplenishmentLedgerTable, { state: state, summary: summary, activeSku: activeSku, activeRecommendedQty: activeRecommendedQty, triageFilter: triageFilter, onChangeTriageFilter: setTriageFilter })),
            React.createElement(ReplenishmentInspectorColumn_1.ReplenishmentInspectorColumn, { state: state, activeSku: activeSku, activeRecommendedQty: activeRecommendedQty }))));
}

  };

  moduleFactories["screens/ScreenSupplierChoice"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenSupplierChoice = ScreenSupplierChoice;
const presets_1 = require("../data/presets");
const supplierContracts_1 = require("../data/supplierContracts");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const SupplierContractMatrixCard_1 = require("../components/SupplierContractMatrixCard");
const SupplierReliabilityChartCard_1 = require("../components/SupplierReliabilityChartCard");
function formatSignedValue(value, decimals) {
    const formatted = value.toFixed(decimals);
    return value > 0 ? `+${formatted}` : formatted;
}
function formatSignedInt(value) {
    return value > 0 ? `+${value}` : String(value);
}
function ScreenSupplierChoice({ state }) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
    const selectedSupplier = (0, presets_1.getSupplier)(state.selectedSupplierId);
    const selectedContract = supplierContracts_1.SUPPLIER_CONTRACT_TERMS[selectedSupplier.id] || supplierContracts_1.SUPPLIER_CONTRACT_TERMS['balt-komplekt'];
    const currentLineTotal = (0, replenishmentEngine_1.computeItemCostKrub)(activeSku, state.backupChannel);
    const candidateLineTotal = (0, replenishmentEngine_1.computeItemCostKrub)({ ...activeSku, supplierId: selectedSupplier.id }, state.backupChannel);
    const lineDelta = Number((candidateLineTotal - currentLineTotal).toFixed(1));
    const negImpact = (0, replenishmentEngine_1.computeSupplierNegotiationImpact)(activeSku, selectedSupplier.id, state.transitDelayDays, state.backupChannel);
    return (React.createElement("section", { "data-screen-view": "screen-supplier-choice", "data-shell": "supplier-comparison-chart", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5" },
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch" },
            React.createElement("div", { className: "xl:col-span-7 min-w-0" },
                React.createElement(SupplierReliabilityChartCard_1.SupplierReliabilityChartCard, { activeSku: activeSku, selectedSupplier: selectedSupplier, selectedSupplierId: state.selectedSupplierId, summary: summary })),
            React.createElement("div", { className: "xl:col-span-5 min-w-0" },
                React.createElement("article", { "data-card": "supplier-terms-comparison", className: "surface-card p-3.5 h-full flex flex-col justify-between gap-2.5" },
                    React.createElement("div", { className: "space-y-1" },
                        React.createElement("div", { className: "text-xs text-muted" }, "\u041A\u0430\u0440\u0442\u043E\u0447\u043A\u0430 \u043F\u043B\u043E\u0449\u0430\u0434\u043A\u0438 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438 \u0438 \u0440\u0435\u0433\u043B\u0430\u043C\u0435\u043D\u0442 SLA"),
                        React.createElement("h2", { className: "text-base font-semibold text-primary" },
                            selectedSupplier.name,
                            " \u2013 ",
                            selectedSupplier.city),
                        React.createElement("p", { className: "text-sm text-secondary" }, selectedSupplier.termsNote)),
                    React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041F\u0443\u043D\u043A\u0442\u0443\u0430\u043B\u044C\u043D\u043E\u0441\u0442\u044C OTIF"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" },
                                selectedSupplier.reliabilityPct.toFixed(1),
                                "% \u0432 \u0441\u0440\u043E\u043A, ",
                                selectedContract.leadVariance)),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041F\u043B\u0435\u0447\u043E \u0438 \u043C\u0438\u043D. \u043F\u0430\u0440\u0442\u0438\u044F MOQ"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" },
                                selectedSupplier.leadDays,
                                " \u0441\u0443\u0442., \u043E\u0442 ",
                                selectedSupplier.minBatchQty,
                                " \u0448\u0442.")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0411\u0430\u0437\u0438\u0441 \u0438 \u0442\u0430\u0440\u043D\u044B\u0439 \u043D\u043E\u0440\u043C\u0430\u0442\u0438\u0432"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" }, selectedContract.incoterms)),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041E\u0442\u0441\u0440\u043E\u0447\u043A\u0430 \u0438 \u0448\u0442\u0440\u0430\u0444 \u0437\u0430 \u043F\u0440\u043E\u0441\u0440\u043E\u0447\u043A\u0443"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" },
                                selectedContract.deferralDays,
                                " \u0441\u0443\u0442., \u043F\u0435\u043D\u0438 ",
                                selectedContract.slaPenaltyPct,
                                "/\u0434\u043D.")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u041A\u0440\u0430\u0442\u043D\u043E\u0441\u0442\u044C \u043F\u0430\u043B\u043B\u0435\u0442\u043D\u043E\u0439 \u043E\u0442\u0433\u0440\u0443\u0437\u043A\u0438"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" }, selectedContract.packaging))),
                    React.createElement("div", { className: "surface-inset p-2.5 space-y-1.5 text-sm tabular-nums" },
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" },
                                "\u0421\u0442\u0440\u043E\u043A\u0430 \u00AB",
                                activeSku.name,
                                "\u00BB"),
                            React.createElement("span", { className: "font-semibold text-primary text-right whitespace-nowrap" },
                                currentLineTotal.toFixed(1),
                                " \u2192 ",
                                candidateLineTotal.toFixed(1),
                                " \u0442\u044B\u0441. \u20BD")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2 text-xs" },
                            React.createElement("span", { className: "text-muted" }, "\u0420\u0430\u0437\u043D\u0438\u0446\u0430 \u043F\u043E \u0442\u0435\u043A\u0443\u0449\u0435\u0439 \u043F\u0430\u0440\u0442\u0438\u0438"),
                            React.createElement("span", { className: lineDelta <= 0 ? 'font-semibold text-status-success text-right' : 'font-semibold text-status-warning text-right' },
                                formatSignedValue(lineDelta, 1),
                                " \u0442\u044B\u0441. \u20BD")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2 text-xs" },
                            React.createElement("span", { className: "text-muted" }, "\u0412\u0445\u043E\u0434\u043D\u043E\u0439 \u043A\u043E\u043D\u0442\u0440\u043E\u043B\u044C \u041E\u0422\u041A \u043D\u0430 \u0440\u0430\u043C\u043F\u0435"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" }, "\u0412\u044B\u0431\u043E\u0440\u043A\u0430 10%, \u0448\u0442\u0440\u0438\u0445\u043A\u043E\u0434 SSCC"))),
                    React.createElement("div", { "data-supplier-negotiation-impact": "true", className: "surface-inset px-3 py-2 space-y-1 text-xs tabular-nums" },
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0417\u0430\u043A\u0443\u043F\u043A\u0430, \u03C3-SS \u0438 \u0440\u0438\u0441\u043A"),
                            React.createElement("span", { className: "font-semibold text-primary text-right" },
                                formatSignedValue(negImpact.lineCostDeltaKrub, 1),
                                "\u043A, \u03C3",
                                ' ',
                                formatSignedInt(negImpact.sigmaBufferDeltaUnits),
                                " \u0448\u0442., \u0440\u0438\u0441\u043A",
                                ' ',
                                formatSignedValue(negImpact.riskDeltaKrub, 1),
                                "\u043A")),
                        React.createElement("div", { className: "flex items-center justify-between gap-2" },
                            React.createElement("span", { className: "text-secondary" }, "\u0412\u0435\u0440\u0434\u0438\u043A\u0442 TCO"),
                            React.createElement("span", { className: negImpact.netImpactKrub >= 0
                                    ? 'font-semibold text-status-success text-right'
                                    : 'font-semibold text-status-warning text-right' }, negImpact.verdict))),
                    React.createElement("div", { className: "flex flex-col gap-2" },
                        React.createElement("button", { type: "button", disabled: activeSku.supplierId === selectedSupplier.id, onClick: () => domainStore_1.inventoryStore.updateSkuSupplier(activeSku.id, selectedSupplier.id), className: "btn-secondary w-full radius-control" }, activeSku.supplierId === selectedSupplier.id
                            ? 'Закреплен за активной позицией'
                            : `Закрепить ${selectedSupplier.name} за позицией`),
                        React.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => domainStore_1.inventoryStore.assignOptimalSuppliers(), className: "btn-primary w-full radius-control" }, "\u041D\u0430\u0437\u043D\u0430\u0447\u0438\u0442\u044C \u043B\u0443\u0447\u0448\u0438\u0445 \u043F\u043E\u0441\u0442\u0430\u0432\u0449\u0438\u043A\u043E\u0432"))))),
        React.createElement(SupplierContractMatrixCard_1.SupplierContractMatrixCard, { items: state.items, backupChannel: state.backupChannel, selectedSupplierId: state.selectedSupplierId, selectedSupplierName: selectedSupplier.name })));
}

  };

  moduleFactories["screens/ScreenSupplyMap"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenSupplyMap = ScreenSupplyMap;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const flowNetwork_1 = require("../data/flowNetwork");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const useAnimatedNumber_1 = require("../hooks/useAnimatedNumber");
const SupplyFlowMap_1 = require("../components/SupplyFlowMap");
const FlowCorridorInspector_1 = require("../components/FlowCorridorInspector");
const SupplyCorridorLedger_1 = require("../components/SupplyCorridorLedger");
const LENS_OPTIONS = [
    { id: 'all', label: 'Все потоки' },
    { id: 'inbound', label: 'Вход в РЦ' },
    { id: 'outbound', label: 'Клиентам' },
    { id: 'at_risk', label: 'Под риском' },
    { id: 'sku_peg', label: 'Трасса позиции' }
];
const METRIC_OPTIONS = [
    { id: 'pallets', label: 'Паллеты' },
    { id: 'weight', label: 'Тоннаж' },
    { id: 'budget', label: 'Бюджет' }
];
const REGION_OPTIONS = [
    { id: 'all', label: 'Вся сеть' },
    { id: 'west_center', label: 'Центр и СЗ' },
    { id: 'volga_ural', label: 'Волга и Урал' }
];
function ScreenSupplyMap({ state }) {
    const [metric, setMetric] = (0, react_1.useState)('pallets');
    const [region, setRegion] = (0, react_1.useState)('all');
    const lens = state.mapLens || 'all';
    const activeSku = state.items.find((it) => it.id === state.activeSkuId) || state.items[0];
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const net = (0, flowNetwork_1.computeSupplyNetwork)(state);
    const selectedNodeId = state.selectedMapNodeId || 'dc-moscow';
    const animInboundPallets = (0, useAnimatedNumber_1.useAnimatedNumber)(net.inboundPallets, 220);
    const animOutboundPallets = (0, useAnimatedNumber_1.useAnimatedNumber)(net.outboundPallets, 220);
    const animOtifPct = (0, useAnimatedNumber_1.useAnimatedNumber)(net.otifNetworkPct, 220);
    const selectedInbound = net.inbound.find((f) => f.id === selectedNodeId);
    const selectedOutbound = net.outbound.find((o) => o.id === selectedNodeId);
    const channelInfo = presets_1.BACKUP_CHANNELS[state.backupChannel];
    const dependentCustomers = selectedInbound
        ? net.outbound.filter((o) => o.peggedSuppliers.includes(selectedInbound.id))
        : [];
    return (React.createElement("section", { "data-screen-view": "screen-supply-map", "data-shell": "supply-flow-map", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3 space-y-3" },
        React.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch" },
            React.createElement("div", { className: "xl:col-span-8 min-w-0" },
                React.createElement("article", { "data-card": "swiss-supply-flow-map", className: "surface-card p-3.5 h-full flex flex-col gap-2" },
                    React.createElement("div", { className: "flex flex-wrap items-start justify-between gap-2 min-w-0" },
                        React.createElement("div", null,
                            React.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u041A\u0430\u0440\u0442\u0430 \u0432\u0445\u043E\u0434\u044F\u0449\u0438\u0445 \u043F\u043E\u0441\u0442\u0430\u0432\u043E\u043A \u0438 \u043A\u043B\u0438\u0435\u043D\u0442\u0441\u043A\u0438\u0445 \u043E\u0442\u0433\u0440\u0443\u0437\u043E\u043A"),
                            React.createElement("p", { className: "text-sm text-secondary tabular-nums" },
                                "\u041A\u0430\u043D\u0430\u043B: ",
                                channelInfo.label,
                                ", \u0441\u0434\u0432\u0438\u0433 +",
                                state.transitDelayDays,
                                " \u0441\u0443\u0442.")),
                        React.createElement("div", { className: "flex flex-wrap items-center gap-1.5" },
                            React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u041C\u0435\u0442\u0440\u0438\u043A\u0430 \u0442\u043E\u043B\u0449\u0438\u043D\u044B \u043F\u043E\u0442\u043E\u043A\u043E\u0432" }, METRIC_OPTIONS.map((m) => (React.createElement("button", { key: m.id, type: "button", "aria-pressed": metric === m.id, onClick: () => setMetric(m.id), className: "seg-btn" }, m.label)))),
                            React.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u041C\u0430\u0441\u0448\u0442\u0430\u0431 \u0440\u0435\u0433\u0438\u043E\u043D\u0430 \u043A\u0430\u0440\u0442\u044B" }, REGION_OPTIONS.map((r) => (React.createElement("button", { key: r.id, type: "button", "aria-pressed": region === r.id, onClick: () => setRegion(r.id), className: "seg-btn" }, r.label)))))),
                    React.createElement("div", { className: "surface-inset px-3 py-2 grid grid-cols-2 sm:grid-cols-4 gap-3 items-end tabular-nums" },
                        React.createElement("div", null,
                            React.createElement("div", { className: "text-xs text-secondary" }, "\u0412\u0445\u043E\u0434 \u0432 \u0420\u0426"),
                            React.createElement("div", { "data-hero-metric": "true", className: "hero-metric font-semibold text-primary tabular-nums" },
                                animInboundPallets.toFixed(1),
                                " \u043F\u0430\u043B\u043B.")),
                        React.createElement("div", null,
                            React.createElement("div", { className: "text-xs text-secondary" }, "\u0412\u044B\u0432\u043E\u0437 \u043A\u043B\u0438\u0435\u043D\u0442\u0430\u043C"),
                            React.createElement("div", { className: "text-base font-semibold text-primary tabular-nums" },
                                animOutboundPallets.toFixed(1),
                                " \u043F\u0430\u043B\u043B.")),
                        React.createElement("div", null,
                            React.createElement("div", { className: "text-xs text-secondary" }, "\u041D\u0430\u0434\u0435\u0436\u043D\u043E\u0441\u0442\u044C \u0441\u0435\u0442\u0438"),
                            React.createElement("div", { className: "text-base font-semibold text-primary tabular-nums" },
                                animOtifPct.toFixed(1),
                                "% OTIF")),
                        React.createElement("div", null,
                            React.createElement("div", { className: "text-xs text-secondary" }, "\u0423\u0437\u043A\u0438\u0435 \u043F\u043B\u0435\u0447\u0438"),
                            React.createElement("div", { className: `text-base font-semibold tabular-nums ${net.riskCorridorsCount > 0 ? 'text-status-danger' : 'text-status-success'}` },
                                net.riskCorridorsCount,
                                " \u043D\u0430\u043F\u0440."))),
                    React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2" },
                        React.createElement("div", { className: "seg-group flex-wrap", role: "group", "aria-label": "\u041B\u0438\u043D\u0437\u0430 \u043F\u043E\u0442\u043E\u043A\u043E\u0432 \u043F\u043E\u0441\u0442\u0430\u0432\u043E\u043A" }, LENS_OPTIONS.map((opt) => (React.createElement("button", { key: opt.id, type: "button", "data-map-lens": opt.id, "aria-pressed": lens === opt.id, onClick: () => domainStore_1.inventoryStore.setMapLens(opt.id), className: "seg-btn" }, opt.label)))),
                        React.createElement("div", { className: "flex items-center gap-1.5 min-w-0", style: { flex: '1 1 256px' } },
                            React.createElement("label", { htmlFor: "map-peg-sku-select", className: "hidden sm:inline text-xs text-muted shrink-0" }, "SKU:"),
                            React.createElement("select", { id: "map-peg-sku-select", "aria-label": "\u041F\u043E\u0437\u0438\u0446\u0438\u044F \u0434\u043B\u044F \u0442\u0440\u0430\u0441\u0441\u0438\u0440\u043E\u0432\u043A\u0438 \u043F\u043E\u0442\u043E\u043A\u043E\u0432", value: activeSku.id, onChange: (e) => {
                                    domainStore_1.inventoryStore.selectSku(e.target.value);
                                    domainStore_1.inventoryStore.setMapLens('sku_peg');
                                }, className: "w-full field-compact" }, state.items.map((it) => (React.createElement("option", { key: it.id, value: it.id }, it.name.length > 22 ? `${it.name.slice(0, 21).trimEnd()}…` : it.name)))))),
                    React.createElement(SupplyFlowMap_1.SupplyFlowMap, { inbound: net.inbound, outbound: net.outbound, selectedNodeId: selectedNodeId, lens: lens, metric: metric, region: region, effectivePalletLimit: summary.effectivePalletLimit, totalPallets: summary.totalPallets, peggedSku: activeSku, onSelectNode: (id) => domainStore_1.inventoryStore.selectMapNode(id) }))),
            React.createElement("div", { className: "xl:col-span-4 min-w-0" },
                React.createElement(FlowCorridorInspector_1.FlowCorridorInspector, { state: state, summary: summary, lens: lens, activeSku: activeSku, selectedNodeId: selectedNodeId, selectedInbound: selectedInbound, selectedOutbound: selectedOutbound, outbound: net.outbound, dependentCustomers: dependentCustomers, outboundPallets: net.outboundPallets, outboundValueKrub: net.outboundValueKrub }))),
        React.createElement(SupplyCorridorLedger_1.SupplyCorridorLedger, { inbound: net.inbound, outbound: net.outbound, selectedNodeId: selectedNodeId })));
}

  };

  moduleFactories["screens/ScreenWarehouseLimits"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ScreenWarehouseLimits = ScreenWarehouseLimits;
const react_1 = __importStar(require("react"));
const presets_1 = require("../data/presets");
const domainStore_1 = require("../store/domainStore");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
const Icons_1 = require("../components/Icons");
const WarehouseGateScheduleCard_1 = require("../components/WarehouseGateScheduleCard");
const WarehousePalletShareCard_1 = require("../components/WarehousePalletShareCard");
const PALLET_CEILINGS = [34, 46, 56];
function ScreenWarehouseLimits({ state }) {
    const [draftName, setDraftName] = (0, react_1.useState)('');
    const [formError, setFormError] = (0, react_1.useState)('');
    const [draftQtyStr, setDraftQtyStr] = (0, react_1.useState)('40');
    const [draftSupplier, setDraftSupplier] = (0, react_1.useState)('balt-komplekt');
    const [draftPriority, setDraftPriority] = (0, react_1.useState)('standard');
    const inputRef = (0, react_1.useRef)(null);
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const freeReserve = Number((summary.effectivePalletLimit - summary.totalPallets).toFixed(1));
    const waveFin = (0, replenishmentEngine_1.computeWaveFinancialSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const handleComposeSubmit = (e) => {
        e.preventDefault();
        const clean = draftName.trim();
        if (!clean) {
            setFormError('Укажите наименование узла или расходника');
            inputRef.current?.focus();
            return;
        }
        setFormError('');
        const parsedQty = Number(String(draftQtyStr).replace(',', '.'));
        domainStore_1.inventoryStore.addCustomSku({
            name: clean,
            category: 'Складской заказ',
            orderQty: Number.isFinite(parsedQty) && parsedQty > 0 ? parsedQty : 40,
            supplierId: draftSupplier,
            priority: draftPriority
        });
        setDraftName('');
    };
    return (react_1.default.createElement("section", { "data-screen-view": "screen-warehouse-limits", "data-shell": "warehouse-capacity-composer", "data-active-entity": state.activeSkuId, className: "app-rail-stage px-3 sm:px-4 lg:px-5 py-3.5 space-y-3.5" },
        react_1.default.createElement("div", { className: "grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch" },
            react_1.default.createElement("div", { className: "xl:col-span-6 flex flex-col justify-between gap-2 min-w-0" },
                react_1.default.createElement("article", { "data-card": "warehouse-ceiling-controls", className: "surface-card p-2.5 space-y-2" },
                    react_1.default.createElement("div", { className: "flex flex-wrap items-baseline justify-between gap-2 min-w-0" },
                        react_1.default.createElement("div", null,
                            react_1.default.createElement("h1", { className: "text-lg font-semibold tracking-tight text-primary" }, "\u041E\u0433\u0440\u0430\u043D\u0438\u0447\u0435\u043D\u0438\u044F \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442, \u043C\u0430\u0441\u0441\u044B \u0438 \u0431\u044E\u0434\u0436\u0435\u0442\u0430"),
                            react_1.default.createElement("p", { className: "text-sm text-secondary tabular-nums" },
                                "\u0414\u043E\u0441\u0442\u0443\u043F\u043D\u043E ",
                                summary.effectivePalletLimit,
                                " \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442, \u0440\u0430\u043C\u043F\u0430 ",
                                state.constraints.maxWeightKg,
                                " \u043A\u0433")),
                        react_1.default.createElement("span", { className: `text-sm font-semibold tabular-nums ${freeReserve >= 0 ? 'text-status-success' : 'text-status-danger'}` },
                            "\u041E\u0441\u0442\u0430\u0442\u043E\u043A: ",
                            freeReserve.toFixed(1),
                            " \u043F\u0430\u043B\u043B.")),
                    react_1.default.createElement("div", { className: "flex items-center justify-between gap-2 flex-wrap" },
                        react_1.default.createElement("div", { className: "flex items-center gap-1.5" },
                            react_1.default.createElement(Icons_1.WarehouseBoxIcon, { size: 15, className: "text-accent-primary" }),
                            react_1.default.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u041D\u043E\u0440\u043C\u0430\u0442\u0438\u0432\u044B \u0437\u043E\u043D\u044B \u043F\u0440\u0438\u0435\u043C\u043A\u0438 \u0438 \u043F\u043E\u0442\u043E\u043B\u043E\u043A \u0431\u044E\u0434\u0436\u0435\u0442\u0430")),
                        react_1.default.createElement("div", { className: "seg-group", role: "group", "aria-label": "\u041F\u043E\u0442\u043E\u043B\u043E\u043A \u043F\u0430\u043B\u043B\u0435\u0442\u043E\u043C\u0435\u0441\u0442" }, PALLET_CEILINGS.map((cap) => (react_1.default.createElement("button", { key: cap, type: "button", "aria-pressed": state.constraints.maxPallets === cap, onClick: () => domainStore_1.inventoryStore.updateConstraints({ maxPallets: cap }), className: "seg-btn tabular-nums" },
                            cap,
                            " \u043F\u0430\u043B\u043B."))))),
                    react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" },
                        react_1.default.createElement("div", { className: "flex flex-col justify-end gap-1 min-w-0" },
                            react_1.default.createElement("label", { htmlFor: "limit-weight-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u0440\u0435\u0434\u0435\u043B\u044C\u043D\u0430\u044F \u043C\u0430\u0441\u0441\u0430 \u043D\u0430 \u0440\u0430\u043C\u043F\u0443"),
                            react_1.default.createElement("select", { id: "limit-weight-select", value: state.constraints.maxWeightKg, onChange: (e) => domainStore_1.inventoryStore.updateConstraints({ maxWeightKg: Number(e.target.value) }), className: "w-full field-compact tabular-nums" },
                                react_1.default.createElement("option", { value: 9600 }, "9 600 \u043A\u0433, \u043C\u0430\u043B\u0430\u044F"),
                                react_1.default.createElement("option", { value: 11800 }, "11 800 \u043A\u0433, \u0448\u0442\u0430\u0442\u043D\u0430\u044F"),
                                react_1.default.createElement("option", { value: 12400 }, "12 400 \u043A\u0433, 2 \u0431\u0440\u0438\u0433\u0430\u0434\u044B"),
                                react_1.default.createElement("option", { value: 14500 }, "14 500 \u043A\u0433, \u0440\u0430\u0441\u0448\u0438\u0440."))),
                        react_1.default.createElement("div", { className: "flex flex-col justify-end gap-1 min-w-0" },
                            react_1.default.createElement("label", { htmlFor: "limit-budget-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u043E\u0442\u043E\u043B\u043E\u043A \u0431\u044E\u0434\u0436\u0435\u0442\u0430 \u0432\u043E\u043B\u043D\u044B"),
                            react_1.default.createElement("select", { id: "limit-budget-select", value: state.constraints.maxBudgetKrub, onChange: (e) => domainStore_1.inventoryStore.updateConstraints({ maxBudgetKrub: Number(e.target.value) }), className: "w-full field-compact tabular-nums" },
                                react_1.default.createElement("option", { value: 3150 }, "3 150 \u0442\u044B\u0441. \u20BD, \u0441\u0442\u0440\u043E\u0433\u0438\u0439"),
                                react_1.default.createElement("option", { value: 3650 }, "3 650 \u0442\u044B\u0441. \u20BD, \u0431\u0430\u0437\u043E\u0432\u044B\u0439"),
                                react_1.default.createElement("option", { value: 3900 }, "3 900 \u0442\u044B\u0441. \u20BD, \u0440\u0435\u0437\u0435\u0440\u0432"),
                                react_1.default.createElement("option", { value: 4400 }, "4 400 \u0442\u044B\u0441. \u20BD, \u043F\u0438\u043A\u043E\u0432\u044B\u0439")))),
                    react_1.default.createElement("button", { type: "button", "data-primary-action": "true", onClick: () => domainStore_1.inventoryStore.applyWarehouseLimitsAndBalance(), className: "btn-primary w-full radius-control" }, "\u041F\u0440\u0438\u043C\u0435\u043D\u0438\u0442\u044C \u0433\u0430\u0431\u0430\u0440\u0438\u0442\u043D\u044B\u0435 \u043B\u0438\u043C\u0438\u0442\u044B")),
                react_1.default.createElement("article", { "data-card": "custom-sku-composer", className: "surface-card p-2.5 space-y-1.5" },
                    react_1.default.createElement("h2", { className: "text-sm font-semibold text-primary" }, "\u0411\u044B\u0441\u0442\u0440\u043E\u0435 \u0432\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435 \u043D\u0435\u0441\u0442\u0430\u043D\u0434\u0430\u0440\u0442\u043D\u043E\u0439 \u043F\u043E\u0437\u0438\u0446\u0438\u0438 \u0432 \u0432\u0435\u0434\u043E\u043C\u043E\u0441\u0442\u044C"),
                    react_1.default.createElement("form", { noValidate: true, onSubmit: handleComposeSubmit, className: "space-y-2" },
                        react_1.default.createElement("div", { className: "space-y-1" },
                            react_1.default.createElement("label", { htmlFor: "composer-sku-name", className: "block text-xs font-medium text-secondary" }, "\u041D\u0430\u0438\u043C\u0435\u043D\u043E\u0432\u0430\u043D\u0438\u0435 \u0443\u0437\u043B\u0430 \u0438\u043B\u0438 \u0440\u0430\u0441\u0445\u043E\u0434\u043D\u0438\u043A\u0430"),
                            react_1.default.createElement("input", { ref: inputRef, id: "composer-sku-name", type: "text", value: draftName, "aria-invalid": formError ? 'true' : undefined, "aria-describedby": formError ? 'inv-s2-form-err' : undefined, onChange: (e) => {
                                    setDraftName(e.target.value);
                                    if (formError)
                                        setFormError('');
                                }, placeholder: "\u0414\u043E\u0431\u0430\u0432\u0438\u0442\u044C \u043A\u043E\u043C\u043C\u0435\u0440\u0447\u0435\u0441\u043A\u0443\u044E \u0437\u0430\u044F\u0432\u043A\u0443: \u0410\u0432\u0442\u043E\u043C\u0430\u0442 \u0437\u0430\u0449\u0438\u0442\u044B 16\u0410", className: "w-full field-compact" }),
                            formError ? (react_1.default.createElement("p", { id: "inv-s2-form-err", role: "alert", className: "text-xs text-status-danger mt-0.5" }, formError)) : null),
                        react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" },
                            react_1.default.createElement("div", { className: "flex flex-col justify-end gap-1 min-w-0" },
                                react_1.default.createElement("label", { htmlFor: "composer-sup-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u043B\u043E\u0449\u0430\u0434\u043A\u0430"),
                                react_1.default.createElement("select", { id: "composer-sup-select", value: draftSupplier, onChange: (e) => setDraftSupplier(e.target.value), className: "w-full field-compact" }, presets_1.SUPPLIER_LIST.map((sup) => (react_1.default.createElement("option", { key: sup.id, value: sup.id }, sup.name))))),
                            react_1.default.createElement("div", { className: "flex flex-col justify-end gap-1 min-w-0" },
                                react_1.default.createElement("label", { htmlFor: "composer-prio-select", className: "block text-xs font-medium text-secondary" }, "\u041F\u0440\u0438\u043E\u0440\u0438\u0442\u0435\u0442"),
                                react_1.default.createElement("select", { id: "composer-prio-select", value: draftPriority, onChange: (e) => setDraftPriority(e.target.value), className: "w-full field-compact" },
                                    react_1.default.createElement("option", { value: "critical" }, "\u041A\u0440\u0438\u0442\u0438\u0447\u043D\u044B\u0439"),
                                    react_1.default.createElement("option", { value: "standard" }, "\u0421\u0442\u0430\u043D\u0434\u0430\u0440\u0442\u043D\u044B\u0439")))),
                        react_1.default.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5 items-end" },
                            react_1.default.createElement("div", { className: "flex flex-col justify-end gap-1 min-w-0" },
                                react_1.default.createElement("label", { htmlFor: "composer-qty-input", className: "block text-xs font-medium text-secondary" }, "\u041F\u0430\u0440\u0442\u0438\u044F, \u0448\u0442."),
                                react_1.default.createElement("input", { id: "composer-qty-input", type: "number", min: "1", max: "5000", step: "1", value: draftQtyStr, onChange: (e) => setDraftQtyStr(e.target.value), className: "w-full field-compact tabular-nums" })),
                            react_1.default.createElement("div", { className: "flex flex-col justify-end min-w-0" },
                                react_1.default.createElement("button", { type: "submit", className: "btn-secondary w-full radius-control" }, "\u0414\u043E\u0431\u0430\u0432\u0438\u0442\u044C \u0441\u0442\u0440\u043E\u043A\u0443")))))),
            react_1.default.createElement("div", { className: "xl:col-span-6 min-w-0" },
                react_1.default.createElement(WarehousePalletShareCard_1.WarehousePalletShareCard, { state: state, summary: summary, discreteRampSlots: waveFin.discreteRampSlots }))),
        react_1.default.createElement(WarehouseGateScheduleCard_1.WarehouseGateScheduleCard, { items: state.items, activeSkuId: state.activeSkuId, summary: summary })));
}

  };

  moduleFactories["store/balanceSolver"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.formatShortBalanceReason = formatShortBalanceReason;
exports.balanceOrderToWarehouse = balanceOrderToWarehouse;
exports.computeWhatIfComparison = computeWhatIfComparison;
const presets_1 = require("../data/presets");
const replenishmentMetrics_1 = require("./replenishmentMetrics");
const stochasticAnalytics_1 = require("./stochasticAnalytics");
function formatShortBalanceReason(reason) {
    if (!reason)
        return '';
    return reason
        .replace(/\s*\([^)]*\)/g, '')
        .replace(/\s*·\s*/g, ', ')
        .trim();
}
function selectTrimmableCandidate(working, transitDelayDays, backupChannel) {
    const safeStandard = working
        .filter((it) => {
        if (it.priority !== 'standard')
            return false;
        const step = (0, presets_1.getSupplierBatchStep)(it.supplierId);
        if (it.orderQty <= step)
            return false;
        const minSafe = Math.max(step, (0, replenishmentMetrics_1.computeRequiredTargetStock)(it, transitDelayDays, backupChannel) - it.currentStock);
        return it.orderQty - step >= minSafe;
    })
        .sort((a, b) => {
        const aExcess = (a.currentStock + a.orderQty) / Math.max(1, a.dailyDemand);
        const bExcess = (b.currentStock + b.orderQty) / Math.max(1, b.dailyDemand);
        if (Math.abs(bExcess - aExcess) > 0.5)
            return bExcess - aExcess;
        return 1 / Math.max(1, a.unitsPerPallet) - 1 / Math.max(1, b.unitsPerPallet);
    });
    if (safeStandard.length > 0)
        return safeStandard[0];
    const byOrderQtyDesc = (priority) => working
        .filter((it) => it.priority === priority && it.orderQty > (0, presets_1.getSupplierBatchStep)(it.supplierId))
        .sort((a, b) => b.orderQty - a.orderQty);
    return byOrderQtyDesc('standard')[0] || byOrderQtyDesc('critical')[0] || null;
}
function balanceOrderToWarehouse(items, constraints, transitDelayDays, backupChannel) {
    const beforeSummary = (0, replenishmentMetrics_1.computeOrderSummary)(items, constraints, transitDelayDays, backupChannel);
    const working = items.map((it) => ({ ...it }));
    for (const item of working) {
        if (item.priority !== 'critical')
            continue;
        const step = (0, presets_1.getSupplierBatchStep)(item.supplierId);
        const target = (0, replenishmentMetrics_1.computeRequiredTargetStock)(item, transitDelayDays, backupChannel);
        const neededQty = Math.max(step, Math.ceil((target - item.currentStock) / step) * step);
        if (item.orderQty < neededQty) {
            item.orderQty = neededQty;
            item.manualOverride = false;
        }
    }
    for (let guard = 0; guard < 180; guard++) {
        const cur = (0, replenishmentMetrics_1.computeOrderSummary)(working, constraints, transitDelayDays, backupChannel);
        if (cur.overLimitCount === 0)
            break;
        const candidate = selectTrimmableCandidate(working, transitDelayDays, backupChannel);
        if (!candidate)
            break;
        candidate.orderQty -= (0, presets_1.getSupplierBatchStep)(candidate.supplierId);
        candidate.manualOverride = false;
    }
    const afterSummary = (0, replenishmentMetrics_1.computeOrderSummary)(working, constraints, transitDelayDays, backupChannel);
    const lineDiffs = [];
    for (let i = 0; i < working.length; i++) {
        const orig = items[i];
        const updated = working[i];
        if (updated.orderQty === orig.orderQty)
            continue;
        const deltaQty = updated.orderQty - orig.orderQty;
        const deltaPallets = Number((deltaQty / Math.max(1, orig.unitsPerPallet)).toFixed(1));
        let reason;
        let riskAvoidedKrub;
        if (deltaQty > 0) {
            riskAvoidedKrub = (0, stochasticAnalytics_1.computeCostOfInaction)(orig, transitDelayDays, backupChannel).riskKrub;
            reason = `+${deltaQty} шт., защита крит. буфера (риск ${riskAvoidedKrub.toFixed(1)} тыс. ₽)`;
        }
        else {
            const coverDays = Number(((orig.currentStock + updated.orderQty) / Math.max(1, orig.dailyDemand)).toFixed(1));
            const moqNote = `MOQ ${(0, presets_1.getSupplierBatchStep)(orig.supplierId)}`;
            reason = `${deltaQty} шт. (${deltaPallets.toFixed(1)} палл.), запас ${coverDays} сут. выше нормы, ${moqNote}`;
        }
        lineDiffs.push({
            skuId: orig.id,
            skuName: orig.name,
            beforeQty: orig.orderQty,
            afterQty: updated.orderQty,
            deltaPallets,
            reason,
            riskAvoidedKrub
        });
    }
    return {
        nextItems: working,
        before: (0, replenishmentMetrics_1.toSnapshotMetrics)(beforeSummary),
        after: (0, replenishmentMetrics_1.toSnapshotMetrics)(afterSummary),
        adjustedLinesCount: lineDiffs.length,
        lineDiffs
    };
}
function computeWhatIfComparison(state, stressDelayDays, stressChannel, stressMaxPallets) {
    const stressConstraints = {
        ...state.constraints,
        maxPallets: stressMaxPallets ?? state.constraints.maxPallets
    };
    const baseline = (0, stochasticAnalytics_1.buildWhatIfBranch)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const stressBalanced = balanceOrderToWarehouse(state.items, stressConstraints, stressDelayDays, stressChannel);
    const stress = (0, stochasticAnalytics_1.buildWhatIfBranch)(stressBalanced.nextItems, stressConstraints, stressDelayDays, stressChannel);
    const riskDelta = stress.totalCostOfInactionKrub - baseline.totalCostOfInactionKrub;
    let verdict;
    if (stress.isFeasible && baseline.isFeasible) {
        verdict =
            riskDelta <= 0
                ? `Стресс-сценарий вписывается в лимиты (Δ риск ${riskDelta.toFixed(1)} тыс. ₽).`
                : `Стресс-сценарий выполним, но риск вырастает на ${riskDelta.toFixed(1)} тыс. ₽.`;
    }
    else if (stress.isFeasible) {
        verdict = `Балансировка снимает перегруз и закрывает дефицит (${stress.totalPallets.toFixed(1)} палл.).`;
    }
    else if (stress.overLimitCount > 0) {
        verdict = `Превышено ограничений РЦ: ${stress.overLimitCount}; дефицит позиций: ${stress.stockoutRiskCount}. Смягчите лимит паллет или смените канал.`;
    }
    else {
        verdict = `Габариты РЦ соблюдены (${stress.totalPallets.toFixed(1)} палл.), но остается дефицит ${stress.stockoutRiskCount} поз. (риск ${Math.round(stress.totalCostOfInactionKrub)} тыс. ₽) — выберите ускоренный канал.`;
    }
    return { baseline, stress, verdict };
}

  };

  moduleFactories["store/domainMutations"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateSkuQtyMutation = updateSkuQtyMutation;
exports.resetSkuMutation = resetSkuMutation;
exports.alignSkuStochasticMutation = alignSkuStochasticMutation;
exports.balanceOrderMutation = balanceOrderMutation;
exports.updateConstraintsMutation = updateConstraintsMutation;
exports.addCustomSkuMutation = addCustomSkuMutation;
exports.setTransitScenarioMutation = setTransitScenarioMutation;
const presets_1 = require("../data/presets");
const replenishmentEngine_1 = require("./replenishmentEngine");
const storePersistence_1 = require("./storePersistence");
function updateSkuQtyMutation(state, skuId, nextQty, summary, detail, toastMessage, manualOverride) {
    const nextItems = state.items.map((i) => i.id === skuId
        ? {
            ...i,
            orderQty: nextQty,
            ...(manualOverride === undefined ? {} : { manualOverride })
        }
        : i);
    return {
        ...state,
        activeSkuId: skuId,
        items: nextItems,
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, summary, detail),
        toastMessage,
        toastCanUndo: true
    };
}
function resetSkuMutation(state, skuId) {
    const target = state.items.find((i) => i.id === skuId);
    if (!target)
        return null;
    const recQty = (0, replenishmentEngine_1.computeRecommendedOrderQty)(target, state.transitDelayDays, state.backupChannel);
    if (target.orderQty === recQty && !target.manualOverride)
        return null;
    return updateSkuQtyMutation(state, skuId, recQty, `Сброс к норме «${target.name}»`, `Восстановлена расчетная партия ${recQty} шт. по ROP + SS`, `Расчетная норма: ${recQty} шт.`, false);
}
function alignSkuStochasticMutation(state, skuId) {
    const target = state.items.find((i) => i.id === skuId);
    if (!target)
        return null;
    const stoch = (0, replenishmentEngine_1.computeStochasticBuffer)(target, state.transitDelayDays, state.backupChannel);
    const baseTarget = (0, replenishmentEngine_1.computeRequiredTargetStock)(target, state.transitDelayDays, state.backupChannel);
    const optTarget = Math.max(baseTarget, stoch.stochasticRop);
    const step = (0, presets_1.getSupplierBatchStep)(target.supplierId);
    const optQty = Math.ceil(Math.max(step, optTarget - target.currentStock) / step) * step;
    if (target.orderQty === optQty && !target.manualOverride) {
        return {
            nextState: { ...state, toastMessage: `σ-норма уже установлена: ${optQty} шт.`, toastCanUndo: false },
            pushUndo: false
        };
    }
    return {
        nextState: updateSkuQtyMutation(state, skuId, optQty, `Выравнивание по σ-буферу «${target.name}»: ${optQty} шт.`, `Целевой SL ${stoch.serviceLevelPct}%, σ-ROP ${stoch.stochasticRop} шт., MOQ ${step}`, `Партия по σ-норме: ${optQty} шт.`, false),
        pushUndo: true
    };
}
function balanceOrderMutation(state, requireStockoutZero, statusSeq) {
    const res = (0, replenishmentEngine_1.balanceOrderToWarehouse)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const isClean = state.lastBalanceDiff !== null &&
        res.adjustedLinesCount === 0 &&
        res.after.overLimitCount === 0 &&
        (!requireStockoutZero || res.after.stockoutRiskCount === 0);
    if (isClean) {
        const seq = statusSeq + 1;
        const notice = requireStockoutZero
            ? `Ведомость проверена, паллет ${res.after.totalPallets.toFixed(1)}, сверка #${seq}`
            : `Габаритные лимиты подтверждены, ${res.after.totalPallets.toFixed(1)} паллет, #${seq}`;
        const toast = requireStockoutZero
            ? `Ведомость уже сбалансирована, ${res.after.totalPallets.toFixed(1)} паллет`
            : `Габаритные лимиты уже соблюдены, ${res.after.totalPallets.toFixed(1)} паллет`;
        return {
            nextState: { ...state, exportNotice: notice, toastMessage: toast, toastCanUndo: false },
            pushUndo: false
        };
    }
    return {
        nextState: {
            ...state,
            items: res.nextItems,
            lastBalanceDiff: {
                appliedAt: (0, storePersistence_1.nowHHMM)(),
                before: res.before,
                after: res.after,
                adjustedLinesCount: res.adjustedLinesCount,
                lineDiffs: res.lineDiffs
            },
            history: (0, storePersistence_1.prependAuditEntry)(state.history, requireStockoutZero ? 'Сбалансирован заказ под емкость склада' : 'Применены габаритные лимиты склада', requireStockoutZero
                ? `Паллеты: ${res.before.totalPallets.toFixed(1)} → ${res.after.totalPallets.toFixed(1)}, дефицит: ${res.before.stockoutRiskCount} → ${res.after.stockoutRiskCount}`
                : `Загрузка ${res.after.totalPallets.toFixed(1)} паллет, ${res.after.totalWeightKg} кг, ${res.after.totalBudgetKrub.toFixed(1)} тыс. ₽`),
            toastMessage: requireStockoutZero
                ? `Заказ уложен: ${res.after.totalPallets.toFixed(1)} паллет, дефицит ${res.after.stockoutRiskCount}`
                : `Партии поджаты под лимит: ${res.after.totalPallets.toFixed(1)} паллет`,
            toastCanUndo: true
        },
        pushUndo: true
    };
}
function updateConstraintsMutation(state, patch) {
    const nextConstraints = { ...state.constraints, ...patch };
    return {
        ...state,
        constraints: nextConstraints,
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, 'Обновлен габаритный лимит склада', `Приемка ${nextConstraints.maxPallets} паллет, резерв ворот ${nextConstraints.reserveGatePallets}, до ${nextConstraints.maxWeightKg} кг`),
        toastMessage: `Лимит склада: ${nextConstraints.maxPallets - nextConstraints.reserveGatePallets} рабочих паллет`,
        toastCanUndo: true
    };
}
function addCustomSkuMutation(state, input) {
    const newItem = (0, storePersistence_1.createCustomSkuItem)(input);
    if (!newItem)
        return null;
    return {
        ...state,
        activeSkuId: newItem.id,
        items: [...state.items, newItem],
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, `Добавлена позиция «${newItem.name}»`, `Партия ${newItem.orderQty} шт., ${(0, presets_1.getSupplier)(newItem.supplierId).name}`),
        toastMessage: `Добавлено в заказ: ${newItem.name}`,
        toastCanUndo: true
    };
}
function setTransitScenarioMutation(state, transitDelayDays, backupChannel) {
    if (state.transitDelayDays === transitDelayDays && state.backupChannel === backupChannel) {
        return null;
    }
    const ch = presets_1.BACKUP_CHANNELS[backupChannel];
    return {
        ...state,
        transitDelayDays,
        backupChannel,
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, `Маршрутный режим: ${ch.label}`, `Поправка задержки +${transitDelayDays} дн.`),
        toastMessage: `Канал доставки: ${ch.label}`,
        toastCanUndo: true
    };
}

  };

  moduleFactories["store/domainNetworkMutations"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.selectMapNodeState = selectMapNodeState;
exports.loadPresetState = loadPresetState;
exports.cycleSafetyMutation = cycleSafetyMutation;
exports.updateSkuSupplierMutation = updateSkuSupplierMutation;
exports.assignOptimalSuppliersMutation = assignOptimalSuppliersMutation;
exports.reinforceBufferMutation = reinforceBufferMutation;
exports.reconcileNetworkFlowsMutation = reconcileNetworkFlowsMutation;
const presets_1 = require("../data/presets");
const replenishmentEngine_1 = require("./replenishmentEngine");
const storePersistence_1 = require("./storePersistence");
const OUTBOUND_SKU_MAP = {
    'out-tula': 'sku-power-ctrl',
    'out-nn': 'sku-pressure-sens',
    'out-voronezh': 'sku-line-relay',
    'out-samara': 'sku-terminal-blk'
};
function selectMapNodeState(state, nodeId) {
    const isSup = nodeId in presets_1.SUPPLIERS;
    const matchedSku = isSup
        ? state.items.find((i) => i.supplierId === nodeId)
        : state.items.find((i) => i.id === OUTBOUND_SKU_MAP[nodeId]);
    return {
        ...state,
        selectedMapNodeId: nodeId,
        selectedSupplierId: isSup ? nodeId : state.selectedSupplierId,
        activeSkuId: matchedSku ? matchedSku.id : state.activeSkuId
    };
}
function loadPresetState(state, presetId) {
    const fresh = (0, storePersistence_1.buildInitialState)(presetId);
    const label = presets_1.SCENARIO_PRESETS.find((p) => p.id === presetId)?.label || presetId;
    return {
        ...fresh,
        activeScreenId: state.activeScreenId,
        toastMessage: `Загружен сценарий: ${label}`,
        toastCanUndo: true
    };
}
function cycleSafetyMutation(state, skuId) {
    const target = state.items.find((i) => i.id === skuId);
    if (!target)
        return null;
    const cycle = [6, 8, 10, 12, 14];
    const nextSafety = cycle[(cycle.indexOf(target.safetyDays) + 1) % cycle.length];
    return {
        ...state,
        activeSkuId: skuId,
        items: state.items.map((i) => (i.id === skuId ? { ...i, safetyDays: nextSafety } : i)),
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, `Страховой запас «${target.name}», ${nextSafety} дн.`, `Точка дозаказа: ${target.reorderPoint} шт.`),
        toastMessage: `Страховой буфер: ${nextSafety} дн.`,
        toastCanUndo: true
    };
}
function updateSkuSupplierMutation(state, skuId, supplierId) {
    const target = state.items.find((i) => i.id === skuId);
    if (!target || target.supplierId === supplierId)
        return null;
    const sup = presets_1.SUPPLIERS[supplierId];
    return {
        ...state,
        activeSkuId: skuId,
        selectedSupplierId: supplierId,
        items: state.items.map((i) => (i.id === skuId ? { ...i, supplierId } : i)),
        lastBalanceDiff: null,
        history: (0, storePersistence_1.prependAuditEntry)(state.history, `Поставщик «${target.name}», ${sup.name}`, `Срок ${sup.leadDays} дн., надежность ${sup.reliabilityPct.toFixed(1)}%`),
        toastMessage: `Назначен поставщик: ${sup.name}`,
        toastCanUndo: true
    };
}
function assignOptimalSuppliersMutation(state, statusSeq) {
    const res = (0, replenishmentEngine_1.assignBestSuppliersToItems)(state.items);
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(res.nextItems, state.constraints, state.transitDelayDays, state.backupChannel);
    if (res.switchedCount === 0) {
        const seq = statusSeq + 1;
        return {
            nextState: {
                ...state,
                exportNotice: `Пул поставщиков оптимален, надежность ${summary.avgReliabilityPct.toFixed(1)}%, #${seq}`,
                toastMessage: `Лучшие поставщики уже закреплены, ${summary.avgReliabilityPct.toFixed(1)}%`,
                toastCanUndo: false
            },
            pushUndo: false
        };
    }
    const activeUpdated = res.nextItems.find((i) => i.id === state.activeSkuId) || res.nextItems[0];
    return {
        nextState: {
            ...state,
            items: res.nextItems,
            selectedSupplierId: activeUpdated ? activeUpdated.supplierId : state.selectedSupplierId,
            lastBalanceDiff: null,
            history: (0, storePersistence_1.prependAuditEntry)(state.history, 'Назначены оптимальные поставщики по пулу', `Переключено позиций: ${res.switchedCount}, надежность ${summary.avgReliabilityPct.toFixed(1)}%, срок ${summary.avgLeadDays.toFixed(1)} дн.`),
            toastMessage: `Поставщики обновлены, надежность ${summary.avgReliabilityPct.toFixed(1)}%`,
            toastCanUndo: true
        },
        pushUndo: true
    };
}
function reinforceBufferMutation(state, statusSeq) {
    const nextChannel = state.transitDelayDays >= 4 && state.backupChannel === 'direct_rail'
        ? 'regional_hub'
        : state.backupChannel;
    const res = (0, replenishmentEngine_1.reinforceTransitBuffers)(state.items, state.transitDelayDays, nextChannel);
    if (res.updatedCount === 0 && nextChannel === state.backupChannel) {
        const seq = statusSeq + 1;
        return {
            nextState: {
                ...state,
                exportNotice: `Страховой буфер максимален, канал ${presets_1.BACKUP_CHANNELS[nextChannel].label}, #${seq}`,
                toastMessage: 'Страховой запас уже на защитном уровне',
                toastCanUndo: false
            },
            pushUndo: false
        };
    }
    return {
        nextState: {
            ...state,
            backupChannel: nextChannel,
            items: res.nextItems,
            lastBalanceDiff: null,
            history: (0, storePersistence_1.prependAuditEntry)(state.history, 'Усилен страховой запас на время в пути', `Обновлено строк: ${res.updatedCount}, канал ${presets_1.BACKUP_CHANNELS[nextChannel].label}`),
            toastMessage: `Страховой буфер усилен для ${res.updatedCount} позиций`,
            toastCanUndo: true
        },
        pushUndo: true
    };
}
function reconcileNetworkFlowsMutation(state) {
    const res = (0, replenishmentEngine_1.reconcileSupplyNetworkFlows)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    if (!res.changed && res.after.overLimitCount === 0 && res.after.stockoutRiskCount === 0) {
        return {
            nextState: {
                ...state,
                toastMessage: `Потоки сети сбалансированы, приемка ${res.after.totalPallets.toFixed(1)} паллет`,
                toastCanUndo: false
            },
            pushUndo: false
        };
    }
    const chLabel = presets_1.BACKUP_CHANNELS[res.nextChannel].label;
    return {
        nextState: {
            ...state,
            backupChannel: res.nextChannel,
            items: res.nextItems,
            lastBalanceDiff: {
                appliedAt: (0, storePersistence_1.nowHHMM)(),
                before: res.before,
                after: res.after,
                adjustedLinesCount: Math.max(1, res.lineDiffs.length),
                lineDiffs: res.lineDiffs
            },
            history: (0, storePersistence_1.prependAuditEntry)(state.history, 'Выровнены входящие и исходящие потоки сети', `Канал: ${chLabel}, паллеты ${res.after.totalPallets.toFixed(1)}, дефицит ${res.after.stockoutRiskCount}`),
            toastMessage: `Сеть выровнена: ${res.after.totalPallets.toFixed(1)} паллет, канал ${chLabel}`,
            toastCanUndo: true
        },
        pushUndo: true
    };
}

  };

  moduleFactories["store/domainStore"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.inventoryStore = exports.STORAGE_KEY = void 0;
exports.useInventoryStore = useInventoryStore;
const react_1 = require("react");
const presets_1 = require("../data/presets");
const storePersistence_1 = require("./storePersistence");
Object.defineProperty(exports, "STORAGE_KEY", { enumerable: true, get: function () { return storePersistence_1.STORAGE_KEY; } });
const domainMutations_1 = require("./domainMutations");
const domainNetworkMutations_1 = require("./domainNetworkMutations");
class LocalFirstDomainStore {
    constructor() {
        this.undoStack = [];
        this.listeners = new Set();
        this.exportSeq = 0;
        this.statusSeq = 0;
        this.getSnapshot = () => this.state;
        this.subscribe = (listener) => {
            this.listeners.add(listener);
            return () => this.listeners.delete(listener);
        };
        this.state = (0, storePersistence_1.hydrateStoredState)();
    }
    notify() {
        for (const listener of this.listeners)
            listener();
    }
    commit(nextState, prevForUndo) {
        this.state = nextState;
        if (prevForUndo) {
            this.undoStack.push(prevForUndo);
            if (this.undoStack.length > 20)
                this.undoStack.shift();
        }
        (0, storePersistence_1.saveStoredState)(this.state);
        this.notify();
    }
    commitMaybeUndo(nextState) {
        if (nextState)
            this.commit(nextState, structuredClone(this.state));
    }
    applyRes(res) {
        if (!res.pushUndo)
            this.statusSeq += 1;
        this.commit(res.nextState, res.pushUndo ? structuredClone(this.state) : null);
    }
    canUndo() { return this.undoStack.length > 0; }
    dismissToast() {
        if (!this.state.toastMessage)
            return;
        this.state = { ...this.state, toastMessage: null, toastCanUndo: false };
        this.notify();
    }
    setScreen(screenId) {
        if (this.state.activeScreenId === screenId)
            return;
        this.state = { ...this.state, activeScreenId: screenId };
        this.notify();
    }
    selectSku(skuId) {
        if (this.state.activeSkuId === skuId)
            return;
        const found = this.state.items.find((i) => i.id === skuId);
        this.commit({ ...this.state, activeSkuId: skuId, selectedSupplierId: found ? found.supplierId : this.state.selectedSupplierId }, null);
    }
    undo() {
        const previous = this.undoStack.pop();
        if (!previous)
            return;
        this.commit({ ...previous, activeScreenId: this.state.activeScreenId, toastMessage: 'Последнее действие отменено', toastCanUndo: false }, null);
    }
    resetToSeed() {
        this.undoStack = [];
        this.commit({ ...(0, storePersistence_1.buildInitialState)('preset-seasonal-peak'), toastMessage: 'Восстановлена эталонная ведомость', toastCanUndo: false }, null);
    }
    selectChartSku(skuId) {
        if (this.state.activeSkuId === skuId && this.state.items.length > 1) {
            const idx = this.state.items.findIndex((i) => i.id === skuId);
            this.selectSku(this.state.items[(idx + 1) % this.state.items.length].id);
            return;
        }
        this.selectSku(skuId);
    }
    selectSupplier(supplierId) {
        if (this.state.selectedSupplierId === supplierId)
            return;
        this.commit({ ...this.state, selectedSupplierId: supplierId, selectedMapNodeId: supplierId }, null);
    }
    selectMapNode(nodeId) {
        if (this.state.selectedMapNodeId !== nodeId)
            this.commit((0, domainNetworkMutations_1.selectMapNodeState)(this.state, nodeId), null);
    }
    selectChartSupplier(supplierId) {
        if (this.state.selectedSupplierId === supplierId) {
            const ids = Object.keys(presets_1.SUPPLIERS);
            this.selectSupplier(ids[(ids.indexOf(supplierId) + 1) % ids.length]);
            return;
        }
        this.selectSupplier(supplierId);
    }
    loadPreset(presetId) { this.commitMaybeUndo((0, domainNetworkMutations_1.loadPresetState)(this.state, presetId)); }
    setMapLens(lens) {
        if ((this.state.mapLens || 'all') !== lens)
            this.commit({ ...this.state, mapLens: lens }, null);
    }
    openSkuTraceOnMap(skuId) {
        const found = this.state.items.find((i) => i.id === skuId) || this.state.items[0];
        if (!found)
            return;
        this.state = {
            ...this.state,
            activeSkuId: found.id,
            selectedSupplierId: found.supplierId,
            selectedMapNodeId: found.supplierId,
            mapLens: 'sku_peg',
            activeScreenId: 'screen-supply-map'
        };
        this.notify();
    }
    setOrderQty(skuId, rawQty) {
        const target = this.state.items.find((i) => i.id === skuId);
        if (!target || !Number.isFinite(rawQty))
            return;
        const nextQty = Math.max(10, Math.min(990, Math.round(rawQty)));
        if (nextQty === target.orderQty)
            return;
        this.commitMaybeUndo((0, domainMutations_1.updateSkuQtyMutation)(this.state, skuId, nextQty, `Ручной ввод «${target.name}»: ${nextQty} шт.`, `Прямая корректировка в ведомости (было ${target.orderQty} шт.)`, `Партия вручную: ${nextQty} шт.`, true));
    }
    adjustOrderQty(skuId, deltaQty) {
        const target = this.state.items.find((i) => i.id === skuId);
        if (!target)
            return;
        const nextQty = Math.max(10, Math.min(990, target.orderQty + deltaQty));
        if (nextQty === target.orderQty)
            return;
        const sign = deltaQty > 0 ? `+${deltaQty}` : String(deltaQty);
        this.commitMaybeUndo((0, domainMutations_1.updateSkuQtyMutation)(this.state, skuId, nextQty, `Партия «${target.name}» ${sign} шт.`, `Новый объем дозаказа: ${nextQty} шт.`, `Партия обновлена: ${nextQty} шт.`, true));
    }
    resetSkuToRecommended(skuId) { this.commitMaybeUndo((0, domainMutations_1.resetSkuMutation)(this.state, skuId)); }
    alignSkuToStochasticBuffer(skuId) {
        const res = (0, domainMutations_1.alignSkuStochasticMutation)(this.state, skuId);
        if (res)
            this.applyRes(res);
    }
    cycleSafetyDays(skuId) { this.commitMaybeUndo((0, domainNetworkMutations_1.cycleSafetyMutation)(this.state, skuId)); }
    updateSkuSupplier(skuId, supplierId) {
        this.commitMaybeUndo((0, domainNetworkMutations_1.updateSkuSupplierMutation)(this.state, skuId, supplierId));
    }
    updateConstraints(patch) {
        this.commitMaybeUndo((0, domainMutations_1.updateConstraintsMutation)(this.state, patch));
    }
    addCustomSku(input) {
        this.commitMaybeUndo((0, domainMutations_1.addCustomSkuMutation)(this.state, input));
    }
    setTransitScenario(transitDelayDays, backupChannel) {
        this.commitMaybeUndo((0, domainMutations_1.setTransitScenarioMutation)(this.state, transitDelayDays, backupChannel));
    }
    balanceOrder() { this.applyRes((0, domainMutations_1.balanceOrderMutation)(this.state, true, this.statusSeq)); }
    applyWarehouseLimitsAndBalance() { this.applyRes((0, domainMutations_1.balanceOrderMutation)(this.state, false, this.statusSeq)); }
    reconcileNetworkFlows() { this.applyRes((0, domainNetworkMutations_1.reconcileNetworkFlowsMutation)(this.state)); }
    assignOptimalSuppliers() { this.applyRes((0, domainNetworkMutations_1.assignOptimalSuppliersMutation)(this.state, this.statusSeq)); }
    reinforceDeliveryBuffer() { this.applyRes((0, domainNetworkMutations_1.reinforceBufferMutation)(this.state, this.statusSeq)); }
    setExportFormat(fmt) {
        if (this.state.exportFormat === fmt)
            return;
        this.commit({
            ...this.state,
            exportFormat: fmt,
            exportNotice: fmt === 'csv'
                ? 'Показана табличная спецификация заказа .csv с разделителем точка с запятой'
                : 'Показана пояснительная записка для согласования закупки'
        }, null);
    }
    recordArtifactExport(actionLabel) {
        this.exportSeq += 1;
        this.commit({
            ...this.state,
            exportNotice: `${actionLabel}, строк ${this.state.items.length}, выгрузка #${this.exportSeq}`,
            history: (0, storePersistence_1.prependAuditEntry)(this.state.history, actionLabel, `${this.state.waveLabel}, позиций ${this.state.items.length}`),
            toastMessage: actionLabel,
            toastCanUndo: false
        }, null);
    }
}
exports.inventoryStore = new LocalFirstDomainStore();
function useInventoryStore() {
    return (0, react_1.useSyncExternalStore)(exports.inventoryStore.subscribe, exports.inventoryStore.getSnapshot, exports.inventoryStore.getSnapshot);
}

  };

  moduleFactories["store/replenishmentEngine"] = function(exports, module, require) {
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.formatShortBalanceReason = exports.computeWhatIfComparison = exports.balanceOrderToWarehouse = exports.computeWaveFinancialSummary = exports.computeSupplierNegotiationImpact = exports.computeStochasticBuffer = exports.computeCostOfInaction = void 0;
exports.assignBestSuppliersToItems = assignBestSuppliersToItems;
exports.reinforceTransitBuffers = reinforceTransitBuffers;
exports.reconcileSupplyNetworkFlows = reconcileSupplyNetworkFlows;
const balanceSolver_1 = require("./balanceSolver");
const replenishmentMetrics_1 = require("./replenishmentMetrics");
const stochasticAnalytics_1 = require("./stochasticAnalytics");
Object.defineProperty(exports, "computeCostOfInaction", { enumerable: true, get: function () { return stochasticAnalytics_1.computeCostOfInaction; } });
Object.defineProperty(exports, "computeStochasticBuffer", { enumerable: true, get: function () { return stochasticAnalytics_1.computeStochasticBuffer; } });
Object.defineProperty(exports, "computeSupplierNegotiationImpact", { enumerable: true, get: function () { return stochasticAnalytics_1.computeSupplierNegotiationImpact; } });
Object.defineProperty(exports, "computeWaveFinancialSummary", { enumerable: true, get: function () { return stochasticAnalytics_1.computeWaveFinancialSummary; } });
__exportStar(require("./replenishmentMetrics"), exports);
var balanceSolver_2 = require("./balanceSolver");
Object.defineProperty(exports, "balanceOrderToWarehouse", { enumerable: true, get: function () { return balanceSolver_2.balanceOrderToWarehouse; } });
Object.defineProperty(exports, "computeWhatIfComparison", { enumerable: true, get: function () { return balanceSolver_2.computeWhatIfComparison; } });
Object.defineProperty(exports, "formatShortBalanceReason", { enumerable: true, get: function () { return balanceSolver_2.formatShortBalanceReason; } });
function resolveBestSupplierForSku(item) {
    if (item.priority !== 'critical')
        return 'ural-privod';
    return item.dailyDemand >= 7 ? 'sever-snab' : 'balt-komplekt';
}
function assignBestSuppliersToItems(items) {
    let switchedCount = 0;
    const nextItems = items.map((item) => {
        const targetSupplier = resolveBestSupplierForSku(item);
        if (item.supplierId !== targetSupplier) {
            switchedCount += 1;
            return { ...item, supplierId: targetSupplier };
        }
        return { ...item };
    });
    return { nextItems, switchedCount };
}
function reinforceTransitBuffers(items, transitDelayDays, backupChannel) {
    let updatedCount = 0;
    const nextItems = items.map((item) => {
        const nextSafety = item.priority === 'critical' ? Math.min(16, item.safetyDays + 2) : item.safetyDays;
        const target = (0, replenishmentMetrics_1.computeRequiredTargetStock)({ ...item, safetyDays: nextSafety }, transitDelayDays, backupChannel);
        const minOrder = Math.max(item.orderQty, Math.ceil(Math.max(10, target - item.currentStock) / 10) * 10);
        if (nextSafety !== item.safetyDays || minOrder !== item.orderQty) {
            updatedCount += 1;
        }
        return {
            ...item,
            safetyDays: nextSafety,
            orderQty: minOrder
        };
    });
    return { nextItems, updatedCount };
}
function pickEscalatedChannel(transitDelayDays, backupChannel) {
    if (transitDelayDays >= 9)
        return 'express_auto';
    if (transitDelayDays >= 4 && backupChannel === 'direct_rail')
        return 'regional_hub';
    return backupChannel;
}
function reconcileSupplyNetworkFlows(items, constraints, transitDelayDays, backupChannel) {
    const nextChannel = pickEscalatedChannel(transitDelayDays, backupChannel);
    const tunedItems = items.map((it) => {
        const nextSupplier = it.priority === 'critical' && it.supplierId === 'volga-pribor'
            ? 'sever-snab'
            : it.supplierId;
        return { ...it, supplierId: nextSupplier };
    });
    const balanced = (0, balanceSolver_1.balanceOrderToWarehouse)(tunedItems, constraints, transitDelayDays, nextChannel);
    const before = (0, replenishmentMetrics_1.computeOrderSummary)(items, constraints, transitDelayDays, backupChannel);
    const lineDiffs = [];
    let skuChanged = nextChannel !== backupChannel;
    for (let i = 0; i < items.length; i++) {
        if (balanced.nextItems[i].orderQty !== items[i].orderQty ||
            balanced.nextItems[i].supplierId !== items[i].supplierId) {
            skuChanged = true;
            if (balanced.nextItems[i].orderQty !== items[i].orderQty) {
                const dq = balanced.nextItems[i].orderQty - items[i].orderQty;
                lineDiffs.push({
                    skuId: items[i].id,
                    skuName: items[i].name,
                    beforeQty: items[i].orderQty,
                    afterQty: balanced.nextItems[i].orderQty,
                    deltaPallets: Number((dq / Math.max(1, items[i].unitsPerPallet)).toFixed(1)),
                    reason: dq > 0 ? 'Поднято под отгрузку' : 'Сжато под рампу'
                });
            }
        }
    }
    return {
        nextItems: balanced.nextItems,
        nextChannel,
        before: (0, replenishmentMetrics_1.toSnapshotMetrics)(before),
        after: balanced.after,
        lineDiffs,
        changed: skuChanged
    };
}

  };

  moduleFactories["store/replenishmentMetrics"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.computeEffectiveLeadDays = computeEffectiveLeadDays;
exports.computeLineUnitCostKrub = computeLineUnitCostKrub;
exports.computeRequiredTargetStock = computeRequiredTargetStock;
exports.isSkuAtStockoutRisk = isSkuAtStockoutRisk;
exports.computeRecommendedOrderQty = computeRecommendedOrderQty;
exports.computeDaysOfCover = computeDaysOfCover;
exports.computeSawtoothProjection = computeSawtoothProjection;
exports.computeItemPallets = computeItemPallets;
exports.computeItemWeightKg = computeItemWeightKg;
exports.computeItemCostKrub = computeItemCostKrub;
exports.computeOrderSummary = computeOrderSummary;
exports.toSnapshotMetrics = toSnapshotMetrics;
const presets_1 = require("../data/presets");
function computeEffectiveLeadDays(item, transitDelayDays, backupChannel) {
    const sup = (0, presets_1.getSupplier)(item.supplierId);
    const ch = presets_1.BACKUP_CHANNELS[backupChannel] || presets_1.BACKUP_CHANNELS.direct_rail;
    return Math.max(2, sup.leadDays + transitDelayDays + ch.leadDeltaDays);
}
function computeLineUnitCostKrub(item, backupChannel) {
    const sup = (0, presets_1.getSupplier)(item.supplierId);
    const ch = presets_1.BACKUP_CHANNELS[backupChannel] || presets_1.BACKUP_CHANNELS.direct_rail;
    const raw = item.unitCostKrub * sup.priceFactor * (1 + ch.costSurchargePct / 100);
    return Number(raw.toFixed(2));
}
function computeRequiredTargetStock(item, transitDelayDays, backupChannel) {
    const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
    const coverDays = leadDays + item.safetyDays;
    return Math.max(item.reorderPoint, Math.round(item.dailyDemand * coverDays));
}
function isSkuAtStockoutRisk(item, transitDelayDays, backupChannel) {
    const target = computeRequiredTargetStock(item, transitDelayDays, backupChannel);
    return item.currentStock + item.orderQty < target;
}
function computeRecommendedOrderQty(item, transitDelayDays, backupChannel) {
    const step = (0, presets_1.getSupplierBatchStep)(item.supplierId);
    const target = computeRequiredTargetStock(item, transitDelayDays, backupChannel);
    const gap = Math.max(step, target - item.currentStock);
    return Math.ceil(gap / step) * step;
}
function computeDaysOfCover(item, transitDelayDays, backupChannel) {
    const demand = Math.max(1, item.dailyDemand);
    const leadDays = computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
    const runoutDays = Number((item.currentStock / demand).toFixed(1));
    const totalCoverDays = Number(((item.currentStock + item.orderQty) / demand).toFixed(1));
    const targetCoverDays = leadDays + item.safetyDays;
    const atRisk = isSkuAtStockoutRisk(item, transitDelayDays, backupChannel);
    let status = 'healthy';
    if (atRisk)
        status = 'deficit';
    else if (totalCoverDays > targetCoverDays + 20)
        status = 'overstock';
    return {
        runoutDays,
        totalCoverDays,
        leadDays,
        targetCoverDays,
        status
    };
}
function computeSawtoothProjection(item, transitDelayDays, backupChannel, horizonDays = 21) {
    const demand = Math.max(1, item.dailyDemand);
    const leadDays = Math.min(horizonDays - 1, computeEffectiveLeadDays(item, transitDelayDays, backupChannel));
    const safetyUnits = Math.round(demand * item.safetyDays);
    const rawAtArrival = item.currentStock - leadDays * demand;
    const preArrivalStock = Math.max(0, rawAtArrival);
    const stockoutGapDays = rawAtArrival < 0 ? Number((Math.abs(rawAtArrival) / demand).toFixed(1)) : 0;
    const arrivalPeakStock = preArrivalStock + item.orderQty;
    const vertices = [];
    for (let d = 0; d < leadDays; d++) {
        vertices.push({
            day: d,
            stock: Math.max(0, Math.round(item.currentStock - d * demand)),
            phase: 'before'
        });
    }
    vertices.push({
        day: leadDays,
        stock: Math.round(preArrivalStock),
        phase: 'arrival_low'
    });
    vertices.push({
        day: leadDays,
        stock: Math.round(arrivalPeakStock),
        phase: 'arrival_peak'
    });
    for (let d = leadDays + 1; d <= horizonDays; d++) {
        vertices.push({
            day: d,
            stock: Math.max(0, Math.round(arrivalPeakStock - (d - leadDays) * demand)),
            phase: 'after'
        });
    }
    const endStock = vertices[vertices.length - 1]?.stock ?? 0;
    const maxStock = Math.max(item.currentStock, arrivalPeakStock, item.reorderPoint, safetyUnits, 20);
    return {
        horizonDays,
        leadDays,
        safetyUnits,
        reorderPoint: item.reorderPoint,
        preArrivalStock: Math.round(preArrivalStock),
        arrivalPeakStock: Math.round(arrivalPeakStock),
        endStock,
        maxStock,
        stockoutGapDays,
        vertices
    };
}
function computeItemPallets(item) {
    return Number((item.orderQty / Math.max(1, item.unitsPerPallet)).toFixed(1));
}
function computeItemWeightKg(item) {
    return Math.round(item.orderQty * item.unitWeightKg);
}
function computeItemCostKrub(item, backupChannel) {
    const unitCost = computeLineUnitCostKrub(item, backupChannel);
    return Number((item.orderQty * unitCost).toFixed(1));
}
function computeOrderSummary(items, constraints, transitDelayDays, backupChannel) {
    const effectivePalletLimit = Math.max(10, constraints.maxPallets - constraints.reserveGatePallets);
    let totalPalletsRaw = 0;
    let totalWeightKg = 0;
    let totalBudgetRaw = 0;
    let stockoutRiskCount = 0;
    let reliabilityAcc = 0;
    let leadAcc = 0;
    for (const item of items) {
        totalPalletsRaw += item.orderQty / Math.max(1, item.unitsPerPallet);
        totalWeightKg += Math.round(item.orderQty * item.unitWeightKg);
        totalBudgetRaw += computeItemCostKrub(item, backupChannel);
        if (isSkuAtStockoutRisk(item, transitDelayDays, backupChannel)) {
            stockoutRiskCount += 1;
        }
        reliabilityAcc += (0, presets_1.getSupplier)(item.supplierId).reliabilityPct;
        leadAcc += computeEffectiveLeadDays(item, transitDelayDays, backupChannel);
    }
    const totalPallets = Number(totalPalletsRaw.toFixed(1));
    const totalBudgetKrub = Number(totalBudgetRaw.toFixed(1));
    let overLimitCount = 0;
    if (totalPallets > effectivePalletLimit + 0.05)
        overLimitCount += 1;
    if (totalWeightKg > constraints.maxWeightKg)
        overLimitCount += 1;
    if (totalBudgetKrub > constraints.maxBudgetKrub + 0.05)
        overLimitCount += 1;
    const count = Math.max(1, items.length);
    return {
        totalPallets,
        effectivePalletLimit,
        totalWeightKg,
        totalBudgetKrub,
        stockoutRiskCount,
        overLimitCount,
        avgReliabilityPct: Number((reliabilityAcc / count).toFixed(1)),
        avgLeadDays: Number((leadAcc / count).toFixed(1)),
        isFeasible: overLimitCount === 0 && stockoutRiskCount === 0
    };
}
function toSnapshotMetrics(summary) {
    return {
        totalPallets: summary.totalPallets,
        totalWeightKg: summary.totalWeightKg,
        totalBudgetKrub: summary.totalBudgetKrub,
        stockoutRiskCount: summary.stockoutRiskCount,
        overLimitCount: summary.overLimitCount
    };
}

  };

  moduleFactories["store/stochasticAnalytics"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.computeStochasticBuffer = computeStochasticBuffer;
exports.computeCostOfInaction = computeCostOfInaction;
exports.computeWaveFinancialSummary = computeWaveFinancialSummary;
exports.buildWhatIfBranch = buildWhatIfBranch;
exports.computeSupplierNegotiationImpact = computeSupplierNegotiationImpact;
const presets_1 = require("../data/presets");
const replenishmentMetrics_1 = require("./replenishmentMetrics");
function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}
function computeStochasticBuffer(item, transitDelayDays, backupChannel) {
    const sup = (0, presets_1.getSupplier)(item.supplierId);
    const leadDays = (0, replenishmentMetrics_1.computeEffectiveLeadDays)(item, transitDelayDays, backupChannel);
    const serviceLevelPct = item.priority === 'critical' ? 98.5 : 92.0;
    const zScore = item.priority === 'critical' ? 2.17 : 1.41;
    const r = clamp(sup.reliabilityPct / 100, 0.5, 0.995);
    const sigmaLeadDays = Number((leadDays * Math.sqrt((1 - r) / r)).toFixed(1));
    const cv = item.priority === 'critical' ? 0.30 : 0.20;
    const sigmaDemand = Number((item.dailyDemand * cv).toFixed(1));
    const variance = leadDays * sigmaDemand ** 2 + item.dailyDemand ** 2 * sigmaLeadDays ** 2;
    const stochasticSafetyUnits = Math.round(zScore * Math.sqrt(variance));
    const stochasticSafetyDays = Number((stochasticSafetyUnits / Math.max(1, item.dailyDemand)).toFixed(1));
    const stochasticRop = Math.round(item.dailyDemand * leadDays + stochasticSafetyUnits);
    const staticSafetyUnits = Math.round(item.dailyDemand * item.safetyDays);
    const deltaUnits = stochasticSafetyUnits - staticSafetyUnits;
    return {
        serviceLevelPct,
        zScore,
        sigmaLeadDays,
        sigmaDemand,
        stochasticSafetyUnits,
        stochasticSafetyDays,
        stochasticRop,
        staticSafetyUnits,
        deltaUnits
    };
}
function computeCostOfInaction(item, transitDelayDays, backupChannel) {
    const stoch = computeStochasticBuffer(item, transitDelayDays, backupChannel);
    const target = Math.max((0, replenishmentMetrics_1.computeRequiredTargetStock)(item, transitDelayDays, backupChannel), stoch.stochasticRop);
    const covered = item.currentStock + item.orderQty;
    const shortfallUnits = Math.max(0, target - covered);
    const leadDays = (0, replenishmentMetrics_1.computeEffectiveLeadDays)(item, transitDelayDays, backupChannel);
    let stockoutProb;
    if (shortfallUnits === 0) {
        stockoutProb = clamp(0.04 + (1 - stoch.serviceLevelPct / 100) * 0.5, 0.01, 0.15);
    }
    else if (covered < leadDays * item.dailyDemand) {
        stockoutProb = clamp(0.70 + (shortfallUnits / Math.max(1, item.dailyDemand)) * 0.03, 0.70, 0.92);
    }
    else {
        stockoutProb = clamp(0.15 + (shortfallUnits / Math.max(1, stoch.stochasticSafetyUnits + 1)) * 0.55, 0.15, 0.80);
    }
    const dailyDowntimeRate = item.priority === 'critical' ? 180 : 38;
    const expectedDeficitDays = (shortfallUnits / Math.max(1, item.dailyDemand)) * stockoutProb;
    const downtimeKrub = Number((dailyDowntimeRate * expectedDeficitDays).toFixed(1));
    const orderValueKrub = item.orderQty * item.unitCostKrub;
    const expressDeltaKrub = shortfallUnits > 0 ? Number(Math.max(14, orderValueKrub * 0.075).toFixed(1)) : 0;
    const otifPenaltyKrub = Number((shortfallUnits * item.unitCostKrub * 0.12 * stockoutProb).toFixed(1));
    const riskKrub = Number((downtimeKrub + expressDeltaKrub + otifPenaltyKrub).toFixed(1));
    return {
        riskKrub,
        stockoutProbPct: Math.round(stockoutProb * 100),
        shortfallUnits,
        downtimeKrub,
        expressDeltaKrub,
        otifPenaltyKrub
    };
}
function computeWaveFinancialSummary(items, constraints, transitDelayDays, backupChannel) {
    let totalCostOfInactionKrub = 0;
    let atRiskSkuCount = 0;
    let workingCapitalKrub = 0;
    let discreteRampSlots = 0;
    let totalFloatPallets = 0;
    for (const item of items) {
        const coi = computeCostOfInaction(item, transitDelayDays, backupChannel);
        totalCostOfInactionKrub += coi.riskKrub;
        if (coi.stockoutProbPct > 15)
            atRiskSkuCount += 1;
        workingCapitalKrub += item.orderQty * item.unitCostKrub;
        const pallets = item.orderQty / Math.max(1, item.unitsPerPallet);
        discreteRampSlots += Math.ceil(pallets);
        totalFloatPallets += pallets;
    }
    const summary = (0, replenishmentMetrics_1.computeOrderSummary)(items, constraints, transitDelayDays, backupChannel);
    const estAnnualWcSavingsKrub = Number((workingCapitalKrub * 12 * 0.22 * 0.16).toFixed(1));
    const tcoWaveKrub = Number((summary.totalBudgetKrub + totalCostOfInactionKrub).toFixed(1));
    return {
        totalCostOfInactionKrub: Number(totalCostOfInactionKrub.toFixed(1)),
        atRiskSkuCount,
        workingCapitalKrub: Number(workingCapitalKrub.toFixed(1)),
        discreteRampSlots,
        floatPallets: Number(totalFloatPallets.toFixed(1)),
        estAnnualWcSavingsKrub,
        tcoWaveKrub
    };
}
function buildWhatIfBranch(items, constraints, transitDelayDays, backupChannel) {
    const summary = (0, replenishmentMetrics_1.computeOrderSummary)(items, constraints, transitDelayDays, backupChannel);
    const financials = computeWaveFinancialSummary(items, constraints, transitDelayDays, backupChannel);
    return {
        totalPallets: summary.totalPallets,
        totalWeightKg: summary.totalWeightKg,
        totalBudgetKrub: summary.totalBudgetKrub,
        stockoutRiskCount: summary.stockoutRiskCount,
        overLimitCount: summary.overLimitCount,
        totalCostOfInactionKrub: financials.totalCostOfInactionKrub,
        atRiskSkuCount: financials.atRiskSkuCount,
        isFeasible: summary.isFeasible
    };
}
function computeSupplierNegotiationImpact(sku, candidateSupplierId, transitDelayDays, backupChannel) {
    const currentCost = (0, replenishmentMetrics_1.computeItemCostKrub)(sku, backupChannel);
    const currentStoch = computeStochasticBuffer(sku, transitDelayDays, backupChannel);
    const currentCoi = computeCostOfInaction(sku, transitDelayDays, backupChannel);
    const candidateSku = { ...sku, supplierId: candidateSupplierId };
    const candidateCost = (0, replenishmentMetrics_1.computeItemCostKrub)(candidateSku, backupChannel);
    const candidateStoch = computeStochasticBuffer(candidateSku, transitDelayDays, backupChannel);
    const candidateCoi = computeCostOfInaction(candidateSku, transitDelayDays, backupChannel);
    const lineCostDeltaKrub = Number((candidateCost - currentCost).toFixed(1));
    const sigmaBufferDeltaUnits = candidateStoch.stochasticSafetyUnits - currentStoch.stochasticSafetyUnits;
    const riskDeltaKrub = Number((candidateCoi.riskKrub - currentCoi.riskKrub).toFixed(1));
    const netImpactKrub = Number((-(lineCostDeltaKrub + riskDeltaKrub)).toFixed(1));
    let verdict;
    if (candidateSupplierId === sku.supplierId) {
        verdict = 'Текущий контрагент позиции, параметры зафиксированы';
    }
    else if (netImpactKrub > 0) {
        verdict = `Выгода перехода +${netImpactKrub.toFixed(1)} тыс. ₽ по TCO`;
    }
    else if (netImpactKrub < 0) {
        verdict = `Удорожание TCO на ${Math.abs(netImpactKrub).toFixed(1)} тыс. ₽, нужен дисконт`;
    }
    else {
        verdict = 'Паритет совокупной стоимости TCO';
    }
    return {
        currentSupplierId: sku.supplierId,
        candidateSupplierId,
        lineCostDeltaKrub,
        sigmaBufferDeltaUnits,
        riskDeltaKrub,
        netImpactKrub,
        verdict
    };
}

  };

  moduleFactories["store/storePersistence"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STORAGE_KEY = void 0;
exports.nowHHMM = nowHHMM;
exports.buildInitialState = buildInitialState;
exports.hydrateStoredState = hydrateStoredState;
exports.saveStoredState = saveStoredState;
exports.prependAuditEntry = prependAuditEntry;
exports.createCustomSkuItem = createCustomSkuItem;
const presets_1 = require("../data/presets");
exports.STORAGE_KEY = 'inventory_notebook_v7_store';
function nowHHMM() {
    const now = new Date();
    const h = now.getHours();
    const m = now.getMinutes();
    const hh = h < 10 ? `0${h}` : String(h);
    const mm = m < 10 ? `0${m}` : String(m);
    return `${hh}:${mm}`;
}
function buildInitialState(presetId = 'preset-seasonal-peak') {
    const preset = presets_1.SCENARIO_PRESETS.find((p) => p.id === presetId) || presets_1.SCENARIO_PRESETS[0];
    const clonedItems = preset.items.map((it) => ({ ...it }));
    return {
        activeScreenId: 'screen-replenishment-notebook',
        activePresetId: preset.id,
        activeSkuId: clonedItems[0]?.id || 'sku-power-ctrl',
        selectedSupplierId: clonedItems[0]?.supplierId || 'balt-komplekt',
        selectedMapNodeId: 'dc-moscow',
        mapLens: 'all',
        waveLabel: preset.waveLabel,
        transitDelayDays: preset.transitDelayDays,
        backupChannel: preset.backupChannel,
        constraints: { ...preset.constraints },
        items: clonedItems,
        lastBalanceDiff: null,
        exportFormat: 'csv',
        exportNotice: 'Готово к выгрузке спецификации .csv или копированию записки',
        history: [
            {
                id: 'hist-seed-1',
                timeLabel: '09:15',
                summary: `Открыт сценарий «${preset.label}»`,
                detail: `Позиций: ${clonedItems.length}, лимит приемки ${preset.constraints.maxPallets} паллет`
            },
            {
                id: 'hist-seed-2',
                timeLabel: '09:05',
                summary: 'Подтвержден резерв разгрузочных ворот Смены А',
                detail: `Буфер рампы: ${preset.constraints.reserveGatePallets} паллет, лимит тоннажа ${preset.constraints.maxWeightKg} кг`
            },
            {
                id: 'hist-seed-3',
                timeLabel: '08:50',
                summary: 'Синхронизация остатков WMS терминала Шушары',
                detail: `Проверены страховые нормативы и точки дозаказа по ${clonedItems.length} узлам`
            },
            {
                id: 'hist-seed-4',
                timeLabel: '08:35',
                summary: 'Утвержден финансовый потолок закупочной волны',
                detail: `Лимит казначейства: ${preset.constraints.maxBudgetKrub} тыс. ₽ на текущую неделю`
            }
        ],
        toastMessage: null,
        toastCanUndo: false
    };
}
function hydrateStoredState() {
    if (typeof window === 'undefined' || !window.localStorage) {
        return buildInitialState();
    }
    try {
        const raw = window.localStorage.getItem(exports.STORAGE_KEY);
        if (!raw)
            return buildInitialState();
        const parsed = JSON.parse(raw);
        if (!parsed || !Array.isArray(parsed.items) || parsed.items.length === 0) {
            return buildInitialState();
        }
        return {
            ...buildInitialState(parsed.activePresetId || 'preset-seasonal-peak'),
            ...parsed,
            activeScreenId: 'screen-replenishment-notebook',
            toastMessage: null,
            toastCanUndo: false
        };
    }
    catch (err) {
        if (err instanceof Error) {
            return buildInitialState();
        }
        return buildInitialState();
    }
}
function saveStoredState(state) {
    if (typeof window === 'undefined' || !window.localStorage) {
        return false;
    }
    try {
        const persistedPayload = {
            ...state,
            activeScreenId: 'screen-replenishment-notebook',
            toastMessage: null,
            toastCanUndo: false
        };
        window.localStorage.setItem(exports.STORAGE_KEY, JSON.stringify(persistedPayload));
        return true;
    }
    catch (err) {
        if (err instanceof Error) {
            return false;
        }
        return false;
    }
}
function prependAuditEntry(history, summary, detail) {
    const entry = {
        id: `hist-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        timeLabel: nowHHMM(),
        summary,
        detail
    };
    return [entry, ...history].slice(0, 12);
}
function createCustomSkuItem(input) {
    const cleanName = input.name.trim();
    if (!cleanName)
        return null;
    const safeQty = Math.max(10, Math.min(1200, Math.round(input.orderQty) || 40));
    const safeCost = Number((input.unitCostKrub && input.unitCostKrub > 0 ? input.unitCostKrub : 6.8).toFixed(2));
    const safeBuffer = Math.max(4, Math.min(24, Math.round(input.safetyDays || 8)));
    return {
        id: `sku-custom-${Date.now()}`,
        name: cleanName,
        category: input.category || 'Комплектация',
        currentStock: 18,
        dailyDemand: 4,
        reorderPoint: 36,
        safetyDays: safeBuffer,
        orderQty: safeQty,
        unitCostKrub: safeCost,
        unitWeightKg: 7.5,
        unitsPerPallet: 20,
        supplierId: input.supplierId,
        priority: input.priority
    };
}

  };

  moduleFactories["types/domain"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });

  };

  moduleFactories["utils/a11yDialog"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.useDialogFocusTrap = useDialogFocusTrap;
exports.handleSelectableKeyDown = handleSelectableKeyDown;
const react_1 = require("react");
const FOCUSABLE_SELECTOR = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]';
function useDialogFocusTrap(open) {
    const dialogRef = (0, react_1.useRef)(null);
    const triggerRef = (0, react_1.useRef)(null);
    const prevRenderOpenRef = (0, react_1.useRef)(false);
    const prevOpenEffectRef = (0, react_1.useRef)(false);
    // Capture trigger before React commits modal autoFocus into the DOM
    if (open && !prevRenderOpenRef.current && typeof document !== 'undefined') {
        const ae = document.activeElement;
        if (ae && ae !== document.body && !ae.closest('[role="dialog"]')) {
            triggerRef.current = ae;
        }
    }
    prevRenderOpenRef.current = open;
    (0, react_1.useEffect)(() => {
        if (!open) {
            if (prevOpenEffectRef.current) {
                const prev = triggerRef.current;
                triggerRef.current = null;
                if (prev && document.contains(prev) && !document.querySelector('[role="dialog"]')) {
                    prev.focus();
                }
            }
            prevOpenEffectRef.current = false;
            return;
        }
        prevOpenEffectRef.current = true;
        const onKeyDown = (e) => {
            if (e.key !== 'Tab')
                return;
            const root = dialogRef.current || document.querySelector('[role="dialog"]');
            if (!root)
                return;
            const items = Array.from(root.querySelectorAll(FOCUSABLE_SELECTOR)).filter((el) => el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
            if (items.length === 0)
                return;
            const first = items[0];
            const last = items[items.length - 1];
            const active = document.activeElement;
            if (e.shiftKey) {
                if (!active || !root.contains(active) || active === first) {
                    e.preventDefault();
                    last.focus();
                }
            }
            else {
                if (!active || !root.contains(active) || active === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        };
        window.addEventListener('keydown', onKeyDown, true);
        return () => {
            window.removeEventListener('keydown', onKeyDown, true);
        };
    }, [open]);
    return dialogRef;
}
function handleSelectableKeyDown(e, onSelect) {
    if (e.target !== e.currentTarget)
        return;
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect();
    }
}

  };

  moduleFactories["utils/orderExport"] = function(exports, module, require) {
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildOrderCsv = buildOrderCsv;
exports.buildProcurementMemo = buildProcurementMemo;
exports.triggerBrowserCsvDownload = triggerBrowserCsvDownload;
const presets_1 = require("../data/presets");
const flowNetwork_1 = require("../data/flowNetwork");
const replenishmentEngine_1 = require("../store/replenishmentEngine");
function escapeCsvCell(val) {
    const s = String(val);
    if (s.includes(';') || s.includes('"') || s.includes('\n')) {
        return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
}
function buildOrderCsv(state) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const header = [
        'Позиция',
        'Категория',
        'Поставщик',
        'Партия_шт',
        'Паллеты',
        'Масса_кг',
        'Сумма_тыс_руб',
        'Срок_дней'
    ].join(';');
    const rows = state.items.map((item) => {
        const sup = (0, presets_1.getSupplier)(item.supplierId);
        const pallets = (0, replenishmentEngine_1.computeItemPallets)(item);
        const weight = (0, replenishmentEngine_1.computeItemWeightKg)(item);
        const cost = (0, replenishmentEngine_1.computeItemCostKrub)(item, state.backupChannel);
        const lead = (0, replenishmentEngine_1.computeEffectiveLeadDays)(item, state.transitDelayDays, state.backupChannel);
        return [
            escapeCsvCell(item.name),
            escapeCsvCell(item.category),
            escapeCsvCell(sup.name),
            item.orderQty,
            pallets.toFixed(1),
            weight,
            cost.toFixed(1),
            lead
        ].join(';');
    });
    const footer = [
        'ИТОГО ПО ВОЛНЕ',
        escapeCsvCell(state.waveLabel),
        escapeCsvCell(presets_1.BACKUP_CHANNELS[state.backupChannel].label),
        state.items.reduce((acc, i) => acc + i.orderQty, 0),
        summary.totalPallets.toFixed(1),
        summary.totalWeightKg,
        summary.totalBudgetKrub.toFixed(1),
        summary.avgLeadDays.toFixed(1)
    ].join(';');
    return [header, ...rows, footer].join('\n');
}
function resolveErpReadinessLine(summary) {
    if (summary.isFeasible) {
        return 'Готовность пакета для OData 1C:ERP / SAP MM: ДА — заказ в лимитах, статус APPROVED';
    }
    if (summary.overLimitCount > 0) {
        return 'Готовность пакета для OData 1C:ERP / SAP MM: НЕТ — превышен лимит приемки РЦ';
    }
    return `Готовность пакета для OData 1C:ERP / SAP MM: ВНИМАНИЕ — габариты в норме, требуется закрытие дефицита (${summary.stockoutRiskCount} поз.)`;
}
function buildProcurementMemo(state) {
    const summary = (0, replenishmentEngine_1.computeOrderSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    const channel = presets_1.BACKUP_CHANNELS[state.backupChannel];
    let statusLine = 'Статус: Заказ уложен в габаритный лимит склада и страховой запас';
    if (!summary.isFeasible) {
        statusLine =
            summary.overLimitCount > 0
                ? `Статус: Требуется укладка: превышений лимита ${summary.overLimitCount}, риск дефицита ${summary.stockoutRiskCount}`
                : `Статус: Габариты в допуске, риск дефицита по ${summary.stockoutRiskCount} поз.`;
    }
    const net = (0, flowNetwork_1.computeSupplyNetwork)(state);
    const lines = [
        `ПОЯСНИТЕЛЬНАЯ ЗАПИСКА К ЗАКУПКЕ – ${state.waveLabel}`,
        statusLine,
        `Склад приемки: ${summary.totalPallets.toFixed(1)} из ${summary.effectivePalletLimit} паллет, ${summary.totalWeightKg} из ${state.constraints.maxWeightKg} кг`,
        `Бюджет волны: ${summary.totalBudgetKrub.toFixed(1)} из ${state.constraints.maxBudgetKrub} тыс. ₽ | Канал: ${channel.label}`,
        `Отгрузки заказчикам: ${net.readyCustomersCount} из ${net.outbound.length} в графике (${net.outboundPallets.toFixed(1)} паллет, ${net.outboundValueKrub.toFixed(0)} тыс. ₽)`,
        '--- Состав заказа по позициям ---'
    ];
    for (const item of state.items) {
        const sup = (0, presets_1.getSupplier)(item.supplierId);
        const pallets = (0, replenishmentEngine_1.computeItemPallets)(item);
        const cost = (0, replenishmentEngine_1.computeItemCostKrub)(item, state.backupChannel);
        const lead = (0, replenishmentEngine_1.computeEffectiveLeadDays)(item, state.transitDelayDays, state.backupChannel);
        lines.push(`- ${item.name}: ${item.orderQty} шт., ${pallets.toFixed(1)} паллет, ${cost.toFixed(1)} тыс. ₽ (${sup.name}, ${lead} дн.)`);
    }
    const waveFin = (0, replenishmentEngine_1.computeWaveFinancialSummary)(state.items, state.constraints, state.transitDelayDays, state.backupChannel);
    lines.push('--- P&L и стохастический аудит волны ---');
    lines.push(`WMS дискретные слоты рампы: ${waveFin.discreteRampSlots} слот. (float: ${waveFin.floatPallets.toFixed(1)} паллет.)`);
    lines.push(`Совокупный остаточный риск бездействия: ${Math.round(waveFin.totalCostOfInactionKrub)} тыс. ₽`);
    lines.push(`Оборотный капитал волны: ${waveFin.workingCapitalKrub.toFixed(1)} тыс. ₽ | ТСО волны: ${waveFin.tcoWaveKrub.toFixed(1)} тыс. ₽`);
    lines.push(`Расчетная экономия ОК за год: ${waveFin.estAnnualWcSavingsKrub.toFixed(1)} тыс. ₽/год`);
    lines.push(resolveErpReadinessLine(summary));
    return lines.join('\n');
}
function triggerBrowserCsvDownload(filename, csvPayload) {
    if (typeof document === 'undefined' || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
        return false;
    }
    try {
        const blob = new Blob([csvPayload], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        return true;
    }
    catch (err) {
        if (err instanceof Error)
            return false;
        return false;
    }
}

  };

  function normalizePath(fromDir, reqPath) {
    const parts = (fromDir ? fromDir.split('/') : []).concat(reqPath.split('/'));
    const resolved = [];
    for (const part of parts) {
      if (!part || part === '.') continue;
      if (part === '..') resolved.pop();
      else resolved.push(part);
    }
    return resolved.join('/').replace(/\.(?:tsx|ts|jsx|js)$/, '');
  }

  function loadModule(modId) {
    if (moduleCache[modId]) return moduleCache[modId].exports;
    const factory =
      moduleFactories[modId] ||
      moduleFactories[modId + '/index'];
    if (!factory) {
      throw new Error('Module not found in sandbox bundle: ' + modId);
    }
    const resolvedId = moduleFactories[modId] ? modId : modId + '/index';
    const mod = { exports: {} };
    moduleCache[resolvedId] = mod;
    const fromDir = resolvedId.includes('/') ? resolvedId.slice(0, resolvedId.lastIndexOf('/')) : '';

    const localRequire = (reqName) => {
      if (reqName === 'react') return { __esModule: true, default: React, ...React };
      if (reqName === 'react-dom/client' || reqName === 'react-dom') {
        return { __esModule: true, createRoot: () => ({ render: () => {}, unmount: () => {} }) };
      }
      if (reqName.endsWith('ux-spec.json')) return { __esModule: true, default: uxSpecData, ...uxSpecData };
      if (reqName.endsWith('.css')) return {};
      if (reqName.startsWith('.')) {
        const targetId = normalizePath(fromDir, reqName);
        if (moduleFactories[targetId] || moduleFactories[targetId + '/index']) {
          return loadModule(targetId);
        }
      }
      // Fallback suffix match for non-relative local aliases
      const cleanAlias = reqName.replace(/^@\//, '').replace(/\.(?:tsx|ts|jsx|js)$/, '');
      if (moduleFactories[cleanAlias]) return loadModule(cleanAlias);
      for (const key of Object.keys(moduleFactories)) {
        if (key.endsWith('/' + cleanAlias) || key === cleanAlias) {
          return loadModule(key);
        }
      }
      return {};
    };

    factory(mod.exports, mod, localRequire);
    return mod.exports;
  }

  const entryExports = loadModule("App");
  const AppComponent = entryExports.default || entryExports.App || Object.values(entryExports)[0];
  const rootEl = document.getElementById('root');
  React.mount(AppComponent, rootEl);
})();
