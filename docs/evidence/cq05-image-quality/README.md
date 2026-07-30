# C-Q05 图片质量人工验收计划

状态：`BLOCKED`。2026-07-30 获批执行六次真实调用后，第 1 次
`ZN-SB-001 / minimal` 返回 `failed`，已按规则立即停止且未重试。实际调用
1 次、成功 0 次、结果图 0 张；`samples/` 中仍没有测试图、占位图或质量样本。

执行证据见
[`CQ05执行报告_2026-07-30.md`](CQ05执行报告_2026-07-30.md)。

## 已批准方案与本轮中止状态

- 对象：`docs/demo/products.json` 中 3 个“栖纳家居”商品。
- 前置条件：每个商品提供 1 张来源清晰、允许用于验收的真实参考图。
- 场景：每个商品分别生成 `minimal`、`home` 两种场景。
- 当前适配器每次请求 `n=3`，因此计划为 6 次真实 API 调用、18 张图片。
- 不自动重试。失败调用或补充样本需重新报告，不从本次 6 次预算中静默扩张。
- 华北 2（北京）`qwen-image-2.0` 官方原价为 0.20 元/成功图片，18 张上限
  预计 3.60 元；免费额度或控制台优惠可能降低实付金额，最终以账单为准。
- 本轮已获得六次调用授权，但第 1 次失败后停止；后续调用或重试需要新的明确指令。

官方依据：

- https://help.aliyun.com/zh/model-studio/qwen-image-2-0
- https://help.aliyun.com/zh/model-studio/qwen-image-edit-api
- https://help.aliyun.com/zh/model-studio/text-to-image

## 样本目录约定

批准并生成后才创建图片文件：

```text
samples/
  product-01/
    reference/
    minimal/
    home/
  product-02/
    reference/
    minimal/
    home/
  product-03/
    reference/
    minimal/
    home/
```

每个结果文件必须已通过项目统一的 Pillow `decode -> verify -> reload`
完整性校验，并使用本地不透明文件名。临时 Provider URL 不作为样本证据。

验收人按 [人工验收清单](checklist.md) 逐张记录，不接受仅看缩略图的结论。
