import type { SupplierId } from '../types/domain';

export const SHORT_SUPPLIER_NAMES: Record<SupplierId, string> = {
  'balt-komplekt': 'БалтКомплект',
  'ural-privod': 'УралПривод',
  'volga-pribor': 'ВолгаПрибор',
  'sever-snab': 'СеверСнаб'
};

export interface SupplierContractTerms {
  incoterms: string;
  deferralDays: number;
  moqStepQty: number;
  slaPenaltyPct: string;
  leadVariance: string;
  packaging: string;
}

export const SUPPLIER_CONTRACT_TERMS: Record<SupplierId, SupplierContractTerms> = {
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
