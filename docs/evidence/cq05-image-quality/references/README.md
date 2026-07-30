# C-Q05 原创参考图执行记录

> 执行日期：2026-07-29
> 状态：三张参考图已通过产品负责人复核；第 1 次真实 Qwen 调用失败后按规则停止。

## 授权与来源说明

参考图由项目负责人明确要求为本项目 C-Q05 人工验收生成。`ZN-SB-001` 使用
Codex 内置 ImageGen 从零生成；`ZN-DB-002` 与 `ZN-VB-003` 由项目负责人使用
“ChatGPT Web 内置图像生成”手动生成并放入证据目录。未复制公开品牌图片、品牌名、
品牌文案或包装；提示词明确禁止人物、商标、水印、品牌名、包装文字和无关文字。
生成图仅用于本项目内部验收证据。

## ZN-SB-001

- 文件：`ZN-SB-001-reference.png`
- 生成方式：Codex 内置 ImageGen，`product-mockup`
- SHA-256：`FCFBD70C99CB21561BBCA1349B368FF02D669805DE12567AE39BC8F506CF1BF4`
- 文件格式/尺寸：PNG，1254×1254，2,184,678 bytes
- 完整性：Pillow decode、`verify()`、重新打开并 `load()` 全部通过
- 人物/商标/水印/文字：目视未发现

完整提示词：

```text
Use case: product-mockup
Asset type: original authorized reference image for an internal ecommerce image-editing acceptance test
Primary request: create a completely original photorealistic catalog reference image of one foldable fabric clothing storage box
Scene/backdrop: seamless warm-white studio background with a subtle neutral floor, no room scene
Subject: a single rectangular beige/off-white thick nonwoven fabric storage box, closed structured lid, two-way zipper detail, one large clear PVC viewing window on the front showing neatly folded pale neutral sweaters; practical generic construction, no resemblance to any known branded product
Style/medium: realistic product photography, physically plausible materials and stitching
Composition/framing: three-quarter 45-degree front view, centered, whole object visible with generous padding, square image
Lighting/mood: soft diffused studio light, natural shadow, factual catalog mood
Constraints: no person, no hands, no logo, no trademark, no brand name, no packaging, no label, no watermark, no text, no unrelated objects
Avoid: promotional copy, decorative typography, distorted zippers, impossible geometry, duplicate boxes
```

## ZN-DB-002

- 文件：`ZN-DB-002-reference.png`
- 来源：ChatGPT Web 内置图像生成
- SHA-256：`183707A5F50D1706B56C10A58A4DC20B06AB33601CAA9E84A06C613B8C0F8830`
- 文件格式/尺寸：PNG，1254×1254，1,188,682 bytes
- 图像模式：RGB
- 完整性：Pillow decode、`verify()`、重新打开并 `load()` 全部通过
- 人工初检：单个雾白色桌面抽屉收纳盒，半拉开，纯白棚拍背景；未发现人物、品牌、
  Logo、商标、水印、文字、包装、价格或尺寸标注。抽屉和滑轨整体可理解，文具、
  回形针和白色数据线可见。画面分隔视觉上可能形成五个区域，与提示词要求的“四个
  可拆卸大分区”存在潜在偏差，提交产品负责人重点复核，不在本报告中判定通过。

完整提示词：

```text
请生成一张原创的电商商品参考图。
商品：雾白色桌面分格抽屉收纳盒。
材质为哑光 PP 塑料，圆角设计，只有一个完整盒体。
抽屉处于半拉开状态，内部明确分成四个可拆卸的大分区。
分区内放少量无品牌文具、回形针和两根整齐盘好的白色数据线。
使用纯白色无缝电商摄影背景，商品居中完整展示，
采用正面偏45度视角，柔和棚拍光线，保留自然接触阴影，
整体应像真实淘宝商品主图，而不是插画或3D卡通。
必须满足：
1. 不出现人物、手或身体部位。
2. 不出现品牌名、Logo、商标、水印和任何文字。
3. 不出现商品包装、价格标签和尺寸标注。
4. 抽屉、隔板和滑轨结构必须合理。
5. 只展示一个收纳盒，不生成多个重复商品。
6. 不模仿任何现实品牌或现有商品包装。
7. 输出正方形高清图片。
```

## ZN-VB-003

