# 视觉设计与参考图生成

## 输入

调用方通过 prompt 传入项目路径，并通过 context_files 注入以下文件：
- `meta.json` — style_prefix、negative_prefix、aspect_ratio
- `entities.json` — 角色/场景/道具的基础定义（fixed_traits、description）
- `states.json` — 状态节点清单（CharacterAppearance 的 visual、LocationState 的 lighting/atmosphere 等）

## 步骤

### Step 1: 建立视觉基准

读取 meta.json，提取：
- `style.style_prefix` — 全局正向风格（如 "hand-drawn illustration, warm color palette"）
- `style.negative_prefix` — 全局排除风格（如 "photorealistic, dark, horror"）

这两个值贯穿所有图片生成，确保风格统一。

### Step 2: 第 1 层 — 实体参考图

为每个实体设计视觉方案并生成一张身份锚点图。

#### 角色（Character）

对每个角色：
1. 读取 fixed_traits（如 age、hair、signature_look）
2. 基于 fixed_traits 和全局风格，设计完整的视觉方案：
   - 补充 fixed_traits 未指定的细节（肤色、体型、服装材质、配饰等）
   - 确保设计与风格一致（手绘风就不要写真实皮肤纹理）
   - 确保不同角色之间有足够的视觉区分度
3. 组装 prompt，生成图片：
   - 构图：全身正面，从头到脚完整可见，居中
   - 背景：纯白背景
   - 比例：1:1
   - 路径：`{project_path}/assets/images/{character_id}.png`
4. 用 ReadMediaFile 查看生成结果，检查：
   - 角色特征是否与设计一致（服装颜色、发型、体型）
   - 全身是否完整可见（不截断）
   - 风格是否与 style_prefix 一致
5. 不满意则调整 prompt 重新生成，最多重试 2 次

#### 场景（Location）

对每个场景：
1. 读取 description
2. 设计视觉方案：补充光照、色调、空间纵深等细节
3. 组装 prompt，生成图片：
   - 构图：纯环境，无角色
   - 比例：1:1
   - 路径：`{project_path}/assets/images/{location_id}.png`
4. 审查并迭代

#### 道具（Prop）

只为剧情关键道具生成。对每个需要生成的道具：
1. 读取 description
2. 设计视觉方案
3. 组装 prompt，生成图片：
   - 构图：白底特写
   - 比例：1:1
   - 路径：`{project_path}/assets/images/{prop_id}.png`
4. 审查并迭代

**并行策略**：每批最多并行 3 个 GenerateImage 调用。按 角色 → 场景 → 道具 的优先级排列。

### Step 3: 第 2 层 — 状态参考图

基于第 1 层的实体图，为有视觉差异的状态生成派生图。

#### 去重判断

逐个状态检查是否需要生成新图：
- 该实体只有一个状态，且视觉描述与实体基础描述无实质差异 → **跳过**，reference_image 直接指向实体图
- 状态描述有明确的视觉变化（换装、受伤、光照变化等） → **需要生成**

#### 生成

对每个需要生成的状态：
1. 读取状态的视觉描述（CharacterAppearance 的 visual、LocationState 的 lighting/atmosphere 等）
2. 确定对应的实体基础图路径：`{project_path}/assets/images/{entity_id}.png`（Step 2 已生成）
3. 基于描述和全局风格，设计该状态的视觉方案：
   - 与实体基础图保持一致的基础特征
   - 突出状态变化的视觉差异
4. 调用 GenerateImage，**必须传入以下参数**：
   - `prompt`: 按 guide-prompt.md 组装（style_prefix 在 prompt 开头）
   - `reference_image_paths`: **必须传入对应实体基础图路径**，如 `["{project_path}/assets/images/loc_farm_yard.png"]`（lstate → loc 图），`["{project_path}/assets/images/char_pony.png"]`（appear → char 图）。这是保证状态图与实体图视觉风格一致的关键机制（provider 会将参考图作为视觉输入），**不可省略**
   - `negative_prompt`: 传入 negative_prefix + 通用排除项
   - `output_path`: `{project_path}/assets/images/{state_id}.png`
5. 用 ReadMediaFile 审查：
   - 与实体图的角色/场景是否一致（不能变成另一个人/地方）
   - 状态变化是否体现（换装后衣服确实变了）
   - 风格是否统一
6. 不满意则调整，最多重试 2 次

### Step 4: 写回结果

#### 4a. 更新 entities.json

读取当前 `{project_path}/entities.json`，为每个生成了图片的实体（角色、场景、道具）添加 `reference_image` 字段：

- 生成成功：绝对路径指向 `{project_path}/assets/images/{entity_id}.png`
- 生成失败：null

用 WriteFile 写回 entities.json。

#### 4b. 更新 states.json

读取当前 `{project_path}/states.json`，为 `character_appearances`、`location_states`、`prop_states` 中的状态节点添加 `reference_image` 字段：

- 生成成功的状态：绝对路径指向图片文件
- 去重跳过的状态：绝对路径指向对应实体图
- 生成失败的状态：null

用 WriteFile 写回 states.json。

### Step 5: 汇报

向调用方报告：
- 生成成功的数量（实体图 + 状态图）
- 跳过的数量（去重）
- 失败的数量及失败原因
- 每个失败项的 ID

## 输出

- `{project_path}/assets/images/` 下的参考图文件
- 更新后的 `entities.json`（每个实体增加 reference_image 字段）
- 更新后的 `states.json`（每个状态节点增加 reference_image 字段）

## 错误处理

- **GenerateImage 失败**：调整 prompt 重试 1 次。仍失败则记录失败，继续处理下一个。
- **ReadMediaFile 失败**：跳过审查，保留当前图片。
- **states.json 写回失败**：重试 1 次，仍失败则报告调用方。
- **所有图片都失败**：停止执行，报告调用方。
