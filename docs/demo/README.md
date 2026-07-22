# 栖纳家居 Demo 数据集

此目录是 EcomAgent P0 的开发与回归固定输入，不含真实品牌、公开页面图片或复制文案。

- `products.json`：三款居家收纳商品及 SKU、成本拆分、规则与 Demo 图片提示词。
- `field_dictionary.md`：字段来源、强事实与可生成范围。
- `qa_gold.json` 与 `qa_gold_addendum.json`：合计 50 条商品问答金标集。
- `red_team.json` 与 `red_team_addendum.json`：合计 30 条风险与拒答测试题。

所有页面与导入流程必须展示 `data_scope=demo`。Demo 价格、库存、成本和订单状态均不得对外表达为实时商家数据。