- 文件：`ZN-VB-003-reference.png`
- 来源：ChatGPT Web 内置图像生成
- SHA-256：`61EEB8B33735FBC27241B69AEB41FA72607C00C81B6C49CFAEEE0FD2C12D9A24`
- 文件格式/尺寸：PNG，1254×1254，1,261,786 bytes
- 图像模式：RGB
- 完整性：Pillow decode、`verify()`、重新打开并 `load()` 全部通过
- 版本说明：当前文件是产品负责人复核后的替换版本，不是未经修改的初始版本。
- 人工初检：画面可辨识为前方一个已装衣压缩袋和后方五个空袋，共六个透明收纳袋；
  具有密封边和圆形抽气阀。未发现人物、品牌、Logo、商标、水印、文字、包装、价格、
  尺寸或促销标注，也未出现吸尘器吸嘴或独立抽气泵。
- 替换记录：旧版本因吸尘器吸嘴存在“可能被误解为套装内容”的歧义，被产品负责人
  拒绝并替换。旧版本 SHA-256 保留为
  `C93ED705F0F21777D1D6DA5D5C40707EB7C7994069BBB34DBDA8F532C8CC5B4B`。

完整提示词：

```text
请生成一张原创的电商商品参考图。
商品：六个装透明旅行衣物真空压缩收纳袋。
材质为透明 PA+PE 复合膜，具有合理的双层密封边和圆形抽气阀。
画面中必须能理解这是六个装：
一个透明收纳袋位于前方，内部装有整齐折叠的米白色和浅灰色衣物，
并已经被明显压缩；另外五个空的透明收纳袋折叠整齐排列在后方。
旁边可以放一个无品牌的普通家用吸尘器吸嘴作为使用提示，
但不能出现独立抽气泵，也不能让人误以为吸尘器包含在商品套装中。
使用纯白色无缝电商摄影背景，商品居中完整展示，
采用正面偏45度视角，柔和棚拍光线，
透明薄膜反光自然，密封边和抽气阀结构真实合理。
必须满足：
1. 总共表现六个真空压缩袋。
2. 不出现人物、手或身体部位。
3. 不出现品牌、Logo、商标、水印和任何文字。
4. 不出现包装、价格、尺寸标注和促销标签。
5. 不生成额外的手动抽气泵。
6. 透明袋边缘、密封条和阀门不能明显扭曲。
7. 不模仿任何现实品牌。
8. 输出正方形高清真实商品摄影图。
```

## 中断记录

- `ZN-DB-002` 内置 ImageGen 请求发生网络传输错误；同一请求重试一次后仍失败。
- GitHub 技术基线推送和华北 2 默认 Workspace 配置完成后恢复执行，`ZN-DB-002` 第三次请求仍发生相同网络传输错误，因此再次停止。
- 产品负责人批准稍后仅重试一次后，本轮 `ZN-DB-002` 单次请求仍发生相同网络传输错误；按规则立即暂停，未连续重试。
- 按安全边界未切换到需要额外 Key 的 CLI Provider。
- 后续两张图片由项目负责人通过 ChatGPT Web 内置图像生成手动完成，本次仅核对落盘
  文件、生成记录和完整性，没有再次调用 Codex ImageGen。
- 2026-07-30 获批执行 6 次 `qwen-image-2.0` 真实调用；第 1 次 `ZN-SB-001 / minimal` 返回 `failed`，实际调用 1 次、成功 0 次、重试 0 次，随后立即停止。
- 未产生结果样本或联系表；完整证据见 [`../CQ05执行报告_2026-07-30.md`](../CQ05执行报告_2026-07-30.md)。

## 三张参考图核验结论

| 商品 | 来源 | Pillow decode / verify / reload | 人工初检 |
| --- | --- | --- | --- |
| ZN-SB-001 | Codex 内置 ImageGen | PASS / PASS / PASS | 未发现人物、商标、水印或文字 |
| ZN-DB-002 | ChatGPT Web 内置图像生成 | PASS / PASS / PASS | 产品负责人复核通过 |
| ZN-VB-003 | ChatGPT Web 内置图像生成（替换版本） | PASS / PASS / PASS | 产品负责人复核通过；旧版因吸尘器吸嘴歧义被拒绝 |

三张当前参考图均已落盘、通过 Pillow 完整性核验并通过产品负责人复核。真实调用
已在第 1 次失败后依规则停止，未生成可供逐图复核的结果，因此 `C-Q05` 继续保持
`BLOCKED`，不得标记为 `PASS`。

## 发布与配置前置状态

- Public 仓库 `Hmx-7488/EcomAgent` 的远端 `main` 与本地技术基线 `0b63bcef7c79493b7ded4678d8f044d989e5d923` 一致。
- 百炼控制台确认地域为华北 2（北京），当前默认 Workspace 唯一。
- 本机 `backend/.env` 已切换到该 Workspace 专属 HTTPS API Host；Key 存在且配置替换前后未改变。本文档不记录 Key、Workspace ID 或完整地址。
