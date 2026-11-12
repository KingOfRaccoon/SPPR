import type {
  OutboundDestinationId,
  SelectedMapNodeId,
  SupplierId
} from '../types/domain';

export interface GeoPointMeta {
  id: SelectedMapNodeId;
  kind: 'supplier' | 'hub' | 'customer';
  city: string;
  title: string;
  coordsLabel: string;
  highwayLabel: string;
  distanceKm: number;
  gateLabel: string;
  x: number;
  y: number;
  labelAnchor: 'start' | 'middle' | 'end';
  labelDx: number;
  labelDy: number;
}

export const CENTRAL_HUB_META: GeoPointMeta = {
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

export const SUPPLIER_GEO: Record<SupplierId, GeoPointMeta> = {
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

export interface OutboundCustomerSpec {
  id: OutboundDestinationId;
  geo: GeoPointMeta;
  customerName: string;
  contractCode: string;
  dispatchWindowDays: number;
  dispatchWindowLabel: string;
  vehicleLabel: string;
  allocations: Array<{
    skuId: string;
    fallbackCategory: string;
    requiredQty: number;
  }>;
}

export const OUTBOUND_SPECS: OutboundCustomerSpec[] = [
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

export const INBOUND_CONTROL_POINTS: Record<SupplierId, [number, number]> = {
  'balt-komplekt': [174, 88],
  'sever-snab': [296, 80],
  'volga-pribor': [404, 66],
  'ural-privod': [488, 28]
};

export const OUTBOUND_CONTROL_POINTS: Record<OutboundDestinationId, [number, number]> = {
  'out-tula': [222, 144],
  'out-nn': [346, 134],
  'out-voronezh': [282, 180],
  'out-samara': [448, 184]
};
