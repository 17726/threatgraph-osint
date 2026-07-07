export interface EvalMetrics {
  entity_precision: number;
  entity_recall: number;
  entity_f1: number;
  relation_precision: number;
  relation_recall: number;
  relation_f1: number;
  test_docs: number;
  test_entities: number;
  test_relations: number;
  errors: { type: string; description: string }[];
}

export const MOCK_EVAL: EvalMetrics = {
  entity_precision: 0.87,
  entity_recall: 0.82,
  entity_f1: 0.84,
  relation_precision: 0.79,
  relation_recall: 0.71,
  relation_f1: 0.75,
  test_docs: 5,
  test_entities: 45,
  test_relations: 30,
  errors: [
    { type: "漏标", description: "APT28 的别名 Sednit 未被识别" },
    { type: "误标", description: "将 CVE-2021-44228 错误关联到 Lazarus" },
    { type: "关系缺失", description: "APT28 使用 LameHug 的关系未正确抽取" },
  ],
};
