import { BACKUP_CHANNELS, getSupplier } from '../data/presets';
import { computeSupplyNetwork } from '../data/flowNetwork';
import {
  computeEffectiveLeadDays,
  computeItemCostKrub,
  computeItemPallets,
  computeItemWeightKg,
  computeOrderSummary,
  computeWaveFinancialSummary
} from '../store/replenishmentEngine';
import type { InventoryDomainState } from '../types/domain';

function escapeCsvCell(val: string | number): string {
  const s = String(val);
  if (s.includes(';') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function buildOrderCsv(state: InventoryDomainState): string {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
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
    const sup = getSupplier(item.supplierId);
    const pallets = computeItemPallets(item);
    const weight = computeItemWeightKg(item);
    const cost = computeItemCostKrub(item, state.backupChannel);
    const lead = computeEffectiveLeadDays(item, state.transitDelayDays, state.backupChannel);
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
    escapeCsvCell(BACKUP_CHANNELS[state.backupChannel].label),
    state.items.reduce((acc, i) => acc + i.orderQty, 0),
    summary.totalPallets.toFixed(1),
    summary.totalWeightKg,
    summary.totalBudgetKrub.toFixed(1),
    summary.avgLeadDays.toFixed(1)
  ].join(';');

  return [header, ...rows, footer].join('\n');
}

function resolveErpReadinessLine(summary: ReturnType<typeof computeOrderSummary>): string {
  if (summary.isFeasible) {
    return 'Готовность пакета для OData 1C:ERP / SAP MM: ДА — заказ в лимитах, статус APPROVED';
  }
  if (summary.overLimitCount > 0) {
    return 'Готовность пакета для OData 1C:ERP / SAP MM: НЕТ — превышен лимит приемки РЦ';
  }
  return `Готовность пакета для OData 1C:ERP / SAP MM: ВНИМАНИЕ — габариты в норме, требуется закрытие дефицита (${summary.stockoutRiskCount} поз.)`;
}

export function buildProcurementMemo(state: InventoryDomainState): string {
  const summary = computeOrderSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  const channel = BACKUP_CHANNELS[state.backupChannel];
  let statusLine = 'Статус: Заказ уложен в габаритный лимит склада и страховой запас';
  if (!summary.isFeasible) {
    statusLine =
      summary.overLimitCount > 0
        ? `Статус: Требуется укладка: превышений лимита ${summary.overLimitCount}, риск дефицита ${summary.stockoutRiskCount}`
        : `Статус: Габариты в допуске, риск дефицита по ${summary.stockoutRiskCount} поз.`;
  }

  const net = computeSupplyNetwork(state);
  const lines: string[] = [
    `ПОЯСНИТЕЛЬНАЯ ЗАПИСКА К ЗАКУПКЕ – ${state.waveLabel}`,
    statusLine,
    `Склад приемки: ${summary.totalPallets.toFixed(1)} из ${summary.effectivePalletLimit} паллет, ${summary.totalWeightKg} из ${state.constraints.maxWeightKg} кг`,
    `Бюджет волны: ${summary.totalBudgetKrub.toFixed(1)} из ${state.constraints.maxBudgetKrub} тыс. ₽ | Канал: ${channel.label}`,
    `Отгрузки заказчикам: ${net.readyCustomersCount} из ${net.outbound.length} в графике (${net.outboundPallets.toFixed(1)} паллет, ${net.outboundValueKrub.toFixed(0)} тыс. ₽)`,
    '--- Состав заказа по позициям ---'
  ];

  for (const item of state.items) {
    const sup = getSupplier(item.supplierId);
    const pallets = computeItemPallets(item);
    const cost = computeItemCostKrub(item, state.backupChannel);
    const lead = computeEffectiveLeadDays(item, state.transitDelayDays, state.backupChannel);
    lines.push(
      `- ${item.name}: ${item.orderQty} шт., ${pallets.toFixed(1)} паллет, ${cost.toFixed(1)} тыс. ₽ (${sup.name}, ${lead} дн.)`
    );
  }

  const waveFin = computeWaveFinancialSummary(
    state.items,
    state.constraints,
    state.transitDelayDays,
    state.backupChannel
  );
  lines.push('--- P&L и стохастический аудит волны ---');
  lines.push(`WMS дискретные слоты рампы: ${waveFin.discreteRampSlots} слот. (float: ${waveFin.floatPallets.toFixed(1)} паллет.)`);
  lines.push(`Совокупный остаточный риск бездействия: ${Math.round(waveFin.totalCostOfInactionKrub)} тыс. ₽`);
  lines.push(`Оборотный капитал волны: ${waveFin.workingCapitalKrub.toFixed(1)} тыс. ₽ | ТСО волны: ${waveFin.tcoWaveKrub.toFixed(1)} тыс. ₽`);
  lines.push(`Расчетная экономия ОК за год: ${waveFin.estAnnualWcSavingsKrub.toFixed(1)} тыс. ₽/год`);
  lines.push(resolveErpReadinessLine(summary));

  return lines.join('\n');
}

export function triggerBrowserCsvDownload(filename: string, csvPayload: string): boolean {
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
  } catch (err: unknown) {
    if (err instanceof Error) return false;
    return false;
  }
}
