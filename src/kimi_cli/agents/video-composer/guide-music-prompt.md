# Music Prompt 编写规范

> 为每首 BGM 主题曲编写 GenerateMusic 的 prompt 时，参考本文件。

## 基本规则

1. **英文编写**：所有 prompt 用英文
2. **300 字符限制**：Suno API 硬限制，超出会被截断
3. **纯器乐**：make_instrumental=true，不需要歌词描述
4. **描述音乐本身**：不要描述画面内容，只描述要听到什么

## Prompt 结构

按优先级组合以下要素（总字符不超过 300）：

1. **情绪/氛围**（必须）：warm, tense, mysterious, joyful, melancholic, epic, playful, ominous...
2. **乐器**（推荐）：acoustic guitar, piano, strings, orchestra, flute, percussion, synth...
3. **风格/流派**（推荐）：cinematic, folk, ambient, classical, jazz, electronic...
4. **节奏/速度**（可选）：slow tempo, upbeat, moderate pace, building intensity...
5. **质感描述**（可选）：soft, delicate, powerful, ethereal, gritty...

## 从视觉风格推断音乐方向

| 视觉风格关键词 | 音乐方向 |
|----------------|---------|
| children's storybook / illustration | whimsical, playful, acoustic instruments, folk |
| cinematic / epic | orchestral, sweeping strings, cinematic |
| anime / cartoon | J-pop influenced, energetic, synth + acoustic |
| watercolor / pastoral | gentle, pastoral, flute, harp, ambient |
| dark / horror | dissonant, tension, minor key, sparse |
| cyberpunk / sci-fi | electronic, synth, ambient, industrial |
| vintage / retro | jazz, lo-fi, warm analog |

## 主题曲 Prompt 写法

主题曲会在多个场景中复用，prompt 应描述**通用氛围和风格**，不绑定具体事件情节。

<example>
| 主题曲定位 | 英文 Music Prompt |
|-----------|------------------|
| 温暖日常主题（贯穿全片的主基调） | Warm whimsical folk, acoustic guitar arpeggios, soft glockenspiel, gentle flute, cozy and tender, moderate tempo, cinematic cartoon underscore |
| 紧张/悬疑主题（冲突与挑战段落） | Cautious tension, low pizzicato strings, soft hand percussion, muted woodwinds, steady pulse, cinematic underscore, understated and building |
| 欢快冒险主题 | Bright upbeat orchestral, adventurous and cheerful, woodwinds and strings, moderate tempo, playful and energetic |
| 史诗/高潮主题 | Epic orchestral, powerful brass and percussion, soaring strings, triumphant, building intensity |
| 安静/留白 | 不生成（标记为 silence，由编排决定静默区间） |
</example>

## 从中文情绪描述翻译

<example>
| 中文描述 | 英文 Music Prompt |
|---------|------------------|
| 轻柔的木吉他指弹，温馨家庭氛围 | Gentle acoustic fingerstyle guitar, warm and cozy family atmosphere, soft folk melody |
| 紧张的弦乐震音，危险逼近 | Tense tremolo strings, rising suspense, dark orchestral, danger approaching |
| 诡异的音乐盒旋律 | Eerie music box melody, unsettling, detuned, slow tempo, creepy nursery rhyme |
</example>

## 写作技巧

1. **用形容词堆叠而非句子**：`"warm gentle acoustic guitar folk melody"` 优于 `"a warm and gentle melody played on acoustic guitar in folk style"`
2. **避免叙事**：不要写 `"music that plays when the hero enters"` — 只写音乐特征
3. **避免否定**：不要写 `"no drums, not loud"` — 只写想要的
4. **具体乐器优先**：`"fingerstyle acoustic guitar"` 优于 `"string instrument"`
5. **情绪词放前面**：Suno 对 prompt 开头的权重更高

## 长度控制

<example>
如果初始 prompt 超过 300 字符，按优先级删减：
1. 删除质感描述
2. 简化乐器列表（保留最关键的 1-2 个）
3. 合并同义形容词
4. 最后手段：删除节奏/速度描述
</example>
