# C-Q05 正式质量样本

本目录保存 C-Q05 最终人工验收的 18 张真实 Qwen 结果图。所有文件均从运行结果按字节
原样复制，没有编辑或重新编码；复制后必须以
[`../CQ05最终验收报告_2026-07-31.md`](../CQ05最终验收报告_2026-07-31.md)
记录的 SHA-256 复验。

| 商品 | 场景 | Task | Result Asset | 目录 | 数量 |
| --- | --- | ---: | --- | --- | ---: |
| `ZN-SB-001` | minimal | 6 | 10、11、12 | `product-01/minimal/` | 3 |
| `ZN-SB-001` | home | 7 | 15、16、17 | `product-01/home/` | 3 |
| `ZN-DB-002` | minimal | 8 | 18、19、20 | `product-02/minimal/` | 3 |
| `ZN-DB-002` | home | 9 | 21、22、23 | `product-02/home/` | 3 |
| `ZN-VB-003` | minimal | 10 | 24、25、26 | `product-03/minimal/` | 3 |
| `ZN-VB-003` | home | 11 | 27、28、29 | `product-03/home/` | 3 |

样本要求：

- 精确 18 张 PNG。
- 每张为 RGB、1024×1024。
- 每个场景精确 3 张。
- 使用运行时不透明文件名。
- 不保存 Provider 临时 URL、请求体、Base64 或敏感配置。
- 参考图继续保存在 [`../references/`](../references/) 中，不在本目录重复复制。
- Asset 27、28 的包装数量表达为非阻塞观察项，详见最终验收报告。

此目录不得放入离线 fixture、占位图或测试 PNG。
