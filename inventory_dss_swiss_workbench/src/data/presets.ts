import { SCENARIO_PRESETS } from './scenarioPresets';
import type {
  BackupChannelInfo,
  BackupChannelMode,
  ScreenId,
  SupplierId,
  SupplierOption
} from '../types/domain';

export { SCENARIO_PRESETS };

export const SCREEN_DEFINITIONS: Array<{
  id: ScreenId;
  label: string;
  shortLabel: string;
  shortcut: string;
}> = [
  { id: 'screen-replenishment-notebook', label: 'Ведомость заказа', shortLabel: 'Заказ', shortcut: 'Alt+1' },
  { id: 'screen-supply-map', label: 'Карта потоков', shortLabel: 'Карта', shortcut: 'Alt+2' },
  { id: 'screen-warehouse-limits', label: 'Габариты склада', shortLabel: 'Склад', shortcut: 'Alt+3' },
  { id: 'screen-supplier-choice', label: 'Поставщики', shortLabel: 'Базы', shortcut: 'Alt+4' },
  { id: 'screen-delivery-buffer', label: 'Страховой буфер', shortLabel: 'Буфер', shortcut: 'Alt+5' },
  { id: 'screen-order-export', label: 'Спецификация CSV', shortLabel: 'Файл', shortcut: 'Alt+6' }
];

export const SUPPLIERS: Record<SupplierId, SupplierOption> = {
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

export function getSupplier(supplierId: SupplierId): SupplierOption {
  return SUPPLIERS[supplierId] || SUPPLIERS['balt-komplekt'];
}

export function getSupplierBatchStep(supplierId: SupplierId): number {
  return Math.max(10, getSupplier(supplierId).minBatchQty || 10);
}

export const SUPPLIER_LIST: SupplierOption[] = [
  SUPPLIERS['balt-komplekt'],
  SUPPLIERS['ural-privod'],
  SUPPLIERS['volga-pribor'],
  SUPPLIERS['sever-snab']
];

export const BACKUP_CHANNELS: Record<BackupChannelMode, BackupChannelInfo> = {
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
