import type { ScenarioPreset, SkuItem } from '../types/domain';

function makeSku(
  id: string,
  name: string,
  category: string,
  currentStock: number,
  dailyDemand: number,
  reorderPoint: number,
  safetyDays: number,
  orderQty: number,
  unitCostKrub: number,
  unitWeightKg: number,
  unitsPerPallet: number,
  supplierId: SkuItem['supplierId'],
  priority: SkuItem['priority']
): SkuItem {
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

export const SCENARIO_PRESETS: ScenarioPreset[] = [
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
