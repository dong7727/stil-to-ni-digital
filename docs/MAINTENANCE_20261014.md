# STIL → NI-Digital v0.4.0 维护说明

日期：2026-10-14。依据用户提供的《P2506 STIL → NI-Digital 转换问题总结与脚本维护分析》维护当前仓库的直接 STIL 转换器。原报告描述的 CHROMA 转换器及历史交付目录未修改。

## 修复结果

| 范围 | 原实现的问题 | v0.4.0 行为 |
| --- | --- | --- |
| PWD / 测试模式入口 | 没有独立的 NRST 项目覆盖 | 显式 P2506 配置校验源 SHA-256、宏实例、周期范围、原值及 `pattern_0` 边界，只把初始化 186 周期的 NRST 从 X 改为 0 |
| 多链短链补位 | ScanIn 前补复制第一个有效位，非 0/1 缺省被强制为 0；ScanOut 后补统一 X | 根据首次占位符前的条件/向量上下文取补位值，输入前补、输出后补；缺失整个参数时保持上下文 |
| capture Fixed | F 被当成一次普通赋值，后续组赋值覆盖 PA1 | F 约束独立保存，默认冲突报错；P2506 显式选择保留 Fixed，并记录冲突周期、过程实例、源行、组名及原/新值 |
| T / 波形解释 | 统一 T→V；全局比较时刻和脉冲边沿 | 按 WFT、引脚和事件解释；比较 T 需显式策略映射为 M，比较 V 才生成 V；不同 WFT 可保留不同边沿 |
| NI 紧凑格式 | 正确的 X 补位不能直接写入 NI scan 输入串 | 把不可表示的周期拆成普通向量，其余段继续使用 scan；不增加周期或移动串行数据 |
| 验证追溯 | 生成和编译缺乏完整绑定 | 每次写入空目录，输出 manifest、诊断、宏时间轴；官方编译后自动反编译并检查完整源语义 |

`por` 没有被自动映射到 NRST。`ScanInversion` 不会导致已由 ATPG 生成的串行字符串再次反相。以上补位规则是当前已支持 STIL 子集的求值方式，不代表所有方言、显式补位属性和多 V Shift 都已实现。

## 使用方法

桌面版选择“P2506 已确认入口配置（固定 17 引脚）”，时间倍率选 `1` 或 `10`，输出使用新的空目录。该配置使用 PA0～PA15、NRST；通用模式仍使用引脚选择表。

命令行示例：

```powershell
stil-to-ni P2506_TOP_stuck.scan.stil -o out-p2506-1x --profile p2506-20261014 --expand-scan --compile
stil-to-ni P2506_TOP_stuck.scan.stil -o out-p2506-10x --profile p2506-20261014 --time-scale 10 --expand-scan --compile
```

P2506 配置仅适用于 SHA-256 为 `71cc957ffd53815c253c9f85716aa1f98d08fb14bca4e925e44a48290b583ffc` 的未压缩 STIL 文件。新版本或 gzip 文件字节哈希不同，会拒绝套用旧配置；不能仅改配置哈希而跳过语义复核。

其他项目默认 `fixed_policy=error`、`high_z_policy=error`。工程分析确需保留冲突 Fixed 或把高阻比较映射为 M 时，分别显式使用 `--fixed-policy preserve_fixed_with_diagnostic`、`--high-z-policy midband`。P2506 配置自身确定这两个策略。M 的电气等价仍须由机台负载、阈值和真实波形验证。

## 本地验证

- 20 项合成回归在 `python -O -m unittest discover -s tests -v` 下通过，覆盖上下文补位、首 unload/末 load 缺参、Fixed 冲突及作用域、空 V、T/V 区别、不同 WFT 边沿、精确缩放、入口守卫、单周期最终 scan/halt、未知执行语句及输出防覆盖。
- P2506：3,654,071 周期；`test_setup` 1 次、186 周期；`load_unload` 649 次；`multiclock_capture` 652 次。
- PA5 有参数的短链前补共 648 处，首次 cycle 187；补位 Z→X，有效 5,623 位顺序不变。缺失整个参数的调用单独记录。
- capture Fixed 冲突共 1,304 周期，首次 cycle 5,814；每次 capture 第 4、5 个 V 保持 PA1=0。
- NRST 项目覆盖 186 周期，cycle 186 在 `pattern_0` 恢复 X。
- 全量展开后与既有 NRST 修正版的 17 引脚有效波形事件逐周期比较零差异；649 个共同标签位置一致，24 处 M 位置一致。历史文件额外的包装标签由比较报告单独列出。
- 原速与 10 倍版的全部 348 个时间字段精确乘 10；向量文件逐字节相同，timing 均通过本机 NI `Timing.xsd`。
- 本机 NI Digital Pattern Compiler 19.0.0 / Build 5.3.1.52024 对紧凑和展开格式进行编译、反编译；完整代码、pin 顺序、标签及 timeset 引用核对，只有空白、注释与 timeset 声明顺序被规范化。
- P2601 对照：12 引脚、4,345,626 周期、初始化 86 周期，在通用严格模式下生成；未应用 P2506 配置。setup/shift 和 capture 的不同周期保留。

`scripts/compare_expanded.py` 独立读取两份展开 NI 文本和各自 timing，比较每个执行周期的有效驱动、比较、脉冲事件、周期、halt 及共同标签。它不复用转换器解析器，不用于验证压缩控制流，也不把文件一致性宣称为硬件等价。

## PWD 时间轴

`macro_timeline.csv` 保存宏中每个 V 的零基执行周期、STIL 源行、timeset、周期时长及所有输出引脚状态。P2506 初始化 PA5 在相邻向量中出现 58 次 0→1 跳变，第一次为 cycle 19；这只是整个初始化的边沿计数，不能直接当作密码位数。

原速初始化时长为 18.6 µs，10 倍版为 186 µs。PA5 的逐向量翻转随周期整体缩放，与 PA0/PA2 返回型脉冲一同保留原有顺序。NRST 的覆盖范围由宏实例识别，不依赖输出文件行号。

## 构建产物与边界

主要新增文件：

- `build_manifest.json`：输入、配置、脚本和输出 hash；调用周期范围；编译、反编译、机台加载与硬件运行的独立状态。
- `source_semantics_report.json`：Fixed 冲突、补位来源、缺失参数及 NRST 有意偏离原 STIL 的记录。
- `macro_timeline.csv`：PWD / 初始化逐周期时间轴。
- `*.compile.json`、`*.readback.digipatsrc`：官方编译命令、版本输出、返回码、二进制 hash 与反编译核对证据。

当前仍是受限 STIL 前端：不支持复杂控制流、嵌套或多个 V 的 Shift、嵌入 join、多平面 WFCMap 求值、符号时序表达式、一个 WFT/引脚下多个比较时刻或脉冲形状。前置 `\j` 仅接受已展平的单平面值，随后仍做宽度与波形存在性检查。

机台 Editor/驱动加载、完整 scan PASS/FAIL、高阻电气等价、被省略引脚的机台替代条件仍为 unknown。逻辑 pinmap 仅供编译；本次文件级验证不解决原报告中二进制加载错误的机台根因。
