# extract-v1 (基线)

## 说明

extract-v1 是最初版本，没有 prior version。包含基础的 26 条规则和 entity/relation 类型白名单。

## 评测结果 (deepseek-v4-flash)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_080 | 0.4151 | 0.2667 |

## 基线问题

- 5 条 DISCOVERED_BY 假阳性（如 Unit 42 DISCOVERED_BY Sofacy）
- 3 条 CONTROLS 假阳性（如 Palo Alto Networks CONTROLS WildFire）
- TOOL recall=0.11, TECHNIQUE recall=0.20（文档后半部分被遗漏）
